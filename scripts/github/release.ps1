<#
.SYNOPSIS
    Push a new version tag to GitHub and trigger specific workflows.

.PARAMETER Version
    Version string (e.g., 1.0.0). If not provided, will auto-increment from latest tag.

.PARAMETER Message
    Optional tag message. Defaults to "Release v{Version}".

.PARAMETER Target
    Which workflow to trigger: 'all', 'docker', 'release'. Defaults to 'all'.

.EXAMPLE
    .\scripts\github\release.ps1                           # Auto-increment, ask which part
    .\scripts\github\release.ps1 -Version 1.0.0
    .\scripts\github\release.ps1 -Version 1.0.0 -Target docker
    .\scripts\github\release.ps1 -Version 1.0.0 -Target release
    .\scripts\github\release.ps1 -Version 1.2.3 -Message "Bug fixes" -Target all
#>

param(
    [string]$Version,
    [string]$Message,

    [ValidateSet('all', 'docker', 'release')]
    [string]$Target = 'all'
)

$ErrorActionPreference = "Stop"

# Function to get latest version tag
function Get-LatestVersion {
    $tags = git tag --sort=-version:refname 2>$null | Where-Object { $_ -match '^v?\d+\.\d+\.\d+$' }
    if ($tags) {
        $latest = ($tags | Select-Object -First 1) -replace '^v', ''
        return $latest
    }
    return $null
}

# Function to increment version
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

# If no version provided, auto-increment
if (-not $Version) {
    $latestVersion = Get-LatestVersion
    
    if (-not $latestVersion) {
        Write-Host "No existing version tags found. Starting from 1.0.0" -ForegroundColor Yellow
        $Version = "1.0.0"
    } else {
        Write-Host "Latest version: v$latestVersion" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "Which part to increment?" -ForegroundColor Yellow
        Write-Host "  [1] Patch  $latestVersion -> $(Get-IncrementedVersion $latestVersion 'patch')  (bug fixes)" -ForegroundColor Gray
        Write-Host "  [2] Minor  $latestVersion -> $(Get-IncrementedVersion $latestVersion 'minor')  (new features)" -ForegroundColor Gray
        Write-Host "  [3] Major  $latestVersion -> $(Get-IncrementedVersion $latestVersion 'major')  (breaking changes)" -ForegroundColor Gray
        Write-Host ""
        
        $choice = Read-Host "Enter choice (1/2/3)"
        
        $Version = switch ($choice) {
            '1' { Get-IncrementedVersion $latestVersion 'patch' }
            '2' { Get-IncrementedVersion $latestVersion 'minor' }
            '3' { Get-IncrementedVersion $latestVersion 'major' }
            default {
                Write-Host "Invalid choice. Defaulting to patch." -ForegroundColor Yellow
                Get-IncrementedVersion $latestVersion 'patch'
            }
        }
    }
    
    Write-Host ""
    Write-Host "New version: v$Version" -ForegroundColor Green
    $confirm = Read-Host "Continue? (Y/n)"
    if ($confirm -eq 'n') {
        Write-Host "Aborted." -ForegroundColor Yellow
        exit 0
    }
}

# Validate version format
if ($Version -notmatch '^\d+\.\d+\.\d+$') {
    Write-Host "Error: Version must be in format X.Y.Z (e.g., 1.0.0)" -ForegroundColor Red
    exit 1
}

$tag = "v$Version"
$Message = if ($Message) { $Message } else { "Release $tag" }

# Check for uncommitted changes
$status = git status --porcelain
if ($status) {
    Write-Host ""
    Write-Host "Warning: You have uncommitted changes:" -ForegroundColor Yellow
    Write-Host ""
    
    $status -split "`n" | ForEach-Object {
        $line = $_.Trim()
        if ($line) {
            $code = $line.Substring(0, 2).Trim()
            $file = $line.Substring(2).Trim()
            
            $statusText = switch ($code) {
                'M'  { "[Modified]  " }
                'A'  { "[Added]     " }
                'D'  { "[Deleted]   " }
                'R'  { "[Renamed]   " }
                '??' { "[Untracked] " }
                'MM' { "[Modified]  " }
                'AM' { "[Added]     " }
                default { "[$code]      " }
            }
            
            Write-Host "  $statusText$file" -ForegroundColor Gray
        }
    }
    
    Write-Host ""
    Write-Host "These changes will NOT be included in this release." -ForegroundColor Yellow
    Write-Host "Consider running: git add . && git commit -m 'your message'" -ForegroundColor Gray
    Write-Host ""
    $confirm = Read-Host "Continue anyway? (y/N)"
    if ($confirm -ne 'y') {
        Write-Host "Aborted." -ForegroundColor Yellow
        exit 0
    }
}

# Check if tag already exists
$existingTag = git tag -l $tag 2>$null
$tagExists = [bool]$existingTag

if ($Target -eq 'all') {
    # Push tag to trigger both workflows
    if ($tagExists) {
        Write-Host "Warning: Tag '$tag' already exists. Replacing..." -ForegroundColor Yellow
        git tag -d $tag 2>$null
        git push origin --delete $tag 2>$null
    }
    
    Write-Host "Creating tag: $tag" -ForegroundColor Cyan
    git tag -a $tag -m $Message
    
    Write-Host "Pushing tag to origin..." -ForegroundColor Cyan
    git push origin $tag
    
    Write-Host ""
    Write-Host "Done! Tag '$tag' pushed to GitHub." -ForegroundColor Green
    Write-Host "Both Docker build and Release workflows will run." -ForegroundColor Green
}
else {
    # Manual trigger specific workflow via GitHub CLI
    $workflowFile = switch ($Target) {
        'docker' { 'docker-build.yml' }
        'release' { 'release.yml' }
    }
    
    $workflowName = switch ($Target) {
        'docker' { 'Docker Build' }
        'release' { 'Release' }
    }
    
    # Check if gh CLI is available
    if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
        Write-Host "Error: GitHub CLI (gh) is required for manual workflow trigger." -ForegroundColor Red
        Write-Host "Install from: https://cli.github.com/" -ForegroundColor Yellow
        exit 1
    }
    
    # Determine ref to use
    $ref = if ($tagExists) { $tag } else { "main" }
    
    Write-Host "Triggering $workflowName workflow on ref: $ref" -ForegroundColor Cyan
    
    if ($Target -eq 'docker') {
        # Pass version to docker workflow
        gh workflow run $workflowFile --ref $ref -f version=$Version
    } else {
        gh workflow run $workflowFile --ref $ref
    }
    
    Write-Host ""
    Write-Host "Done! $workflowName workflow triggered." -ForegroundColor Green
    Write-Host "Check status: gh run list --workflow=$workflowFile" -ForegroundColor Gray
}
