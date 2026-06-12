#!/usr/bin/env bash
# Ежедневный бэкап Postgres. Устанавливается в host cron — см. SETUP.md шаг 5.
# Ретенция 14 дней (specs/architecture.md §3.4).

set -euo pipefail

BACKUP_DIR="/var/backups/api-tracker"
RETENTION_DAYS=14
TIMESTAMP=$(date -u +%Y%m%dT%H%M%SZ)
DUMP_FILE="$BACKUP_DIR/postgres-$TIMESTAMP.sql.gz"

mkdir -p "$BACKUP_DIR"

docker exec api-tracker-postgres pg_dumpall -U postgres | gzip > "$DUMP_FILE"

# Ротация.
find "$BACKUP_DIR" -name 'postgres-*.sql.gz' -type f -mtime +"$RETENTION_DAYS" -delete

# Лог.
echo "[$(date -u +%FT%TZ)] backup OK: $DUMP_FILE ($(du -h "$DUMP_FILE" | cut -f1))" >> "$BACKUP_DIR/backup.log"
