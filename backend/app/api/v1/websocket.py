"""
WebSocket endpoint for real-time workspace messaging.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from sqlalchemy import select
import jwt

from app.db.session import AsyncSessionLocal
from app.core.config import get_settings
from app.core.websocket import manager
from app.models.workspace import Workspace
from app.models.api_key import ApiKey

router = APIRouter()
settings = get_settings()


def get_user_from_token(token: str) -> str | None:
    """Validate JWT access token and return user_id."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        # Only access tokens grant WS access (refresh tokens are for /auth/refresh)
        if payload.get("type") != "access":
            return None
        user_id = payload.get("sub")
        return user_id
    except jwt.InvalidTokenError:
        return None


async def validate_api_key(key: str, workspace_id: str) -> dict | None:
    """Validate API key and check it grants access to the given workspace.

    Handles both key types:
    - Workspace-level keys (workspace_id set): must match the requested workspace.
    - User-level keys (user_id set): the key's owner must own the workspace.
    """
    import hashlib
    from datetime import datetime

    if not key.startswith("mt_"):
        return None

    # Hash the key the same way it was stored
    key_hash = hashlib.sha256(key.encode(), usedforsecurity=False).hexdigest()

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ApiKey).where(ApiKey.key_hash == key_hash)
        )
        api_key = result.scalar_one_or_none()
        if not api_key:
            return None

        # Check if expired
        if api_key.expires_at and api_key.expires_at < datetime.utcnow():
            return None

        if api_key.workspace_id is not None:
            # Workspace-level key: only valid for its bound workspace
            if str(api_key.workspace_id) != workspace_id:
                return None
        else:
            # User-level key: the key's owner must own the requested workspace
            result = await db.execute(
                select(Workspace).where(Workspace.id == workspace_id)
            )
            workspace = result.scalar_one_or_none()
            if not workspace or workspace.owner_id != api_key.user_id:
                return None

        return {
            "workspace_id": workspace_id,
            "key_name": api_key.name,
            "type": "api_key",
        }


@router.websocket("/ws/workspaces/{workspace_id}")
async def websocket_workspace(
    websocket: WebSocket,
    workspace_id: str,
    token: str = Query(...),
):
    """
    WebSocket endpoint for real-time workspace updates.

    Connect with:
    - JWT: ws://localhost:8000/api/v1/ws/workspaces/{workspace_id}?token=JWT_TOKEN
    - API Key: ws://localhost:8000/api/v1/ws/workspaces/{workspace_id}?token=mt_YOUR_API_KEY

    Messages received:
    - {"type": "new_message", "message": {...}} - New message in workspace
    - {"type": "connected", "workspace_id": "..."} - Connection confirmed
    - {"type": "error", "message": "..."} - Error occurred
    """
    auth_info = None
    # Plain literal for logging — never log token-derived values (auth_info
    # carries data derived from the credential; CodeQL py/clear-text-logging)
    auth_kind = "none"

    # Try API key first (starts with mt_)
    if token.startswith("mt_"):
        auth_info = await validate_api_key(token, workspace_id)
        if auth_info:
            auth_kind = "api_key"

    # Fall back to JWT token
    if not auth_info:
        user_id = get_user_from_token(token)
        if user_id:
            auth_info = {"user_id": user_id, "type": "jwt"}
            auth_kind = "jwt"

    if not auth_info:
        await websocket.close(code=4001, reason="Invalid token or API key")
        return

    # Validate workspace exists and user has access
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
        workspace = result.scalar_one_or_none()
        if not workspace:
            await websocket.close(code=4004, reason="Workspace not found")
            return

        # Verify ownership/access based on auth type
        # (API keys were already checked against this workspace in validate_api_key)
        if auth_info.get("type") == "jwt":
            # JWT users must own the workspace
            if str(workspace.owner_id) != auth_info.get("user_id"):
                await websocket.close(code=4003, reason="Access denied")
                return

    import asyncio
    import logging
    logger = logging.getLogger(__name__)

    await manager.connect(websocket, workspace_id)
    logger.info(f"WebSocket connected for workspace {workspace_id}, auth_type={auth_kind}")

    try:
        # Send connection confirmation
        await websocket.send_json({
            "type": "connected",
            "workspace_id": workspace_id,
        })
        logger.info(f"Sent connection confirmation to workspace {workspace_id}")

        # Keep connection alive - receive messages or pings
        # The broadcast mechanism handles sending new messages to clients
        while True:
            try:
                # Wait for client messages with timeout to allow connection health checks
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                logger.info(f"Received from client: {data}")
                # Handle ping/pong or other client messages
                if data == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                logger.info(f"Sending keepalive ping to workspace {workspace_id}")
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception as e:
                    logger.warning(f"Failed to send ping: {e}")
                    break  # Connection lost

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected from workspace {workspace_id}")
        manager.disconnect(websocket, workspace_id)
    except Exception as e:
        logger.error(f"WebSocket error for workspace {workspace_id}: {e}")
        manager.disconnect(websocket, workspace_id)

