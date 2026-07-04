#!/usr/bin/env bash
#
# boot-mai-tai.sh - Manage self-healing Claude mai-tai sessions, one per repo.
#
# All sessions live as windows in a single tmux session named "mai-tai"
# (one window per repo). Attach with:  tmux attach -t mai-tai
#   Ctrl-b w  = pick a window (agent),  Ctrl-b n/p = next/prev
#
# Each window runs mai-tai-supervisor.sh, which keeps Claude alive across the
# ~27h single-process limit and crashes. State lives in the mai-tai workspace/DB.
#
# The mai-tai backend/frontend/db are Docker (restart=unless-stopped) and come
# back on their own after a reboot; this only restores the terminal side.
#
# USAGE:
#   boot-mai-tai.sh                 (no args) same as --start-all; used by @reboot
#   boot-mai-tai.sh --list          show configured repos and session status
#   boot-mai-tai.sh --start <repo>  start one repo (e.g. folio or folio/)
#   boot-mai-tai.sh --start-all     wait for backend, then start all configured repos
#   boot-mai-tai.sh --stop  <repo>  stop one repo's window
#   boot-mai-tai.sh --stop-all      stop every managed session
#   boot-mai-tai.sh --restart <repo>
#   boot-mai-tai.sh --help
#
# Configured repos: ~/.config/mai-tai/boot-repos.conf (one dir per line).
#
set -uo pipefail

REPOS_ROOT="/home/joey/repos"
CONFIG="$HOME/.config/mai-tai/boot-repos.conf"
MAI_TAI_CONFIG="$HOME/.config/mai-tai/config"
SUPERVISOR="$REPOS_ROOT/mai-tai-dev/scripts/mai-tai-supervisor.sh"
LOG_DIR="$REPOS_ROOT/mai-tai-dev/logs"
SESSION="mai-tai"
HEALTH_TIMEOUT=300

# Load PATH + Vertex auth env (cron runs with a bare environment). Relax -u
# while sourcing since the profile may reference unset vars.
set +u
[ -f "$HOME/.bash_profile" ] && . "$HOME/.bash_profile" >/dev/null 2>&1
set -u

mkdir -p "$LOG_DIR"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# --- Preconditions ---
command -v claude >/dev/null 2>&1 || { log "FATAL: claude not on PATH"; exit 1; }
command -v tmux   >/dev/null 2>&1 || { log "FATAL: tmux not on PATH"; exit 1; }
[ -f "$CONFIG" ]     || { log "FATAL: config not found: $CONFIG"; exit 1; }
[ -x "$SUPERVISOR" ] || { log "FATAL: supervisor not found/executable: $SUPERVISOR"; exit 1; }

# tmux window names can't contain '.' or ':'; normalize.
sanitize() { echo "$1" | tr -c 'A-Za-z0-9_-' '-' | sed 's/-\{2,\}/-/g; s/-$//'; }

# Emit cleaned repo tokens (basename, no comments/blanks/trailing slash) from config.
read_config() {
  while IFS= read -r raw || [ -n "$raw" ]; do
    local line="${raw%%#*}"
    line="$(echo "$line" | tr -d '[:space:]')"
    line="${line%/}"
    [ -n "$line" ] && basename "$line"
  done < "$CONFIG"
}

session_exists() { tmux has-session -t "$SESSION" 2>/dev/null; }
window_exists()  { tmux list-windows -t "$SESSION" -F '#W' 2>/dev/null | grep -Fxq "$1"; }

# Lowest window index not currently in use (we address windows by name, so the
# index only needs to be free -- avoids tmux's "-t <session>" resolving to the
# active window's index and erroring "index N in use").
next_free_index() {
  local used; used="$(tmux list-windows -t "$SESSION" -F '#{window_index}' 2>/dev/null)"
  local i=0
  while echo "$used" | grep -qx "$i"; do i=$((i+1)); done
  echo "$i"
}

# Poll backend /health. Args: max-seconds (0 = single quick check).
wait_for_backend() {
  local max="$1"
  local url; url="$(grep -E '^MAI_TAI_API_URL=' "$MAI_TAI_CONFIG" 2>/dev/null | cut -d= -f2- | tr -d '[:space:]')"
  if [ -z "$url" ]; then log "WARN: no MAI_TAI_API_URL in $MAI_TAI_CONFIG; skipping health check."; return 0; fi
  local code
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$url/health" 2>/dev/null)"
  if [ "$code" = "200" ] || [ "$max" -eq 0 ]; then
    [ "$code" = "200" ] && log "backend healthy ($url)." || log "WARN: backend not healthy (HTTP ${code:-none}); starting anyway (self-heals)."
    return 0
  fi
  log "waiting for backend $url/health (up to ${max}s)..."
  local deadline=$(( $(date +%s) + max ))
  until [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$url/health" 2>/dev/null)" = "200" ]; do
    if [ "$(date +%s)" -ge "$deadline" ]; then
      log "WARN: backend not healthy after ${max}s; starting anyway (self-heals)."; return 0
    fi
    sleep 5
  done
  log "backend healthy ($url)."
}

# Start one repo as a window in the mai-tai session. Idempotent.
start_one() {
  local token="$1"
  local name; name="$(basename "${token%/}")"
  local dir="$REPOS_ROOT/$name"
  local win; win="$(sanitize "$name")"

  if [ ! -d "$dir" ]; then log "SKIP $name: directory not found ($dir)"; return 1; fi
  if [ ! -f "$dir/.env.mai-tai" ]; then log "SKIP $name: no .env.mai-tai in $dir"; return 1; fi
  if session_exists && window_exists "$win"; then log "SKIP $name: window '$win' already running"; return 0; fi

  local cmd="bash -lc '\"$SUPERVISOR\" \"$dir\"'"
  if session_exists; then
    local idx; idx="$(next_free_index)"
    log "START $name -> window '$SESSION:$idx' ($win)"
    tmux new-window -d -t "$SESSION:$idx" -n "$win" -c "$dir" "$cmd"
  else
    log "START $name -> new session '$SESSION', window '$win'"
    tmux new-session -d -s "$SESSION" -n "$win" -c "$dir" "$cmd"
  fi
}

stop_one() {
  local name; name="$(basename "${1%/}")"
  local win; win="$(sanitize "$name")"
  if session_exists && window_exists "$win"; then
    log "STOP $name -> killing window '$SESSION:$win'"
    tmux kill-window -t "$SESSION:$win"
  else
    log "SKIP $name: no window '$win' running"
  fi
}

cmd_list() {
  echo "Configured repos (session: $SESSION)"
  echo
  local any=0
  while read -r name; do
    [ -z "$name" ] && continue
    any=1
    local win; win="$(sanitize "$name")"
    local status="stopped"
    session_exists && window_exists "$win" && status="running"
    printf "  %-8s  %-24s  window: %s\n" "$status" "$name" "$win"
  done < <(read_config)
  [ "$any" -eq 0 ] && echo "  (no repos configured in $CONFIG)"
  echo
  if session_exists; then
    echo "Attach:  tmux attach -t $SESSION    (Ctrl-b w = pick, Ctrl-b n/p = next/prev)"
  else
    echo "Session '$SESSION' not running. Start with: $0 --start-all"
  fi
}

cmd_start_all() {
  log "start-all beginning"
  wait_for_backend "$HEALTH_TIMEOUT"
  local started=0
  while read -r name; do
    [ -z "$name" ] && continue
    start_one "$name" && started=$((started+1)) || true
  done < <(read_config)
  log "start-all done."
  cmd_list
}

usage() { sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'; }

# --- Dispatch ---
case "${1:---start-all}" in
  --list|list)        cmd_list ;;
  --start|start)      shift; [ $# -ge 1 ] || { log "usage: --start <repo>"; exit 2; }
                      wait_for_backend 0; start_one "$1" ;;
  --start-all|start-all) cmd_start_all ;;
  --stop|stop)        shift; [ $# -ge 1 ] || { log "usage: --stop <repo>"; exit 2; }; stop_one "$1" ;;
  --stop-all|stop-all)
                      if session_exists; then log "stopping all: killing session '$SESSION'"; tmux kill-session -t "$SESSION"; else log "session '$SESSION' not running"; fi ;;
  --restart|restart)  shift; [ $# -ge 1 ] || { log "usage: --restart <repo>"; exit 2; }
                      stop_one "$1"; sleep 1; wait_for_backend 0; start_one "$1" ;;
  -h|--help|help)     usage ;;
  *)                  log "unknown option: $1"; usage; exit 2 ;;
esac
