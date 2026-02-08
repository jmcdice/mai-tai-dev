"""Workspace API endpoints."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.websocket import manager as ws_manager
from app.models.api_key import ApiKey
from app.models.workspace import Workspace
from app.models.workspace_agent_activity import WorkspaceAgentActivity
from app.models.message import Message
from app.models.user import User
from app.schemas.api_key import ApiKeyCreate, ApiKeyListItem, ApiKeyListResponse, ApiKeyResponse
from app.schemas.workspace import WorkspaceCreate, WorkspaceListResponse, WorkspaceResponse, WorkspaceUpdate
from app.schemas.message import MessageCreate, MessageListResponse, MessageResponse

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


def generate_api_key() -> tuple[str, str]:
    """Generate API key and its hash."""
    raw_key = f"mt_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    return raw_key, key_hash


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    data: WorkspaceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Workspace:
    """Create a new workspace."""
    workspace = Workspace(
        name=data.name,
        owner_id=current_user.id,
        settings=data.settings,
    )
    db.add(workspace)
    await db.commit()
    await db.refresh(workspace)
    return workspace


@router.get("", response_model=WorkspaceListResponse)
async def list_workspaces(
    archived: bool | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """List all workspaces for the current user.

    Args:
        archived: Filter by archived status. None = all, True = archived only, False = active only.
    """
    query = select(Workspace).where(Workspace.owner_id == current_user.id)

    if archived is not None:
        query = query.where(Workspace.archived == archived)

    result = await db.execute(query)
    workspaces = result.scalars().all()
    return {"workspaces": workspaces, "total": len(workspaces)}


async def check_workspace_access(
    workspace_id: UUID,
    db: AsyncSession,
    current_user: User,
) -> Workspace:
    """Get a workspace if user owns it."""
    result = await db.execute(
        select(Workspace).where(Workspace.id == workspace_id, Workspace.owner_id == current_user.id)
    )
    workspace = result.scalar_one_or_none()
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return workspace


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Workspace:
    """Get a workspace by ID."""
    return await check_workspace_access(workspace_id, db, current_user)


@router.patch("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    workspace_id: UUID,
    data: WorkspaceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Workspace:
    """Update a workspace."""
    workspace = await check_workspace_access(workspace_id, db, current_user)

    if data.name is not None:
        workspace.name = data.name
    if data.settings is not None:
        workspace.settings = data.settings
    if data.archived is not None:
        workspace.archived = data.archived
    workspace.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(workspace)
    return workspace


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(
    workspace_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete a workspace."""
    workspace = await check_workspace_access(workspace_id, db, current_user)
    await db.delete(workspace)
    await db.commit()


# API Key endpoints
@router.post("/{workspace_id}/api-keys", response_model=ApiKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    workspace_id: UUID,
    data: ApiKeyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Generate a new API key for the workspace."""
    await check_workspace_access(workspace_id, db, current_user)

    raw_key, key_hash = generate_api_key()
    expires_at = None
    if data.expires_in_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=data.expires_in_days)

    api_key = ApiKey(
        workspace_id=workspace_id,
        name=data.name,
        key_hash=key_hash,
        scopes=data.scopes,
        expires_at=expires_at,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    return {
        "id": api_key.id,
        "name": api_key.name,
        "key": raw_key,  # Only time the raw key is returned!
        "workspace_id": api_key.workspace_id,
        "scopes": api_key.scopes,
        "expires_at": api_key.expires_at,
        "created_at": api_key.created_at,
    }


@router.get("/{workspace_id}/api-keys", response_model=ApiKeyListResponse)
async def list_api_keys(
    workspace_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """List all API keys for a workspace."""
    await check_workspace_access(workspace_id, db, current_user)

    result = await db.execute(
        select(ApiKey).where(ApiKey.workspace_id == workspace_id)
    )
    api_keys = result.scalars().all()

    api_key_items = [
        ApiKeyListItem(
            id=ak.id,
            name=ak.name,
            workspace_id=ak.workspace_id,
            scopes=ak.scopes,
            expires_at=ak.expires_at,
            last_used_at=ak.last_used_at,
            created_at=ak.created_at,
        )
        for ak in api_keys
    ]
    return {"api_keys": api_key_items, "total": len(api_key_items)}


@router.delete("/{workspace_id}/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    workspace_id: UUID,
    key_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Revoke an API key."""
    await check_workspace_access(workspace_id, db, current_user)

    result = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.workspace_id == workspace_id)
    )
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")

    await db.delete(api_key)
    await db.commit()


# Message endpoints
@router.post("/{workspace_id}/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def create_message(
    workspace_id: UUID,
    data: MessageCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Send a message to a workspace."""
    await check_workspace_access(workspace_id, db, current_user)

    message = Message(
        workspace_id=workspace_id,
        user_id=current_user.id,
        agent_name=None,
        content=data.content,
        message_metadata=data.metadata,
        message_type=data.message_type,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)

    # Broadcast to WebSocket clients
    await ws_manager.broadcast_to_channel(str(workspace_id), {
        "type": "new_message",
        "message": {
            "id": str(message.id),
            "workspace_id": str(message.workspace_id),
            "user_id": str(message.user_id) if message.user_id else None,
            "agent_name": message.agent_name,
            "sender_name": current_user.name,
            "sender_avatar_url": current_user.avatar_url,
            "content": message.content,
            "message_metadata": message.message_metadata,
            "created_at": message.created_at.isoformat(),
            "message_type": message.message_type,
        },
    })

    return {
        "id": message.id,
        "workspace_id": message.workspace_id,
        "user_id": message.user_id,
        "agent_name": message.agent_name,
        "sender_name": current_user.name,
        "sender_avatar_url": current_user.avatar_url,
        "content": message.content,
        "message_metadata": message.message_metadata,
        "created_at": message.created_at,
        "message_type": message.message_type,
    }


@router.get("/{workspace_id}/messages", response_model=MessageListResponse)
async def list_messages(
    workspace_id: UUID,
    limit: int = Query(50, le=1000, ge=1),
    before: datetime | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Get messages for a workspace with pagination. Use limit=1000 for export."""
    await check_workspace_access(workspace_id, db, current_user)

    query = select(Message).where(Message.workspace_id == workspace_id)
    if before:
        query = query.where(Message.created_at < before)
    query = query.order_by(Message.created_at.desc()).limit(limit + 1)

    result = await db.execute(query)
    messages = list(result.scalars().all())

    has_more = len(messages) > limit
    if has_more:
        messages = messages[:limit]

    # Return in chronological order
    messages.reverse()

    # Fetch sender info for user messages
    user_ids = [msg.user_id for msg in messages if msg.user_id]
    sender_info: dict[UUID, dict] = {}
    if user_ids:
        users_result = await db.execute(select(User).where(User.id.in_(user_ids)))
        for user in users_result.scalars().all():
            sender_info[user.id] = {"name": user.name, "avatar_url": user.avatar_url}

    # Build response with sender info
    messages_with_sender = []
    for msg in messages:
        msg_dict = {
            "id": msg.id,
            "workspace_id": msg.workspace_id,
            "user_id": msg.user_id,
            "agent_name": msg.agent_name,
            "sender_name": None,
            "sender_avatar_url": None,
            "content": msg.content,
            "message_metadata": msg.message_metadata,
            "created_at": msg.created_at,
            "message_type": msg.message_type,
        }
        if msg.user_id and msg.user_id in sender_info:
            msg_dict["sender_name"] = sender_info[msg.user_id]["name"]
            msg_dict["sender_avatar_url"] = sender_info[msg.user_id]["avatar_url"]
        elif msg.agent_name:
            msg_dict["sender_name"] = msg.agent_name
        messages_with_sender.append(msg_dict)

    return {"messages": messages_with_sender, "has_more": has_more, "total": len(messages)}


@router.get("/{workspace_id}/agent-status")
async def get_agent_status(
    workspace_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Get the agent connection status for a workspace.

    Uses workspace_agent_activity table to track when agents are active.
    This table is updated on every MCP API call, giving real-time connection
    status for both user-level and workspace-level API keys.

    Thresholds:
    - Connected (green): Activity within 7 minutes
    - Idle (yellow): Activity 7-10 minutes ago
    - Offline (gray): No activity for 10+ minutes or never
    """
    await check_workspace_access(workspace_id, db, current_user)

    # Query workspace_agent_activity table for this workspace
    result = await db.execute(
        select(WorkspaceAgentActivity).where(
            WorkspaceAgentActivity.workspace_id == workspace_id,
        )
    )
    activity = result.scalar_one_or_none()

    if not activity:
        return {
            "status": "offline",
            "last_activity": None,
            "message": "No agent connected",
        }

    now = datetime.utcnow()
    seconds_since_activity = (now - activity.last_activity_at).total_seconds()

    if seconds_since_activity < 420:  # 7 minutes
        status_str = "connected"
        message = "Agent is connected"
    elif seconds_since_activity < 600:  # 10 minutes
        status_str = "idle"
        message = "Agent may be busy"
    else:
        status_str = "offline"
        message = "Agent is offline"

    return {
        "status": status_str,
        "last_activity": activity.last_activity_at.isoformat() + "Z",
        "seconds_since_activity": int(seconds_since_activity),
        "message": message,
    }
