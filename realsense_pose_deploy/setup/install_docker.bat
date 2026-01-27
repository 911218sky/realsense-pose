@echo off
chcp 65001 >nul
setlocal

echo ============================================
echo   Install Docker Desktop via winget
echo ============================================
echo.

REM Check if Docker is already installed
where docker >nul 2>&1
if %errorlevel%==0 (
    echo Docker is already installed:
    docker --version
    echo.
    echo If you want to reinstall, run: winget uninstall Docker.DockerDesktop
    goto :end
)

echo Installing Docker Desktop...
winget install Docker.DockerDesktop --source winget --accept-package-agreements --accept-source-agreements

if %errorlevel%==0 (
    echo.
    echo ============================================
    echo   Docker Desktop installed successfully!
    echo.
    echo   Please:
    echo   1. Restart your computer
    echo   2. Launch Docker Desktop
    echo   3. Wait for Docker to start
    echo ============================================
) else (
    echo.
    echo [ERROR] Failed to install Docker Desktop.
    echo Please run this script as Administrator.
)

:end
echo.
pause
