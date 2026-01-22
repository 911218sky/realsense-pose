@echo off
REM =============================================================================
REM Docker Volume Backup Script (Keep Multiple Backups)
REM =============================================================================
REM Daily backup of MongoDB and Redis Docker Volume data with rotation
REM =============================================================================

setlocal enabledelayedexpansion

REM Switch to project root directory (two levels up from script location)
cd /d "%~dp0..\.."

REM Configuration
set MAX_BACKUPS=7
set TIMESTAMP=%date:~0,4%%date:~5,2%%date:~8,2%_%time:~0,2%%time:~3,2%%time:~6,2%
set TIMESTAMP=%TIMESTAMP: =0%
set BACKUP_DIR=backups\%TIMESTAMP%

echo ============================================
echo Docker Volume Backup Tool
echo ============================================
echo.
echo Backup Time: %date% %time%
echo Backup Directory: %BACKUP_DIR%
echo Max Backups: %MAX_BACKUPS%
echo.

REM Create backup directory
if not exist "backups" mkdir "backups"
if not exist "%BACKUP_DIR%" mkdir "%BACKUP_DIR%"

REM Backup MongoDB
echo [1/3] Backing up MongoDB...
docker run --rm ^
  -v realsense-pose-mongo-data:/data ^
  -v %cd%\%BACKUP_DIR%:/backup ^
  alpine tar czf /backup/mongo.tar.gz -C /data .

if %errorlevel% equ 0 (
  echo       [OK] MongoDB backup completed
) else (
  echo       [FAIL] MongoDB backup failed
  exit /b 1
)

REM Backup Redis
echo [2/3] Backing up Redis...
docker run --rm ^
  -v realsense-pose-redis-data:/data ^
  -v %cd%\%BACKUP_DIR%:/backup ^
  alpine tar czf /backup/redis.tar.gz -C /data .

if %errorlevel% equ 0 (
  echo       [OK] Redis backup completed
) else (
  echo       [FAIL] Redis backup failed
  exit /b 1
)

REM Record backup time
echo %date% %time% > "%BACKUP_DIR%\backup_time.txt"

REM Clean old backups
echo [3/3] Cleaning old backups...
set COUNT=0
for /f "delims=" %%d in ('dir /b /ad /o-n backups 2^>nul') do (
  set /a COUNT+=1
  if !COUNT! GTR %MAX_BACKUPS% (
    echo       Deleting old backup: %%d
    rd /s /q "backups\%%d"
  )
)

echo.
echo ============================================
echo Backup Completed!
echo ============================================
echo Backup Location: %BACKUP_DIR%
echo.
dir /b "%BACKUP_DIR%"
echo.
echo Current backups:
dir /b /ad /o-n backups
echo.

REM Pause only if manually executed
if /i not "%1"=="auto" pause
