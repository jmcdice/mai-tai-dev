#!/usr/bin/env bash
# Install the DDNS cron job to run every 5 minutes
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DDNS_SCRIPT="$SCRIPT_DIR/ddns-update.sh"
LOG_FILE="$(dirname "$SCRIPT_DIR")/logs/ddns.log"

echo "Installing DDNS cron job for user joey..."
echo "*/5 * * * * /usr/bin/bash $DDNS_SCRIPT >> $LOG_FILE 2>&1" | sudo crontab -u joey -
echo "Done. Verifying:"
sudo crontab -u joey -l
