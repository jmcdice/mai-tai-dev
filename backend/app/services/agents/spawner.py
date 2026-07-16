"""Agent container spawner.

Manages agent containers via Docker, one per workspace. Runtime-agnostic: the
image and model defaults come from the RuntimeSpec; auth env vars come from
the caller (which knows which credential the runtime needs).
"""

import logging
import os
from pathlib import Path
from uuid import UUID

import docker
from docker.errors import DockerException, NotFound, APIError

from app.services.agents.runtimes import RuntimeSpec, get_runtime

logger = logging.getLogger(__name__)

# Docker network for agent containers. Defaults to the isolated agents network
# (backend is attached to it too, so agents can reach the API but not postgres).
AGENT_NETWORK = os.environ.get("AGENT_NETWORK", "mai-tai-dev_agents")

# Host mai-tai config (mounted read-only into backend container)
HOST_CONFIG_PATH = Path(os.environ.get("HOST_MAI_TAI_CONFIG", "/host-mai-tai-config/config"))

# Container name prefix
CONTAINER_PREFIX = "maitai-agent-"


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


def _get_docker_client() -> docker.DockerClient:
    """Get a Docker client connected to the host daemon."""
    return docker.from_env()


def _container_name(workspace_id: UUID) -> str:
    """Get the container name for a workspace agent."""
    return f"{CONTAINER_PREFIX}{str(workspace_id)[:8]}"


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
        "AGENT_MODEL": model or spec.default_model,
        **auth_env,
    }

    # Set GitHub token and repo URL for coder templates
    if github_token:
        environment["GITHUB_TOKEN"] = github_token
    if repo_url:
        environment["REPO_URL"] = repo_url

    # Persistent memory volume — survives container restarts
    memory_volume = f"maitai-agent-memory-{str(workspace_id)}"

    try:
        container = client.containers.run(
            spec.image,
            name=name,
            environment=environment,
            network=AGENT_NETWORK,
            detach=True,
            restart_policy={"Name": "unless-stopped"},
            mem_limit="512m",
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
        logger.info(f"Started {spec.id} agent container {name} for workspace {workspace_id}")
        return {
            "status": "started",
            "container": name,
            "container_id": container.short_id,
            "runtime": spec.id,
            "model": environment["AGENT_MODEL"],
        }
    except APIError as e:
        logger.error(f"Failed to start agent container: {e}")
        return {"status": "error", "message": str(e)}


def stop_agent(workspace_id: UUID) -> dict:
    """Stop a running agent container."""
    client = _get_docker_client()
    name = _container_name(workspace_id)

    try:
        container = client.containers.get(name)
        # 30s grace: the driver runs a short memory-flush turn on SIGTERM so
        # the agent can save in-flight context before the container dies.
        container.stop(timeout=30)
        container.remove()
        logger.info(f"Stopped and removed agent container {name}")
        return {"status": "stopped"}
    except NotFound:
        return {"status": "not_running"}
    except APIError as e:
        return {"status": "error", "message": str(e)}


def restart_agent(workspace_id: UUID, **kwargs) -> dict:
    """Restart an agent container."""
    stop_agent(workspace_id)
    return start_agent(workspace_id, **kwargs)


def get_agent_status(workspace_id: UUID) -> dict:
    """Get the status of an agent container."""
    client = _get_docker_client()
    name = _container_name(workspace_id)

    try:
        container = client.containers.get(name)
        return {
            "workspace_id": str(workspace_id),
            "container": name,
            "container_id": container.short_id,
            "status": container.status,
            "running": container.status == "running",
            "created": container.attrs.get("Created", ""),
            "labels": container.labels,
        }
    except NotFound:
        return {
            "workspace_id": str(workspace_id),
            "container": name,
            "status": "not_found",
            "running": False,
        }


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
