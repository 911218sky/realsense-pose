"""
Migration: Add bag_filename field to RealsensePoseExtractor.

This migration extracts the filename from bag_path for records that don't
have the bag_filename field yet.

Date: 2024-12-30
"""

from pathlib import Path
from typing import Dict

from src.db.mongo.models import RealsensePoseExtractor
from src.logger import setup_logger

logger = setup_logger(__name__)


async def migrate() -> Dict[str, int]:
    """
    Add bag_filename field to all RealsensePoseExtractor documents.

    Extracts filename from bag_path for records that are missing bag_filename.

    Returns:
        Dict with migration statistics:
        - updated: Number of documents updated
        - failed: Number of documents that failed to update
        - total: Total number of documents that needed migration
    """
    try:
        # Find all documents without bag_filename
        total = await RealsensePoseExtractor.count()
        logger.info(f"  Total documents: {total}")

        # Find documents missing bag_filename or with None value
        missing_count = await RealsensePoseExtractor.find(
            {"$or": [{"bag_filename": {"$exists": False}}, {"bag_filename": None}]}
        ).count()

        logger.info(f"  Documents missing bag_filename: {missing_count}")

        if missing_count == 0:
            logger.info("  ✅ All documents already have bag_filename field")
            return {"updated": 0, "failed": 0, "total": 0}

        # Update documents
        updated = 0
        failed = 0

        cursor = RealsensePoseExtractor.find(
            {"$or": [{"bag_filename": {"$exists": False}}, {"bag_filename": None}]}
        )

        async for doc in cursor:
            try:
                # Extract filename from bag_path
                if doc.bag_path:
                    doc.bag_filename = Path(doc.bag_path).name
                    await doc.save()
                    updated += 1

                    if updated % 100 == 0:
                        logger.info(f"  Progress: {updated}/{missing_count} documents updated")
                else:
                    logger.warning(f"  Document {doc.session_name} has no bag_path, skipping")
                    failed += 1

            except Exception as e:
                logger.error(f"  Failed to update document {doc.session_name}: {e}")
                failed += 1

        return {"updated": updated, "failed": failed, "total": missing_count}

    except Exception as e:
        logger.error(f"  Migration failed: {e}")
        return {"error": str(e)}
