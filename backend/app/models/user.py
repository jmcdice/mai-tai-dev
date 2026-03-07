"""User model."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    """A user of the mai-tai platform."""
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)  # Nullable for OAuth users
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_admin: Mapped[bool] = mapped_column(default=False)
    settings: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # OAuth fields
    oauth_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)  # "github", "google", or None
    oauth_id: Mapped[str | None] = mapped_column(String(255), nullable=True)  # Provider's user ID

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    workspaces: Mapped[list["Workspace"]] = relationship(back_populates="owner")
    api_keys: Mapped[list["ApiKey"]] = relationship(back_populates="user")
    stash_links: Mapped[list["StashLink"]] = relationship(back_populates="user", cascade="all, delete-orphan")

