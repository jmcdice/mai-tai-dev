#!/bin/bash
# Mai-Tai claude-code runtime entrypoint: bootstrap, then hand off to the
# per-turn driver loop.

set -euo pipefail

# Auth: support both OAuth token (Pro/Max subscription) and standard API key
if [ -z "${ANTHROPIC_API_KEY:-}" ] && [ -z "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then
  echo "[mai-tai-agent] ERROR: Set either ANTHROPIC_API_KEY or CLAUDE_CODE_OAUTH_TOKEN"
  exit 1
fi

export INSTRUCTIONS_FILE="CLAUDE.md"
source /home/agent/bootstrap.sh

# Claude Code settings: tool permissions per template
WORKDIR="${AGENT_WORKDIR:-/home/agent/workspace}"
mkdir -p "${WORKDIR}/.claude"

MAI_TAI_TOOLS='"mcp__mai-tai__chat_with_human",
      "mcp__mai-tai__update_status",
      "mcp__mai-tai__get_messages",
      "mcp__mai-tai__get_project_info",
      "mcp__mai-tai__search_history",
      "mcp__mai-tai__memory",
      "mcp__mai-tai__journal"'

if [ "${AGENT_TEMPLATE:-custom}" = "coder" ]; then
  # Coder agents get full permissions for development work
  cat > "${WORKDIR}/.claude/settings.local.json" << SETTINGS_EOF
{
  "permissions": {
    "allow": [
      "Bash(*)",
      "Read",
      "Write",
      "Edit",
      "Glob",
      "Grep",
      "WebSearch",
      "WebFetch",
      ${MAI_TAI_TOOLS}
    ],
    "deny": []
  }
}
SETTINGS_EOF
else
  # Non-coder agents get limited permissions
  cat > "${WORKDIR}/.claude/settings.local.json" << SETTINGS_EOF
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
      ${MAI_TAI_TOOLS}
    ],
    "deny": []
  }
}
SETTINGS_EOF
fi

# Skip onboarding prompt (required for headless mode)
echo '{"hasCompletedOnboarding": true}' > ~/.claude.json

echo "[mai-tai-agent] Starting driver loop..."
exec python3 /home/agent/driver.py
