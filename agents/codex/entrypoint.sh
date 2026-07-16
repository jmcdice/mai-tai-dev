#!/bin/bash
# Mai-Tai codex runtime entrypoint: bootstrap, write codex config, then hand
# off to the per-turn driver loop.

set -euo pipefail

if [ -z "${OPENAI_API_KEY:-}" ]; then
  echo "[mai-tai-agent] ERROR: OPENAI_API_KEY is required for the codex runtime"
  exit 1
fi

# codex exec reads CODEX_API_KEY (v0.36+); keep OPENAI_API_KEY for older paths
export CODEX_API_KEY="${OPENAI_API_KEY}"

export INSTRUCTIONS_FILE="AGENTS.md"
source /home/agent/bootstrap.sh

MEMORY_DIR="${MAI_TAI_MEMORY_DIR:-/home/agent/memory}"
AGENT_MODEL="${AGENT_MODEL:-gpt-5-codex}"

# Codex config: model, headless-safe approvals/sandbox (the container IS the
# sandbox — network-isolated from everything but the backend), API-key auth,
# and the mai-tai MCP server in driver mode.
mkdir -p ~/.codex
cat > ~/.codex/config.toml << TOML_EOF
model = "${AGENT_MODEL}"
approval_policy = "never"
sandbox_mode = "danger-full-access"
preferred_auth_method = "apikey"

[mcp_servers.mai-tai]
command = "uvx"
args = ["--refresh", "mai-tai-mcp"]
env = { MAI_TAI_DRIVER_MODE = "1", MAI_TAI_MEMORY_DIR = "${MEMORY_DIR}" }
TOML_EOF

echo "[mai-tai-agent] Starting driver loop (codex, model=${AGENT_MODEL})..."
exec python3 /home/agent/driver.py
