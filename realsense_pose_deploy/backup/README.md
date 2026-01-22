# Docker Volume Backup System

## Overview

This backup system provides both automatic and manual backup solutions for MongoDB and Redis Docker Volume data.

**Features:**
- Automatic backup via Docker container (recommended)
- Manual backup scripts for on-demand backups
- Keeps up to 7 backups (configurable)
- Timestamped backup directories
- Automatic cleanup of old backups
- Select which backup to restore

## Automatic Backup (Default Enabled)

Automatic backup is **enabled by default**. The backup service starts automatically with `docker compose up -d`.

### Configuration

Edit `.env` file:
```bash
# Enable/disable automatic backup
BACKUP_ENABLED=enabled    # Set to "disabled" to turn off

# Backup schedule (cron format)
BACKUP_CRON=0 2 * * *    # Daily at 2 AM

# Maximum backups to keep
MAX_BACKUPS=7

# Backup storage location
HOST_BACKUP_DIR=./backups

# Timezone
TZ=Asia/Taipei
```

### Disable Automatic Backup

To disable automatic backup:
```bash
# In .env
BACKUP_ENABLED=disabled

# Restart services
docker compose up -d
```

### Cron Schedule Examples

```bash
BACKUP_CRON=0 2 * * *      # Daily at 2:00 AM
BACKUP_CRON=0 */6 * * *    # Every 6 hours
BACKUP_CRON=0 0 * * 0      # Weekly on Sunday at midnight
BACKUP_CRON=*/30 * * * *   # Every 30 minutes
```

### Manual Trigger

Trigger backup manually:
```bash
docker exec realsense-pose-backup /usr/local/bin/backup.sh
```

### View Logs

Check backup logs:
```bash
docker logs realsense-pose-backup
```

## Manual Backup Scripts

### 1. `backup_volumes.bat` - Manual Backup
Execute a backup immediately without Docker.

```bash
scripts\backup\backup_volumes.bat
```

### 2. `restore_volumes.bat` - Restore Backup
Restore data from selected backup.

```bash
scripts\backup\restore_volumes.bat
```

### 3. `migrate_to_volume.bat` - Data Migration
Migrate existing `./data/mongo` and `./data/redis` data to Docker Volume.

```bash
scripts\backup\migrate_to_volume.bat
```

## Quick Start

### Option 1: Automatic Backup (Recommended - Default)

1. **Configure backup settings in `.env` (optional):**
   ```bash
   BACKUP_ENABLED=1         # Already enabled by default
   BACKUP_CRON=0 2 * * *
   MAX_BACKUPS=7
   HOST_BACKUP_DIR=./backups
   ```

2. **Start services:**
   ```bash
   docker compose up -d
   ```

3. **Done!** Backup runs immediately on startup, then follows schedule.

### Option 2: Disable Automatic Backup

1. **Set in `.env`:**
   ```bash
   BACKUP_ENABLED=0
   ```

2. **Start services:**
   ```bash
   docker compose up -d
   ```

3. **Use manual backup when needed:**
   ```bash
   backup\backup_volumes.bat
   ```

## Backup Location

```
backups/
├── 20241229_140530/         # Backup from 2024-12-29 14:05:30
│   ├── mongo.tar.gz
│   ├── redis.tar.gz
│   └── backup_time.txt
├── 20241228_020000/         # Backup from 2024-12-28 02:00:00
│   ├── mongo.tar.gz
│   ├── redis.tar.gz
│   └── backup_time.txt
└── ...                      # Up to 7 backups total
```

## Notes

1. **Automatic backup runs on container start**
   - First backup runs immediately when container starts
   - Then follows the cron schedule

2. **Keeps up to 7 backups by default**
   - Automatically deletes backups older than the most recent 7
   - Configurable via `MAX_BACKUPS` in `.env`

3. **Backup does not affect running services**
   - Backup reads data in read-only mode
   - Can be executed while services are running

4. **Restore will overwrite existing data**
   - You can select which backup to restore
   - MongoDB and Redis containers will be stopped before restore
   - Containers will be automatically restarted after restore

## Troubleshooting

### Automatic Backup Not Running

1. Check if backup container is running:
   ```bash
   docker ps | findstr backup
   ```

2. Check backup logs:
   ```bash
   docker logs realsense-pose-backup
   ```

3. Verify backup profile is enabled:
   ```bash
   docker compose --profile backup ps
   ```

### Manual Backup Failed

1. Confirm Docker is running
2. Confirm Volume exists: `docker volume ls | findstr realsense-pose`
3. Confirm sufficient disk space

### Restore Failed

1. Confirm backup files exist: `dir backups`
2. Confirm containers are stopped: `docker compose ps`
3. Manually stop containers: `docker compose stop mongo redis`
