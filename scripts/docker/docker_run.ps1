. (Join-Path $PSScriptRoot '..\_common.ps1')

$ProjectRoot = Initialize-Script -ScriptRoot $PSScriptRoot

$DoBuild = $false
if ($args.Count -ge 1 -and $args[0] -ieq '--build') { $DoBuild = $true }

$Compose = Get-ComposeCmd

Write-Host '============================================'
Write-Host "Docker run (project: $ProjectRoot)"
Write-Host '============================================'

if (-not (Test-Path 'docker-compose.yml')) {
  Write-Host "ERROR: docker-compose.yml not found in `"$ProjectRoot`""
  Pause-IfInteractive
  exit 1
}

# Create .env if missing (do NOT overwrite existing)
if (-not (Test-Path '.env')) {
  if (Test-Path 'env.example') {
    Copy-Item 'env.example' '.env' -Force
    Write-Host 'Created .env from env.example'
  } else {
    Write-Host 'WARN: env.example not found; continuing without .env'
  }
} else {
  Write-Host 'Using existing .env'
}

# Create host folders used by bind mounts (safe no-op if already exist)
New-Item -ItemType Directory -Force -Path 'data' | Out-Null
New-Item -ItemType Directory -Force -Path 'outputs' | Out-Null
New-Item -ItemType Directory -Force -Path 'data\mongo' | Out-Null
New-Item -ItemType Directory -Force -Path 'data\redis' | Out-Null
New-Item -ItemType Directory -Force -Path 'backups' | Out-Null

Write-Host ''
if ($DoBuild) {
  Write-Host "Running: $($Compose -join ' ') up --build -d"
  Invoke-Compose $Compose up --build -d
} else {
  Write-Host 'Pulling: api image (from docker-compose.yml: API_IMAGE/API_TAG)'
  Invoke-Compose $Compose pull api
  Write-Host ''
  Write-Host "Running: $($Compose -join ' ') up -d"
  Invoke-Compose $Compose up -d
}
if ($LASTEXITCODE -ne 0) {
  Write-Host 'ERROR: docker compose up failed.'
  Write-Host 'Tip: run `docker compose logs api --tail 200` to see why.'
  Pause-IfInteractive
  exit 1
}

Write-Host ''
Invoke-Compose $Compose ps

Write-Host ''
Write-Host '============================================'
Write-Host 'Done.'
Write-Host 'API:   http://localhost:8100/v1'
Write-Host 'DOCS:  http://localhost:8100/docs   (when IS_PROD=0)'
Write-Host '============================================'
Pause-IfInteractive
exit 0


