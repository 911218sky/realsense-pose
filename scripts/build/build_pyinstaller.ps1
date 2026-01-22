. (Join-Path $PSScriptRoot '..\common.ps1')

$ProjectRoot = Initialize-Script -ScriptRoot $PSScriptRoot

$OutputDir = 'dist'
$Entry = Join-Path 'src' 'cli.py'

# onedir (output one folder), onefile (output one file)
$ModeFlag = '--onedir'
$PyiFlags = @('--clean', '--noconfirm')

# ---- Key volume control ----
$env:MPLBACKEND = 'TkAgg'
$Excludes = @(
  '--exclude-module', 'PyQt5',
  '--exclude-module', 'PyQt6',
  '--exclude-module', 'PySide2',
  '--exclude-module', 'PySide6',
  '--exclude-module', 'matplotlib.tests',
  '--exclude-module', 'tests'
)
$Collect = @('--collect-data', 'mediapipe')

$VenvPath = Get-VenvPath -ProjectRoot $ProjectRoot

try {
  # Ensure PyInstaller exists
  try {
    Invoke-VenvRun -VenvPath $VenvPath -Args @('-m', 'PyInstaller', '--version')
  } catch {
    Write-Host 'PyInstaller not installed, installing now...'
    & uv pip install --python $VenvPath -U pyinstaller
  }

  Write-Host "Packaging with PyInstaller, target: $Entry"
  Write-Host ''

  $pyiArgs = @('-m', 'PyInstaller', $ModeFlag) + $PyiFlags + @(
    '--name', 'cli'
  ) + $Excludes + $Collect + @(
    '--distpath', $OutputDir,
    $Entry
  )
  Invoke-VenvRun -VenvPath $VenvPath -Args $pyiArgs

  Write-Host ''
  Write-Host "Done! Output in $OutputDir"
  if (Test-Path $OutputDir) {
    Get-ChildItem -Name $OutputDir
  }
  exit 0
} catch {
  Write-Host 'An error occurred, packaging aborted.'
  Write-Error $_
  exit 1
}
