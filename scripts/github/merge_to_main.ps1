<#
.SYNOPSIS
  Merge development branch to main (PowerShell)

.DESCRIPTION
  - Ensure working directory is clean
  - Switch to main branch
  - Pull latest changes
  - Merge development branch
  - Push to remote
  - Optionally delete development branch

.PARAMETER BranchName
  Development branch to merge (default: develop)

.PARAMETER DeleteBranch
  Delete development branch after merge

.PARAMETER Squash
  Squash commits into single commit

.EXAMPLE
  powershell -File scripts\github\merge_to_main.ps1

.EXAMPLE
  powershell -File scripts\github\merge_to_main.ps1 -BranchName feature/new-chart -DeleteBranch

.EXAMPLE
  powershell -File scripts\github\merge_to_main.ps1 -Squash
#>

param(
    [string]$BranchName = "develop",
    [switch]$DeleteBranch,
    [switch]$Squash
)

$ErrorActionPreference = "Stop"

. "$PSScriptRoot\..\common.ps1"

$root = Initialize-Script -ScriptRoot $PSScriptRoot

Write-Section "Merge to Main"

# Check for uncommitted changes
$status = git status --porcelain
if ($status) {
    Write-Host "Uncommitted changes detected:" -ForegroundColor Yellow
    git status --short
    Write-Host ""
    throw "[ERROR] Please commit or stash changes before merging"
}

$currentBranch = git branch --show-current
Write-Host "Current branch: $currentBranch"
Write-Host "Source branch: $BranchName"
Write-Host "Target branch: main"
Write-Host ""

# Check if source branch exists
$branchExists = git branch --list $BranchName | Where-Object { $_.Trim() -replace '^\* ', '' -eq $BranchName }
if (-not $branchExists) {
    throw "[ERROR] Branch '$BranchName' does not exist"
}

# Get commit count to merge
$commitCount = (git rev-list --count main..$BranchName 2>$null)
if ($commitCount -eq 0) {
    Write-Host "No commits to merge from '$BranchName' to main" -ForegroundColor Yellow
    exit 0
}

Write-Host "Commits to merge: $commitCount"
Write-Host ""

# Show commits to be merged
Write-Host "Commits:" -ForegroundColor Cyan
git log main..$BranchName --oneline
Write-Host ""

# Confirm merge
$confirm = Read-Host "Proceed with merge? (y/N)"
if ($confirm -notmatch "^[yY]") {
    Write-Host "Aborted." -ForegroundColor Yellow
    exit 0
}

Write-Host ""

# Switch to main
Write-Host "[1/4] Switching to main..."
git checkout main

# Pull latest
Write-Host "[2/4] Pulling latest main..."
git pull origin main

# Merge
Write-Host "[3/4] Merging '$BranchName'..."
if ($Squash) {
    git merge --squash $BranchName
    
    # For squash merge, we need to commit manually
    $defaultMsg = "feat: merge $BranchName"
    $commitMsg = Read-Host "Commit message (default: $defaultMsg)"
    if (-not $commitMsg) {
        $commitMsg = $defaultMsg
    }
    git commit -m $commitMsg
} else {
    git merge $BranchName --no-edit
}

# Push
Write-Host "[4/4] Pushing to remote..."
git push origin main

Write-Host ""
Write-Host "Successfully merged '$BranchName' to main!" -ForegroundColor Green

# Delete branch if requested
if ($DeleteBranch) {
    Write-Host ""
    Write-Host "Deleting branch '$BranchName'..."
    
    # Delete local branch
    git branch -d $BranchName
    Write-Host "Deleted local branch '$BranchName'"
    
    # Delete remote branch
    $deleteRemote = Read-Host "Delete remote branch 'origin/$BranchName'? (y/N)"
    if ($deleteRemote -match "^[yY]") {
        git push origin --delete $BranchName
        Write-Host "Deleted remote branch 'origin/$BranchName'" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "Current branch: $(git branch --show-current)" -ForegroundColor Cyan
