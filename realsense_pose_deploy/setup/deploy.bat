@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM ============================================================
REM Deploy (Windows cmd)
REM - Pulls prebuilt image from Docker Hub and starts via docker compose
REM - Does NOT build locally
REM ============================================================

cd /d "%~dp0.."

echo === Checking Docker ===
docker version >nul 2>&1
if errorlevel 1 (
  echo ERROR: Docker is not available. Please install/start Docker Desktop.
  pause
  exit /b 1
)

docker compose version >nul 2>&1
if errorlevel 1 (
  echo ERROR: docker compose is not available. Please update Docker Desktop.
  pause
  exit /b 1
)

if not exist ".env" (
  echo .env not found. Creating from env.example...
  if exist "env.example" (
    copy /Y "env.example" ".env" >nul
    echo Created .env.
    echo Please open .env and set API_IMAGE / API_TAG, then run this again.
    echo Tip: For auto-update via Watchtower, use API_TAG=latest, or push a new image to the same tag.
    pause
    exit /b 2
  ) else (
    echo ERROR: env.example not found. Cannot create .env
    pause
    exit /b 1
  )
)

echo.
echo === Pull images (API + dependencies) ===
docker compose --env-file .env -f docker-compose.yml pull
if errorlevel 1 (
  echo ERROR: docker compose pull failed.
  echo - If you see "not found", check .env API_IMAGE/API_TAG exists on Docker Hub.
  pause
  exit /b 1
)

echo.
echo === Start services (no build) ===
docker compose --env-file .env -f docker-compose.yml up -d --no-build
if errorlevel 1 (
  echo ERROR: docker compose up failed.
  pause
  exit /b 1
)

echo.
docker compose --env-file .env -f docker-compose.yml ps

echo.
echo Done.
echo API default:
echo   http://localhost:8100/v1
echo Check .env for API_PORT / PREFIX
pause
exit /b 0
