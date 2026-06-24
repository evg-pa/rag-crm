#!/usr/bin/env bash
#
# APP-177: Backup health check for monitoring (Nagios/cron compatible).
# Checks backup status via docker exec into the postgres container.
set -euo pipefail

MAX_AGE_HOURS="${MAX_AGE_HOURS:-26}"
VERBOSE=false
for a in "$@"; do case "$a" in --verbose|-v) VERBOSE=true ;; esac; done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="${INFRA_DIR}/docker-compose.yml"
DOCKER_CMD="docker compose -f ${COMPOSE_FILE} exec -T postgres"

# Convert YYYYMMDDTHHMMSSZ -> epoch
_ts_to_epoch() {
    local ts="$1"
    local y="${ts:0:4}"
    local m="${ts:4:2}"
    local d="${ts:6:2}"
    local hh="${ts:9:2}"
    local mm="${ts:11:2}"
    local ss="${ts:13:2}"
    date -d "${y}-${m}-${d} ${hh}:${mm}:${ss}" +%s 2>/dev/null || echo 0
}

# Check container is running
if ! ${DOCKER_CMD} pg_isready -U rag_user -d rag_crm -t 5 > /dev/null 2>&1; then
    echo "CRITICAL: PostgreSQL container not reachable"
    exit 2
fi

HEALTH_LINE=$( ${DOCKER_CMD} cat /backups/.last_backup_status 2>/dev/null || echo "" )
if [ -z "${HEALTH_LINE}" ]; then
    echo "WARNING: No backup health file"
    exit 1
fi

STATUS=$(echo "${HEALTH_LINE}" | awk '{print $1}')
LAST_TS=$(echo "${HEALTH_LINE}" | awk '{print $2}')

if [ "${STATUS}" != "OK" ]; then
    echo "CRITICAL: Last backup status=${STATUS} (${HEALTH_LINE})"
    exit 2
fi

if [ -n "${LAST_TS}" ]; then
    LAST_EPOCH=$(_ts_to_epoch "${LAST_TS}")
    NOW_EPOCH=$(date +%s)
    AGE_HOURS=$(( (NOW_EPOCH - LAST_EPOCH) / 3600 ))
    if [ "${AGE_HOURS}" -gt "${MAX_AGE_HOURS}" ]; then
        echo "WARNING: Last backup ${AGE_HOURS}h old (max ${MAX_AGE_HOURS}h)"
        exit 1
    fi
else
    echo "WARNING: Cannot determine backup age"
    exit 1
fi

COUNT=$( ${DOCKER_CMD} sh -c "find /backups -maxdepth 1 -name 'rag_crm_*.dump' -type f | wc -l" 2>/dev/null || echo 0 )
COUNT=$(echo "${COUNT}" | tr -d ' ')
if [ "${COUNT}" -eq 0 ]; then
    echo "CRITICAL: No backup files in /backups"
    exit 2
fi

if ${VERBOSE}; then
    LATEST=$( ${DOCKER_CMD} sh -c "find /backups -maxdepth 1 -name 'rag_crm_*.dump' -type f | sort -r | head -1 | xargs basename" 2>/dev/null || echo unknown )
    echo "OK: ${COUNT} backups, latest=${LATEST}, age=${AGE_HOURS}h"
else
    echo "OK: ${AGE_HOURS}h since last backup, ${COUNT} backups retained"
fi
exit 0
