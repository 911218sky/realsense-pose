---
description: Project maintenance guidelines for Python under src/
alwaysApply: true
globs: ["src/**/*.py"]
---

# Project Maintenance Guidelines

Scope: All Python code under `src/` directory

## Project Overview

RealSense Pose — Pose estimation and rehabilitation analysis system using Intel RealSense camera and MediaPipe.

Tech Stack: FastAPI + MongoDB + Redis + Flutter Web UI

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

Dependency direction: Must flow downward only, circular dependencies are prohibited

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

## File Splitting Rules

| Rule | Description |
|------|-------------|
| Single Responsibility | One file, one topic (e.g., `lap_detector.py` only contains lap detection) |
| File Size Limit | Files exceeding 400-600 lines should be split into 2-4 modules |
| Facade Pattern | Keep old entry points for re-export (e.g., `rehab_analyzer.py`), maintain `from xxx import Y` unchanged |
| Utility Modules | Place common utilities in `utils/` or use precise naming like `cache_keys.py`, don't pile into one file |

## Naming Conventions

- Modules: `snake_case.py`
- Public API: Use `__all__` in `__init__.py` to manage re-exports
- Internal modules: Use `_xxx.py` prefix for private (don't rename if already referenced externally)
- Lazy import: Use `__getattr__` for heavy dependencies (matplotlib/cv2)

## Type Requirements

- Use `dataclass` for external data structures (e.g., `entities.py`) or Pydantic models (e.g., `api/v1/*/models.py`)
- All new/modified functions must have type hints
- Avoid using `Any`

## Caching Strategy

- API layer: Use `@redis_cache(expire=30)` decorator
- Analysis core: Use `cachetools.cachedmethod` + `TTLCache`
- Cache keys: Use `rehab_analyzer.cache_keys.method_key` uniformly
- Note: `ndarray`/`list` are not hashable, conversion required

## Post-Modification Checks

After every modification to `src/`, run:

```bash
python -m compileall src
```

If API schema or CLI behavior changes, perform smoke test verification.
