# Docker Volume Backup System

## Overview

This backup system backs up MongoDB and Redis Docker Volume data with automatic rotation. It keeps the latest 7 backups and automatically deletes older ones.

**Features:**
- Keeps up to 7 backups (configurable)
- Timestamped backup directories
- Automatic cleanup of old backups
- Select which backup to restore

## Scripts

### 1. `backup_volumes.bat` - Manual Backup
Execute a backup immediately.

```bash
scripts\backup\backup_volumes.bat
```

### 2. `restore_volumes.bat` - Restore Backup
Restore data from `backups/latest`.

```bash
scripts\backup\restore_volumes.bat
```

### 3. `setup_daily_backup.bat` - Setup Daily Automatic Backup
Create a daily automatic backup task in Windows Task Scheduler.

**Usage:**
1. Run as Administrator
2. Enter daily backup time (e.g., 02:00)
3. Confirm creation

```bash
# Right-click -> Run as Administrator
scripts\backup\setup_daily_backup.bat
```

### 4. `remove_daily_backup.bat` - Remove Automatic Backup
Remove the automatic backup task from Task Scheduler.

```bash
# Right-click -> Run as Administrator
scripts\backup\remove_daily_backup.bat
```

### 5. `migrate_to_volume.bat` - Data Migration
Migrate existing `./data/mongo` and `./data/redis` data to Docker Volume.

```bash
scripts\backup\migrate_to_volume.bat
```

## Quick Start

### Initial Setup

1. **Migrate existing data (if any):**
   ```bash
   scripts\backup\migrate_to_volume.bat
   ```

2. **Setup daily automatic backup:**
   ```bash
   # Right-click -> Run as Administrator
   scripts\backup\setup_daily_backup.bat
   ```

### Daily Usage

- **Manual backup:** `scripts\backup\backup_volumes.bat`
- **Restore data:** `scripts\backup\restore_volumes.bat`
- **View backup time:** Check `backups\latest\backup_time.txt`

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

1. **Keeps up to 7 backups**
   - Automatically deletes backups older than the 7 most recent
   - Configurable by editing `MAX_BACKUPS` in `backup_volumes.bat`

2. **Backup does not delete Docker Volume**
   - Backup only copies data, does not affect running services
   - Can be executed while services are running

3. **Restore will overwrite existing data**
   - You can select which backup to restore
   - MongoDB and Redis containers will be stopped before restore
   - Containers will be automatically restarted after restore

4. **Automatic backup requires administrator privileges**
   - Setting up Task Scheduler requires administrator privileges
   - Backup script itself does not require administrator privileges

## Manual Task Scheduler Management

### View Task
```bash
schtasks /query /tn "RealSense-Pose-Daily-Backup" /fo list /v
```

### Run Task Immediately
```bash
schtasks /run /tn "RealSense-Pose-Daily-Backup"
```

### Disable Task
```bash
schtasks /change /tn "RealSense-Pose-Daily-Backup" /disable
```

### Enable Task
```bash
schtasks /change /tn "RealSense-Pose-Daily-Backup" /enable
```

## Troubleshooting

### Backup Failed
1. Confirm Docker is running
2. Confirm Volume exists: `docker volume ls | findstr realsense-pose`
3. Confirm sufficient disk space

### Restore Failed
1. Confirm backup files exist: `dir backups\latest`
2. Confirm containers are stopped: `docker compose ps`
3. Manually stop containers: `docker compose stop mongo redis`

### Automatic Backup Not Running
1. Open Task Scheduler and check task status
2. View task history
3. Confirm task is enabled and time is set correctly
