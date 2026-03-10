"""Workspace schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class WorkspaceCreate(BaseModel):
    """Schema for creating a workspace."""

    name: str = Field(default="My Workspace", min_length=1, max_length=255)
    settings: dict = Field(default_factory=dict)
    workspace_type: str = Field(default="chat", pattern="^(chat|agent)$")
    agent_purpose: str | None = None
    agent_config: dict | None = None


class WorkspaceUpdate(BaseModel):
    """Schema for updating a workspace."""

    name: str | None = Field(None, min_length=1, max_length=255)
    settings: dict | None = None
    archived: bool | None = None
    agent_purpose: str | None = None
    agent_config: dict | None = None


class WorkspaceResponse(BaseModel):
    """Schema for workspace response."""

    id: UUID
    name: str
    owner_id: UUID
    settings: dict
    archived: bool
    created_at: datetime
    updated_at: datetime
    workspace_type: str = "chat"
    agent_purpose: str | None = None
    agent_config: dict | None = None

    model_config = {"from_attributes": True}


class WorkspaceListResponse(BaseModel):
    """Schema for list of workspaces."""

    workspaces: list[WorkspaceResponse]
    total: int

