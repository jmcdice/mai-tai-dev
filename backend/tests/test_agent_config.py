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

    assert runtimes["codex"]["enabled"] is True
    assert runtimes["codex"]["credential_label"] == "OpenAI API key"
    assert any(m["id"] == "gpt-5.5" for m in runtimes["codex"]["models"])


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


def test_start_agent_rejects_unknown_stored_runtime(client, user_a):
    """Legacy configs may hold runtimes the registry no longer knows."""
    from sqlalchemy import text

    from tests.conftest import sync_engine

    ws = make_agent_workspace(client, user_a["token"], {"runtime": "claude-code"})
    with sync_engine.begin() as conn:
        conn.execute(
            text("UPDATE workspaces SET agent_config = '{\"runtime\": \"retired-runtime\"}' WHERE id = :id"),
            {"id": ws["id"]},
        )

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


def test_start_agent_codex_requires_openai_key(client, user_a):
    ws = make_agent_workspace(client, user_a["token"], {"runtime": "codex"})
    resp = client.post(
        f"/api/v1/workspaces/{ws['id']}/agent/start",
        headers=auth_headers(user_a["token"]),
    )
    assert resp.status_code == 400
    assert "OpenAI API key" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Container memory limits (issue #40). One global 512m cap meant a coder agent
# was OOM-killed by an ordinary dependency install.
# ---------------------------------------------------------------------------


def test_coder_template_gets_more_memory_than_a_chat_agent():
    from app.services.agents.templates import parse_mem_limit, template_mem_limit

    coder = parse_mem_limit(template_mem_limit("coder"))
    assistant = parse_mem_limit(template_mem_limit("assistant"))

    assert coder > assistant, "a coder agent must not share the chat-agent cap"
    assert coder >= 2 * 1024**3, "512m could not survive a pnpm install; 2g is the floor"


def test_unknown_template_falls_back_to_the_default_limit():
    from app.services.agents.templates import DEFAULT_MEM_LIMIT, template_mem_limit

    assert template_mem_limit("not-a-template") == DEFAULT_MEM_LIMIT


def test_parse_mem_limit_units():
    from app.services.agents.templates import parse_mem_limit

    assert parse_mem_limit("512m") == 512 * 1024**2
    assert parse_mem_limit("2g") == 2 * 1024**3
    assert parse_mem_limit("1024") == 1024
    assert parse_mem_limit("1536M") == 1536 * 1024**2


def test_mem_limit_override_accepted_and_stored(client, user_a):
    ws = make_agent_workspace(
        client, user_a["token"], {"template": "coder", "mem_limit": "8g"}
    )
    assert ws["agent_config"]["mem_limit"] == "8g"


def test_mem_limit_defaults_to_none_meaning_template_default(client, user_a):
    ws = make_agent_workspace(client, user_a["token"], {"template": "coder"})
    assert ws["agent_config"]["mem_limit"] is None


def test_malformed_mem_limit_rejected(client, user_a):
    resp = client.post(
        "/api/v1/workspaces",
        json={
            "name": "Bad",
            "workspace_type": "agent",
            "agent_config": {"template": "coder", "mem_limit": "lots"},
        },
        headers=auth_headers(user_a["token"]),
    )
    assert resp.status_code == 422


def test_absurdly_small_mem_limit_rejected(client, user_a):
    """Accepting 16m would just trade one silent OOM for another."""
    resp = client.post(
        "/api/v1/workspaces",
        json={
            "name": "Bad",
            "workspace_type": "agent",
            "agent_config": {"template": "coder", "mem_limit": "16m"},
        },
        headers=auth_headers(user_a["token"]),
    )
    assert resp.status_code == 422


def test_agent_templates_endpoint_exposes_default_mem_limit(client, user_a):
    resp = client.get(
        "/api/v1/workspaces/agent-templates", headers=auth_headers(user_a["token"])
    )
    assert resp.status_code == 200
    templates = resp.json()["templates"]
    assert templates["coder"]["default_mem_limit"]
    assert templates["coder"]["default_mem_limit"] != templates["assistant"]["default_mem_limit"]
