. (Join-Path $PSScriptRoot '..\common.ps1')

$ProjectRoot = Initialize-Script -ScriptRoot $PSScriptRoot

$VenvPath = Join-Path $ProjectRoot 'venv'
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

  # Check pipreqs availability (try running help)
  $rc = Try-CondaRun -VenvPath $VenvPath -Args @('pipreqs', '--help')
  if ($rc -ne 0) {
    Write-Host 'pipreqs not installed, installing now...'
    Invoke-CondaRun -VenvPath $VenvPath -Args @('python', '-m', 'pip', 'install', 'pipreqs')
  } else {
    Write-Host 'pipreqs already installed'
  }

  Write-Host ''
  Write-Host 'Running pipreqs, this may take a moment...'

  $rc = Try-CondaRun -VenvPath $VenvPath -Args @(
    'pipreqs', '.\src',
    '--encoding=utf-8-sig',
    '--ignore', $IgnoreString,
    '--mode', 'compat',
    '--force',
    '--savepath', $OutputFile
  )
  if ($rc -ne 0) {
    Write-Host 'pipreqs execution failed, trying with python -m pipreqs...'
    Invoke-CondaRun -VenvPath $VenvPath -Args @(
      'python', '-m', 'pipreqs', '.\src',
      '--encoding=utf-8-sig',
      '--ignore', $IgnoreString,
      '--mode', 'compat',
      '--force',
      '--savepath', $OutputFile
    )
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
    Write-Host "Tip: To install dependencies, run: pip install -r $OutputFile"
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


