#!/usr/bin/env bash
# ────────────────────────────────────────────────────────────────
# init-letsencrypt.sh — First-time Let's Encrypt certificate setup
# ────────────────────────────────────────────────────────────────
# Run this once to obtain your initial SSL certificate before
# starting the full production stack.
#
# Prerequisites:
#   1. DNS A record pointing ${DOMAIN} to this server's public IP
#   2. Ports 80 and 443 open on firewall
#   3. DOMAIN and CERTBOT_EMAIL set in infrastructure/.env
#
# Usage:
#   cd infrastructure
#   ./init-letsencrypt.sh            # production certificate
#   ./init-letsencrypt.sh --staging  # test with Let's Encrypt staging
#
# After this script succeeds, start the production stack:
#   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
# ────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Load environment ────────────────────────────────────────────
if [ ! -f .env ]; then
    echo "ERROR: infrastructure/.env file not found."
    echo "Create it with at least DOMAIN and CERTBOT_EMAIL:"
    echo "  DOMAIN=rag-crm.example.com"
    echo "  CERTBOT_EMAIL=admin@example.com"
    exit 1
fi
set -a; source .env; set +a

# ── Argument parsing ────────────────────────────────────────────
STAGING=0
if [ "${1:-}" = "--staging" ]; then
    STAGING=1
    echo "=== USING LET'S ENCRYPT STAGING (test certificates) ==="
fi

# ── Validate required env vars ──────────────────────────────────
DOMAIN="${DOMAIN:-}"
CERTBOT_EMAIL="${CERTBOT_EMAIL:-}"

if [ -z "$DOMAIN" ]; then
    echo "ERROR: DOMAIN is not set in infrastructure/.env"
    echo "Add: DOMAIN=rag-crm.example.com"
    exit 1
fi

if [ -z "$CERTBOT_EMAIL" ]; then
    echo "ERROR: CERTBOT_EMAIL is not set in infrastructure/.env"
    echo "Add: CERTBOT_EMAIL=admin@example.com"
    exit 1
fi

echo "Domain:          $DOMAIN"
echo "Email:           $CERTBOT_EMAIL"
echo ""

# ── Create required directories ─────────────────────────────────
mkdir -p ./certbot/www
mkdir -p ./certbot/conf/live/"$DOMAIN"
mkdir -p ./nginx/conf.d

# ── Generate dummy (self-signed) certificate ────────────────────
# nginx needs a certificate to start on port 443.
# We create a self-signed placeholder, start nginx, then replace
# it with the real Let's Encrypt certificate.
echo "=== Generating placeholder self-signed certificate ==="
openssl req -x509 -nodes -newkey rsa:4096 \
    -days 1 \
    -keyout ./certbot/conf/live/"$DOMAIN"/privkey.pem \
    -out ./certbot/conf/live/"$DOMAIN"/fullchain.pem \
    -subj "/CN=${DOMAIN}" \
    2>/dev/null
echo "Placeholder certificate created."

# ── Generate nginx conf from template ───────────────────────────
# Substitute ${DOMAIN} into the nginx template
DOMAIN="$DOMAIN" envsubst '$DOMAIN' \
    < ./nginx/conf.d/app.conf.template \
    > ./nginx/conf.d/app.conf
echo "nginx configuration generated for ${DOMAIN}."

# ── Start nginx with dummy certificate ──────────────────────────
echo ""
echo "=== Starting temporary nginx (dummy cert) ==="
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
    up -d --force-recreate nginx 2>&1

# Wait for nginx to be healthy
# Use HTTPS with --no-check-certificate (dummy cert is self-signed)
echo "Waiting for nginx to start..."
for i in $(seq 1 30); do
    if docker compose -f docker-compose.yml -f docker-compose.prod.yml \
        exec -T nginx wget -q --spider --no-check-certificate https://localhost/health/ready 2>/dev/null; then
        echo "nginx is healthy."
        break
    fi
    sleep 2
done

# ── Delete dummy certificate ────────────────────────────────────
echo ""
echo "=== Removing placeholder certificate ==="
rm -rf ./certbot/conf/live/"$DOMAIN"/*

# ── Request real Let's Encrypt certificate ──────────────────────
echo ""
echo "=== Requesting Let's Encrypt certificate for ${DOMAIN} ==="

CERTBOT_ARGS=(
    certonly
    --webroot
    -w /var/www/certbot
    --email "$CERTBOT_EMAIL"
    --domain "$DOMAIN"
    --agree-tos
    --non-interactive
    --force-renewal
)

if [ "$STAGING" -eq 1 ]; then
    CERTBOT_ARGS+=(--staging)
fi

docker compose -f docker-compose.yml -f docker-compose.prod.yml \
    run --rm \
    --entrypoint "certbot" \
    certbot "${CERTBOT_ARGS[@]}"

echo ""
echo "=== Certificate obtained successfully! ==="

# ── Reload nginx to pick up real certificate ────────────────────
echo "Reloading nginx with real certificate..."
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
    exec -T nginx nginx -s reload 2>/dev/null || \
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
    restart nginx

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  Let's Encrypt certificate installed for ${DOMAIN}"
echo "  Auto-renewal: certbot container runs 'certbot renew' every 12h"
echo "  nginx reloads every 6h to pick up renewed certificates"
echo ""
echo "  Start the full production stack:"
echo "    docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d"
echo "═══════════════════════════════════════════════════════════════"
