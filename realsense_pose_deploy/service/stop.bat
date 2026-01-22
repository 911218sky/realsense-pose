@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM ============================================================
REM Stop Services (Windows cmd)
REM ============================================================

cd /d "%~dp0.."

if not exist ".env" (
  echo ERROR: .env not found.
  pause
  exit /b 1
)

echo === Stopping services ===
docker compose --env-file .env -f docker-compose.yml down
if errorlevel 1 (
  echo ERROR: docker compose down failed.
  pause
  exit /b 1
)

echo.
echo Done.
pause
exit /b 0
