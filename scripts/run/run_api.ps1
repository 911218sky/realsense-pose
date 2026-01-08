. (Join-Path $PSScriptRoot '..\common.ps1')

$ProjectRoot = Initialize-Script -ScriptRoot $PSScriptRoot
$VenvPath = Get-VenvPath -ProjectRoot $ProjectRoot

# ========== 環境設定檔 ==========
$ENV_FILE_DEBUG = '.debug.env'
$ENV_FILE_DEFAULT = '.env'
# ================================

function Load-DotEnv {
  param([string]$Path)
  if (-not (Test-Path $Path)) { return }

  foreach ($line in Get-Content $Path) {
    $t = $line.Trim()
    if ($t.Length -eq 0) { continue }
    if ($t.StartsWith('#')) { continue }
    $idx = $t.IndexOf('=')
    if ($idx -lt 1) { continue }
    $k = $t.Substring(0, $idx).Trim()
    $v = $t.Substring($idx + 1).Trim()
    if ($k.Length -eq 0) { continue }
    Set-Item -Path ("Env:{0}" -f $k) -Value $v
  }
}

Write-Host "[INFO] Repo: $ProjectRoot"

# 優先使用 debug env，沒有的話用 default env
if (Test-Path $ENV_FILE_DEBUG) {
  Write-Host ''
  Write-Host '============================================' -ForegroundColor Yellow
  Write-Host "  DEBUG MODE: Using $ENV_FILE_DEBUG" -ForegroundColor Yellow
  Write-Host '============================================' -ForegroundColor Yellow
  Write-Host ''
  Load-DotEnv -Path $ENV_FILE_DEBUG
} elseif (Test-Path $ENV_FILE_DEFAULT) {
  Write-Host "[INFO] Using $ENV_FILE_DEFAULT"
  Load-DotEnv -Path $ENV_FILE_DEFAULT
}

# Match legacy defaults from run_api.bat
$Port = if ($env:PORT) { [int]$env:PORT } else { 8200 }
$HostName = if ($env:HOST) { $env:HOST } else { 'localhost' }

Write-Host "[INFO] Starting API: http://$HostName`:$Port" -ForegroundColor Green
Write-Host "[INFO] Using venv: $VenvPath" -ForegroundColor Cyan
Write-Host ""
[Console]::Out.Flush()
Start-Sleep -Milliseconds 100

try {
  Invoke-VenvRun -VenvPath $VenvPath -Args @(
    'uvicorn', 'api.main:app',
    '--reload',
    '--reload-exclude', '.venv',
    '--reload-exclude', 'venv',
    '--reload-exclude', '__pycache__',
    '--app-dir', './src',
    '--port', $Port,
    '--host', $HostName
  )
  exit 0
} catch {
  Write-Error $_
  exit 1
}
