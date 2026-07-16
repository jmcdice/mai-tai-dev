# Mai-Tai Agent Container — claude-code runtime
# Runs Claude Code turns under the mai-tai driver loop, connected to a
# workspace via the Mai-Tai MCP server + REST API.
#
# Build (from the repo root; the build context is agents/):
#   docker build -t mai-tai-agent:latest -f agents/claude-code/Dockerfile agents/
#
# Required env vars at runtime:
#   ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN
#   MAI_TAI_API_URL      - Mai-Tai backend URL (e.g. http://backend:8000)
#   MAI_TAI_API_KEY      - Mai-Tai API key (mt_...)
#   MAI_TAI_WORKSPACE_ID - Workspace UUID
#
# Optional env vars:
#   AGENT_NAME     - Agent display name (default: "Agent")
#   AGENT_PURPOSE  - What this agent should do
#   AGENT_TEMPLATE - research | monitor | assistant | coder | custom
#   AGENT_MODEL    - Claude model alias (default: sonnet)

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
    && mkdir -p /home/agent/memory/tasks /home/agent/memory/journal /home/agent/memory/state \
    && chown -R agent:agent /home/agent
USER agent

# Install uv for the agent user (runs the mai-tai MCP server via uvx)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/home/agent/.local/bin:$PATH"

WORKDIR /home/agent/workspace

# Shared driver + bootstrap, runtime entrypoint
COPY --chown=agent:agent common/driver.py /home/agent/driver.py
COPY --chown=agent:agent common/bootstrap.sh /home/agent/bootstrap.sh
COPY --chown=agent:agent claude-code/entrypoint.sh /home/agent/entrypoint.sh
RUN chmod +x /home/agent/entrypoint.sh /home/agent/bootstrap.sh

ENTRYPOINT ["/home/agent/entrypoint.sh"]
