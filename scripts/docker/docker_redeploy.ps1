. (Join-Path $PSScriptRoot '..\common.ps1')

$ProjectRoot = Initialize-Script -ScriptRoot $PSScriptRoot
$Compose = Get-ComposeCmd

Write-Host '============================================'
Write-Host '[1/4] Checking docker-compose.yml ...'
Write-Host '============================================'
if (-not (Test-Path 'docker-compose.yml')) {
  Write-Host "docker-compose.yml not found in `"$ProjectRoot`""
  Write-Host 'Please run this script from the project root.'
  Pause-IfInteractive
  exit 1
}

Write-Host ''
Write-Host '============================================'
Write-Host '[2/4] compose down --remove-orphans --volumes'
Write-Host '============================================'
Invoke-Compose $Compose down --remove-orphans --volumes
if ($LASTEXITCODE -ne 0) {
  Write-Host 'compose down failed.'
  Pause-IfInteractive
  exit 1
}

Write-Host ''
Write-Host '============================================'
Write-Host '[3/4] compose up -d'
Write-Host '============================================'
Invoke-Compose $Compose up -d
if ($LASTEXITCODE -ne 0) {
  Write-Host 'compose up -d failed.'
  Pause-IfInteractive
  exit 1
}

Write-Host ''
Write-Host '============================================'
Write-Host 'Done. All services are redeployed.'
Write-Host '============================================'
Invoke-Compose $Compose ps

Write-Host ''
Pause-IfInteractive
exit 0


