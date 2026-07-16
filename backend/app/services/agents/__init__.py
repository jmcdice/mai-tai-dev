"""Agent runtime management.

A "runtime" is a pluggable agent CLI (Claude Code, OpenAI Codex, ...) packaged
as a Docker image. The spawner is runtime-agnostic: it resolves a RuntimeSpec
from the registry and launches a container wired to a workspace via the
Mai-Tai MCP server / REST API.
"""

from app.services.agents.runtimes import RUNTIMES, RuntimeSpec, get_runtime
from app.services.agents.spawner import (
    get_agent_logs,
    get_agent_status,
    list_agents,
    restart_agent,
    start_agent,
    stop_agent,
)
from app.services.agents.templates import AGENT_TEMPLATES

__all__ = [
    "AGENT_TEMPLATES",
    "RUNTIMES",
    "RuntimeSpec",
    "get_runtime",
    "get_agent_logs",
    "get_agent_status",
    "list_agents",
    "restart_agent",
    "start_agent",
    "stop_agent",
]
