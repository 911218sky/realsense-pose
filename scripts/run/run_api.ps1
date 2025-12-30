. (Join-Path $PSScriptRoot '..\common.ps1')

$ProjectRoot = Initialize-Script -ScriptRoot $PSScriptRoot
$VenvPath = Join-Path $ProjectRoot 'venv'

Write-Host "[INFO] Repo: $ProjectRoot"

# Match legacy defaults from run_api.bat
$Port = if ($env:PORT) { [int]$env:PORT } else { 8200 }
$HostName = if ($env:HOST) { $env:HOST } else { 'localhost' }

Write-Host "[INFO] Starting API: http://$HostName`:$Port" -ForegroundColor Green
Write-Host "[INFO] Using venv: $VenvPath" -ForegroundColor Cyan
Write-Host ""
[Console]::Out.Flush()
Start-Sleep -Milliseconds 100

try {
  Invoke-CondaRun -VenvPath $VenvPath -Args @(
    'uvicorn', 'api.main:app',
    '--reload',
    '--app-dir', './src',
    '--port', $Port,
    '--host', $HostName
  )
  exit 0
} catch {
  Write-Error $_
  exit 1
}


