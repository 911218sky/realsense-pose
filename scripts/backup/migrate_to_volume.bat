@echo off
REM =============================================================================
REM Migrate Data to Docker Volume
REM =============================================================================
REM Migrate existing bind mount data to Docker Volume
REM =============================================================================

REM Switch to project root directory (two levels up from script location)
cd /d "%~dp0..\.."

echo ============================================
echo Data Migration Tool
echo ============================================
echo.
echo This script will migrate existing data from ./data directory
echo to Docker Volume
echo.

REM Check if data directories exist
if not exist "data\mongo" (
  echo Warning: data\mongo directory not found, skipping MongoDB migration
  set SKIP_MONGO=1
)

if not exist "data\redis" (
  echo Warning: data\redis directory not found, skipping Redis migration
  set SKIP_REDIS=1
)

if defined SKIP_MONGO if defined SKIP_REDIS (
  echo.
  echo No data to migrate
  pause
  exit /b 0
)

echo.
set /p CONFIRM="Are you sure you want to start migration? (yes/no): "

if /i not "%CONFIRM%"=="yes" (
  echo Operation cancelled
  pause
  exit /b 0
)

echo.
echo ============================================
echo Starting Migration...
echo ============================================
echo.

REM Stop containers
echo [0/3] Stopping containers...
docker compose down
echo.

REM Migrate MongoDB
if not defined SKIP_MONGO (
  echo [1/3] Migrating MongoDB data...
  docker run --rm ^
    -v realsense-pose-mongo-data:/data ^
    -v %cd%\data\mongo:/source ^
    alpine sh -c "cp -r /source/. /data/"
  
  if %errorlevel% equ 0 (
    echo       ✓ MongoDB migration completed
  ) else (
    echo       ✗ MongoDB migration failed
  )
) else (
  echo [1/3] Skipping MongoDB migration
)

REM Migrate Redis
if not defined SKIP_REDIS (
  echo [2/3] Migrating Redis data...
  docker run --rm ^
    -v realsense-pose-redis-data:/data ^
    -v %cd%\data\redis:/source ^
    alpine sh -c "cp -r /source/. /data/"
  
  if %errorlevel% equ 0 (
    echo       ✓ Redis migration completed
  ) else (
    echo       ✗ Redis migration failed
  )
) else (
  echo [2/3] Skipping Redis migration
)

REM Restart containers
echo [3/3] Restarting containers...
docker compose up -d
echo.

echo ============================================
echo Migration Completed!
echo ============================================
echo.
echo Recommendations:
echo 1. After confirming services are working properly
echo 2. You can delete the old data\mongo and data\redis directories
echo 3. Or keep them as backup
echo.

pause
