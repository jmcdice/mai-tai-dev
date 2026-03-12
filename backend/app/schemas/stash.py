"""StashAI schemas."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class StashLinkCreate(BaseModel):
    url: str
    title: str | None = None
    description: str | None = None
    thumbnail_url: str | None = None
    tags: list[str] = []
    notes: str | None = None


class StashLinkUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    thumbnail_url: str | None = None
    tags: list[str] | None = None
    status: Literal["unread", "read", "archived"] | None = None
    notes: str | None = None


class StashLinkResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    issue_number: int
    url: str
    title: str | None
    description: str | None
    thumbnail_url: str | None
    tags: list[str]
    status: str
    notes: str | None
    summary: str | None = None
    ai_title: str | None = None
    ai_tags: list[str] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class StashLinkListResponse(BaseModel):
    links: list[StashLinkResponse]
    total: int


class UrlMetadata(BaseModel):
    url: str
    title: str | None = None
    description: str | None = None
    thumbnail_url: str | None = None
