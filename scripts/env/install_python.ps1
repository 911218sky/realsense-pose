param(
    [string]$Version = "",
    [switch]$Silent = $false,
    [switch]$CheckOnly = $false
)

$ErrorActionPreference = "Stop"

# Python installer configuration
$InstallerPath = "$env:TEMP\Python-Installer.exe"

function Write-ColorOutput {
    param([string]$Message, [string]$Color = "White")
    Write-Host $Message -ForegroundColor $Color
}

function Get-LatestPythonVersion {
    Write-ColorOutput "Fetching latest stable Python version..." "Yellow"
    try {
        # Fetch Python downloads page
        $response = Invoke-WebRequest -Uri "https://www.python.org/downloads/windows/" -UseBasicParsing
        
        # Extract latest stable version (3.x.x format)
        if ($response.Content -match 'Latest Python 3 Release - Python (\d+\.\d+\.\d+)') {
            $version = $matches[1]
            Write-ColorOutput "✓ Latest stable Python version: $version" "Green"
            return $version
        }
        
        # Fallback: try alternative pattern
        if ($response.Content -match 'python-(\d+\.\d+\.\d+)-amd64\.exe') {
            $version = $matches[1]
            Write-ColorOutput "✓ Latest stable Python version: $version" "Green"
            return $version
        }
        
        throw "Could not parse version from page"
    } catch {
        Write-ColorOutput "⚠ Failed to fetch latest version, using fallback version 3.12.8" "Yellow"
        return "3.12.8"
    }
}

function Test-PythonInstalled {
    try {
        $pythonVersion = python --version 2>$null
        if ($pythonVersion) {
            Write-ColorOutput "✓ Python is already installed: $pythonVersion" "Green"
            
            # Also check for pip
            $pipVersion = pip --version 2>$null
            if ($pipVersion) {
                Write-ColorOutput "✓ pip is available: $pipVersion" "Green"
            }
            
            return $true
        }
    } catch {
        return $false
    }
    return $false
}

function Install-Python {
    # Get latest version if not specified
    if ([string]::IsNullOrEmpty($Version)) {
        $PythonVersion = Get-LatestPythonVersion
    } else {
        $PythonVersion = $Version
    }
    
    $PythonInstallerUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-amd64.exe"
    
    Write-ColorOutput "`n=== Installing Python $PythonVersion ===" "Cyan"
    
    # Download installer
    Write-ColorOutput "`nDownloading Python installer..." "Yellow"
    try {
        Invoke-WebRequest -Uri $PythonInstallerUrl -OutFile $InstallerPath -UseBasicParsing
        Write-ColorOutput "✓ Download completed" "Green"
    } catch {
        Write-ColorOutput "✗ Failed to download Python installer: $_" "Red"
        Write-ColorOutput "URL: $PythonInstallerUrl" "Yellow"
        exit 1
    }
    
    # Install Python
    Write-ColorOutput "`nInstalling Python..." "Yellow"
    
    if ($Silent) {
        # Silent installation with recommended settings
        $InstallArgs = @(
            "/quiet",
            "InstallAllUsers=1",
            "PrependPath=1",
            "Include_test=0",
            "Include_pip=1",
            "Include_doc=0",
            "Include_dev=1",
            "Include_launcher=1",
            "InstallLauncherAllUsers=1",
            "Include_tcltk=1"
        )
    } else {
        # Interactive installation with PATH enabled
        $InstallArgs = @(
            "/passive",
            "InstallAllUsers=1",
            "PrependPath=1",
            "Include_pip=1",
            "Include_dev=1",
            "Include_launcher=1"
        )
    }
    
    try {
        Start-Process -FilePath $InstallerPath -ArgumentList $InstallArgs -Wait -NoNewWindow
        Write-ColorOutput "✓ Python installation completed" "Green"
    } catch {
        Write-ColorOutput "✗ Failed to install Python: $_" "Red"
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
        $pythonVersion = python --version 2>$null
        if ($pythonVersion) {
            Write-ColorOutput "✓ Python installed successfully: $pythonVersion" "Green"
            
            # Check pip
            $pipVersion = pip --version 2>$null
            if ($pipVersion) {
                Write-ColorOutput "✓ pip is available: $pipVersion" "Green"
            }
        } else {
            Write-ColorOutput "⚠ Python installed but not found in PATH. Please restart your terminal." "Yellow"
        }
    } catch {
        Write-ColorOutput "⚠ Python installed but not found in PATH. Please restart your terminal." "Yellow"
    }
}

function Show-PythonConfig {
    Write-ColorOutput "`n=== Recommended Python Configuration ===" "Cyan"
    Write-ColorOutput @"

After installation, you can:

1. Verify Python installation:
    python --version
    pip --version

2. Upgrade pip to latest version:
    python -m pip install --upgrade pip

3. Install common development tools:
    pip install virtualenv
    pip install black flake8 mypy pytest

4. Create virtual environment:
    python -m venv .venv
    .venv\Scripts\activate

5. Install project dependencies (if using uv):
    pip install uv
    uv sync

"@ "White"
}

function Show-UvInstallation {
    Write-ColorOutput "`n=== Install uv (Recommended) ===" "Cyan"
    Write-ColorOutput @"

This project uses 'uv' for Python package management.
Install uv with:

    pip install uv

Or use the standalone installer:
    powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

After installing uv, sync project dependencies:
    uv sync

"@ "White"
}

# Main execution
Write-ColorOutput @"
╔════════════════════════════════════════╗
║     Python for Windows Installer       ║
╚════════════════════════════════════════╝
"@ "Cyan"

# Check if Python is already installed
if (Test-PythonInstalled) {
    if ($CheckOnly) {
        exit 0
    }
    
    Write-ColorOutput "`nPython is already installed. Skipping installation." "Green"
    Show-PythonConfig
    Show-UvInstallation
    exit 0
} else {
    Write-ColorOutput "Python is not installed." "Yellow"
    
    if ($CheckOnly) {
        exit 1
    }
}

# Install Python
Install-Python

# Show configuration guide
Show-PythonConfig
Show-UvInstallation

Write-ColorOutput "`n✓ Installation complete!" "Green"
Write-ColorOutput "⚠ Please restart your terminal or IDE to use Python." "Yellow"
