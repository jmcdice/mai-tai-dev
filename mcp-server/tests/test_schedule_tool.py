"""The schedule tool's local guardrails.

The interesting behaviour isn't the happy path — that's the backend's job and
it has its own tests. It's what happens when the agent gets an argument wrong,
because the obvious wiring for that turns a typo into a dead container.
"""

import httpx
import pytest

from mai_tai_mcp.backend import MaiTaiBackend, _detail
from mai_tai_mcp.config import MaiTaiConfig
from mai_tai_mcp.errors import FatalRuntimeError


def make_backend(handler) -> MaiTaiBackend:
    """A backend whose HTTP client is a canned-response transport."""
    config = MaiTaiConfig(
        api_url="http://backend:8000",
        api_key="mt_test",
        workspace_id="11111111-1111-1111-1111-111111111111",
    )
    backend = MaiTaiBackend(config)
    backend.workspace_id = config.workspace_id
    backend._client = httpx.Client(
        base_url=config.api_url, transport=httpx.MockTransport(handler)
    )
    return backend


# ---------------------------------------------------------------------------
# Argument errors must not be fatal
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", [400, 404, 409, 422])
def test_argument_errors_return_instead_of_killing_the_agent(status):
    """classify_http_error() maps unknown 4xx to FatalRuntimeError, and the
    driver answers that by terminating the container. Right for a revoked API
    key; catastrophic for a mistyped cron expression, which is a 422. These
    have to come back as a result the agent can read and retry."""
    backend = make_backend(
        lambda request: httpx.Response(status, json={"detail": "nope"})
    )
    result = backend.create_schedule({"name": "x"})
    assert result == {"status": "error", "detail": "nope"}


def test_auth_failure_is_still_fatal():
    """The flip side: a revoked key must keep its old behaviour."""
    backend = make_backend(lambda request: httpx.Response(401, json={"detail": "bad key"}))
    with pytest.raises(FatalRuntimeError):
        backend.list_schedules()


def test_server_error_stays_recoverable():
    from mai_tai_mcp.errors import RecoverableError

    backend = make_backend(lambda request: httpx.Response(503, text="down"))
    with pytest.raises(RecoverableError):
        backend.list_schedules()


def test_delete_handles_204_with_no_body():
    backend = make_backend(lambda request: httpx.Response(204))
    assert backend.delete_schedule("abc") == {"status": "ok"}


# ---------------------------------------------------------------------------
# Error bodies have to be legible to the agent
# ---------------------------------------------------------------------------


def test_detail_flattens_pydantic_validation_errors():
    """FastAPI reports 422s as nested per-field structures. The agent needs to
    be told which field was wrong, not handed a tree to interpret."""
    response = httpx.Response(
        422,
        json={
            "detail": [
                {"loc": ["body", "timezone"], "msg": "Field required"},
                {"loc": ["body", "cron_expression"], "msg": "Invalid cron expression"},
            ]
        },
    )
    detail = _detail(response)
    assert "timezone: Field required" in detail
    assert "cron_expression: Invalid cron expression" in detail


def test_detail_passes_through_plain_strings():
    response = httpx.Response(409, json={"detail": "limit 25 reached"})
    assert _detail(response) == "limit 25 reached"


def test_detail_survives_a_non_json_body():
    response = httpx.Response(400, text="<html>gateway barf</html>")
    assert "gateway barf" in _detail(response)


# ---------------------------------------------------------------------------
# The tool refuses incomplete calls before spending a round trip
# ---------------------------------------------------------------------------


def test_create_requires_the_fields_it_needs(monkeypatch):
    from mai_tai_mcp import server

    def boom(*args, **kwargs):  # pragma: no cover - must never be reached
        raise AssertionError("should not have called the backend")

    backend = make_backend(boom)
    monkeypatch.setattr(server, "get_backend", lambda: backend)

    result = server.schedule(action="create", name="Daily", prompt="do it")
    assert result["status"] == "error"
    # Says which ones, so the retry is one call rather than a guessing game
    assert "cron" in result["detail"] and "timezone" in result["detail"]


def test_timezone_is_never_inferred(monkeypatch):
    """A cron without a zone is the failure that hides: it runs, just at the
    wrong hour. The tool won't fill one in."""
    from mai_tai_mcp import server

    backend = make_backend(lambda request: httpx.Response(201, json={}))
    monkeypatch.setattr(server, "get_backend", lambda: backend)

    result = server.schedule(
        action="create", name="Daily", prompt="do it", cron="0 5 * * *"
    )
    assert result["status"] == "error"
    assert "timezone" in result["detail"]


def test_update_needs_a_task_id(monkeypatch):
    from mai_tai_mcp import server

    backend = make_backend(lambda request: httpx.Response(200, json={}))
    monkeypatch.setattr(server, "get_backend", lambda: backend)

    result = server.schedule(action="update", enabled=False)
    assert result["status"] == "error"
    assert "task_id" in result["detail"]


def test_unknown_action_lists_the_real_ones(monkeypatch):
    from mai_tai_mcp import server

    backend = make_backend(lambda request: httpx.Response(200, json={}))
    monkeypatch.setattr(server, "get_backend", lambda: backend)

    result = server.schedule(action="destroy")
    assert result["status"] == "error"
    assert "list" in result["detail"] and "delete" in result["detail"]


def test_update_sends_only_what_changed(monkeypatch):
    """PATCH semantics: an update that also shipped empty strings for every
    untouched field would blank the prompt on a rename."""
    from mai_tai_mcp import server

    sent = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        sent.update(json.loads(request.content))
        return httpx.Response(200, json={})

    backend = make_backend(handler)
    monkeypatch.setattr(server, "get_backend", lambda: backend)

    server.schedule(action="update", task_id="abc", name="New name")
    assert sent == {"name": "New name"}
