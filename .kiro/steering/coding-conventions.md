# Coding Conventions

## File Organization Rules

### File Splitting Guidelines

| Rule | Description |
|------|-------------|
| **Single Responsibility** | One file, one topic (e.g., `lap_detector.py` only contains lap detection) |
| **File Size Limit** | Files exceeding 400-600 lines should be split into 2-4 modules |
| **Facade Pattern** | Keep old entry points for re-export (e.g., `rehab_analyzer.py`), maintain `from xxx import Y` unchanged |
| **Utility Modules** | Place common utilities in `utils/` or use precise naming like `cache_keys.py`, don't pile into one file |

### Naming Conventions

- **Modules:** `snake_case.py`
- **Public API:** Use `__all__` in `__init__.py` to manage re-exports
- **Internal modules:** Use `_xxx.py` prefix for private (don't rename if already referenced externally)
- **Lazy import:** Use `__getattr__` for heavy dependencies (matplotlib/cv2)

## Python Code Standards

### Type Requirements
- Use `dataclass` for external data structures (e.g., `entities.py`) or Pydantic models (e.g., `api/v1/*/models.py`)
- **All new/modified functions must have type hints**
- Avoid using `Any` - be specific with types
- Use `from typing import` for complex types

### Example Type Annotations
```python
from typing import List, Dict, Optional, Union
from dataclasses import dataclass
import numpy as np

@dataclass
class PoseData:
    landmarks: np.ndarray
    timestamp: float
    confidence: float

def process_pose_data(
    data: List[PoseData], 
    threshold: float = 0.5
) -> Dict[str, Union[int, float]]:
    """Process pose data with proper type hints."""
    pass
```

## Caching Strategy

### Cache Implementation Patterns

- **API layer:** Use `@redis_cache(expire=30)` decorator
- **Analysis core:** Use `cachetools.cachedmethod` + `TTLCache`
- **Cache keys:** Use `rehab_analyzer.cache_keys.method_key` uniformly
- **Note:** `ndarray`/`list` are not hashable, conversion required

### Cache Key Examples
```python
# In cache_keys.py
def gait_analysis_key(user_id: str, session_id: str) -> str:
    return f"gait_analysis:{user_id}:{session_id}"

def pose_processing_key(bag_file: str, config_hash: str) -> str:
    return f"pose_proc:{bag_file}:{config_hash}"
```

## Import Organization

### Import Order
1. Standard library imports
2. Third-party imports (numpy, fastapi, etc.)
3. Local application imports (from src/)

### Import Style Examples
```python
# Standard library
import os
import logging
from pathlib import Path
from typing import List, Dict, Optional

# Third-party
import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException
from beanie import Document

# Local imports
from db.mongo.models import UserProfile
from utils.file import ensure_dir
from rehab_analyzer.entities import GaitMetrics
```

## Error Handling

### Exception Patterns
```python
# API layer - use HTTPException
from fastapi import HTTPException

def get_user_data(user_id: str):
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID is required")
    
    try:
        # Process data
        pass
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"Invalid data: {e}")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

# Core modules - use specific exceptions
class PoseProcessingError(Exception):
    """Raised when pose processing fails."""
    pass

def process_pose_data(data):
    if not data:
        raise ValueError("Pose data cannot be empty")
    
    try:
        # Process
        pass
    except Exception as e:
        raise PoseProcessingError(f"Failed to process pose data: {e}") from e
```

## Documentation Standards

### Docstring Format
```python
def analyze_gait_pattern(
    pose_data: List[PoseData], 
    config: GaitConfig
) -> GaitMetrics:
    """
    Analyze gait patterns from pose data.
    
    Args:
        pose_data: List of pose landmarks with timestamps
        config: Configuration parameters for gait analysis
        
    Returns:
        GaitMetrics containing stride length, cadence, and symmetry
        
    Raises:
        ValueError: If pose_data is empty or invalid
        PoseProcessingError: If analysis fails
        
    Example:
        >>> config = GaitConfig(min_confidence=0.7)
        >>> metrics = analyze_gait_pattern(pose_data, config)
        >>> print(f"Stride length: {metrics.stride_length}")
    """
    pass
```

## Post-Modification Validation

### Required Checks
After every modification to `src/`, run:

```bash
python -m compileall src
```

### Smoke Testing
If API schema or CLI behavior changes, perform smoke test verification:

```bash
# Test API endpoints
curl http://localhost:8100/api/v1/health

# Test CLI functionality  
python src/cli.py --help

# Verify imports work
python -c "from rehab_analyzer import RehabilitationSessionAnalyzer"
```

## Performance Considerations

### Lazy Loading
```python
# For heavy dependencies like matplotlib, opencv
def __getattr__(name: str):
    if name == "plt":
        import matplotlib.pyplot as plt
        globals()["plt"] = plt
        return plt
    elif name == "cv2":
        import cv2
        globals()["cv2"] = cv2
        return cv2
    raise AttributeError(f"module {__name__} has no attribute {name}")
```

### Memory Management
- Use generators for large datasets
- Clear large arrays when no longer needed
- Use `del` for explicit cleanup of heavy objects
- Consider using `numpy.memmap` for very large files