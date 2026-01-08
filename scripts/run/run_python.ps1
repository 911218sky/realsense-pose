. (Join-Path $PSScriptRoot '..\common.ps1')

$ProjectRoot = Initialize-Script -ScriptRoot $PSScriptRoot
$VenvPath = Get-VenvPath -ProjectRoot $ProjectRoot

try {
  # This matches the legacy hardcoded example in run_python.bat
  Invoke-VenvRun -VenvPath $VenvPath -Args @(
    'src/cli.py', 'analyze',
    '--npy', './outputs/1_1_1031/1_1_1031_pose.npy',
    '--output', './outputs/1_1_1031',
    '--tag', '1_1_1031',
    '--config', './configs/default_analyzer.yaml'
  )
  exit 0
} catch {
  Write-Error $_
  exit 1
}
