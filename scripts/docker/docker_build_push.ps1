. (Join-Path $PSScriptRoot '..\common.ps1')

$ProjectRoot = Initialize-Script -ScriptRoot $PSScriptRoot

function Show-Help {
  Write-Host 'Build (and optionally push) Docker image to Docker Hub.'
  Write-Host ''
  Write-Host 'Usage:'
  Write-Host '  scripts\docker\docker_build_push.ps1 [--image <dockerhub_user/repo>] [--tag <tag>] [--dockerfile <path>] [--platform <p>] [--push y|n] [--latest y|n]'
  Write-Host ''
  Write-Host 'Optional:'
  Write-Host '  --image        Docker Hub repository (default: sky1218/nycu-realsense-pose)'
  Write-Host '  --tag          Image tag (default: latest)'
  Write-Host '  --dockerfile   Dockerfile path (default: Dockerfile)'
  Write-Host '  --platform     Platform for buildx (default: linux/amd64)'
  Write-Host '  --push         y or n (default: y)'
  Write-Host '  --latest       y or n (default: n)'
}

$Image = 'sky1218/nycu-realsense-pose'
$Tag = 'latest'
$Dockerfile = 'Dockerfile'
$Platform = 'linux/amd64'
$Push = 'y'
$TagLatest = 'n'

# ----------------------
# Parse arguments (bat-compatible style)
# ----------------------
for ($i = 0; $i -lt $args.Count; $i++) {
  $a = $args[$i]
  switch ($a.ToLowerInvariant()) {
    '--image' { $Image = $args[$i + 1]; $i++; continue }
    '--tag' { $Tag = $args[$i + 1]; $i++; continue }
    '--dockerfile' { $Dockerfile = $args[$i + 1]; $i++; continue }
    '--platform' { $Platform = $args[$i + 1]; $i++; continue }
    '--push' { $Push = $args[$i + 1]; $i++; continue }
    '--latest' { $TagLatest = $args[$i + 1]; $i++; continue }
    '-h' { Show-Help; exit 2 }
    '--help' { Show-Help; exit 2 }
    default {
      Write-Host "ERROR: Unknown argument: $a"
      Write-Host ''
      Show-Help
      exit 2
    }
  }
}

if (-not (Test-Path $Dockerfile)) {
  Write-Host "ERROR: Dockerfile not found: `"$Dockerfile`""
  exit 1
}

function Normalize-YesNo([string]$v) {
  switch ($v.ToLowerInvariant()) {
    'y' { return 'y' }
    'n' { return 'n' }
    'yes' { return 'y' }
    'no' { return 'n' }
    default { return $null }
  }
}

$PushN = Normalize-YesNo $Push
if (-not $PushN) { Write-Host "ERROR: --push must be y or n, got `"$Push`""; exit 1 }
$Push = $PushN

$LatestN = Normalize-YesNo $TagLatest
if (-not $LatestN) { Write-Host "ERROR: --latest must be y or n, got `"$TagLatest`""; exit 1 }
$TagLatest = $LatestN

Write-Host '============================================'
Write-Host "Project:    $ProjectRoot"
Write-Host "Dockerfile: $Dockerfile"
Write-Host "Image:      $Image`:$Tag"
Write-Host "Platform:   $Platform"
Write-Host "Push:       $Push"
Write-Host "Tag latest: $TagLatest"
Write-Host '============================================'
Write-Host ''

$HasBuildx = $false
try {
  & docker buildx version *>$null
  if ($LASTEXITCODE -eq 0) { $HasBuildx = $true }
} catch {
  $HasBuildx = $false
}

try {
  if ($Push -eq 'y') {
    if ($HasBuildx) {
      Write-Host 'Using buildx --push'
      if ($TagLatest -eq 'y') {
        & docker buildx build -f $Dockerfile --platform $Platform -t "$Image`:$Tag" -t "$Image`:latest" --push .
      } else {
        & docker buildx build -f $Dockerfile --platform $Platform -t "$Image`:$Tag" --push .
      }
      if ($LASTEXITCODE -ne 0) { throw 'docker buildx build --push failed.' }
    } else {
      Write-Host 'Buildx not available; falling back to docker build + docker push'
      & docker build -f $Dockerfile -t "$Image`:$Tag" .
      if ($LASTEXITCODE -ne 0) { throw 'docker build failed.' }

      & docker push "$Image`:$Tag"
      if ($LASTEXITCODE -ne 0) { throw 'docker push failed. Did you run `docker login`?' }

      if ($TagLatest -eq 'y') {
        & docker tag "$Image`:$Tag" "$Image`:latest"
        & docker push "$Image`:latest"
        if ($LASTEXITCODE -ne 0) { throw 'docker push latest failed.' }
      }
    }
  } else {
    Write-Host 'Build only - no push'
    if ($HasBuildx) {
      # Use buildx --load so the image ends up in local docker images
      if ($TagLatest -eq 'y') {
        & docker buildx build -f $Dockerfile --platform $Platform -t "$Image`:$Tag" -t "$Image`:latest" --load .
      } else {
        & docker buildx build -f $Dockerfile --platform $Platform -t "$Image`:$Tag" --load .
      }
    } else {
      if ($TagLatest -eq 'y') {
        & docker build -f $Dockerfile -t "$Image`:$Tag" -t "$Image`:latest" .
      } else {
        & docker build -f $Dockerfile -t "$Image`:$Tag" .
      }
    }
    if ($LASTEXITCODE -ne 0) { throw 'build failed.' }
  }

  Write-Host ''
  Write-Host '============================================'
  Write-Host 'Done.'
  Write-Host 'Pull command:'
  if ($TagLatest -eq 'y') {
    Write-Host "  docker pull $Image`:latest"
  } else {
    Write-Host "  docker pull $Image`:$Tag"
  }
  Write-Host '============================================'
  exit 0
} catch {
  Write-Error $_
  exit 1
}


