"""
Backward-compat module.

Auth signed-headers verification was moved into `src/api/auth/` to keep auth-related
logic in a dedicated folder for easier maintenance.
"""

from .auth.signed_headers import require_signed_headers

__all__ = [
    "require_signed_headers",
]


