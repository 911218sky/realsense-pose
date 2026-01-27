# 檢查命令列參數
param(
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$Arguments = @()
)

. (Join-Path $PSScriptRoot '..\common.ps1')

$ProjectRoot = Initialize-Script -ScriptRoot $PSScriptRoot
$VenvPath = Get-VenvPath -ProjectRoot $ProjectRoot

try {
    # 直接調用 CLI，傳遞所有參數
    Write-Host "執行 CLI..." -ForegroundColor Green
    
    # 如果沒有參數，顯示幫助
    if ($Arguments.Count -eq 0) {
        $Arguments = @("--help")
    }
    
    Invoke-VenvRun -VenvPath $VenvPath -Args (@('src/cli.py') + $Arguments)
    
    Write-Host "執行完成!" -ForegroundColor Green
    exit 0
} catch {
    Write-Error "執行失敗: $_"
    exit 1
}