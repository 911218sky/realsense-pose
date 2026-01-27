@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM ============================================================
REM Restart Services (Windows cmd)
REM - Stops and restarts all services without pulling new images
REM ============================================================

cd /d "%~dp0.."

if not exist ".env" (
  echo ERROR: .env not found. Run deploy.bat first.
  pause
  exit /b 1
)

echo === Restarting services ===
docker compose --env-file .env -f docker-compose.yml restart
if errorlevel 1 (
  echo ERROR: docker compose restart failed.
  pause
  exit /b 1
)

echo.
docker compose --env-file .env -f docker-compose.yml ps

echo.
echo Done.
pause
exit /b 0
