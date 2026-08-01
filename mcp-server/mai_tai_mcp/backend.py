"""Backend client for communicating with mai-tai API (v4 - user-level API keys).

This module provides the HTTP client for communicating with the Mai-Tai backend.
In v4, we support user-level API keys that work across all workspaces.
The workspace ID is sent via X-Workspace-ID header.
Uses structured error types from errors.py to classify failures
as recoverable (retry with backoff) or fatal (exit the process).
"""

from typing import Any, Optional

import httpx

from .config import MaiTaiConfig
from .errors import (
    FatalRuntimeError,
    MaiTaiError,
    RecoverableError,
    classify_http_error,
)


class MaiTaiBackendError(MaiTaiError):
    """Legacy error class for backward compatibility.

    New code should catch RecoverableError or FatalRuntimeError instead.
    """

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Backend error ({status_code}): {detail}")


class MaiTaiBackend:
    """Synchronous client for mai-tai backend API (v4 - user-level API keys).

    Uses synchronous httpx since MCP tools are called synchronously.
    HTTP errors are classified as recoverable or fatal using the errors module.

    Sends both X-API-Key and X-Workspace-ID headers to support user-level API keys.
    """

    def __init__(self, config: MaiTaiConfig):
        """Initialize backend client with configuration."""
        self.config = config
        self._client: Optional[httpx.Client] = None
        self.workspace_id: Optional[str] = None
        self.workspace_name: Optional[str] = None

    def _get_client(self) -> httpx.Client:
        """Get or create the HTTP client.

        Sends both X-API-Key and X-Workspace-ID headers.
        This supports both user-level and workspace-level API keys:
        - User-level keys: X-Workspace-ID is required
        - Workspace-level keys: X-Workspace-ID is ignored (key's workspace is used)
        """
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.config.api_url.rstrip("/"),
                headers={
                    "X-API-Key": self.config.api_key,
                    "X-Workspace-ID": self.config.workspace_id,
                },
                timeout=30.0,
            )
        return self._client

    def _handle_error(self, e: Exception, context: str = "") -> MaiTaiError:
        """Convert an exception to the appropriate MaiTaiError type.

        Args:
            e: The caught exception
            context: Optional context string for the error message

        Returns:
            RecoverableError or FatalRuntimeError based on the error type

        Raises:
            The appropriate error type (never returns normally for HTTP errors)
        """
        prefix = f"{context}: " if context else ""

        if isinstance(e, httpx.HTTPStatusError):
            # HTTP error - classify by status code
            error = classify_http_error(e.response.status_code, e.response.text)
            error.original_error = e
            raise error

        if isinstance(e, httpx.TimeoutException):
            # Timeout - always recoverable
            raise RecoverableError(f"{prefix}Request timed out", original_error=e)

        if isinstance(e, httpx.ConnectError):
            # Connection error - always recoverable
            raise RecoverableError(f"{prefix}Connection failed", original_error=e)

        if isinstance(e, httpx.RequestError):
            # Other request errors - treat as recoverable
            raise RecoverableError(f"{prefix}{str(e)}", original_error=e)

        # Unknown error type - treat as recoverable to be safe
        raise RecoverableError(f"{prefix}Unexpected error: {str(e)}", original_error=e)

    def connect(self) -> bool:
        """Verify connection and get workspace info.

        Raises:
            RecoverableError: For transient errors (retry with backoff)
            FatalRuntimeError: For permanent errors (auth failure, etc.)
        """
        try:
            client = self._get_client()
            response = client.get("/api/v1/mcp/auth/verify")
            response.raise_for_status()
            data = response.json()
            self.workspace_id = data["workspace_id"]
            self.workspace_name = data["workspace_name"]
            return True
        except (RecoverableError, FatalRuntimeError):
            raise  # Already classified
        except Exception as e:
            self._handle_error(e, "Failed to connect")

    def get_workspace(self) -> dict[str, Any]:
        """Get the workspace this API key is bound to.

        Raises:
            RecoverableError: For transient errors
            FatalRuntimeError: For permanent errors
        """
        try:
            client = self._get_client()
            response = client.get("/api/v1/mcp/workspace")
            response.raise_for_status()
            return response.json()
        except (RecoverableError, FatalRuntimeError):
            raise
        except Exception as e:
            self._handle_error(e, "Failed to get workspace")
            return {}  # Unreachable

    def send_message(
        self,
        content: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Send a message to the workspace.

        Raises:
            RecoverableError: For transient errors
            FatalRuntimeError: For permanent errors
        """
        try:
            client = self._get_client()
            payload: dict[str, Any] = {
                "content": content,
            }
            if metadata:
                payload["metadata"] = metadata

            response = client.post(
                "/api/v1/mcp/messages",
                json=payload,
            )
            response.raise_for_status()
            return response.json()
        except (RecoverableError, FatalRuntimeError):
            raise
        except Exception as e:
            self._handle_error(e, "Failed to send message")
            return {}  # Unreachable

    def get_messages(
        self,
        limit: int = 50,
        after: Optional[str] = None,
        unseen: bool = False,
    ) -> dict[str, Any]:
        """Get messages from the workspace.

        Args:
            limit: Maximum number of messages to return
            after: Get messages after this message ID
            unseen: If True, only return unseen user messages

        Raises:
            RecoverableError: For transient errors
            FatalRuntimeError: For permanent errors
        """
        try:
            client = self._get_client()
            params: dict[str, Any] = {"limit": limit}
            if after:
                params["after"] = after
            if unseen:
                params["unseen"] = "true"

            response = client.get(
                "/api/v1/mcp/messages",
                params=params,
            )
            response.raise_for_status()
            return response.json()
        except (RecoverableError, FatalRuntimeError):
            raise
        except Exception as e:
            self._handle_error(e, "Failed to get messages")
            return {}  # Unreachable

    def search_messages(self, query: str, limit: int = 10) -> dict[str, Any]:
        """Full-text search over the workspace's message history.

        Args:
            query: Search terms (2-200 chars)
            limit: Maximum results to return

        Raises:
            RecoverableError: For transient errors
            FatalRuntimeError: For permanent errors
        """
        try:
            client = self._get_client()
            response = client.get(
                "/api/v1/mcp/messages/search",
                params={"q": query, "limit": limit},
            )
            response.raise_for_status()
            return response.json()
        except (RecoverableError, FatalRuntimeError):
            raise
        except Exception as e:
            self._handle_error(e, "Failed to search messages")
            return {}  # Unreachable

    def acknowledge_messages(self, message_ids: list[str]) -> dict[str, Any]:
        """Mark messages as seen by the agent.

        Args:
            message_ids: List of message UUIDs to acknowledge

        Raises:
            RecoverableError: For transient errors
            FatalRuntimeError: For permanent errors
        """
        try:
            client = self._get_client()
            response = client.post(
                "/api/v1/mcp/messages/acknowledge",
                json={"message_ids": message_ids},
            )
            response.raise_for_status()
            return response.json()
        except (RecoverableError, FatalRuntimeError):
            raise
        except Exception as e:
            self._handle_error(e, "Failed to acknowledge messages")
            return {}  # Unreachable

    def close(self) -> None:
        """Close the client."""
        if self._client:
            self._client.close()
            self._client = None


def create_backend(config: Optional[MaiTaiConfig] = None) -> MaiTaiBackend:
    """Create a mai-tai backend client instance.

    Args:
        config: Optional configuration. If not provided, loads from environment.

    Returns:
        Configured MaiTaiBackend instance
    """
    if config is None:
        from .config import get_config

        config = get_config()

    return MaiTaiBackend(config)

