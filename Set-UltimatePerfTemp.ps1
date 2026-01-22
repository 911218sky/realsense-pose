<#
Simple, easy-to-maintain script:
- saves current power scheme
- switches to Ultimate Performance
- restores original scheme on exit

Modes:
- interactive (default): press Enter to restore
- monitor: specify -ProcessName "mygame" to restore when process exits
- timeout: specify -TimeoutSeconds 1800 to auto-restore after timeout
#>

param(
    [string]$ProcessName = $null,
    [int]$TimeoutSeconds = 0
)

# ---------- Helpers ----------
function Is-Administrator {
    $principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Relaunch-AsAdmin {
    Write-Host "Not running as Administrator. Relaunching elevated..."
    $args = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    if ($ProcessName) { $args += " -ProcessName `"$ProcessName`"" }
    if ($TimeoutSeconds -gt 0) { $args += " -TimeoutSeconds $TimeoutSeconds" }
    Start-Process -FilePath "powershell" -ArgumentList $args -Verb RunAs
    Exit 0
}

function Get-ActiveGuid {
    $out = powercfg /getactivescheme 2>&1
    if ($out -match '([0-9a-fA-F-]{36})') { return $matches[1] }
    return $null
}

function Ensure-UltimateGuid {
    $ultimate = 'e9a42b02-d5df-448d-aa00-03f14749eb61'
    $list = powercfg /list 2>&1
    if ($list -match $ultimate) { return $ultimate }

    # try duplicate (some Windows editions need it)
    $dup = powercfg -duplicatescheme $ultimate 2>&1
    if ($dup -match '([0-9a-fA-F-]{36})') { return $matches[1] }

    # fallback to builtin GUID (may or may not work)
    return $ultimate
}

function Set-ActiveScheme($guid) {
    powercfg -setactive $guid 2>&1
    return $LASTEXITCODE
}

# ---------- Main ----------
if (-not (Is-Administrator)) { Relaunch-AsAdmin }

$originalGuid = Get-ActiveGuid
if ($originalGuid) { Write-Host "Saved original GUID: $originalGuid" }
else { Write-Warning "Could not read original GUID; restore may fail." }

$ultimateGuid = Ensure-UltimateGuid
Write-Host "Using Ultimate GUID: $ultimateGuid"

try {
    Write-Host "Switching to Ultimate Performance..."
    if ((Set-ActiveScheme $ultimateGuid) -ne 0) {
        Write-Warning "Switch failed. You may need to run as Administrator."
    } else {
        Write-Host "Switched to Ultimate Performance."
    }

    $start = Get-Date

    while ($true) {
        # timeout check
        if ($TimeoutSeconds -gt 0) {
            $elapsed = (Get-Date) - $start
            if ($elapsed.TotalSeconds -ge $TimeoutSeconds) {
                Write-Host "Timeout reached. Restoring..."
                break
            }
        }

        # process monitor
        if ($ProcessName) {
            $proc = Get-Process -Name $ProcessName -ErrorAction SilentlyContinue
            if (-not $proc) {
                Write-Host "Process '$ProcessName' not found. Restoring..."
                break
            }
        }

        # interactive mode
        if (-not $ProcessName -and $TimeoutSeconds -eq 0) {
            Read-Host -Prompt "Press Enter to restore and exit (or Ctrl+C to abort)"
            break
        }

        Start-Sleep -Seconds 2
    }

} finally {
    if ($originalGuid) {
        Write-Host "Restoring original power scheme..."
        if ((Set-ActiveScheme $originalGuid) -ne 0) {
            Write-Warning "Restore failed. Run as Admin: powercfg -setactive $originalGuid"
        } else {
            Write-Host "Restore complete."
        }
    } else {
        Write-Warning "Original GUID unknown — cannot restore automatically."
    }
}
