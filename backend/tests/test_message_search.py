"""Full-text search over workspace message history (/mcp/messages/search)."""

from sqlalchemy import text

from tests.conftest import sync_engine
from tests.test_mcp_messages import mcp_headers, post_user_message


def _create_fts_index():
    """Tests build schema from models, so apply migration 015's index by hand."""
    with sync_engine.begin() as conn:
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_messages_content_fts
            ON messages USING GIN (to_tsvector('english', content))
        """))


def test_search_finds_relevant_messages(client, user_a):
    _create_fts_index()
    post_user_message(client, user_a, "let's deploy the caddy reverse proxy on Friday")
    post_user_message(client, user_a, "unrelated chatter about lunch")

    resp = client.get(
        "/api/v1/mcp/messages/search",
        params={"q": "caddy reverse proxy"},
        headers=mcp_headers(user_a),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 1
    hit = body["results"][0]
    assert "caddy" in hit["content"]
    assert hit["sender_name"] == "Test User"
    assert "<b>" in hit["snippet"]  # ts_headline highlighting


def test_search_scoped_to_workspace(client, user_a, user_b):
    post_user_message(client, user_b, "secret plans about the zeppelin project")

    resp = client.get(
        "/api/v1/mcp/messages/search",
        params={"q": "zeppelin"},
        headers=mcp_headers(user_a),
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 0

    resp = client.get(
        "/api/v1/mcp/messages/search",
        params={"q": "zeppelin"},
        headers=mcp_headers(user_b),
    )
    assert resp.json()["total"] == 1


def test_search_includes_agent_messages(client, user_a):
    client.post(
        "/api/v1/mcp/messages",
        json={"content": "I finished refactoring the websocket handler"},
        headers=mcp_headers(user_a),
    )
    resp = client.get(
        "/api/v1/mcp/messages/search",
        params={"q": "websocket refactoring"},
        headers=mcp_headers(user_a),
    )
    assert resp.json()["total"] == 1
    assert resp.json()["results"][0]["sender_name"] == "Default Agent Key"


def test_search_query_validation(client, user_a):
    resp = client.get(
        "/api/v1/mcp/messages/search", params={"q": "x"}, headers=mcp_headers(user_a)
    )
    assert resp.status_code == 422

    resp = client.get(
        "/api/v1/mcp/messages/search", headers=mcp_headers(user_a)
    )
    assert resp.status_code == 422
