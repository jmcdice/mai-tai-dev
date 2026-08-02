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


class AgentScheduledTaskCreate(ScheduledTaskCreate):
    """Create payload for the agent-facing (API-key) surface.

    Identical to the human one except that `timezone` is required. A human
    picks it from a dropdown that shows their own zone; an agent handed "every
    morning at 5" has nothing to infer from, and the UTC default would put
    Joey's 5am job at 10pm the night before without anything looking wrong.
    """

    timezone: str = Field(..., min_length=1, max_length=64)

    _tz_required = field_validator("timezone")(_validate_timezone)


class ScheduledTaskWithPreview(ScheduledTaskResponse):
    """A task plus its upcoming fire times, so an agent can read them back.

    The agent has to confirm a schedule in plain language ("that's 5:00 AM
    Mountain, next three: ..."); making it derive those from a cron string
    itself is how you get a confident, wrong answer.

    These carry the task's timezone offset, unlike the naive-UTC times the web
    form gets. There's no browser in front of an agent to localise them, and an
    unlabelled 11:00 on a Denver task reads as 11am.
    """

    next_runs: list[datetime]


class AgentScheduledTaskListResponse(BaseModel):
    """List for the agent surface — same shape as create and patch return.

    "What do I have scheduled?" is the question most likely to be answered out
    loud to the human, so it's the last place that should omit the fire times.
    """

    tasks: list[ScheduledTaskWithPreview]
    total: int


class SchedulePreviewRequest(BaseModel):
    cron_expression: str = Field(..., max_length=100)
    timezone: str = Field(default="UTC", max_length=64)

    _cron = field_validator("cron_expression")(_validate_cron)
    _tz = field_validator("timezone")(_validate_timezone)


class SchedulePreviewResponse(BaseModel):
    next_runs: list[datetime]  # naive UTC


class AgentSchedulePreviewResponse(BaseModel):
    """Preview for the agent surface: aware datetimes in the requested zone.

    Same field, deliberately different contract — see ScheduledTaskWithPreview.
    """

    next_runs: list[datetime]
