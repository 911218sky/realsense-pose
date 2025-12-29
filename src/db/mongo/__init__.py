"""
MongoDB (Motor + Beanie) integration.

This subpackage holds:
- client/connection init
- document models
- small db utilities

Top-level `db` keeps backward-compatible re-exports for existing imports.
"""

from .client import DB_NAME, MONGO_DB, MONGO_URI, get_db

__all__ = ["get_db", "MONGO_URI", "MONGO_DB", "DB_NAME"]