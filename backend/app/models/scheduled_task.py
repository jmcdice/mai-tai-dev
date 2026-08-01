"""Scheduled task model — per-workspace recurring prompts."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ScheduledTask(Base):
    """A recurring prompt delivered into a workspace on a cron schedule.

    Firing inserts a message (message_type='scheduled') attributed to the
    workspace owner, so running agents pick it up through the normal
    unseen-message flow — no agent-side support required.
    """
    __tablename__ = "scheduled_tasks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    cron_expression: Mapped[str] = mapped_column(String(100), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    wake_agent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # UTC-naive, matching the codebase convention
    next_run_at: Mapped[datetime | None] = mapped_column(nullable=True, index=True)
    last_run_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)

    workspace: Mapped["Workspace"] = relationship()
