import os
from datetime import datetime
from typing import Optional, Sequence, Tuple

from redis import asyncio as aioredis

from fastapi import Header, HTTPException, Request, status

from db import AdminAccount

from .auth_utils import (
    ADMIN_TOKEN_COOKIE_NAME,
    get_active_session_by_token_hash,
    token_hash,
)

# 管理員驗證快取（使用 Redis；若 Redis 不可用則不快取）
#
# 目的：
# - 避免每個 API request 都查詢 MongoDB（AdminSession / AdminAccount）
#
# 安全性策略：
# - 快取 TTL 必須很短（預設 5 秒）
# - 登出 / 撤銷 session / 變更密碼 / 刪除帳號時，必須主動失效（刪除對應 Redis keys）
#
# Redis key 設計：
# - token_key: auth:admin:token:<token_hash> -> "admin_code|expires_ts"
# - admin_set: auth:admin:tokens:<admin_code> -> set(token_hash, ...)
#
# 注意：
# - 這個快取只作為「性能優化」；Redis 缺失/故障時會退回走 DB 驗證（fail open for cache）
#

# 管理員驗證快取 TTL（預設 15 秒）
ADMIN_AUTH_CACHE_TTL_SECONDS = float(os.getenv("ADMIN_AUTH_CACHE_TTL_SECONDS", "15"))
# 管理員驗證負快取 TTL（預設 2 秒）
ADMIN_AUTH_NEGATIVE_CACHE_TTL_SECONDS = float(os.getenv("ADMIN_AUTH_NEGATIVE_CACHE_TTL_SECONDS", "2"))
# 負快取值（預設 "invalid"）
_CACHE_INVALID_VALUE = "invalid"

def _redis_token_key(token_h: str) -> str:
    return f"auth:admin:token:{token_h}"


def _redis_admin_tokens_key(admin_code: str) -> str:
    return f"auth:admin:tokens:{admin_code}"


def _encode_cache_value(admin_code: str, expires_at: datetime) -> str:
    # 用精簡格式降低 Redis payload。
    # 使用 POSIX timestamp 避免時區序列化差異。
    # 使用 | 分割 admin_code 和 expires_at
    return f"{admin_code}|{expires_at.timestamp():.3f}"

def _decode_cache_value(value: str) -> Optional[Tuple[str, datetime]]:
    try:
        # 分割 admin_code 和 expires_at
        admin_code, ts = value.split("|", 1)
        admin_code = admin_code.strip()
        expires_ts = float(ts)
        if not admin_code:
            return None
        return admin_code, datetime.fromtimestamp(expires_ts)
    except Exception:
        return None


def _get_redis_from_request(request: Request) -> Optional[aioredis.Redis]:
    return getattr(request.app.state, "redis", None)

async def invalidate_admin_auth_cache_by_token(request: Request, token: str) -> None:
    """依 raw bearer token 失效快取（Redis best-effort）。"""
    token_h = token_hash(token)
    redis = _get_redis_from_request(request)
    if redis is not None:
        try:
            # Best-effort delete; do not block logout if Redis is momentarily unavailable.
            await redis.delete(_redis_token_key(token_h))
        except Exception:
            pass


async def invalidate_admin_auth_cache_by_admin_code(request: Request, admin_code: str) -> None:
    """依 admin_code 失效所有快取 token（Redis set fan-out, best-effort）。"""
    redis = _get_redis_from_request(request)
    if redis is None:
        return

    set_key = _redis_admin_tokens_key(admin_code)
    try:
        token_hashes: Sequence[bytes] = await redis.smembers(set_key)
        if token_hashes:
            keys = [_redis_token_key(th.decode("utf-8")) for th in token_hashes]
            # Delete token keys in bulk
            await redis.delete(*keys)
        await redis.delete(set_key)
    except Exception:
        # Best-effort; don't fail requests on cache invalidation issues.
        return


async def _get_cached_admin_code_by_token_hash(
    request: Request,
    token_h: str,
) -> Optional[Tuple[str, datetime]]:
    """
    從 Redis 快取取得 (admin_code, expires_at)。

    - 快取命中且未過期：回傳 (admin_code, expires_at)
    - 快取未命中 / Redis 不可用 / 解析失敗：回傳 None（呼叫端會改走 DB）
    """
    if ADMIN_AUTH_CACHE_TTL_SECONDS <= 0:
        return None

    redis = _get_redis_from_request(request)
    if redis is None:
        return None

    try:
        cached = await redis.get(_redis_token_key(token_h))
    except Exception:
        return None

    if cached is None:
        return None

    cached_str = cached.decode("utf-8") if isinstance(cached, (bytes, bytearray)) else str(cached)
    if cached_str == _CACHE_INVALID_VALUE:
        # 負快取命中：代表近期已判定此 token 無效，可直接拒絕（避免打 DB）
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or expired token")

    decoded = _decode_cache_value(cached_str)
    if not decoded:
        return None

    admin_code, expires_at = decoded
    if expires_at <= datetime.now():
        # Stale entry; best-effort cleanup
        try:
            await redis.delete(_redis_token_key(token_h))
        except Exception:
            pass
        return None

    return admin_code, expires_at


async def _set_cached_admin_code_by_token_hash(request: Request, token_h: str, admin_code: str, expires_at: datetime) -> None:
    """
    寫入 Redis 快取：token -> (admin_code, expires_at)

    TTL 規則：
    - 快取 TTL 取 min(ADMIN_AUTH_CACHE_TTL_SECONDS, session 剩餘存活秒數)
    - 因此快取永遠不會比 session 實際過期時間更久
    """
    if ADMIN_AUTH_CACHE_TTL_SECONDS <= 0:
        return

    redis = _get_redis_from_request(request)
    if redis is None:
        return

    now = datetime.now()
    ttl_session = max(0, int((expires_at - now).total_seconds()))
    ttl_cache = max(0, int(ADMIN_AUTH_CACHE_TTL_SECONDS))
    ttl = min(ttl_session, ttl_cache) if ttl_session else ttl_cache
    if ttl <= 0:
        return

    token_key = _redis_token_key(token_h)
    set_key = _redis_admin_tokens_key(admin_code)
    value = _encode_cache_value(admin_code, expires_at)

    try:
        async with redis.pipeline(transaction=False) as pipe:
            pipe.set(token_key, value, ex=ttl)
            pipe.sadd(set_key, token_h)
            # keep the set around at least as long as any token entry
            pipe.expire(set_key, ttl_session if ttl_session > 0 else ttl)
            await pipe.execute()
    except Exception:
        return


async def _set_negative_cache_by_token_hash(request: Request, token_h: str) -> None:
    """對無效 token 做短暫負快取，降低大量無效/過期 token 對 DB 的壓力。"""
    if ADMIN_AUTH_CACHE_TTL_SECONDS <= 0:
        return
    redis = _get_redis_from_request(request)
    if redis is None:
        return
    ttl = max(1, int(ADMIN_AUTH_NEGATIVE_CACHE_TTL_SECONDS))
    try:
        await redis.set(_redis_token_key(token_h), _CACHE_INVALID_VALUE, ex=ttl)
    except Exception:
        return


async def require_admin_account(
    request: Request,
    authorization: Optional[str] = Header(None),
) -> AdminAccount:
    """
    提供給需要「拿到 AdminAccount」的路由使用的依賴。

    - 支援 Authorization: Bearer <token>
    - 若無 header，則回退使用 cookie (ADMIN_TOKEN_COOKIE_NAME)
    """
    token: Optional[str] = None

    # 1) Authorization header (Bearer)
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()

    # 2) Cookie fallback
    if not token:
        token = request.cookies.get(ADMIN_TOKEN_COOKIE_NAME)

    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")

    token_h = token_hash(token)

    # 快取命中：跳過 session 查詢與 session.last_used 寫入（但仍需查 AdminAccount）
    cached = await _get_cached_admin_code_by_token_hash(request, token_h)
    if cached:
        admin_code, _expires_at = cached
        admin = await AdminAccount.find_one(AdminAccount.admin_code == admin_code)
        if admin:
            return admin

    session = await get_active_session_by_token_hash(token_h)
    if not session:
        await _set_negative_cache_by_token_hash(request, token_h)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or expired token")

    admin = await AdminAccount.find_one(AdminAccount.admin_code == session.admin_code)
    if not admin:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="admin not found")

    # 注意：這裡仍會更新 last_used_at（行為與原本一致）
    session.last_used_at = datetime.now()
    await session.save()
    await _set_cached_admin_code_by_token_hash(request, token_h, session.admin_code, session.expires_at)
    return admin

async def require_admin(
    request: Request,
    authorization: Optional[str] = Header(None),
) -> None:
    """
    驗證管理員 token 是否有效（不查詢 AdminAccount）。

    適用情境：
    - 作為 router-level dependency，只需要「已登入」即可，不需要拿到 AdminAccount doc。
    - 搭配 Redis cache 可把每次請求的 DB hit 降到接近 0（cache miss 才查 DB）。
    """
    token: Optional[str] = None

    # 1) Authorization header (Bearer)
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
    # 2) Cookie fallback
    if not token:
        token = request.cookies.get(ADMIN_TOKEN_COOKIE_NAME)
        
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")

    token_h = token_hash(token)

    # router-level 驗證：快取命中則直接放行
    cached = await _get_cached_admin_code_by_token_hash(request, token_h)
    # 只要沒丟例外（負快取）就代表快取命中有效 or 快取 miss
    if cached:
        return None

    session = await get_active_session_by_token_hash(token_h)
    if not session:
        await _set_negative_cache_by_token_hash(request, token_h)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or expired token")

    # NOTE: 不在這裡查 AdminAccount（router-level auth-only）
    await _set_cached_admin_code_by_token_hash(request, token_h, session.admin_code, session.expires_at)
    return None

__all__ = [
    "ADMIN_AUTH_CACHE_TTL_SECONDS",
    "ADMIN_AUTH_NEGATIVE_CACHE_TTL_SECONDS",
    "require_admin",
    "require_admin_account",
    "invalidate_admin_auth_cache_by_token",
    "invalidate_admin_auth_cache_by_admin_code",
]