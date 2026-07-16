#!/bin/bash
# Mai-Tai agent bootstrap (shared across runtimes).
#
# Prepares the workspace before the driver starts: mai-tai config, memory
# directories, instructions file (CLAUDE.md / AGENTS.md), optional repo clone,
# runtime settings, and the MCP config.
#
# Expects to be sourced (or run) by a runtime entrypoint with
# INSTRUCTIONS_FILE set (CLAUDE.md for claude-code, AGENTS.md for codex).

set -euo pipefail

WORKDIR="${AGENT_WORKDIR:-/home/agent/workspace}"
MEMORY_DIR="${MAI_TAI_MEMORY_DIR:-/home/agent/memory}"
INSTRUCTIONS_FILE="${INSTRUCTIONS_FILE:-CLAUDE.md}"

# Required env vars
: "${MAI_TAI_API_URL:?MAI_TAI_API_URL is required}"
: "${MAI_TAI_API_KEY:?MAI_TAI_API_KEY is required}"
: "${MAI_TAI_WORKSPACE_ID:?MAI_TAI_WORKSPACE_ID is required}"

# Optional env vars
AGENT_NAME="${AGENT_NAME:-Agent}"
AGENT_PURPOSE="${AGENT_PURPOSE:-General-purpose agent.}"
AGENT_TEMPLATE="${AGENT_TEMPLATE:-custom}"
AGENT_MODEL="${AGENT_MODEL:-sonnet}"

echo "[mai-tai-agent] Bootstrapping agent: ${AGENT_NAME} (template=${AGENT_TEMPLATE}, model=${AGENT_MODEL})"
echo "[mai-tai-agent] Workspace: ${MAI_TAI_WORKSPACE_ID}"

# 1. Global mai-tai config (API URL + key)
mkdir -p ~/.config/mai-tai
cat > ~/.config/mai-tai/config << EOF
MAI_TAI_API_URL=${MAI_TAI_API_URL}
MAI_TAI_API_KEY=${MAI_TAI_API_KEY}
EOF

# 2. Persistent memory layout (volume-backed, survives restarts)
mkdir -p "${MEMORY_DIR}/tasks" "${MEMORY_DIR}/journal" "${MEMORY_DIR}/state"

# 3. Project-level .env.mai-tai (workspace ID)
mkdir -p "${WORKDIR}"
echo "MAI_TAI_WORKSPACE_ID=${MAI_TAI_WORKSPACE_ID}" > "${WORKDIR}/.env.mai-tai"

# 4. Build the instructions file at a temp path — the coder template wipes
# WORKDIR when cloning, so it's only installed into WORKDIR at the end.
INSTRUCTIONS_TMP="/tmp/agent_instructions_tmp"
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

cat > "${INSTRUCTIONS_TMP}" << INSTRUCTIONS_EOF
# ${AGENT_NAME}

## Purpose
${AGENT_PURPOSE}

${TEMPLATE_CONTENT}

## How You Communicate (Driver Mode)
Messages from the human arrive automatically as new prompts, and your final
response each turn is posted to the workspace chat automatically — just answer.
- Progress updates during long work: call \`update_status\` (non-blocking).
- Questions for the human: call \`chat_with_human\` — it delivers immediately
  and their answer arrives as your NEXT prompt. Finish your turn after asking;
  never wait or poll.
- Recall past conversations: call \`search_history\` — full-text search over
  everything ever said in this workspace. Search before asking the human to
  repeat themselves.

## Memory (persistent across sessions)
Your sessions reset; your memory does not. At session start your memory
context is injected into the first prompt.
- \`memory\` tool → MEMORY.md: durable facts, preferences, decisions
  (2200-char cap — consolidate when full). Loaded every session.
- \`journal\` tool → daily notes: task state, decisions, in-flight work.
  Today's and yesterday's entries load at session start. Journal before
  finishing any long task and whenever something significant happens.
- \`${MEMORY_DIR}/tasks/lessons.md\`: after ANY correction from the human,
  append the lesson — format: \`- [date] LESSON: <what went wrong> → <the rule>\`.
  The goal: never make the same mistake twice.

## Working Principles

### Plan before acting
- For any non-trivial task (3+ steps or architectural decisions), plan first
- If something goes sideways, STOP and re-plan — don't keep pushing
- Verify correctness before marking anything done

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
INSTRUCTIONS_EOF

# 5. Clone repo for coder agents
if [ "${AGENT_TEMPLATE}" = "coder" ] && [ -n "${REPO_URL:-}" ]; then
  echo "[mai-tai-agent] Cloning repository: ${REPO_URL}"

  if [ -n "${GITHUB_TOKEN:-}" ]; then
    git config --global url."https://x-access-token:${GITHUB_TOKEN}@github.com/".insteadOf "https://github.com/"
    git config --global url."https://x-access-token:${GITHUB_TOKEN}@github.com/".insteadOf "git@github.com:"
  fi

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
fi

# 5b. Install the built instructions file into the (possibly freshly cloned)
# workspace. Intentionally overwrites any instructions file from a cloned repo
# — the agent's purpose, role, and communication contract take precedence.
cp "${INSTRUCTIONS_TMP}" "${WORKDIR}/${INSTRUCTIONS_FILE}"

# 6. Git identity (agent CLIs require a repo)
git config --global user.email "agent@mai-tai.dev"
git config --global user.name "${AGENT_NAME}"

if [ ! -d "${WORKDIR}/.git" ]; then
  git init "${WORKDIR}"
  git -C "${WORKDIR}" add -A
  git -C "${WORKDIR}" commit -m "Initial agent workspace" --allow-empty
fi

# 7. MCP config for the mai-tai server (driver mode + memory dir passed
# explicitly so the MCP server child process is configured regardless of
# how the runtime propagates env)
cat > /tmp/mcp-config.json << MCP_EOF
{
  "mcpServers": {
    "mai-tai": {
      "command": "uvx",
      "args": ["--refresh", "mai-tai-mcp"],
      "env": {
        "MAI_TAI_DRIVER_MODE": "1",
        "MAI_TAI_MEMORY_DIR": "${MEMORY_DIR}"
      }
    }
  }
}
MCP_EOF

echo "[mai-tai-agent] Bootstrap complete."
