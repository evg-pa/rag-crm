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
  __timer_start=$(date +%s)
}

timer_elapsed() {
  local elapsed=$(( $(date +%s) - __timer_start ))
  printf "%02d:%02d" $((elapsed / 60)) $((elapsed % 60))
}

# Indeterminate spinner — wraps a background pid, shows elapsed
spinner() {
  local pid=$1 label="$2" rc
  local spin='⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏'
  local start=$(date +%s) i=0
  while kill -0 "$pid" 2>/dev/null; do
    local elapsed elapsed=$(( $(date +%s) - start ))
    printf "\r  ${YELLOW}%s${NC} %s  ${BLUE}[%02d:%02d]${NC}" "${spin:$i:1}" "$label" $((elapsed / 60)) $((elapsed % 60))
    i=$(( (i + 1) % ${#spin} ))
    sleep 0.15
  done
  wait "$pid"; rc=$?
  local elapsed=$(( $(date +%s) - start ))
  if [ $rc -eq 0 ]; then
    printf "\r  ${GREEN}✓${NC} %s  ${BLUE}[%02d:%02d]${NC}\n" "$label" $((elapsed / 60)) $((elapsed % 60))
  else
    printf "\r  ${RED}✗${NC} %s  ${BLUE}[%02d:%02d]${NC}\n" "$label" $((elapsed / 60)) $((elapsed % 60))
  fi
  return $rc
}

# Determinate progress bar — used inside a known-length loop
progress_bar() {
  local cur=$1 total=$2 label="$3"
  local pct=$(( cur * 100 / total ))
  local fill=$(( cur * BAR_WIDTH / total ))
  local bar=""
  for ((j=0; j<fill; j++)); do bar="${bar}█"; done
  for ((j=fill; j<BAR_WIDTH; j++)); do bar="${bar}░"; done
  printf "\r  ${CYAN}%3d%%${NC} ${BLUE}%s${NC} [%s]" "$pct" "$label" "$bar"
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

echo -e "${CYAN}
echo -e "${CYAN}  RAG-CRM -- One-command Setup${NC}"
echo -e "${CYAN}

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
  local key_name="$1"
  # shellcheck disable=SC2016
  v=$(grep -E "^${key_name}=.+" .env 2>/dev/null | cut -d= -f2-)
  [ -n "$v" ]
}

write_env() {
  local key="$1" url="$2" model="$3"

  if [[ "$${OSTYPE}" == "darwin"* ]]; then
    sed -i '' 's|^LLM_API_KEY=.*|LLM_API_KEY=$key|' .env
    sed -i "s|^LLM_BASE_URL=.*|LLM_BASE_URL=$url|" .env
    sed -i "s|^LLM_MODEL=.*|LLM_MODEL=$model|" .env
    sed -i ' s|^DEEPSEEK_API_KEY=.*|DEEPSEEK_API_KEY=$key| ' .env 2>/dev/null || true
  else
    sed -i 's|^LLM_API_KEY=.*|LLM_API_KEY=$key|' .env
    sed -i "s|^LLM_BASE_URL=.*|LLM_BASE_URL=$url|" .env
    sed -i "s|^LLM_MODEL=.*|LLM_MODEL=$model|" .env
    sed -i ' s|^DEEPSEEK_API_KEY=.*|DEEPSEEK_API_KEY=$key| ' .env 2>/dev/null || true
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
  read -r -p "  Choose [1-8] (default: 1): " provider_choice

  case "${provider_choice:-1}" in
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
  read -r -p "  Paste your API key (or press Enter to skip): " user_key

  if [ -n "$user_key" ]; then
    write_env "$user_key" "$BASE_URL" "$MODEL"
    echo -e "  ${GREEN}Y${NC} API key saved"
  else
    echo -e "  ${YELLOW}W${NC} Skipped -- RAG will run without AI answers (document search only)"
  fi
fi

echo -e "\\n${YELLOW}[4/5]${NC} Starting Docker stack..."
cp .env infrastructure/.env 2>/dev/null || true

# Pull pre-built images (fast!) — fall back to local build if pull fails
timer_start
docker compose -f infrastructure/docker-compose.yml pull > /tmp/rag-pull.log 2>&1 &
spinner $! "Pulling pre-built images..." || \
  echo -e "  ${YELLOW}Image pull failed — will build locally (takes 5-15 min)${NC}"

# Start the stack
timer_start
docker compose -f infrastructure/docker-compose.yml up -d --wait --wait-timeout 180 > /tmp/rag-up.log 2>&1 &
spinner $! "Starting containers (waiting for healthy)..."

echo -e "  ${GREEN}Y${NC} Stack started"

echo -e "\\n${YELLOW}[5/5]${NC} Verifying..."

MAX_RETRIES=30
BACKEND_OK=false
timer_start
for i in $(seq 1 "$MAX_RETRIES"); do
  elapsed=$(timer_elapsed)
  progress_bar "$i" "$MAX_RETRIES" "Waiting for backend  [${elapsed}]"
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
  echo -e "  ${YELLOW}W${NC} Backend not yet healthy -- check: docker compose -f infrastructure/docker-compose.yml logs backend"
fi
