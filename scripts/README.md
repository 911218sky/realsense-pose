## scripts 目錄結構

- `scripts/build/`: 打包/編譯（Nuitka、PyInstaller）
- `scripts/docker/`: Docker Compose 相關（run/redeploy/clean/build+push）
- `scripts/env/`: 開發環境建置（Conda + pip 安裝）
- `scripts/python/`: Python/依賴工具
- `scripts/run/`: 本機啟動/開發用入口（API、CLI）
- `scripts/web/`: Web 靜態資產工具

## 執行方式（Windows / PowerShell）

建議用 PowerShell 7：

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File scripts\docker\docker_run.ps1
```