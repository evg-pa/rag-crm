#!/usr/bin/env bash
# ── RAG-CRM Frontend Test Runner ──────────────────────────────
# Usage:
#   ./run_tests.sh              # Run all frontend tests
#   ./run_tests.sh apptest      # Streamlit AppTest only (container)
#   ./run_tests.sh e2e          # Playwright E2E only (host)
#   ./run_tests.sh backend      # Run backend tests (container)
# ──────────────────────────────────────────────────────────────

set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'

mode="${1:-all}"

case "$mode" in
  apptest)
    echo -e "${CYAN}▶ Running Streamlit AppTest (in container)...${NC}"
    docker exec rag-frontend python -m pytest /app/tests/ \
      --tb=short -v --ignore=/app/tests/e2e
    ;;

  e2e)
    echo -e "${CYAN}▶ Running Playwright E2E (from host)...${NC}"
    cd "$DIR" && python -m pytest tests/e2e/ \
      --tb=short -v --rootdir=.
    ;;

  backend)
    echo -e "${CYAN}▶ Running backend tests (in container)...${NC}"
    docker exec rag-backend python -m pytest \
      --tb=short -v 2>&1 | tail -20
    ;;

  all|*)
    echo -e "${CYAN}▶ 1/4: Syncing test files to container...${NC}"
    docker cp "$DIR/tests/" rag-frontend:/app/tests/

    echo -e "${CYAN}▶ 2/4: Streamlit AppTest (container)...${NC}"
    docker exec rag-frontend python -m pytest /app/tests/ \
      --tb=short -v --ignore=/app/tests/e2e

    echo -e "\n${CYAN}▶ 3/4: Playwright E2E (host)...${NC}"
    cd "$DIR" && python -m pytest tests/e2e/ \
      --tb=short -v --rootdir=.

    echo -e "\n${CYAN}▶ 4/4: Backend tests (container)...${NC}"
    docker exec rag-backend python -m pytest \
      --tb=short -q 2>&1 | tail -10

    echo -e "\n${GREEN}✅ All frontend test suites completed.${NC}"
    ;;
esac
