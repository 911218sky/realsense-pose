# Realsense Pose Deploy

One-click deployment scripts for Realsense Pose API.

## Quick Start

### Windows

1. Download `realsense-pose-deploy.zip` and extract
2. Run `install_docker.bat` if Docker Desktop is not installed
3. Make sure Docker Desktop is running
4. Double-click `docker_login.bat` to login to registry (first time only)
5. Double-click `deploy.bat`
6. Done! Visit http://localhost:8100

### Linux

1. Install Docker (see below)
2. Clone or download the project
3. Copy `env.example` to `.env` and configure
4. Run:
```bash
docker compose up -d
```
5. Done! Visit http://localhost:8100

## Install Docker

### Windows

**Option 1: Using winget (recommended)**
```powershell
winget install Docker.DockerDesktop
```

**Option 2: Manual download**
1. Download from [Docker Desktop](https://www.docker.com/products/docker-desktop/)
2. Run installer and follow instructions
3. Restart computer if prompted

### Linux (Ubuntu/Debian)

```bash
# Remove old versions
sudo apt-get remove docker docker-engine docker.io containerd runc

# Install dependencies
sudo apt-get update
sudo apt-get install ca-certificates curl gnupg

# Add Docker's official GPG key
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

# Add repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker
sudo apt-get update
sudo apt-get install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Add user to docker group (optional, avoids sudo)
sudo usermod -aG docker $USER
newgrp docker
```

### Linux (CentOS/RHEL/Fedora)

```bash
# Install dependencies
sudo yum install -y yum-utils

# Add repository
sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo

# Install Docker
sudo yum install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Start Docker
sudo systemctl start docker
sudo systemctl enable docker

# Add user to docker group (optional)
sudo usermod -aG docker $USER
```

### macOS

```bash
# Using Homebrew
brew install --cask docker

# Then open Docker.app from Applications
```

Or download from [Docker Desktop for Mac](https://www.docker.com/products/docker-desktop/)

## Scripts (Windows)

| Script | Description |
|--------|-------------|
| `install_docker.bat` | 🐳 Install Docker Desktop via winget |
| `install_helm.bat` | 📦 Install Helm via winget (optional, for K8s deployment) |
| `docker_login.bat` | 🔑 Login to Docker Hub / ghcr.io (first time only) |
| `deploy.bat` | 🚀 First deploy: pull images and start all services |
| `update.bat` | 🔄 Update: pull latest images and restart |
| `stop.bat` | ⏹️ Stop: shut down all containers |
| `clean_project.bat` | 🧹 Clean project: remove containers, images, volumes |
| `prune_docker.bat` | 🗑️ Prune Docker: remove all unused Docker resources |

### Backup Scripts (backup/)

| Script | Description |
|--------|-------------|
| `backup/backup_volumes.bat` | 💾 Manual backup of MongoDB and Redis data |
| `backup/restore_volumes.bat` | 📥 Restore data from backup |
| `backup/migrate_to_volume.bat` | 🔄 Migrate existing data to Docker Volume |

See `backup/README.md` for detailed backup documentation.

## Linux Commands

```bash
# Deploy
docker compose up -d

# Update
docker compose pull && docker compose up -d

# Stop
docker compose down

# View logs
docker compose logs -f

# Check status
docker compose ps

# Manual backup
docker exec realsense-pose-backup /usr/local/bin/backup.sh

# Clean up
docker compose down -v --rmi all
```

## Workflow

```
First Time Setup    →    Daily Update    →    Stop Services    →    Restart
docker_login             update               stop                  deploy
deploy
```

## Requirements

- Windows 10/11, Linux, or macOS
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows/Mac) or Docker Engine (Linux)
- At least 4GB available memory

## Configuration

A `.env` file will be created automatically on first run. You can customize:

- `NGINX_PORT` - API external port (default: 8100)
- `MONGO_ROOT_PASSWORD` - MongoDB password
- See `env.example` for all available options

## Data Storage

MongoDB and Redis data are stored in Docker Volumes for better performance:

```
Docker Volumes:
realsense-pose-mongo-data   - MongoDB data
realsense-pose-redis-data   - Redis data

Backups:
./backups/                  - Backup files (auto & manual)
```

## Automatic Backup

The deployment includes an automatic backup service that runs inside Docker:

- **Schedule**: Daily at 2:00 AM (configurable via `BACKUP_CRON` in `.env`)
- **Retention**: Keeps last 7 backups (configurable via `MAX_BACKUPS` in `.env`)
- **Location**: `./backups/` directory

**Manual backup/restore:**
- Windows: `backup\backup_volumes.bat` / `backup\restore_volumes.bat`
- Linux: `docker exec realsense-pose-backup /usr/local/bin/backup.sh`

See `backup/README.md` for more details.

## FAQ

**Q: "Docker is not available" error?**  
A: Make sure Docker Desktop is running (Windows/Mac) or Docker service is started (Linux: `sudo systemctl start docker`)

**Q: "unauthorized" or "pull access denied" error?**  
A: Run `docker_login.bat` (Windows) or `docker login ghcr.io` (Linux)

**Q: How to completely reset the environment?**  
A: Run `clean_project.bat` (Windows) or `docker compose down -v --rmi all` (Linux)

**Q: How to check service status?**  
A: Run `docker compose ps`

**Q: How to change backup schedule?**  
A: Edit `BACKUP_CRON` in `.env` file (cron format, default: `0 2 * * *` = 2 AM daily)

**Q: Permission denied on Linux?**  
A: Add your user to docker group: `sudo usermod -aG docker $USER` then logout/login
