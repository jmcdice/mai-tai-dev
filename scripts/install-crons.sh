#!/bin/bash
# Install mai-tai cron jobs, replacing any old entries.
# Usage: sudo bash install-crons.sh
#
# Must run as root: /usr/bin/crontab on this box is NOT setgid, so a non-root
# `crontab -e` / `crontab -` fails with "/var/spool/cron/: mkstemp: Permission
# denied". Root writes the user's spool via `crontab -u <user>` just fine.
#
# Only touches mai-tai's own entries (see REMOVE_PATTERNS); any other cron jobs
# in the user's crontab (e.g. couch-commander's) are preserved untouched.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
USER="${SUDO_USER:-joey}"
LOG_DIR="$REPO_ROOT/logs"

CRONS=(
    # Restore mai-tai Claude sessions after a reboot/power outage. The mai-tai
    # backend (Docker, restart=unless-stopped) comes back on its own; this
    # reconnects the terminal side. No args = --start-all.
    "@reboot /usr/bin/bash $SCRIPT_DIR/boot-mai-tai.sh >> $LOG_DIR/boot-mai-tai.log 2>&1"
)

# Patterns to remove old/duplicate mai-tai entries (only our own lines).
REMOVE_PATTERNS=(
    "boot-mai-tai.sh"
    "mai-tai boot sessions"
)

echo "Installing mai-tai cron jobs for user: $USER"
mkdir -p "$LOG_DIR"

# Get existing crontab, strip our old entries (leaving everyone else's alone).
EXISTING=$(crontab -l -u "$USER" 2>/dev/null || true)
CLEANED="$EXISTING"
for pattern in "${REMOVE_PATTERNS[@]}"; do
    CLEANED=$(echo "$CLEANED" | grep -v "$pattern" || true)
done

# Build new crontab: everyone else's entries + our managed block.
{
    echo "$CLEANED"
    echo ""
    echo "# --- mai-tai boot sessions (managed by install-crons.sh) ---"
    for entry in "${CRONS[@]}"; do
        echo "$entry"
    done
} | crontab -u "$USER" -

echo ""
echo "Installed cron jobs:"
for entry in "${CRONS[@]}"; do
    echo "  $entry"
done

echo ""
echo "Full crontab for $USER:"
crontab -l -u "$USER"
