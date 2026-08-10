"""Turning a workspace into a startable agent container.

Three callers need the same answer to "what would it take to start this
workspace's agent": the REST endpoint, the scheduler's wake-on-fire path, and
the watchdog. They had drifted before — the scheduler once resolved
credentials its own way and, on a Vertex deployment where no per-user key is
stored, silently never woke anything. The failure mode of duplicating this is
not a crash, it is an agent that quietly stops showing up.

So the resolution lives here once and returns *data*: either a ready-to-splat
kwargs dict, or a reason with a machine-readable code the caller can render
however suits it (HTTP 400 detail, a scheduler status string, a log line).
"""

import logging
from dataclasses import dataclass

from app.core.crypto import get_user_secret
from app.models.user import User
from app.models.workspace import Workspace
from app.services.agents.runtimes import RuntimeSpec, get_runtime
from app.services.agents.spawner import resolve_auth_env

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StartPlan:
    """Everything start_agent() needs for this workspace."""

    runtime: RuntimeSpec
    kwargs: dict


@dataclass(frozen=True)
class StartBlocked:
    """Why this workspace cannot start an agent right now.

    `code` is for callers that branch; `detail` is a short human phrase that
    reads correctly mid-sentence ("not woken: no credential configured").
    `runtime_id` is set once the runtime is known, so a caller can tailor the
    advice it gives (only Claude Code has a host-Vertex fallback to suggest).
    """

    code: str
    detail: str
    runtime_id: str | None = None


def plan_agent_start(workspace: Workspace, owner: User | None) -> StartPlan | StartBlocked:
    """Resolve a workspace's runtime, credential, and container arguments.

    Does not touch Docker — call start_agent(**plan.kwargs) for that. Keeping
    the decision separate from the side effect is what lets the watchdog log
    "would have restarted, but no credential" instead of thrashing.
    """
    from pydantic import ValidationError

    from app.schemas.workspace import AgentConfig

    if workspace.workspace_type != "agent":
        return StartBlocked("not_agent", "workspace is not an agent workspace")

    # Stored configs can predate the registry or name a retired runtime.
    try:
        config = AgentConfig.model_validate(workspace.agent_config or {})
    except ValidationError as e:
        msg = e.errors()[0].get("msg", "invalid") if e.errors() else "invalid"
        return StartBlocked(
            "bad_config",
            f"stored agent config is not available on this server: {msg}",
        )

    runtime = get_runtime(config.runtime)
    if runtime is None or not runtime.enabled:
        return StartBlocked(
            "runtime_unavailable",
            f"agent runtime '{config.runtime}' is not available on this server",
        )

    settings = (owner.settings if owner else None) or {}
    auth_env = resolve_auth_env(runtime, settings)
    if not auth_env:
        return StartBlocked(
            "no_credential",
            f"{runtime.credential_label} is not configured",
            runtime_id=runtime.id,
        )

    is_coder = config.template == "coder"
    return StartPlan(
        runtime=runtime,
        kwargs={
            "workspace_id": workspace.id,
            "workspace_name": workspace.name,
            "runtime": runtime.id,
            "model": config.model,
            "auth_env": auth_env,
            "purpose": workspace.agent_purpose,
            "template": config.template,
            "github_token": get_user_secret(settings, "github_token") if is_coder else None,
            "repo_url": config.repo_url if is_coder else None,
        },
    )
