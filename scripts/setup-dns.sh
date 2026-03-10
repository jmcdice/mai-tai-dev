#!/usr/bin/env bash
# setup-dns.sh — create/update GCP Cloud DNS records for mai-tai.dev
# Run this once when ready to cut over from GCP-hosted infra.
set -euo pipefail

PROJECT="echo-fiction"
ZONE="mai-tai-dev"
TTL=300

# Get current public IP
CURRENT_IP=$(curl -sf --max-time 5 https://api.ipify.org \
    || curl -sf --max-time 5 https://ifconfig.me)

echo "Public IP: $CURRENT_IP"
echo "Setting www.mai-tai.dev and api.mai-tai.dev -> $CURRENT_IP"
echo ""

# --- www.mai-tai.dev ---
if gcloud dns record-sets describe "www.mai-tai.dev." --type=A \
        --zone="$ZONE" --project="$PROJECT" &>/dev/null; then
    echo "Updating existing www.mai-tai.dev A record..."
    gcloud dns record-sets update "www.mai-tai.dev." \
        --type=A --ttl="$TTL" --rrdatas="$CURRENT_IP" \
        --zone="$ZONE" --project="$PROJECT"
else
    echo "Creating www.mai-tai.dev A record..."
    gcloud dns record-sets create "www.mai-tai.dev." \
        --type=A --ttl="$TTL" --rrdatas="$CURRENT_IP" \
        --zone="$ZONE" --project="$PROJECT"
fi

# --- api.mai-tai.dev ---
# Remove existing CNAME if present, then create A record
if gcloud dns record-sets describe "api.mai-tai.dev." --type=CNAME \
        --zone="$ZONE" --project="$PROJECT" &>/dev/null; then
    echo "Removing old api.mai-tai.dev CNAME..."
    gcloud dns record-sets delete "api.mai-tai.dev." \
        --type=CNAME --zone="$ZONE" --project="$PROJECT"
fi

if gcloud dns record-sets describe "api.mai-tai.dev." --type=A \
        --zone="$ZONE" --project="$PROJECT" &>/dev/null; then
    echo "Updating existing api.mai-tai.dev A record..."
    gcloud dns record-sets update "api.mai-tai.dev." \
        --type=A --ttl="$TTL" --rrdatas="$CURRENT_IP" \
        --zone="$ZONE" --project="$PROJECT"
else
    echo "Creating api.mai-tai.dev A record..."
    gcloud dns record-sets create "api.mai-tai.dev." \
        --type=A --ttl="$TTL" --rrdatas="$CURRENT_IP" \
        --zone="$ZONE" --project="$PROJECT"
fi

echo ""
echo "Done. DNS records set to $CURRENT_IP"
echo "Propagation typically takes 1-5 minutes (TTL is ${TTL}s)."
