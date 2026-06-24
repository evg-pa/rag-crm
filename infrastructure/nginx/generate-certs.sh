#!/usr/bin/env bash
set -euo pipefail

# ── generate-certs.sh ─────────────────────────────────────────────────
# Generate self-signed certificate for local development / testing with
# the Docker production override (no real domain required).
#
# Usage:
#   cd infrastructure
#   ./nginx/generate-certs.sh [domain]
#
# Default domain: localhost
#
# This creates:
#   certbot/conf/live/<domain>/fullchain.pem
#   certbot/conf/live/<domain>/privkey.pem
#   certbot/conf/live/<domain>/chain.pem
#   nginx/conf.d/app.conf (generated from template)
#
# Then start with:
#   DOMAIN=<domain> docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
#
# ⚠️  Browsers will show a certificate warning for self-signed certs.
#     For production, use init-letsencrypt.sh with a real domain instead.
# ──────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(dirname "$SCRIPT_DIR")"
DOMAIN="${1:-localhost}"

echo "=== Generating self-signed certificate for ${DOMAIN} ==="

# ── Create cert directories ──────────────────────────────────────────
mkdir -p "$INFRA_DIR/certbot/conf/live/$DOMAIN"
mkdir -p "$INFRA_DIR/certbot/www"

# ── Generate self-signed cert (don't overwrite real certs) ───────────
CERT_FILE="$INFRA_DIR/certbot/conf/live/$DOMAIN/fullchain.pem"
KEY_FILE="$INFRA_DIR/certbot/conf/live/$DOMAIN/privkey.pem"

if [ -f "$CERT_FILE" ] && [ -f "$KEY_FILE" ]; then
    echo "Certs already exist at certbot/conf/live/${DOMAIN}/"
    echo "Remove them manually if you want to regenerate."
else
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout "$KEY_FILE" \
        -out    "$CERT_FILE" \
        -subj   "/CN=${DOMAIN}" 2>/dev/null
    cp "$CERT_FILE" "$INFRA_DIR/certbot/conf/live/$DOMAIN/chain.pem"
    chmod 600 "$KEY_FILE"
    chmod 644 "$CERT_FILE"
    echo "✓ Self-signed certs generated."
fi

# ── Generate nginx config from template ──────────────────────────────
DOMAIN="$DOMAIN" envsubst '$DOMAIN' \
    < "$INFRA_DIR/nginx/conf.d/app.conf.template" \
    > "$INFRA_DIR/nginx/conf.d/app.conf"
echo "✓ nginx config generated for ${DOMAIN}."

echo ""
echo "═══════════════════════════════════════════════════════════════════"
echo "  Self-signed certs ready for ${DOMAIN}"
echo ""
echo "  Start the stack with HTTPS:"
echo "    cd infrastructure"
echo "    DOMAIN=${DOMAIN} docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d"
echo ""
echo "  ⚠️  Self-signed certs will trigger browser warnings."
echo "     For production, use init-letsencrypt.sh instead."
echo "═══════════════════════════════════════════════════════════════════"
