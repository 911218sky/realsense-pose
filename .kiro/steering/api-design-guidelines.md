# API Design Guidelines

## FastAPI Standards

### Route Organization

Follow the established pattern in `src/api/v1/`:

```
api/v1/
├── admins/           # Admin authentication & management
├── users/            # User profile management  
├── realsense_pose_extractor/  # Pose extraction endpoints
├── rehab_analyzer/   # Rehabilitation analysis endpoints
└── cohort_benchmark/ # Cohort comparison endpoints
```

### Endpoint Naming Conventions

- **Use kebab-case for URLs:** `/api/v1/pose-extraction/process`
- **Use plural nouns for collections:** `/users`, `/sessions`, `/analyses`
- **Use singular for single resources:** `/user/{user_id}`, `/session/{session_id}`
- **Use verbs for actions:** `/pose-extraction/start`, `/analysis/generate-report`

### HTTP Methods & Status Codes

| Method | Purpose | Success Status | Error Status |
|--------|---------|----------------|--------------|
| GET | Retrieve data | 200 | 404, 400 |
| POST | Create resource | 201 | 400, 422, 409 |
| PUT | Update entire resource | 200 | 400, 404, 422 |
| PATCH | Partial update | 200 | 400, 404, 422 |
| DELETE | Remove resource | 204 | 404, 409 |

### Response Format Standards

#### Success Response
```python
# Single resource
{
    "data": {
        "id": "user_123",
        "name": "John Doe",
        "created_at": "2024-01-15T10:30:00Z"
    },
    "meta": {
        "timestamp": "2024-01-15T10:30:00Z"
    }
}

# Collection with pagination
{
    "data": [...],
    "meta": {
        "total": 150,
        "page": 1,
        "page_size": 50,
        "total_pages": 3
    }
}
```

#### Error Response
```python
{
    "error": {
        "code": "VALIDATION_ERROR",
        "message": "Invalid input data",
        "details": {
            "field": "email",
            "reason": "Invalid email format"
        }
    }
}
```

### Pydantic Models

#### Request/Response Models
```python
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class UserCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: str = Field(..., regex=r'^[^@]+@[^@]+\.[^@]+$')
    age: Optional[int] = Field(None, ge=0, le=150)

class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    created_at: datetime
    
    class Config:
        from_attributes = True

class PaginatedResponse(BaseModel):
    data: List[UserResponse]
    meta: dict
```

### Authentication & Authorization

#### Signed Headers Pattern
```python
from api.auth import require_admin, get_current_user
from api.auth.dependencies import AuthenticatedUser

@router.get("/admin/users")
async def list_users(
    current_admin: AuthenticatedUser = Depends(require_admin)
):
    """Admin-only endpoint."""
    pass

@router.get("/profile")
async def get_profile(
    current_user: AuthenticatedUser = Depends(get_current_user)
):
    """User profile endpoint."""
    pass
```

### Error Handling Patterns

#### API Layer Error Handling
```python
from fastapi import HTTPException
import logging

logger = logging.getLogger(__name__)

@router.post("/process-pose")
async def process_pose_data(request: PoseProcessRequest):
    try:
        # Validate input
        if not request.bag_file_path:
            raise HTTPException(
                status_code=400, 
                detail="bag_file_path is required"
            )
        
        # Process data
        result = await pose_processor.process(request.bag_file_path)
        
        return {"data": result}
        
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail="Bag file not found")
    except Exception as e:
        logger.error(f"Unexpected error in pose processing: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, 
            detail="Internal server error during pose processing"
        )
```

### Caching Strategy

#### Redis Cache Decorator
```python
from api.utils.cache import redis_cache

@router.get("/analysis/{session_id}")
@redis_cache(expire=300)  # 5 minutes
async def get_analysis_results(session_id: str):
    """Cached analysis results."""
    return await analysis_service.get_results(session_id)
```

### Background Tasks

#### Long-running Operations
```python
from fastapi import BackgroundTasks
from api.v1.realsense_pose_extractor.extract_utils import process_bag_async

@router.post("/extract/start")
async def start_extraction(
    request: ExtractionRequest,
    background_tasks: BackgroundTasks
):
    """Start pose extraction as background task."""
    job_id = generate_job_id()
    
    # Store job status
    await job_store.create_job(job_id, "pending")
    
    # Start background processing
    background_tasks.add_task(
        process_bag_async, 
        job_id, 
        request.bag_file_path,
        request.config
    )
    
    return {
        "data": {
            "job_id": job_id,
            "status": "pending"
        }
    }

@router.get("/extract/status/{job_id}")
async def get_extraction_status(job_id: str):
    """Check extraction job status."""
    job = await job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return {"data": job}
```

## Database Integration

### MongoDB with Beanie

#### Document Models
```python
from beanie import Document
from pydantic import Field
from datetime import datetime
from typing import Optional

class UserProfile(Document):
    name: str
    email: str = Field(..., unique=True)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = None
    
    class Settings:
        collection = "user_profiles"
        indexes = [
            "email",
            [("created_at", -1)],
        ]

# Usage in API
@router.post("/users", response_model=UserResponse)
async def create_user(request: UserCreateRequest):
    # Check if user exists
    existing = await UserProfile.find_one({"email": request.email})
    if existing:
        raise HTTPException(status_code=409, detail="User already exists")
    
    # Create new user
    user = UserProfile(**request.dict())
    await user.insert()
    
    return UserResponse.from_orm(user)
```

### Query Patterns
```python
# Pagination
@router.get("/users", response_model=PaginatedResponse)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200)
):
    skip = (page - 1) * page_size
    
    users = await UserProfile.find().skip(skip).limit(page_size).to_list()
    total = await UserProfile.count()
    
    return PaginatedResponse(
        data=[UserResponse.from_orm(user) for user in users],
        meta={
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size
        }
    )
```

## Testing Guidelines

### API Testing Structure
```python
import pytest
from httpx import AsyncClient
from fastapi.testclient import TestClient

@pytest.mark.asyncio
async def test_create_user_success():
    """Test successful user creation."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/api/v1/users", json={
            "name": "Test User",
            "email": "test@example.com"
        })
    
    assert response.status_code == 201
    data = response.json()
    assert data["data"]["name"] == "Test User"
    assert data["data"]["email"] == "test@example.com"

@pytest.mark.asyncio
async def test_create_user_duplicate_email():
    """Test user creation with duplicate email."""
    # Create first user
    await create_test_user("test@example.com")
    
    # Try to create duplicate
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/api/v1/users", json={
            "name": "Another User",
            "email": "test@example.com"
        })
    
    assert response.status_code == 409
    assert "already exists" in response.json()["error"]["message"]
```

## Performance Guidelines

### Response Time Targets
- **Simple queries:** < 100ms
- **Complex analysis:** < 5s (with progress updates)
- **File uploads:** < 30s for typical bag files
- **Background jobs:** Immediate response with job ID

### Optimization Strategies
- Use database indexes for frequent queries
- Implement Redis caching for expensive operations
- Use background tasks for long-running processes
- Paginate large result sets
- Compress large responses when appropriate