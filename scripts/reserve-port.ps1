# Reserve port to avoid Hyper-V dynamic port exclusion
# Auto-elevate to administrator if not running as admin

param(
    [int]$Port = 8100
)

# Check if running as administrator
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "[INFO] Requesting administrator privileges..." -ForegroundColor Yellow
    $scriptPath = $MyInvocation.MyCommand.Path
    Start-Process powershell -Verb RunAs -ArgumentList "-ExecutionPolicy Bypass -File `"$scriptPath`" -Port $Port"
    exit
}

Write-Host "[INFO] Stopping WinNAT service..." -ForegroundColor Yellow
net stop winnat 2>$null

Write-Host "[INFO] Reserving port $Port..." -ForegroundColor Yellow
netsh int ipv4 add excludedportrange protocol=tcp startport=$Port numberofports=1

Write-Host "[INFO] Starting WinNAT service..." -ForegroundColor Yellow
net start winnat

Write-Host ""
Write-Host "[OK] Port $Port reserved successfully!" -ForegroundColor Green
Write-Host "You can now run your API on port $Port."
Write-Host ""
Read-Host "Press Enter to close"
