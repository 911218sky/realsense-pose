. (Join-Path $PSScriptRoot '..\common.ps1')

$ProjectRoot = Initialize-Script -ScriptRoot $PSScriptRoot
$VenvPath = Join-Path $ProjectRoot 'venv'

function Ensure-EnvFile {
  if (-not (Test-Path '.env')) {
    if (Test-Path 'env.example') {
      Copy-Item 'env.example' '.env' -Force
      Write-Host '[INFO] Created .env from env.example'
    }
  }
}

function Ensure-Conda {
  if (Get-Command conda -ErrorAction SilentlyContinue) {
    Write-Host '[INFO] conda found.'
    return
  }

  if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    throw 'conda not found and winget not found. Please install "App Installer" (winget) OR install Miniconda manually, then re-run setup_env.ps1.'
  }

  Write-Host '[INFO] conda not found. Installing Miniconda via winget...'
  & winget install -e --id Anaconda.Miniconda3 --accept-source-agreements --accept-package-agreements
  if ($LASTEXITCODE -ne 0) { throw 'winget install failed.' }

  # PATH may not be updated in the current shell; try common locations
  $candidates = @(
    Join-Path $env:USERPROFILE 'miniconda3\Scripts\conda.exe'
    Join-Path $env:LOCALAPPDATA 'miniconda3\Scripts\conda.exe'
    'C:\ProgramData\Miniconda3\Scripts\conda.exe'
    'C:\Program Files\Miniconda3\Scripts\conda.exe'
  ) | Where-Object { $_ -and (Test-Path $_) }

  if ($candidates.Count -eq 0) {
    throw 'Miniconda installed but conda was not found in common locations. Please open a NEW terminal and re-run setup_env.ps1.'
  }

  $condaExe = $candidates[0]
  $condaScripts = Split-Path $condaExe -Parent
  $condaBase = (Resolve-Path (Join-Path $condaScripts '..')).Path

  $addPath = "$condaBase;$condaBase\Scripts;$condaBase\Library\bin;$condaBase\condabin"
  $env:Path = "$addPath;$env:Path"
  Write-Host "[INFO] Added Miniconda to PATH for current session: $condaBase"

  # Persist to user's PATH (best-effort)
  try {
    $p = [Environment]::GetEnvironmentVariable('Path', 'User')
    if ([string]::IsNullOrWhiteSpace($p)) {
      [Environment]::SetEnvironmentVariable('Path', $addPath, 'User')
    } elseif ($p -notlike ('*' + $addPath + '*')) {
      [Environment]::SetEnvironmentVariable('Path', $addPath + ';' + $p, 'User')
    }
  } catch {}

  if (-not (Get-Command conda -ErrorAction SilentlyContinue)) {
    throw 'conda still not found in current shell. Please open a NEW terminal and re-run setup_env.ps1.'
  }

  Write-Host '[INFO] conda now available.'
}

try {
  Set-Location $ProjectRoot
  Write-Host "[INFO] Repo: $ProjectRoot"

  Ensure-EnvFile
  Ensure-Conda

  # Create conda env if missing
  if (-not (Test-Path (Join-Path $VenvPath 'conda-meta'))) {
    Write-Host '[INFO] Creating conda env at .\venv, python=3.11 ...' -ForegroundColor Yellow
    Write-Host ''
    & conda create --live-stream -p $VenvPath -c conda-forge python=3.11 -y
    if ($LASTEXITCODE -ne 0) { throw 'conda create failed.' }
    Write-Host ''
    Write-Host '[SUCCESS] Conda env created!' -ForegroundColor Green
  } else {
    Write-Host '[INFO] Conda env already exists: .\venv' -ForegroundColor Cyan
  }

  Write-Host ''
  Write-Host '[INFO] Installing Python deps...' -ForegroundColor Yellow
  Write-Host '[1/3] Upgrading pip...' -ForegroundColor Cyan
  Invoke-CondaRun -VenvPath $VenvPath -Args @('python', '-m', 'pip', 'install', '--upgrade', 'pip')
  
  Write-Host ''
  Write-Host '[2/3] Installing requirements.txt...' -ForegroundColor Cyan
  Invoke-CondaRun -VenvPath $VenvPath -Args @('pip', 'install', '-r', 'requirements.txt')
  
  Write-Host ''
  Write-Host '[3/3] Installing requirements_db.txt...' -ForegroundColor Cyan
  Invoke-CondaRun -VenvPath $VenvPath -Args @('pip', 'install', '-r', 'requirements_db.txt')

  Write-Host '[DONE] Environment ready.'
  Write-Host '       Next: scripts\run\run_api_with_db.ps1'
  exit 0
} catch {
  Write-Error $_
  exit 1
}


