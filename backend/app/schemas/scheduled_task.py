"""Scheduled task schemas."""

from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from croniter import croniter
from pydantic import BaseModel, Field, field_validator


def _validate_cron(value: str) -> str:
    if not croniter.is_valid(value):
        raise ValueError(f"Invalid cron expression: '{value}'")
    return value


def _validate_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except Exception:
        raise ValueError(f"Unknown timezone: '{value}'")
    return value


class ScheduledTaskCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    prompt: str = Field(..., min_length=1, max_length=10000)
    cron_expression: str = Field(..., max_length=100)
    timezone: str = Field(default="UTC", max_length=64)
    enabled: bool = True
    wake_agent: bool = True

    _cron = field_validator("cron_expression")(_validate_cron)
    _tz = field_validator("timezone")(_validate_timezone)


class ScheduledTaskUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    prompt: str | None = Field(None, min_length=1, max_length=10000)
    cron_expression: str | None = Field(None, max_length=100)
    timezone: str | None = Field(None, max_length=64)
    enabled: bool | None = None
    wake_agent: bool | None = None

    @field_validator("cron_expression")
    @classmethod
    def cron_valid(cls, v: str | None) -> str | None:
        return None if v is None else _validate_cron(v)

    @field_validator("timezone")
    @classmethod
    def tz_valid(cls, v: str | None) -> str | None:
        return None if v is None else _validate_timezone(v)


class ScheduledTaskResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    prompt: str
    cron_expression: str
    timezone: str
    enabled: bool
    wake_agent: bool
    next_run_at: datetime | None
    last_run_at: datetime | None
    last_status: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ScheduledTaskListResponse(BaseModel):
    tasks: list[ScheduledTaskResponse]
    total: int


class SchedulePreviewRequest(BaseModel):
    cron_expression: str = Field(..., max_length=100)
    timezone: str = Field(default="UTC", max_length=64)

    _cron = field_validator("cron_expression")(_validate_cron)
    _tz = field_validator("timezone")(_validate_timezone)


class SchedulePreviewResponse(BaseModel):
    next_runs: list[datetime]  # naive UTC
