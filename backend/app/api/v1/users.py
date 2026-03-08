"""User API endpoints - manage user-level resources like API keys."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.api_key import ApiKey
from app.models.user import User
from app.schemas.api_key import (
    ApiKeyListItem,
    ApiKeyListResponse,
    ApiKeyResponse,
    UserApiKeyCreate,
)

router = APIRouter(prefix="/users", tags=["users"])


def generate_api_key() -> tuple[str, str]:
    """Generate API key and its hash."""
    raw_key = f"mt_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode(), usedforsecurity=False).hexdigest()
    return raw_key, key_hash


@router.post("/me/api-keys", response_model=ApiKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_user_api_key(
    data: UserApiKeyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Create a user-level API key that works for all workspaces owned by the user."""
    raw_key, key_hash = generate_api_key()
    expires_at = None
    if data.expires_in_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=data.expires_in_days)

    api_key = ApiKey(
        user_id=current_user.id,
        workspace_id=None,  # User-level key, not bound to a workspace
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
        "user_id": api_key.user_id,
        "workspace_id": api_key.workspace_id,
        "scopes": api_key.scopes,
        "expires_at": api_key.expires_at,
        "created_at": api_key.created_at,
    }


@router.get("/me/api-keys", response_model=ApiKeyListResponse)
async def list_user_api_keys(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """List all API keys owned by the current user (both user-level and workspace-level)."""
    # Get user-level keys
    result = await db.execute(
        select(ApiKey).where(ApiKey.user_id == current_user.id)
    )
    user_keys = result.scalars().all()

    api_key_items = [
        ApiKeyListItem(
            id=ak.id,
            name=ak.name,
            user_id=ak.user_id,
            workspace_id=ak.workspace_id,
            scopes=ak.scopes,
            expires_at=ak.expires_at,
            last_used_at=ak.last_used_at,
            created_at=ak.created_at,
        )
        for ak in user_keys
    ]
    return {"api_keys": api_key_items, "total": len(api_key_items)}


@router.delete("/me/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_user_api_key(
    key_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Revoke a user-level API key."""
    result = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == current_user.id)
    )
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")

    await db.delete(api_key)
    await db.commit()


@router.post("/me/api-keys/{key_id}/regenerate", response_model=ApiKeyResponse)
async def regenerate_user_api_key(
    key_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Regenerate a user-level API key. Creates a new key value, keeping the same ID and name."""
    result = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == current_user.id)
    )
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")

    # Generate new key
    raw_key, key_hash = generate_api_key()
    api_key.key_hash = key_hash
    await db.commit()
    await db.refresh(api_key)

    return {
        "id": api_key.id,
        "name": api_key.name,
        "key": raw_key,  # Return the new raw key
        "user_id": api_key.user_id,
        "workspace_id": api_key.workspace_id,
        "scopes": api_key.scopes,
        "expires_at": api_key.expires_at,
        "created_at": api_key.created_at,
    }

