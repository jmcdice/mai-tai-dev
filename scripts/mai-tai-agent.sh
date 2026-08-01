#!/bin/bash
#
# mai-tai-agent.sh - Agent workspace manager for Mai-Tai
#
# Manages Claude Code agent processes that run in tmux sessions,
# each connected to a Mai-Tai workspace via the MCP server.
#
# USAGE:
#   ./mai-tai-agent.sh create <workspace-id> <name> [--purpose "..."] [--template research]
#   ./mai-tai-agent.sh start <workspace-id>
#   ./mai-tai-agent.sh stop <workspace-id>
#   ./mai-tai-agent.sh restart <workspace-id>
#   ./mai-tai-agent.sh status [workspace-id]
#   ./mai-tai-agent.sh logs <workspace-id>
#   ./mai-tai-agent.sh list
#   ./mai-tai-agent.sh delete <workspace-id>
#
# REQUIREMENTS:
#   - tmux
#   - claude (Claude Code CLI)
#   - uvx (for mai-tai-mcp)
#   - ~/.config/mai-tai/config with MAI_TAI_API_URL and MAI_TAI_API_KEY
#

set -euo pipefail

# Configuration
AGENTS_DIR="${AGENTS_DIR:-$HOME/agents}"
TMUX_PREFIX="agent-"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { echo -e "${BLUE}[mai-tai-agent]${NC} $*"; }
error() { echo -e "${RED}[mai-tai-agent]${NC} $*" >&2; }
success() { echo -e "${GREEN}[mai-tai-agent]${NC} $*"; }
warn() { echo -e "${YELLOW}[mai-tai-agent]${NC} $*"; }

# Get tmux session name from workspace ID (first 8 chars)
session_name() {
    echo "${TMUX_PREFIX}${1:0:8}"
}

# Get agent directory
agent_dir() {
    echo "${AGENTS_DIR}/$1"
}

# Check if an agent session is running
is_running() {
    tmux has-session -t "$(session_name "$1")" 2>/dev/null
}

cmd_create() {
    local workspace_id="$1"
    local name="${2:-Agent}"
    local purpose=""
    local template="custom"

    # Parse optional args
    shift 2 || true
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --purpose) purpose="$2"; shift 2 ;;
            --template) template="$2"; shift 2 ;;
            *) shift ;;
        esac
    done

    local dir
    dir=$(agent_dir "$workspace_id")

    if [[ -d "$dir" ]]; then
        warn "Agent directory already exists: $dir"
        return 0
    fi

    log "Creating agent workspace: $name"
    mkdir -p "$dir/workspace"
    mkdir -p "$dir/.claude"

    # Write CLAUDE.md
    cat > "$dir/CLAUDE.md" << CLAUDE_EOF
# ${name}

## Purpose
${purpose:-General-purpose agent.}

## Mai-Tai Mode
When this session starts, IMMEDIATELY call \`chat_with_human\` to greet the user.
Stay in mai-tai mode for the entire session — use \`update_status\` for progress
updates and \`chat_with_human\` as HOME BASE when done or when you need an answer.
After completing any task, ALWAYS call \`chat_with_human\` to report results.
CLAUDE_EOF

    # Write .env.mai-tai
    echo "MAI_TAI_WORKSPACE_ID=${workspace_id}" > "$dir/.env.mai-tai"

    # Write .claude/settings.local.json
    cat > "$dir/.claude/settings.local.json" << 'SETTINGS_EOF'
{
  "permissions": {
    "allow": [
      "WebSearch",
      "WebFetch",
      "mcp__mai-tai__chat_with_human",
      "mcp__mai-tai__update_status",
      "mcp__mai-tai__get_messages",
      "mcp__mai-tai__get_project_info"
    ],
    "deny": []
  }
}
SETTINGS_EOF

    success "Created agent workspace at $dir"
    log "To start: mai-tai-agent start $workspace_id"
}

cmd_start() {
    local workspace_id="$1"
    local dir
    dir=$(agent_dir "$workspace_id")
    local session
    session=$(session_name "$workspace_id")

    if ! [[ -d "$dir" ]]; then
        error "Agent directory not found: $dir"
        error "Run: mai-tai-agent create $workspace_id \"Agent Name\" first"
        return 1
    fi

    if is_running "$workspace_id"; then
        warn "Agent already running in tmux session: $session"
        return 0
    fi

    log "Starting agent in tmux session: $session"
    tmux new-session -d -s "$session" -c "$dir" \
        "claude --dangerously-skip-permissions 2>&1 | tee -a $dir/agent.log"

    sleep 1
    if is_running "$workspace_id"; then
        success "Agent started! Attach with: tmux attach -t $session"
    else
        error "Agent failed to start. Check $dir/agent.log"
        return 1
    fi
}

cmd_stop() {
    local workspace_id="$1"
    local session
    session=$(session_name "$workspace_id")

    if ! is_running "$workspace_id"; then
        warn "Agent not running: $session"
        return 0
    fi

    log "Stopping agent: $session"
    tmux kill-session -t "$session"
    success "Agent stopped"
}

cmd_restart() {
    local workspace_id="$1"
    cmd_stop "$workspace_id" || true
    sleep 1
    cmd_start "$workspace_id"
}

cmd_status() {
    local workspace_id="${1:-}"

    if [[ -n "$workspace_id" ]]; then
        local session
        session=$(session_name "$workspace_id")
        local dir
        dir=$(agent_dir "$workspace_id")

        echo "Workspace: $workspace_id"
        echo "Directory: $dir"
        echo "Session:   $session"

        if [[ -d "$dir" ]]; then
            echo "Directory: exists"
        else
            echo "Directory: missing"
        fi

        if is_running "$workspace_id"; then
            echo -e "Status:    ${GREEN}running${NC}"
        else
            echo -e "Status:    ${RED}stopped${NC}"
        fi
    else
        cmd_list
    fi
}

cmd_logs() {
    local workspace_id="$1"
    local dir
    dir=$(agent_dir "$workspace_id")

    if [[ -f "$dir/agent.log" ]]; then
        tail -50 "$dir/agent.log"
    else
        error "No log file found at $dir/agent.log"
    fi
}

cmd_list() {
    echo "Agent Workspaces:"
    echo ""

    if [[ ! -d "$AGENTS_DIR" ]]; then
        echo "  No agents directory found ($AGENTS_DIR)"
        return 0
    fi

    local found=0
    for dir in "$AGENTS_DIR"/*/; do
        [[ -d "$dir" ]] || continue
        local ws_id
        ws_id=$(basename "$dir")
        local session
        session=$(session_name "$ws_id")

        local status_str
        if is_running "$ws_id"; then
            status_str="${GREEN}●${NC} running"
        else
            status_str="${RED}●${NC} stopped"
        fi

        local name="(unknown)"
        if [[ -f "$dir/CLAUDE.md" ]]; then
            name=$(head -1 "$dir/CLAUDE.md" | sed 's/^# //')
        fi

        printf "  %b  %-30s  %s\n" "$status_str" "$name" "$ws_id"
        found=1
    done

    if [[ $found -eq 0 ]]; then
        echo "  No agent workspaces found"
    fi
}

cmd_delete() {
    local workspace_id="$1"
    local dir
    dir=$(agent_dir "$workspace_id")

    if is_running "$workspace_id"; then
        cmd_stop "$workspace_id"
    fi

    if [[ -d "$dir" ]]; then
        log "Deleting agent directory: $dir"
        rm -rf "$dir"
        success "Agent deleted"
    else
        warn "Agent directory not found: $dir"
    fi
}

# Main
case "${1:-help}" in
    create)  shift; cmd_create "$@" ;;
    start)   shift; cmd_start "$@" ;;
    stop)    shift; cmd_stop "$@" ;;
    restart) shift; cmd_restart "$@" ;;
    status)  shift; cmd_status "$@" ;;
    logs)    shift; cmd_logs "$@" ;;
    list)    cmd_list ;;
    delete)  shift; cmd_delete "$@" ;;
    help|*)
        echo "Usage: mai-tai-agent <command> [args]"
        echo ""
        echo "Commands:"
        echo "  create <workspace-id> <name> [--purpose '...'] [--template type]"
        echo "  start <workspace-id>        Start agent in tmux"
        echo "  stop <workspace-id>         Stop agent"
        echo "  restart <workspace-id>      Restart agent"
        echo "  status [workspace-id]       Show status"
        echo "  logs <workspace-id>         Show agent logs"
        echo "  list                        List all agents"
        echo "  delete <workspace-id>       Delete agent"
        ;;
esac
