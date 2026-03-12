#!/bin/bash
# Mai-Tai Agent Entrypoint
#
# Configures Claude Code with MCP and mai-tai settings,
# then launches Claude in mai-tai mode.

set -euo pipefail

WORKDIR="/home/agent/workspace"
MEMORY_DIR="/home/agent/memory"

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

# 2. Ensure persistent memory directory exists
mkdir -p "${MEMORY_DIR}/tasks"

# 3. Write project-level .env.mai-tai (workspace ID)
echo "MAI_TAI_WORKSPACE_ID=${MAI_TAI_WORKSPACE_ID}" > "${WORKDIR}/.env.mai-tai"

# 4. Build CLAUDE.md — template-specific content + shared principles + past lessons
case "${AGENT_TEMPLATE}" in
  research)
    TEMPLATE_CONTENT="## Role
You are a research assistant. Your job is to help the user with research tasks.
- Search the web, compile findings, and present clear summaries.
- When given a topic, proactively find relevant information from multiple sources.
- Be thorough but concise in your reports."
    ;;
  monitor)
    TEMPLATE_CONTENT="## Role
You are a monitoring agent that runs periodic checks and reports findings.
- Present findings in clear, actionable summaries.
- Alert the user to significant changes or anomalies."
    ;;
  assistant)
    TEMPLATE_CONTENT="## Role
You are a personal assistant. Help with questions, tasks, and daily needs.
- Be proactive about offering help and following up on previous conversations.
- Be conversational and helpful."
    ;;
  coder)
    TEMPLATE_CONTENT="## Role
You are a software engineering agent. You help with code, PRs, bug fixes, and development tasks.
- Read and understand the codebase before making changes.
- Write clean, tested code. Run existing tests before and after changes.
- Create branches for your work and commit with clear messages.
- When asked to review code, be thorough but constructive."
    ;;
  *)
    TEMPLATE_CONTENT="## Role
You are a general-purpose agent. Help the user with whatever they need."
    ;;
esac

cat > "${WORKDIR}/CLAUDE.md" << CLAUDE_EOF
# ${AGENT_NAME}

## Purpose
${AGENT_PURPOSE}

${TEMPLATE_CONTENT}

## Working Principles

### Plan before acting
- For any non-trivial task (3+ steps or architectural decisions), plan first
- If something goes sideways, STOP and re-plan — don't keep pushing
- Verify correctness before marking anything done

### Self-improvement loop
- After ANY correction from the user, write the lesson to \`${MEMORY_DIR}/tasks/lessons.md\`
- Format: \`- [date] LESSON: <what went wrong> → <the rule>\`
- Review this file at the start of each session — these are your standing rules
- The goal: never make the same mistake twice

### Verification before done
- Never report a task complete without proving it works
- Check logs, run tests, demonstrate correctness
- Ask yourself: "Would a senior engineer approve this?"

### Autonomous execution
- When given a task or bug report: just fix it. No hand-holding needed.
- Point at logs, errors, tests — then resolve them.

### Simplicity first
- Make changes as simple as possible. Minimal code impact.
- No temporary fixes. Find root causes.

## Mai-Tai Mode
When this session starts, IMMEDIATELY enter mai-tai mode by calling \`chat_with_human\`
to greet the user and ask what they'd like to work on.
After completing ANY task, ALWAYS call \`chat_with_human\` to report results and get next instructions.
NEVER go idle — \`chat_with_human\` is your home base.

## Memory
Your persistent memory is at: ${MEMORY_DIR}/
- \`tasks/lessons.md\` — lessons learned (read at start, write after corrections)
- \`tasks/todo.md\` — current task plan (write before starting, check off as you go)
CLAUDE_EOF

# 5. Inject past lessons if they exist
LESSONS_FILE="${MEMORY_DIR}/tasks/lessons.md"
if [ -f "${LESSONS_FILE}" ] && [ -s "${LESSONS_FILE}" ]; then
  echo "[mai-tai-agent] Loading past lessons from memory..."
  cat >> "${WORKDIR}/CLAUDE.md" << LESSONS_EOF

## Past Lessons (from previous sessions)
$(cat "${LESSONS_FILE}")
LESSONS_EOF
fi

# 6. Clone repo for coder agents
if [ "${AGENT_TEMPLATE}" = "coder" ] && [ -n "${REPO_URL:-}" ]; then
  echo "[mai-tai-agent] Cloning repository: ${REPO_URL}"

  # Configure GitHub token for HTTPS clone if available
  if [ -n "${GITHUB_TOKEN:-}" ]; then
    git config --global url."https://x-access-token:${GITHUB_TOKEN}@github.com/".insteadOf "https://github.com/"
    git config --global url."https://x-access-token:${GITHUB_TOKEN}@github.com/".insteadOf "git@github.com:"
  fi

  # Clone into workspace (clear it first, then clone directly)
  cd /home/agent
  rm -rf "${WORKDIR}"
  if git clone "${REPO_URL}" "${WORKDIR}" 2>&1; then
    echo "[mai-tai-agent] Repository cloned successfully"
  else
    echo "[mai-tai-agent] WARNING: Failed to clone repo, creating empty workspace"
    mkdir -p "${WORKDIR}"
  fi
  cd "${WORKDIR}"

  # Re-write .env.mai-tai since we replaced WORKDIR
  echo "MAI_TAI_WORKSPACE_ID=${MAI_TAI_WORKSPACE_ID}" > "${WORKDIR}/.env.mai-tai"

  # Copy the CLAUDE.md we already built into the repo root
  cp /tmp/claude_md_tmp "${WORKDIR}/CLAUDE.md" 2>/dev/null || true
fi

# Save CLAUDE.md to a temp location before potential coder clone overwrites it
cp "${WORKDIR}/CLAUDE.md" /tmp/claude_md_tmp 2>/dev/null || true

# 7. Write Claude Code settings with permissions + MCP server
mkdir -p "${WORKDIR}/.claude"

if [ "${AGENT_TEMPLATE}" = "coder" ]; then
  # Coder agents get full permissions for development work
  cat > "${WORKDIR}/.claude/settings.local.json" << 'SETTINGS_EOF'
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
else
  # Non-coder agents get limited permissions
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
fi

# 8. Configure git (Claude Code requires a repo)
git config --global user.email "agent@mai-tai.dev"
git config --global user.name "${AGENT_NAME}"

if [ ! -d "${WORKDIR}/.git" ]; then
  git init "${WORKDIR}"
  git -C "${WORKDIR}" add -A
  git -C "${WORKDIR}" commit -m "Initial agent workspace" --allow-empty
fi

# 9. Skip onboarding prompt (required for headless mode)
echo '{"hasCompletedOnboarding": true}' > ~/.claude.json

echo "[mai-tai-agent] Configuration complete. Starting Claude..."

# 10. Write MCP config as JSON for --mcp-config flag
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

# 11. Launch Claude in headless mai-tai mode
cd "${WORKDIR}"
exec claude -p "start mai tai mode" \
  --dangerously-skip-permissions \
  --model sonnet \
  --mcp-config /tmp/mcp-config.json
