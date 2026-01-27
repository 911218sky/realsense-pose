"""
Migration: Fix duplicate bag_filename bindings to users.

This migration ensures that each bag_filename is only bound to one user.
If multiple sessions with the same bag_filename are bound to different users,
it will keep the oldest binding and unlink the others.

Date: 2024-12-30
"""

from collections import defaultdict
from typing import Dict, List

from db.mongo.models import RealsensePoseExtractor
from logger import setup_logger

logger = setup_logger(__name__)


async def migrate() -> Dict[str, int]:
    """
    Fix duplicate bag_filename bindings.

    Ensures that each bag_filename is only bound to one user_code.
    If duplicates are found, keeps the oldest binding and unlinks others.

    Returns:
        Dict with migration statistics:
        - checked: Number of unique bag_filenames checked
        - conflicts: Number of bag_filenames with conflicting bindings
        - unlinked: Number of sessions that were unlinked
        - total: Total sessions processed
    """
    try:
        # Find all sessions that are bound to users
        bound_sessions = await RealsensePoseExtractor.find(
            RealsensePoseExtractor.user_code != None
        ).to_list()

        total = len(bound_sessions)
        logger.info(f"  Total bound sessions: {total}")

        if total == 0:
            logger.info("  ✅ No bound sessions found")
            return {"checked": 0, "conflicts": 0, "unlinked": 0, "total": 0}

        # Group sessions by bag_filename
        bag_to_sessions: Dict[str, List[RealsensePoseExtractor]] = defaultdict(list)
        
        for session in bound_sessions:
            if session.bag_filename:
                bag_to_sessions[session.bag_filename].append(session)
            else:
                logger.warning(
                    f"  Session {session.session_name} is bound but has no bag_filename"
                )

        checked = len(bag_to_sessions)
        logger.info(f"  Unique bag_filenames checked: {checked}")

        # Find conflicts (same bag_filename bound to multiple users)
        conflicts = 0
        unlinked = 0

        for bag_filename, sessions in bag_to_sessions.items():
            # Get unique user_codes for this bag
            user_codes = set(s.user_code for s in sessions if s.user_code)

            if len(user_codes) > 1:
                conflicts += 1
                logger.warning(
                    f"  Conflict found: bag_filename='{bag_filename}' "
                    f"is bound to {len(user_codes)} different users: {user_codes}"
                )

                # Sort sessions by created_at (keep oldest binding)
                sessions_sorted = sorted(sessions, key=lambda s: s.created_at)
                keep_session = sessions_sorted[0]
                unlink_sessions = sessions_sorted[1:]

                logger.info(
                    f"    Keeping: session={keep_session.session_name}, "
                    f"user={keep_session.user_code}, "
                    f"created={keep_session.created_at}"
                )

                # Unlink the others
                for session in unlink_sessions:
                    logger.info(
                        f"    Unlinking: session={session.session_name}, "
                        f"user={session.user_code}"
                    )
                    session.user_code = None
                    await session.save()
                    unlinked += 1

        if conflicts == 0:
            logger.info("  ✅ No conflicts found - all bag_filenames have unique bindings")
        else:
            logger.info(
                f"  ✅ Fixed {conflicts} conflicts by unlinking {unlinked} sessions"
            )

        return {
            "checked": checked,
            "conflicts": conflicts,
            "unlinked": unlinked,
            "total": total,
        }

    except Exception as e:
        logger.error(f"  Migration failed: {e}")
        return {"error": str(e)}
