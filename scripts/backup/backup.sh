#!/bin/sh
# =============================================================================
# Database Backup Script
# =============================================================================
# Backs up MongoDB and Redis data to backup directory
# Usage: backup.sh [--startup]
#   --startup: Run backup immediately on container start
#
# Environment Variables:
#   BACKUP_DIR   - Backup destination directory (default: /backups)
#   MONGO_DATA   - MongoDB data directory (default: /data/mongo)
#   REDIS_DATA   - Redis data directory (default: /data/redis)
#   MAX_BACKUPS  - Maximum number of backups to keep (default: 7)
#   BACKUP_CRON  - Cron schedule for periodic backups (optional)
# =============================================================================

set -e

BACKUP_DIR="${BACKUP_DIR:-/backups}"
MONGO_DATA="${MONGO_DATA:-/data/mongo}"
REDIS_DATA="${REDIS_DATA:-/data/redis}"
MAX_BACKUPS="${MAX_BACKUPS:-7}"

do_backup() {
  TIMESTAMP=$(date +%Y%m%d_%H%M%S)
  TARGET_DIR="$BACKUP_DIR/$TIMESTAMP"
  
  echo "[$(date)] Starting backup..."
  mkdir -p "$TARGET_DIR"
  
  # Backup MongoDB
  if [ -d "$MONGO_DATA" ] && [ "$(ls -A $MONGO_DATA 2>/dev/null)" ]; then
    echo "Backing up MongoDB..."
    tar czf "$TARGET_DIR/mongo.tar.gz" -C "$MONGO_DATA" . 2>/dev/null || echo "MongoDB backup failed"
  else
    echo "No MongoDB data found, skipping..."
  fi
  
  # Backup Redis
  if [ -d "$REDIS_DATA" ] && [ "$(ls -A $REDIS_DATA 2>/dev/null)" ]; then
    echo "Backing up Redis..."
    tar czf "$TARGET_DIR/redis.tar.gz" -C "$REDIS_DATA" . 2>/dev/null || echo "Redis backup failed"
  else
    echo "No Redis data found, skipping..."
  fi
  
  # Write backup timestamp
  date > "$TARGET_DIR/backup_time.txt"
  
  # Clean old backups
  cd "$BACKUP_DIR"
  BACKUP_COUNT=$(ls -d */ 2>/dev/null | wc -l)
  if [ "$BACKUP_COUNT" -gt "$MAX_BACKUPS" ]; then
    echo "Cleaning old backups (keeping last $MAX_BACKUPS)..."
    ls -dt */ | tail -n +$((MAX_BACKUPS + 1)) | xargs -r rm -rf
  fi
  
  echo "[$(date)] Backup completed: $TARGET_DIR"
}

# Main
mkdir -p "$BACKUP_DIR"

case "${1:-}" in
  --startup)
    echo "[$(date)] Backup service started"
    echo "[$(date)] Running startup backup..."
    do_backup
    
    # Setup cron if BACKUP_CRON is set
    if [ -n "${BACKUP_CRON:-}" ]; then
      echo "[$(date)] Setting up cron schedule: $BACKUP_CRON"
      echo "$BACKUP_CRON /usr/local/bin/backup.sh" > /etc/crontabs/root
      crond -f -l 2
    else
      echo "[$(date)] No BACKUP_CRON set, exiting after startup backup"
    fi
    ;;
  *)
    do_backup
    ;;
esac
