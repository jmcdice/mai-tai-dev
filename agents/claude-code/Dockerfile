# Mai-Tai Agent Container — claude-code runtime
# Runs Claude Code turns under the mai-tai driver loop, connected to a
# workspace via the Mai-Tai MCP server + REST API.
#
# BUILD FROM THE REPO ROOT — the context must include mcp-server/:
#   docker build -t mai-tai-agent:latest -f agents/claude-code/Dockerfile .
#
# Claude auth (need exactly one):
#   ANTHROPIC_API_KEY       - Anthropic API key (sk-ant-api...)
#   CLAUDE_CODE_OAUTH_TOKEN - Pro/Max subscription token (sk-ant-oat...)
#   CLAUDE_CODE_USE_VERTEX=1 + ANTHROPIC_VERTEX_PROJECT_ID + GOOGLE_ADC_JSON
#
# Required env vars at runtime:
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

# Install uv for the agent user
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/home/agent/.local/bin:$PATH"

# Install the Mai-Tai MCP server from vendored source rather than PyPI. Pulling
# it at runtime with `uvx --refresh` re-resolves dependencies on every start,
# so a bad upstream release breaks every agent at once — and it silently skews
# from the source in this repo. Baking it in pins both.
COPY --chown=agent:agent mcp-server /home/agent/mcp-server
RUN uv tool install /home/agent/mcp-server \
    && test -x /home/agent/.local/bin/mai-tai-mcp

WORKDIR /home/agent/workspace

# Shared driver + bootstrap, runtime entrypoint
COPY --chown=agent:agent agents/common/driver.py /home/agent/driver.py
COPY --chown=agent:agent agents/common/bootstrap.sh /home/agent/bootstrap.sh
COPY --chown=agent:agent agents/claude-code/entrypoint.sh /home/agent/entrypoint.sh
RUN chmod +x /home/agent/entrypoint.sh /home/agent/bootstrap.sh

ENTRYPOINT ["/home/agent/entrypoint.sh"]
