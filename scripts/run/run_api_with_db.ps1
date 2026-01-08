. (Join-Path $PSScriptRoot '..\common.ps1')

$ProjectRoot = Initialize-Script -ScriptRoot $PSScriptRoot
$VenvPath = Get-VenvPath -ProjectRoot $ProjectRoot
$Compose = Get-ComposeCmd

# ========== 環境設定檔 ==========
$ENV_FILE_DEBUG = '.debug.env'
$ENV_FILE_DEFAULT = '.env'
# ================================

function Ensure-EnvFile {
  if (-not (Test-Path '.env')) {
    if (Test-Path 'env.example') {
      Copy-Item 'env.example' '.env' -Force
      Write-Host '[INFO] Created .env from env.example'
    }
  }
}

function Load-DotEnv {
  param([string]$Path = '.env')
  if (-not (Test-Path $Path)) { return }

  foreach ($line in Get-Content $Path) {
    $t = $line.Trim()
    if ($t.Length -eq 0) { continue }
    if ($t.StartsWith('#')) { continue }
    $idx = $t.IndexOf('=')
    if ($idx -lt 1) { continue }
    $k = $t.Substring(0, $idx).Trim()
    $v = $t.Substring($idx + 1).Trim()
    if ($k.Length -eq 0) { continue }
    # Keep values as-is (no unquoting) to match bat behavior
    Set-Item -Path ("Env:{0}" -f $k) -Value $v
  }
}

function Wait-Port {
  param(
    [Parameter(Mandatory)][int]$Port,
    [Parameter(Mandatory)][int]$TimeoutSeconds,
    [Parameter(Mandatory)][string]$Name
  )
  $elapsed = 0
  while ($elapsed -lt $TimeoutSeconds) {
    try {
      $ok = (Test-NetConnection -ComputerName '127.0.0.1' -Port $Port -InformationLevel Quiet)
      if ($ok) { return $true }
    } catch {}
    Start-Sleep -Seconds 2
    $elapsed += 2
  }
  Write-Host "[ERROR] $Name not ready on port $Port after ${TimeoutSeconds}s."
  return $false
}

try {
  Set-Location $ProjectRoot
  Write-Host "[INFO] Repo: $ProjectRoot"

  Ensure-EnvFile

  # 優先使用 debug env，沒有的話用 default env
  if (Test-Path $ENV_FILE_DEBUG) {
    $envFile = $ENV_FILE_DEBUG
    $isDebugMode = $true
  } else {
    Write-Host "[INFO] Using $ENV_FILE_DEFAULT"
    $envFile = $ENV_FILE_DEFAULT
    $isDebugMode = $false
  }
  Load-DotEnv -Path $envFile

  if (-not $env:API_PORT) { $env:API_PORT = '8100' }
  if (-not $env:API_HOST) { $env:API_HOST = 'localhost' }
  if (-not $env:MONGO_PORT) { $env:MONGO_PORT = '27015' }
  if (-not $env:REDIS_PORT) { $env:REDIS_PORT = '6379' }
  if (-not $env:MONGO_ROOT_PASSWORD) { $env:MONGO_ROOT_PASSWORD = '4I0rsokkcCICZNMx' }

  # Ensure docker exists
  if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host '[ERROR] docker not found. Please install Docker Desktop first.'
    exit 1
  }

  Write-Host '[INFO] Ensuring Mongo+Redis are running (docker compose up -d)...'
  $composeArgs = $Compose + @('--file', 'docker-compose.db.yml', '--env-file', $envFile, 'up', '-d')
  & $composeArgs[0] $composeArgs[1..($composeArgs.Length - 1)]
  if ($LASTEXITCODE -ne 0) {
    Write-Host '[ERROR] Failed to start docker compose.'
    exit 1
  }

  $mongoPort = [int]$env:MONGO_PORT
  $redisPort = [int]$env:REDIS_PORT

  Write-Host "[INFO] Waiting for Mongo (127.0.0.1:$mongoPort)..."
  if (-not (Wait-Port -Port $mongoPort -TimeoutSeconds 90 -Name 'MongoDB')) { exit 1 }

  Write-Host "[INFO] Waiting for Redis (127.0.0.1:$redisPort)..."
  if (-not (Wait-Port -Port $redisPort -TimeoutSeconds 60 -Name 'Redis')) { exit 1 }

  # Provide sensible defaults for local run (override via .env if desired)
  if (-not $env:MONGO_URI) { $env:MONGO_URI = "mongodb://root:$($env:MONGO_ROOT_PASSWORD)@localhost:$mongoPort/admin" }
  if (-not $env:REDIS_URL) { $env:REDIS_URL = "redis://localhost:$redisPort" }

  $hostName = $env:API_HOST
  $port = [int]$env:API_PORT

  # 在啟動 API 前顯示 DEBUG MODE 提示（避免被 Test-NetConnection 蓋住）
  if ($isDebugMode) {
    Write-Host ''
    Write-Host '============================================' -ForegroundColor Yellow
    Write-Host "  DEBUG MODE: Using $ENV_FILE_DEBUG" -ForegroundColor Yellow
    Write-Host '============================================' -ForegroundColor Yellow
    Write-Host ''
  }

  Write-Host "[INFO] Starting API: http://$hostName`:$port"
  Invoke-VenvRun -VenvPath $VenvPath -Args @(
    'uvicorn', 'api.main:app',
    '--reload',
    '--reload-exclude', '.venv',
    '--reload-exclude', 'venv',
    '--reload-exclude', '__pycache__',
    '--app-dir', './src',
    '--port', $port,
    '--host', $hostName
  )
  exit 0
} catch {
  Write-Error $_
  exit 1
}
