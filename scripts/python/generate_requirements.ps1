. (Join-Path $PSScriptRoot '..\_common.ps1')

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
  Write-Host '🔍 分析專案依賴中...'
  Write-Host "📁 忽略目錄: $IgnoreString"
  Write-Host ''

  # Check pipreqs availability (try running help)
  $rc = Try-CondaRun -VenvPath $VenvPath -Args @('pipreqs', '--help')
  if ($rc -ne 0) {
    Write-Host '❌ pipreqs 未安裝，正在安裝...'
    Invoke-CondaRun -VenvPath $VenvPath -Args @('python', '-m', 'pip', 'install', 'pipreqs')
  } else {
    Write-Host '✅ pipreqs 已安裝'
  }

  Write-Host ''
  Write-Host '正在執行 pipreqs，這可能需要一點時間...'

  $rc = Try-CondaRun -VenvPath $VenvPath -Args @(
    'pipreqs', '.\src',
    '--encoding=utf-8-sig',
    '--ignore', $IgnoreString,
    '--mode', 'compat',
    '--force',
    '--savepath', $OutputFile
  )
  if ($rc -ne 0) {
    Write-Host 'pipreqs 執行失敗，改用 python -m pipreqs 嘗試...'
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
    Write-Host "✅ $OutputFile 產生成功！"
    Write-Host ''
    Write-Host '📋 產生的依賴清單如下：'
    Write-Host '===================='
    Get-Content $OutputFile
    Write-Host '===================='
    Write-Host ''
    Write-Host "💡 要安裝依賴，請執行: pip install -r $OutputFile"
    exit 0
  }

  throw "❗ 未找到 $OutputFile，可能是 pipreqs 未產生檔案或發生錯誤。"
} catch {
  Write-Host ''
  Write-Host '====== 發生錯誤 ======'
  Write-Host '無法完成 requirements 檔案產生。請檢查上方訊息以找出錯誤原因。'
  Write-Host '======================'
  Write-Error $_
  exit 1
}


