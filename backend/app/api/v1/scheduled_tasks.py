"""Scheduled task endpoints — per-workspace recurring prompts (human/JWT side).

The agent-facing equivalents live in app/api/v1/mcp.py; both delegate to
app.services.scheduled_tasks so the two surfaces can't drift.
"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, status
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
from app.services import scheduled_tasks as svc
from app.services.scheduler import fire_task, preview_runs

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
    tasks = await svc.list_tasks(workspace_id, db)
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
    return await svc.create_task(workspace_id, data, db)


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
    task = await svc.get_task(workspace_id, task_id, db)
    return await svc.update_task(task, data, db)


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
    task = await svc.get_task(workspace_id, task_id, db)
    await svc.delete_task(task, db)


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
    await check_workspace_access(workspace_id, db, current_user)
    task = await svc.get_task(workspace_id, task_id, db)

    task.last_status = await fire_task(db, task, manual=True)
    task.last_run_at = datetime.utcnow()
    await db.commit()
    await db.refresh(task)
    return task
