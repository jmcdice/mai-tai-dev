"""API dependencies for authentication and authorization."""

import hashlib
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.iap import IAPUserInfo, IAPValidationError, validate_iap_jwt
from app.core.security import decode_token
from app.db.session import get_db as _get_db
from app.models.api_key import ApiKey
from app.models.workspace import Workspace
from app.models.workspace_agent_activity import WorkspaceAgentActivity
from app.models.user import User

logger = logging.getLogger(__name__)

# Re-export get_db for use in route modules
get_db = _get_db

# OAuth2 scheme for local development (JWT tokens)
# auto_error=False so we can fall back to IAP in production
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


async def get_or_create_user_from_iap(
    db: AsyncSession, iap_info: IAPUserInfo
) -> User:
    """Get existing user or create new one from IAP info (auto-provisioning)."""
    # First try to find by email
    result = await db.execute(select(User).where(User.email == iap_info.email))
    user = result.scalar_one_or_none()

    if user:
        # Update last login time (could add google_sub if not set)
        return user

    # Create new user (auto-provisioning on first login)
    user = User(
        email=iap_info.email,
        name=iap_info.name or iap_info.email.split("@")[0],
        password_hash="",  # No password for IAP users
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    logger.info(f"Auto-provisioned new user from IAP: {iap_info.email}")
    return user


async def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Get the current authenticated user.

    Supports dual-mode authentication:
    - Production (USE_IAP=true): Validates X-Goog-IAP-JWT-Assertion header
    - Development (USE_IAP=false): Validates Bearer JWT token
    """
    settings = get_settings()
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if settings.use_iap:
        # Production mode: validate IAP JWT from header
        iap_jwt = request.headers.get("X-Goog-IAP-JWT-Assertion")
        if not iap_jwt:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing IAP authentication",
            )

        try:
            iap_info = validate_iap_jwt(iap_jwt)
        except IAPValidationError as e:
            logger.warning(f"IAP validation failed: {e}")
            raise credentials_exception

        # Get or create user from IAP info
        return await get_or_create_user_from_iap(db, iap_info)

    else:
        # Development mode: validate JWT Bearer token
        if not token:
            raise credentials_exception

        payload = decode_token(token)
        if payload is None:
            raise credentials_exception

        if payload.get("type") != "access":
            raise credentials_exception

        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise credentials_exception

        try:
            uuid = UUID(user_id)
        except ValueError:
            raise credentials_exception

        result = await db.execute(select(User).where(User.id == uuid))
        user = result.scalar_one_or_none()

        if user is None:
            raise credentials_exception

        return user


async def _record_workspace_activity(
    db: AsyncSession, workspace_id: UUID, api_key_id: UUID
) -> None:
    """Record agent activity for a workspace (upsert).

    Called on every MCP API request to track when agents are active.
    Uses INSERT ... ON CONFLICT DO UPDATE for atomic upsert.
    """
    now = datetime.utcnow()

    # Try to get existing activity record
    result = await db.execute(
        select(WorkspaceAgentActivity).where(
            WorkspaceAgentActivity.workspace_id == workspace_id
        )
    )
    activity = result.scalar_one_or_none()

    if activity:
        # Update existing record
        activity.last_activity_at = now
        activity.api_key_id = api_key_id
    else:
        # Create new record
        activity = WorkspaceAgentActivity(
            workspace_id=workspace_id,
            last_activity_at=now,
            api_key_id=api_key_id
        )
        db.add(activity)

    await db.commit()


class ApiKeyAuth:
    """Container for API key authentication result."""

    def __init__(self, api_key: ApiKey, workspace: Workspace, user: Optional[User] = None):
        self.api_key = api_key
        self.workspace = workspace
        self.workspace_id = workspace.id
        self.user = user  # Only set for user-level API keys


async def get_api_key_auth(
    x_api_key: str | None = Header(None),
    x_workspace_id: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
) -> ApiKeyAuth:
    """Authenticate using X-API-Key header. Returns API key and workspace.

    For user-level API keys (api_key.user_id is set), the X-Workspace-ID header
    is required and must reference a workspace owned by the user.

    For workspace-level API keys (api_key.workspace_id is set), the X-Workspace-ID
    header is optional and ignored (the key's bound workspace is used).
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-API-Key header required",
        )

    # Hash the provided key to compare with stored hash
    key_hash = hashlib.sha256(x_api_key.encode()).hexdigest()

    result = await db.execute(select(ApiKey).where(ApiKey.key_hash == key_hash))
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    # Check if expired
    if api_key.expires_at and api_key.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key has expired",
        )

    # Update last_used_at (use naive datetime to match DB column)
    api_key.last_used_at = datetime.utcnow()
    await db.commit()

    # Determine which workspace to use based on key type
    if api_key.is_user_level:
        # User-level key: X-Workspace-ID header is required
        if not x_workspace_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="X-Workspace-ID header required for user-level API keys",
            )

        try:
            workspace_uuid = UUID(x_workspace_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid X-Workspace-ID format",
            )

        # Get the workspace and verify ownership
        result = await db.execute(select(Workspace).where(Workspace.id == workspace_uuid))
        workspace = result.scalar_one_or_none()

        if not workspace:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace not found",
            )

        # Verify the user owns this workspace
        if workspace.owner_id != api_key.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="API key does not have access to this workspace",
            )

        # Get the user for context
        result = await db.execute(select(User).where(User.id == api_key.user_id))
        user = result.scalar_one_or_none()

        # Record workspace agent activity
        await _record_workspace_activity(db, workspace.id, api_key.id)

        return ApiKeyAuth(api_key=api_key, workspace=workspace, user=user)

    else:
        # Workspace-level key: use the bound workspace
        result = await db.execute(select(Workspace).where(Workspace.id == api_key.workspace_id))
        workspace = result.scalar_one_or_none()

        if not workspace:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace not found",
            )

        # Record workspace agent activity
        await _record_workspace_activity(db, workspace.id, api_key.id)

        return ApiKeyAuth(api_key=api_key, workspace=workspace)

