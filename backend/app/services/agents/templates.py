"""Agent workspace templates (runtime-agnostic).

Templates shape the agent's role instructions and container bootstrap; the
frontend template picker is driven by this dict via /workspaces/agent-templates.

Each template also carries a default container memory limit. One global cap
does not fit both a chat bot and a coding agent: 512m is plenty for research /
monitor / assistant, but a coder agent doing an ordinary `pnpm install` on a
real repo will be OOM-killed by it. A workspace can override its own limit via
agent_config.mem_limit.
"""

import os
import re

# Docker byte-suffix form, e.g. "512m", "2g", "1536M".
MEM_LIMIT_RE = re.compile(r"^\d+[bkmgBKMG]?$")

# Floor for any configured limit. Below this the runtime CLI itself won't
# start, so accepting it would just trade one silent OOM for another.
MIN_MEM_LIMIT_BYTES = 256 * 1024 * 1024

_UNIT_MULTIPLIER = {"": 1, "b": 1, "k": 1024, "m": 1024**2, "g": 1024**3}

DEFAULT_MEM_LIMIT = os.environ.get("AGENT_MEM_LIMIT", "").strip() or "512m"
DEFAULT_CODER_MEM_LIMIT = os.environ.get("AGENT_CODER_MEM_LIMIT", "").strip() or "4g"

AGENT_TEMPLATES = {
    "research": {
        "label": "Research Assistant",
        "description": "General-purpose research agent that can search the web and compile reports.",
        "mem_limit": DEFAULT_MEM_LIMIT,
    },
    "monitor": {
        "label": "Daily Monitor",
        "description": "Scheduled monitoring agent that runs periodic checks and reports.",
        "mem_limit": DEFAULT_MEM_LIMIT,
    },
    "assistant": {
        "label": "Personal Assistant",
        "description": "General-purpose assistant for daily tasks and questions.",
        "mem_limit": DEFAULT_MEM_LIMIT,
    },
    "coder": {
        "label": "Coding Agent",
        "description": "Software engineering agent that clones a repo and helps with code, PRs, and bug fixes.",
        # Installing dependencies for a real project is the baseline workload
        # here, not an edge case. See the OOM analysis in issue #40.
        "mem_limit": DEFAULT_CODER_MEM_LIMIT,
    },
    "custom": {
        "label": "Custom Agent",
        "description": "A custom agent with user-defined purpose and behavior.",
        "mem_limit": DEFAULT_MEM_LIMIT,
    },
}


def parse_mem_limit(value: str) -> int:
    """Bytes for a Docker memory string. Raises ValueError if malformed."""
    value = value.strip()
    if not MEM_LIMIT_RE.match(value):
        raise ValueError(
            f"Invalid memory limit {value!r}. Use a number with an optional "
            "b/k/m/g suffix, e.g. '512m' or '2g'."
        )
    if value[-1].isalpha():
        return int(value[:-1]) * _UNIT_MULTIPLIER[value[-1].lower()]
    return int(value)


def template_mem_limit(template: str) -> str:
    """Default container memory limit for a template."""
    return AGENT_TEMPLATES.get(template, {}).get("mem_limit", DEFAULT_MEM_LIMIT)
