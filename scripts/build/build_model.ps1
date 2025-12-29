. (Join-Path $PSScriptRoot '..\_common.ps1')

$ProjectRoot = Initialize-Script -ScriptRoot $PSScriptRoot

$OutputDir = 'dist'
$ModuleName = 'src'
$ModeFlag = @('--module', $ModuleName)

$env:CC = 'clang-cl'
$env:CXX = 'clang++'

$VenvPath = Join-Path $ProjectRoot 'venv'

try {
  # Ensure Nuitka exists
  try {
    Invoke-CondaRun -VenvPath $VenvPath -Args @('python', '-m', 'nuitka', '--version')
  } catch {
    Write-Host 'Nuitka not installed, installing now...'
    Invoke-CondaRun -VenvPath $VenvPath -Args @('python', '-m', 'pip', 'install', '-U', 'nuitka')
  }

  Write-Host 'Compiling (module mode)...'
  $nuitkaArgs = @(
    'python', '-m', 'nuitka',
    '--clang'
  ) + $ModeFlag + @(
    "--include-package=$ModuleName",
    '--python-flag=no_warnings,-O,no_docstrings'
  )
  Invoke-CondaRun -VenvPath $VenvPath -Args $nuitkaArgs

  Write-Host ''
  Write-Host "✅ Done! Output in $OutputDir"
  if (Test-Path $OutputDir) {
    Get-ChildItem -Name $OutputDir
  }
  exit 0
} catch {
  Write-Host 'An error occurred'
  Write-Error $_
  exit 1
}


