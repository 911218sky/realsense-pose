. (Join-Path $PSScriptRoot '..\common.ps1')

$ProjectRoot = Initialize-Script -ScriptRoot $PSScriptRoot

$VenvPath = Get-VenvPath -ProjectRoot $ProjectRoot
$OutputFile = 'requirements.txt'

$IgnoreList = @(
  'runtime',
  'venv',
  'env',
  '.venv',
  '.git',
  '__pycache__',
  'src/crawler',
  'yolov12',
  'build',
  'dist'
)
$IgnoreString = ($IgnoreList -join ',')

try {
  Write-Host 'Analyzing project dependencies...'
  Write-Host "Ignoring directories: $IgnoreString"
  Write-Host ''

  # Check pipreqs availability
  $rc = Try-VenvRun -VenvPath $VenvPath -Args @('-m', 'pipreqs', '--help')
  if ($rc -ne 0) {
    Write-Host 'pipreqs not installed, installing now...'
    & uv pip install --python $VenvPath pipreqs
  } else {
    Write-Host 'pipreqs already installed'
  }

  Write-Host ''
  Write-Host 'Running pipreqs, this may take a moment...'

  $rc = Try-VenvRun -VenvPath $VenvPath -Args @(
    '-m', 'pipreqs.pipreqs', '.\src',
    '--encoding=utf-8-sig',
    '--ignore', $IgnoreString,
    '--mode', 'compat',
    '--force',
    '--savepath', $OutputFile
  )
  if ($rc -ne 0) {
    throw "pipreqs execution failed"
  }

  if (Test-Path $OutputFile) {
    Write-Host ''
    Write-Host "$OutputFile generated successfully!"
    Write-Host ''
    Write-Host 'Generated dependency list:'
    Write-Host '===================='
    Get-Content $OutputFile
    Write-Host '===================='
    Write-Host ''
    Write-Host "Tip: To install dependencies, run: uv pip install -r $OutputFile"
    exit 0
  }

  throw "Failed to generate $OutputFile, pipreqs may not have created the file or an error occurred."
} catch {
  Write-Host ''
  Write-Host '====== An Error Occurred ======'
  Write-Host 'Unable to complete requirements file generation. Please check the message above for the error cause.'
  Write-Host '=============================='
  Write-Error $_
  exit 1
}
