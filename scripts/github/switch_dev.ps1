<#
.SYNOPSIS
  Create or switch to development branch (PowerShell)

.DESCRIPTION
  - Check if development branch exists
  - Create it from main if not exists
  - Switch to development branch
  - Optionally sync with remote

.PARAMETER BranchName
  Development branch name (default: develop)

.PARAMETER FromBranch
  Base branch to create from (default: main)

.PARAMETER Sync
  Sync with remote before switching

.EXAMPLE
  powershell -File scripts\github\dev_branch.ps1

.EXAMPLE
  powershell -File scripts\github\dev_branch.ps1 -BranchName feature/new-chart

.EXAMPLE
  powershell -File scripts\github\dev_branch.ps1 -Sync
#>

param(
    [string]$BranchName = "develop",
    [string]$FromBranch = "main",
    [switch]$Sync
)

$ErrorActionPreference = "Stop"

. "$PSScriptRoot\..\common.ps1"

$root = Initialize-Script -ScriptRoot $PSScriptRoot

Write-Section "Development Branch"

# Get current branch
$currentBranch = git branch --show-current
Write-Host "Current branch: $currentBranch"
Write-Host "Target branch: $BranchName"
Write-Host ""

# Sync with remote if requested
if ($Sync) {
    Write-Host "Fetching from remote..."
    git fetch origin
    Write-Host ""
}

# Check if branch exists locally
$localBranchExists = git branch --list $BranchName | Where-Object { $_.Trim() -replace '^\* ', '' -eq $BranchName }

# Check if branch exists on remote
$remoteBranchExists = git branch -r --list "origin/$BranchName" | Where-Object { $_ -match "origin/$BranchName$" }

if ($localBranchExists) {
    # Branch exists locally, just switch to it
    Write-Host "Branch '$BranchName' exists locally"
    
    if ($currentBranch -eq $BranchName) {
        Write-Host "Already on branch '$BranchName'" -ForegroundColor Green
    } else {
        Write-Host "Switching to '$BranchName'..."
        git checkout $BranchName
        Write-Host "Switched to '$BranchName'" -ForegroundColor Green
    }
    
    # Optionally pull latest changes
    if ($Sync -and $remoteBranchExists) {
        Write-Host "Pulling latest changes..."
        git pull origin $BranchName
    }
} elseif ($remoteBranchExists) {
    # Branch exists on remote but not locally
    Write-Host "Branch '$BranchName' exists on remote, checking out..."
    git checkout -b $BranchName origin/$BranchName
    Write-Host "Created local branch '$BranchName' from remote" -ForegroundColor Green
} else {
    # Branch doesn't exist, create it
    Write-Host "Branch '$BranchName' does not exist"
    Write-Host "Creating from '$FromBranch'..."
    
    # Make sure we have the latest base branch
    if ($Sync) {
        git checkout $FromBranch
        git pull origin $FromBranch
    }
    
    # Create and switch to new branch
    git checkout -b $BranchName $FromBranch
    Write-Host "Created and switched to '$BranchName'" -ForegroundColor Green
    
    # Ask if user wants to push to remote
    $pushToRemote = Read-Host "Push '$BranchName' to remote? (y/N)"
    if ($pushToRemote -match "^[yY]") {
        git push -u origin $BranchName
        Write-Host "Pushed '$BranchName' to remote" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "Current branch: $(git branch --show-current)" -ForegroundColor Cyan
