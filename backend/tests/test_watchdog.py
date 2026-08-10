"""Agent liveness watchdog (services.watchdog).

Docker is stubbed out entirely: every test decides what `get_agent_status`
reports and records whether `restart_agent` was called. What's under test is
the decision, not the container.
"""

import asyncio
import os
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.pool import NullPool

import app.services.agents as agents_pkg
import app.services.watchdog as watchdog
from tests.conftest import auth_headers, sync_engine


def run_sweep() -> int:
    """Run watchdog.sweep() on its own loop with a loop-local engine.

    Same constraint as the scheduler's run_tick: the app's pool belongs to the
    TestClient's event loop.
    """
    async def _run() -> int:
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
        from sqlalchemy.orm import sessionmaker

        url = os.environ["DATABASE_URL"].replace("postgresql://", "postgresql+asyncpg://")
        engine = create_async_engine(url, poolclass=NullPool)
        maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        original = watchdog.AsyncSessionLocal
        watchdog.AsyncSessionLocal = maker
        try:
            return await watchdog.sweep()
        finally:
            watchdog.AsyncSessionLocal = original
            await engine.dispose()

    return asyncio.run(_run())


@pytest.fixture
def docker(monkeypatch):
    """Stub the Docker-facing calls the sweep makes.

    sweep() and _revive() import these from app.services.agents at call time,
    so patching the package attributes is enough.
    """

    class Fake:
        def __init__(self):
            self.running = True
            self.started_at = _iso(datetime.utcnow() - timedelta(hours=2))
            self.restarts: list = []
            self.restart_result = {"status": "started"}
            self.blocked = None

        def status(self, workspace_id):
            return {"running": self.running, "started_at": self.started_at}

        def restart(self, **kwargs):
            self.restarts.append(kwargs)
            return self.restart_result

        def plan(self, workspace, owner):
            if self.blocked is not None:
                return self.blocked
            return agents_pkg.StartPlan(
                runtime=agents_pkg.get_runtime("claude-code"),
                kwargs={"workspace_id": workspace.id, "workspace_name": workspace.name},
            )

    fake = Fake()
    monkeypatch.setattr(agents_pkg, "get_agent_status", fake.status)
    monkeypatch.setattr(agents_pkg, "restart_agent", fake.restart)
    monkeypatch.setattr(agents_pkg, "plan_agent_start", fake.plan)
    return fake


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f000Z")


def make_agent_workspace(client, user, name: str = "Watched") -> str:
    resp = client.post(
        "/api/v1/workspaces",
        json={
            "name": name,
            "workspace_type": "agent",
            "agent_purpose": "be watched",
            "agent_config": {"runtime": "claude-code", "template": "custom"},
        },
        headers=auth_headers(user["token"]),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def set_activity(workspace_id: str, minutes_ago: float, restart_minutes_ago: float | None = None):
    """Write a heartbeat (and optionally a prior watchdog restart) directly."""
    last = datetime.utcnow() - timedelta(minutes=minutes_ago)
    restarted = (
        datetime.utcnow() - timedelta(minutes=restart_minutes_ago)
        if restart_minutes_ago is not None
        else None
    )
    with sync_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO workspace_agent_activity
                    (workspace_id, last_activity_at, last_restart_at, restart_count)
                VALUES (:ws, :last, :restarted, :count)
                ON CONFLICT (workspace_id) DO UPDATE
                    SET last_activity_at = :last,
                        last_restart_at  = :restarted,
                        restart_count    = :count
                """
            ),
            {
                "ws": workspace_id,
                "last": last,
                "restarted": restarted,
                "count": 1 if restarted else 0,
            },
        )


def read_activity(workspace_id: str) -> dict:
    with sync_engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT last_restart_at, restart_count FROM workspace_agent_activity "
                "WHERE workspace_id = :ws"
            ),
            {"ws": workspace_id},
        ).fetchone()
    return {"last_restart_at": row[0], "restart_count": row[1]} if row else {}


# ---------------------------------------------------------------------------


def test_silent_running_agent_is_restarted(client, user_a, docker):
    ws = make_agent_workspace(client, user_a)
    set_activity(ws, minutes_ago=45)

    assert run_sweep() == 1
    assert len(docker.restarts) == 1

    activity = read_activity(ws)
    assert activity["restart_count"] == 1
    assert activity["last_restart_at"] is not None


def test_recently_active_agent_is_left_alone(client, user_a, docker):
    ws = make_agent_workspace(client, user_a)
    set_activity(ws, minutes_ago=2)

    assert run_sweep() == 0
    assert docker.restarts == []


def test_stopped_container_is_not_started(client, user_a, docker):
    """Stopping an agent is an operator decision the watchdog must not undo."""
    ws = make_agent_workspace(client, user_a)
    set_activity(ws, minutes_ago=600)
    docker.running = False

    assert run_sweep() == 0
    assert docker.restarts == []


def test_freshly_started_container_gets_grace(client, user_a, docker):
    """A booting agent has no heartbeat yet — that isn't the same as a dead one."""
    ws = make_agent_workspace(client, user_a)
    set_activity(ws, minutes_ago=600)
    docker.started_at = _iso(datetime.utcnow() - timedelta(minutes=1))

    assert run_sweep() == 0
    assert docker.restarts == []


def test_agent_that_never_checked_in_is_restarted(client, user_a, docker):
    """No activity row at all, container up for hours: still dead."""
    make_agent_workspace(client, user_a)

    assert run_sweep() == 1
    assert len(docker.restarts) == 1


def test_no_second_restart_without_a_heartbeat(client, user_a, docker):
    """One restart per death. A wedged agent must not be restarted on a loop."""
    ws = make_agent_workspace(client, user_a)
    # Restarted 40m ago, and the last heartbeat predates that restart.
    set_activity(ws, minutes_ago=90, restart_minutes_ago=40)

    assert run_sweep() == 0
    assert docker.restarts == []
    assert read_activity(ws)["restart_count"] == 1


def test_rearms_once_the_agent_proves_it_can_talk(client, user_a, docker):
    """A heartbeat after the last restart means the restart worked; re-arm."""
    ws = make_agent_workspace(client, user_a)
    # Restarted 5h ago, agent checked in 4h ago, then went silent again.
    set_activity(ws, minutes_ago=240, restart_minutes_ago=300)

    assert run_sweep() == 1
    assert len(docker.restarts) == 1
    assert read_activity(ws)["restart_count"] == 2


def test_non_agent_workspaces_are_ignored(client, user_a, docker):
    resp = client.post(
        "/api/v1/workspaces",
        json={"name": "Just a chat"},
        headers=auth_headers(user_a["token"]),
    )
    ws = resp.json()["id"]
    set_activity(ws, minutes_ago=600)

    assert run_sweep() == 0
    assert docker.restarts == []


def test_unstartable_agent_is_reported_not_restarted(client, user_a, docker):
    """No credential means the restart would fail; say so instead of thrashing."""
    ws = make_agent_workspace(client, user_a)
    set_activity(ws, minutes_ago=45)
    docker.blocked = agents_pkg.StartBlocked("no_credential", "Anthropic API key is not configured")

    assert run_sweep() == 0
    assert docker.restarts == []
    # No restart recorded, so the next sweep will try again once it's fixable.
    assert read_activity(ws)["restart_count"] == 0

    resp = client.get(
        f"/api/v1/workspaces/{ws}/messages", headers=auth_headers(user_a["token"])
    )
    notes = [m["content"] for m in resp.json()["messages"] if m["message_type"] == "system"]
    assert any("Not restarted" in n for n in notes)


def test_restart_leaves_a_system_note_the_agent_will_not_see(client, user_a, docker):
    """The human needs to know; the revived agent must not wake to its own obituary."""
    ws = make_agent_workspace(client, user_a)
    set_activity(ws, minutes_ago=45)
    run_sweep()

    resp = client.get(
        f"/api/v1/workspaces/{ws}/messages", headers=auth_headers(user_a["token"])
    )
    notes = [m for m in resp.json()["messages"] if m["message_type"] == "system"]
    assert len(notes) == 1
    assert "Watchdog" in notes[0]["content"]
    # user_id is what the agent's unseen poll filters on.
    assert notes[0]["user_id"] is None


def test_docker_failure_on_one_workspace_does_not_abort_the_sweep(client, user_a, docker, monkeypatch):
    first = make_agent_workspace(client, user_a, name="Broken")
    second = make_agent_workspace(client, user_a, name="Silent")
    set_activity(first, minutes_ago=45)
    set_activity(second, minutes_ago=45)

    def flaky(workspace_id):
        if str(workspace_id) == first:
            raise RuntimeError("docker daemon unreachable")
        return {"running": True, "started_at": _iso(datetime.utcnow() - timedelta(hours=2))}

    monkeypatch.setattr(agents_pkg, "get_agent_status", flaky)

    assert run_sweep() == 1
    assert len(docker.restarts) == 1


def test_parse_docker_time_handles_nanoseconds_and_zero_value():
    assert watchdog._parse_docker_time("0001-01-01T00:00:00Z") is None
    assert watchdog._parse_docker_time("") is None
    assert watchdog._parse_docker_time(None) is None

    parsed = watchdog._parse_docker_time("2026-08-10T01:02:03.123456789Z")
    assert parsed == datetime(2026, 8, 10, 1, 2, 3, 123456)
    assert parsed.tzinfo is None
