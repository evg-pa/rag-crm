#!/usr/bin/env bash
#
# APP-177: Cron wrapper for PostgreSQL backup with monitoring
#
# Runs backup via docker exec into postgres container.
# Reports status via health file for monitoring.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="${INFRA_DIR}/docker-compose.yml"
BACKUP_DIR="${SCRIPT_DIR}/backups"
mkdir -p "${BACKUP_DIR}"

LOG_FILE="${BACKUP_DIR}/backup.log"
log_msg() { echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] $*" | tee -a "${LOG_FILE}"; }

log_msg "=== Backup cron started ==="

cd "${INFRA_DIR}"
if docker compose -f "${COMPOSE_FILE}" exec -T postgres     env PGHOST=localhost PGUSER="${PGUSER:-rag_user}" PGPASSWORD="${PGPASSWORD:-rag_pass}"         PGDATABASE="${PGDATABASE:-rag_crm}" BACKUP_DIR=/backups BACKUP_KEEP="${BACKUP_KEEP:-7}"     bash /scripts/backup.sh /backups 2>&1 | tee -a "${LOG_FILE}"; then
    STATUS=OK
    EXIT_CODE=0
else
    STATUS=FAILED
    EXIT_CODE=$?
fi

echo "${STATUS} $(date -u +"%Y%m%dT%H%M%SZ")" > "${BACKUP_DIR}/.last_backup_status"

LATEST=$(find "${BACKUP_DIR}" -maxdepth 1 -name 'rag_crm_*.dump' -type f | sort -r | head -n 1)
COUNT=$(find "${BACKUP_DIR}" -maxdepth 1 -name 'rag_crm_*.dump' -type f | wc -l)
log_msg "Backup cron done: status=${STATUS}, count=${COUNT}, latest=${LATEST:-none}"

exit ${EXIT_CODE}
