"""Agent liveness watchdog.

Agents call the MCP API roughly every three seconds — the driver polls between
turns, and `chat_with_human` / `wait_for_human` poll while they block — so
`workspace_agent_activity.last_activity_at` is a real heartbeat rather than an
approximation. A container that is *running* while that heartbeat has gone
silent is the failure this exists for: the process is up, `docker ps` is
green, and the agent stopped being an agent some hours ago.

That shape has shown up repeatedly and never the same way twice: a supervisor
timeout with no TTY, a session rotating into a memoryless cold start, an MCP
tool call killed by an idle timeout, an MCP client that gave up while the
server process stayed alive. What they have in common isn't a cause, it's a
symptom — silence with the lights on. Watching the symptom catches the next
one too.

Deliberately not an agent. Something whose job is noticing that agents have
stopped responding cannot itself be an agent, because it fails in exactly the
ways it is supposed to detect. This is a plain asyncio loop reading a
timestamp column.

Two things it will not do:

- **Start a stopped container.** Stopping an agent is an explicit operator
  action. A watchdog that undoes it is a watchdog you turn off.
- **Restart twice without evidence the first one worked.** The agent must
  produce at least one heartbeat after a restart before it is eligible again.
  A wedged agent therefore gets exactly one restart, then waits for a human —
  and re-arms on its own the moment it comes back to life.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone as dt_timezone

from sqlalchemy import select

from app.core.config import get_settings
from app.core.websocket import manager as ws_manager
from app.db.session import AsyncSessionLocal
from app.models.message import Message
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_agent_activity import WorkspaceAgentActivity

logger = logging.getLogger(__name__)

TICK_SECONDS = 60


def _parse_docker_time(value: str | None) -> datetime | None:
    """Parse Docker's RFC3339 timestamp into naive UTC.

    Docker returns nanosecond precision ("...T01:02:03.123456789Z") which
    fromisoformat rejects on older Pythons, and a zero value
    ("0001-01-01T00:00:00Z") for a container that has never run. Both come
    back as None rather than raising into the sweep loop.
    """
    if not value or value.startswith("0001-01-01"):
        return None
    text = value.replace("Z", "+00:00")
    if "." in text:
        head, _, tail = text.partition(".")
        frac, sign, offset = (
            tail.partition("+") if "+" in tail else tail.partition("-")
        )
        text = f"{head}.{frac[:6]}{sign}{offset}"
    try:
        return datetime.fromisoformat(text).astimezone(dt_timezone.utc).replace(tzinfo=None)
    except ValueError:
        logger.warning("watchdog: unparseable docker timestamp %r", value)
        return None


async def _note_restart(db, workspace: Workspace, silent_for: timedelta, outcome: str) -> None:
    """Leave a system message in the workspace explaining the intervention.

    Posted with user_id=None so the agent's unseen poll skips it — the agent
    that just came back does not need to wake up to a message about its own
    death, and the human does need to find out without reading logs.
    """
    minutes = int(silent_for.total_seconds() // 60)
    message = Message(
        workspace_id=workspace.id,
        user_id=None,
        agent_name=None,
        content=(
            f"Watchdog: agent container was running but silent for {minutes}m. {outcome}"
        ),
        message_type="system",
        message_metadata={"watchdog": True, "silent_minutes": minutes},
    )
    db.add(message)
    await db.flush()

    await ws_manager.broadcast_to_channel(str(workspace.id), {
        "type": "new_message",
        "message": {
            "id": str(message.id),
            "workspace_id": str(workspace.id),
            "user_id": None,
            "agent_name": None,
            "sender_name": "Watchdog",
            "content": message.content,
            "message_metadata": message.message_metadata,
            "created_at": (message.created_at or datetime.utcnow()).isoformat(),
            "message_type": "system",
        },
    })


def _revive(workspace: Workspace, owner: User | None) -> tuple[bool, str]:
    """Recreate the workspace's agent container. Returns (restarted, outcome)."""
    from app.services.agents import StartBlocked, plan_agent_start, restart_agent

    plan = plan_agent_start(workspace, owner)
    if isinstance(plan, StartBlocked):
        return False, f"Not restarted: {plan.detail}."

    # restart_agent, not start_agent: the container is running, and a running
    # container is precisely what start_agent declines to touch.
    result = restart_agent(**plan.kwargs)
    if result.get("status") in ("started", "already_running"):
        return True, "Restarted."
    return False, f"Restart failed: {str(result.get('message', 'unknown'))[:160]}"


async def sweep() -> int:
    """One pass over agent workspaces. Returns the number restarted."""
    from app.services.agents import get_agent_status

    settings = get_settings()
    stale_after = timedelta(minutes=settings.watchdog_stale_minutes)
    now = datetime.utcnow()
    restarted = 0

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Workspace).where(
                Workspace.workspace_type == "agent",
                Workspace.archived.is_(False),
            )
        )
        workspaces = list(result.scalars().all())

        for workspace in workspaces:
            try:
                status = get_agent_status(workspace.id)
            except Exception as e:
                # Docker being unreachable is the backend's problem, not this
                # workspace's — don't let it abort the sweep for the others.
                logger.warning("watchdog: status check failed for %s: %s", workspace.id, e)
                continue

            if not status.get("running"):
                continue

            started_at = _parse_docker_time(status.get("started_at"))
            activity = await db.get(WorkspaceAgentActivity, workspace.id)
            last_activity = activity.last_activity_at if activity else None

            # Silence is measured from the later of "last heartbeat" and
            # "container started". The second term is what gives a booting
            # agent its grace period, and what covers an agent that has never
            # checked in at all.
            marks = [t for t in (last_activity, started_at) if t is not None]
            if not marks:
                continue
            last_seen = max(marks)
            silent_for = now - last_seen
            if silent_for < stale_after:
                continue

            # One restart per death. Re-arms as soon as the agent proves it
            # can still talk, so a human fixing it by hand resets this too.
            if activity and activity.last_restart_at:
                revived_since = last_activity is not None and last_activity > activity.last_restart_at
                if not revived_since:
                    logger.warning(
                        "watchdog: %s (%s) still silent %dm after a restart — leaving it for a human",
                        workspace.name, workspace.id, silent_for.total_seconds() // 60,
                    )
                    continue

            owner = await db.get(User, workspace.owner_id)
            did_restart, outcome = await asyncio.to_thread(_revive, workspace, owner)

            logger.warning(
                "watchdog: %s (%s) silent for %dm. %s",
                workspace.name, workspace.id, silent_for.total_seconds() // 60, outcome,
            )
            await _note_restart(db, workspace, silent_for, outcome)

            if did_restart:
                restarted += 1
                if activity is None:
                    activity = WorkspaceAgentActivity(
                        workspace_id=workspace.id,
                        last_activity_at=now,
                    )
                    db.add(activity)
                activity.last_restart_at = now
                activity.restart_count = (activity.restart_count or 0) + 1

        await db.commit()

    return restarted


async def run_watchdog(stop_event: asyncio.Event) -> None:
    """The watchdog loop. Runs until stop_event is set."""
    logger.info("watchdog: started")
    while not stop_event.is_set():
        try:
            count = await sweep()
            if count:
                logger.warning("watchdog: restarted %d unresponsive agent(s)", count)
        except Exception as e:
            logger.error("watchdog: sweep failed: %s", e)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=TICK_SECONDS)
        except asyncio.TimeoutError:
            pass
    logger.info("watchdog: stopped")
