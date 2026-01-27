<#
.SYNOPSIS
  Merge development branch to main with auto version bump (PowerShell)

.DESCRIPTION
  - Ensure working directory is clean
  - Switch to main branch
  - Pull latest changes
  - Merge development branch
  - Auto bump version and create tag
  - Push to remote
  - Optionally delete development branch

.PARAMETER BranchName
  Development branch to merge (default: develop)

.PARAMETER DeleteBranch
  Delete development branch after merge

.PARAMETER Squash
  Squash commits into single commit

.PARAMETER NoRelease
  Skip version bump and tag creation

.PARAMETER VersionPart
  Which version part to increment: patch, minor, major (default: patch)

.EXAMPLE
  powershell -File scripts\github\merge_to_main.ps1

.EXAMPLE
  powershell -File scripts\github\merge_to_main.ps1 -VersionPart minor

.EXAMPLE
  powershell -File scripts\github\merge_to_main.ps1 -NoRelease

.EXAMPLE
  powershell -File scripts\github\merge_to_main.ps1 -BranchName feature/new-chart -DeleteBranch
#>

param(
    [string]$BranchName = "develop",
    [switch]$DeleteBranch,
    [switch]$Squash,
    [switch]$NoRelease,
    [ValidateSet('patch', 'minor', 'major')]
    [string]$VersionPart
)

$ErrorActionPreference = "Stop"

. "$PSScriptRoot\..\common.ps1"

$root = Initialize-Script -ScriptRoot $PSScriptRoot

# Version helper functions
function Get-LatestVersion {
    $tags = git tag --sort=-version:refname 2>$null | Where-Object { $_ -match '^v?\d+\.\d+\.\d+$' }
    if ($tags) {
        $latest = ($tags | Select-Object -First 1) -replace '^v', ''
        return $latest
    }
    return $null
}

function Get-IncrementedVersion {
    param(
        [string]$CurrentVersion,
        [ValidateSet('major', 'minor', 'patch')]
        [string]$Part
    )
    
    $parts = $CurrentVersion -split '\.'
    $major = [int]$parts[0]
    $minor = [int]$parts[1]
    $patch = [int]$parts[2]
    
    switch ($Part) {
        'major' { $major++; $minor = 0; $patch = 0 }
        'minor' { $minor++; $patch = 0 }
        'patch' { $patch++ }
    }
    
    return "$major.$minor.$patch"
}

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

# Determine version bump
$newVersion = $null
if (-not $NoRelease) {
    $latestVersion = Get-LatestVersion
    
    if (-not $latestVersion) {
        $latestVersion = "1.0.0"
        Write-Host "No existing tags found. Starting from v1.0.0" -ForegroundColor Yellow
        $newVersion = $latestVersion
    } else {
        Write-Host "Latest version: v$latestVersion" -ForegroundColor Cyan
        
        if (-not $VersionPart) {
            Write-Host ""
            Write-Host "Which part to increment?" -ForegroundColor Yellow
            Write-Host "  [1] Patch  $latestVersion -> $(Get-IncrementedVersion $latestVersion 'patch')  (bug fixes)" -ForegroundColor Gray
            Write-Host "  [2] Minor  $latestVersion -> $(Get-IncrementedVersion $latestVersion 'minor')  (new features)" -ForegroundColor Gray
            Write-Host "  [3] Major  $latestVersion -> $(Get-IncrementedVersion $latestVersion 'major')  (breaking changes)" -ForegroundColor Gray
            Write-Host ""
            
            $choice = Read-Host "Enter choice (1/2/3, default: 1)"
            $VersionPart = switch ($choice) {
                '2' { 'minor' }
                '3' { 'major' }
                default { 'patch' }
            }
        }
        
        $newVersion = Get-IncrementedVersion $latestVersion $VersionPart
    }
    
    Write-Host ""
    Write-Host "New version: v$newVersion" -ForegroundColor Green
}

Write-Host ""

# Confirm merge
$confirm = Read-Host "Proceed with merge? (y/N)"
if ($confirm -notmatch "^[yY]") {
    Write-Host "Aborted." -ForegroundColor Yellow
    exit 0
}

Write-Host ""

$totalSteps = if ($NoRelease) { 4 } else { 5 }
$step = 0

# Switch to main
$step++
Write-Host "[$step/$totalSteps] Switching to main..."
git checkout main

# Pull latest
$step++
Write-Host "[$step/$totalSteps] Pulling latest main..."
git pull origin main

# Merge
$step++
Write-Host "[$step/$totalSteps] Merging '$BranchName'..."
if ($Squash) {
    git merge --squash $BranchName
    
    $defaultMsg = "feat: merge $BranchName"
    $commitMsg = Read-Host "Commit message (default: $defaultMsg)"
    if (-not $commitMsg) {
        $commitMsg = $defaultMsg
    }
    git commit -m $commitMsg
} else {
    git merge $BranchName --no-edit
}

# Create tag
if (-not $NoRelease) {
    $step++
    Write-Host "[$step/$totalSteps] Creating tag v$newVersion..."
    git tag -a "v$newVersion" -m "Release v$newVersion"
}

# Push
$step++
Write-Host "[$step/$totalSteps] Pushing to remote..."
git push origin main
if (-not $NoRelease) {
    git push origin "v$newVersion"
}

Write-Host ""
Write-Host "Successfully merged '$BranchName' to main!" -ForegroundColor Green
if (-not $NoRelease) {
    Write-Host "Released version: v$newVersion" -ForegroundColor Green
    Write-Host "GitHub Actions will now build and release." -ForegroundColor Cyan
}

# Delete branch if requested
if ($DeleteBranch) {
    Write-Host ""
    Write-Host "Deleting branch '$BranchName'..."
    
    git branch -d $BranchName
    Write-Host "Deleted local branch '$BranchName'"
    
    $deleteRemote = Read-Host "Delete remote branch 'origin/$BranchName'? (y/N)"
    if ($deleteRemote -match "^[yY]") {
        git push origin --delete $BranchName
        Write-Host "Deleted remote branch 'origin/$BranchName'" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "Current branch: $(git branch --show-current)" -ForegroundColor Cyan
