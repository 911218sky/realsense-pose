<#
.SYNOPSIS
    Delete all versions of a package from GitHub Container Registry (ghcr.io).

.PARAMETER Package
    Package name (default: realsense-pose)

.PARAMETER Keep
    Number of latest tagged versions to keep (default: 3)

.PARAMETER All
    Delete all versions (ignore Keep)

.PARAMETER DryRun
    Show what would be deleted without actually deleting

.EXAMPLE
    .\scripts\github\clean-ghcr.ps1              # Keep latest 3
    .\scripts\github\clean-ghcr.ps1 -Keep 5      # Keep latest 5
    .\scripts\github\clean-ghcr.ps1 -All         # Delete all
    .\scripts\github\clean-ghcr.ps1 -DryRun      # Preview only
#>

param(
    [string]$Package = "realsense-pose",
    [int]$Keep = 3,
    [switch]$All,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

# If -All is specified, delete everything
if ($All) {
    $Keep = 0
}

# Check if gh CLI is available
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Write-Host "Error: GitHub CLI (gh) is required." -ForegroundColor Red
    Write-Host "Install from: https://cli.github.com/" -ForegroundColor Yellow
    exit 1
}

# Check if logged in
$authStatus = gh auth status 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Error: Not logged in to GitHub CLI. Run 'gh auth login' first." -ForegroundColor Red
    exit 1
}

# Get repo info
$repoInfo = gh repo view --json owner,name 2>$null | ConvertFrom-Json
if (-not $repoInfo) {
    Write-Host "Error: Could not determine repo info. Run this from within a git repo." -ForegroundColor Red
    exit 1
}

$owner = $repoInfo.owner.login
$repo = $repoInfo.name

Write-Host "Owner: $owner" -ForegroundColor Cyan
Write-Host "Repo: $repo" -ForegroundColor Cyan
Write-Host "Package: $Package" -ForegroundColor Cyan
Write-Host ""

# Get all versions - try user endpoint first, then org endpoint
Write-Host "Fetching package versions..." -ForegroundColor Yellow

$allVersions = @()
$page = 1
$perPage = 100
$apiBase = "users/$owner"

# Try user endpoint first
$testResponse = gh api "$apiBase/packages/container/$Package/versions?per_page=1" 2>&1
if ($testResponse -match "404" -or $testResponse -match "Not Found") {
    # Try org endpoint
    $apiBase = "orgs/$owner"
    $testResponse = gh api "$apiBase/packages/container/$Package/versions?per_page=1" 2>&1
}

if ($testResponse -match "404" -or $testResponse -match "Not Found") {
    Write-Host "Package '$Package' not found. Checking available packages..." -ForegroundColor Yellow
    
    # List available packages
    $packages = gh api "users/$owner/packages?package_type=container" 2>$null | ConvertFrom-Json
    if ($packages -and $packages.Count -gt 0) {
        Write-Host "Available packages:" -ForegroundColor Cyan
        $packages | ForEach-Object { Write-Host "  - $($_.name)" }
    } else {
        Write-Host "No container packages found for user $owner" -ForegroundColor Yellow
    }
    exit 1
}

# Fetch all pages - try different API endpoints
$endpoints = @(
    "users/$owner/packages/container/$Package/versions",
    "user/packages/container/$Package/versions"
)

foreach ($endpoint in $endpoints) {
    Write-Host "Trying: $endpoint" -ForegroundColor Gray
    $page = 1
    $allVersions = @()
    
    do {
        $response = gh api "$endpoint`?per_page=$perPage&page=$page" 2>$null
        if (-not $response -or $response -match "Not Found") { break }
        
        $pageVersions = $response | ConvertFrom-Json
        if (-not $pageVersions -or $pageVersions.Count -eq 0) { break }
        
        $allVersions += $pageVersions
        Write-Host "  Fetched page $page ($($allVersions.Count) versions so far)..." -ForegroundColor Gray
        $page++
    } while ($pageVersions.Count -eq $perPage)
    
    if ($allVersions.Count -gt 0) {
        $versions = $allVersions
        $apiBase = $endpoint -replace "/versions$", ""
        break
    }
}

if (-not $versions -or $versions.Count -eq 0) {
    Write-Host "No versions found for package '$Package'." -ForegroundColor Yellow
    exit 0
}

Write-Host "Found $($versions.Count) versions." -ForegroundColor Cyan

# Sort by created_at descending and determine which to delete
$sorted = $versions | Sort-Object { 
    if ($_.created_at) { [datetime]$_.created_at } else { [datetime]::MinValue }
} -Descending

$toDelete = @()
$toKeep = @()

for ($i = 0; $i -lt $sorted.Count; $i++) {
    $v = $sorted[$i]
    $tags = ($v.metadata.container.tags -join ", ")
    if (-not $tags) { $tags = "(untagged)" }
    
    if ($Keep -gt 0 -and $i -lt $Keep -and $v.metadata.container.tags.Count -gt 0) {
        $toKeep += [PSCustomObject]@{
            Id = $v.id
            Tags = $tags
            CreatedAt = $v.created_at
        }
    } else {
        $toDelete += [PSCustomObject]@{
            Id = $v.id
            Tags = $tags
            CreatedAt = $v.created_at
        }
    }
}

if ($toKeep.Count -gt 0) {
    Write-Host "`nKeeping $($toKeep.Count) versions:" -ForegroundColor Green
    $toKeep | ForEach-Object { Write-Host "  - $($_.Tags) ($($_.CreatedAt))" -ForegroundColor Green }
}

if ($toDelete.Count -eq 0) {
    Write-Host "`nNothing to delete." -ForegroundColor Yellow
    exit 0
}

Write-Host "`nWill delete $($toDelete.Count) versions:" -ForegroundColor Red
$toDelete | ForEach-Object { Write-Host "  - $($_.Tags) ($($_.CreatedAt))" -ForegroundColor Red }

if ($DryRun) {
    Write-Host "`n[DRY RUN] No changes made." -ForegroundColor Yellow
    exit 0
}

# Confirm
Write-Host ""
$confirm = Read-Host "Are you sure you want to delete these versions? (y/N)"
if ($confirm -ne 'y') {
    Write-Host "Aborted." -ForegroundColor Yellow
    exit 0
}

# Delete versions
$deleted = 0
$failed = 0

foreach ($v in $toDelete) {
    Write-Host "Deleting $($v.Tags)..." -NoNewline
    try {
        gh api --method DELETE "users/$owner/packages/container/$Package/versions/$($v.Id)" 2>$null
        Write-Host " OK" -ForegroundColor Green
        $deleted++
    } catch {
        Write-Host " FAILED" -ForegroundColor Red
        $failed++
    }
}

Write-Host ""
Write-Host "Done! Deleted: $deleted, Failed: $failed" -ForegroundColor Cyan
