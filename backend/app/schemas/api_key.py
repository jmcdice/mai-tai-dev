"""API Key schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.core.scopes import DEFAULT_SCOPES, KNOWN_SCOPES


def _validate_scopes(scopes: list[str]) -> list[str]:
    """Reject scope names the deployment doesn't implement.

    Scopes are now enforced, which means a typo silently produces a key that
    is missing a permission rather than one that has an extra unused label.
    Failing at creation is the only point where the caller can still see what
    they meant to type.
    """
    unknown = sorted(set(scopes) - KNOWN_SCOPES)
    if unknown:
        raise ValueError(
            f"unknown scope(s): {', '.join(unknown)}. "
            f"Valid scopes: {', '.join(sorted(KNOWN_SCOPES))}"
        )
    return scopes


class ApiKeyCreate(BaseModel):
    """Schema for creating an API key (workspace-scoped)."""

    name: str = Field(..., min_length=1, max_length=255)
    scopes: list[str] = Field(default_factory=lambda: list(DEFAULT_SCOPES))
    expires_in_days: int | None = Field(None, gt=0)

    _check_scopes = field_validator("scopes")(_validate_scopes)


class UserApiKeyCreate(BaseModel):
    """Schema for creating a user-level API key."""

    name: str = Field(..., min_length=1, max_length=255)
    scopes: list[str] = Field(default_factory=lambda: list(DEFAULT_SCOPES))
    expires_in_days: int | None = Field(None, gt=0)

    _check_scopes = field_validator("scopes")(_validate_scopes)


class ApiKeyResponse(BaseModel):
    """Schema for API key response (includes key, only on creation)."""

    id: UUID
    name: str
    key: str  # Only returned on creation!
    user_id: UUID | None = None
    workspace_id: UUID | None = None
    scopes: list[str]
    expires_at: datetime | None
    created_at: datetime

    @property
    def is_user_level(self) -> bool:
        """Return True if this is a user-level API key."""
        return self.user_id is not None


class ApiKeyListItem(BaseModel):
    """Schema for API key list item (no key shown)."""

    id: UUID
    name: str | None
    user_id: UUID | None = None
    workspace_id: UUID | None = None
    scopes: list[str]
    expires_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}

    @property
    def is_user_level(self) -> bool:
        """Return True if this is a user-level API key."""
        return self.user_id is not None


class ApiKeyListResponse(BaseModel):
    """Schema for list of API keys."""

    api_keys: list[ApiKeyListItem]
    total: int

