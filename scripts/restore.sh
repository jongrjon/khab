#!/bin/bash
# PostgreSQL restore script for KHA Boutique
#
# Usage:
#   ./scripts/restore.sh /backups/khab_20260331_120000.sql.gz
#
# WARNING: This will DROP and recreate the database!

set -e

if [ -z "$1" ]; then
    echo "Usage: $0 <backup_file.sql.gz>"
    echo ""
    echo "Available backups:"
    ls -lh "${BACKUP_DIR:-/backups}"/khab_*.sql.gz 2>/dev/null || echo "  No backups found"
    exit 1
fi

BACKUP_FILE="$1"
POSTGRES_HOST="${POSTGRES_HOST:-db}"
POSTGRES_DB="${POSTGRES_DB:-khab}"
POSTGRES_USER="${POSTGRES_USER:-khab}"

if [ ! -f "$BACKUP_FILE" ]; then
    echo "Error: Backup file not found: $BACKUP_FILE"
    exit 1
fi

echo "[$(date)] Restoring from: $BACKUP_FILE"
echo "WARNING: This will overwrite the current database '$POSTGRES_DB'!"
read -p "Continue? (y/N) " -n 1 -r
echo

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

echo "[$(date)] Restoring database..."
gunzip -c "$BACKUP_FILE" | PGPASSWORD="${POSTGRES_PASSWORD}" psql \
    -h "$POSTGRES_HOST" \
    -U "$POSTGRES_USER" \
    -d "$POSTGRES_DB" \
    --quiet

echo "[$(date)] Restore complete."
