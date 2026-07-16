"""Workspace schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.services.agents.runtimes import RUNTIMES
from app.services.agents.templates import AGENT_TEMPLATES


class AgentConfig(BaseModel):
    """Validated shape of workspace.agent_config.

    Stored as JSONB; extra keys are preserved for forward compatibility.
    """

    runtime: str = "claude-code"
    model: str | None = None  # falls back to the runtime default
    template: str = "custom"
    repo_url: str | None = None

    model_config = {"extra": "allow"}

    @field_validator("runtime")
    @classmethod
    def runtime_must_be_known(cls, v: str) -> str:
        if v not in RUNTIMES:
            valid = ", ".join(sorted(RUNTIMES))
            raise ValueError(f"Unknown runtime '{v}'. Valid runtimes: {valid}")
        return v

    @field_validator("template")
    @classmethod
    def template_must_be_known(cls, v: str) -> str:
        if v not in AGENT_TEMPLATES:
            valid = ", ".join(sorted(AGENT_TEMPLATES))
            raise ValueError(f"Unknown template '{v}'. Valid templates: {valid}")
        return v


class WorkspaceCreate(BaseModel):
    """Schema for creating a workspace."""

    name: str = Field(default="My Workspace", min_length=1, max_length=255)
    settings: dict = Field(default_factory=dict)
    workspace_type: str = Field(default="chat", pattern="^(chat|agent)$")
    agent_purpose: str | None = None
    agent_config: AgentConfig | None = None


class WorkspaceUpdate(BaseModel):
    """Schema for updating a workspace."""

    name: str | None = Field(None, min_length=1, max_length=255)
    settings: dict | None = None
    archived: bool | None = None
    agent_purpose: str | None = None
    agent_config: AgentConfig | None = None


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

