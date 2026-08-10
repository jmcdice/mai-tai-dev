"""Workspace Agent Activity model."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class WorkspaceAgentActivity(Base):
    """Tracks agent activity per-workspace.

    Updated on every MCP API call. Used to display correct agent status
    (green/yellow/gray dot) for user-level API keys.

    Primary key is workspace_id - each workspace has at most one activity record.
    """
    __tablename__ = "workspace_agent_activity"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        primary_key=True
    )
    last_activity_at: Mapped[datetime] = mapped_column(nullable=False)
    api_key_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("api_keys.id", ondelete="SET NULL"),
        nullable=True
    )

    # Watchdog bookkeeping. last_restart_at is load-bearing, not just a stat:
    # the watchdog only intervenes again once last_activity_at has moved past
    # it, which is what stops a permanently wedged agent from being restarted
    # on a loop forever. See app/services/watchdog.py.
    last_restart_at: Mapped[datetime | None] = mapped_column(nullable=True)
    restart_count: Mapped[int] = mapped_column(nullable=False, default=0, server_default="0")

    # Relationships
    workspace: Mapped["Workspace"] = relationship()
    api_key: Mapped["ApiKey"] = relationship()

