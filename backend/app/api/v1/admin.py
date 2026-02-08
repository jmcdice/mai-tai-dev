"""Admin endpoints - only accessible by admin users."""

from datetime import datetime, timedelta
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user, get_db
from app.core.security import create_access_token, create_refresh_token
from app.models.api_key import ApiKey
from app.models.message import Message
from app.models.workspace import Workspace
from app.models.user import User

router = APIRouter(prefix="/admin", tags=["admin"])


# --- Schemas ---


class AdminUserResponse(BaseModel):
    """User with admin-level details."""

    id: UUID
    email: str
    name: str
    avatar_url: str | None = None
    is_admin: bool
    created_at: datetime
    workspace_count: int
    message_count: int

    class Config:
        from_attributes = True


class AdminStatsResponse(BaseModel):
    """System-wide statistics."""

    total_users: int
    total_workspaces: int
    total_messages: int
    admin_count: int
    connected_agents: int


class ImpersonateResponse(BaseModel):
    """Response for impersonation."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: str
    user_email: str
    user_name: str


# --- Dependencies ---


async def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Dependency that requires the current user to be an admin.
    Returns 404 to hide the existence of admin endpoints from non-admins.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Not found",
        )
    return current_user


# --- Endpoints ---


@router.get("/users", response_model=List[AdminUserResponse])
async def list_users(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> List[AdminUserResponse]:
    """List all users with workspace and message counts. Admin only."""
    # Query users with workspace count
    result = await db.execute(
        select(User, func.count(Workspace.id).label("workspace_count"))
        .outerjoin(Workspace, Workspace.owner_id == User.id)
        .group_by(User.id)
        .order_by(User.created_at.desc())
    )
    rows = result.all()

    # Build response with message counts
    responses = []
    for user, workspace_count in rows:
        # Get message count for all workspaces owned by this user
        msg_result = await db.execute(
            select(func.count(Message.id))
            .join(Workspace, Message.workspace_id == Workspace.id)
            .where(Workspace.owner_id == user.id)
        )
        message_count = msg_result.scalar() or 0

        responses.append(
            AdminUserResponse(
                id=user.id,
                email=user.email,
                name=user.name,
                avatar_url=user.avatar_url,
                is_admin=user.is_admin,
                created_at=user.created_at,
                workspace_count=workspace_count,
                message_count=message_count,
            )
        )

    return responses


@router.get("/stats", response_model=AdminStatsResponse)
async def get_stats(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminStatsResponse:
    """Get system-wide statistics. Admin only."""
    # Count users
    user_count_result = await db.execute(select(func.count(User.id)))
    total_users = user_count_result.scalar() or 0

    # Count admins
    admin_count_result = await db.execute(
        select(func.count(User.id)).where(User.is_admin.is_(True))
    )
    admin_count = admin_count_result.scalar() or 0

    # Count workspaces
    workspace_count_result = await db.execute(select(func.count(Workspace.id)))
    total_workspaces = workspace_count_result.scalar() or 0

    # Count messages
    message_count_result = await db.execute(select(func.count(Message.id)))
    total_messages = message_count_result.scalar() or 0

    # Count connected agents (API keys used in last 5 minutes)
    five_min_ago = datetime.utcnow() - timedelta(minutes=5)
    connected_result = await db.execute(
        select(func.count(ApiKey.id)).where(ApiKey.last_used_at > five_min_ago)
    )
    connected_agents = connected_result.scalar() or 0

    return AdminStatsResponse(
        total_users=total_users,
        total_workspaces=total_workspaces,
        total_messages=total_messages,
        admin_count=admin_count,
        connected_agents=connected_agents,
    )


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: UUID,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Delete a user and all their data. Admin only."""
    if admin.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete yourself",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Delete user's workspaces first (cascade will handle messages, etc.)
    workspaces_result = await db.execute(
        select(Workspace).where(Workspace.owner_id == user_id)
    )
    workspaces = workspaces_result.scalars().all()
    for workspace in workspaces:
        await db.delete(workspace)

    # Now delete the user
    await db.delete(user)
    await db.commit()

    return {"status": "deleted", "user_id": str(user_id)}


@router.post("/impersonate/{user_id}", response_model=ImpersonateResponse)
async def impersonate_user(
    user_id: UUID,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ImpersonateResponse:
    """
    Generate tokens to impersonate another user. Admin only.
    Use with caution - this grants full access as that user.
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Generate tokens for the target user
    access_token = create_access_token(data={"sub": str(user.id)})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})

    return ImpersonateResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user_id=str(user.id),
        user_email=user.email,
        user_name=user.name,
    )


@router.post("/users/{user_id}/toggle-admin")
async def toggle_admin(
    user_id: UUID,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Toggle admin status for a user. Admin only."""
    if admin.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change your own admin status",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user.is_admin = not user.is_admin
    await db.commit()

    return {
        "status": "updated",
        "user_id": str(user_id),
        "is_admin": user.is_admin,
    }

