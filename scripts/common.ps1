[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ErrorActionPreference = 'Stop'

function Write-Section {
  param(
    [Parameter(Mandatory)]
    [string] $Title
  )
  $line = "=" * 50
  Write-Host ""
  Write-Host $line -ForegroundColor Cyan
  Write-Host "  $Title" -ForegroundColor Cyan
  Write-Host $line -ForegroundColor Cyan
  Write-Host ""
}

function Get-ProjectRoot {
  param(
    [Parameter(Mandatory)]
    [string] $StartDir
  )

  $dir = (Resolve-Path $StartDir).Path
  while ($true) {
    $hasSrc = Test-Path (Join-Path $dir 'src')
    $hasCompose = Test-Path (Join-Path $dir 'docker-compose.yml')
    $hasPyproject = Test-Path (Join-Path $dir 'pyproject.toml')

    if ($hasSrc -and ($hasCompose -or $hasPyproject)) {
      return $dir
    }

    $parent = Split-Path $dir -Parent
    if ([string]::IsNullOrWhiteSpace($parent) -or $parent -eq $dir) {
      throw "Project root not found walking up from: $StartDir"
    }
    $dir = $parent
  }
}

function Initialize-Script {
  param(
    [Parameter(Mandatory)]
    [string] $ScriptRoot
  )
  $root = Get-ProjectRoot -StartDir $ScriptRoot
  Set-Location $root
  return $root
}

function Pause-IfInteractive {
  param(
    [string] $Prompt = 'Press Enter to continue...'
  )
  try {
    if ($Host.Name -eq 'ConsoleHost') {
      Read-Host $Prompt | Out-Null
    }
  } catch {}
}

function Get-ComposeCmd {
  try {
    & docker compose version *>$null
    if ($LASTEXITCODE -eq 0) { return @('docker', 'compose') }
  } catch {}
  return @('docker-compose')
}

function Invoke-Compose {
  param(
    [Parameter(Mandatory)]
    [string[]] $ComposeCmd,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $Args
  )

  if ($ComposeCmd.Length -le 0) {
    throw 'Compose command is empty.'
  }

  if ($ComposeCmd.Length -eq 1) {
    & $ComposeCmd[0] @Args
    return $LASTEXITCODE
  }

  $sub = @()
  if ($ComposeCmd.Length -gt 1) {
    $sub = @($ComposeCmd[1..($ComposeCmd.Length - 1)])
  }
  & $ComposeCmd[0] @sub @Args
  return $LASTEXITCODE
}

function Get-VenvPath {
  param(
    [Parameter(Mandatory)]
    [string] $ProjectRoot
  )
  return Join-Path $ProjectRoot '.venv'
}

function Invoke-VenvRun {
  param(
    [Parameter(Mandatory)]
    [string] $VenvPath,
    [Parameter(Mandatory)]
    [string[]] $Args
  )
  
  $pythonExe = Join-Path $VenvPath 'Scripts\python.exe'
  if (-not (Test-Path $pythonExe)) {
    throw "Python not found in venv: $pythonExe"
  }
  
  # Convert common commands to -m module format
  $moduleMap = @{
    'uvicorn' = 'uvicorn'
    'pytest' = 'pytest'
    'pip' = 'pip'
    'uv' = 'uv'
    'black' = 'black'
    'ruff' = 'ruff'
    'flake8' = 'flake8'
    'mypy' = 'mypy'
  }
  
  $cmd = $Args[0]
  if ($moduleMap.ContainsKey($cmd)) {
    $moduleArgs = @('-m', $moduleMap[$cmd]) + $Args[1..($Args.Length - 1)]
    & $pythonExe @moduleArgs
    if ($LASTEXITCODE -ne 0) { throw "Command failed: $pythonExe $($moduleArgs -join ' ')" }
    return
  }
  
  # If first arg is already -m or a .py file, use python directly
  if ($Args[0] -eq '-m' -or $Args[0] -match '\.(py|pyw)$') {
    & $pythonExe @Args
    if ($LASTEXITCODE -ne 0) { throw "Command failed: $pythonExe $($Args -join ' ')" }
    return
  }
  
  # Default: run as python command
  & $pythonExe @Args
  if ($LASTEXITCODE -ne 0) { throw "Command failed: $pythonExe $($Args -join ' ')" }
}

function Try-VenvRun {
  param(
    [Parameter(Mandatory)]
    [string] $VenvPath,
    [Parameter(Mandatory)]
    [string[]] $Args
  )
  $pythonExe = Join-Path $VenvPath 'Scripts\python.exe'
  & $pythonExe @Args
  return $LASTEXITCODE
}

function Get-VenvOutput {
  param(
    [Parameter(Mandatory)]
    [string] $VenvPath,
    [Parameter(Mandatory)]
    [string[]] $Args
  )
  $pythonExe = Join-Path $VenvPath 'Scripts\python.exe'
  $out = & $pythonExe @Args
  if ($LASTEXITCODE -ne 0) { throw "Command failed: $pythonExe $($Args -join ' ')" }
  return ($out -join "`n").Trim()
}

# Legacy aliases for backward compatibility
function Invoke-CondaRun {
  param(
    [Parameter(Mandatory)]
    [string] $VenvPath,
    [Parameter(Mandatory)]
    [string[]] $Args
  )
  Invoke-VenvRun -VenvPath $VenvPath -Args $Args
}

function Try-CondaRun {
  param(
    [Parameter(Mandatory)]
    [string] $VenvPath,
    [Parameter(Mandatory)]
    [string[]] $Args
  )
  Try-VenvRun -VenvPath $VenvPath -Args $Args
}

function Get-CondaOutput {
  param(
    [Parameter(Mandatory)]
    [string] $VenvPath,
    [Parameter(Mandatory)]
    [string[]] $Args
  )
  Get-VenvOutput -VenvPath $VenvPath -Args $Args
}
