"""MCP message flow: send, unseen polling, acknowledge — the agent home-base loop."""

from tests.conftest import auth_headers


def mcp_headers(user: dict) -> dict:
    return {"X-API-Key": user["api_key"], "X-Workspace-ID": user["workspace_id"]}


def post_user_message(client, user: dict, content: str) -> dict:
    resp = client.post(
        f"/api/v1/workspaces/{user['workspace_id']}/messages",
        json={"content": content},
        headers=auth_headers(user["token"]),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_agent_sends_message(client, user_a):
    resp = client.post(
        "/api/v1/mcp/messages",
        json={"content": "Task complete!"},
        headers=mcp_headers(user_a),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["agent_name"] == "Default Agent Key"
    assert body["user_id"] is None

    # Visible in the workspace message list
    resp = client.get(
        f"/api/v1/workspaces/{user_a['workspace_id']}/messages",
        headers=auth_headers(user_a["token"]),
    )
    assert resp.status_code == 200
    contents = [m["content"] for m in resp.json()["messages"]]
    assert "Task complete!" in contents


def test_unseen_acknowledge_cycle(client, user_a):
    post_user_message(client, user_a, "hey agent, do the thing")

    # Agent polls for unseen user messages
    resp = client.get(
        "/api/v1/mcp/messages", params={"unseen": True}, headers=mcp_headers(user_a)
    )
    assert resp.status_code == 200
    messages = resp.json()["messages"]
    assert len(messages) == 1
    msg = messages[0]
    # User messages get instruction stuffing + sender attribution
    assert msg["content"].startswith("[FORMATTING")
    assert "[Test User]: hey agent, do the thing" in msg["content"]

    # Acknowledge
    resp = client.post(
        "/api/v1/mcp/messages/acknowledge",
        json={"message_ids": [msg["id"]]},
        headers=mcp_headers(user_a),
    )
    assert resp.status_code == 200
    assert resp.json()["acknowledged"] == 1

    # Nothing unseen anymore
    resp = client.get(
        "/api/v1/mcp/messages", params={"unseen": True}, headers=mcp_headers(user_a)
    )
    assert resp.json()["messages"] == []


def test_agent_messages_not_in_unseen(client, user_a):
    client.post(
        "/api/v1/mcp/messages",
        json={"content": "status update"},
        headers=mcp_headers(user_a),
    )
    resp = client.get(
        "/api/v1/mcp/messages", params={"unseen": True}, headers=mcp_headers(user_a)
    )
    assert resp.json()["messages"] == []


def test_acknowledge_scoped_to_workspace(client, user_a, user_b):
    """One workspace's key can't acknowledge another workspace's messages."""
    msg = post_user_message(client, user_b, "private to workspace B")

    resp = client.post(
        "/api/v1/mcp/messages/acknowledge",
        json={"message_ids": [msg["id"]]},
        headers=mcp_headers(user_a),
    )
    assert resp.status_code == 200
    assert resp.json()["acknowledged"] == 0

    # Still unseen for workspace B's agent
    resp = client.get(
        "/api/v1/mcp/messages", params={"unseen": True}, headers=mcp_headers(user_b)
    )
    assert len(resp.json()["messages"]) == 1


def test_agent_message_content_not_modified(client, user_a):
    """Instruction stuffing applies to user messages only."""
    client.post(
        "/api/v1/mcp/messages",
        json={"content": "plain agent message"},
        headers=mcp_headers(user_a),
    )
    resp = client.get("/api/v1/mcp/messages", headers=mcp_headers(user_a))
    agent_msgs = [m for m in resp.json()["messages"] if m["user_id"] is None]
    assert agent_msgs[0]["content"] == "plain agent message"
