"""Agent runtime registry, agent_config validation, and start-agent gating."""

from tests.conftest import auth_headers


def make_agent_workspace(client, token: str, agent_config: dict | None = None) -> dict:
    resp = client.post(
        "/api/v1/workspaces",
        json={
            "name": "Agent WS",
            "workspace_type": "agent",
            "agent_purpose": "test agent",
            "agent_config": agent_config,
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_agent_runtimes_endpoint(client, user_a):
    resp = client.get(
        "/api/v1/workspaces/agent-runtimes", headers=auth_headers(user_a["token"])
    )
    assert resp.status_code == 200
    runtimes = resp.json()["runtimes"]

    assert runtimes["claude-code"]["enabled"] is True
    assert runtimes["claude-code"]["default_model"] == "sonnet"
    assert any(m["id"] == "opus" for m in runtimes["claude-code"]["models"])

    # Codex is registered but gated until its image ships
    assert "codex" in runtimes
    assert runtimes["codex"]["enabled"] is False


def test_agent_config_defaults_and_storage(client, user_a):
    ws = make_agent_workspace(
        client, user_a["token"], {"template": "coder", "repo_url": "https://github.com/x/y"}
    )
    cfg = ws["agent_config"]
    # Defaults filled in by the schema
    assert cfg["runtime"] == "claude-code"
    assert cfg["model"] is None
    assert cfg["template"] == "coder"
    assert cfg["repo_url"] == "https://github.com/x/y"


def test_agent_config_extra_keys_preserved(client, user_a):
    """Legacy/forward-compat keys in agent_config must survive validation."""
    ws = make_agent_workspace(
        client, user_a["token"], {"template": "custom", "legacy_key": "keep-me"}
    )
    assert ws["agent_config"]["legacy_key"] == "keep-me"


def test_unknown_runtime_rejected(client, user_a):
    resp = client.post(
        "/api/v1/workspaces",
        json={
            "name": "Bad",
            "workspace_type": "agent",
            "agent_config": {"runtime": "gemini-cli"},
        },
        headers=auth_headers(user_a["token"]),
    )
    assert resp.status_code == 422


def test_unknown_template_rejected(client, user_a):
    resp = client.post(
        "/api/v1/workspaces",
        json={
            "name": "Bad",
            "workspace_type": "agent",
            "agent_config": {"template": "nonsense"},
        },
        headers=auth_headers(user_a["token"]),
    )
    assert resp.status_code == 422


def test_update_agent_config_validated(client, user_a):
    ws = make_agent_workspace(client, user_a["token"], {"template": "research"})
    resp = client.patch(
        f"/api/v1/workspaces/{ws['id']}",
        json={"agent_config": {"runtime": "claude-code", "model": "opus", "template": "research"}},
        headers=auth_headers(user_a["token"]),
    )
    assert resp.status_code == 200
    assert resp.json()["agent_config"]["model"] == "opus"

    resp = client.patch(
        f"/api/v1/workspaces/{ws['id']}",
        json={"agent_config": {"runtime": "not-a-runtime"}},
        headers=auth_headers(user_a["token"]),
    )
    assert resp.status_code == 422


def test_start_agent_rejects_chat_workspace(client, user_a):
    resp = client.post(
        f"/api/v1/workspaces/{user_a['workspace_id']}/agent/start",
        headers=auth_headers(user_a["token"]),
    )
    assert resp.status_code == 400
    assert "agent workspaces" in resp.json()["detail"].lower()


def test_start_agent_rejects_disabled_runtime(client, user_a):
    ws = make_agent_workspace(client, user_a["token"], {"runtime": "codex"})
    resp = client.post(
        f"/api/v1/workspaces/{ws['id']}/agent/start",
        headers=auth_headers(user_a["token"]),
    )
    assert resp.status_code == 400
    assert "not available" in resp.json()["detail"]


def test_start_agent_requires_credential(client, user_a):
    ws = make_agent_workspace(client, user_a["token"], {"runtime": "claude-code"})
    resp = client.post(
        f"/api/v1/workspaces/{ws['id']}/agent/start",
        headers=auth_headers(user_a["token"]),
    )
    assert resp.status_code == 400
    assert "Anthropic API key" in resp.json()["detail"]
