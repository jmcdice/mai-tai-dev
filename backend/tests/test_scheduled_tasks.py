"""Scheduled tasks: cron math, CRUD, run-now, and the scheduler tick."""

import asyncio
import os
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.pool import NullPool

from app.services.scheduler import compute_next_run, preview_runs
from tests.conftest import auth_headers, sync_engine
from tests.test_mcp_messages import mcp_headers


def run_tick() -> int:
    """Run scheduler.tick() on its own loop with a loop-local engine.

    The app's async engine pool is bound to the TestClient's event loop;
    reusing it from a fresh loop deadlocks. Swap in a NullPool engine for
    the duration of the tick.
    """
    async def _run() -> int:
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
        from sqlalchemy.orm import sessionmaker

        import app.services.scheduler as sched

        url = os.environ["DATABASE_URL"].replace("postgresql://", "postgresql+asyncpg://")
        engine = create_async_engine(url, poolclass=NullPool)
        maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        original = sched.AsyncSessionLocal
        sched.AsyncSessionLocal = maker
        try:
            return await sched.tick()
        finally:
            sched.AsyncSessionLocal = original
            await engine.dispose()

    return asyncio.run(_run())


def make_task(client, user, **overrides) -> dict:
    payload = {
        "name": "Morning report",
        "prompt": "Summarize overnight activity",
        "cron_expression": "0 9 * * 1-5",
        "timezone": "America/Denver",
        "wake_agent": False,
    }
    payload.update(overrides)
    resp = client.post(
        f"/api/v1/workspaces/{user['workspace_id']}/scheduled-tasks",
        json=payload,
        headers=auth_headers(user["token"]),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# --- cron math ---------------------------------------------------------------


def test_compute_next_run_respects_timezone():
    # 9:00 in Denver is 15:00 or 16:00 UTC depending on DST — never 9:00 UTC
    after = datetime(2026, 7, 16, 0, 0)
    next_run = compute_next_run("0 9 * * *", "America/Denver", after=after)
    assert next_run == datetime(2026, 7, 16, 15, 0)  # MDT = UTC-6


def test_preview_runs_sequential():
    runs = preview_runs("0 * * * *", "UTC", count=3)
    assert len(runs) == 3
    assert runs[0] < runs[1] < runs[2]
    assert (runs[1] - runs[0]) == timedelta(hours=1)


# --- CRUD --------------------------------------------------------------------


def test_create_computes_next_run(client, user_a):
    task = make_task(client, user_a)
    assert task["next_run_at"] is not None
    assert task["enabled"] is True


def test_invalid_cron_rejected(client, user_a):
    resp = client.post(
        f"/api/v1/workspaces/{user_a['workspace_id']}/scheduled-tasks",
        json={"name": "x", "prompt": "y", "cron_expression": "not a cron"},
        headers=auth_headers(user_a["token"]),
    )
    assert resp.status_code == 422

    resp = client.post(
        f"/api/v1/workspaces/{user_a['workspace_id']}/scheduled-tasks",
        json={"name": "x", "prompt": "y", "cron_expression": "0 9 * * *", "timezone": "Mars/Olympus"},
        headers=auth_headers(user_a["token"]),
    )
    assert resp.status_code == 422


def test_disable_clears_next_run(client, user_a):
    task = make_task(client, user_a)
    resp = client.patch(
        f"/api/v1/workspaces/{user_a['workspace_id']}/scheduled-tasks/{task['id']}",
        json={"enabled": False},
        headers=auth_headers(user_a["token"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is False
    assert body["next_run_at"] is None

    # Re-enable restores the schedule
    resp = client.patch(
        f"/api/v1/workspaces/{user_a['workspace_id']}/scheduled-tasks/{task['id']}",
        json={"enabled": True},
        headers=auth_headers(user_a["token"]),
    )
    assert resp.json()["next_run_at"] is not None


def test_tasks_scoped_to_workspace_owner(client, user_a, user_b):
    task = make_task(client, user_a)
    resp = client.get(
        f"/api/v1/workspaces/{user_a['workspace_id']}/scheduled-tasks",
        headers=auth_headers(user_b["token"]),
    )
    assert resp.status_code == 404  # workspace not visible to B

    resp = client.delete(
        f"/api/v1/workspaces/{user_a['workspace_id']}/scheduled-tasks/{task['id']}",
        headers=auth_headers(user_b["token"]),
    )
    assert resp.status_code == 404


def test_schedule_preview_endpoint(client, user_a):
    resp = client.post(
        "/api/v1/schedule-preview",
        json={"cron_expression": "0 9 * * 1-5", "timezone": "America/Denver"},
        headers=auth_headers(user_a["token"]),
    )
    assert resp.status_code == 200
    assert len(resp.json()["next_runs"]) == 3


# --- firing ------------------------------------------------------------------


def test_run_now_delivers_message_to_agent(client, user_a):
    task = make_task(client, user_a, name="Fire drill", prompt="check the perimeter")
    resp = client.post(
        f"/api/v1/workspaces/{user_a['workspace_id']}/scheduled-tasks/{task['id']}/run",
        headers=auth_headers(user_a["token"]),
    )
    assert resp.status_code == 200
    assert resp.json()["last_status"] == "delivered"
    assert resp.json()["last_run_at"] is not None

    # The fired prompt is an unseen user-attributed message for the agent
    resp = client.get(
        "/api/v1/mcp/messages", params={"unseen": True}, headers=mcp_headers(user_a)
    )
    messages = resp.json()["messages"]
    assert len(messages) == 1
    assert "check the perimeter" in messages[0]["content"]


def test_scheduler_tick_fires_due_tasks(client, user_a):
    task = make_task(client, user_a, name="Overdue", prompt="do the overdue thing")

    # Force the task overdue
    past = datetime.utcnow() - timedelta(minutes=5)
    with sync_engine.begin() as conn:
        conn.execute(
            text("UPDATE scheduled_tasks SET next_run_at = :past WHERE id = :id"),
            {"past": past, "id": task["id"]},
        )

    fired = run_tick()
    assert fired == 1

    # next_run_at advanced into the future (missed fires skipped)
    with sync_engine.begin() as conn:
        row = conn.execute(
            text("SELECT next_run_at, last_status FROM scheduled_tasks WHERE id = :id"),
            {"id": task["id"]},
        ).fetchone()
    assert row[0] > datetime.utcnow()
    assert row[1] == "delivered"

    # Message landed in the workspace
    resp = client.get(
        f"/api/v1/workspaces/{user_a['workspace_id']}/messages",
        headers=auth_headers(user_a["token"]),
    )
    contents = [m["content"] for m in resp.json()["messages"]]
    assert "do the overdue thing" in contents


def test_tick_skips_disabled_and_future_tasks(client, user_a):
    make_task(client, user_a, name="future")  # next run is tomorrow 9am
    disabled = make_task(client, user_a, name="disabled", enabled=False)
    assert disabled["next_run_at"] is None

    fired = run_tick()
    assert fired == 0
