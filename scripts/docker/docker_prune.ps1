# Clean Docker unused resources (images, containers, volumes, networks, build cache)
# Usage:
#   .\scripts\docker\docker_prune.ps1          # Default cleanup (keep in-use resources)
#   .\scripts\docker\docker_prune.ps1 --all    # Clean all unused images (including tagged)
#   .\scripts\docker\docker_prune.ps1 --nuke   # Nuclear cleanup (delete everything)

. (Join-Path $PSScriptRoot '..\common.ps1')
$null = Initialize-Script -ScriptRoot $PSScriptRoot

$All = $false
$Nuke = $false

foreach ($a in $args) {
  switch -Regex ($a) {
    '^(--all|-a)$' { $All = $true }
    '^--nuke$' { $Nuke = $true; $All = $true }
  }
}

# Preflight
& docker info *>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host 'ERROR: Docker engine not reachable. Start Docker Desktop first.'
  Pause-IfInteractive
  exit 1
}

Write-Host ''
Write-Host '=========================================='
Write-Host 'Docker Prune - Clean Unused Resources'
Write-Host '=========================================='
Write-Host ''

# 1. Stopped containers
Write-Host '[1/6] Removing stopped containers...'
& docker container prune -f

# 2. Dangling images (no tag)
Write-Host ''
Write-Host '[2/6] Removing dangling images...'
& docker image prune -f

# 3. Unused images (including tagged, requires --all)
if ($All) {
  Write-Host ''
  Write-Host '[3/6] Removing ALL unused images (including tagged)...'
  & docker image prune -af
} else {
  Write-Host ''
  Write-Host '[3/6] Skipped (use --all to remove tagged images)'
}

# 4. Unused volumes
Write-Host ''
Write-Host '[4/6] Removing unused volumes...'
& docker volume prune -f

# 5. Unused networks
Write-Host ''
Write-Host '[5/6] Removing unused networks...'
& docker network prune -f

# Clean old backups
Write-Host ''
Write-Host '[6/6] Removing build cache...'
if ($Nuke) {
  # Nuclear: remove all build cache
  & docker builder prune --all -f
  & docker buildx prune --all -f 2>$null
} else {
  # Normal: only remove unused
  & docker builder prune -f
  & docker buildx prune -f 2>$null
}

# Summary
Write-Host ''
Write-Host '=========================================='
Write-Host 'Disk Usage Summary'
Write-Host '=========================================='
& docker system df

Write-Host ''
Write-Host 'Done!'
Pause-IfInteractive
exit 0

