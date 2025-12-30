"""
Database migration runner.

This module provides the main entry point for running database migrations.
All migration logic is organized in separate migration modules.
"""

import asyncio
import os
import sys
from typing import Callable, Dict, List, Tuple

from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

from db.mongo.models import RealsensePoseExtractor
from logger import setup_logger

logger = setup_logger(__name__)


class MigrationRunner:
    """Main migration runner that executes all registered migrations."""

    def __init__(self):
        self.client = None
        self.database = None
        self.stats = {
            "total_migrations": 0,
            "successful_migrations": 0,
            "failed_migrations": 0,
            "total_documents_updated": 0,
        }

    async def connect(self):
        """Initialize MongoDB connection."""
        # Get MongoDB configuration from environment
        mongo_host = os.getenv("MONGO_HOST", "localhost")
        mongo_port = os.getenv("MONGO_PORT", "27017")
        mongo_user = os.getenv("MONGO_USER", "root")
        mongo_password = os.getenv("MONGO_ROOT_PASSWORD", "4I0rsokkcCICZNMx")
        mongo_db = os.getenv("MONGO_DB", "nycu_rehab")

        # Build MongoDB URI
        # In Docker, use service name; locally use localhost
        if os.getenv("IS_PROD") == "1" or os.path.exists("/.dockerenv"):
            # Running in Docker
            mongo_uri = f"mongodb://{mongo_user}:{mongo_password}@mongo:27017/admin"
        else:
            # Running locally
            mongo_uri = f"mongodb://{mongo_user}:{mongo_password}@{mongo_host}:{mongo_port}/admin"

        logger.info(f"Connecting to MongoDB: {mongo_db}")
        self.client = AsyncIOMotorClient(mongo_uri)
        self.database = self.client[mongo_db]

        # Initialize Beanie
        await init_beanie(database=self.database, document_models=[RealsensePoseExtractor])

        logger.info("✅ Connected to MongoDB successfully")

    async def disconnect(self):
        """Close MongoDB connection."""
        if self.client:
            self.client.close()
            logger.info("Disconnected from MongoDB")

    async def run_migration(
        self, migration_name: str, migration_func: Callable
    ) -> Dict[str, any]:
        """
        Run a single migration.

        Args:
            migration_name: Name of the migration
            migration_func: Async function that performs the migration

        Returns:
            Dict with migration results
        """
        logger.info(f"Running migration: {migration_name}")

        try:
            result = await migration_func()

            if "error" in result:
                self.stats["failed_migrations"] += 1
                logger.error(f"  ❌ Migration '{migration_name}' failed: {result['error']}")
            else:
                self.stats["successful_migrations"] += 1
                self.stats["total_documents_updated"] += result.get("updated", 0)
                logger.info(
                    f"  ✅ Migration '{migration_name}' completed: "
                    f"{result.get('updated', 0)} updated, {result.get('failed', 0)} failed"
                )

            return result

        except Exception as e:
            self.stats["failed_migrations"] += 1
            logger.error(f"  ❌ Migration '{migration_name}' crashed: {e}")
            return {"error": str(e)}

    async def run_all_migrations(self, migrations: List[Tuple[str, Callable]]):
        """
        Run all migrations in order.

        Args:
            migrations: List of (migration_name, migration_func) tuples
        """
        logger.info("=" * 60)
        logger.info("Starting Database Migrations")
        logger.info("=" * 60)

        await self.connect()

        for migration_name, migration_func in migrations:
            self.stats["total_migrations"] += 1
            await self.run_migration(migration_name, migration_func)

        await self.disconnect()

        # Print summary
        logger.info("=" * 60)
        logger.info("Migration Summary")
        logger.info("=" * 60)
        logger.info(f"Total migrations: {self.stats['total_migrations']}")
        logger.info(f"Successful: {self.stats['successful_migrations']}")
        logger.info(f"Failed: {self.stats['failed_migrations']}")
        logger.info(f"Total documents updated: {self.stats['total_documents_updated']}")
        logger.info("=" * 60)

        if self.stats["failed_migrations"] > 0:
            logger.warning("⚠️  Some migrations failed. Please check the logs above.")
            return False
        else:
            logger.info("✅ All migrations completed successfully!")
            return True


async def run_all_migrations() -> bool:
    """
    Main entry point for running all migrations.

    Returns:
        True if all migrations succeeded, False otherwise
    """
    # Import migration modules
    from db.mongo.migrations import bag_filename as bag_filename_migration
    from db.mongo.migrations import fix_duplicate_bag_bindings as fix_bindings_migration

    # Register all migrations here (in order)
    migrations = [
        ("bag_filename", bag_filename_migration.migrate),
        ("fix_duplicate_bag_bindings", fix_bindings_migration.migrate),
        # Add more migrations here as needed:
        # ("new_field", new_field_migration.migrate),
    ]

    runner = MigrationRunner()
    return await runner.run_all_migrations(migrations)


if __name__ == "__main__":
    import sys
    success = asyncio.run(run_all_migrations())
    sys.exit(0 if success else 1)
