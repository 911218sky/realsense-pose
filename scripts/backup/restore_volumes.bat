@echo off
REM =============================================================================
REM Docker Volume Restore Script
REM =============================================================================
REM Restore MongoDB and Redis Docker Volume data from selected backup
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

REM Check if backups directory exists
if not exist "backups" (
  echo Error: No backups directory found!
  pause
  exit /b 1
)

REM List available backups
echo Available backups:
echo.
set COUNT=0
for /f "delims=" %%d in ('dir /b /ad /o-n backups 2^>nul') do (
  set /a COUNT+=1
  set BACKUP_!COUNT!=%%d
  
  REM Display backup info
  if exist "backups\%%d\backup_time.txt" (
    set /p BACKUP_TIME=<"backups\%%d\backup_time.txt"
    echo   [!COUNT!] %%d - !BACKUP_TIME!
  ) else (
    echo   [!COUNT!] %%d
  )
)

if %COUNT% EQU 0 (
  echo No backups found!
  pause
  exit /b 1
)

echo.
set /p CHOICE="Select backup number to restore (1-%COUNT%): "

REM Validate choice
if not defined CHOICE (
  echo Error: No selection made!
  pause
  exit /b 1
)

if %CHOICE% LSS 1 (
  echo Error: Invalid selection!
  pause
  exit /b 1
)

if %CHOICE% GTR %COUNT% (
  echo Error: Invalid selection!
  pause
  exit /b 1
)

REM Get selected backup directory
call set SELECTED_BACKUP=%%BACKUP_%CHOICE%%%
set BACKUP_PATH=backups\%SELECTED_BACKUP%

echo.
echo Selected backup: %SELECTED_BACKUP%

REM Check if backup files exist
if not exist "%BACKUP_PATH%\mongo.tar.gz" (
  echo Error: MongoDB backup file not found in %SELECTED_BACKUP%!
  pause
  exit /b 1
)

if not exist "%BACKUP_PATH%\redis.tar.gz" (
  echo Error: Redis backup file not found in %SELECTED_BACKUP%!
  pause
  exit /b 1
)

REM Display backup time
if exist "%BACKUP_PATH%\backup_time.txt" (
  echo Backup Time:
  type "%BACKUP_PATH%\backup_time.txt"
  echo.
)

REM Confirm operation
set /p CONFIRM="Are you sure you want to restore this backup? (yes/no): "

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
  -v %cd%\%BACKUP_PATH%:/backup ^
  alpine sh -c "rm -rf /data/* && tar xzf /backup/mongo.tar.gz -C /data"

if %errorlevel% equ 0 (
  echo       [OK] MongoDB restore completed
) else (
  echo       [FAIL] MongoDB restore failed
)

REM Restore Redis
echo [2/3] Restoring Redis...
docker run --rm ^
  -v realsense-pose-redis-data:/data ^
  -v %cd%\%BACKUP_PATH%:/backup ^
  alpine sh -c "rm -rf /data/* && tar xzf /backup/redis.tar.gz -C /data"

if %errorlevel% equ 0 (
  echo       [OK] Redis restore completed
) else (
  echo       [FAIL] Redis restore failed
)

REM Restart containers
echo [3/3] Restarting containers...
docker compose up -d mongo redis
echo.

echo ============================================
echo Restore Completed!
echo ============================================
echo Restored from: %SELECTED_BACKUP%
echo.

pause
