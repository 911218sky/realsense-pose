## Scripts Directory Structure

- `scripts/backup/`: Backup and restore tools for Docker Volumes
- `scripts/build/`: Build/compile scripts (Nuitka, PyInstaller)
- `scripts/docker/`: Docker Compose related (run/redeploy/clean/build+push)
- `scripts/env/`: Development environment setup (Conda + pip install)
- `scripts/python/`: Python/dependency tools
- `scripts/run/`: Local startup/development entry points (API, CLI)
- `scripts/web/`: Web static asset tools
- `scripts/github/`: GitHub release and workflow tools

## Usage (Windows / PowerShell)

Recommended to use PowerShell 7:

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File scripts\docker\docker_run.ps1
```