# 清理 Docker 未使用的垃圾（images, containers, volumes, networks, build cache）
# 用法：
#   .\scripts\docker\docker_prune.ps1          # 預設清理（保留使用中的）
#   .\scripts\docker\docker_prune.ps1 --all    # 清理所有未使用的 images（包括 tagged）
#   .\scripts\docker\docker_prune.ps1 --nuke   # 核彈級清理（全部刪光）

. (Join-Path $PSScriptRoot '..\_common.ps1')
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

# 1. 停止的容器
Write-Host '[1/6] Removing stopped containers...'
& docker container prune -f

# 2. 懸空的 images（無 tag）
Write-Host ''
Write-Host '[2/6] Removing dangling images...'
& docker image prune -f

# 3. 未使用的 images（含 tagged，需 --all）
if ($All) {
  Write-Host ''
  Write-Host '[3/6] Removing ALL unused images (including tagged)...'
  & docker image prune -af
} else {
  Write-Host ''
  Write-Host '[3/6] Skipped (use --all to remove tagged images)'
}

# 4. 未使用的 volumes
Write-Host ''
Write-Host '[4/6] Removing unused volumes...'
& docker volume prune -f

# 5. 未使用的 networks
Write-Host ''
Write-Host '[5/6] Removing unused networks...'
& docker network prune -f

# 6. Build cache（最大的垃圾來源）
Write-Host ''
Write-Host '[6/6] Removing build cache...'
if ($Nuke) {
  # 核彈：清除所有 build cache
  & docker builder prune --all -f
  & docker buildx prune --all -f 2>$null
} else {
  # 一般：只清除未使用的
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

