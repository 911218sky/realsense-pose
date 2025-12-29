@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM ============================================================
REM Stop (Windows cmd)
REM ============================================================

cd /d "%~dp0"

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
