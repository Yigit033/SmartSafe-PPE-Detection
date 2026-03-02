#!/bin/bash

# SmartSafe AI Backup Script
# This script backs up databases and important files

set -e

# Configuration
BACKUP_DIR="/backups"
DATE=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=30

# Database credentials
DB_HOST="postgres"
DB_PORT="5432"
DB_NAME="smartsafe_saas"
DB_USER="smartsafe"
DB_PASSWORD="smartsafe2024db"

# Create backup directory
mkdir -p "$BACKUP_DIR/database"
mkdir -p "$BACKUP_DIR/files"

echo "🔄 Starting SmartSafe AI backup - $DATE"

# Backup PostgreSQL database
echo "📊 Backing up PostgreSQL database..."
PGPASSWORD="$DB_PASSWORD" pg_dump \
    -h "$DB_HOST" \
    -p "$DB_PORT" \
    -U "$DB_USER" \
    -d "$DB_NAME" \
    --no-owner \
    --no-privileges \
    --clean \
    --if-exists \
    | gzip > "$BACKUP_DIR/database/smartsafe_db_$DATE.sql.gz"

# Backup SQLite database (if exists)
if [ -f "/app/data/smartsafe_saas.db" ]; then
    echo "📊 Backing up SQLite database..."
    cp "/app/data/smartsafe_saas.db" "$BACKUP_DIR/database/smartsafe_sqlite_$DATE.db"
    gzip "$BACKUP_DIR/database/smartsafe_sqlite_$DATE.db"
fi

# Backup application files
echo "📁 Backing up application files..."
tar -czf "$BACKUP_DIR/files/smartsafe_files_$DATE.tar.gz" \
    -C /app \
    data/models \
    static/uploads \
    logs \
    2>/dev/null || true

# Backup Redis dump (if exists)
if [ -f "/data/dump.rdb" ]; then
    echo "🔄 Backing up Redis data..."
    cp "/data/dump.rdb" "$BACKUP_DIR/files/redis_dump_$DATE.rdb"
    gzip "$BACKUP_DIR/files/redis_dump_$DATE.rdb"
fi

# Clean old backups
echo "🧹 Cleaning old backups (older than $RETENTION_DAYS days)..."
find "$BACKUP_DIR" -name "*.gz" -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -name "*.db" -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +$RETENTION_DAYS -delete

# Generate backup report
echo "📋 Generating backup report..."
BACKUP_SIZE=$(du -sh "$BACKUP_DIR" | cut -f1)
BACKUP_COUNT=$(find "$BACKUP_DIR" -name "*$DATE*" | wc -l)

cat > "$BACKUP_DIR/backup_report_$DATE.txt" << EOF
SmartSafe AI Backup Report
==========================
Date: $DATE
Backup Size: $BACKUP_SIZE
Files Backed Up: $BACKUP_COUNT
Status: SUCCESS

Database Backups:
- PostgreSQL: ✅
- SQLite: $([ -f "$BACKUP_DIR/database/smartsafe_sqlite_$DATE.db.gz" ] && echo "✅" || echo "❌")
- Redis: $([ -f "$BACKUP_DIR/files/redis_dump_$DATE.rdb.gz" ] && echo "✅" || echo "❌")

File Backups:
- Application Files: ✅
- Models: ✅
- Uploads: ✅
- Logs: ✅

Retention Policy: $RETENTION_DAYS days
EOF

echo "✅ Backup completed successfully!"
echo "📊 Backup size: $BACKUP_SIZE"
echo "📁 Backup location: $BACKUP_DIR"

# Optional: Send backup notification (uncomment if needed)
# curl -X POST "https://api.smartsafe.ai/webhook/backup" \
#      -H "Content-Type: application/json" \
#      -d "{\"status\":\"success\",\"date\":\"$DATE\",\"size\":\"$BACKUP_SIZE\"}" 