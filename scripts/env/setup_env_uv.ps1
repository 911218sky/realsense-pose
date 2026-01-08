param(
  [switch]$SkipPose
)

. (Join-Path $PSScriptRoot '..\common.ps1')

$ProjectRoot = Initialize-Script -ScriptRoot $PSScriptRoot
$VenvPath = Join-Path $ProjectRoot '.venv'

function Ensure-EnvFile {
  if (-not (Test-Path '.env')) {
    if (Test-Path 'env.example') {
      Copy-Item 'env.example' '.env' -Force
      Write-Host '[INFO] Created .env from env.example'
    }
  }
}

function Ensure-Uv {
  if (Get-Command uv -ErrorAction SilentlyContinue) {
    Write-Host '[INFO] uv found.'
    return
  }

  Write-Host '[INFO] uv not found. Installing via winget...'
  try {
    & winget install --id=astral-sh.uv -e --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) { throw 'winget install failed.' }
    
    # Refresh PATH
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
      throw 'uv installed but not found in PATH. Please open a NEW terminal and re-run setup_env_uv.ps1.'
    }
    Write-Host '[INFO] uv installed successfully.'
  } catch {
    throw "Failed to install uv: $_"
  }
}

try {
  Set-Location $ProjectRoot
  Write-Host "[INFO] Repo: $ProjectRoot"

  Ensure-EnvFile
  Ensure-Uv

  Write-Host ''
  Write-Host '[INFO] Installing dependencies via uv sync...' -ForegroundColor Yellow

  if (-not $SkipPose) {
    Write-Host '[INFO] Installing all extras (db + pose)...' -ForegroundColor Cyan
    & uv sync --extra db --extra pose
  } else {
    Write-Host '[INFO] Installing db extras only (SkipPose)...' -ForegroundColor Cyan
    & uv sync --extra db
  }

  if ($LASTEXITCODE -ne 0) { throw 'uv sync failed.' }

  Write-Host ''
  Write-Host '[DONE] Environment ready!' -ForegroundColor Green
  Write-Host '       Activate: .\.venv\Scripts\Activate.ps1'
  Write-Host '       Next: scripts\run\run_api_with_db.ps1'
  exit 0
} catch {
  Write-Error $_
  exit 1
}
