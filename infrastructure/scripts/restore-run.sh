#!/usr/bin/env bash
#
# APP-177: Host wrapper — runs restore via PostgreSQL container.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="${INFRA_DIR}/docker-compose.yml"
cd "${INFRA_DIR}"

case "${1:-}" in
    --list|-l)
        echo "=== Available Backups ==="
        docker compose -f "${COMPOSE_FILE}" exec -T postgres env BACKUP_DIR=/backups bash /scripts/restore.sh --list
        ;;
    *)
        [ $# -eq 0 ] && { echo "Usage: $0 [--list | --latest | <backup-path>]"; exit 1; }
        echo "=== RAG-CRM PostgreSQL Restore ==="
        docker compose -f "${COMPOSE_FILE}" exec -T postgres             env PGHOST=localhost PGUSER="${PGUSER:-rag_user}" PGPASSWORD="${PGPASSWORD:-rag_pass}"                 PGDATABASE="${PGDATABASE:-rag_crm}" BACKUP_DIR=/backups             bash /scripts/restore.sh "$@"
        ;;
esac
