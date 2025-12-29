@echo off
REM =============================================================================
REM Setup Daily Backup Task
REM =============================================================================
REM Setup Windows Task Scheduler for daily automatic backup
REM =============================================================================

echo ============================================
echo Setup Daily Automatic Backup
echo ============================================
echo.
echo This script will create a daily backup task in Windows Task Scheduler
echo.

REM Check administrator privileges
net session >nul 2>&1
if %errorlevel% neq 0 (
  echo Error: Administrator privileges required!
  echo Please run this script as Administrator
  echo.
  pause
  exit /b 1
)

REM Get absolute path of project root directory
set PROJECT_DIR=%~dp0..
pushd "%PROJECT_DIR%"
set PROJECT_DIR=%cd%
popd

set SCRIPT_PATH=%PROJECT_DIR%\backup\backup_volumes.bat

echo Project Directory: %PROJECT_DIR%
echo Backup Script: %SCRIPT_PATH%
echo.

REM Set backup time
set /p BACKUP_TIME="Enter daily backup time (Format: HH:MM or H:MM, e.g. 02:00 or 2:00): "

REM Simple validation: check if contains colon
echo %BACKUP_TIME% | findstr ":" >nul
if %errorlevel% neq 0 (
  echo Error: Invalid time format! Must contain ':'
  pause
  exit /b 1
)

REM Extract hour and minute
for /f "tokens=1,2 delims=:" %%a in ("%BACKUP_TIME%") do (
  set HOUR=%%a
  set MINUTE=%%b
)

REM Validate hour and minute are numbers
set /a TEST_HOUR=%HOUR% 2>nul
set /a TEST_MINUTE=%MINUTE% 2>nul

if not defined HOUR (
  echo Error: Invalid hour!
  pause
  exit /b 1
)

if not defined MINUTE (
  echo Error: Invalid minute!
  pause
  exit /b 1
)

REM Validate ranges
if %HOUR% LSS 0 (
  echo Error: Hour must be 0-23!
  pause
  exit /b 1
)

if %HOUR% GTR 23 (
  echo Error: Hour must be 0-23!
  pause
  exit /b 1
)

if %MINUTE% LSS 0 (
  echo Error: Minute must be 0-59!
  pause
  exit /b 1
)

if %MINUTE% GTR 59 (
  echo Error: Minute must be 0-59!
  pause
  exit /b 1
)

REM Add leading zeros if needed
if %HOUR% LSS 10 (
  if not "%HOUR:~0,1%"=="0" (
    set HOUR=0%HOUR%
  )
)

if %MINUTE% LSS 10 (
  if not "%MINUTE:~0,1%"=="0" (
    set MINUTE=0%MINUTE%
  )
)

set BACKUP_TIME=%HOUR%:%MINUTE%

echo.
echo The following scheduled task will be created:
echo   Task Name: RealSense-Pose-Daily-Backup
echo   Run Time: Daily at %BACKUP_TIME%
echo   Script: %SCRIPT_PATH%
echo.

set /p CONFIRM="Are you sure you want to create this task? (yes/no): "

if /i not "%CONFIRM%"=="yes" (
  echo Operation cancelled
  pause
  exit /b 0
)

echo.
echo Creating scheduled task...

REM Delete old task (if exists)
schtasks /delete /tn "RealSense-Pose-Daily-Backup" /f >nul 2>&1

REM Create new task
schtasks /create ^
  /tn "RealSense-Pose-Daily-Backup" ^
  /tr "\"%SCRIPT_PATH%\" auto" ^
  /sc daily ^
  /st %BACKUP_TIME% ^
  /ru SYSTEM ^
  /rl HIGHEST ^
  /f

if %errorlevel% equ 0 (
  echo.
  echo ============================================
  echo [OK] Scheduled task created successfully!
  echo ============================================
  echo.
  echo Task Details:
  schtasks /query /tn "RealSense-Pose-Daily-Backup" /fo list /v
  echo.
  echo Tips:
  echo - You can view and manage this task in Task Scheduler
  echo - Backup files will be saved to: %PROJECT_DIR%\backups\latest
  echo - Each backup will overwrite the previous one
  echo.
) else (
  echo.
  echo [FAIL] Failed to create scheduled task!
  echo.
)

pause
