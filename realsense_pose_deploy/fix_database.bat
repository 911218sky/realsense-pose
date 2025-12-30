@echo off
REM ============================================================================
REM Database Migration/Fix Script for Deployment
REM ============================================================================
REM This script runs database migrations inside the Docker container.
REM It should be run after updating to a new version.
REM ============================================================================

setlocal enabledelayedexpansion

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
    echo   docker compose up -d
    echo.
    pause
    exit /b 1
)

echo [INFO] API container is running
echo.

REM Run migration script inside container
echo [INFO] Running database migrations...
echo.
docker exec realsense-pose-api python -m src.db.mongo.migration_runner

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
echo Next steps:
echo   1. Verify API is working: http://localhost:8100/v1/docs
echo   2. Check logs: docker compose logs api
echo.

pause
exit /b 0
