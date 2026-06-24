#!/usr/bin/env bash
#
# APP-177: PostgreSQL restore script for RAG-CRM
#
# Usage:
#   ./restore.sh /path/to/backup.dump    # Restore specific backup
#   ./restore.sh --latest                 # Restore latest backup
#   ./restore.sh --list                   # List available backups

set -euo pipefail

PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-rag_user}"
PGDATABASE="${PGDATABASE:-rag_crm}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"

export PGHOST PGUSER PGPORT PGDATABASE
[ -n "${PGPASSWORD:-}" ] && export PGPASSWORD

log() { echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] $*"; }

list_backups() {
    if [ ! -d "${BACKUP_DIR}" ]; then
        echo "No backup directory: ${BACKUP_DIR}"
        exit 1
    fi
    echo "Available backups in ${BACKUP_DIR}:"
    find "${BACKUP_DIR}" -maxdepth 1 -name 'rag_crm_*.dump' -type f | sort -r | while read -r f; do
        SIZE=$(du -h "$f" | cut -f1)
        echo "  $(basename "$f")  ${SIZE}"
    done
}

BACKUP_FILE=""
case "${1:-}" in
    --list|-l) list_backups; exit 0 ;;
    --latest|-L)
        BACKUP_FILE=$(find "${BACKUP_DIR}" -maxdepth 1 -name 'rag_crm_*.dump' -type f | sort -r | head -n 1)
        [ -z "${BACKUP_FILE}" ] && { log "ERROR: No backups in ${BACKUP_DIR}"; exit 1; }
        log "Latest backup: ${BACKUP_FILE}" ;;
    *) BACKUP_FILE="${1}"
        [ ! -f "${BACKUP_FILE}" ] && { log "ERROR: File not found: ${BACKUP_FILE}"; exit 1; } ;;
esac

if ! pg_isready -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${PGDATABASE}" -t 5 > /dev/null 2>&1; then
    log "ERROR: PostgreSQL not reachable"
    exit 1
fi

log "Verifying backup integrity..."
if ! pg_restore -l "${BACKUP_FILE}" > /dev/null 2>&1; then
    log "ERROR: Backup file corrupted or invalid"
    exit 2
fi
log "Integrity OK"

BACKUP_SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
log "WARNING: This will DROP and REPLACE '${PGDATABASE}' from ${BACKUP_FILE} (${BACKUP_SIZE})"

if [ -t 0 ]; then
    read -r -p "Type yes to confirm: " CONFIRM
    [ "${CONFIRM}" != "yes" ] && { log "Cancelled"; exit 0; }
fi

log "Dropping connections and recreating database..."
psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${PGDATABASE}' AND pid<>pg_backend_pid();" > /dev/null 2>&1 || true
dropdb -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" --if-exists "${PGDATABASE}" 2>/dev/null || true
createdb -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" "${PGDATABASE}"

log "Restoring from ${BACKUP_FILE}..."
pg_restore -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${PGDATABASE}" -v --no-owner --no-privileges "${BACKUP_FILE}"
RESTORE_EXIT=$?

if [ ${RESTORE_EXIT} -eq 0 ]; then
    TABLE_COUNT=$(psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${PGDATABASE}" -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';" 2>/dev/null | tr -d ' ')
    log "Restore complete: ${TABLE_COUNT} tables restored"
    psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${PGDATABASE}" -c "CREATE EXTENSION IF NOT EXISTS vector;" > /dev/null 2>&1 || true
else
    log "ERROR: Restore failed (exit ${RESTORE_EXIT})"
    exit ${RESTORE_EXIT}
fi
