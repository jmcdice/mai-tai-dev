"""API key scope enforcement (core.scopes + deps.require_scope).

The column existed for a long time before anything read it, so these tests are
mostly about the enforcement actually biting: a read key must not be able to
post, and a key created before scopes meant anything must not lose access.
"""

from sqlalchemy import text

from tests.conftest import auth_headers, sync_engine


def make_key(client, user, scopes: list[str], name: str = "scoped") -> str:
    resp = client.post(
        f"/api/v1/workspaces/{user['workspace_id']}/api-keys",
        json={"name": name, "scopes": scopes},
        headers=auth_headers(user["token"]),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["key"]


def test_read_key_can_read_but_not_write(client, user_a):
    key = make_key(client, user_a, ["read"])
    headers = {"X-API-Key": key}

    assert client.get("/api/v1/mcp/messages", headers=headers).status_code == 200

    resp = client.post(
        "/api/v1/mcp/messages",
        json={"content": "hello", "agent_name": "test"},
        headers=headers,
    )
    assert resp.status_code == 403
    assert "write" in resp.json()["detail"]


def test_write_key_can_write_but_not_read(client, user_a):
    key = make_key(client, user_a, ["write"])
    headers = {"X-API-Key": key}

    resp = client.post(
        "/api/v1/mcp/messages",
        json={"content": "hello", "agent_name": "test"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text

    resp = client.get("/api/v1/mcp/messages", headers=headers)
    assert resp.status_code == 403
    assert "read" in resp.json()["detail"]


def test_scheduled_task_endpoints_are_scoped(client, user_a):
    read_only = {"X-API-Key": make_key(client, user_a, ["read"], name="ro")}

    assert client.get("/api/v1/mcp/scheduled-tasks", headers=read_only).status_code == 200

    resp = client.post(
        "/api/v1/mcp/scheduled-tasks",
        json={
            "name": "nope",
            "prompt": "should not be created",
            "cron_expression": "0 9 * * *",
            "timezone": "UTC",
        },
        headers=read_only,
    )
    assert resp.status_code == 403


def test_scopeless_key_is_denied_everything_but_can_still_identify_itself(client, user_a):
    """A powerless key should read as 'forbidden', never as 'bad credential'."""
    key = make_key(client, user_a, [], name="powerless")
    headers = {"X-API-Key": key}

    resp = client.get("/api/v1/mcp/auth/verify", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["scopes"] == []

    assert client.get("/api/v1/mcp/messages", headers=headers).status_code == 403
    assert client.get("/api/v1/mcp/workspace", headers=headers).status_code == 403


def test_verify_reports_scopes(client, user_a):
    key = make_key(client, user_a, ["read", "fleet"], name="supervisor")
    resp = client.get("/api/v1/mcp/auth/verify", headers={"X-API-Key": key})
    assert resp.status_code == 200
    assert sorted(resp.json()["scopes"]) == ["fleet", "read"]


def test_unknown_scope_rejected_at_creation(client, user_a):
    resp = client.post(
        f"/api/v1/workspaces/{user_a['workspace_id']}/api-keys",
        json={"name": "typo", "scopes": ["read", "wrtie"]},
        headers=auth_headers(user_a["token"]),
    )
    assert resp.status_code == 422
    assert "wrtie" in resp.text


def test_user_level_key_from_registration_still_works(client, user_a):
    """The default provisioned key must not lose access when enforcement lands."""
    headers = {
        "X-API-Key": user_a["api_key"],
        "X-Workspace-ID": user_a["workspace_id"],
    }
    assert client.get("/api/v1/mcp/messages", headers=headers).status_code == 200
    resp = client.post(
        "/api/v1/mcp/messages",
        json={"content": "hi", "agent_name": "test"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text


def test_legacy_key_with_empty_scopes_is_denied(client, user_a):
    """Migration 018 backfills these; a row that slips through still fails closed.

    Enforcement must not fall back to "empty means allow" — that would make
    the migration optional and the scope check advisory.
    """
    key = make_key(client, user_a, ["read", "write"], name="legacy")
    with sync_engine.begin() as conn:
        conn.execute(text("UPDATE api_keys SET scopes = '{}' WHERE name = 'legacy'"))

    assert client.get("/api/v1/mcp/messages", headers={"X-API-Key": key}).status_code == 403
