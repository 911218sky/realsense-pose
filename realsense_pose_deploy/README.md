# Realsense Pose Deploy

One-click deployment scripts for Realsense Pose API on Windows.

## Quick Start

1. Download `realsense-pose_deploy.zip` and extract
2. Run `install_docker.bat` if Docker Desktop is not installed
3. Make sure Docker Desktop is running
4. Double-click `docker_login.bat` to login to registry (first time only)
5. Double-click `deploy.bat`
6. Done! Visit http://localhost:8100/v1

## Scripts

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

## Workflow

```
First Time Setup    →    Daily Update    →    Stop Services    →    Restart
docker_login             update               stop                  deploy
deploy
```

## Requirements

- Windows 10/11
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- At least 4GB available memory

## Configuration

A `.env` file will be created automatically on first run. You can customize:
- `NGINX_PORT` - API external port (default: 8100)
- `MONGO_ROOT_PASSWORD` - MongoDB password
- See `env.example` for all available options

## Data Storage

All data is stored in the script directory:
```
./data/mongo/   - MongoDB data
./data/redis/   - Redis data
./outputs/      - Output results
```

## FAQ

**Q: "Docker is not available" error?**  
A: Make sure Docker Desktop is running

**Q: "unauthorized" or "pull access denied" error?**  
A: Run `docker_login.bat` to login to the registry

**Q: How to completely reset the environment?**  
A: Run `clean_project.bat` and choose to delete data directories

**Q: How to check service status?**  
A: Open terminal and run `docker compose ps`
