"""
API auth package.

This package groups authentication-related utilities for easier maintenance.
"""

from .signed_headers import require_signed_headers

__all__ = [
    "require_signed_headers",
]


