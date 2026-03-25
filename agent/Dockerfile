# Mai-Tai Agent Container
# Runs a Claude Code instance connected to a Mai-Tai workspace via MCP.
#
# Required env vars at runtime:
#   ANTHROPIC_API_KEY    - Anthropic API key for Claude
#   MAI_TAI_API_URL      - Mai-Tai backend URL (e.g. http://backend:8000)
#   MAI_TAI_API_KEY      - Mai-Tai API key (mt_...)
#   MAI_TAI_WORKSPACE_ID - Workspace UUID
#
# Optional env vars:
#   AGENT_NAME           - Agent display name (default: "Agent")
#   AGENT_PURPOSE        - What this agent should do
#   AGENT_TEMPLATE       - Template type: research, monitor, assistant, custom

FROM node:20-slim

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    python3 \
    python3-pip \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install GitHub CLI
RUN GH_VERSION=2.45.0 \
    && curl -sL "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_amd64.tar.gz" \
       | tar -xz -C /tmp \
    && mv /tmp/gh_${GH_VERSION}_linux_amd64/bin/gh /usr/local/bin/gh \
    && rm -rf /tmp/gh_${GH_VERSION}_linux_amd64

# Install Claude Code CLI globally (as root)
RUN npm install -g @anthropic-ai/claude-code

# Create non-root user (claude --dangerously-skip-permissions refuses to run as root)
RUN useradd -m -s /bin/bash agent \
    && mkdir -p /home/agent/workspace \
    && mkdir -p /home/agent/memory/tasks \
    && chown -R agent:agent /home/agent
USER agent

# Install uv for the agent user
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/home/agent/.local/bin:$PATH"

# Create agent workspace
WORKDIR /home/agent/workspace

# Copy entrypoint
COPY --chown=agent:agent entrypoint.sh /home/agent/entrypoint.sh
RUN chmod +x /home/agent/entrypoint.sh

ENTRYPOINT ["/home/agent/entrypoint.sh"]
