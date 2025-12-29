@echo off
REM =============================================================================
REM Remove Daily Backup Task
REM =============================================================================
REM Remove daily backup task from Windows Task Scheduler
REM =============================================================================

echo ============================================
echo Remove Daily Automatic Backup
echo ============================================
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

REM Check if task exists
schtasks /query /tn "RealSense-Pose-Daily-Backup" >nul 2>&1
if %errorlevel% neq 0 (
  echo Scheduled task not found
  pause
  exit /b 0
)

echo About to remove scheduled task: RealSense-Pose-Daily-Backup
echo.
set /p CONFIRM="Are you sure you want to remove it? (yes/no): "

if /i not "%CONFIRM%"=="yes" (
  echo Operation cancelled
  pause
  exit /b 0
)

schtasks /delete /tn "RealSense-Pose-Daily-Backup" /f

if %errorlevel% equ 0 (
  echo.
  echo ✓ Scheduled task removed
) else (
  echo.
  echo ✗ Removal failed
)

echo.
pause
