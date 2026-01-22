@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

echo ============================================
echo   Docker Registry Login
echo ============================================
echo.

:: Check if Docker is running
docker info >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Docker is not running. Please start Docker Desktop first.
    pause
    exit /b 1
)

echo Select registry to login:
echo   [1] GitHub Container Registry (ghcr.io)
echo   [2] Docker Hub
echo   [3] Both
echo.
set /p CHOICE="Enter choice (1/2/3): "

if "%CHOICE%"=="1" goto :ghcr
if "%CHOICE%"=="2" goto :dockerhub
if "%CHOICE%"=="3" goto :both
echo Invalid choice.
pause
exit /b 1

:ghcr
echo.
echo === GitHub Container Registry (ghcr.io) ===
echo You need a GitHub Personal Access Token (PAT) with 'read:packages' scope.
echo Create one at: https://github.com/settings/tokens
echo.
set /p GH_USER="GitHub Username: "
set /p GH_TOKEN="GitHub Token (PAT): "
echo.
echo %GH_TOKEN%| docker login ghcr.io -u %GH_USER% --password-stdin
if %ERRORLEVEL% equ 0 (
    echo [OK] Successfully logged in to ghcr.io
) else (
    echo [ERROR] Failed to login to ghcr.io
)
goto :done

:dockerhub
echo.
echo === Docker Hub ===
echo.
docker login
goto :done

:both
echo.
echo === Docker Hub ===
docker login
echo.
echo === GitHub Container Registry (ghcr.io) ===
echo You need a GitHub Personal Access Token (PAT) with 'read:packages' scope.
echo Create one at: https://github.com/settings/tokens
echo.
set /p GH_USER="GitHub Username: "
set /p GH_TOKEN="GitHub Token (PAT): "
echo.
echo %GH_TOKEN%| docker login ghcr.io -u %GH_USER% --password-stdin
if %ERRORLEVEL% equ 0 (
    echo [OK] Successfully logged in to ghcr.io
) else (
    echo [ERROR] Failed to login to ghcr.io
)
goto :done

:done
echo.
echo ============================================
echo   Login complete!
echo ============================================
pause
