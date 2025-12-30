[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ErrorActionPreference = 'Stop'

function Get-ProjectRoot {
  param(
    [Parameter(Mandatory)]
    [string] $StartDir
  )

  $dir = (Resolve-Path $StartDir).Path
  while ($true) {
    $hasSrc = Test-Path (Join-Path $dir 'src')
    $hasCompose = Test-Path (Join-Path $dir 'docker-compose.yml')
    $hasReq = Test-Path (Join-Path $dir 'requirements.txt')

    if ($hasSrc -and ($hasCompose -or $hasReq)) {
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

function Invoke-CondaRun {
  param(
    [Parameter(Mandatory)]
    [string] $VenvPath,
    [Parameter(Mandatory)]
    [string[]] $Args
  )
  
  # Use Python -m for conda environments (avoids canonicalization issues)
  $pythonExe = Join-Path $VenvPath 'python.exe'
  if (Test-Path $pythonExe) {
    # Convert common commands to -m module format
    $moduleMap = @{
      'uvicorn' = 'uvicorn'
      'pytest' = 'pytest'
      'pip' = 'pip'
      'black' = 'black'
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
  }
  
  # Fallback to conda run
  & conda run --live-stream -p $VenvPath @Args
  if ($LASTEXITCODE -ne 0) { throw "Command failed: conda run -p `"$VenvPath`" $($Args -join ' ')" }
}

function Try-CondaRun {
  param(
    [Parameter(Mandatory)]
    [string] $VenvPath,
    [Parameter(Mandatory)]
    [string[]] $Args
  )
  & conda run --live-stream -p $VenvPath @Args
  return $LASTEXITCODE
}

function Get-CondaOutput {
  param(
    [Parameter(Mandatory)]
    [string] $VenvPath,
    [Parameter(Mandatory)]
    [string[]] $Args
  )
  $out = & conda run -p $VenvPath @Args
  if ($LASTEXITCODE -ne 0) { throw "Command failed: conda run -p `"$VenvPath`" $($Args -join ' ')" }
  return ($out -join "`n").Trim()
}


