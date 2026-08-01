"""Agent workspace spawner service.

Manages Claude Code agent containers via Docker. Each agent workspace
gets its own container running Claude Code connected to Mai-Tai via MCP.
"""

import logging
import os
from pathlib import Path
from uuid import UUID

import docker
from docker.errors import NotFound, APIError

logger = logging.getLogger(__name__)

# Docker image for agent containers
AGENT_IMAGE = os.environ.get("AGENT_IMAGE", "mai-tai-agent:latest")

# Docker network (same network as the backend)
AGENT_NETWORK = os.environ.get("AGENT_NETWORK", "mai-tai-dev_default")

# Model agents run. Must be a model the backing deployment actually serves —
# on Vertex the alias "sonnet" resolves to a version that may not be enabled.
AGENT_MODEL = os.environ.get("AGENT_MODEL", "").strip()

# Host mai-tai config (mounted read-only into backend container)
HOST_CONFIG_PATH = Path(os.environ.get("HOST_MAI_TAI_CONFIG", "/host-mai-tai-config/config"))

# Host gcloud config, mounted read-only into the backend so we can read ADC.
GCLOUD_MOUNT_PATH = Path(os.environ.get("HOST_GCLOUD_MOUNT", "/host-gcloud"))
HOST_ADC_PATH = GCLOUD_MOUNT_PATH / "application_default_credentials.json"


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
    except OSError:
        pass
    return None


def get_host_vertex_config() -> dict | None:
    """Detect host Vertex AI auth for Claude Code.

    Returns a dict of env vars for the agent container, or None if Vertex
    isn't usable. Requires both the env config (project id) and Application
    Default Credentials to actually be present on the host.
    """
    if os.environ.get("CLAUDE_CODE_USE_VERTEX", "").strip() not in ("1", "true", "True"):
        return None

    project_id = os.environ.get("ANTHROPIC_VERTEX_PROJECT_ID", "").strip()
    if not project_id:
        return None

    # Read the ADC and hand it to the agent as JSON rather than bind-mounting
    # it. The host file is typically mode 0600 owned by the host user, so a
    # read-only mount is unreadable to the container's unprivileged `agent`
    # user; the entrypoint writes this out with the right ownership instead.
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

# Container name prefix
CONTAINER_PREFIX = "maitai-agent-"

# Agent templates (used by frontend for template picker)
AGENT_TEMPLATES = {
    "research": {
        "label": "Research Assistant",
        "description": "General-purpose research agent that can search the web and compile reports.",
    },
    "monitor": {
        "label": "Daily Monitor",
        "description": "Scheduled monitoring agent that runs periodic checks and reports.",
    },
    "assistant": {
        "label": "Personal Assistant",
        "description": "General-purpose assistant for daily tasks and questions.",
    },
    "coder": {
        "label": "Coding Agent",
        "description": "Software engineering agent that clones a repo and helps with code, PRs, and bug fixes.",
    },
    "custom": {
        "label": "Custom Agent",
        "description": "A custom agent with user-defined purpose and behavior.",
    },
}


def _get_docker_client() -> docker.DockerClient:
    """Get a Docker client connected to the host daemon."""
    return docker.from_env()


def _container_name(workspace_id: UUID) -> str:
    """Get the container name for a workspace agent."""
    return f"{CONTAINER_PREFIX}{str(workspace_id)[:8]}"


def start_agent(
    workspace_id: UUID,
    workspace_name: str,
    api_key: str | None = None,
    anthropic_api_key: str | None = None,
    claude_oauth_token: str | None = None,
    api_url: str | None = None,
    purpose: str | None = None,
    template: str = "custom",
    github_token: str | None = None,
    repo_url: str | None = None,
    vertex_config: dict | None = None,
) -> dict:
    """Start a Claude Code agent in a Docker container.

    Args:
        workspace_id: The workspace UUID this agent connects to.
        workspace_name: Human-readable name for the agent.
        api_key: Mai-Tai API key (mt_...) for MCP authentication.
        anthropic_api_key: Standard Anthropic API key (sk-ant-api03-*).
        claude_oauth_token: OAuth token for Pro/Max subscription (sk-ant-oat01-*).
        vertex_config: Vertex AI env vars from get_host_vertex_config(). Used
            when no explicit Anthropic credential is supplied.
        api_url: Mai-Tai backend URL. Defaults to http://backend:8000 (Docker internal).
        purpose: What this agent should do.
        template: Agent template type (research, monitor, assistant, custom).

    Returns:
        Dict with status and container info.
    """
    if not anthropic_api_key and not claude_oauth_token and not vertex_config:
        return {
            "status": "error",
            "message": (
                "No Claude credential available. Provide an Anthropic API key or OAuth "
                "token in Settings > AI, or configure Vertex AI on the host."
            ),
        }

    client = _get_docker_client()
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
    }

    if AGENT_MODEL:
        environment["AGENT_MODEL"] = AGENT_MODEL

    # Set GitHub token and repo URL for coder template
    if github_token:
        environment["GITHUB_TOKEN"] = github_token
    if repo_url:
        environment["REPO_URL"] = repo_url

    # Persistent memory volume — survives container restarts
    memory_volume = f"maitai-agent-memory-{str(workspace_id)}"
    volumes = {
        memory_volume: {"bind": "/home/agent/memory", "mode": "rw"},
    }

    # Set auth: explicit credentials win, otherwise fall back to host Vertex.
    if claude_oauth_token:
        environment["CLAUDE_CODE_OAUTH_TOKEN"] = claude_oauth_token
    elif anthropic_api_key:
        environment["ANTHROPIC_API_KEY"] = anthropic_api_key
    elif vertex_config:
        environment.update(vertex_config)

    try:
        container = client.containers.run(
            AGENT_IMAGE,
            name=name,
            environment=environment,
            network=AGENT_NETWORK,
            detach=True,
            restart_policy={"Name": "unless-stopped"},
            mem_limit="512m",
            volumes=volumes,
            labels={
                "mai-tai.agent": "true",
                "mai-tai.workspace-id": str(workspace_id),
                "mai-tai.workspace-name": workspace_name,
                "mai-tai.template": template,
            },
        )
        logger.info(f"Started agent container {name} for workspace {workspace_id}")
        return {
            "status": "started",
            "container": name,
            "container_id": container.short_id,
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
        container.stop(timeout=10)
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
            }
            for c in containers
        ]
    except APIError:
        return []
