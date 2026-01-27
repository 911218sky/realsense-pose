import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional, Tuple, cast

from fastapi import Response

from db import AdminAccount, AdminSession

# Bearer token 存活時間（小時），預設 24h，可用環境變數覆寫
TOKEN_TTL_HOURS = int(os.getenv("ADMIN_TOKEN_TTL_HOURS", "24"))
# 密碼雜湊的 PBKDF2 迭代次數
PBKDF2_ITERATIONS = 120_000
# Cookie 設定（預設 HttpOnly + Lax；secure 可透過環境變數開啟）
ADMIN_TOKEN_COOKIE_NAME = os.getenv("ADMIN_TOKEN_COOKIE_NAME", "admin_token")
# 是否啟用 Secure 屬性（預設關閉，可用環境變數 ADMIN_TOKEN_COOKIE_SECURE 啟用）
ADMIN_TOKEN_COOKIE_SECURE = os.getenv("ADMIN_TOKEN_COOKIE_SECURE", "false").lower() == "true"
# 設定 SameSite 屬性（預設為 'lax'，可用環境變數 ADMIN_TOKEN_COOKIE_SAMESITE 設定）
_samesite_value = os.getenv("ADMIN_TOKEN_COOKIE_SAMESITE", "lax").lower()
ADMIN_TOKEN_COOKIE_SAMESITE = cast(Literal["lax", "strict", "none"], _samesite_value if _samesite_value in ("lax", "strict", "none") else "lax")


def hash_password(password: str, salt_hex: Optional[str] = None) -> Tuple[str, str]:
    """建立或重用 salt，回傳 (salt_hex, hash_hex)。"""
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return salt.hex(), digest.hex()


def verify_password(password: str, salt_hex: str, hash_hex: str) -> bool:
    """驗證密碼是否符合既有雜湊。"""
    salt = bytes.fromhex(salt_hex)
    expected = bytes.fromhex(hash_hex)
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return hmac.compare_digest(expected, candidate)


def token_hash(token: str) -> str:
    """Session token 只儲存雜湊，避免明文洩漏。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def set_auth_cookie(response: Response, token: str, expires_at: datetime) -> None:
    """在回應上設置 HttpOnly cookie，方便前端直接帶 cookie 呼叫。"""
    max_age = max(0, int((expires_at - datetime.now()).total_seconds()))
    # Starlette 需要 UTC-aware datetime 才能用 usegmt=True
    expires_dt = expires_at
    if expires_dt.tzinfo is None or expires_dt.utcoffset() is None:
        # 將 naive datetime 轉成 UTC aware，時間點保持不變的 timestamp
        expires_dt = datetime.fromtimestamp(expires_at.timestamp(), tz=timezone.utc)
    else:
        expires_dt = expires_dt.astimezone(timezone.utc)
    response.set_cookie(
        key=ADMIN_TOKEN_COOKIE_NAME,
        value=token,
        max_age=max_age,
        expires=expires_dt,
        httponly=True,
        secure=ADMIN_TOKEN_COOKIE_SECURE,
        samesite=ADMIN_TOKEN_COOKIE_SAMESITE,
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    """刪除認證 cookie（瀏覽器側移除）。"""
    response.delete_cookie(
        key=ADMIN_TOKEN_COOKIE_NAME,
        path="/",
        samesite=ADMIN_TOKEN_COOKIE_SAMESITE,
        secure=ADMIN_TOKEN_COOKIE_SECURE,
    )


async def issue_session(admin: AdminAccount) -> tuple[str, AdminSession]:
    """簽發新的 session token 並存雜湊。"""
    token = secrets.token_urlsafe(32)
    now = datetime.now()
    expires_at = now + timedelta(hours=TOKEN_TTL_HOURS)
    session = AdminSession(
        admin_code=admin.admin_code,
        token_hash=token_hash(token),
        expires_at=expires_at,
        last_used_at=now,
        created_at=now,
        revoked_at=None,
    )
    await session.insert()
    return token, session


async def get_active_session(token: str) -> Optional[AdminSession]:
    """依 token 查詢有效 session（未撤銷且未過期）。"""
    token_h = token_hash(token)
    return await get_active_session_by_token_hash(token_h)


async def get_active_session_by_token_hash(token_h: str) -> Optional[AdminSession]:
    """依 token_hash 查詢有效 session（未撤銷且未過期）。"""
    now = datetime.now()
    session: Optional[AdminSession] = await AdminSession.find_one(
        AdminSession.token_hash == token_h,
        AdminSession.revoked_at == None,
        AdminSession.expires_at > now,
    )
    return session

__all__ = [
    "TOKEN_TTL_HOURS",
    "PBKDF2_ITERATIONS",
    "ADMIN_TOKEN_COOKIE_NAME",
    "ADMIN_TOKEN_COOKIE_SECURE",
    "ADMIN_TOKEN_COOKIE_SAMESITE",
    "hash_password",
    "verify_password",
    "token_hash",
    "set_auth_cookie",
    "clear_auth_cookie",
    "issue_session",
    "get_active_session",
    "get_active_session_by_token_hash",
]