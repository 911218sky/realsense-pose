. (Join-Path $PSScriptRoot '..\common.ps1')

$ProjectRoot = Initialize-Script -ScriptRoot $PSScriptRoot

$OutputDir = 'dist'
$ModuleName = 'src'
$ModeFlag = @('--module', $ModuleName)

$env:CC = 'clang-cl'
$env:CXX = 'clang++'

$VenvPath = Get-VenvPath -ProjectRoot $ProjectRoot

try {
  # Ensure Nuitka exists
  try {
    Invoke-VenvRun -VenvPath $VenvPath -Args @('-m', 'nuitka', '--version')
  } catch {
    Write-Host 'Nuitka not installed, installing now...'
    & uv pip install --python $VenvPath -U nuitka
  }

  Write-Host 'Compiling (module mode)...'
  $nuitkaArgs = @(
    '-m', 'nuitka',
    '--clang'
  ) + $ModeFlag + @(
    "--include-package=$ModuleName",
    '--python-flag=no_warnings,-O,no_docstrings'
  )
  Invoke-VenvRun -VenvPath $VenvPath -Args $nuitkaArgs

  Write-Host ''
  Write-Host "Done! Output in $OutputDir"
  if (Test-Path $OutputDir) {
    Get-ChildItem -Name $OutputDir
  }
  exit 0
} catch {
  Write-Host 'An error occurred'
  Write-Error $_
  exit 1
}
