"""Authentication endpoints."""

import hashlib
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.models.system_settings import SystemSetting
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    verify_password,
)
from app.db.session import get_db
from app.models.api_key import ApiKey
from app.models.workspace import Workspace
from app.models.user import User
from app.schemas.auth import (
    OAuthLogin,
    OAuthResponse,
    PasswordChange,
    RegisterResponse,
    TokenRefresh,
    TokenResponse,
    UserCreate,
    UserResponse,
    UserUpdate,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# Rate limiter instance - uses the same key function as main.py
# The actual limiter state is stored in app.state.limiter
limiter = Limiter(key_func=get_remote_address)


def generate_api_key() -> tuple[str, str]:
    """Generate API key and its hash."""
    raw_key = f"mt_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode(), usedforsecurity=False).hexdigest()
    return raw_key, key_hash


async def is_registration_enabled(db: AsyncSession) -> bool:
    """Check if registration is enabled (DB setting overrides env var)."""
    result = await db.execute(
        select(SystemSetting).where(SystemSetting.key == "registration_enabled")
    )
    setting = result.scalar_one_or_none()
    if setting:
        return setting.value == "true"
    # Fall back to env var if no DB setting
    return get_settings().registration_enabled


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("3/minute")
async def register(
    request: Request,
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Register a new user with auto-provisioning.

    Creates:
    - User account
    - Default workspace ("My Workspace") with dude_mode disabled
    - User-level API key (works for all workspaces the user owns)

    Returns user info plus provisioning details including the raw API key.
    """
    if not await is_registration_enabled(db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is not enabled on this server",
        )

    # Check if email already exists
    result = await db.execute(select(User).where(User.email == user_in.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Check if this is the first user (will be made admin)
    user_count_result = await db.execute(select(User))
    is_first_user = len(user_count_result.all()) == 0

    # Create user with agent_type in settings if provided
    user_settings = {}
    if user_in.agent_type:
        user_settings["agent_type"] = user_in.agent_type

    user = User(
        email=user_in.email,
        name=user_in.name,
        password_hash=get_password_hash(user_in.password),
        settings=user_settings if user_settings else None,
        is_admin=is_first_user,  # First user becomes admin
    )
    db.add(user)
    await db.flush()  # Get user.id without committing

    # Create default workspace with dude_mode disabled by default
    workspace = Workspace(
        name="My Workspace",
        owner_id=user.id,
        settings={"dude_mode": False},
    )
    db.add(workspace)
    await db.flush()  # Get workspace.id

    # Create USER-LEVEL API key (works for ALL workspaces the user owns)
    raw_key, key_hash = generate_api_key()
    api_key = ApiKey(
        user_id=user.id,  # User-level key!
        workspace_id=None,  # Not bound to a specific workspace
        name="Default Agent Key",
        key_hash=key_hash,
        scopes=["read", "write"],
    )
    db.add(api_key)

    # Commit everything
    await db.commit()
    await db.refresh(user)
    await db.refresh(workspace)
    await db.refresh(api_key)

    return {
        "user": user,
        "workspace": {
            "id": workspace.id,
            "name": workspace.name,
            "settings": workspace.settings,
        },
        "api_key": {
            "id": api_key.id,
            "key": raw_key,  # Only time raw key is returned!
            "name": api_key.name,
        },
    }


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Login and get access token."""
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalar_one_or_none()

    # Check if user exists and has a password (OAuth users may not have one)
    if not user or not user.password_hash or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": str(user.id)})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("10/minute")
async def refresh_token(
    request: Request,
    token_in: TokenRefresh,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Refresh access token using refresh token."""
    payload = decode_token(token_in.refresh_token)

    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    access_token = create_access_token(data={"sub": str(user.id)})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> User:
    """Get current user info."""
    return current_user


@router.put("/me", response_model=UserResponse)
async def update_me(
    data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> User:
    """Update current user's profile."""
    if data.name is not None:
        current_user.name = data.name
    if data.avatar_url is not None:
        current_user.avatar_url = data.avatar_url
    if data.settings is not None:
        # Merge settings instead of replacing (preserve keys from other tabs)
        existing = dict(current_user.settings or {})
        existing.update(data.settings)
        # Remove keys explicitly set to None
        current_user.settings = {k: v for k, v in existing.items() if v is not None}

    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("3/minute")
async def change_password(
    request: Request,
    data: PasswordChange,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Change current user's password."""
    if not current_user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth users must set a password first",
        )
    if not verify_password(data.current_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    current_user.password_hash = get_password_hash(data.new_password)
    await db.commit()


@router.post("/oauth", response_model=OAuthResponse)
@limiter.limit("10/minute")
async def oauth_login(
    request: Request,
    data: OAuthLogin,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Login or register via OAuth provider.

    This endpoint is called by the frontend after successful OAuth authentication.
    It either finds an existing user or creates a new one with auto-provisioning.

    Flow:
    1. Check if user exists by oauth_provider + oauth_id
    2. If not, check if user exists by email (for account linking)
    3. If exists, update OAuth fields and return JWT
    4. If not, create new user + workspace + API key, return JWT
    """
    if data.provider not in ("github", "google"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OAuth provider. Must be 'github' or 'google'.",
        )

    if not get_settings().registration_enabled:
        # Only block new OAuth users, not existing ones logging in
        result = await db.execute(
            select(User).where(
                (User.oauth_provider == data.provider) & (User.oauth_id == data.oauth_id)
            )
        )
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Registration is not enabled on this server",
            )

    is_new_user = False

    # 1. Check if user exists by oauth_provider + oauth_id
    result = await db.execute(
        select(User).where(
            User.oauth_provider == data.provider,
            User.oauth_id == data.oauth_id,
        )
    )
    user = result.scalar_one_or_none()

    # For new users, store provisioned resources to return
    provisioned_workspace = None
    provisioned_api_key = None
    raw_key = None

    if not user:
        # 2. Check if user exists by email (for account linking)
        result = await db.execute(select(User).where(User.email == data.email))
        user = result.scalar_one_or_none()

        if user:
            # Link OAuth to existing account
            user.oauth_provider = data.provider
            user.oauth_id = data.oauth_id
            if data.avatar_url and not user.avatar_url:
                user.avatar_url = data.avatar_url
            await db.commit()
            await db.refresh(user)
        else:
            # 3. Create new user with auto-provisioning
            is_new_user = True

            # Check if this is the first user (will be made admin)
            user_count_result = await db.execute(select(User))
            is_first_user = len(user_count_result.all()) == 0

            user = User(
                email=data.email,
                name=data.name,
                password_hash=None,  # OAuth users don't have a password initially
                avatar_url=data.avatar_url,
                oauth_provider=data.provider,
                oauth_id=data.oauth_id,
                is_admin=is_first_user,  # First user becomes admin
            )
            db.add(user)
            await db.flush()

            # Create default workspace with dude_mode disabled by default
            workspace = Workspace(
                name="My Workspace",
                owner_id=user.id,
                settings={"dude_mode": False},
            )
            db.add(workspace)
            await db.flush()

            # Create user-level API key
            raw_key, key_hash = generate_api_key()
            api_key = ApiKey(
                user_id=user.id,
                workspace_id=None,
                name="Default Agent Key",
                key_hash=key_hash,
                scopes=["read", "write"],
            )
            db.add(api_key)

            await db.commit()
            await db.refresh(user)
            await db.refresh(workspace)
            await db.refresh(api_key)

            # Store provisioned resources to return
            provisioned_workspace = {
                "id": workspace.id,
                "name": workspace.name,
                "settings": workspace.settings,
            }
            provisioned_api_key = {
                "id": api_key.id,
                "key": raw_key,  # Only time raw key is returned!
                "name": api_key.name,
            }

    # Generate tokens
    access_token = create_access_token(data={"sub": str(user.id)})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "is_new_user": is_new_user,
        "user": user,
        "workspace": provisioned_workspace,
        "api_key": provisioned_api_key,
    }

