@echo off
REM ============================================================================
REM Database Migration/Fix Script for Deployment
REM ============================================================================

setlocal enabledelayedexpansion

cd /d "%~dp0.."

echo.
echo ============================================================
echo   Database Migration Tool
echo ============================================================
echo.

REM Check if Docker is running
docker info >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker is not running!
    echo Please start Docker Desktop and try again.
    pause
    exit /b 1
)

REM Check if container is running
docker ps --filter "name=realsense-pose-api" --format "{{.Names}}" | findstr /C:"realsense-pose-api" >nul
if errorlevel 1 (
    echo [ERROR] API container is not running!
    echo.
    echo Please start the services first:
    echo   service\start.bat
    echo.
    pause
    exit /b 1
)

echo [INFO] API container is running
echo.

REM Run migration script inside container
echo [INFO] Running database migrations...
echo.
docker exec -w /app/src realsense-pose-api python -m db.mongo.migration_runner

if errorlevel 1 (
    echo.
    echo [ERROR] Migration failed!
    echo Please check the logs above for details.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   Migration Completed Successfully!
echo ============================================================
echo.
pause
exit /b 0
