<#
.SYNOPSIS
  Switch to main branch and sync with remote (PowerShell)

.DESCRIPTION
  - Stash uncommitted changes if any
  - Switch to main branch
  - Pull latest changes from remote
  - Optionally restore stashed changes

.PARAMETER NoSync
  Skip pulling from remote

.PARAMETER Stash
  Auto-stash uncommitted changes (will restore after switch)

.EXAMPLE
  powershell -File scripts\github\switch_main.ps1

.EXAMPLE
  powershell -File scripts\github\switch_main.ps1 -NoSync

.EXAMPLE
  powershell -File scripts\github\switch_main.ps1 -Stash
#>

param(
    [switch]$NoSync,
    [switch]$Stash
)

$ErrorActionPreference = "Stop"

. "$PSScriptRoot\..\common.ps1"

$root = Initialize-Script -ScriptRoot $PSScriptRoot

Write-Section "Switch to Main"

$currentBranch = git branch --show-current
Write-Host "Current branch: $currentBranch"

if ($currentBranch -eq "main") {
    Write-Host "Already on main branch" -ForegroundColor Green
    
    if (-not $NoSync) {
        Write-Host "Pulling latest changes..."
        git pull origin main
    }
    exit 0
}

# Check for uncommitted changes
$status = git status --porcelain
$stashed = $false

if ($status) {
    Write-Host "Uncommitted changes detected:" -ForegroundColor Yellow
    git status --short
    Write-Host ""
    
    if ($Stash) {
        Write-Host "Stashing changes..."
        git stash push -m "Auto-stash before switch to main"
        $stashed = $true
    } else {
        $choice = Read-Host "Stash changes and continue? (y/N)"
        if ($choice -match "^[yY]") {
            git stash push -m "Auto-stash before switch to main"
            $stashed = $true
        } else {
            throw "[ERROR] Please commit or stash changes before switching"
        }
    }
}

# Switch to main
Write-Host "Switching to main..."
git checkout main

# Sync with remote
if (-not $NoSync) {
    Write-Host "Pulling latest changes..."
    git pull origin main
}

Write-Host ""
Write-Host "Switched to main" -ForegroundColor Green

# Restore stashed changes
if ($stashed) {
    Write-Host ""
    $restore = Read-Host "Restore stashed changes? (y/N)"
    if ($restore -match "^[yY]") {
        git stash pop
        Write-Host "Stashed changes restored" -ForegroundColor Green
    } else {
        Write-Host "Changes remain in stash. Use 'git stash pop' to restore later." -ForegroundColor Yellow
    }
}
