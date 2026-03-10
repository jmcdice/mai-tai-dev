#!/bin/bash
# Mai-Tai Agent Entrypoint
#
# Configures Claude Code with MCP and mai-tai settings,
# then launches Claude in mai-tai mode.

set -euo pipefail

WORKDIR="/home/agent/workspace"

# Required env vars
: "${MAI_TAI_API_URL:?MAI_TAI_API_URL is required}"
: "${MAI_TAI_API_KEY:?MAI_TAI_API_KEY is required}"
: "${MAI_TAI_WORKSPACE_ID:?MAI_TAI_WORKSPACE_ID is required}"

# Auth: support both OAuth token (Pro/Max subscription) and standard API key
if [ -z "${ANTHROPIC_API_KEY:-}" ] && [ -z "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then
  echo "[mai-tai-agent] ERROR: Set either ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN"
  exit 1
fi

# Optional env vars
AGENT_NAME="${AGENT_NAME:-Agent}"
AGENT_PURPOSE="${AGENT_PURPOSE:-General-purpose agent.}"
AGENT_TEMPLATE="${AGENT_TEMPLATE:-custom}"

echo "[mai-tai-agent] Configuring agent: ${AGENT_NAME}"
echo "[mai-tai-agent] Workspace: ${MAI_TAI_WORKSPACE_ID}"
echo "[mai-tai-agent] API URL: ${MAI_TAI_API_URL}"

# 1. Write global mai-tai config (API URL + key)
mkdir -p ~/.config/mai-tai
cat > ~/.config/mai-tai/config << EOF
MAI_TAI_API_URL=${MAI_TAI_API_URL}
MAI_TAI_API_KEY=${MAI_TAI_API_KEY}
EOF

# 2. Write project-level .env.mai-tai (workspace ID)
echo "MAI_TAI_WORKSPACE_ID=${MAI_TAI_WORKSPACE_ID}" > "${WORKDIR}/.env.mai-tai"

# 3. Write CLAUDE.md based on template
case "${AGENT_TEMPLATE}" in
  research)
    cat > "${WORKDIR}/CLAUDE.md" << CLAUDE_EOF
# ${AGENT_NAME} - Research Agent

## Purpose
${AGENT_PURPOSE}

## Behavior
- You are a research assistant. Your job is to help the user with research tasks.
- Search the web, compile findings, and present clear summaries.
- When given a topic, proactively find relevant information from multiple sources.
- Be thorough but concise in your reports.

## Mai-Tai Mode
When this session starts, IMMEDIATELY enter mai-tai mode by calling \`chat_with_human\`
to greet the user and ask what they'd like you to research.
After completing any task, ALWAYS call \`chat_with_human\` to report results.
CLAUDE_EOF
    ;;
  monitor)
    cat > "${WORKDIR}/CLAUDE.md" << CLAUDE_EOF
# ${AGENT_NAME} - Monitor Agent

## Purpose
${AGENT_PURPOSE}

## Behavior
- You are a monitoring agent that runs periodic checks and reports findings.
- Present findings in clear, actionable summaries.
- Alert the user to significant changes or findings.

## Mai-Tai Mode
When this session starts, IMMEDIATELY enter mai-tai mode by calling \`chat_with_human\`
to greet the user and ask what they'd like you to monitor.
After completing any task, ALWAYS call \`chat_with_human\` to report results.
CLAUDE_EOF
    ;;
  assistant)
    cat > "${WORKDIR}/CLAUDE.md" << CLAUDE_EOF
# ${AGENT_NAME} - Personal Assistant

## Purpose
${AGENT_PURPOSE}

## Behavior
- You are a personal assistant. Help with questions, tasks, and daily needs.
- Be proactive about offering help and following up on previous conversations.
- Be conversational and helpful.

## Mai-Tai Mode
When this session starts, IMMEDIATELY enter mai-tai mode by calling \`chat_with_human\`
to greet the user. After completing any task, ALWAYS call \`chat_with_human\` to report results.
CLAUDE_EOF
    ;;
  *)
    cat > "${WORKDIR}/CLAUDE.md" << CLAUDE_EOF
# ${AGENT_NAME}

## Purpose
${AGENT_PURPOSE}

## Mai-Tai Mode
When this session starts, IMMEDIATELY enter mai-tai mode by calling \`chat_with_human\`
to greet the user. After completing any task, ALWAYS call \`chat_with_human\` to report results.
CLAUDE_EOF
    ;;
esac

# 4. Write Claude Code settings with permissions + MCP server
mkdir -p "${WORKDIR}/.claude"
cat > "${WORKDIR}/.claude/settings.local.json" << 'SETTINGS_EOF'
{
  "permissions": {
    "allow": [
      "Bash(curl:*)",
      "Bash(ls:*)",
      "Bash(cat:*)",
      "Bash(mkdir:*)",
      "Bash(echo:*)",
      "Bash(python3:*)",
      "WebSearch",
      "WebFetch",
      "mcp__mai-tai__chat_with_human",
      "mcp__mai-tai__update_status",
      "mcp__mai-tai__get_messages",
      "mcp__mai-tai__get_project_info"
    ],
    "deny": []
  },
  "mcpServers": {
    "mai-tai": {
      "command": "uvx",
      "args": ["--refresh", "mai-tai-mcp"]
    }
  }
}
SETTINGS_EOF

# 5. Configure git (Claude Code requires a repo)
git config --global user.email "agent@mai-tai.dev"
git config --global user.name "${AGENT_NAME}"

if [ ! -d "${WORKDIR}/.git" ]; then
  git init "${WORKDIR}"
  git -C "${WORKDIR}" add -A
  git -C "${WORKDIR}" commit -m "Initial agent workspace" --allow-empty
fi

# 6. Skip onboarding prompt (required for headless mode)
echo '{"hasCompletedOnboarding": true}' > ~/.claude.json

echo "[mai-tai-agent] Configuration complete. Starting Claude..."

# 7. Write MCP config as JSON for --mcp-config flag
cat > /tmp/mcp-config.json << 'MCP_EOF'
{
  "mcpServers": {
    "mai-tai": {
      "command": "uvx",
      "args": ["--refresh", "mai-tai-mcp"]
    }
  }
}
MCP_EOF

# 8. Launch Claude in headless mai-tai mode
# Using -p for non-interactive, --mcp-config to ensure MCP tools are loaded
cd "${WORKDIR}"
exec claude -p "start mai tai mode" \
  --dangerously-skip-permissions \
  --model sonnet \
  --mcp-config /tmp/mcp-config.json
