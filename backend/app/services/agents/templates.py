"""Agent workspace templates (runtime-agnostic).

Templates shape the agent's role instructions and container bootstrap; the
frontend template picker is driven by this dict via /workspaces/agent-templates.
"""

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
