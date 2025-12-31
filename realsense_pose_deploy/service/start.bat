@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM ============================================================
REM Start Services (Windows cmd)
REM - Starts all services without pulling new images
REM ============================================================

cd /d "%~dp0.."

if not exist ".env" (
  echo ERROR: .env not found. Run deploy.bat first.
  pause
  exit /b 1
)

echo === Starting services ===
docker compose --env-file .env -f docker-compose.yml up -d
if errorlevel 1 (
  echo ERROR: docker compose up failed.
  pause
  exit /b 1
)

echo.
docker compose --env-file .env -f docker-compose.yml ps

echo.
echo Done.
pause
exit /b 0
