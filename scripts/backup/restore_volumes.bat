@echo off
REM =============================================================================
REM Docker Volume Restore Script
REM =============================================================================
REM Restore MongoDB and Redis Docker Volume data
REM =============================================================================

setlocal enabledelayedexpansion

REM Switch to project root directory (two levels up from script location)
cd /d "%~dp0..\.."

echo ============================================
echo Docker Volume Restore Tool
echo ============================================
echo.
echo WARNING: This operation will overwrite existing data!
echo.

REM Check if backup exists
if not exist "backups\latest\mongo.tar.gz" (
  echo Error: MongoDB backup file not found!
  pause
  exit /b 1
)

if not exist "backups\latest\redis.tar.gz" (
  echo Error: Redis backup file not found!
  pause
  exit /b 1
)

REM Display backup time
if exist "backups\latest\backup_time.txt" (
  echo Backup Time:
  type "backups\latest\backup_time.txt"
  echo.
)

REM Confirm operation
set /p CONFIRM="Are you sure you want to restore data? (yes/no): "

if /i not "%CONFIRM%"=="yes" (
  echo Operation cancelled
  pause
  exit /b 0
)

echo.
echo ============================================
echo Starting Restore...
echo ============================================
echo.

REM Stop containers
echo [0/3] Stopping containers...
docker compose stop mongo redis
echo.

REM Restore MongoDB
echo [1/3] Restoring MongoDB...
docker run --rm ^
  -v realsense-pose-mongo-data:/data ^
  -v %cd%\backups\latest:/backup ^
  alpine sh -c "rm -rf /data/* && tar xzf /backup/mongo.tar.gz -C /data"

if %errorlevel% equ 0 (
  echo       ✓ MongoDB restore completed
) else (
  echo       ✗ MongoDB restore failed
)

REM Restore Redis
echo [2/3] Restoring Redis...
docker run --rm ^
  -v realsense-pose-redis-data:/data ^
  -v %cd%\backups\latest:/backup ^
  alpine sh -c "rm -rf /data/* && tar xzf /backup/redis.tar.gz -C /data"

if %errorlevel% equ 0 (
  echo       ✓ Redis restore completed
) else (
  echo       ✗ Redis restore failed
)

REM Restart containers
echo [3/3] Restarting containers...
docker compose up -d mongo redis
echo.

echo ============================================
echo Restore Completed!
echo ============================================
echo.

pause
