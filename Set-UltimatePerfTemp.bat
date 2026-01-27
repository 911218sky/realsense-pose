@echo off
setlocal ENABLEDELAYEDEXPANSION

set "SCRIPT_DIR=%~dp0"
set "PS1_FILE=%SCRIPT_DIR%Set-UltimatePerfTemp.ps1"

if not exist "%PS1_FILE%" (
  echo [ERROR] PowerShell script not found: %PS1_FILE%
  exit /b 1
)

REM Check for admin (net session requires admin)
net session >nul 2>&1
if not "%errorlevel%"=="0" (
  echo Requesting administrator privileges...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

REM Run the script with process-scoped policy bypass; pass through args
echo Running PowerShell script...
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1_FILE%" %*
set "ERR=%ERRORLEVEL%"

if not "%ERR%"=="0" (
  echo [ERROR] Script exit code: %ERR%
  pause
)
exit /b %ERR%