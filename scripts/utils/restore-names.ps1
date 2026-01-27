<#
.SYNOPSIS
    Terminal File Restore Tool (Drag & Drop Support)
    Accepts files or folders via drag-and-drop in the console window.
#>

# Force UTF8 output for console to display filenames correctly
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# ==========================================
# Core Logic
# ==========================================
function Rename-UrlEncodedFile {
    param (
        [System.IO.FileInfo]$FileItem,
        [ref]$Stats
    )

    $OriginalName = $FileItem.Name
    
    # Check if decoding is needed (Optimization)
    if ($OriginalName -notlike "*%*") { return }

    try {
        $DecodedName = [Uri]::UnescapeDataString($OriginalName)
    }
    catch {
        Write-Host " [Error] Cannot decode: $OriginalName" -ForegroundColor Red
        $Stats.Value.Error++
        return
    }

    if ($OriginalName -cne $DecodedName) {
        $NewPath = Join-Path -Path $FileItem.DirectoryName -ChildPath $DecodedName
        
        if (Test-Path -LiteralPath $NewPath) {
            Write-Host " [Skip] Target exists: $DecodedName" -ForegroundColor Yellow
            $Stats.Value.Skipped++
        }
        else {
            try {
                Rename-Item -LiteralPath $FileItem.FullName -NewName $DecodedName -ErrorAction Stop
                Write-Host " [OK] $OriginalName -> $DecodedName" -ForegroundColor Green
                $Stats.Value.Success++
            }
            catch {
                Write-Host " [Fail] $($_.Exception.Message)" -ForegroundColor Red
                $Stats.Value.Error++
            }
        }
    }
}

# ==========================================
# Main Terminal Loop
# ==========================================

Clear-Host
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host "   URL Decode Tool (Drag & Drop Mode)   " -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan
Write-Host "Instructions:" -ForegroundColor Gray
Write-Host "1. Drag a FOLDER or FILE into this window." -ForegroundColor Gray
Write-Host "2. Press ENTER to execute." -ForegroundColor Gray
Write-Host "3. Press ENTER without input to Exit." -ForegroundColor Gray
Write-Host "==============================================`n" -ForegroundColor Cyan

while ($true) {
    # 1. Get User Input
    $rawInput = Read-Host "Drag File/Folder Here >"

    # Exit condition
    if ([string]::IsNullOrWhiteSpace($rawInput)) {
        break
    }

    # 2. Clean Input (Remove quotes added by Windows when dragging)
    $cleanPath = $rawInput.Trim('"').Trim("'")

    # 3. Validate Path
    if (-not (Test-Path -LiteralPath $cleanPath)) {
        Write-Host " [Error] Path not found: $cleanPath`n" -ForegroundColor Red
        continue
    }

    $item = Get-Item -LiteralPath $cleanPath
    $TargetFiles = @()

    # 4. Determine File or Folder
    if ($item.PSIsContainer) {
        # It is a Folder
        Write-Host " -> Processing Folder: $($item.FullName)" -ForegroundColor Magenta
        $TargetFiles = Get-ChildItem -LiteralPath $item.FullName -Recurse -File
    }
    else {
        # It is a File
        Write-Host " -> Processing File: $($item.Name)" -ForegroundColor Magenta
        $TargetFiles = @($item)
    }

    # 5. Execute Renaming
    $Statistics = @{ Success = 0; Skipped = 0; Error = 0 }
    
    foreach ($file in $TargetFiles) {
        Rename-UrlEncodedFile -FileItem $file -Stats ([ref]$Statistics)
    }

    # 6. Summary
    Write-Host "`n --- Result ---" -ForegroundColor Gray
    Write-Host " Success : $($Statistics.Success)" -ForegroundColor Green
    Write-Host " Skipped : $($Statistics.Skipped)" -ForegroundColor Yellow
    Write-Host " Errors  : $($Statistics.Error)" -ForegroundColor Red
    Write-Host "----------------------------------------------`n"
}

Write-Host "Bye!" -ForegroundColor Cyan
Start-Sleep -Seconds 1