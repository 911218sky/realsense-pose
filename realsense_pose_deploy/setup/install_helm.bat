@echo off
chcp 65001 >nul
setlocal

echo ============================================
echo   Install Helm via winget
echo ============================================
echo.

REM Check if Helm is already installed
where helm >nul 2>&1
if %errorlevel%==0 (
    echo Helm is already installed:
    helm version --short
    echo.
    echo If you want to reinstall, run: winget uninstall Helm.Helm
    goto :end
)

echo Installing Helm...
winget install Helm.Helm --source winget --accept-package-agreements --accept-source-agreements

if %errorlevel%==0 (
    echo.
    echo ============================================
    echo   Helm installed successfully!
    echo   Please restart your terminal to use helm.
    echo ============================================
) else (
    echo.
    echo [ERROR] Failed to install Helm.
    echo Please run this script as Administrator.
)

:end
echo.
pause
