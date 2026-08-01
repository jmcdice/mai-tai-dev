"""API key authentication for the MCP endpoints (deps.get_api_key_auth)."""

from datetime import datetime, timedelta

from sqlalchemy import text

from tests.conftest import auth_headers, sync_engine


def make_workspace_key(client, token: str, workspace_id: str, name: str = "ws-key") -> str:
    resp = client.post(
        f"/api/v1/workspaces/{workspace_id}/api-keys",
        json={"name": name, "scopes": ["read", "write"]},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["key"]


def test_workspace_level_key_verifies(client, user_a):
    key = make_workspace_key(client, user_a["token"], user_a["workspace_id"])

    resp = client.get("/api/v1/mcp/auth/verify", headers={"X-API-Key": key})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "authenticated"
    assert body["workspace_id"] == user_a["workspace_id"]


def test_user_level_key_requires_workspace_header(client, user_a):
    # Without X-Workspace-ID: rejected
    resp = client.get(
        "/api/v1/mcp/auth/verify", headers={"X-API-Key": user_a["api_key"]}
    )
    assert resp.status_code == 400

    # With an owned workspace: accepted
    resp = client.get(
        "/api/v1/mcp/auth/verify",
        headers={
            "X-API-Key": user_a["api_key"],
            "X-Workspace-ID": user_a["workspace_id"],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["workspace_id"] == user_a["workspace_id"]


def test_user_level_key_denied_for_foreign_workspace(client, user_a, user_b):
    resp = client.get(
        "/api/v1/mcp/auth/verify",
        headers={
            "X-API-Key": user_a["api_key"],
            "X-Workspace-ID": user_b["workspace_id"],
        },
    )
    assert resp.status_code == 403


def test_invalid_key_rejected(client):
    resp = client.get(
        "/api/v1/mcp/auth/verify", headers={"X-API-Key": "mt_definitely-not-a-key"}
    )
    assert resp.status_code == 401


def test_expired_key_rejected(client, user_a):
    key = make_workspace_key(client, user_a["token"], user_a["workspace_id"], name="expiring")

    # Expire it directly in the DB (naive UTC, matching the column convention)
    past = datetime.utcnow() - timedelta(days=1)
    with sync_engine.begin() as conn:
        conn.execute(
            text("UPDATE api_keys SET expires_at = :past WHERE name = 'expiring'"),
            {"past": past},
        )

    resp = client.get("/api/v1/mcp/auth/verify", headers={"X-API-Key": key})
    assert resp.status_code == 401


def test_key_with_expiry_can_be_created_and_used(client, user_a):
    """Regression: expires_at was stored tz-aware into a naive column."""
    resp = client.post(
        f"/api/v1/workspaces/{user_a['workspace_id']}/api-keys",
        json={"name": "with-expiry", "scopes": ["read"], "expires_in_days": 30},
        headers=auth_headers(user_a["token"]),
    )
    assert resp.status_code == 201, resp.text
    key = resp.json()["key"]

    resp = client.get("/api/v1/mcp/auth/verify", headers={"X-API-Key": key})
    assert resp.status_code == 200
