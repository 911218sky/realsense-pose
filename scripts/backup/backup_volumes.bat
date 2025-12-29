@echo off
REM =============================================================================
REM Docker Volume Backup Script (Daily - Keep Latest Only)
REM =============================================================================
REM Daily backup of MongoDB and Redis Docker Volume data, keeping only the latest
REM =============================================================================

setlocal enabledelayedexpansion

REM Switch to project root directory (two levels up from script location)
cd /d "%~dp0..\.."

REM Set backup directory
set BACKUP_DIR=backups\latest

echo ============================================
echo Docker Volume Daily Backup Tool
echo ============================================
echo.
echo Backup Time: %date% %time%
echo Backup Directory: %BACKUP_DIR%
echo.

REM Create backup directory
if not exist "backups" mkdir "backups"
if not exist "%BACKUP_DIR%" mkdir "%BACKUP_DIR%"

REM Backup MongoDB
echo [1/2] Backing up MongoDB...
docker run --rm ^
  -v realsense-pose-mongo-data:/data ^
  -v %cd%\%BACKUP_DIR%:/backup ^
  alpine tar czf /backup/mongo.tar.gz -C /data .

if %errorlevel% equ 0 (
  echo       ✓ MongoDB backup completed
) else (
  echo       ✗ MongoDB backup failed
  exit /b 1
)

REM Backup Redis
echo [2/2] Backing up Redis...
docker run --rm ^
  -v realsense-pose-redis-data:/data ^
  -v %cd%\%BACKUP_DIR%:/backup ^
  alpine tar czf /backup/redis.tar.gz -C /data .

if %errorlevel% equ 0 (
  echo       ✓ Redis backup completed
) else (
  echo       ✗ Redis backup failed
  exit /b 1
)

REM Record backup time
echo %date% %time% > "%BACKUP_DIR%\backup_time.txt"

echo.
echo ============================================
echo Backup Completed!
echo ============================================
echo Backup Location: %BACKUP_DIR%
echo.
dir /b "%BACKUP_DIR%"
echo.

REM Pause only if manually executed
if /i not "%1"=="auto" pause
