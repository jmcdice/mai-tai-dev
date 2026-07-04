#!/usr/bin/env bash
#
# mai-tai-supervisor.sh - Keep a single Claude Code mai-tai session alive.
#
# Runs inside a tmux window (one per repo). Launches Claude in mai-tai mode and
# keeps it healthy two ways:
#
#   1. Relaunch on exit -- crashes, manual /mai-tai stop, or the process simply
#      dying.
#   2. Proactive rotation -- Claude is capped at MAI_TAI_ROTATE_AFTER (default
#      24h) via `timeout`. This pre-empts Claude's ~27h single-process limit,
#      which does NOT necessarily kill the process: it can instead drop Claude
#      back to a plain interactive prompt, disconnected from mai-tai, which a
#      relaunch-on-exit loop alone would never catch. Recycling at 24h avoids
#      that dead-but-alive state entirely.
#
# Durable state lives in the mai-tai workspace/DB, so a fresh process reconnects
# to the same workspace via the repo's .env.mai-tai (MAI_TAI_WORKSPACE_ID).
# Killing Claude also cleans up its MCP child (its stdin closes and the mai-tai
# MCP server self-exits), so rotation leaves no orphans.
#
# USAGE: mai-tai-supervisor.sh <repo-dir>
# ENV:   MAI_TAI_ROTATE_AFTER  max session lifetime (default 24h; 0 disables)
#
set -uo pipefail

REPO_DIR="${1:?usage: mai-tai-supervisor.sh <repo-dir>}"
REPO_NAME="$(basename "$REPO_DIR")"
LOG_DIR="/home/joey/repos/mai-tai-dev/logs"
LOG="$LOG_DIR/session-$REPO_NAME.log"
ROTATE_AFTER="${MAI_TAI_ROTATE_AFTER:-24h}"

# Ensure PATH + Vertex auth env are present even if launched outside a login
# shell (e.g. straight from cron). Sourcing may touch unset vars, so relax -u.
set +u
[ -f "$HOME/.bash_profile" ] && . "$HOME/.bash_profile" >/dev/null 2>&1
set -u

mkdir -p "$LOG_DIR"
cd "$REPO_DIR" || { echo "FATAL: cannot cd to $REPO_DIR"; exit 1; }

# Expanded form of the `yolo` alias plus the mai-tai activation prompt.
CLAUDE_CMD=(claude --model claude-opus-4-8 --dangerously-skip-permissions "/mai-tai start")

MIN_BACKOFF=3
MAX_BACKOFF=60
backoff=$MIN_BACKOFF

stamp() { date '+%Y-%m-%d %H:%M:%S'; }

# Run Claude, bounded by ROTATE_AFTER when set.
#
# `--foreground` is REQUIRED: without it, `timeout` runs claude in a separate
# process group that cannot become the terminal's foreground group, so claude's
# TTY detection fails, its interactive UI never renders, and it never brings up
# the mai-tai MCP server -- the window looks "running" but the bot is dead
# (blank pane, no MCP, never answers). `--foreground` lets claude own the pane
# TTY while still being bounded by the timeout.
run_claude() {
  if [ -n "$ROTATE_AFTER" ] && [ "$ROTATE_AFTER" != "0" ] && command -v timeout >/dev/null 2>&1; then
    timeout -k 30 --foreground "$ROTATE_AFTER" "${CLAUDE_CMD[@]}"
  else
    "${CLAUDE_CMD[@]}"
  fi
}

# Claude runs directly on the pane TTY (no pipe) so the window stays interactive.
# The full transcript lives in the mai-tai workspace/DB; we only log lifecycle.
while true; do
  echo "=== [$(stamp)] starting claude for $REPO_NAME (rotate after ${ROTATE_AFTER:-off}) ===" >> "$LOG"
  start=$SECONDS
  run_claude
  rc=$?
  ran=$(( SECONDS - start ))

  if [ "$rc" -eq 124 ]; then
    echo "=== [$(stamp)] $REPO_NAME rotated after ${ran}s (max lifetime reached; pre-empting 27h limit) ===" >> "$LOG"
  else
    echo "=== [$(stamp)] $REPO_NAME claude exited rc=$rc after ${ran}s ===" >> "$LOG"
  fi

  # Quick exit => likely backend still down / transient. Back off. A normal run
  # or a rotation (long-lived) resets to the minimum.
  if [ "$ran" -lt 60 ]; then
    backoff=$(( backoff * 2 ))
    [ "$backoff" -gt "$MAX_BACKOFF" ] && backoff=$MAX_BACKOFF
  else
    backoff=$MIN_BACKOFF
  fi

  echo "[$(stamp)] relaunching $REPO_NAME in ${backoff}s..." >> "$LOG"
  sleep "$backoff"
done
