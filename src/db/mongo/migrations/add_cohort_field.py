"""
Migration: Add cohort field to UserProfile

This migration adds the 'cohort' field to existing UserProfile documents,
setting the default value to ['正常人'] for all users without a cohort.
Also handles migration from string cohort to list cohort for existing data.

Date: 2026-01-06
"""

from typing import Dict

from db.mongo.models import UserProfile
from logger import setup_logger

logger = setup_logger(__name__)


async def migrate() -> Dict[str, int]:
    """
    Add 'cohort' field to existing UserProfile documents.

    - Sets cohort=['正常人'] for documents missing the cohort field
    - Sets cohort=['正常人'] for documents with empty array cohort
    - Sets cohort=['正常人'] for documents with null cohort
    - Converts string cohort to list for documents with old format (e.g., "中風" -> ["中風"])
    
    This ensures all documents have a consistent List[str] format for the cohort field.

    Returns:
        Dict with migration statistics:
        - updated: Number of documents updated
        - failed: Number of documents that failed to update
        - total: Total number of documents that needed migration
    """
    try:
        # Step 1: Count total documents
        total = await UserProfile.count()
        logger.info(f"  Total UserProfile documents: {total}")

        # Step 2: Find documents that need migration
        # Case 1: Missing cohort field entirely
        missing_cohort = await UserProfile.find(
            {"cohort": {"$exists": False}}
        ).count()
        logger.info(f"  Documents missing cohort field: {missing_cohort}")

        # Case 2: cohort is null or empty array
        empty_cohort = await UserProfile.find(
            {"cohort": {"$in": [None, []]}}
        ).count()
        logger.info(f"  Documents with null/empty cohort: {empty_cohort}")

        # Case 3: cohort is a string (old format, needs conversion to list)
        string_cohort = await UserProfile.find(
            {"cohort": {"$type": "string"}}
        ).count()
        logger.info(f"  Documents with string cohort (needs conversion): {string_cohort}")

        total_needing_migration = missing_cohort + empty_cohort + string_cohort

        if total_needing_migration == 0:
            logger.info("  ✅ All UserProfile documents already have correct cohort format")
            return {"updated": 0, "failed": 0, "total": 0}

        # Step 3: Update documents
        updated = 0
        failed = 0

        # Handle missing cohort field
        if missing_cohort > 0:
            cursor = UserProfile.find({"cohort": {"$exists": False}})
            async for doc in cursor:
                try:
                    doc.cohort = ["正常人"]
                    await doc.save()
                    updated += 1

                    if updated % 100 == 0:
                        logger.info(f"  Progress: {updated}/{total_needing_migration} documents updated")

                except Exception as e:
                    logger.error(f"  Failed to update document {doc.id}: {e}")
                    failed += 1

        # Handle null or empty array cohort
        if empty_cohort > 0:
            cursor = UserProfile.find({"cohort": {"$in": [None, []]}})
            async for doc in cursor:
                try:
                    doc.cohort = ["正常人"]
                    await doc.save()
                    updated += 1

                    if updated % 100 == 0:
                        logger.info(f"  Progress: {updated}/{total_needing_migration} documents updated")

                except Exception as e:
                    logger.error(f"  Failed to update document {doc.id}: {e}")
                    failed += 1

        # Handle string cohort -> list conversion
        if string_cohort > 0:
            cursor = UserProfile.find({"cohort": {"$type": "string"}})
            async for doc in cursor:
                try:
                    # Convert string to list
                    old_cohort = doc.cohort
                    if isinstance(old_cohort, str):
                        doc.cohort = [old_cohort] if old_cohort else ["正常人"]
                    await doc.save()
                    updated += 1

                    if updated % 100 == 0:
                        logger.info(f"  Progress: {updated}/{total_needing_migration} documents updated")

                except Exception as e:
                    logger.error(f"  Failed to update document {doc.id}: {e}")
                    failed += 1

        logger.info(f"  ✅ Migration complete: {updated} updated, {failed} failed")
        return {"updated": updated, "failed": failed, "total": total_needing_migration}

    except Exception as e:
        logger.error(f"  Migration failed: {e}")
        return {"error": str(e)}

