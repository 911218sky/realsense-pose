# Database Migrations

This directory contains all database migration modules. Each migration is in a separate file for better organization and maintainability.

## Structure

```
migrations/
├── __init__.py           # Package initialization
├── _template.py          # Template for creating new migrations
├── bag_filename.py       # Migration: Add bag_filename field
└── README.md            # This file
```

## How to Create a New Migration

### 1. Copy the Template

```bash
cp _template.py your_migration_name.py
```

### 2. Implement the Migration

Edit the new file and implement the `migrate()` function:

```python
async def migrate() -> Dict[str, int]:
    """
    Your migration logic here.
    
    Returns:
        Dict with keys: updated, failed, total
        Or: Dict with key: error (if migration failed)
    """
    # Your implementation
    pass
```

### 3. Register the Migration

Edit `../migration_runner.py` and add your migration to the list:

```python
async def run_all_migrations() -> bool:
    from db.mongo.migrations import bag_filename
    from db.mongo.migrations import your_migration_name  # Add this
    
    migrations = [
        ("bag_filename", bag_filename.migrate),
        ("your_migration_name", your_migration_name.migrate),  # Add this
    ]
    
    runner = MigrationRunner()
    return await runner.run_all_migrations(migrations)
```

### 4. Test the Migration

```bash
# Local
python scripts/fix_database.py

# Docker
docker exec realsense-pose-api python scripts/fix_database.py
```

## Migration Guidelines

### Best Practices

1. **Idempotent**: Migrations should be safe to run multiple times
2. **Atomic**: Each migration should handle one specific change
3. **Documented**: Include clear docstrings explaining what the migration does
4. **Error Handling**: Catch and log errors, return proper error dict
5. **Progress Logging**: Log progress for long-running migrations

### Return Format

All migrations must return a dict with one of these formats:

**Success:**
```python
{
    "updated": 10,   # Number of documents updated
    "failed": 0,     # Number of documents that failed
    "total": 10      # Total documents that needed migration
}
```

**Error:**
```python
{
    "error": "Error message here"
}
```

### Example Migration

```python
"""
Migration: Add default role to users

This migration adds a default 'user' role to all UserProfile documents
that don't have a role field.

Date: 2024-12-30
"""

from typing import Dict
from db.mongo.models import UserProfile
from logger import setup_logger

logger = setup_logger(__name__)


async def migrate() -> Dict[str, int]:
    """Add default role to users without one."""
    try:
        # Count documents needing migration
        missing_count = await UserProfile.find(
            {"role": {"$exists": False}}
        ).count()
        
        logger.info(f"  Documents needing migration: {missing_count}")
        
        if missing_count == 0:
            logger.info("  ✅ All documents already have role field")
            return {"updated": 0, "failed": 0, "total": 0}
        
        # Update documents
        updated = 0
        failed = 0
        
        cursor = UserProfile.find({"role": {"$exists": False}})
        
        async for user in cursor:
            try:
                user.role = "user"
                await user.save()
                updated += 1
                
                if updated % 100 == 0:
                    logger.info(f"  Progress: {updated}/{missing_count}")
                    
            except Exception as e:
                logger.error(f"  Failed to update user {user.id}: {e}")
                failed += 1
        
        return {"updated": updated, "failed": failed, "total": missing_count}
        
    except Exception as e:
        logger.error(f"  Migration failed: {e}")
        return {"error": str(e)}
```

## Existing Migrations

### bag_filename (2024-12-30)

Adds `bag_filename` field to `RealsensePoseExtractor` documents by extracting the filename from `bag_path`.

**Status**: Active  
**File**: `bag_filename.py`

## Testing

Always test migrations in a development environment before running in production:

1. Create a backup of production data
2. Restore backup to development database
3. Run migration in development
4. Verify results
5. Run in production during maintenance window

## Troubleshooting

### Migration Failed

Check the logs for specific error messages. Common issues:

- Database connection failed
- Model validation errors
- Missing required fields in source data

### Partial Migration

If a migration partially completes, it's safe to run again. Migrations are designed to be idempotent.

### Rollback

If you need to rollback:

1. Stop the services
2. Restore from backup
3. Fix the migration code
4. Test again

## Related Files

- `../migration_runner.py` - Main migration runner
- `../migrations.py` - Legacy compatibility layer (deprecated)
- `../../models/` - Database models
- `../../../scripts/fix_database.py` - Entry point script
