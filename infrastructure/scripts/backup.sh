#!/usr/bin/env bash
#
# APP-177: PostgreSQL backup script for RAG-CRM
#
# Usage:
#   ./backup.sh /path/to/backups    # Backup to specified directory
#   BACKUP_KEEP=14 ./backup.sh      # Keep 14 backups (default: 7)
#
# Designed to run inside the PostgreSQL container or on a host
# with pg client tools installed.
# When running inside Docker, BACKUP_DIR defaults to /backups.

set -euo pipefail

PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-rag_user}"
PGDATABASE="${PGDATABASE:-rag_crm}"
BACKUP_KEEP="${BACKUP_KEEP:-7}"
BACKUP_DIR="${1:-${BACKUP_DIR:-./backups}}"

TIMESTAMP=$(date -u +"%Y%m%dT%H%M%SZ")
BACKUP_FILE="${BACKUP_DIR}/rag_crm_${TIMESTAMP}.dump"
LOG_FILE="${BACKUP_DIR}/backup.log"
HEALTH_FILE="${BACKUP_DIR}/.last_backup_status"

export PGHOST PGUSER PGPORT PGDATABASE
[ -n "${PGPASSWORD:-}" ] && export PGPASSWORD

mkdir -p "${BACKUP_DIR}"

log() { echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] $*" | tee -a "${LOG_FILE}"; }

log "Starting backup of ${PGDATABASE} to ${BACKUP_FILE}"

if ! pg_isready -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${PGDATABASE}" -t 5 > /dev/null 2>&1; then
    log "ERROR: PostgreSQL not reachable at ${PGHOST}:${PGPORT}/${PGDATABASE}"
    echo "FAILED" > "${HEALTH_FILE}"
    exit 1
fi

log "Running pg_dump (custom format, compressed)..."

if pg_dump -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${PGDATABASE}" -F c -Z 9 -v -f "${BACKUP_FILE}" >> "${LOG_FILE}" 2>&1; then
    BACKUP_SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
    log "Backup complete: ${BACKUP_FILE} (${BACKUP_SIZE})"
    log "Verifying backup integrity..."
    if pg_restore -l "${BACKUP_FILE}" > /dev/null 2>&1; then
        log "Backup integrity verified OK"
        echo "OK ${TIMESTAMP}" > "${HEALTH_FILE}"
    else
        log "ERROR: Backup integrity check FAILED"
        echo "CORRUPT ${TIMESTAMP}" > "${HEALTH_FILE}"
        exit 2
    fi
else
    log "ERROR: pg_dump failed"
    echo "FAILED ${TIMESTAMP}" > "${HEALTH_FILE}"
    exit 1
fi

log "Rotating backups (keep last ${BACKUP_KEEP})..."
find "${BACKUP_DIR}" -maxdepth 1 -name 'rag_crm_*.dump' -type f | sort | head -n -${BACKUP_KEEP} | while read -r old; do
    log "Removing old backup: ${old}"
    rm -f "${old}"
done

BACKUP_COUNT=$(find "${BACKUP_DIR}" -maxdepth 1 -name 'rag_crm_*.dump' -type f | wc -l)
log "Backup complete. ${BACKUP_COUNT} backups retained (max ${BACKUP_KEEP})."
