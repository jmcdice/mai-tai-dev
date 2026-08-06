"""Reconnecting after a session rotation.

The supervisor rotates each bot's session roughly daily. Before this, every
rotation cold-started the CLI on `/mai-tai start`, so the human got a
"Mai-tai mode activated!" greeting every night from a bot that had forgotten
everything. Two pieces fix that, and both are tested here: a home base that
waits without speaking, and a memory context the agent can pull on startup.
"""

import httpx
import pytest

from mai_tai_mcp import server
from mai_tai_mcp.backend import MaiTaiBackend
from mai_tai_mcp.config import MaiTaiConfig

WORKSPACE_ID = "11111111-1111-1111-1111-111111111111"


def make_backend(handler) -> MaiTaiBackend:
    config = MaiTaiConfig(
        api_url="http://backend:8000", api_key="mt_test", workspace_id=WORKSPACE_ID
    )
    backend = MaiTaiBackend(config)
    backend.workspace_id = config.workspace_id
    backend.workspace_name = "test-ws"
    backend._client = httpx.Client(
        base_url=config.api_url, transport=httpx.MockTransport(handler)
    )
    return backend


@pytest.fixture(autouse=True)
def reset_server_state(monkeypatch):
    # pytest closes stdin, which the poll loop reads as "the CLI exited".
    # Real sessions hold it open; pin it so the loop actually runs.
    monkeypatch.setattr(server, "_is_stdin_closed", lambda: False)
    server._cancel_event.clear()
    server.shutting_down = False
    server._chat_in_progress = False
    yield
    server._cancel_event.clear()
    server.shutting_down = False
    server._chat_in_progress = False


# ---------------------------------------------------------------------------
# The quiet home base
# ---------------------------------------------------------------------------


def test_poll_returns_unseen_without_sending_anything():
    """The whole point: listen without speaking. A reconnect that posts a
    message is the nightly greeting spam we're removing."""
    posted = []

    def handler(request):
        if request.method == "POST":
            posted.append(request.url.path)
            return httpx.Response(200, json={"id": "m1"})
        return httpx.Response(
            200, json={"messages": [{"id": "u1", "content": "you up?", "user_id": "u"}]}
        )

    messages = server._poll_for_unseen(make_backend(handler), poll_interval=0.01)

    assert [m["content"] for m in messages] == ["you up?"]
    assert posted == []  # nothing sent to the workspace


def test_poll_keeps_waiting_while_queue_is_empty():
    """An empty queue must not be mistaken for a reply — the bot has to keep
    holding the line, which is what makes this usable as home base."""
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(200, json={"messages": []})
        return httpx.Response(
            200, json={"messages": [{"id": "u1", "content": "hey", "user_id": "u"}]}
        )

    messages = server._poll_for_unseen(make_backend(handler), poll_interval=0.01)

    assert calls["n"] == 3
    assert messages[0]["content"] == "hey"


def test_poll_stops_on_shutdown():
    """Rotation kills the CLI, closing the MCP server's stdin. A poll that
    ignored that would leave an orphan polling the backend forever."""
    server.shutting_down = True
    handler = lambda request: httpx.Response(200, json={"messages": []})  # noqa: E731

    assert server._poll_for_unseen(make_backend(handler), poll_interval=0.01) is None


def test_poll_survives_a_backend_blip():
    """The backend restarts under the bots regularly. A transient error must
    not end the wait — that would drop the bot out of mai-tai mode."""
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, text="down")
        return httpx.Response(
            200, json={"messages": [{"id": "u1", "content": "back", "user_id": "u"}]}
        )

    messages = server._poll_for_unseen(make_backend(handler), poll_interval=0.01)

    assert messages[0]["content"] == "back"


@pytest.mark.asyncio
async def test_wait_for_human_acknowledges_and_returns_messages():
    acked = []

    def handler(request):
        if request.url.path.endswith("/acknowledge"):
            acked.append(request.url.path)
            return httpx.Response(200, json={})
        if request.method == "POST":
            return httpx.Response(200, json={"id": "m1"})
        return httpx.Response(
            200,
            json={
                "messages": [
                    {"id": "u1", "content": "one", "user_id": "u"},
                    {"id": "u2", "content": "two", "user_id": "u"},
                ]
            },
        )

    server._backend = make_backend(handler)
    result = await server.wait_for_human()

    assert result["status"] == "response_received"
    assert result["response"] == "one\n\ntwo"
    assert acked, "unacknowledged messages would be re-delivered forever"


@pytest.mark.asyncio
async def test_wait_for_human_is_a_no_op_in_driver_mode(monkeypatch):
    """Containerised agents get messages as prompts; blocking would deadlock
    the turn rather than reconnect anything."""
    monkeypatch.setattr(server, "DRIVER_MODE", True)

    result = await server.wait_for_human()

    assert result["status"] == "not_applicable"


# ---------------------------------------------------------------------------
# Memory context on startup
# ---------------------------------------------------------------------------


def test_memory_context_action_returns_assembled_context(tmp_path, monkeypatch):
    """Host bots had no way to pull memory at session start, so they never did.
    `context` is that way in."""
    monkeypatch.setenv("MAI_TAI_MEMORY_DIR", str(tmp_path))
    (tmp_path / "MEMORY.md").write_text("Joey prefers casual tone")
    (tmp_path / "journal").mkdir()
    (tmp_path / "journal" / "2026-08-05.md").write_text("- [22:00] shipped the fix")

    server._backend = make_backend(lambda r: httpx.Response(200, json={}))
    result = server.memory(action="context")

    assert result["status"] == "ok"
    assert "casual tone" in result["context"]
    assert "shipped the fix" in result["context"]


def test_unknown_memory_action_mentions_context(tmp_path, monkeypatch):
    monkeypatch.setenv("MAI_TAI_MEMORY_DIR", str(tmp_path))
    server._backend = make_backend(lambda r: httpx.Response(200, json={}))

    result = server.memory(action="bogus")

    assert result["status"] == "error"
    assert "context" in result["error"]
