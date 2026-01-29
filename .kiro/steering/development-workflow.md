# Development Workflow

## Environment Setup

### Prerequisites
- **Python:** Managed by `uv` (see `.python-version`)
- **Docker:** Required for MongoDB and Redis
- **Git:** For version control

### Initial Setup
```bash
# Clone and setup
git clone <repository>
cd realsense-pose

# Install dependencies with uv
uv sync

# Copy environment configuration
cp env.example .env
# Edit .env with your settings

# Start databases
docker compose -f docker-compose.db.yml up -d

# Run API with database
./scripts/run/run_api_with_db.ps1
```

## Development Scripts

### PowerShell Scripts Location
All development scripts are in `scripts/` directory:

```
scripts/
├── run/                    # Application runners
│   ├── run_api.ps1        # API only
│   ├── run_api_with_db.ps1 # API + databases
│   └── cli.ps1            # CLI interface
├── docker/                # Docker management
│   ├── docker_build_push.ps1
│   ├── docker_clean_all.ps1
│   └── docker_redeploy.ps1
├── github/                # Git/GitHub utilities
│   ├── merge_to_main.ps1
│   ├── release.ps1
│   └── clean-tags.ps1
└── backup/                # Backup utilities
    ├── backup_volumes.bat
    └── restore_volumes.bat
```

### Common Development Commands

#### Start Development Environment
```powershell
# Full stack (API + databases)
.\scripts\run\run_api_with_db.ps1

# API only (assumes databases running)
.\scripts\run\run_api.ps1

# CLI interface
.\scripts\run\cli.ps1
```

#### Docker Management
```powershell
# Clean everything and restart
.\scripts\docker\docker_clean_all.ps1 --nuke
.\scripts\docker\docker_redeploy.ps1

# Build and push images
.\scripts\docker\docker_build_push.ps1
```

## Code Quality Checks

### Pre-commit Validation
Before committing, always run:

```bash
# Compile check (required)
python -m compileall src

# Type checking (recommended)
mypy src --ignore-missing-imports

# Import validation
python -c "from rehab_analyzer import RehabilitationSessionAnalyzer"
python -c "from realsense_pose_extractor import PoseProcessor"
```

### Testing Strategy
```bash
# Run all tests
pytest src/tests/

# Run specific test categories
pytest src/tests/gait/          # Gait analysis tests
pytest src/tests/lap/           # Lap detection tests
pytest src/tests/balance/       # Balance analysis tests

# Run with coverage
pytest --cov=src src/tests/
```

## Database Management

### MongoDB Operations
```bash
# Connect to MongoDB
docker exec -it realsense-pose-mongo-dev mongosh "mongodb://root:password@localhost:27017/admin"

# Backup database
.\scripts\backup\backup_volumes.bat

# Restore database
.\scripts\backup\restore_volumes.bat
```

### Redis Operations
```bash
# Connect to Redis
docker exec -it realsense-pose-redis-dev redis-cli

# Clear cache
docker exec -it realsense-pose-redis-dev redis-cli FLUSHALL
```

## API Development Workflow

### Adding New Endpoints

1. **Create route module** in `src/api/v1/<module>/`
2. **Define Pydantic models** in `models.py`
3. **Implement business logic** in core modules
4. **Add route to router** in `__init__.py`
5. **Write tests** in `src/tests/`
6. **Update documentation**

#### Example: Adding New Analysis Endpoint
```python
# 1. Create src/api/v1/new_analyzer/models.py
from pydantic import BaseModel
from typing import List

class AnalysisRequest(BaseModel):
    session_id: str
    parameters: dict

class AnalysisResponse(BaseModel):
    results: dict
    confidence: float

# 2. Create src/api/v1/new_analyzer/new_analyzer.py
from fastapi import APIRouter, HTTPException
from .models import AnalysisRequest, AnalysisResponse

router = APIRouter()

@router.post("/analyze", response_model=AnalysisResponse)
async def analyze_session(request: AnalysisRequest):
    try:
        # Business logic here
        results = await perform_analysis(request.session_id, request.parameters)
        return AnalysisResponse(results=results, confidence=0.95)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 3. Update src/api/v1/__init__.py
from .new_analyzer.new_analyzer import router as new_analyzer_router
app.include_router(new_analyzer_router, prefix="/new-analyzer", tags=["analysis"])
```

### Core Module Development

#### Adding Analysis Features

1. **Create module** in `src/rehab_analyzer/` or `src/realsense_pose_extractor/`
2. **Define data structures** in `entities.py`
3. **Implement core logic** following single responsibility principle
4. **Add caching** if computationally expensive
5. **Update facade classes** to expose new functionality

#### Example: Adding New Gait Metric
```python
# 1. Add to src/rehab_analyzer/entities.py
@dataclass
class NewGaitMetric:
    value: float
    confidence: float
    timestamp: float

# 2. Create src/rehab_analyzer/new_metric_analyzer.py
from typing import List
import numpy as np
from .entities import PoseData, NewGaitMetric

def calculate_new_metric(pose_data: List[PoseData]) -> NewGaitMetric:
    """Calculate new gait metric from pose data."""
    # Implementation here
    pass

# 3. Update src/rehab_analyzer/session_analyzer.py
from .new_metric_analyzer import calculate_new_metric

class RehabilitationSessionAnalyzer:
    def analyze_new_metric(self) -> NewGaitMetric:
        return calculate_new_metric(self.pose_data)
```

## Release Process

### Version Management
Follow semantic versioning (vMAJOR.MINOR.PATCH):

```bash
# Check current version
git tag | sort -V | tail -1

# Create new version
git tag -a v1.2.0 -m "Release v1.2.0 - Add new gait analysis features"
git push origin v1.2.0
```

### Release Workflow
```powershell
# 1. Merge develop to main
.\scripts\github\merge_to_main.ps1

# 2. Create release
.\scripts\github\release.ps1 -Version "v1.2.0" -Message "New features and bug fixes"

# 3. Build and push Docker images
.\scripts\docker\docker_build_push.ps1 -Tag "v1.2.0"
```

## Debugging Guidelines

### Common Issues

#### Import Errors
```bash
# Check Python path
python -c "import sys; print('\n'.join(sys.path))"

# Verify module structure
python -m compileall src

# Test specific imports
python -c "from src.rehab_analyzer import RehabilitationSessionAnalyzer"
```

#### Database Connection Issues
```bash
# Check container status
docker ps

# Check logs
docker logs realsense-pose-mongo-dev
docker logs realsense-pose-redis-dev

# Test connections
docker exec realsense-pose-mongo-dev mongosh --eval "db.adminCommand('ping')"
docker exec realsense-pose-redis-dev redis-cli ping
```

#### Performance Issues
```python
# Add timing decorators
from utils.timing import timing_decorator

@timing_decorator
def expensive_function():
    pass

# Use profiling
import cProfile
cProfile.run('your_function()')
```

### Logging Configuration
```python
# Use project logger
from logger import setup_logger

logger = setup_logger(__name__)

# Log levels by environment
# Development: DEBUG
# Staging: INFO  
# Production: WARNING
```

## Environment-Specific Configurations

### Development (.env)
```bash
IS_PROD=0
API_PORT=8100
MONGO_PORT=27015
REDIS_PORT=6379
USE_REDIS_CACHE=0  # Disabled in dev
```

### Production (.env)
```bash
IS_PROD=1
API_PORT=8100
MONGO_PORT=27015
REDIS_PORT=6379
USE_REDIS_CACHE=1  # Enabled in prod
```

## Troubleshooting Checklist

### Before Asking for Help
1. ✅ Check container status: `docker ps`
2. ✅ Verify environment variables: `cat .env`
3. ✅ Run compile check: `python -m compileall src`
4. ✅ Check logs: `docker logs <container_name>`
5. ✅ Test database connections
6. ✅ Verify Python environment: `uv run python --version`

### Common Solutions
- **Import errors:** Check `PYTHONPATH` and module structure
- **Database errors:** Restart containers, check credentials
- **Port conflicts:** Change ports in `.env`, restart services
- **Permission errors:** Check file permissions, Docker daemon status