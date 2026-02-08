"""MCP server for mai-tai AI agent collaboration platform."""

import asyncio
import os
import select
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from .backend import MaiTaiBackend, MaiTaiBackendError, create_backend
from .config import ConfigurationError, get_config, is_project_configured

# Load .env from current working directory BEFORE any config is read.
# This allows per-project configuration to override global env vars.
load_dotenv()


def _is_stdin_closed() -> bool:
    """Check if stdin has been closed (client disconnected).

    This is used to detect when the MCP client (e.g., Claude) has exited,
    so we can stop polling and let the server shut down gracefully.

    On Unix, we use select() to check if stdin is readable. If stdin is
    closed, select() returns it as readable but reading returns empty.

    On Windows, we check if stdin is a valid file descriptor.
    """
    if sys.platform == "win32":
        # Windows: check if stdin is still valid
        try:
            # If stdin is closed, this will raise an error
            os.fstat(sys.stdin.fileno())
            return False
        except (OSError, ValueError):
            return True
    else:
        # Unix: use select to check if stdin is readable
        try:
            # Check if stdin has data or is closed (both make it "readable")
            readable, _, _ = select.select([sys.stdin], [], [], 0)
            if readable:
                # stdin is readable - check if it's EOF (closed)
                # We peek by reading with a non-blocking check
                # If the file is at EOF, read() returns empty string
                old_flags = None
                try:
                    import fcntl
                    fd = sys.stdin.fileno()
                    old_flags = fcntl.fcntl(fd, fcntl.F_GETFL)
                    fcntl.fcntl(fd, fcntl.F_SETFL, old_flags | os.O_NONBLOCK)
                    data = sys.stdin.buffer.peek(1)
                    if data == b'':
                        return True  # EOF - stdin closed
                except (OSError, ValueError, BlockingIOError):
                    pass
                finally:
                    if old_flags is not None:
                        try:
                            fcntl.fcntl(fd, fcntl.F_SETFL, old_flags)
                        except (OSError, ValueError):
                            pass
            return False
        except (OSError, ValueError):
            return True  # Error checking stdin - assume closed

# ============================================================================
# Load Agent Instructions from Prompt File
# ============================================================================

def _load_agent_instructions() -> str:
    """Load agent instructions from the prompts directory.

    Loads once at module import time. Fails fast if the file is missing.

    Returns:
        The contents of agent_instructions.md

    Raises:
        RuntimeError: If the prompt file cannot be found or read
    """
    prompts_dir = Path(__file__).parent / "prompts"
    instructions_file = prompts_dir / "agent_instructions.md"

    if not instructions_file.exists():
        raise RuntimeError(
            f"Missing agent instructions file: {instructions_file}\n"
            "This file is required for the MCP server to start."
        )

    try:
        return instructions_file.read_text(encoding="utf-8")
    except Exception as e:
        raise RuntimeError(
            f"Failed to read agent instructions: {instructions_file}\n"
            f"Error: {e}"
        ) from e


# Load instructions once at module import time
_AGENT_INSTRUCTIONS = _load_agent_instructions()

# ============================================================================
# Global State
# ============================================================================

# Flag for clean shutdown on SIGINT (Ctrl+C)
# When set to True, the server should finish current work and exit gracefully
shutting_down: bool = False

# Lock to prevent concurrent chat_with_human calls
# If True, a chat_with_human call is already in progress
_chat_in_progress: bool = False

# Event to signal cancellation of the current polling operation
# This allows the blocking wait to be interrupted cleanly when Claude cancels a tool call
_cancel_event: threading.Event = threading.Event()


def _handle_shutdown_signal(signum: int, frame: Any) -> None:
    """Handle SIGINT/SIGTERM for clean shutdown."""
    global shutting_down
    shutting_down = True
    print("\nReceived shutdown signal, finishing current work...", file=sys.stderr)


def _start_stdin_monitor() -> None:
    """Start a background thread that monitors stdin and triggers shutdown when it closes.

    This prevents zombie processes when the MCP client (e.g., Augment Agent) exits
    while the server is idle (not actively polling in chat_with_human).

    The thread runs as a daemon, so it will be automatically killed when the main
    thread exits. It checks stdin every 5 seconds and forces exit if stdin closes.
    """
    def monitor() -> None:
        global shutting_down
        while not shutting_down:
            if _is_stdin_closed():
                print("mai-tai-mcp: client disconnected, shutting down...", file=sys.stderr)
                shutting_down = True
                # Force exit - mcp.run() might not check the shutting_down flag
                os._exit(0)
            time.sleep(5)  # Check every 5 seconds

    t = threading.Thread(target=monitor, daemon=True, name="stdin-monitor")
    t.start()


# Create FastMCP server with externalized instructions
mcp = FastMCP(
    name="mai-tai-mcp",
    instructions=_AGENT_INSTRUCTIONS,
)

# Global backend client (initialized on first use)
_backend: Optional[MaiTaiBackend] = None


def get_backend() -> MaiTaiBackend:
    """Get or create the backend client instance."""
    global _backend
    if _backend is None:
        try:
            config = get_config()
            _backend = create_backend(config)
            _backend.connect()
        except Exception as e:
            raise MaiTaiBackendError(0, f"Failed to initialize mai-tai backend: {e}") from e
    return _backend


# ============================================================================
# HTTP Polling for Response Detection
# ============================================================================


def _wait_for_response_polling(
    backend: "MaiTaiBackend",
    after_message_id: str,
    timeout_seconds: int,
    poll_interval: float = 3.0,
) -> dict[str, Any] | None:
    """
    Wait for a human response using HTTP polling.

    Simple and reliable - polls for new messages every few seconds.
    Returns the response message or None on timeout/shutdown.

    IMPORTANT: This function checks for client disconnection (stdin closed)
    on each poll iteration. When the MCP client (e.g., Claude) exits, stdin
    is closed and we detect this to allow graceful shutdown instead of
    leaving orphaned processes polling forever.

    Args:
        backend: The backend client instance
        after_message_id: Only look for messages after this ID (the question we sent)
        timeout_seconds: How long to wait before timing out (0 = wait forever)
        poll_interval: How often to poll (default: 3 seconds)

    Returns:
        Response dict if received, None on timeout or if shutdown requested
    """
    global shutting_down
    start_time = time.time()

    # timeout_seconds=0 means wait forever (until response or shutdown)
    while timeout_seconds == 0 or time.time() - start_time < timeout_seconds:
        # Check if cancellation was requested (tool call cancelled by Claude)
        if _cancel_event.is_set():
            print("mai-tai-mcp: poll cancelled", file=sys.stderr)
            return None

        # Check if we should shut down (signal received or stdin closed)
        if shutting_down:
            print("mai-tai-mcp: shutdown requested, stopping poll", file=sys.stderr)
            return None

        if _is_stdin_closed():
            print("mai-tai-mcp: client disconnected (stdin closed), stopping poll", file=sys.stderr)
            shutting_down = True
            return None

        try:
            # Get messages after the question we sent
            result = backend.get_messages(limit=10, after=after_message_id)
            messages = result.get("messages", [])

            # Look for a user response (messages with user_id set)
            for msg in messages:
                if msg.get("user_id") is not None:
                    return {
                        "content": msg.get("content", ""),
                        "sender_name": msg.get("sender_name"),
                        "created_at": msg.get("created_at"),
                    }

            # No response yet, wait before polling again using Event.wait()
            # This can be interrupted by setting _cancel_event, unlike time.sleep()
            _cancel_event.wait(timeout=poll_interval)

        except Exception as e:
            print(f"Polling error: {e}", file=sys.stderr)
            _cancel_event.wait(timeout=poll_interval)

    return None  # Timeout


# ============================================================================
# Primary Tool - Chat with Human (HOME BASE)
# ============================================================================


@mcp.tool()
def chat_with_human(
    message: str,
) -> dict[str, Any]:
    """Send a message to the human and WAIT for their response. This is your HOME BASE.

    ⚠️ ACTIVATION: When user says "start mai-tai mode" (or similar), call this tool IMMEDIATELY
    as your VERY FIRST action. Do NOT respond with normal text first - this tool call IS your response.

    CRITICAL: In mai-tai mode, you must ALWAYS return to this tool after completing any task.
    This keeps you connected to the human. Never finish work and go idle - always call this
    tool to report what you did and wait for the next instruction.

    USE THIS TOOL WHEN:
    - User says "start mai-tai mode" → Call IMMEDIATELY as first action
    - You finished a task and need to report results ("Done! Here's what I did...")
    - You need input, clarification, or a decision from the human
    - You have a question that requires an answer before proceeding
    - You're ready for the next instruction

    DO NOT USE THIS TOOL FOR:
    - Quick acknowledgments like "Got it, starting now..." (use update_status instead)
    - Progress updates while working (use update_status instead)
    - Status updates that don't need a response (use update_status instead)

    Args:
        message: What you want to say to the human (be clear and conversational)

    Returns:
        Dictionary with the human's response
    """
    global _chat_in_progress

    # Prevent concurrent calls - if a chat is already in progress, reject this call
    if _chat_in_progress:
        return {
            "status": "already_in_progress",
            "error": "A chat_with_human call is already waiting for a response. Wait for it to complete before calling again.",
        }

    _chat_in_progress = True
    _cancel_event.clear()  # Reset cancellation state for this call
    try:
        return _chat_with_human_impl(message)
    except (KeyboardInterrupt, asyncio.CancelledError, SystemExit):
        # Tool was cancelled/interrupted by the user - exit gracefully
        _cancel_event.set()  # Signal any waiting polls to stop
        return {
            "status": "cancelled",
            "note": "Chat was interrupted by user.",
        }
    finally:
        _chat_in_progress = False
        _cancel_event.clear()  # Clean up for next call


def _chat_with_human_impl(
    message: str,
) -> dict[str, Any]:
    """Internal implementation of chat_with_human.

    Flow:
    1. Send the agent's message
    2. Check for unseen user messages FIRST
    3. If unseen messages exist: acknowledge them and return immediately (no blocking)
    4. If no unseen messages: poll and wait for new input
    """
    backend = get_backend()

    # API keys are bound to a workspace - verify we have one
    if not backend.workspace_id:
        return {
            "status": "error",
            "error": "No workspace bound to this API key.",
        }

    # Send the message to the workspace
    sent_message = backend.send_message(
        content=message,
        metadata={"type": "chat", "awaiting_response": True},
    )

    # Check for unseen messages FIRST - these are messages the user sent while
    # the agent was busy doing work. We want to return them immediately so the
    # agent doesn't miss anything.
    unseen_result = backend.get_messages(unseen=True)
    unseen_messages = unseen_result.get("messages", [])

    if unseen_messages:
        # Found unseen messages! Acknowledge them and return immediately.
        message_ids = [msg["id"] for msg in unseen_messages]
        backend.acknowledge_messages(message_ids)

        # Format all unseen messages for the agent
        formatted_messages = []
        for msg in unseen_messages:
            formatted_messages.append(msg.get("content", ""))

        combined_response = "\n\n".join(formatted_messages)

        return {
            "status": "response_received",
            "response": combined_response,
            "workspace": backend.workspace_name,
            "note": f"Returned {len(unseen_messages)} message(s) that were sent while you were working.",
        }

    # No unseen messages - wait for new response using HTTP polling
    response = _wait_for_response_polling(
        backend=backend,
        after_message_id=sent_message["id"],
        timeout_seconds=0,  # 0 = wait forever
        poll_interval=3.0,  # Check every 3 seconds
    )

    if response:
        # Acknowledge this new message too
        # Note: The polling function returns the message content, not the full message
        # We need to get the message ID to acknowledge it. For now, we'll acknowledge
        # by fetching unseen again (which should now include this message).
        unseen_after_poll = backend.get_messages(unseen=True)
        if unseen_after_poll.get("messages"):
            message_ids = [msg["id"] for msg in unseen_after_poll["messages"]]
            backend.acknowledge_messages(message_ids)

        return {
            "status": "response_received",
            "response": response["content"],
            "workspace": backend.workspace_name,
        }

    # This shouldn't happen with timeout_seconds=0, but handle it gracefully
    return {
        "status": "no_response",
        "workspace": backend.workspace_name,
        "note": "Unexpected: no response received. Human may respond later - check back with get_messages if needed.",
    }


# ============================================================================
# Status Update Tool (Non-blocking)
# ============================================================================


@mcp.tool()
def update_status(
    message: str,
) -> dict[str, Any]:
    """Send a status update to the human WITHOUT waiting for a response. Non-blocking.

    This tool sends a message and returns IMMEDIATELY so you can continue working.
    Use this for progress updates, acknowledgments, and status reports while you work.

    USE THIS TOOL WHEN:
    - Acknowledging a task: "Got it, starting on that now..."
    - Progress updates: "Finished the backend, moving to frontend..."
    - Milestones: "Tests passing, about to commit..."
    - Quick status: "Still working on this, found an interesting edge case..."

    DO NOT USE THIS TOOL WHEN:
    - You need a response before continuing (use chat_with_human)
    - You're done with a task (use chat_with_human to report and get next task)
    - You have a question (use chat_with_human)

    IMPORTANT: After completing any task, you MUST call chat_with_human (not this tool)
    to report results and wait for the next instruction. This tool is for updates WHILE
    you're working, not for when you're done.

    Args:
        message: Status update to send (be concise)

    Returns:
        Dictionary confirming the message was sent (does NOT wait for response)
    """
    backend = get_backend()

    # Verify we have a bound workspace
    if not backend.workspace_id:
        return {
            "status": "error",
            "error": "No workspace bound to this API key. Cannot send status update.",
        }

    # Send the status update message
    sent_message = backend.send_message(
        content=message,
        metadata={"type": "status_update", "awaiting_response": False},
    )

    # Return immediately - no waiting for response
    return {
        "status": "sent",
        "message_id": sent_message["id"],
        "workspace": backend.workspace_name,
        "note": "Status update sent. Continue with your work - no response expected.",
    }


# ============================================================================
# Message Tools
# ============================================================================


@mcp.tool()
def get_messages(
    limit: int = 50,
) -> dict[str, Any]:
    """Get messages from the workspace.

    Args:
        limit: Maximum number of messages to return (default: 50)

    Returns:
        Dictionary with 'messages' list and workspace info
    """
    backend = get_backend()

    # Verify we have a bound workspace
    if not backend.workspace_id:
        return {
            "status": "error",
            "error": "No workspace bound to this API key.",
        }

    result = backend.get_messages(limit=limit)
    result["workspace"] = backend.workspace_name
    return result


# ============================================================================
# Utility Tools
# ============================================================================


@mcp.tool()
def get_project_info() -> dict[str, Any]:
    """Get information about the connected mai-tai project.

    Returns:
        Project details including id, name, and connection status
    """
    backend = get_backend()
    return {
        "workspace_id": backend.workspace_id,
        "workspace_name": backend.workspace_name,
        "api_url": backend.config.api_url,
        "status": "connected",
    }


# ============================================================================
# Main Entry Point
# ============================================================================


def main() -> None:
    """Main entry point for the MCP server.

    v2 behavior:
    - Fail fast on configuration errors (missing env vars)
    - Register signal handlers for clean shutdown
    - Exit cleanly on SIGINT (Ctrl+C) with status 0
    - Exit with non-zero status on fatal errors
    """
    global shutting_down

    # Register signal handlers for clean shutdown
    signal.signal(signal.SIGINT, _handle_shutdown_signal)
    signal.signal(signal.SIGTERM, _handle_shutdown_signal)

    try:
        # Check if this project is configured for mai-tai
        # If not, exit silently (no error, no output) to avoid noise in non-mai-tai projects
        if not is_project_configured():
            sys.exit(0)

        # Validate configuration early (fail fast on missing env vars)
        # This will raise ConfigurationError with a clear message if config is invalid
        config = get_config()
        print(f"mai-tai-mcp: connecting to {config.api_url}", file=sys.stderr)

        # Start background stdin monitor to detect client disconnection
        # This prevents zombie processes when the client exits while server is idle
        _start_stdin_monitor()

        # Run the server with stdio transport
        mcp.run(transport="stdio")

        # Clean exit after server stops
        if shutting_down:
            print("mai-tai-mcp: shutdown complete", file=sys.stderr)
            sys.exit(0)

    except ConfigurationError as e:
        # Configuration errors are fatal - clear message, non-zero exit
        print(f"\n{e}", file=sys.stderr)
        sys.exit(1)

    except KeyboardInterrupt:
        # User pressed Ctrl+C - clean exit
        print("\nmai-tai-mcp: shutdown complete", file=sys.stderr)
        sys.exit(0)

    except Exception as e:
        # Unexpected error - log and exit with non-zero status
        print(f"mai-tai-mcp fatal error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
