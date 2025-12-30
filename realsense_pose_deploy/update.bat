@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM ============================================================
REM Update (Windows cmd)
REM - Pulls latest images (only downloads changed layers)
REM - Restarts services only if image changed
REM ============================================================

cd /d "%~dp0"

if not exist ".env" (
  echo ERROR: .env not found. Run deploy.bat first.
  pause
  exit /b 1
)

REM Get image info from .env
for /f "tokens=2 delims==" %%a in ('findstr /i "^API_IMAGE=" .env') do set API_IMAGE=%%a
for /f "tokens=2 delims==" %%a in ('findstr /i "^API_TAG=" .env') do set API_TAG=%%a
if "!API_IMAGE!"=="" set API_IMAGE=ghcr.io/911218sky/realsense-pose
if "!API_TAG!"=="" set API_TAG=latest

echo === Checking for updates ===
echo Image: !API_IMAGE!:!API_TAG!
echo.

REM Pull image (only downloads changed layers)
docker pull !API_IMAGE!:!API_TAG!
if errorlevel 1 (
  echo ERROR: docker pull failed.
  pause
  exit /b 1
)

echo.
echo === Restarting services ===
docker compose --env-file .env -f docker-compose.yml up -d
if errorlevel 1 (
  echo ERROR: docker compose up failed.
  pause
  exit /b 1
)

echo.
docker compose --env-file .env -f docker-compose.yml ps

echo.
echo === Running database migrations ===
echo Waiting for services to be ready...
timeout /t 5 /nobreak >nul

REM Check if API container is running
docker ps --filter "name=realsense-pose-api" --format "{{.Names}}" | findstr /C:"realsense-pose-api" >nul
if errorlevel 1 (
  echo [WARNING] API container not found, skipping database migration
  echo You can run it manually later: fix_database.bat
) else (
  echo Running database fixes...
  docker exec realsense-pose-api python -m src.db.mongo.migration_runner
  if errorlevel 1 (
    echo [WARNING] Database migration failed. You may need to run fix_database.bat manually.
  ) else (
    echo [SUCCESS] Database migration completed!
  )
)

echo.
echo Done.
pause
exit /b 0
