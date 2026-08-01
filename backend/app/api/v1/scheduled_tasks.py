"""Scheduled task endpoints — per-workspace recurring prompts."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.v1.workspaces import check_workspace_access
from app.models.scheduled_task import ScheduledTask
from app.models.user import User
from app.schemas.scheduled_task import (
    SchedulePreviewRequest,
    SchedulePreviewResponse,
    ScheduledTaskCreate,
    ScheduledTaskListResponse,
    ScheduledTaskResponse,
    ScheduledTaskUpdate,
)
from app.services.scheduler import compute_next_run, fire_task, preview_runs

router = APIRouter(tags=["scheduled-tasks"])


@router.post("/schedule-preview", response_model=SchedulePreviewResponse)
async def schedule_preview(
    data: SchedulePreviewRequest,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Next fire times for a cron expression — powers the form's live preview."""
    return {"next_runs": preview_runs(data.cron_expression, data.timezone)}


@router.get("/workspaces/{workspace_id}/scheduled-tasks", response_model=ScheduledTaskListResponse)
async def list_scheduled_tasks(
    workspace_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    await check_workspace_access(workspace_id, db, current_user)
    result = await db.execute(
        select(ScheduledTask)
        .where(ScheduledTask.workspace_id == workspace_id)
        .order_by(ScheduledTask.created_at)
    )
    tasks = result.scalars().all()
    return {"tasks": tasks, "total": len(tasks)}


@router.post(
    "/workspaces/{workspace_id}/scheduled-tasks",
    response_model=ScheduledTaskResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_scheduled_task(
    workspace_id: UUID,
    data: ScheduledTaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ScheduledTask:
    await check_workspace_access(workspace_id, db, current_user)

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


async def _get_task(workspace_id: UUID, task_id: UUID, db: AsyncSession) -> ScheduledTask:
    result = await db.execute(
        select(ScheduledTask).where(
            ScheduledTask.id == task_id, ScheduledTask.workspace_id == workspace_id
        )
    )
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Scheduled task not found")
    return task


@router.patch(
    "/workspaces/{workspace_id}/scheduled-tasks/{task_id}",
    response_model=ScheduledTaskResponse,
)
async def update_scheduled_task(
    workspace_id: UUID,
    task_id: UUID,
    data: ScheduledTaskUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ScheduledTask:
    await check_workspace_access(workspace_id, db, current_user)
    task = await _get_task(workspace_id, task_id, db)

    if data.name is not None:
        task.name = data.name
    if data.prompt is not None:
        task.prompt = data.prompt
    if data.cron_expression is not None:
        task.cron_expression = data.cron_expression
    if data.timezone is not None:
        task.timezone = data.timezone
    if data.wake_agent is not None:
        task.wake_agent = data.wake_agent
    if data.enabled is not None:
        task.enabled = data.enabled

    # Any change to schedule or enablement recomputes the next fire
    task.next_run_at = (
        compute_next_run(task.cron_expression, task.timezone) if task.enabled else None
    )

    await db.commit()
    await db.refresh(task)
    return task


@router.delete(
    "/workspaces/{workspace_id}/scheduled-tasks/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_scheduled_task(
    workspace_id: UUID,
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    await check_workspace_access(workspace_id, db, current_user)
    task = await _get_task(workspace_id, task_id, db)
    await db.delete(task)
    await db.commit()


@router.post(
    "/workspaces/{workspace_id}/scheduled-tasks/{task_id}/run",
    response_model=ScheduledTaskResponse,
)
async def run_scheduled_task_now(
    workspace_id: UUID,
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ScheduledTask:
    """Fire a task immediately (does not affect its regular schedule)."""
    from datetime import datetime

    await check_workspace_access(workspace_id, db, current_user)
    task = await _get_task(workspace_id, task_id, db)

    task.last_status = await fire_task(db, task, manual=True)
    task.last_run_at = datetime.utcnow()
    await db.commit()
    await db.refresh(task)
    return task
