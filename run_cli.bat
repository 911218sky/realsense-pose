@echo off
setlocal

REM Get this .bat folder
set "SCRIPT_DIR=%~dp0"
set "PS1=%SCRIPT_DIR%run_cli.ps1"

REM Check PS1 exists
if not exist "%PS1%" (
    echo ERROR: Cannot find "%PS1%". Make sure run_cli.ps1 is in the same folder as this batch file.
    endlocal
    exit /b 1
)

REM Prefer pwsh (PowerShell Core) if available, otherwise fallback to Windows PowerShell
where pwsh >nul 2>&1
if %ERRORLEVEL%==0 (
    set "PWSH_CMD=pwsh"
) else (
    set "PWSH_CMD=powershell"
)

REM Invoke PowerShell and forward all args.
REM Use -Command so we can exit with the script's $LASTEXITCODE.
REM The -- stops PowerShell's parameter parsing so subsequent tokens are passed as positional args.
%PWSH_CMD% -NoProfile -ExecutionPolicy Bypass -Command " & { & '%PS1%' @args; exit $LASTEXITCODE }" -- %*

REM capture and propagate exit code
set "EXITCODE=%ERRORLEVEL%"
endlocal & exit /b %EXITCODE%