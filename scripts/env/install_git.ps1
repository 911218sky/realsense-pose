param(
    [switch]$Silent = $false,
    [switch]$CheckOnly = $false
)

$ErrorActionPreference = "Stop"

# Git installer configuration
$InstallerPath = "$env:TEMP\Git-Installer.exe"

function Write-ColorOutput {
    param([string]$Message, [string]$Color = "White")
    Write-Host $Message -ForegroundColor $Color
}

function Get-LatestGitVersion {
    Write-ColorOutput "Fetching latest Git version..." "Yellow"
    try {
        $response = Invoke-RestMethod -Uri "https://api.github.com/repos/git-for-windows/git/releases/latest" -UseBasicParsing
        $version = $response.tag_name -replace '^v', '' -replace '\.windows\.\d+$', ''
        Write-ColorOutput "✓ Latest Git version: $version" "Green"
        return $version
    } catch {
        Write-ColorOutput "⚠ Failed to fetch latest version, using fallback version 2.47.1" "Yellow"
        return "2.47.1"
    }
}

function Test-GitInstalled {
    try {
        $gitVersion = git --version 2>$null
        if ($gitVersion) {
            Write-ColorOutput "✓ Git is already installed: $gitVersion" "Green"
            return $true
        }
    } catch {
        return $false
    }
    return $false
}

function Install-Git {
    # Get latest version
    $GitVersion = Get-LatestGitVersion
    $GitInstallerUrl = "https://github.com/git-for-windows/git/releases/download/v$GitVersion.windows.1/Git-$GitVersion-64-bit.exe"
    
    Write-ColorOutput "`n=== Installing Git for Windows v$GitVersion ===" "Cyan"
    
    # Download installer
    Write-ColorOutput "`nDownloading Git installer..." "Yellow"
    try {
        Invoke-WebRequest -Uri $GitInstallerUrl -OutFile $InstallerPath -UseBasicParsing
        Write-ColorOutput "✓ Download completed" "Green"
    } catch {
        Write-ColorOutput "✗ Failed to download Git installer: $_" "Red"
        exit 1
    }
    
    # Install Git
    Write-ColorOutput "`nInstalling Git..." "Yellow"
    
    if ($Silent) {
        # Silent installation with recommended settings
        $InstallArgs = @(
            "/VERYSILENT",
            "/NORESTART",
            "/NOCANCEL",
            "/SP-",
            "/CLOSEAPPLICATIONS",
            "/RESTARTAPPLICATIONS",
            "/COMPONENTS=`"icons,ext\shellhere,assoc,assoc_sh`"",
            "/EditorOption=VisualStudioCode",
            "/PathOption=Cmd",
            "/SSHOption=OpenSSH",
            "/CURLOption=WinSSL",
            "/CRLFOption=CRLFAlways",
            "/BashTerminalOption=MinTTY",
            "/GitPullBehaviorOption=Merge",
            "/UseCredentialManager=Enabled",
            "/PerformanceTweaksFSCache=Enabled",
            "/EnableSymlinks=Disabled",
            "/EnableFSMonitor=Disabled"
        )
    } else {
        # Interactive installation
        $InstallArgs = @(
            "/SILENT",
            "/NORESTART"
        )
    }
    
    try {
        Start-Process -FilePath $InstallerPath -ArgumentList $InstallArgs -Wait -NoNewWindow
        Write-ColorOutput "✓ Git installation completed" "Green"
    } catch {
        Write-ColorOutput "✗ Failed to install Git: $_" "Red"
        exit 1
    }
    
    # Cleanup
    if (Test-Path $InstallerPath) {
        Remove-Item $InstallerPath -Force
    }
    
    # Refresh environment variables
    Write-ColorOutput "`nRefreshing environment variables..." "Yellow"
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    
    # Verify installation
    Write-ColorOutput "`nVerifying installation..." "Yellow"
    Start-Sleep -Seconds 2
    
    try {
        $gitVersion = git --version 2>$null
        if ($gitVersion) {
            Write-ColorOutput "✓ Git installed successfully: $gitVersion" "Green"
        } else {
            Write-ColorOutput "⚠ Git installed but not found in PATH. Please restart your terminal." "Yellow"
        }
    } catch {
        Write-ColorOutput "⚠ Git installed but not found in PATH. Please restart your terminal." "Yellow"
    }
}

function Show-GitConfig {
    Write-ColorOutput "`n=== Recommended Git Configuration ===" "Cyan"
    Write-ColorOutput @"

After installation, configure Git with your information:

    git config --global user.name "Your Name"
    git config --global user.email "your.email@example.com"

Optional recommended settings:

    # Set default branch name
    git config --global init.defaultBranch main

    # Enable credential helper
    git config --global credential.helper manager-core

    # Set line ending handling
    git config --global core.autocrlf true

    # Enable color output
    git config --global color.ui auto

    # Set default editor (VS Code)
    git config --global core.editor "code --wait"

"@ "White"
}

# Main execution
Write-ColorOutput @"
╔════════════════════════════════════════╗
║     Git for Windows Installer          ║
╚════════════════════════════════════════╝
"@ "Cyan"

# Check if Git is already installed
if (Test-GitInstalled) {
    if ($CheckOnly) {
        exit 0
    }
    
    Write-ColorOutput "`nGit is already installed. Skipping installation." "Green"
    Show-GitConfig
    exit 0
} else {
    Write-ColorOutput "Git is not installed." "Yellow"
    
    if ($CheckOnly) {
        exit 1
    }
}

# Install Git
Install-Git

# Show configuration guide
Show-GitConfig

Write-ColorOutput "`n✓ Installation complete!" "Green"
Write-ColorOutput "⚠ Please restart your terminal or IDE to use Git." "Yellow"
