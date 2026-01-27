# Realsense Pose Deploy

One-click deployment scripts for Realsense Pose API.

## Directory Structure

```
realsense_pose_deploy/
├── setup/              # First-time setup scripts
├── service/            # Service control scripts
├── maintenance/        # Maintenance & cleanup scripts
└── backup/             # Backup & restore scripts
```

## Quick Start

### Windows

1. Download `realsense-pose-deploy.zip` and extract
2. Run `setup\install_docker.bat` if Docker Desktop is not installed
3. Make sure Docker Desktop is running
4. Run `setup\docker_login.bat` to login to registry (first time only)
5. Run `setup\deploy.bat`
6. Done! Visit http://localhost:8100

### Linux

```bash
docker compose up -d
```

## Scripts (Windows)

### 📦 setup/ — First-time Setup

| Script | Description |
|--------|-------------|
| `install_docker.bat` | Install Docker Desktop via winget |
| `install_helm.bat` | Install Helm via winget (optional, for K8s) |
| `docker_login.bat` | Login to ghcr.io registry |
| `deploy.bat` | First deploy: pull images and start services |

### 🚀 service/ — Service Control

| Script | Description |
|--------|-------------|
| `start.bat` | Start services (without pulling images) |
| `stop.bat` | Stop all containers |
| `restart.bat` | Restart all services |
| `update.bat` | Check for updates, restart only if changed |

### 🔧 maintenance/ — Maintenance

| Script | Description |
|--------|-------------|
| `fix_database.bat` | Run database migrations |
| `clean_project.bat` | Remove containers, images, and volumes |
| `prune_docker.bat` | Remove all unused Docker resources |

### 💾 backup/ — Backup & Restore

| Script | Description |
|--------|-------------|
| `backup_volumes.bat` | Manual backup of MongoDB and Redis |
| `restore_volumes.bat` | Restore data from backup |
| `migrate_to_volume.bat` | Migrate existing data to Docker Volume |

See `backup/README.md` for detailed backup documentation.

## Workflow

```
First Time              Daily Use               Maintenance
──────────────          ──────────────          ──────────────
setup\docker_login  →   service\update      →   maintenance\fix_database
setup\deploy            service\start           maintenance\clean_project
                        service\stop
                        service\restart
```

## Linux Commands

```bash
# Service Control
docker compose up -d              # Start
docker compose down               # Stop
docker compose restart            # Restart
docker compose pull && docker compose up -d  # Update

# Monitoring
docker compose ps                 # Status
docker compose logs -f            # Logs

# Maintenance
docker compose exec api python -m src.db.mongo.migration_runner  # Migrations
docker exec realsense-pose-backup /usr/local/bin/backup.sh       # Backup

# Cleanup
docker compose down -v --rmi all  # Remove everything
```

## Requirements

- Windows 10/11, Linux, or macOS
- Docker Desktop (Windows/Mac) or Docker Engine (Linux)
- At least 4GB available memory

## Configuration

A `.env` file will be created automatically on first run. You can customize:

- `NGINX_PORT` — API external port (default: 8100)
- `MONGO_ROOT_PASSWORD` — MongoDB password
- See `env.example` for all available options

## FAQ

**Q: "Docker is not available" error?**  
A: Make sure Docker Desktop is running

**Q: "unauthorized" error?**  
A: Run `setup\docker_login.bat`

**Q: How to completely reset?**  
A: Run `maintenance\clean_project.bat`

**Q: Database schema issues after update?**  
A: Run `maintenance\fix_database.bat`
