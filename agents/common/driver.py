#!/usr/bin/env python3
"""Mai-Tai agent driver: per-turn CLI invocation with session resume.

Replaces the old "eternal blocking session" model (agent parked inside a
chat_with_human tool call for hours, fighting idle timeouts and the ~27h
process limit). Instead, the driver:

  1. polls the workspace for unseen user messages (3s)
  2. invokes the agent CLI for ONE turn, resuming the previous session
  3. posts the turn result back to the workspace
  4. repeats — forever, cheaply, with no long-lived CLI process

Session continuity comes from the CLI's own resume support (claude -p
--resume). When a session chain starts fresh, the driver injects the
persistent memory context (MEMORY.md + recent journal + lessons) into the
first prompt. On SIGTERM it runs a short "flush" turn so the agent can save
state before the container stops.

Stdlib only — no pip dependencies. The memory-context assembly mirrors
mai_tai_mcp/memory.py:build_session_context (kept in sync by hand; the
driver must not depend on the MCP package).
"""

import json
import os
import signal
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API_URL = os.environ["MAI_TAI_API_URL"].rstrip("/")
API_KEY = os.environ["MAI_TAI_API_KEY"]
WORKSPACE_ID = os.environ["MAI_TAI_WORKSPACE_ID"]
AGENT_NAME = os.environ.get("AGENT_NAME", "Agent")
AGENT_MODEL = os.environ.get("AGENT_MODEL", "sonnet")
AGENT_RUNTIME = os.environ.get("AGENT_RUNTIME", "claude-code")
WORKDIR = Path(os.environ.get("AGENT_WORKDIR", "/home/agent/workspace"))
MEMORY_DIR = Path(os.environ.get("MAI_TAI_MEMORY_DIR", "/home/agent/memory"))
MCP_CONFIG = os.environ.get("AGENT_MCP_CONFIG", "/tmp/mcp-config.json")

POLL_INTERVAL = float(os.environ.get("AGENT_POLL_INTERVAL", "3"))
TURN_TIMEOUT = int(os.environ.get("AGENT_TURN_TIMEOUT", "3600"))
FLUSH_TIMEOUT = int(os.environ.get("AGENT_FLUSH_TIMEOUT", "25"))

STATE_FILE = MEMORY_DIR / "state" / "driver.json"

_shutdown = False


def log(msg: str) -> None:
    print(f"[driver] {msg}", flush=True)


# ---------------------------------------------------------------------------
# Mai-Tai API (stdlib HTTP)
# ---------------------------------------------------------------------------


def _request(method: str, path: str, params: dict | None = None, body: dict | None = None) -> dict | None:
    """Call the Mai-Tai API. Returns parsed JSON, or None on failure."""
    url = f"{API_URL}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "X-API-Key": API_KEY,
            "X-Workspace-ID": WORKSPACE_ID,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        log(f"API {method} {path} -> HTTP {e.code}: {e.read().decode()[:200]}")
    except Exception as e:
        log(f"API {method} {path} failed: {e}")
    return None


def get_unseen_messages() -> list[dict]:
    result = _request("GET", "/api/v1/mcp/messages", params={"unseen": "true", "limit": 50})
    return result.get("messages", []) if result else []


def acknowledge(message_ids: list[str]) -> None:
    _request("POST", "/api/v1/mcp/messages/acknowledge", body={"message_ids": message_ids})


def post_message(content: str) -> None:
    _request("POST", "/api/v1/mcp/messages", body={"content": content})


# ---------------------------------------------------------------------------
# Driver state + memory context
# ---------------------------------------------------------------------------


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except (OSError, ValueError):
        return {"session_id": None, "turns": 0}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state))


def build_memory_context(lookback_days: int = 2) -> str:
    """MEMORY.md + recent journal + lessons (mirrors mai_tai_mcp.memory)."""
    parts: list[str] = []

    memory_file = MEMORY_DIR / "MEMORY.md"
    if memory_file.exists():
        content = memory_file.read_text(encoding="utf-8").strip()
        if content:
            parts.append("## Curated memory (MEMORY.md)\n" + content)

    journal_dir = MEMORY_DIR / "journal"
    if journal_dir.is_dir():
        days = sorted(journal_dir.glob("*.md"), reverse=True)[:lookback_days]
        for f in reversed(days):
            content = f.read_text(encoding="utf-8").strip()
            if content:
                parts.append(f"## Journal {f.stem}\n" + content)

    lessons = MEMORY_DIR / "tasks" / "lessons.md"
    if lessons.exists():
        content = lessons.read_text(encoding="utf-8").strip()
        if content:
            parts.append("## Lessons learned\n" + content)

    return "\n\n".join(parts) if parts else "(no persistent memory yet)"


def session_start_preamble() -> str:
    return (
        "[NEW SESSION] You are starting a fresh session. "
        "Your persistent memory follows — read it before acting.\n\n"
        f"{build_memory_context()}\n\n"
        "---\n\n"
    )


# ---------------------------------------------------------------------------
# Turn execution
# ---------------------------------------------------------------------------


def build_turn_cmd(prompt: str, session_id: str | None) -> list[str]:
    if AGENT_RUNTIME == "claude-code":
        cmd = [
            "claude",
            "-p", prompt,
            "--output-format", "json",
            "--dangerously-skip-permissions",
            "--model", AGENT_MODEL,
            "--mcp-config", MCP_CONFIG,
        ]
        if session_id:
            cmd += ["--resume", session_id]
        return cmd
    if AGENT_RUNTIME == "codex":
        # Model, sandbox, approvals, and MCP servers come from ~/.codex/config.toml
        # (written by the codex entrypoint). codex exec prints only the final
        # agent message to stdout; session state lives in ~/.codex/sessions,
        # resumed via the --last sentinel.
        if session_id:
            return ["codex", "exec", "resume", "--last", prompt]
        return ["codex", "exec", prompt]
    raise RuntimeError(f"Runtime '{AGENT_RUNTIME}' has no driver adapter yet")


def parse_turn_output(stdout: str) -> tuple[str | None, str | None]:
    """Extract (result_text, session_id) from the CLI's turn output.

    claude-code: single JSON object on stdout ({"result": ..., "session_id": ...}).
    codex: the final agent message is stdout verbatim; "last" is the session
    sentinel (resumed with `codex exec resume --last`).
    """
    if AGENT_RUNTIME == "codex":
        text = stdout.strip()
        return (text if text else None), "last"

    for line in reversed(stdout.strip().splitlines()):
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict) and "result" in obj:
            return obj.get("result") or "", obj.get("session_id")
    return None, None


def run_turn(prompt: str, session_id: str | None, timeout: int = TURN_TIMEOUT) -> dict:
    """Run one CLI turn. Returns {ok, result, session_id, error}."""
    env = dict(os.environ)
    env["MAI_TAI_DRIVER_MODE"] = "1"
    env["MAI_TAI_MEMORY_DIR"] = str(MEMORY_DIR)

    cmd = build_turn_cmd(prompt, session_id)
    log(f"turn start (session={session_id or 'new'}, prompt={len(prompt)} chars)")
    try:
        proc = subprocess.run(
            cmd, cwd=WORKDIR, env=env, capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"turn timed out after {timeout}s", "session_id": session_id}

    result, new_session_id = parse_turn_output(proc.stdout)
    if proc.returncode != 0 or result is None:
        stderr_tail = (proc.stderr or "")[-500:]
        return {
            "ok": False,
            "error": f"exit={proc.returncode} stderr={stderr_tail}",
            "session_id": session_id,
        }

    log(f"turn done (session={new_session_id}, result={len(result)} chars)")
    return {"ok": True, "result": result, "session_id": new_session_id or session_id}


def execute_messages(state: dict, prompt_body: str) -> dict:
    """Run a turn, retrying once with a fresh session if resume fails."""
    session_id = state.get("session_id")

    if session_id is None:
        outcome = run_turn(session_start_preamble() + prompt_body, None)
    else:
        outcome = run_turn(prompt_body, session_id)
        if not outcome["ok"]:
            # Resume chains can expire/corrupt; fall back to a fresh session
            # with the memory context so continuity comes from disk.
            log(f"resumed turn failed ({outcome['error']}); retrying with fresh session")
            outcome = run_turn(session_start_preamble() + prompt_body, None)

    if outcome["ok"]:
        state["session_id"] = outcome["session_id"]
        state["turns"] = state.get("turns", 0) + 1
        save_state(state)
    return outcome


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def _handle_sigterm(signum, frame):
    global _shutdown
    _shutdown = True
    log("SIGTERM received — will flush and exit")


def flush_before_exit(state: dict) -> None:
    """Give the agent one short turn to save state before the container stops."""
    session_id = state.get("session_id")
    if not session_id:
        return
    log("running memory flush turn")
    run_turn(
        "[SESSION ENDING] The container is stopping right now. If there is any "
        "in-flight work, decision, or context your future self will need, save "
        "it IMMEDIATELY with the journal and memory tools. Reply with just 'ok'.",
        session_id,
        timeout=FLUSH_TIMEOUT,
    )


def main() -> None:
    signal.signal(signal.SIGTERM, _handle_sigterm)
    signal.signal(signal.SIGINT, _handle_sigterm)

    state = load_state()
    log(
        f"online: workspace={WORKSPACE_ID} runtime={AGENT_RUNTIME} "
        f"model={AGENT_MODEL} resumed_session={state.get('session_id')}"
    )
    post_message(
        f"🟢 {AGENT_NAME} online — {AGENT_RUNTIME}/{AGENT_MODEL}. "
        "Send me a message and I'll pick it up within a few seconds."
    )

    while not _shutdown:
        messages = get_unseen_messages()
        if not messages:
            time.sleep(POLL_INTERVAL)
            continue

        # Ack first: a poison message must not wedge the loop forever.
        acknowledge([m["id"] for m in messages])
        prompt_body = "\n\n".join(m.get("content", "") for m in messages)

        outcome = execute_messages(state, prompt_body)
        if outcome["ok"]:
            if outcome["result"].strip():
                post_message(outcome["result"])
        else:
            log(f"turn failed: {outcome['error']}")
            post_message(
                "⚠️ I hit an error processing that message "
                f"(`{outcome['error'][:200]}`). My session was reset — "
                "please resend or rephrase."
            )
            state["session_id"] = None
            save_state(state)

    flush_before_exit(state)
    log("driver exiting")


if __name__ == "__main__":
    main()
