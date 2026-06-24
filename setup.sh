#!/usr/bin/env bash
set -euo pipefail

# ──────────────────────────────────────────────
# RAG-CRM — One-command setup
# ──────────────────────────────────────────────

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

show_help() {
  cat <<EOF
Usage:  ./setup.sh [-k <api_key>] [-h]

  -k <api_key>   DeepSeek API key (skip to be prompted interactively)
  -h             Show this help

Example:
  ./setup.sh -k sk-your-key-here
EOF
  exit 0
}

# ── Parse flags ──
API_KEY=""
while getopts "k:h" opt; do
  case "$opt" in
    k) API_KEY="$OPTARG" ;;
    h) show_help ;;
    *) show_help ;;
  esac
done

echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}  RAG-CRM — One-command Setup${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# ── 1. Check prerequisites ──
echo -e "\n${YELLOW}[1/5]${NC} Checking prerequisites..."

if ! command -v docker &>/dev/null; then
  echo -e "${RED}✗ Docker is not installed.${NC}"
  echo "  Install: https://docs.docker.com/engine/install/"
  exit 1
fi
echo -e "  ${GREEN}✓${NC} Docker $(docker --version)"

if ! docker compose version &>/dev/null; then
  echo -e "${RED}✗ Docker Compose is not available.${NC}"
  echo "  Install: https://docs.docker.com/compose/install/"
  exit 1
fi
echo -e "  ${GREEN}✓${NC} Docker Compose $(docker compose version 2>/dev/null | head -1)"

# ── 2. Environment file ──
echo -e "\n${YELLOW}[2/5]${NC} Setting up environment..."

if [ ! -f .env ]; then
  cp .env.example .env 2>/dev/null || cat > .env <<-ENVEOF
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DATABASE_URL=postgresql+asyncpg://rag_user:rag_pass@localhost:5432/rag_crm
REDIS_URL=redis://localhost:6379/0
APP_NAME=RAG-CRM
APP_VERSION=0.1.0
LOG_LEVEL=INFO
ENVEOF
  echo -e "  ${GREEN}✓${NC} Created .env"
else
  echo -e "  ${GREEN}✓${NC} .env already exists"
fi

# ── 3. API key ──
echo -e "\n${YELLOW}[3/5]${NC} Connecting a neural network (LLM)..."

has_key() {
  # returns 0 if DEEPSEEK_API_KEY has a non-empty value
  grep -qE '^DEEPSEEK_API_KEY=[^"'"'"']+$' .env 2>/dev/null && return 0
  grep -q '^DEEPSEEK_API_KEY=...' .env 2>/dev/null && return 0
  return 1
}

if [ -n "$API_KEY" ]; then
  # Key from -k flag
  if [[ "$OSTYPE" == "darwin"* ]]; then
    sed -i '' "s/^DEEPSEEK_API_KEY=.*/DEEPSEEK_API_KEY=$API_KEY/" .env
  else
    sed -i "s/^DEEPSEEK_API_KEY=.*/DEEPSEEK_API_KEY=$API_KEY/" .env
  fi
  echo -e "  ${GREEN}✓${NC} API key saved from -k flag"

elif has_key; then
  echo -e "  ${GREEN}✓${NC} API key found in .env"

else
  echo -e "  ${YELLOW}╔══════════════════════════════════════════════╗${NC}"
  echo -e "  ${YELLOW}║  RAG needs a neural network to understand    ║${NC}"
  echo -e "  ${YELLOW}║  your documents and answer your questions.   ║${NC}"
  echo -e "  ${YELLOW}║                                              ║${NC}"
  echo -e "  ${YELLOW}║  Get a free key at:                          ║${NC}"
  echo -e "  ${YELLOW}║  https://platform.deepseek.com/api_keys      ║${NC}"
  echo -e "  ${YELLOW}╚══════════════════════════════════════════════╝${NC}"
  read -r -p "  Paste your DeepSeek API key (or press Enter to skip): " user_key
  if [ -n "$user_key" ]; then
    if [[ "$OSTYPE" == "darwin"* ]]; then
      sed -i '' "s/^DEEPSEEK_API_KEY=.*/DEEPSEEK_API_KEY=$user_key/" .env
    else
      sed -i "s/^DEEPSEEK_API_KEY=.*/DEEPSEEK_API_KEY=$user_key/" .env
    fi
    echo -e "  ${GREEN}✓${NC} API key saved"
  else
    echo -e "  ${YELLOW}⚠${NC} Skipped — RAG will run without AI answers (document search only)"
  fi
fi

# ── 4. Start Docker stack ──
echo -e "\n${YELLOW}[4/5]${NC} Starting Docker stack..."
cp .env infrastructure/.env 2>/dev/null || true

docker compose -f infrastructure/docker-compose.yml up -d --wait --wait-timeout 120 2>&1 || \
  docker compose -f infrastructure/docker-compose.yml up -d 2>&1

echo -e "  ${GREEN}✓${NC} Stack started"

# ── 5. Verify ──
echo -e "\n${YELLOW}[5/5]${NC} Verifying..."

MAX_RETRIES=30
BACKEND_OK=false
for i in $(seq 1 "$MAX_RETRIES"); do
  if curl -sf http://localhost:8000/health/ready >/dev/null 2>&1; then
    BACKEND_OK=true
    break
  fi
  sleep 2
done

echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  ✓ Setup complete!${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  Dashboard:  ${CYAN}http://localhost:8501${NC}"
echo -e "  API docs:   ${CYAN}http://localhost:8000/docs${NC}"
echo ""

if [ "$BACKEND_OK" = false ]; then
  echo -e "  ${YELLOW}⚠${NC} Backend not yet healthy — check: docker compose -f infrastructure/docker-compose.yml logs backend"
fi
