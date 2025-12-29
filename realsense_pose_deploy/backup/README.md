# Docker Volume Backup System

## Overview

This backup system backs up MongoDB and Redis Docker Volume data to the `backups/latest` directory. Each backup overwrites the previous one, keeping only the latest backup.

## Scripts

### 1. `backup_volumes.bat` - Manual Backup
Execute a backup immediately.

```bash
backup\backup_volumes.bat
```

### 2. `restore_volumes.bat` - Restore Backup
Restore data from `backups/latest`.

```bash
backup\restore_volumes.bat
```

### 3. `setup_daily_backup.bat` - Setup Daily Automatic Backup
Create a daily automatic backup task in Windows Task Scheduler.

**Usage:**
1. Run as Administrator
2. Enter daily backup time (e.g., 02:00)
3. Confirm creation

```bash
# Right-click -> Run as Administrator
backup\setup_daily_backup.bat
```

### 4. `remove_daily_backup.bat` - Remove Automatic Backup
Remove the automatic backup task from Task Scheduler.

```bash
# Right-click -> Run as Administrator
backup\remove_daily_backup.bat
```

### 5. `migrate_to_volume.bat` - Data Migration
Migrate existing `./data/mongo` and `./data/redis` data to Docker Volume.

```bash
backup\migrate_to_volume.bat
```

## Quick Start

### Initial Setup

1. **Migrate existing data (if any):**
   ```bash
   backup\migrate_to_volume.bat
   ```

2. **Setup daily automatic backup:**
   ```bash
   # Right-click -> Run as Administrator
   backup\setup_daily_backup.bat
   ```

### Daily Usage

- **Manual backup:** `backup\backup_volumes.bat`
- **Restore data:** `backup\restore_volumes.bat`
- **View backup time:** Check `backups\latest\backup_time.txt`

## Backup Location

```
backups/
└── latest/
    ├── mongo.tar.gz        # MongoDB backup
    ├── redis.tar.gz        # Redis backup
    └── backup_time.txt     # Backup time record
```

## Notes

1. **Only keeps the latest backup**
   - Each backup overwrites the previous one
   - To keep multiple versions, manually copy the `backups/latest` directory

2. **Backup does not delete Docker Volume**
   - Backup only copies data, does not affect running services
   - Can be executed while services are running

3. **Restore will overwrite existing data**
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
