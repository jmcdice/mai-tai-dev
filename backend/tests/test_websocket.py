"""WebSocket auth and realtime broadcast."""

import pytest
from starlette.websockets import WebSocketDisconnect

from tests.conftest import auth_headers
from tests.test_api_key_auth import make_workspace_key


def ws_url(workspace_id: str, token: str) -> str:
    return f"/api/v1/ws/workspaces/{workspace_id}?token={token}"


def test_connect_with_jwt(client, user_a):
    with client.websocket_connect(ws_url(user_a["workspace_id"], user_a["token"])) as ws:
        msg = ws.receive_json()
        assert msg["type"] == "connected"
        assert msg["workspace_id"] == user_a["workspace_id"]


def test_connect_with_workspace_level_key(client, user_a):
    key = make_workspace_key(client, user_a["token"], user_a["workspace_id"])
    with client.websocket_connect(ws_url(user_a["workspace_id"], key)) as ws:
        assert ws.receive_json()["type"] == "connected"


def test_connect_with_user_level_key(client, user_a):
    """Regression: user-level keys were always denied over WS."""
    with client.websocket_connect(ws_url(user_a["workspace_id"], user_a["api_key"])) as ws:
        assert ws.receive_json()["type"] == "connected"


def test_user_level_key_denied_for_foreign_workspace(client, user_a, user_b):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(ws_url(user_b["workspace_id"], user_a["api_key"])):
            pass


def test_refresh_token_rejected(client, user_a):
    """Regression: WS auth accepted refresh tokens as credentials."""
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            ws_url(user_a["workspace_id"], user_a["refresh_token"])
        ):
            pass


def test_foreign_jwt_rejected(client, user_a, user_b):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(ws_url(user_a["workspace_id"], user_b["token"])):
            pass


def test_message_broadcast(client, user_a):
    """A REST-posted message is pushed to connected WS clients."""
    with client.websocket_connect(ws_url(user_a["workspace_id"], user_a["token"])) as ws:
        assert ws.receive_json()["type"] == "connected"

        resp = client.post(
            f"/api/v1/workspaces/{user_a['workspace_id']}/messages",
            json={"content": "realtime hello"},
            headers=auth_headers(user_a["token"]),
        )
        assert resp.status_code == 201

        event = ws.receive_json()
        assert event["type"] == "new_message"
        assert event["message"]["content"] == "realtime hello"
        assert event["message"]["sender_name"] == "Test User"
