#!/usr/bin/env bash
#
# boot-mai-tai.sh - Restore the mai-tai Claude sessions after a reboot.
#
# This is the @reboot path and nothing else. Day-to-day bot management lives in
# the admin CLI:
#
#   mai-tai bots list                 what is running, and what should be
#   mai-tai bots start <repo>|--all   start a supervisor window
#   mai-tai bots stop  <repo>         kill one for good
#   mai-tai bots restart <repo>       rotate one in place (supervisor relaunches)
#
# Why this stays a shell script: @reboot runs with a bare environment and the
# CLI is a uv-installed Python tool. If booting the bots depended on that venv,
# a broken venv after a power cut would mean no bots AND no CLI to say why. This
# path deliberately needs nothing but bash, tmux and claude.
#
# All sessions live as windows in a single tmux session named "mai-tai" (one
# window per repo). Attach with:  tmux attach -t mai-tai
#   Ctrl-b w  = pick a window (agent),  Ctrl-b n/p = next/prev
#
# Each window runs mai-tai-supervisor.sh, which keeps Claude alive across the
# ~27h single-process limit and crashes. State lives in the mai-tai workspace/DB.
#
# The mai-tai backend/frontend/db are Docker (restart=unless-stopped) and come
# back on their own after a reboot; this only restores the terminal side.
#
# USAGE:
#   boot-mai-tai.sh            start every configured repo (what @reboot runs)
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

usage() { sed -n '2,31p' "$0" | sed 's/^# \{0,1\}//'; }

case "${1:-}" in
  -h|--help|help) usage; exit 0 ;;
  "")             ;;
  *)              log "unknown option: $1 (this script only does start-all now; see 'mai-tai bots --help')"
                  usage; exit 2 ;;
esac

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

# Poll backend /health, up to HEALTH_TIMEOUT seconds.
wait_for_backend() {
  local url; url="$(grep -E '^MAI_TAI_API_URL=' "$MAI_TAI_CONFIG" 2>/dev/null | cut -d= -f2- | tr -d '[:space:]')"
  if [ -z "$url" ]; then log "WARN: no MAI_TAI_API_URL in $MAI_TAI_CONFIG; skipping health check."; return 0; fi
  if [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$url/health" 2>/dev/null)" = "200" ]; then
    log "backend healthy ($url)."; return 0
  fi
  log "waiting for backend $url/health (up to ${HEALTH_TIMEOUT}s)..."
  local deadline=$(( $(date +%s) + HEALTH_TIMEOUT ))
  until [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$url/health" 2>/dev/null)" = "200" ]; do
    if [ "$(date +%s)" -ge "$deadline" ]; then
      log "WARN: backend not healthy after ${HEALTH_TIMEOUT}s; starting anyway (self-heals)."; return 0
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

log "start-all beginning"
wait_for_backend
started=0
while read -r name; do
  [ -z "$name" ] && continue
  start_one "$name" && started=$((started+1)) || true
done < <(read_config)
log "start-all done ($started repos processed). Inspect with: mai-tai bots list"
