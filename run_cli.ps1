# Set working dir to this script's folder
$ScriptRoot = Split-Path -Path $MyInvocation.MyCommand.Definition -Parent
Set-Location $ScriptRoot

# ---------------------------
# Defaults / Templates
# ---------------------------
$Exe = @("bin\cli.exe", "bin\cli.dist\cli.exe", "dist\cli.exe", "dist\cli.dist\cli.exe")
$DefaultBag = "dataset\4_1_1208.bag"
$DefaultOutputRoot = "outputs"
$DefaultConfigPose = "configs\default_pose.yaml"
$DefaultConfigAnalyzer = "configs\default_analyzer.yaml"

# Exit flag (kept for compatibility)
$ExitRequested = $false

# ---------------------------
# Helpers (unchanged behavior)
# ---------------------------
function Get-ExecutablePath {
    param([Parameter(Mandatory)][Object]$ExeCandidates)

    if ($null -eq $ExeCandidates) { return $null }

    $cands = @()
    if ($ExeCandidates -is [array]) { $cands = $ExeCandidates } else { $cands = @("$ExeCandidates") }

    foreach ($c in $cands) {
        if (-not [string]::IsNullOrWhiteSpace($c) -and (Test-Path $c)) {
            try { return (Resolve-Path $c).Path } catch { return $c }
        }
    }
    return $null
}

function Read-Default([string]$prompt, [string]$default) {
    if ($null -eq $default) { $default = "" }
    $input = Read-Host ("$prompt (default: $default)")
    if ([string]::IsNullOrWhiteSpace($input)) { return $default }
    return $input
}

function Refresh-EnvPath {
    $machine = [System.Environment]::GetEnvironmentVariable('Path','Machine')
    $user    = [System.Environment]::GetEnvironmentVariable('Path','User')
    $env:Path = "$user;$machine"
}

function Ensure-FFmpeg {
    if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
        Write-Host "ffmpeg found." -ForegroundColor Green
        return $true
    }
    Write-Warning "ffmpeg not found on PATH."
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Write-Warning "winget is not available. Please install ffmpeg manually or install winget."
        return $false
    }
    Write-Host "Installing lightweight FFmpeg (Essentials) via winget..." -ForegroundColor Cyan
    try {
        winget install --id Gyan.FFmpeg.Essentials -e `
            --disable-interactivity `
            --accept-package-agreements --accept-source-agreements
    } catch {
        Write-Warning "winget installation failed or was cancelled: $_"
    }
    Refresh-EnvPath
    if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
        Write-Host "ffmpeg installed and on PATH." -ForegroundColor Green
        return $true
    }
    $candidates = @(
        "C:\ffmpeg\bin\ffmpeg.exe",
        "$env:ProgramFiles\FFmpeg\bin\ffmpeg.exe",
        "$env:ProgramFiles\ffmpeg\bin\ffmpeg.exe"
    )
    foreach ($p in $candidates) {
        if (Test-Path $p) {
            $dir = Split-Path $p -Parent
            if ($env:Path -notlike "*$dir*") { $env:Path = "$dir;$env:Path" }
            if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
                Write-Host "ffmpeg detected at $dir and added to current PATH." -ForegroundColor Green
                return $true
            }
        }
    }
    Write-Warning "ffmpeg still not found. You may need to open a NEW PowerShell window or reboot as a last resort."
    return $false
}

function Invoke-External {
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [Parameter(Mandatory)][string[]]$ArgumentList
    )
    try {
        $proc = Start-Process -FilePath $FilePath -ArgumentList $ArgumentList -Wait -NoNewWindow -PassThru
        return $proc.ExitCode
    } catch {
        Write-Error "Failed to start process: $_"
        return 1
    }
}

function Get-TagFromPath {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) { return $null }
    try {
        $name = [System.IO.Path]::GetFileNameWithoutExtension($Path)
        if ([string]::IsNullOrWhiteSpace($name)) { return $null }

        # Only for .npy files, remove trailing `_pose` or `-pose`
        $ext = [System.IO.Path]::GetExtension($Path)
        if ($ext -ieq ".npy") {
            $name = $name -replace '([_-])pose$', ''
        }
        return $name
    } catch {
        return $null
    }
}

function Prompt-ForTag {
    param(
        [string]$CandidateTag,
        [string]$PromptPrefix = "Use the automatically inferred tag"
    )
    if ($CandidateTag) {
        $ans = Read-Host "$PromptPrefix '$CandidateTag'? (Press Enter to accept / type 'n' to cancel / type a custom tag)"
        if ([string]::IsNullOrWhiteSpace($ans)) { return $CandidateTag }
        elseif ($ans -match '^[Nn]$') { return $null }
        else { return $ans }
    } else {
        $ans = Read-Host "$PromptPrefix? (No tag could be inferred. Enter a custom tag or press Enter to cancel)"
        if ([string]::IsNullOrWhiteSpace($ans)) { return $null }
        return $ans
    }
}

function Resolve-NpyPath {
    param(
        [Parameter(Mandatory)][string]$OutputDir,
        [Parameter(Mandatory)][string]$DefaultNpyPath,
        [string]$Tag
    )
    if (-not [string]::IsNullOrWhiteSpace($Tag)) {
        $tagpath = Join-Path $OutputDir ($Tag + "_pose.npy")
        if (Test-Path $tagpath) { return $tagpath }
        if ($OutputDir -eq $DefaultOutputRoot -or $OutputDir -eq ".\" -or $OutputDir -eq "") {
            $candidate = Join-Path (Join-Path $DefaultOutputRoot $Tag) ($Tag + "_pose.npy")
            if (Test-Path $candidate) { return $candidate }
        }
    }
    $direct = Join-Path $OutputDir "pose.npy"
    if (Test-Path $direct) { return $direct }
    $found = Get-ChildItem -Path $OutputDir -Filter *.npy -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) { return $found.FullName }
    if (Test-Path $DefaultNpyPath) {
        Write-Warning "Could not locate pose.npy under '$OutputDir'. Falling back to '$DefaultNpyPath'."
        return $DefaultNpyPath
    }
    Write-Warning "pose.npy not found. Using expected path: $direct"
    return $direct
}

# Optionally warn if EXE missing
if (-not (Test-Path $Exe)) {
    Write-Warning "Executable '$Exe' not found. Please verify path. The script will continue so you can change values."
}

# Ensure ffmpeg (best-effort)
Ensure-FFmpeg | Out-Null

# ---------------------------
# New shared utilities
# ---------------------------
function Ensure-OutputDir {
    param([string]$Path)
    if (-not (Test-Path $Path)) {
        Write-Host "Creating output directory: $Path"
        try { New-Item -ItemType Directory -Path $Path -Force | Out-Null } catch { Write-Warning "Failed to create output dir: $_" }
    }
}

function Summarize-And-Run {
    param(
        [string]$Mode,             # "extract" or "analyze"
        [string[]]$ArgList,        # full argument array for exe (excluding exe path)
        [string]$ExePath = (Get-ExecutablePath $Exe),
        [string]$OutputDir,
        [string]$Tag,
        [string]$NpyOrBag,
        [string]$Config
    )
    Write-Host ""
    Write-Host "Executable: $ExePath"
    Write-Host ("Mode      : {0}" -f $Mode)
    if ($Mode -eq "extract") { Write-Host ("Bag file  : {0}" -f $NpyOrBag) } else { Write-Host ("NPY file  : {0}" -f $NpyOrBag) }
    Write-Host ("Output dir: {0}" -f $OutputDir)
    Write-Host ("Config    : {0}" -f $Config)
    if ($Tag) { Write-Host ("Tag       : {0}" -f $Tag) } else { Write-Host "Tag       : (none)" }
    Ensure-OutputDir -Path $OutputDir
    Write-Host ""
    Write-Host ("Running {0}..." -f $Mode) -ForegroundColor Cyan
    $exit = Invoke-External -FilePath $ExePath -ArgumentList $ArgList
    return $exit
}

function Build-And-Run {
    param(
        [Parameter(Mandatory)][ValidateSet("extract","analyze")] [string]$Step,
        [string]$BagPath,
        [string]$NpyPath,
        [string]$Output,
        [string]$Config,
        [string]$Tag
    )
    if ($Step -eq "extract") {
        $args = @("extract","--bag",$BagPath,"--output",$Output,"--config",$Config)
        if ($Tag) { $args += @("--tag",$Tag) }
        return Summarize-And-Run -Mode "extract" -ArgList $args -OutputDir $Output -Tag $Tag -NpyOrBag $BagPath -Config $Config
    } else {
        $args = @("analyze","--npy",$NpyPath,"--output",$Output,"--config",$Config)
        if ($Tag) { $args += @("--tag",$Tag) }
        return Summarize-And-Run -Mode "analyze" -ArgList $args -OutputDir $Output -Tag $Tag -NpyOrBag $NpyPath -Config $Config
    }
}

# ★ New: force output directory rule
function Get-OutputDir {
    param([string]$Tag)
    if (-not [string]::IsNullOrWhiteSpace($Tag)) {
        return (Join-Path $DefaultOutputRoot $Tag)
    } else {
        return $DefaultOutputRoot
    }
}

# ---------------------------
# Main loop
# ---------------------------
while ($true) {
    Write-Host ""
    Write-Host "Select mode:"
    Write-Host "  1) extract (pose extraction)"
    Write-Host "  2) analyze (rehab analysis)"
    Write-Host "  3) auto (extract -> analyze)"
    Write-Host "  4) Exit"
    $modeSel = Read-Host "Enter 1, 2, 3 or 4 (default 3)"
    if ([string]::IsNullOrWhiteSpace($modeSel)) { $modeSel = "3" }
    $modeSel = $modeSel.Trim().ToLower()
    switch ($modeSel) {
        "1" { $Mode = "extract" }
        "2" { $Mode = "analyze" }
        "3" { $Mode = "auto" }
        "4" { Write-Host "Exiting..."; exit }
        "extract" { $Mode = "extract" }
        "analyze" { $Mode = "analyze" }
        "auto" { $Mode = "auto" }
        default { Write-Warning "Invalid selection: '$modeSel'. Please choose 1, 2, 3 or 4."; continue }
    }

    if ($Mode -eq "extract") {
        # --- Extract: ask bag, (optional) tag, force output path
        $Bag = Read-Default "Path to .bag" $DefaultBag
        $candidateTag = Get-TagFromPath $Bag
        $Tag = Prompt-ForTag -CandidateTag $candidateTag -PromptPrefix "Enable tag inferred from the bag filename (default: enabled)"

        # Force output directory by rule
        $Output = Get-OutputDir -Tag $Tag
        Write-Host "Output directory is to: $Output" -ForegroundColor Blue

        $Config = Read-Default "Optional YAML config (press Enter for default)" $DefaultConfigPose

        Build-And-Run -Step "extract" -BagPath $Bag -Output $Output -Config $Config -Tag $Tag | Out-Null
        continue
    }

    if ($Mode -eq "analyze") {
        # --- Analyze: choose npy, derive/confirm tag, force output path
        $npyInput = Read-Host "Path to .npy (press Enter to use default based on tag: outputs\\{tag}\\{tag}_pose.npy)"
        if ([string]::IsNullOrWhiteSpace($npyInput)) {
            $candidateTag = Get-TagFromPath $DefaultBag
            $Tag = Prompt-ForTag -CandidateTag $candidateTag -PromptPrefix "Which tag should be used to form the default NPY path (default: enabled)"
            if ($Tag) {
                $defaultNpy = Join-Path (Join-Path $DefaultOutputRoot $Tag) ($Tag + "_pose.npy")
            } else {
                $defaultNpy = Join-Path $DefaultOutputRoot "pose.npy"
            }
            $Npy = Read-Default "Path to .npy" $defaultNpy
        } else {
            $Npy = $npyInput
            $candidateTag = Get-TagFromPath $Npy
            $Tag = Prompt-ForTag -CandidateTag $candidateTag -PromptPrefix "Enable tag inferred from the npy filename (default: enabled)"
        }

        # Force output directory by rule
        $Output = Get-OutputDir -Tag $Tag
        Write-Host "Output directory is to: $Output" -ForegroundColor Blue

        $Config = Read-Default "Optional YAML config (press Enter for default)" $DefaultConfigAnalyzer

        Build-And-Run -Step "analyze" -NpyPath $Npy -Output $Output -Config $Config -Tag $Tag | Out-Null
        continue
    }

    if ($Mode -eq "auto") {
        # --- Auto: one tag, force one output, run extract then analyze
        $Bag = Read-Default "Path to .bag" $DefaultBag
        $candidateTag = Get-TagFromPath $Bag
        $Tag = Prompt-ForTag -CandidateTag $candidateTag -PromptPrefix "Enable tag inferred from the bag filename (applies to extract & analyze, default: enabled)"

        # Force output directory shared by both steps
        $Output = Get-OutputDir -Tag $Tag
        Write-Host "Output directory is to: $Output" -ForegroundColor Blue

        $ConfigPose = Read-Default "YAML config for extract (Enter for default)" $DefaultConfigPose
        $ConfigAnalyzer = Read-Default "YAML config for analyze (Enter for default)" $DefaultConfigAnalyzer

        $codeExtract = Build-And-Run -Step "extract" -BagPath $Bag -Output $Output -Config $ConfigPose -Tag $Tag
        if ($codeExtract -ne 0) {
            Write-Warning "extract failed with exit code $codeExtract. Auto mode aborted."
            continue
        }

        # Resolve NPY for analyze
        if ($Tag) {
            $DefaultNpy = Join-Path (Join-Path $DefaultOutputRoot $Tag) ($Tag + "_pose.npy")
        } else {
            $DefaultNpy = Join-Path $DefaultOutputRoot "pose.npy"
        }
        $NpyAuto = Resolve-NpyPath -OutputDir $Output -DefaultNpyPath $DefaultNpy -Tag $Tag
        Write-Host "Using NPY for analyze: $NpyAuto"

        Build-And-Run -Step "analyze" -NpyPath $NpyAuto -Output $Output -Config $ConfigAnalyzer -Tag $Tag | Out-Null
        continue
    }
}

# loop end