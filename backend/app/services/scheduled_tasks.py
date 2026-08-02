"""Scheduled-task CRUD shared by the two callers that can reach it.

Humans reach scheduled tasks with a JWT (app/api/v1/scheduled_tasks.py);
agents reach them with an API key (app/api/v1/mcp.py). Both need the same
create/update semantics — in particular, that any change to the cron, the
timezone, or the enabled flag has to recompute next_run_at, because the
scheduler only ever looks at next_run_at. Two copies of that rule is one copy
too many: the copy nobody edits is the one that silently stops firing.
"""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scheduled_task import ScheduledTask
from app.schemas.scheduled_task import ScheduledTaskCreate, ScheduledTaskUpdate
from app.services.scheduler import compute_next_run

# A ceiling on tasks per workspace. Nothing here is expensive, but an agent
# that can create schedules can also create a schedule that wakes it up to
# create more schedules. This makes that a bounded mistake.
MAX_TASKS_PER_WORKSPACE = 25


async def list_tasks(workspace_id: UUID, db: AsyncSession) -> list[ScheduledTask]:
    result = await db.execute(
        select(ScheduledTask)
        .where(ScheduledTask.workspace_id == workspace_id)
        .order_by(ScheduledTask.created_at)
    )
    return list(result.scalars().all())


async def get_task(workspace_id: UUID, task_id: UUID, db: AsyncSession) -> ScheduledTask:
    """Fetch one task, scoped to the workspace. 404s rather than leaking."""
    result = await db.execute(
        select(ScheduledTask).where(
            ScheduledTask.id == task_id, ScheduledTask.workspace_id == workspace_id
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Scheduled task not found")
    return task


async def create_task(
    workspace_id: UUID, data: ScheduledTaskCreate, db: AsyncSession
) -> ScheduledTask:
    count = await db.scalar(
        select(func.count())
        .select_from(ScheduledTask)
        .where(ScheduledTask.workspace_id == workspace_id)
    )
    if count >= MAX_TASKS_PER_WORKSPACE:
        raise HTTPException(
            status_code=409,
            detail=(
                f"This workspace already has {count} scheduled tasks "
                f"(limit {MAX_TASKS_PER_WORKSPACE}). Delete one first."
            ),
        )

    task = ScheduledTask(
        workspace_id=workspace_id,
        name=data.name,
        prompt=data.prompt,
        cron_expression=data.cron_expression,
        timezone=data.timezone,
        enabled=data.enabled,
        wake_agent=data.wake_agent,
        next_run_at=compute_next_run(data.cron_expression, data.timezone) if data.enabled else None,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return task


async def update_task(
    task: ScheduledTask, data: ScheduledTaskUpdate, db: AsyncSession
) -> ScheduledTask:
    for field, value in data.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(task, field, value)

    # Recompute unconditionally: a disabled task must lose its next_run_at, and
    # a re-enabled one must get a fresh one rather than an expired timestamp
    # that would fire the instant it's switched back on.
    task.next_run_at = (
        compute_next_run(task.cron_expression, task.timezone) if task.enabled else None
    )

    await db.commit()
    await db.refresh(task)
    return task


async def delete_task(task: ScheduledTask, db: AsyncSession) -> None:
    await db.delete(task)
    await db.commit()
