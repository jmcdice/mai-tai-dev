"""Workspace CRUD, ownership isolation, and API key lifecycle."""

from tests.conftest import auth_headers


def test_workspace_isolation_between_users(client, user_a, user_b):
    ws_a = user_a["workspace_id"]

    # Owner can read
    resp = client.get(f"/api/v1/workspaces/{ws_a}", headers=auth_headers(user_a["token"]))
    assert resp.status_code == 200

    # Other users get 404 (not 403 — existence is not leaked)
    resp = client.get(f"/api/v1/workspaces/{ws_a}", headers=auth_headers(user_b["token"]))
    assert resp.status_code == 404

    resp = client.patch(
        f"/api/v1/workspaces/{ws_a}",
        json={"name": "hijacked"},
        headers=auth_headers(user_b["token"]),
    )
    assert resp.status_code == 404


def test_agent_templates_route_reachable(client, user_a):
    """Regression: this static route was shadowed by /{workspace_id} and 422'd."""
    resp = client.get(
        "/api/v1/workspaces/agent-templates", headers=auth_headers(user_a["token"])
    )
    assert resp.status_code == 200
    templates = resp.json()["templates"]
    assert "coder" in templates
    assert "research" in templates


def test_create_and_archive_workspace(client, user_a):
    resp = client.post(
        "/api/v1/workspaces",
        json={"name": "Second Workspace"},
        headers=auth_headers(user_a["token"]),
    )
    assert resp.status_code == 201
    ws_id = resp.json()["id"]

    resp = client.patch(
        f"/api/v1/workspaces/{ws_id}",
        json={"archived": True},
        headers=auth_headers(user_a["token"]),
    )
    assert resp.status_code == 200

    # archived=false filter excludes it
    resp = client.get(
        "/api/v1/workspaces", params={"archived": False}, headers=auth_headers(user_a["token"])
    )
    names = [w["name"] for w in resp.json()["workspaces"]]
    assert "Second Workspace" not in names


def test_api_key_lifecycle(client, user_a):
    ws_id = user_a["workspace_id"]
    headers = auth_headers(user_a["token"])

    resp = client.post(
        f"/api/v1/workspaces/{ws_id}/api-keys",
        json={"name": "lifecycle-key", "scopes": ["read"]},
        headers=headers,
    )
    assert resp.status_code == 201
    key_id = resp.json()["id"]
    assert resp.json()["key"].startswith("mt_")

    # Raw key is never exposed in the list
    resp = client.get(f"/api/v1/workspaces/{ws_id}/api-keys", headers=headers)
    assert resp.status_code == 200
    listed = resp.json()["api_keys"]
    assert any(k["id"] == key_id for k in listed)
    assert all("key" not in k or not str(k.get("key", "")).startswith("mt_") for k in listed)

    # Revoke
    resp = client.delete(f"/api/v1/workspaces/{ws_id}/api-keys/{key_id}", headers=headers)
    assert resp.status_code == 204

    resp = client.get(f"/api/v1/workspaces/{ws_id}/api-keys", headers=headers)
    assert all(k["id"] != key_id for k in resp.json()["api_keys"])


def test_message_pagination(client, user_a):
    ws_id = user_a["workspace_id"]
    headers = auth_headers(user_a["token"])

    for i in range(3):
        resp = client.post(
            f"/api/v1/workspaces/{ws_id}/messages",
            json={"content": f"message {i}"},
            headers=headers,
        )
        assert resp.status_code == 201

    resp = client.get(
        f"/api/v1/workspaces/{ws_id}/messages", params={"limit": 2}, headers=headers
    )
    body = resp.json()
    assert body["has_more"] is True
    assert len(body["messages"]) == 2
    # Chronological order within the page
    contents = [m["content"] for m in body["messages"]]
    assert contents == sorted(contents)
