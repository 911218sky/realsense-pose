import os
from pathlib import Path

DATA_DIR = Path("./data")
NPY_DIR = DATA_DIR / "npy"
BAG_DIR = DATA_DIR / "bag"

NPY_DIR.mkdir(parents=True, exist_ok=True)
BAG_DIR.mkdir(parents=True, exist_ok=True)

# Container-side dataset mount path (default: docker-compose mounts host dataset to /app/dataset)
DATASET_DIR = Path((os.getenv("DATASET_DIR") or "").strip() or "/app/dataset")

# Dataset mount info (for mapping client paths -> container paths)
# - HOST_DATASET_DIR: host-side directory you mount (e.g. ./bb or /srv/dataset/bb)
HOST_DATASET_DIR = (os.getenv("HOST_DATASET_DIR") or "").strip() or None

GITHUB_REPO = "911218sky/gait-charts"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"