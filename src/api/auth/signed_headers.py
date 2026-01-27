"""HMAC 簽章驗證。"""

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from fastapi import HTTPException, Request, status
from redis import asyncio as aioredis

from api.utils.env import env_bool

VERSION = "v1"


def _parse_client_secrets(raw: Optional[str]) -> Dict[str, str]:
    """解析 AUTH_CLIENT_SECRETS 環境變數。

    支援 JSON 或 CSV 格式：
    - JSON: {"flutter":"secret","deviceA":"secret2"}
    - CSV: flutter=secret,deviceA=secret2
    """
    raw = (raw or "").strip()
    if not raw:
        return {}

    if raw.startswith("{"):
        try:
            obj = json.loads(raw)
        except Exception as e:
            raise ValueError(f"AUTH_CLIENT_SECRETS invalid JSON: {e}") from e
        if not isinstance(obj, dict):
            raise ValueError("AUTH_CLIENT_SECRETS JSON must be an object")
        result: Dict[str, str] = {}
        for k, v in obj.items():
            if not isinstance(k, str) or not isinstance(v, str):
                raise ValueError("AUTH_CLIENT_SECRETS JSON must be {string: string}")
            if k.strip() and v:
                result[k.strip()] = v
        return result

    out: Dict[str, str] = {}
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    for part in parts:
        if "=" not in part:
            raise ValueError("AUTH_CLIENT_SECRETS CSV must be like client=secret,client2=secret2")
        k, v = part.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k and v:
            out[k] = v
    return out


@dataclass(frozen=True)
class AuthSettings:
    """認證設定。"""
    enabled: bool
    client_secrets: Dict[str, str]
    client_secret_bytes: Dict[str, bytes]
    nonce_ttl_seconds: int
    max_body_bytes: int
    exempt_paths: Tuple[str, ...]
    timestamp_tolerance_seconds: int


def _load_settings() -> AuthSettings:
    """載入認證設定。"""
    enabled = env_bool("AUTH_ENABLED", True)
    client_secrets = _parse_client_secrets(os.getenv("AUTH_CLIENT_SECRETS", ""))
    client_secret_bytes = {k: v.encode("utf-8") for k, v in client_secrets.items()}
    nonce_ttl_seconds = int(os.getenv("AUTH_NONCE_TTL_SECONDS", "60"))
    max_body_bytes = int(os.getenv("AUTH_MAX_BODY_BYTES", "0") or "0")
    exempt_paths_raw = (os.getenv("AUTH_EXEMPT_PATHS", "") or "").strip()
    exempt_paths = tuple(p.strip() for p in exempt_paths_raw.split(",") if p.strip())
    timestamp_tolerance_seconds = int(
        os.getenv("AUTH_TIMESTAMP_TOLERANCE_SECONDS", "30")
    )
    return AuthSettings(
        enabled=enabled,
        client_secrets=client_secrets,
        client_secret_bytes=client_secret_bytes,
        nonce_ttl_seconds=max(1, nonce_ttl_seconds),
        max_body_bytes=max(0, max_body_bytes),
        exempt_paths=exempt_paths,
        timestamp_tolerance_seconds=max(0, timestamp_tolerance_seconds),
    )


_SETTINGS = _load_settings()


def _canonical_string(
    *,
    method: str,
    path: str,
    query: str,
    nonce: str,
    timestamp: str,
    body_sha256: str,
    version: str = VERSION,
) -> str:
    """生成正規化字串，客戶端需 100% 一致才能驗簽成功。"""
    path_with_query = path if not query else f"{path}?{query}"
    return "\n".join([version, method.upper(), path_with_query, nonce, timestamp, body_sha256])


def _sha256_hex(data: bytes) -> str:
    """計算 SHA256 hex。"""
    return hashlib.sha256(data).hexdigest()


def _hmac_sha256_digest(secret: bytes, msg: str) -> bytes:
    """計算 HMAC-SHA256。"""
    mac = hmac.new(secret, msg.encode("utf-8"), hashlib.sha256)
    return mac.digest()


def _unauthorized(detail: str) -> HTTPException:
    """回傳 401 錯誤。"""
    from logger import setup_logger
    logger = setup_logger("api.auth")
    logger.warning(f"Auth failed: {detail}")
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


def _check_timestamp(timestamp_str: str) -> None:
    """驗證時間戳是否在容許範圍內。"""
    if _SETTINGS.timestamp_tolerance_seconds <= 0:
        # 設為 0 或負數表示關閉時間戳檢查
        return

    try:
        client_ts = float(timestamp_str)
    except (ValueError, TypeError):
        raise _unauthorized("invalid timestamp format")

    server_ts = time.time()
    diff = abs(server_ts - client_ts)

    if diff > _SETTINGS.timestamp_tolerance_seconds:
        raise _unauthorized("timestamp expired or too far in future")


async def _check_and_store_nonce(request: Request, client_id: str, nonce: str) -> None:
    """防重放：確保 (client_id, nonce) 在 TTL 內只能使用一次。"""
    key = f"auth:nonce:{client_id}:{nonce}"

    redis: Optional[aioredis.Redis] = getattr(request.app.state, "redis", None)
    if redis is None:
        raise _unauthorized("auth nonce check failed (redis missing)")

    try:
        ok = await redis.set(key, "1", ex=_SETTINGS.nonce_ttl_seconds, nx=True)
    except Exception:
        # Redis 故障時採 fail closed
        raise _unauthorized("auth nonce check failed")
    if not ok:
        raise _unauthorized("replay detected (nonce already used)")
    return


async def require_signed_headers(request: Request) -> None:
    """FastAPI dependency：驗證 HMAC 簽章。

    必要 headers：
    - X-Client-Id
    - X-Nonce (建議 UUIDv4)
    - X-Timestamp (Unix 秒)
    - X-Signature (hex HMAC-SHA256)
    - X-Signature-Version (選用)
    """
    if not _SETTINGS.enabled:
        return

    # 放行 CORS preflight
    if request.method.upper() == "OPTIONS":
        return

    path = request.url.path
    for p in _SETTINGS.exempt_paths:
        if p and path.startswith(p):
            return

    client_id = (request.headers.get("x-client-id") or "").strip()
    nonce = (request.headers.get("x-nonce") or "").strip()
    timestamp = (request.headers.get("x-timestamp") or "").strip()
    signature = (request.headers.get("x-signature") or "").strip()
    version = (request.headers.get("x-signature-version") or VERSION).strip()

    if not client_id or not nonce or not timestamp or not signature:
        raise _unauthorized("missing auth headers")

    _check_timestamp(timestamp)

    secret_bytes = _SETTINGS.client_secret_bytes.get(client_id)
    if not secret_bytes:
        raise _unauthorized("unknown client_id")

    # 先擋重放再做較重的工作
    await _check_and_store_nonce(request, client_id, nonce)

    # 計算 body hash：若 middleware 解壓了 gzip，raw bytes 在 request.state.raw_body
    raw_body: Optional[bytes] = getattr(request.state, "raw_body", None)
    body_for_sig = raw_body

    if body_for_sig is None:
        body_for_sig = await request.body()

    if _SETTINGS.max_body_bytes and len(body_for_sig) > _SETTINGS.max_body_bytes:
        raise _unauthorized("request body too large")

    body_sha256 = _sha256_hex(body_for_sig)

    msg = _canonical_string(
        method=request.method,
        path=request.url.path,
        query=request.url.query,
        nonce=nonce,
        timestamp=timestamp,
        body_sha256=body_sha256,
        version=version,
    )
    expected = _hmac_sha256_digest(secret_bytes, msg)

    sig_ok = False
    try:
        sig_bytes = bytes.fromhex(signature)
        sig_ok = hmac.compare_digest(sig_bytes, expected)
    except Exception:
        sig_ok = False

    # 若有 gzip middleware 且 raw 驗簽失敗，改用解壓後 bytes 再試一次
    if not sig_ok and raw_body is not None:
        try:
            body_plain = await request.body()
            if _SETTINGS.max_body_bytes and len(body_plain) > _SETTINGS.max_body_bytes:
                raise _unauthorized("request body too large")
            body_sha256_plain = _sha256_hex(body_plain)
            msg_plain = _canonical_string(
                method=request.method,
                path=request.url.path,
                query=request.url.query,
                nonce=nonce,
                timestamp=timestamp,
                body_sha256=body_sha256_plain,
                version=version,
            )
            expected_plain = _hmac_sha256_digest(secret_bytes, msg_plain)
            sig_bytes = bytes.fromhex(signature)
            sig_ok = hmac.compare_digest(sig_bytes, expected_plain)
        except HTTPException:
            raise
        except Exception:
            sig_ok = False

    if not sig_ok:
        raise _unauthorized("invalid signature")

    # 如有需要，將身份資訊提供給後續 handlers
    request.state.client_id = client_id