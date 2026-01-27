@echo off
setlocal

echo.
echo ==========================================
echo Docker Prune - Clean Unused Resources
echo ==========================================
echo.

:: Check Docker
docker info >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Docker engine not reachable. Start Docker Desktop first.
    pause
    exit /b 1
)

echo [1/6] Removing stopped containers...
docker container prune -f

echo.
echo [2/6] Removing dangling images...
docker image prune -f

echo.
echo [3/6] Removing ALL unused images...
docker image prune -af

echo.
echo [4/6] Removing unused volumes...
docker volume prune -f

echo.
echo [5/6] Removing unused networks...
docker network prune -f

echo.
echo [6/6] Removing build cache...
docker builder prune --all -f
docker buildx prune --all -f 2>nul

echo.
echo ==========================================
echo Disk Usage Summary
echo ==========================================
docker system df

echo.
echo Done!
pause
