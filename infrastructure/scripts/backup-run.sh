#!/usr/bin/env bash
#
# APP-177: Host wrapper — runs backup inside the PostgreSQL container.
#
# Usage:
#   ./backup-run.sh                     # Run full backup via container
#   BACKUP_KEEP=14 ./backup-run.sh      # Keep 14 backups
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="${INFRA_DIR}/docker-compose.yml"

echo "=== RAG-CRM PostgreSQL Backup ==="
echo "Timestamp: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"

cd "${INFRA_DIR}"
docker compose -f "${COMPOSE_FILE}" exec -T postgres     env PGHOST=localhost PGUSER="${PGUSER:-rag_user}" PGPASSWORD="${PGPASSWORD:-rag_pass}"         PGDATABASE="${PGDATABASE:-rag_crm}" BACKUP_DIR=/backups BACKUP_KEEP="${BACKUP_KEEP:-7}"     bash /scripts/backup.sh /backups
EXIT_CODE=$?
if [ $EXIT_CODE -eq 0 ]; then
    echo "Backup completed successfully."
else
    echo "Backup FAILED (exit $EXIT_CODE)" >&2
fi
exit $EXIT_CODE
