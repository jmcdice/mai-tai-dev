#!/usr/bin/env bash
# ddns-update.sh — update GCP Cloud DNS A records when home IP changes
set -euo pipefail

PROJECT="echo-fiction"
ZONE="mai-tai-dev"
TTL=300
RECORDS=("www" "api")

# Get current public IP (try multiple providers)
CURRENT_IP=$(curl -sf --max-time 5 https://api.ipify.org \
    || curl -sf --max-time 5 https://ifconfig.me \
    || curl -sf --max-time 5 https://icanhazip.com)

if [ -z "$CURRENT_IP" ]; then
    echo "ERROR: Could not determine public IP" >&2
    exit 1
fi

# Check current DNS value against www record
DNS_IP=$(gcloud dns record-sets describe "www.mai-tai.dev." \
    --type=A --zone="$ZONE" --project="$PROJECT" \
    --format='value(rrdatas[0])' 2>/dev/null || echo "")

if [ "$CURRENT_IP" = "$DNS_IP" ]; then
    exit 0
fi

echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) IP changed: ${DNS_IP:-<not set>} -> $CURRENT_IP"

for record in "${RECORDS[@]}"; do
    gcloud dns record-sets update "${record}.mai-tai.dev." \
        --type=A \
        --ttl="$TTL" \
        --rrdatas="$CURRENT_IP" \
        --zone="$ZONE" \
        --project="$PROJECT"
done

echo "DNS updated successfully"
