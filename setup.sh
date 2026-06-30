#!/usr/bin/env bash
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ── Progress helpers ──────────────────────────────────────────
BAR_WIDTH=30

timer_start() {
  __RAG_TIMER=$(date +%s)
}

timer_elapsed() {
  local rag_now
  rag_now=$(date +%s)
  printf "%02d:%02d" $(( (rag_now - __RAG_TIMER) / 60 )) $(( (rag_now - __RAG_TIMER) % 60 ))
}

# Indeterminate spinner — wraps a background pid, shows elapsed
spinner() {
  local pid rag_pid rag_label rag_start rag_now rag_elapsed rag_i rag_rc
  rag_pid="$1"
  rag_label="$2"
  local spin='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
  rag_start=$(date +%s)
  rag_i=0
  while kill -0 "$rag_pid" 2>/dev/null; do
    rag_now=$(date +%s)
    rag_elapsed=$(( rag_now - rag_start ))
    printf "\r  ${YELLOW}%s${NC} %s  ${BLUE}[%02d:%02d]${NC}" "${spin:rag_i:1}" "$rag_label" $((rag_elapsed / 60)) $((rag_elapsed % 60))
    rag_i=$(( (rag_i + 1) % ${#spin} ))
    sleep 0.15
  done
  wait "$rag_pid"
  rag_rc=$?
  rag_now=$(date +%s)
  rag_elapsed=$(( rag_now - rag_start ))
  if [ "$rag_rc" -eq 0 ]; then
    printf "\r  ${GREEN}✓${NC} %s  ${BLUE}[%02d:%02d]${NC}\n" "$rag_label" $((rag_elapsed / 60)) $((rag_elapsed % 60))
  else
    printf "\r  ${RED}✗${NC} %s  ${BLUE}[%02d:%02d]${NC}\n" "$rag_label" $((rag_elapsed / 60)) $((rag_elapsed % 60))
  fi
  return "$rag_rc"
}

# Determinate progress bar — used inside a known-length loop
progress_bar() {
  local rag_cur rag_total rag_label rag_pct rag_fill rag_j rag_bar
  rag_cur="$1"
  rag_total="$2"
  rag_label="$3"
  rag_bar=""
  rag_pct=$(( rag_cur * 100 / rag_total ))
  rag_fill=$(( rag_cur * BAR_WIDTH / rag_total ))
  for ((rag_j=0; rag_j<rag_fill; rag_j++)); do rag_bar="${rag_bar}█"; done
  for ((rag_j=rag_fill; rag_j<BAR_WIDTH; rag_j++)); do rag_bar="${rag_bar}░"; done
  printf "\r  ${CYAN}%3d%%${NC} ${BLUE}%s${NC} [%s]" "$rag_pct" "$rag_label" "$rag_bar"
}

show_help() {
  cat <<EOF
Usage:  ./setup.sh [options]

Options:
  -k <key>    API key for your LLM provider
  -u <url>    Base URL (defaults to provider preset)
  -m <model>  Model name (defaults to provider preset)
  -h          Show this help

Examples:
  ./setup.sh                                              # interactive
  ./setup.sh -k sk-xxx                                    # DeepSeek (default)
  ./setup.sh -k sk-xxx -u https://api.openai.com -m gpt-4o-mini
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
API_KEY=''
while getopts "k:u:m:h" opt; do
  case "$opt" in
    k) API_KEY="$OPTARG" ;;
    u) BASE_URL="$OPTARG" ;;
    m) MODEL="$OPTARG" ;;
    *) show_help ;;
  esac
done

echo -e "${CYAN}"
echo -e "${CYAN}  RAG-CRM -- One-command Setup${NC}"
echo -e "${CYAN}"

echo -e "\n${YELLOW}[1/5]${NC} Checking prerequisites..."

if ! command -v docker &>/dev/null; then
  echo -e "${RED}X Docker is not installed.${NC}"
  echo "  Install: https://docs.docker.com/engine/install/"
  exit 1
fi
echo -e "  ${GREEN}Y${NC} Docker $(docker --version)"

if ! docker compose version &>/dev/null; then
  echo -e "${RED}X Docker Compose is not available.${NC}"
  echo "  Install: https://docs.docker.com/compose/install/"
  exit 1
fi
echo -e "  ${GREEN}Y${NC} Docker Compose $(docker compose version)"

echo -e "\n${YELLOW}[2/5]${NC} Setting up environment..."

if [ ! -f .env ]; then
  cp .env.example .env 2>/dev/null || cat > .env <<-ENVEOF
LLM_API_KEY=
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat
DATABASE_URL=postgresql+asyncpg://rag_user:rag_pass@localhost:5432/rag_crm
REDIS_URL=redis://localhost:6379/0
APP_NAME=RAG-CRM
APP_VERSION=0.1.0
LOG_LEVEL=INFO
ENVEOF
  echo -e "  ${GREEN}Y${NC} Created .env"
else
  echo -e "  ${GREEN}Y${NC} .env already exists"
fi

echo -e "\n${YELLOW}[3/5]${NC} Connecting a neural network (LLM)..."

has_key_value() {
  local rag_key_name rag_v
  rag_key_name="$1"
  rag_v=$(grep -E "^${rag_key_name}=.+" .env 2>/dev/null | cut -d= -f2- || true)
  [ -n "${rag_v:-}" ]
}

write_env() {
  local rag_key rag_url rag_model
  rag_key="$1"
  rag_url="$2"
  rag_model="$3"

  if [[ "${OSTYPE}" == "darwin"* ]]; then
    sed -i '' "s|^LLM_API_KEY=.*|LLM_API_KEY=$rag_key|" .env
    sed -i '' "s|^LLM_BASE_URL=.*|LLM_BASE_URL=$rag_url|" .env
    sed -i '' "s|^LLM_MODEL=.*|LLM_MODEL=$rag_model|" .env
    sed -i '' "s|^DEEPSEEK_API_KEY=.*|DEEPSEEK_API_KEY=$rag_key|" .env 2>/dev/null || true
  else
    sed -i "s|^LLM_API_KEY=.*|LLM_API_KEY=$rag_key|" .env
    sed -i "s|^LLM_BASE_URL=.*|LLM_BASE_URL=$rag_url|" .env
    sed -i "s|^LLM_MODEL=.*|LLM_MODEL=$rag_model|" .env
    sed -i "s|^DEEPSEEK_API_KEY=.*|DEEPSEEK_API_KEY=$rag_key|" .env 2>/dev/null || true
  fi
}

if [ -n "$API_KEY" ]; then
  [ -z "${BASE_URL:-}" ] && BASE_URL="https://api.deepseek.com"
  [ -z "${MODEL:-}" ] && MODEL="deepseek-chat"
  write_env "$API_KEY" "$BASE_URL" "$MODEL"
  echo -e "  ${GREEN}Y${NC} API key saved (base: $BASE_URL, model: $MODEL)"

elif has_key_value "LLM_API_KEY" || has_key_value "DEEPSEEK_API_KEY"; then
  echo -e "  ${GREEN}Y${NC} API key found in .env"

else
  # Interactive: choose provider
  echo "  RAG needs an LLM to understand your documents."
  echo "  Pick a provider or enter a custom endpoint:"
  echo ""
  echo -e "  ${CYAN}1${NC}) DeepSeek      -- https://api.deepseek.com (deepseek-chat)"
  echo -e "  ${CYAN}2${NC}) DeepSeek V4  -- https://api.deepseek.com/v1 (deepseek-v4-flash)"
  echo -e "  ${CYAN}3${NC}) OpenAI       -- https://api.openai.com"
  echo -e "  ${CYAN}4${NC}) Together AI  -- https://api.together.xyz"
  echo -e "  ${CYAN}5${NC}) Groq         -- https://api.groq.com/openai"
  echo -e "  ${CYAN}6${NC}) OpenRouter   -- https://openrouter.ai/api/v1"
  echo -e "  ${CYAN}7${NC}) OpenModel    -- https://api.openmodel.ai (unified gateway)"
  echo -e "  ${CYAN}8${NC}) Custom URL   -- enter your own"
  echo ""
  read -r -p "  Choose [1-8] (default: 1): " rag_provider_choice

  case "${rag_provider_choice:-1}" in
    1) PROVIDER="deepseek"    ;;
    2) PROVIDER="deepseekv4"  ;;
    3) PROVIDER="openai"      ;;
    4) PROVIDER="together"    ;;
    5) PROVIDER="groq"        ;;
    6) PROVIDER="openrouter"  ;;
    7) PROVIDER="openmodel"   ;;
    8) PROVIDER="custom"      ;;
    *) PROVIDER="deepseek"    ;;
  esac

  if [ "$PROVIDER" = "custom" ]; then
    read -r -p "  Enter Base URL (e.g. https://api.openai.com): " BASE_URL
    read -r -p "  Enter Model name (e.g. gpt-4o-mini): " MODEL
  else
    BASE_URL="${PROVIDER_URL[$PROVIDER]}"
    MODEL="${PROVIDER_MODEL[$PROVIDER]}"
    echo "  Provider: ${PROVIDER^}"
    echo "  URL:      $BASE_URL"
    echo "  Model:    $MODEL"
  fi

  echo ""
  read -r -p "  Paste your API key (or press Enter to skip): " rag_user_key

  if [ -n "$rag_user_key" ]; then
    write_env "$rag_user_key" "$BASE_URL" "$MODEL"
    echo -e "  ${GREEN}Y${NC} API key saved"
  else
    echo -e "  ${YELLOW}W${NC} Skipped -- RAG will run without AI answers (document search only)"
  fi
fi

# ── Step 4: Docker ────────────────────────────────────────────

echo -e "\n${YELLOW}[4/5]${NC} Starting Docker stack..."
cp .env infrastructure/.env 2>/dev/null || true

COMPOSE_FILES="-f infrastructure/docker-compose.yml"

# Try to pull pre-built images (fast). On failure → build locally.
echo -e "  ${CYAN}i${NC} Checking for pre-built images..."
timer_start
if timeout 45 docker compose -f infrastructure/docker-compose.yml pull > /tmp/rag-pull.log 2>&1; then
  echo -e "  ${GREEN}✓${NC} Pre-built images pulled  ${BLUE}[$(timer_elapsed)]${NC}"
else
  echo -e "  ${YELLOW}⌛${NC} Pre-built pull failed  ${BLUE}[$(timer_elapsed)]${NC}"
  echo -e "  ${CYAN}i${NC} Building images from source (5-15 min first time)..."
  timer_start
  if timeout 600 docker compose -f infrastructure/docker-compose.yml -f infrastructure/docker-compose.dev.yml build > /tmp/rag-build.log 2>&1; then
    echo -e "  ${GREEN}✓${NC} Images built from source  ${BLUE}[$(timer_elapsed)]${NC}"
    COMPOSE_FILES="-f infrastructure/docker-compose.yml -f infrastructure/docker-compose.dev.yml"
  else
    echo -e "  ${RED}✗${NC} Build failed! Check /tmp/rag-build.log"
    exit 1
  fi
fi

echo -e "  ${CYAN}i${NC} Starting containers..."
timer_start
if docker compose $COMPOSE_FILES up -d --wait --wait-timeout 300 > /tmp/rag-up.log 2>&1; then
  echo -e "  ${GREEN}✓${NC} Containers started  ${BLUE}[$(timer_elapsed)]${NC}"
else
  echo -e "  ${RED}✗${NC} Failed to start containers! Check: docker compose $COMPOSE_FILES logs"
  exit 1
fi

echo -e "  ${GREEN}Y${NC} Stack started"

# ── Step 5: Verify ────────────────────────────────────────────

echo -e "\n${YELLOW}[5/5]${NC} Verifying..."

MAX_RETRIES=30
BACKEND_OK=false
timer_start
for rag_i in $(seq 1 "$MAX_RETRIES"); do
  progress_bar "$rag_i" "$MAX_RETRIES" "Waiting for backend  [$(timer_elapsed)]"
  if curl -sf http://localhost:8000/health/ready >/dev/null 2>&1; then
    BACKEND_OK=true
    progress_bar "$MAX_RETRIES" "$MAX_RETRIES" "Backend ready!       [$(timer_elapsed)]"
    echo ""
    break
  fi
  sleep 2
done
echo ""

echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  Y Setup complete!${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  Dashboard:  ${CYAN}http://localhost:8501${NC}"
echo -e "  API docs:   ${CYAN}http://localhost:8000/docs${NC}"
echo -e "  Metrics:    ${CYAN}http://localhost:9090${NC}"
echo ""

if [ "$BACKEND_OK" = false ]; then
  echo -e "  ${YELLOW}W${NC} Backend not yet healthy -- check: docker compose $COMPOSE_FILES logs backend"
fi
