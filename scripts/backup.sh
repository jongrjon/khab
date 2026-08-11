#!/bin/bash
# PostgreSQL backup script for KHA Boutique
#
# Usage:
#   ./scripts/backup.sh
#
# Environment variables (or from .env):
#   POSTGRES_HOST     - default: db
#   POSTGRES_DB       - default: khab
#   POSTGRES_USER     - default: khab
#   POSTGRES_PASSWORD - default: khab
#   BACKUP_DIR        - default: /backups
#   BACKUP_RETENTION  - days to keep, default: 30

set -e

POSTGRES_HOST="${POSTGRES_HOST:-db}"
POSTGRES_DB="${POSTGRES_DB:-khab}"
POSTGRES_USER="${POSTGRES_USER:-khab}"
BACKUP_DIR="${BACKUP_DIR:-/backups}"
BACKUP_RETENTION="${BACKUP_RETENTION:-30}"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/khab_${TIMESTAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"

echo "[$(date)] Starting backup..."
PGPASSWORD="${POSTGRES_PASSWORD}" pg_dump \
    -h "$POSTGRES_HOST" \
    -U "$POSTGRES_USER" \
    -d "$POSTGRES_DB" \
    --no-owner \
    --no-privileges \
    | gzip > "$BACKUP_FILE"

echo "[$(date)] Backup created: $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"

# Remove backups older than retention period
if [ "$BACKUP_RETENTION" -gt 0 ]; then
    DELETED=$(find "$BACKUP_DIR" -name "khab_*.sql.gz" -mtime +${BACKUP_RETENTION} -delete -print | wc -l)
    echo "[$(date)] Cleaned up $DELETED backup(s) older than $BACKUP_RETENTION days"
fi

echo "[$(date)] Backup complete."
