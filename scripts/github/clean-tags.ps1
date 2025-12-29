<#
.SYNOPSIS
    Delete git tags from local and remote repository.

.PARAMETER Keep
    Number of latest tags to keep (default: 3)

.PARAMETER Tags
    Specific tags to delete (comma-separated or array)

.PARAMETER All
    Delete all tags (ignore Keep)

.PARAMETER DryRun
    Show what would be deleted without actually deleting

.EXAMPLE
    .\scripts\github\clean-tags.ps1                     # Keep latest 3
    .\scripts\github\clean-tags.ps1 -Keep 5             # Keep latest 5
    .\scripts\github\clean-tags.ps1 -All                # Delete all tags
    .\scripts\github\clean-tags.ps1 -Tags v1.0.1,v1.0.2 # Delete specific tags
    .\scripts\github\clean-tags.ps1 -DryRun             # Preview only
#>

param(
    [int]$Keep = 3,
    [string[]]$Tags = @(),
    [switch]$All,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

# If -All is specified, delete everything
if ($All) {
    $Keep = 0
}

# Get all tags sorted by version (newest first)
$allTags = git tag --sort=-version:refname 2>$null
if (-not $allTags) {
    Write-Host "No tags found." -ForegroundColor Yellow
    exit 0
}

$allTags = $allTags -split "`n" | Where-Object { $_.Trim() }
Write-Host "Found $($allTags.Count) tags." -ForegroundColor Cyan

$toDelete = @()
$toKeep = @()

if ($Tags.Count -gt 0) {
    # Delete specific tags
    foreach ($tag in $Tags) {
        $tag = $tag.Trim()
        if ($allTags -contains $tag) {
            $toDelete += $tag
        } else {
            Write-Host "Warning: Tag '$tag' not found, skipping." -ForegroundColor Yellow
        }
    }
    $toKeep = $allTags | Where-Object { $_ -notin $toDelete }
} else {
    # Keep latest N tags
    for ($i = 0; $i -lt $allTags.Count; $i++) {
        if ($Keep -gt 0 -and $i -lt $Keep) {
            $toKeep += $allTags[$i]
        } else {
            $toDelete += $allTags[$i]
        }
    }
}

if ($toKeep.Count -gt 0) {
    Write-Host "`nKeeping $($toKeep.Count) tags:" -ForegroundColor Green
    $toKeep | ForEach-Object { Write-Host "  - $_" -ForegroundColor Green }
}

if ($toDelete.Count -eq 0) {
    Write-Host "`nNothing to delete." -ForegroundColor Yellow
    exit 0
}

Write-Host "`nWill delete $($toDelete.Count) tags:" -ForegroundColor Red
$toDelete | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }

if ($DryRun) {
    Write-Host "`n[DRY RUN] No changes made." -ForegroundColor Yellow
    exit 0
}

# Confirm
Write-Host ""
$confirm = Read-Host "Are you sure you want to delete these tags? (y/N)"
if ($confirm -ne 'y') {
    Write-Host "Aborted." -ForegroundColor Yellow
    exit 0
}

# Delete tags
$deleted = 0
$failed = 0

foreach ($tag in $toDelete) {
    Write-Host "Deleting $tag..." -NoNewline
    
    # Delete remote tag
    $remoteResult = git push origin --delete $tag 2>&1
    
    # Delete local tag
    $localResult = git tag -d $tag 2>&1
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host " OK" -ForegroundColor Green
        $deleted++
    } else {
        Write-Host " FAILED" -ForegroundColor Red
        $failed++
    }
}

Write-Host ""
Write-Host "Done! Deleted: $deleted, Failed: $failed" -ForegroundColor Cyan

# Also delete associated releases
Write-Host ""
$deleteReleases = Read-Host "Also delete associated GitHub releases? (y/N)"
if ($deleteReleases -eq 'y') {
    foreach ($tag in $toDelete) {
        Write-Host "Deleting release $tag..." -NoNewline
        $result = gh release delete $tag --yes 2>&1
        if ($result -match "Not Found" -or $result -match "release not found") {
            Write-Host " (no release)" -ForegroundColor Gray
        } else {
            Write-Host " OK" -ForegroundColor Green
        }
    }
}
