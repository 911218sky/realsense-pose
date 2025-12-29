@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM ============================================================
REM Clean (Windows cmd)
REM - 停止並移除此專案的容器、網路、volumes
REM - 可選擇是否刪除 data 資料夾
REM ============================================================

cd /d "%~dp0"

echo.
echo ==========================================
echo realsense_pose - Environment Cleanup
echo ==========================================
echo.

REM Check Docker
docker version >nul 2>&1
if errorlevel 1 (
  echo ERROR: Docker is not available. Please install/start Docker Desktop.
  pause
  exit /b 1
)

echo [1/4] Stopping and removing containers, networks, volumes...
docker compose --env-file .env -f docker-compose.yml down -v --remove-orphans
if errorlevel 1 (
  echo WARNING: docker compose down failed, continuing...
)

echo.
echo [2/4] Removing project images...
for %%i in (
  "realsense_pose_api"
  "realsense_pose_api_dev"
  "realsense_pose_nginx"
  "realsense_pose_fail2ban"
) do (
  docker image rm %%~i 2>nul && echo   Removed image: %%~i
)

REM Also try to remove the ghcr image if exists
for /f "tokens=*" %%i in ('docker images --filter "reference=ghcr.io/911218sky/realsense_pose*" -q 2^>nul') do (
  docker image rm %%i 2>nul && echo   Removed ghcr image: %%i
)

echo.
echo [3/4] Removing named volumes...
for %%v in (
  "realsense_pose_nginx_logs"
  "realsense_pose_fail2ban_data"
) do (
  docker volume rm %%~v 2>nul && echo   Removed volume: %%~v
)

echo.
echo [4/4] Data directories cleanup...
echo.
echo Current data directories:
if exist "..\data" (
  echo   - data\mongo
  echo   - data\redis
  echo   - data\npy
  echo   - data\bag
)
if exist "..\outputs" echo   - outputs

echo.
set /p CLEAN_DATA="Delete data directories? (y/N): "
if /i "!CLEAN_DATA!"=="y" (
  echo Removing data directories...
  if exist "..\data\mongo" rmdir /s /q "..\data\mongo" && echo   Removed data\mongo
  if exist "..\data\redis" rmdir /s /q "..\data\redis" && echo   Removed data\redis
  if exist "..\data\npy" rmdir /s /q "..\data\npy" && echo   Removed data\npy
  if exist "..\data\bag" rmdir /s /q "..\data\bag" && echo   Removed data\bag
  if exist "..\outputs" rmdir /s /q "..\outputs" && echo   Removed outputs
  echo Data directories removed.
) else (
  echo Skipped data directory cleanup.
)

echo.
echo ==========================================
echo Cleanup Complete!
echo ==========================================
echo.
echo To redeploy, run: deploy.bat
echo.
pause
exit /b 0
