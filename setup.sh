#!/usr/bin/env bash
set -eo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Simple elapsed timer
timer_start() { __T0=$(date +%s); }
timer_elapsed() {
  local d=$(( $(date +%s) - __T0 ))
  printf "%02d:%02d" $((d/60)) $((d%60))
}

show_help() {
  cat <<EOF
Usage: ./setup.sh [options]

Options:
  -k <key>    API key for your LLM provider
  -u <url>    Base URL (defaults to provider preset)
  -m <model>  Model name (defaults to provider preset)
  -c          Re-configure LLM only (interactive) — skip Docker steps
  -f          Fast mode: skip fancy output, print timestamps only
  -h          Show this help

Examples:
  ./setup.sh                                              # full setup
  ./setup.sh -k sk-xxx                                    # DeepSeek (default)
  ./setup.sh -k sk-xxx -u https://api.openai.com -m gpt-4o-mini
  ./setup.sh -c                                           # change LLM interactively
EOF
  exit 0
}

# Provider presets
declare -A PROVIDER_URL PROVIDER_MODEL
PROVIDER_URL["deepseek"]="https://api.deepseek.com"
PROVIDER_MODEL["deepseek"]="deepseek-chat"
PROVIDER_URL["openai"]="https://api.openai.com"
PROVIDER_MODEL["openai"]="gpt-4o-mini"
PROVIDER_URL["together"]="https://api.together.xyz"
PROVIDER_MODEL["together"]="mistralai/Mixtral-8x7B-Instruct-v0.1"
PROVIDER_URL["groq"]="https://api.groq.com/openai"
PROVIDER_MODEL["groq"]="llama3-70b-8192"
PROVIDER_URL["openrouter"]="https://openrouter.ai/api/v1"
PROVIDER_MODEL["openrouter"]="openai/gpt-4o-mini"
PROVIDER_URL["deepseekv4"]="https://api.deepseek.com/v1"
PROVIDER_MODEL["deepseekv4"]="deepseek-v4-flash"
PROVIDER_URL["openmodel"]="https://api.openmodel.ai"
PROVIDER_MODEL["openmodel"]="openai/gpt-4o"

# Parse flags
API_KEY=""
RECONFIGURE=0
while getopts "k:u:m:cfh" opt; do
  case "$opt" in
    k) API_KEY="$OPTARG" ;;
    u) BASE_URL="$OPTARG" ;;
    m) MODEL="$OPTARG" ;;
    c) RECONFIGURE=1 ;;
    f) FAST=1 ;;
    *) show_help ;;
  esac
done

info()  { echo -e "  ${CYAN}i${NC} $1"; }
good()  { echo -e "  ${GREEN}✓${NC} $1"; }
warn()  { echo -e "  ${YELLOW}w${NC} $1"; }
fail()  { echo -e "  ${RED}✗${NC} $1"; exit 1; }

# ── Interactive LLM configuration ──────────────────────────
configure_llm() {
  echo ""
  echo -e "${YELLOW}  LLM Configuration${NC}"
  echo ""

  # Load existing values if any
  local CURRENT_KEY CURRENT_URL CURRENT_MODEL
  CURRENT_KEY=$(grep -E "^LLM_API_KEY=.*" .env 2>/dev/null | cut -d= -f2- || true)
  CURRENT_URL=$(grep -E "^LLM_BASE_URL=.*" .env 2>/dev/null | cut -d= -f2- || true)
  CURRENT_MODEL=$(grep -E "^LLM_MODEL=.*" .env 2>/dev/null | cut -d= -f2- || true)

  if [ -n "$CURRENT_KEY" ]; then
    echo "  Current provider: ${CURRENT_MODEL:-unknown} @ ${CURRENT_URL:-unknown}"
    echo ""
    read -r -p "  Change LLM? (y/N): " CHANGE
    case "${CHANGE:-n}" in
      y|Y|yes|Yes) ;;
      *) good "Keeping existing LLM config"; return ;;
    esac
    echo ""
  fi

  echo "  RAG needs an LLM to understand your documents."
  echo "  Pick a provider or enter a custom endpoint:"
  echo ""
  echo -e "  ${CYAN}1${NC}) DeepSeek      — https://api.deepseek.com (deepseek-chat)"
  echo -e "  ${CYAN}2${NC}) DeepSeek V4  — https://api.deepseek.com/v1 (deepseek-v4-flash)"
  echo -e "  ${CYAN}3${NC}) OpenAI       — https://api.openai.com"
  echo -e "  ${CYAN}4${NC}) Together AI  — https://api.together.xyz"
  echo -e "  ${CYAN}5${NC}) Groq         — https://api.groq.com/openai"
  echo -e "  ${CYAN}6${NC}) OpenRouter   — https://openrouter.ai/api/v1"
  echo -e "  ${CYAN}7${NC}) OpenModel    — https://api.openmodel.ai (unified gateway)"
  echo -e "  ${CYAN}8${NC}) Custom URL   — enter your own"
  echo ""
  read -r -p "  Choose [1-8] (default: 1): " CHOICE

  local P
  case "${CHOICE:-1}" in
    1) P=deepseek;; 2) P=deepseekv4;; 3) P=openai;;
    4) P=together;; 5) P=groq;; 6) P=openrouter;;
    7) P=openmodel;; 8) P=custom;;
    *) P=deepseek;;
  esac

  if [ "$P" = custom ]; then
    read -r -p "  Enter Base URL: " BASE_URL
    read -r -p "  Enter Model name: " MODEL
  else
    BASE_URL="${PROVIDER_URL[$P]}"
    MODEL="${PROVIDER_MODEL[$P]}"
    echo "  Provider: ${P^}"
    echo "  URL:      $BASE_URL"
    echo "  Model:    $MODEL"
  fi

  echo ""
  read -r -p "  Enter API key (or press Enter to skip): " USER_KEY

  if [ -n "$USER_KEY" ]; then
    write_key "$USER_KEY" "$BASE_URL" "$MODEL"
    good "API key saved (base: $BASE_URL, model: $MODEL)"
  elif [ -n "$CURRENT_KEY" ] && [ -z "$USER_KEY" ]; then
    # Keep existing key, update URL/model only
    write_key "$CURRENT_KEY" "$BASE_URL" "$MODEL"
    good "URL and model updated (key kept unchanged)"
  else
    warn "No API key — RAG runs without AI answers (document search only)"
  fi
}

echo ""
echo -e "${CYAN}  RAG-CRM — One-command Setup${NC}"
echo ""

# ── Step 1: Prerequisites ─────────────────────────────────────

echo -e "${YELLOW}[1/5]${NC} Checking prerequisites..."

if ! command -v docker &>/dev/null; then
  fail "Docker is not installed. See https://docs.docker.com/engine/install/"
fi
good "$(docker --version)"

if ! docker compose version &>/dev/null; then
  fail "Docker Compose is not available. See https://docs.docker.com/compose/install/"
fi
good "$(docker compose version)"

# ── Step 2: Environment ───────────────────────────────────────

echo -e "\n${YELLOW}[2/5]${NC} Setting up environment..."

if [ ! -f .env ]; then
  cp .env.example .env 2>/dev/null || cat > .env <<-EOF
LLM_API_KEY=
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat
DATABASE_URL=postgresql+asyncpg://rag_user:rag_pass@localhost:5432/rag_crm
REDIS_URL=redis://localhost:6379/0
APP_NAME=RAG-CRM
APP_VERSION=0.1.0
LOG_LEVEL=INFO
EOF
  good "Created .env"
else
  good ".env already exists"
fi

# ── Step 3: LLM configuration ─────────────────────────────────

echo -e "\n${YELLOW}[3/5]${NC} Connecting a neural network (LLM)..."

# Reusable helpers
has_key() {
  local v
  v=$(grep -E "^${1}=.+" .env 2>/dev/null | cut -d= -f2- || true)
  [ -n "$v" ]
}

write_key() {
  local k="$1" u="$2" m="$3"
  sed -i "s|^LLM_API_KEY=.*|LLM_API_KEY=$k|" .env
  sed -i "s|^LLM_BASE_URL=.*|LLM_BASE_URL=$u|" .env
  sed -i "s|^LLM_MODEL=.*|LLM_MODEL=$m|" .env
  sed -i "s|^DEEPSEEK_API_KEY=.*|DEEPSEEK_API_KEY=$k|" .env 2>/dev/null || true
}

if [ "$RECONFIGURE" = 1 ]; then
  # -c flag: change LLM only, then exit
  configure_llm
  echo ""
  echo -e "${GREEN}  LLM updated. Re-run without -c to restart the stack.${NC}"
  echo ""
  exit 0

elif [ -n "$API_KEY" ]; then
  : "${BASE_URL:=https://api.deepseek.com}"
  : "${MODEL:=deepseek-chat}"
  write_key "$API_KEY" "$BASE_URL" "$MODEL"
  good "API key saved (base: $BASE_URL, model: $MODEL)"

elif has_key "LLM_API_KEY" || has_key "DEEPSEEK_API_KEY"; then
  good "API key found in .env"

else
  configure_llm
fi

# ── Step 4: Docker ────────────────────────────────────────────

echo -e "\n${YELLOW}[4/5]${NC} Starting Docker stack..."
cp .env infrastructure/.env 2>/dev/null || true

COMPOSE="docker compose -f infrastructure/docker-compose.yml"
COMPOSE_FILES="$COMPOSE"

timer_start
info "Pulling pre-built images..."
if timeout 45 $COMPOSE pull > /tmp/rag-pull.log 2>&1; then
  good "Images pulled [$(timer_elapsed)]"
else
  warn "Pull failed, building from source [$(timer_elapsed)]"
  timer_start
  info "Building images (may take 5-15 min first time)..."
  if timeout 600 $COMPOSE -f infrastructure/docker-compose.dev.yml build > /tmp/rag-build.log 2>&1; then
    good "Images built [$(timer_elapsed)]"
    COMPOSE_FILES="$COMPOSE -f infrastructure/docker-compose.dev.yml"
  else
    fail "Build failed! Check /tmp/rag-build.log"
  fi
fi

timer_start
info "Starting containers..."
if $COMPOSE_FILES up -d --wait --wait-timeout 300 > /tmp/rag-up.log 2>&1; then
  good "Containers started [$(timer_elapsed)]"
else
  fail "Containers failed! Check: $COMPOSE_FILES logs"
fi

# ── Step 5: Verify ────────────────────────────────────────────

echo -e "\n${YELLOW}[5/5]${NC} Verifying..."

echo -n "  Waiting for backend "
timer_start
OK=false
for i in $(seq 1 30); do
  if curl -sf http://localhost:8000/health/ready >/dev/null 2>&1; then
    OK=true
    echo -e "\r  ${GREEN}✓${NC} Backend ready! [$(timer_elapsed)]"
    break
  fi
  echo -n "."
  sleep 2
done
echo ""

if [ "$OK" = false ]; then
  warn "Backend not healthy after 60s — check: $COMPOSE_FILES logs backend"
fi

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  ✓ Setup complete!${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  Dashboard:  ${CYAN}http://localhost:8501${NC}"
echo -e "  API docs:   ${CYAN}http://localhost:8000/docs${NC}"
echo -e "  Metrics:    ${CYAN}http://localhost:9090${NC}"
echo ""
