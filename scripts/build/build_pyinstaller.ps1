. (Join-Path $PSScriptRoot '..\_common.ps1')

$ProjectRoot = Initialize-Script -ScriptRoot $PSScriptRoot

$OutputDir = 'dist'
$Entry = Join-Path 'src' 'cli.py'

# onedir (輸出一個資料夾)、onefile (輸出一個檔案)
$ModeFlag = '--onedir'
$PyiFlags = @('--clean', '--noconfirm')

# ---- 體積控制關鍵 ----
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

$VenvPath = Join-Path $ProjectRoot 'venv'

try {
  # Ensure PyInstaller exists
  try {
    Invoke-CondaRun -VenvPath $VenvPath -Args @('pyinstaller', '--version')
  } catch {
    Write-Host 'PyInstaller 未安裝，正在安裝...'
    Invoke-CondaRun -VenvPath $VenvPath -Args @('python', '-m', 'pip', 'install', '-U', 'pyinstaller')
  }

  Write-Host "以 PyInstaller 打包，目標：$Entry"
  Write-Host ''

  $pyiArgs = @('pyinstaller', $ModeFlag) + $PyiFlags + @(
    '--name', 'cli'
  ) + $Excludes + $Collect + @(
    '--distpath', $OutputDir,
    $Entry
  )
  Invoke-CondaRun -VenvPath $VenvPath -Args $pyiArgs

  Write-Host ''
  Write-Host "✅ 完成！輸出在 $OutputDir"
  if (Test-Path $OutputDir) {
    Get-ChildItem -Name $OutputDir
  }
  exit 0
} catch {
  Write-Host '發生錯誤，打包中止。'
  Write-Error $_
  exit 1
}


