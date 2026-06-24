#!/usr/bin/env bash
set -euo pipefail

# ──────────────────────────────────────────────
# RAG-CRM — One-command setup
# ──────────────────────────────────────────────

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${CYAN}  RAG-CRM — One-command Setup${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# ── 1. Check prerequisites ──
echo -e "\n${YELLOW}[1/5]${NC} Checking prerequisites..."

if ! command -v docker &>/dev/null; then
  echo -e "${RED}✗ Docker is not installed.${NC}"
  echo "  Install it first: https://docs.docker.com/engine/install/"
  exit 1
fi
echo -e "  ${GREEN}✓${NC} Docker $(docker --version)"

if ! docker compose version &>/dev/null; then
  echo -e "${RED}✗ Docker Compose is not available.${NC}"
  echo "  Install it first: https://docs.docker.com/compose/install/"
  exit 1
fi
echo -e "  ${GREEN}✓${NC} Docker Compose $(docker compose version 2>/dev/null | head -1)"

# ── 2. Environment file ──
echo -e "\n${YELLOW}[2/5]${NC} Setting up environment..."

if [ ! -f .env ]; then
  if [ -f .env.example ]; then
    cp .env.example .env
    echo -e "  ${GREEN}✓${NC} Created .env from .env.example"
  else
    echo -e "  ${YELLOW}⚠${NC} No .env.example found, creating minimal .env"
    cat > .env <<-EOF
DEEPSEEK_API_KEY=
EOF
  fi
else
  echo -e "  ${GREEN}✓${NC} .env already exists"
fi

# ── 3. DEEPSEEK_API_KEY ──
echo -e "\n${YELLOW}[3/5]${NC} Checking API key..."

if grep -q 'DEEPSEEK_API_KEY=""' .env 2>/dev/null || \
   grep -q 'DEEPSEEK_API_KEY=$' .env 2>/dev/null || \
   ! grep -q 'DEEPSEEK_API_KEY=' .env 2>/dev/null; then
  echo -e "  ${YELLOW}⚠${NC} DEEPSEEK_API_KEY is not set."
  read -r -p "  Enter your DeepSeek API key (or press Enter to skip): " user_key
  if [ -n "$user_key" ]; then
    if [[ "$OSTYPE" == "darwin"* ]]; then
      sed -i '' "s/DEEPSEEK_API_KEY=.*/DEEPSEEK_API_KEY=$user_key/" .env
    else
      sed -i "s/DEEPSEEK_API_KEY=.*/DEEPSEEK_API_KEY=$user_key/" .env
    fi
    echo -e "  ${GREEN}✓${NC} DEEPSEEK_API_KEY saved to .env"
  else
    echo -e "  ${YELLOW}⚠${NC} Skipping — LLM answers will use fallback mode (raw chunks only)"
  fi
else
  echo -e "  ${GREEN}✓${NC} DEEPSEEK_API_KEY is configured"
fi

# ── 4. Start Docker stack ──
echo -e "\n${YELLOW}[4/5]${NC} Starting Docker stack..."

# Copy .env to infrastructure/ so docker compose can pick it up
cp .env infrastructure/.env 2>/dev/null || true

docker compose -f infrastructure/docker-compose.yml up -d --wait --wait-timeout 120 2>&1 || \
  docker compose -f infrastructure/docker-compose.yml up -d 2>&1

echo -e "  ${GREEN}✓${NC} Stack started"

# ── 5. Verify ──
echo -e "\n${YELLOW}[5/5]${NC} Verifying..."

MAX_RETRIES=30
RETRY_INTERVAL=2
BACKEND_OK=false

for i in $(seq 1 "$MAX_RETRIES"); do
  if curl -sf http://localhost:8000/health/ready >/dev/null 2>&1; then
    BACKEND_OK=true
    break
  fi
  sleep "$RETRY_INTERVAL"
done

if [ "$BACKEND_OK" = true ]; then
  echo -e "  ${GREEN}✓${NC} Backend ready at http://localhost:8000"
  echo -e "  ${GREEN}✓${NC} API docs at http://localhost:8000/docs"
  echo -e "  ${GREEN}✓${NC} Dashboard at http://localhost:8501"
else
  echo -e "  ${YELLOW}⚠${NC} Backend not yet healthy — check logs: docker compose -f infrastructure/docker-compose.yml logs backend"
fi

# ── Done ──
echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  Setup complete!${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  Dashboard:  ${CYAN}http://localhost:8501${NC}"
echo -e "  API docs:   ${CYAN}http://localhost:8000/docs${NC}"
echo -e "  Health:     ${CYAN}http://localhost:8000/health/ready${NC}"
echo ""
