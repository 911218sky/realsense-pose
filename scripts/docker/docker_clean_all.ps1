. (Join-Path $PSScriptRoot '..\common.ps1')

$ProjectRoot = Initialize-Script -ScriptRoot $PSScriptRoot
$Compose = Get-ComposeCmd

# Defaults (match .bat behavior)
$Yes = $false
$DoDown = $true
$DownVolumes = $false
$Prune = $true
$PruneAllImages = $true
$PruneVolumes = $true

foreach ($a in $args) {
  switch -Regex ($a) {
    '^(--yes|-y)$' { $Yes = $true; continue }
    '^--safe$' { $PruneAllImages = $false; $PruneVolumes = $false; continue }
    '^--no-down$' { $DoDown = $false; continue }
    '^--with-volumes$' { $DownVolumes = $true; $PruneVolumes = $true; continue }
    '^--all-images$' { $PruneAllImages = $true; continue }
    '^--prune-volumes$' { $PruneVolumes = $true; continue }
    '^--no-prune$' { $Prune = $false; continue }
    '^--nuke$' {
      $Yes = $true
      $DoDown = $true
      $DownVolumes = $true
      $Prune = $true
      $PruneAllImages = $true
      $PruneVolumes = $true
      continue
    }
    default { continue }
  }
}

Write-Host '============================================'
Write-Host "Docker cleanup (project: $ProjectRoot)"
Write-Host '============================================'

if (-not (Test-Path 'docker-compose.yml')) {
  Write-Host "ERROR: docker-compose.yml not found in `"$ProjectRoot`""
  Write-Host 'Run this script from the project root (it can live anywhere under scripts/).'
  Pause-IfInteractive
  exit 1
}

# Preflight: Docker engine must be reachable
& docker info *>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host ''
  Write-Host 'ERROR: Docker engine is not reachable.'
  Write-Host 'This usually means Docker Desktop is not running, or you are not connected to the Linux engine.'
  Write-Host 'Please start Docker Desktop [Linux containers] and try again.'
  Write-Host ''
  Write-Host 'Quick check: run `docker version` in a new terminal.'
  Pause-IfInteractive
  exit 1
}

Write-Host ''
Write-Host 'Plan:'
Write-Host "  - Compose down            : $([int]$DoDown)"
Write-Host "  - Compose remove volumes  : $([int]$DownVolumes)"
Write-Host "  - Docker prune            : $([int]$Prune)"
Write-Host "  - Prune all unused images : $([int]$PruneAllImages)"
Write-Host "  - Prune volumes           : $([int]$PruneVolumes)"
Write-Host ''
Write-Host 'NOTE:'
Write-Host '  - This script does NOT delete host folders like .\data / .\outputs.'
Write-Host '  - With default settings it WILL prune unused Docker volumes (docker garbage).'
Write-Host '    If you want a safer cleanup, run: scripts\docker\docker_clean_all.ps1 --safe'
Write-Host ''

if (-not $Yes) {
  $confirm = Read-Host 'Proceed? (y/N)'
  if ($confirm -notin @('y', 'Y')) {
    Write-Host 'Cancelled.'
    Pause-IfInteractive
    exit 0
  }
}

if ($DoDown) {
  Write-Host ''
  Write-Host '============================================'
  Write-Host "[1/3] $($Compose -join ' ') down --remove-orphans"
  Write-Host '============================================'
  if ($DownVolumes) {
    Invoke-Compose $Compose down --remove-orphans --volumes
  } else {
    Invoke-Compose $Compose down --remove-orphans
  }
  if ($LASTEXITCODE -ne 0) {
    Write-Host 'ERROR: compose down failed.'
    Pause-IfInteractive
    exit 1
  }
} else {
  Write-Host ''
  Write-Host '[1/3] Skipped compose down [--no-down]'
}

Write-Host ''
Write-Host '============================================'
Write-Host '[2/3] Docker prune'
Write-Host '============================================'
if ($Prune) {
  $pruneArgs = @('-f')
  if ($PruneAllImages) { $pruneArgs += @('-a') }
  if ($PruneVolumes) { $pruneArgs += @('--volumes') }

  & docker system prune @pruneArgs
  if ($LASTEXITCODE -ne 0) {
    Write-Host 'ERROR: docker system prune failed.'
    Pause-IfInteractive
    exit 1
  }

  # Builder cache can be large; prune aggressively
  Write-Host ''
  Write-Host 'Cleaning build cache...'
  
  # Prune all builders (including --mount=type=cache)
  & docker builder prune --all -f 2>$null
  
  # Prune buildx cache
  & docker buildx prune --all -f 2>$null
  
  # Remove user-created buildx builders (skip system builders)
  $builders = docker buildx ls --format "{{.Name}}" 2>$null
  foreach ($b in $builders) {
    # Skip: empty, default, desktop-linux (Docker Desktop built-in)
    if ($b -and $b -notmatch '^\s*$' -and $b -notin @('default', 'desktop-linux')) {
      Write-Host "  Removing builder: $b"
      & docker buildx rm $b 2>$null
    }
  }
} else {
  Write-Host 'Skipped docker prune [--no-prune]'
}

Write-Host ''
Write-Host '============================================'
Write-Host '[3/3] Summary'
Write-Host '============================================'
& docker ps -a
Write-Host ''
& docker images

Write-Host ''
Write-Host 'Done.'
Pause-IfInteractive
exit 0


