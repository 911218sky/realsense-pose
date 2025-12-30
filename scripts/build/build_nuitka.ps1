. (Join-Path $PSScriptRoot '..\common.ps1')

$ProjectRoot = Initialize-Script -ScriptRoot $PSScriptRoot

$OutputDir = 'dist'
$Entry = Join-Path 'src' 'cli.py'
$ModeFlag = @('--standalone')
$env:NUITKA_CACHE_DIR = (Join-Path $ProjectRoot '_nuitka_cache')

$VenvPath = Join-Path $ProjectRoot 'venv'

try {
  # Ensure Nuitka exists
  try {
    Invoke-CondaRun -VenvPath $VenvPath -Args @('python', '-m', 'nuitka', '--version')
  } catch {
    Write-Host 'Nuitka not installed, installing now...'
    Invoke-CondaRun -VenvPath $VenvPath -Args @('python', '-m', 'pip', 'install', '-U', 'nuitka')
  }

  # Resolve mediapipe modules path
  $mpPkg = Get-CondaOutput -VenvPath $VenvPath -Args @(
    'python', '-c',
    'import mediapipe, pathlib; print(pathlib.Path(mediapipe.__file__).resolve().parent)'
  )
  $mpModules = Join-Path $mpPkg 'modules'

  Write-Host 'Compiling (MinGW64)...'
  $nuitkaArgs = @('python', '-m', 'nuitka') + $ModeFlag + @(
    '--mingw64',
    '--jobs=-1',
    '--lto=no',
    '--remove-output',
    "--output-dir=$OutputDir",
    '--include-module=mediapipe.python.solutions.pose',
    '--python-flag=no_docstrings',
    "--include-data-files=$mpModules\pose_detection\*.tflite=mediapipe/modules/pose_detection/",
    "--include-data-files=$mpModules\pose_landmark\*.tflite=mediapipe/modules/pose_landmark/",
    "--include-data-files=$mpModules\pose_landmark\*.binarypb=mediapipe/modules/pose_landmark/",
    $Entry
  )
  Invoke-CondaRun -VenvPath $VenvPath -Args $nuitkaArgs

  Write-Host ''
  Write-Host "✅ Done! Output in $OutputDir"
  if (Test-Path $OutputDir) {
    Get-ChildItem -Name $OutputDir
  }
  exit 0
} catch {
  Write-Host 'An error occurred, compilation aborted.'
  Write-Error $_
  exit 1
}


