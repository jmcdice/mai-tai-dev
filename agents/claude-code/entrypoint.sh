#!/bin/bash
# Mai-Tai claude-code runtime entrypoint: bootstrap, then hand off to the
# per-turn driver loop.

set -euo pipefail

# Auth: OAuth token (Pro/Max subscription), standard API key, or Vertex AI.
if [ "${CLAUDE_CODE_USE_VERTEX:-}" = "1" ]; then
  # The backend passes the host's Application Default Credentials as JSON —
  # bind-mounting them doesn't work, since the host file is owned by the host
  # user and unreadable to this container's unprivileged `agent` user.
  if [ -n "${GOOGLE_ADC_JSON:-}" ]; then
    mkdir -p ~/.config/gcloud
    printf '%s' "${GOOGLE_ADC_JSON}" > ~/.config/gcloud/application_default_credentials.json
    chmod 600 ~/.config/gcloud/application_default_credentials.json
    export GOOGLE_APPLICATION_CREDENTIALS=~/.config/gcloud/application_default_credentials.json
    unset GOOGLE_ADC_JSON
  fi
  if [ ! -r "${GOOGLE_APPLICATION_CREDENTIALS:-/nonexistent}" ]; then
    echo "[mai-tai-agent] ERROR: CLAUDE_CODE_USE_VERTEX=1 but no usable ADC (set GOOGLE_ADC_JSON or GOOGLE_APPLICATION_CREDENTIALS)"
    exit 1
  fi
  echo "[mai-tai-agent] Auth: Vertex AI (project ${ANTHROPIC_VERTEX_PROJECT_ID:-unset}, region ${CLOUD_ML_REGION:-unset})"
elif [ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then
  echo "[mai-tai-agent] Auth: Claude OAuth token"
elif [ -n "${ANTHROPIC_API_KEY:-}" ]; then
  echo "[mai-tai-agent] Auth: Anthropic API key"
else
  echo "[mai-tai-agent] ERROR: Set ANTHROPIC_API_KEY, CLAUDE_CODE_OAUTH_TOKEN, or Vertex AI env"
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

# Skip onboarding prompt (required for headless mode) and pre-trust the
# workspace, otherwise Claude discards the permissions.allow entries above
# ("this workspace has not been trusted") since nobody can accept the dialog.
cat > ~/.claude.json << CLAUDE_JSON_EOF
{
  "hasCompletedOnboarding": true,
  "projects": {
    "${WORKDIR}": {
      "hasTrustDialogAccepted": true
    }
  }
}
CLAUDE_JSON_EOF

echo "[mai-tai-agent] Starting driver loop..."
exec python3 /home/agent/driver.py
