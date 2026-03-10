"""Workspace model."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Workspace(Base):
    """A workspace is a single chat space for a user."""
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="My Workspace")
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    settings: Mapped[dict] = mapped_column(JSONB, default=dict)
    archived: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)

    # Agent workspace fields
    workspace_type: Mapped[str] = mapped_column(String(20), default="chat", server_default="chat")
    agent_purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Relationships
    owner: Mapped["User"] = relationship(back_populates="workspaces")
    agents: Mapped[list["Agent"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")
    messages: Mapped[list["Message"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")
    api_keys: Mapped[list["ApiKey"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")

