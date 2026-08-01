"""Workspace task scheduler.

A single asyncio loop (started from the FastAPI lifespan) wakes every 30s and
fires due scheduled_tasks. Firing = inserting a message into the workspace
attributed to the owner with message_type='scheduled' — running agents pick
it up through the normal unseen-message poll, so no agent-side changes are
needed. Optionally wakes the agent container first.

Missed fires are skipped, not replayed: after firing (or discovering an
overdue task post-downtime), next_run_at always advances from *now* — an
agent doesn't need six stacked "hourly check" messages after a reboot.

Single-process by design: the backend runs one uvicorn worker (same
constraint the in-memory WebSocket manager already imposes).
"""

import asyncio
import logging
from datetime import datetime, timezone as dt_timezone
from zoneinfo import ZoneInfo

from croniter import croniter
from sqlalchemy import select

from app.core.websocket import manager as ws_manager
from app.db.session import AsyncSessionLocal
from app.models.message import Message
from app.models.scheduled_task import ScheduledTask
from app.models.user import User
from app.models.workspace import Workspace

logger = logging.getLogger(__name__)

TICK_SECONDS = 30


def compute_next_run(cron_expression: str, tz_name: str, after: datetime | None = None) -> datetime:
    """Next fire time as naive UTC, evaluating the cron in the task's timezone.

    Raises ValueError on a bad cron expression or timezone.
    """
    tz = ZoneInfo(tz_name)
    base_utc = (after or datetime.utcnow()).replace(tzinfo=dt_timezone.utc)
    local_next = croniter(cron_expression, base_utc.astimezone(tz)).get_next(datetime)
    return local_next.astimezone(dt_timezone.utc).replace(tzinfo=None)


def preview_runs(cron_expression: str, tz_name: str, count: int = 3) -> list[datetime]:
    """Next N fire times as naive UTC (for the schedule form preview)."""
    runs: list[datetime] = []
    after = None
    for _ in range(count):
        after = compute_next_run(cron_expression, tz_name, after=after)
        runs.append(after)
    return runs


async def fire_task(db, task: ScheduledTask, manual: bool = False) -> str:
    """Deliver one firing of a task. Returns a status string for last_status.

    Inserts the scheduled message (visible to the agent's unseen poll and
    broadcast to connected clients) and optionally wakes the agent container.
    Commit is the caller's responsibility.
    """
    workspace = await db.get(Workspace, task.workspace_id)
    if workspace is None:
        return "error: workspace missing"
    owner = await db.get(User, workspace.owner_id)

    message = Message(
        workspace_id=task.workspace_id,
        user_id=workspace.owner_id,  # attributed to owner so agents see it as unseen
        agent_name=None,
        content=task.prompt,
        message_type="scheduled",
        message_metadata={
            "scheduled_task_id": str(task.id),
            "scheduled_task_name": task.name,
            "manual": manual,
        },
    )
    db.add(message)
    await db.flush()

    await ws_manager.broadcast_to_channel(str(task.workspace_id), {
        "type": "new_message",
        "message": {
            "id": str(message.id),
            "workspace_id": str(message.workspace_id),
            "user_id": str(message.user_id),
            "agent_name": None,
            "sender_name": task.name,
            "content": message.content,
            "message_metadata": message.message_metadata,
            "created_at": message.created_at.isoformat() if message.created_at else datetime.utcnow().isoformat(),
            "message_type": "scheduled",
        },
    })

    status = "delivered"
    if task.wake_agent and workspace.workspace_type == "agent":
        status = _maybe_wake_agent(workspace, owner)

    return status


def _maybe_wake_agent(workspace: Workspace, owner: User | None) -> str:
    """Start the workspace's agent container if it isn't running."""
    from pydantic import ValidationError

    from app.core.crypto import get_user_secret
    from app.schemas.workspace import AgentConfig
    from app.services.agents import get_agent_status, get_runtime, start_agent

    try:
        if get_agent_status(workspace.id).get("running"):
            return "delivered"
    except Exception as e:
        logger.warning(f"scheduler: docker status check failed: {e}")
        return "delivered (agent status unknown)"

    try:
        config = AgentConfig.model_validate(workspace.agent_config or {})
    except ValidationError:
        return "delivered (agent config invalid — not woken)"

    runtime = get_runtime(config.runtime)
    if runtime is None or not runtime.enabled:
        return "delivered (runtime unavailable — not woken)"

    settings = (owner.settings if owner else None) or {}
    credential = get_user_secret(settings, runtime.credential_setting)
    if not credential:
        return "delivered (no credential — not woken)"

    if runtime.id == "claude-code":
        auth_env = (
            {"CLAUDE_CODE_OAUTH_TOKEN": credential}
            if credential.startswith("sk-ant-oat")
            else {"ANTHROPIC_API_KEY": credential}
        )
    else:
        auth_env = {"OPENAI_API_KEY": credential}

    result = start_agent(
        workspace_id=workspace.id,
        workspace_name=workspace.name,
        runtime=runtime.id,
        model=config.model,
        auth_env=auth_env,
        purpose=workspace.agent_purpose,
        template=config.template,
        github_token=get_user_secret(settings, "github_token") if config.template == "coder" else None,
        repo_url=config.repo_url,
    )
    if result.get("status") in ("started", "already_running"):
        return "delivered (agent woken)" if result["status"] == "started" else "delivered"
    return f"delivered (wake failed: {result.get('message', 'unknown')[:120]})"


async def tick() -> int:
    """Fire every enabled task whose next_run_at has passed. Returns count fired."""
    now = datetime.utcnow()
    fired = 0
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ScheduledTask).where(
                ScheduledTask.enabled.is_(True),
                ScheduledTask.next_run_at.isnot(None),
                ScheduledTask.next_run_at <= now,
            )
        )
        for task in result.scalars().all():
            try:
                task.last_status = await fire_task(db, task)
            except Exception as e:
                logger.error(f"scheduler: task {task.id} ({task.name}) failed: {e}")
                task.last_status = f"error: {str(e)[:200]}"
            task.last_run_at = now
            # Skip missed fires: always schedule forward from now
            try:
                task.next_run_at = compute_next_run(task.cron_expression, task.timezone)
            except ValueError as e:
                logger.error(f"scheduler: task {task.id} has invalid cron, disabling: {e}")
                task.enabled = False
            fired += 1
        await db.commit()
    return fired


async def run_scheduler(stop_event: asyncio.Event) -> None:
    """The scheduler loop. Runs until stop_event is set."""
    logger.info("scheduler: started")
    while not stop_event.is_set():
        try:
            fired = await tick()
            if fired:
                logger.info(f"scheduler: fired {fired} task(s)")
        except Exception as e:
            logger.error(f"scheduler: tick failed: {e}")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=TICK_SECONDS)
        except asyncio.TimeoutError:
            pass
    logger.info("scheduler: stopped")
