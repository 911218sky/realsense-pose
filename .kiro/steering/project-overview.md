# RealSense Pose Project Overview

## Project Description
RealSense Pose — Pose estimation and rehabilitation analysis system using Intel RealSense camera and MediaPipe.

**Tech Stack:** FastAPI + MongoDB + Redis + Flutter Web UI

## Architecture Layers

```
src/
├── api/                    # Application layer: FastAPI routes & middlewares
│   ├── v1/                 # Versioned API routes
│   │   ├── rehab_analyzer/ # Rehabilitation analysis API endpoints
│   │   ├── realsense_pose_extractor/  # Pose extraction API
│   │   ├── users/          # User management
│   │   └── admins/         # Admin authentication
│   ├── auth/               # Auth module (signed headers)
│   ├── middlewares/        # Middlewares (payload decode)
│   └── utils/              # API utilities (cache, codec, env)
├── rehab_analyzer/         # Analysis core: gait/lap/FFT analysis
│   ├── session_analyzer.py # Facade: RehabilitationSessionAnalyzer
│   ├── lap_detector.py     # Lap detection
│   ├── gait_analyzer.py    # Gait analysis
│   ├── fft_analyzer.py     # Spectrum analysis
│   ├── pose_processor.py   # Pose preprocessing
│   ├── data_loader.py      # Data loading
│   ├── entities.py         # Data structures (dataclass)
│   └── visualizer.py       # Visualization (lazy import)
├── realsense_pose_extractor/  # Pose extraction core
│   ├── processor.py        # Facade: PoseProcessor
│   ├── pipeline.py         # RealSense pipeline
│   ├── bag_io.py           # .bag file I/O
│   ├── pose_ops.py         # Pose operations
│   └── video_overlay.py    # Video overlay
├── db/                     # Data layer: MongoDB models
│   └── mongo/models/       # Beanie document models
├── config/                 # Configuration loading (YAML)
├── logger/                 # Logging setup
├── utils/                  # Shared utilities
└── cli.py                  # CLI entry point
```

## Dependency Rules
**CRITICAL:** Dependency direction must flow downward only, circular dependencies are prohibited

```
API Routes (api/v1/*)
    ↓
Facade (session_analyzer / processor)
    ↓
Analysis Core (lap_detector / gait_analyzer / fft_analyzer)
    ↓
Preprocessing (pose_processor / data_loader)
    ↓
Data Layer (db / config / utils)
```

## Core Principles

1. **Maintainability First** — Clear module boundaries, easy to locate, test, and replace
2. **External Compatibility** — Preserve existing import paths and APIs during refactoring, avoid breaking API/CLI/Visualizer
3. **Readability** — Distribute complexity across multiple small files, avoid long functions/files

## Technology Stack

### Backend
- **Framework:** FastAPI
- **Database:** MongoDB (with Beanie ODM)
- **Cache:** Redis
- **Authentication:** Signed headers with JWT
- **File Processing:** Intel RealSense SDK, MediaPipe
- **Data Analysis:** NumPy, SciPy, pandas

### Frontend
- **Framework:** Flutter Web UI
- **API Communication:** REST API

### Infrastructure
- **Containerization:** Docker + Docker Compose
- **Deployment:** Kubernetes (Helm charts available)
- **Monitoring:** Nginx, Fail2ban
- **Backup:** Automated MongoDB/Redis backups

### Development Tools
- **Package Management:** uv (Python)
- **Code Quality:** Type hints required, compileall validation
- **Testing:** pytest (implied from structure)
- **Scripts:** PowerShell automation scripts