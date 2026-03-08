"""
WebSocket endpoint for real-time workspace messaging.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from sqlalchemy import select
from jose import jwt, JWTError

from app.db.session import AsyncSessionLocal
from app.core.config import get_settings
from app.core.websocket import manager
from app.models.workspace import Workspace
from app.models.api_key import ApiKey

router = APIRouter()
settings = get_settings()


def get_user_from_token(token: str) -> str | None:
    """Validate JWT token and return user_id."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
        user_id = payload.get("sub")
        return user_id
    except JWTError:
        return None


async def validate_api_key(key: str) -> dict | None:
    """Validate API key and return workspace info."""
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
        if api_key:
            # Check if expired
            if api_key.expires_at and api_key.expires_at < datetime.utcnow():
                return None
            return {
                "workspace_id": str(api_key.workspace_id),
                "key_name": api_key.name,
                "type": "api_key",
            }
    return None


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

    # Try API key first (starts with mt_)
    if token.startswith("mt_"):
        auth_info = await validate_api_key(token)

    # Fall back to JWT token
    if not auth_info:
        user_id = get_user_from_token(token)
        if user_id:
            auth_info = {"user_id": user_id, "type": "jwt"}

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
        if auth_info.get("type") == "jwt":
            # JWT users must own the workspace
            if str(workspace.owner_id) != auth_info.get("user_id"):
                await websocket.close(code=4003, reason="Access denied")
                return
        elif auth_info.get("type") == "api_key":
            # API keys must be for this specific workspace
            if auth_info.get("workspace_id") != workspace_id:
                await websocket.close(code=4003, reason="Access denied")
                return

    import asyncio
    import logging
    logger = logging.getLogger(__name__)

    await manager.connect(websocket, workspace_id)
    logger.info(f"WebSocket connected for workspace {workspace_id}, auth_type={auth_info.get('type', 'unknown')}")

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

