. (Join-Path $PSScriptRoot '..\common.ps1')

$ProjectRoot = Initialize-Script -ScriptRoot $PSScriptRoot

$OutputDir = 'dist'
$Entry = Join-Path 'src' 'cli.py'
$ModeFlag = @('--standalone')
$env:NUITKA_CACHE_DIR = (Join-Path $ProjectRoot '_nuitka_cache')

$VenvPath = Get-VenvPath -ProjectRoot $ProjectRoot

try {
  # Ensure Nuitka exists
  try {
    Invoke-VenvRun -VenvPath $VenvPath -Args @('-m', 'nuitka', '--version')
  } catch {
    Write-Host 'Nuitka not installed, installing now...'
    & uv pip install --python $VenvPath -U nuitka
  }

  # Resolve mediapipe modules path
  $mpPkg = Get-VenvOutput -VenvPath $VenvPath -Args @(
    '-c',
    'import mediapipe, pathlib; print(pathlib.Path(mediapipe.__file__).resolve().parent)'
  )
  $mpModules = Join-Path $mpPkg 'modules'

  Write-Host 'Compiling (MinGW64)...'
  $nuitkaArgs = @('-m', 'nuitka') + $ModeFlag + @(
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
  Invoke-VenvRun -VenvPath $VenvPath -Args $nuitkaArgs

  Write-Host ''
  Write-Host "Done! Output in $OutputDir"
  if (Test-Path $OutputDir) {
    Get-ChildItem -Name $OutputDir
  }
  exit 0
} catch {
  Write-Host 'An error occurred, compilation aborted.'
  Write-Error $_
  exit 1
}
