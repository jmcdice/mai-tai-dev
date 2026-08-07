"""Agent container spawner.

Manages agent containers via Docker, one per workspace. Runtime-agnostic: the
image and model defaults come from the RuntimeSpec; auth env vars come from
the caller (which knows which credential the runtime needs).
"""

import json
import logging
import os
import time
from pathlib import Path
from uuid import UUID

import docker
from docker.errors import DockerException, NotFound, APIError

from app.core.crypto import get_user_secret
from app.services.agents.runtimes import RuntimeSpec, get_runtime
from app.services.agents.templates import template_mem_limit

logger = logging.getLogger(__name__)

# Docker network for agent containers. Defaults to the isolated agents network
# (backend is attached to it too, so agents can reach the API but not postgres).
AGENT_NETWORK = os.environ.get("AGENT_NETWORK", "mai-tai-dev_agents")

# Host mai-tai config (mounted read-only into backend container)
HOST_CONFIG_PATH = Path(os.environ.get("HOST_MAI_TAI_CONFIG", "/host-mai-tai-config/config"))

# Host gcloud config, mounted read-only into the backend so we can read ADC.
GCLOUD_MOUNT_PATH = Path(os.environ.get("HOST_GCLOUD_MOUNT", "/host-gcloud"))
HOST_ADC_PATH = GCLOUD_MOUNT_PATH / "application_default_credentials.json"

# Deployment-wide model override. A runtime's default_model is an alias
# ("sonnet") that resolves to whatever version the backing deployment serves —
# on Vertex that may be a version the project isn't entitled to. This lets an
# operator pin a concrete model without touching every workspace.
AGENT_MODEL_OVERRIDE = os.environ.get("AGENT_MODEL", "").strip()

# Container name prefix
CONTAINER_PREFIX = "maitai-agent-"

# Written by agents/common/bootstrap.sh; records whether provisioning (so far
# just the repo clone) actually succeeded. See _read_bootstrap_status.
BOOTSTRAP_STATUS_PATH = "/home/agent/.bootstrap-status"


def _get_host_mai_tai_key() -> str | None:
    """Read the Mai-Tai API key from the host's ~/.config/mai-tai/config."""
    if not HOST_CONFIG_PATH.exists():
        return None
    try:
        for line in HOST_CONFIG_PATH.read_text().splitlines():
            line = line.strip()
            if line.startswith("#") or not line:
                continue
            if line.startswith("MAI_TAI_API_KEY="):
                return line.split("=", 1)[1].strip()
    except (IOError, OSError):
        pass
    return None


def get_host_vertex_config() -> dict[str, str] | None:
    """Build Vertex auth env from the host's gcloud ADC, if Vertex is enabled.

    Lets a deployment run Claude Code agents off the operator's GCP project
    instead of requiring every user to paste an Anthropic key. Returns None
    (rather than raising) whenever Vertex isn't fully configured, so callers
    can fall back to per-user credentials.
    """
    if os.environ.get("CLAUDE_CODE_USE_VERTEX", "").strip().lower() not in ("1", "true"):
        return None

    project_id = os.environ.get("ANTHROPIC_VERTEX_PROJECT_ID", "").strip()
    if not project_id:
        logger.warning("CLAUDE_CODE_USE_VERTEX is set but ANTHROPIC_VERTEX_PROJECT_ID is empty")
        return None

    try:
        adc_json = HOST_ADC_PATH.read_text().strip()
    except OSError as e:
        logger.warning("Vertex enabled but ADC unreadable at %s: %s", HOST_ADC_PATH, e)
        return None
    if not adc_json:
        return None

    return {
        "CLAUDE_CODE_USE_VERTEX": "1",
        "ANTHROPIC_VERTEX_PROJECT_ID": project_id,
        "CLOUD_ML_REGION": os.environ.get("CLOUD_ML_REGION", "global").strip() or "global",
        "GOOGLE_ADC_JSON": adc_json,
    }


# Claude Pro/Max subscription tokens carry this prefix and go in their own
# environment variable; anything else is a standard API key.
OAUTH_TOKEN_PREFIX = "sk-ant-oat"


def resolve_auth_env(runtime: RuntimeSpec, user_settings: dict | None) -> dict[str, str] | None:
    """Auth env for a runtime, from the user's credential or the host's Vertex config.

    The single source of truth for "how does this agent authenticate" — every
    caller that starts a container must go through here. Claude Code
    distinguishes OAuth tokens (Pro/Max subscription) from standard API keys,
    and falls back to host Vertex when the user has no key of their own, so a
    Vertex deployment needs no per-user setup.

    Returns None when nothing resolves; the caller decides how to report that.
    """
    credential = get_user_secret(user_settings or {}, runtime.credential_setting)

    if runtime.id != "claude-code":
        return {"OPENAI_API_KEY": credential} if credential else None

    if not credential:
        return get_host_vertex_config()
    if credential.startswith(OAUTH_TOKEN_PREFIX):
        return {"CLAUDE_CODE_OAUTH_TOKEN": credential}
    return {"ANTHROPIC_API_KEY": credential}


def _get_docker_client() -> docker.DockerClient:
    """Get a Docker client connected to the host daemon."""
    return docker.from_env()


def _container_name(workspace_id: UUID) -> str:
    """Get the container name for a workspace agent."""
    return f"{CONTAINER_PREFIX}{str(workspace_id)[:8]}"


def _memory_volume_name(workspace_id: UUID) -> str:
    """Name of the persistent agent-memory volume for a workspace."""
    return f"maitai-agent-memory-{workspace_id}"


def start_agent(
    workspace_id: UUID,
    workspace_name: str,
    runtime: str = "claude-code",
    model: str | None = None,
    api_key: str | None = None,
    auth_env: dict[str, str] | None = None,
    api_url: str | None = None,
    purpose: str | None = None,
    template: str = "custom",
    github_token: str | None = None,
    repo_url: str | None = None,
    mem_limit: str | None = None,
) -> dict:
    """Start an agent container for a workspace.

    Args:
        workspace_id: The workspace UUID this agent connects to.
        workspace_name: Human-readable name for the agent.
        runtime: Runtime id from the registry (claude-code, codex, ...).
        model: Model id for the runtime; falls back to the runtime default.
        api_key: Mai-Tai API key (mt_...) for MCP authentication.
        auth_env: Runtime credential env vars (e.g. {"ANTHROPIC_API_KEY": ...}
            or {"CLAUDE_CODE_OAUTH_TOKEN": ...} or {"OPENAI_API_KEY": ...}).
        api_url: Mai-Tai backend URL. Defaults to http://backend:8000.
        purpose: What this agent should do.
        template: Agent template type (research, monitor, assistant, coder, custom).
        github_token: GitHub token for coder agents.
        repo_url: Repository to clone for coder agents.
        mem_limit: Container memory cap in Docker syntax ("2g"); falls back to
            the template default.

    Returns:
        Dict with status and container info.
    """
    spec: RuntimeSpec | None = get_runtime(runtime)
    if spec is None or not spec.enabled:
        return {"status": "error", "message": f"Unknown or disabled runtime: {runtime}"}

    if not auth_env:
        return {"status": "error", "message": f"{spec.credential_label} is required to start a {spec.label} agent"}

    try:
        client = _get_docker_client()
    except DockerException as e:
        logger.error(f"Docker daemon unavailable: {e}")
        return {"status": "error", "message": f"Docker daemon unavailable: {e}"}
    name = _container_name(workspace_id)

    # Check if already running
    try:
        existing = client.containers.get(name)
        if existing.status == "running":
            return {
                "status": "already_running",
                "container": name,
                "container_id": existing.short_id,
            }
        # Container exists but stopped — remove it and recreate
        existing.remove(force=True)
    except NotFound:
        pass

    # Default to Docker-internal backend URL
    if not api_url:
        api_url = os.environ.get("MAI_TAI_AGENT_API_URL", "http://backend:8000")

    # Use provided key, or fall back to host's mai-tai config
    mai_tai_key = api_key or _get_host_mai_tai_key()
    if not mai_tai_key:
        return {"status": "error", "message": "No Mai-Tai API key available. Check ~/.config/mai-tai/config on host."}

    environment = {
        "MAI_TAI_API_URL": api_url,
        "MAI_TAI_API_KEY": mai_tai_key,
        "MAI_TAI_WORKSPACE_ID": str(workspace_id),
        "AGENT_NAME": workspace_name,
        "AGENT_PURPOSE": purpose or "General-purpose agent.",
        "AGENT_TEMPLATE": template,
        "AGENT_RUNTIME": spec.id,
        "AGENT_MODEL": AGENT_MODEL_OVERRIDE or model or spec.default_model,
        **auth_env,
    }

    # Set GitHub token and repo URL for coder templates
    if github_token:
        environment["GITHUB_TOKEN"] = github_token
    if repo_url:
        environment["REPO_URL"] = repo_url

    # Persistent memory volume — survives container restarts
    memory_volume = _memory_volume_name(workspace_id)

    # Per-template default, overridable per workspace. A single global cap
    # starved coder agents: 512m cannot survive an ordinary dependency install.
    effective_mem_limit = mem_limit or template_mem_limit(template)

    try:
        container = client.containers.run(
            spec.image,
            name=name,
            environment=environment,
            network=AGENT_NETWORK,
            detach=True,
            restart_policy={"Name": "unless-stopped"},
            mem_limit=effective_mem_limit,
            # Match swap to the limit: leaving it unset lets Docker grant 2x in
            # swap, which turns an OOM into an unbounded thrash instead.
            memswap_limit=effective_mem_limit,
            volumes={
                memory_volume: {"bind": "/home/agent/memory", "mode": "rw"},
            },
            labels={
                "mai-tai.agent": "true",
                "mai-tai.workspace-id": str(workspace_id),
                "mai-tai.workspace-name": workspace_name,
                "mai-tai.template": template,
                "mai-tai.runtime": spec.id,
            },
        )
        logger.info(
            f"Started {spec.id} agent container {name} for workspace {workspace_id} "
            f"(mem_limit={effective_mem_limit})"
        )
        return {
            "status": "started",
            "container": name,
            "container_id": container.short_id,
            "runtime": spec.id,
            "model": environment["AGENT_MODEL"],
            "mem_limit": effective_mem_limit,
        }
    except APIError as e:
        logger.error(f"Failed to start agent container: {e}")
        return {"status": "error", "message": str(e)}


def stop_agent(workspace_id: UUID, remove_memory: bool = False) -> dict:
    """Stop a running agent container.

    Args:
        workspace_id: The workspace whose agent to stop.
        remove_memory: Also delete the persistent memory volume. Only for
            workspace deletion — a plain stop must preserve agent memory
            across restarts, which is the whole point of the volume.
    """
    client = _get_docker_client()
    name = _container_name(workspace_id)
    result: dict = {"status": "not_running"}

    try:
        container = client.containers.get(name)
        # 30s grace: the driver runs a short memory-flush turn on SIGTERM so
        # the agent can save in-flight context before the container dies.
        container.stop(timeout=30)
        container.remove()
        logger.info(f"Stopped and removed agent container {name}")
        result = {"status": "stopped"}
    except NotFound:
        pass
    except APIError as e:
        result = {"status": "error", "message": str(e)}

    if remove_memory:
        result["memory_volume_removed"] = _remove_memory_volume(client, workspace_id)

    return result


def _remove_memory_volume(client: docker.DockerClient, workspace_id: UUID) -> bool:
    """Delete a workspace's agent-memory volume. Returns True if it went away.

    Without this every workspace that ever ran an agent leaves a volume on the
    host forever — nothing else in the lifecycle removes it.
    """
    volume_name = _memory_volume_name(workspace_id)
    try:
        client.volumes.get(volume_name).remove(force=True)
        logger.info(f"Removed agent memory volume {volume_name}")
        return True
    except NotFound:
        return False
    except APIError as e:
        logger.warning(f"Could not remove agent memory volume {volume_name}: {e}")
        return False


def restart_agent(workspace_id: UUID, **kwargs) -> dict:
    """Restart an agent container."""
    stop_agent(workspace_id)
    return start_agent(workspace_id, **kwargs)


# Bootstrap runs once per container, so its result is immutable for that
# container's lifetime. Cached by container id to keep an exec off the status
# path, which the UI polls every few seconds.
_bootstrap_cache: dict[str, dict | None] = {}


def _read_bootstrap_status(container) -> dict | None:
    """Read the bootstrap marker written inside a running agent container.

    The container coming up is not the same as the agent being provisioned:
    a failed repo clone still yields a `running` container. Bootstrap records
    what actually happened; this is how the API gets to see it.
    """
    if container.status != "running":
        return None
    if container.id in _bootstrap_cache:
        return _bootstrap_cache[container.id]
    status = _exec_bootstrap_status(container)
    # Only cache a definitive read: a miss may just mean bootstrap hadn't
    # finished writing the marker yet.
    if status is not None:
        _bootstrap_cache[container.id] = status
    return status


def _exec_bootstrap_status(container) -> dict | None:
    try:
        code, output = container.exec_run(["cat", BOOTSTRAP_STATUS_PATH])
    except (APIError, DockerException) as e:
        logger.debug(f"Could not read bootstrap status from {container.name}: {e}")
        return None
    if code != 0:
        # Container predates the marker, or bootstrap died before writing it.
        return None
    try:
        return json.loads(output.decode("utf-8", errors="replace"))
    except ValueError:
        return None


def get_agent_status(workspace_id: UUID) -> dict:
    """Get the status of an agent container.

    `running` alone is not health. A container whose repo clone failed, or one
    that is being repeatedly OOM-killed, is reported as `degraded` with the
    reason attached so the UI can stop showing a green dot over a broken agent.
    """
    client = _get_docker_client()
    name = _container_name(workspace_id)

    try:
        container = client.containers.get(name)
    except NotFound:
        return {
            "workspace_id": str(workspace_id),
            "container": name,
            "status": "not_found",
            "running": False,
            "degraded": False,
        }

    state = container.attrs.get("State", {})
    bootstrap = _read_bootstrap_status(container)

    problems: list[str] = []
    if bootstrap and bootstrap.get("clone") == "failed":
        problems.append(
            f"Repository clone failed ({bootstrap.get('repo_url', 'unknown repo')}): "
            f"{bootstrap.get('error', 'no detail')}"
        )
    if state.get("OOMKilled"):
        problems.append(
            "Container was killed for exceeding its memory limit. Raise "
            "mem_limit in the workspace's agent config."
        )

    return {
        "workspace_id": str(workspace_id),
        "container": name,
        "container_id": container.short_id,
        "status": container.status,
        "running": container.status == "running",
        "created": container.attrs.get("Created", ""),
        "labels": container.labels,
        "mem_limit": container.attrs.get("HostConfig", {}).get("Memory") or None,
        "oom_killed": bool(state.get("OOMKilled")),
        "restart_count": container.attrs.get("RestartCount", 0),
        "bootstrap": bootstrap,
        "degraded": bool(problems),
        "problems": problems,
    }


# (expires_at, problems) per workspace. The agent-status endpoint is polled
# every ~10s per open workspace; without this, every poll would inspect Docker.
_health_cache: dict[UUID, tuple[float, list[str]]] = {}
HEALTH_CACHE_TTL = 15.0


def get_agent_problems(workspace_id: UUID) -> list[str]:
    """Reasons this workspace's agent is degraded; empty if it looks healthy.

    Cheap enough for the polled status endpoint (TTL-cached), and never
    raises — a Docker hiccup must not turn a status poll into a 500.
    """
    cached = _health_cache.get(workspace_id)
    now = time.monotonic()
    if cached and cached[0] > now:
        return cached[1]

    try:
        problems = get_agent_status(workspace_id).get("problems", [])
    except (DockerException, APIError) as e:
        logger.debug(f"Agent health check failed for {workspace_id}: {e}")
        problems = []

    _health_cache[workspace_id] = (now + HEALTH_CACHE_TTL, problems)
    return problems


def reap_orphaned_agents(live_workspace_ids: set[str]) -> list[str]:
    """Remove agent containers whose workspace no longer exists.

    Deleting a workspace used to leave its container running under
    `restart: unless-stopped`, polling an API that 404s at ~1,260 req/hour
    forever with nothing in the UI to reveal it. Ordering the delete correctly
    fixes new deletions; this catches the ones already stranded and any where
    the backend died mid-delete.

    Args:
        live_workspace_ids: Workspace UUIDs (as strings) that still exist.

    Returns:
        Names of the containers that were removed.
    """
    try:
        client = _get_docker_client()
        containers = client.containers.list(all=True, filters={"label": "mai-tai.agent=true"})
    except (DockerException, APIError) as e:
        logger.warning(f"Orphan reap skipped, Docker unavailable: {e}")
        return []

    reaped: list[str] = []
    for container in containers:
        workspace_id = container.labels.get("mai-tai.workspace-id", "")
        if not workspace_id or workspace_id in live_workspace_ids:
            continue
        try:
            container.remove(force=True)
            reaped.append(container.name)
            logger.info(
                f"Reaped orphaned agent container {container.name} "
                f"(workspace {workspace_id} no longer exists)"
            )
            try:
                _remove_memory_volume(client, UUID(workspace_id))
            except ValueError:
                pass
        except (NotFound, APIError) as e:
            logger.warning(f"Could not reap orphaned container {container.name}: {e}")

    return reaped


def get_agent_logs(workspace_id: UUID, tail: int = 100) -> str:
    """Get recent logs from an agent container."""
    client = _get_docker_client()
    name = _container_name(workspace_id)

    try:
        container = client.containers.get(name)
        return container.logs(tail=tail, timestamps=True).decode("utf-8", errors="replace")
    except NotFound:
        return ""


def list_agents() -> list[dict]:
    """List all mai-tai agent containers."""
    client = _get_docker_client()

    try:
        containers = client.containers.list(
            all=True,
            filters={"label": "mai-tai.agent=true"},
        )
        return [
            {
                "container": c.name,
                "container_id": c.short_id,
                "status": c.status,
                "running": c.status == "running",
                "workspace_id": c.labels.get("mai-tai.workspace-id", ""),
                "workspace_name": c.labels.get("mai-tai.workspace-name", ""),
                "template": c.labels.get("mai-tai.template", ""),
                "runtime": c.labels.get("mai-tai.runtime", "claude-code"),
            }
            for c in containers
        ]
    except APIError:
        return []
