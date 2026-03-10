#!/usr/bin/env bash
# setup-tls.sh — install acme.sh and issue wildcard TLS cert via GCP Cloud DNS
# Run once after setup-dns.sh. acme.sh handles renewals automatically via cron.
set -euo pipefail

DOMAIN="mai-tai.dev"
CERT_DIR="$(realpath "$(dirname "$0")/../caddy/certs")"
ACME_HOME="$HOME/.acme.sh"
EMAIL="jmcdice@gmail.com"

# Install acme.sh if not already present
if [ ! -f "$ACME_HOME/acme.sh" ]; then
    echo "Installing acme.sh..."
    curl -fsSL https://get.acme.sh | sh -s email="$EMAIL"
    echo ""
fi

mkdir -p "$CERT_DIR"

# Issue wildcard cert using GCP Cloud DNS (DNS-01 challenge — no ports needed)
echo "Issuing wildcard cert for *.${DOMAIN} and ${DOMAIN}..."
GCLOUD_PROJECT=echo-fiction \
    "$ACME_HOME/acme.sh" --issue \
    --dns dns_gcloud \
    -d "*.${DOMAIN}" \
    -d "${DOMAIN}" \
    --keylength ec-256 \
    --server letsencrypt

# Deploy cert files to caddy/certs/
echo ""
echo "Deploying certs to ${CERT_DIR}..."
"$ACME_HOME/acme.sh" --install-cert \
    -d "*.${DOMAIN}" \
    --ecc \
    --cert-file      "${CERT_DIR}/cert.cer" \
    --key-file       "${CERT_DIR}/mai-tai.dev.key" \
    --fullchain-file "${CERT_DIR}/fullchain.cer" \
    --reloadcmd      "docker exec maitai-caddy caddy reload --config /etc/caddy/Caddyfile 2>/dev/null || true"

echo ""
echo "TLS setup complete!"
echo "  Certs: ${CERT_DIR}"
echo "  Auto-renewal: managed by acme.sh cron (check with: crontab -l)"
