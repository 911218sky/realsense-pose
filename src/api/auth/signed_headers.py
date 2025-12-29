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

# 解析環境變數 AUTH_CLIENT_SECRETS
def _parse_client_secrets(raw: Optional[str]) -> Dict[str, str]:
    """
    解析環境變數 AUTH_CLIENT_SECRETS。

    支援格式：
    - JSON: {"flutter":"secret","deviceA":"secret2"}
    - CSV 鍵值對：flutter=secret,deviceA=secret2
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
        out: Dict[str, str] = {}
        for k, v in obj.items():
            if not isinstance(k, str) or not isinstance(v, str):
                raise ValueError("AUTH_CLIENT_SECRETS JSON must be {string: string}")
            if k.strip() and v:
                out[k.strip()] = v
        return out

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
    enabled: bool                  # 是否啟用簽章驗證
    client_secrets: Dict[str, str] # 用戶端ID與對應密鑰字典
    client_secret_bytes: Dict[str, bytes] # 用戶端ID與對應密鑰 (bytes 格式) 字典
    nonce_ttl_seconds: int         # nonce 有效存活（防重放攻擊）秒數
    max_body_bytes: int            # 請求 body 允許最大位元組數
    exempt_paths: Tuple[str, ...]  # 免驗證簽章之路徑列表
    timestamp_tolerance_seconds: int  # 時間戳容許偏差秒數（防爬蟲）

def _load_settings() -> AuthSettings:
    # 是否啟用認證
    enabled = env_bool("AUTH_ENABLED", True)
    # 客戶端密鑰
    client_secrets = _parse_client_secrets(os.getenv("AUTH_CLIENT_SECRETS", ""))
    client_secret_bytes = {k: v.encode("utf-8") for k, v in client_secrets.items()}
    # 非重放 nonce 過期時間多少秒
    nonce_ttl_seconds = int(os.getenv("AUTH_NONCE_TTL_SECONDS", "60"))
    # 限制可簽章的 body 大小（bytes）。0 代表不限制。
    max_body_bytes = int(os.getenv("AUTH_MAX_BODY_BYTES", "0") or "0")
    # 免認證路徑
    exempt_paths_raw = (os.getenv("AUTH_EXEMPT_PATHS", "") or "").strip()
    # 免認證路徑列表
    exempt_paths = tuple(p.strip() for p in exempt_paths_raw.split(",") if p.strip())
    # 時間戳容許偏差（防爬蟲）：0 表示關閉時間戳檢查 (預設 30 秒)
    timestamp_tolerance_seconds = int(
        os.getenv("AUTH_TIMESTAMP_TOLERANCE_SECONDS", "30")
    )
    # 認證設定
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

# 生成正規化字串
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
    # 重要：此規格必須保持穩定並文件化；客戶端需要 100% 一致才能驗簽成功。
    # 使用換行避免字串拼接歧義。
    path_with_query = path if not query else f"{path}?{query}"
    return "\n".join([version, method.upper(), path_with_query, nonce, timestamp, body_sha256])

# 計算 SHA256 雜湊值
def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

# 計算 HMAC-SHA256 簽章
def _hmac_sha256_digest(secret: bytes, msg: str) -> bytes:
    mac = hmac.new(secret, msg.encode("utf-8"), hashlib.sha256)
    return mac.digest()

# 未授權錯誤
def _unauthorized(detail: str) -> HTTPException:
    # 保持 status code 一致，方便客戶端處理
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


# 檢查時間戳是否在允許範圍內
def _check_timestamp(timestamp_str: str) -> None:
    """
    驗證時間戳是否在容許的時間窗口內（防爬蟲）。
    時間戳必須是 Unix 時間戳（秒），可為整數或浮點數字串。
    """
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

# 檢查 nonce 並存入 Redis
async def _check_and_store_nonce(request: Request, client_id: str, nonce: str) -> None:
    """
    防止重放攻擊：確保 (client_id, nonce) 在 TTL 內只能使用一次。
    僅使用 Redis（不使用本機記憶體備援）。
    """
    key = f"auth:nonce:{client_id}:{nonce}"

    redis: Optional[aioredis.Redis] = getattr(request.app.state, "redis", None)
    if redis is None:
        # 不提供本機備援：沒有 Redis 就直接拒絕（fail closed）
        raise _unauthorized("auth nonce check failed (redis missing)")

    try:
        # 設定 nonce 過期時間
        ok = await redis.set(key, "1", ex=_SETTINGS.nonce_ttl_seconds, nx=True)
    except Exception:
        # 若 Redis 存在但故障：採「失敗即拒絕」(fail closed)，因為這是安全機制。
        raise _unauthorized("auth nonce check failed")
    if not ok:
        raise _unauthorized("replay detected (nonce already used)")
    return


async def require_signed_headers(request: Request) -> None:
    """
    FastAPI 相依性 (dependency)：使用請求標頭 (headers) 內的 HMAC 簽章驗證客戶端身份。

    必要 headers：
    - X-Client-Id
    - X-Nonce             (隨機字串；建議 UUIDv4)
    - X-Timestamp         (Unix 時間戳，秒；防爬蟲）
    - X-Signature         (hex HMAC-SHA256)
    - X-Signature-Version (選用；預設 VERSION)
    """
    if not _SETTINGS.enabled:
        return

    # 放行 CORS 預檢（preflight）：瀏覽器在預檢階段不會帶自訂 headers。
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

    # 檢查必要 headers
    if not client_id or not nonce or not timestamp or not signature:
        raise _unauthorized("missing auth headers")

    # 檢查時間戳是否在允許範圍內（防爬蟲）
    _check_timestamp(timestamp)

    # 檢查客戶端密鑰
    secret_bytes = _SETTINGS.client_secret_bytes.get(client_id)
    if not secret_bytes:
        raise _unauthorized("unknown client_id")

    # 在做較重的工作前先擋掉重放
    await _check_and_store_nonce(request, client_id, nonce)

    # 計算 body hash：
    # - 若前面 middleware 解壓了 gzip，會把「壓縮前的 raw bytes」放在 request.state.raw_body
    # - 先用 raw bytes 驗簽（與實際傳輸一致）；若失敗再用解壓後 bytes 嘗試一次（相容不同前端流程）
    raw_body: Optional[bytes] = getattr(request.state, "raw_body", None)
    body_for_sig = raw_body

    if body_for_sig is None:
        # 沒有 middleware 介入時，直接用 request.body()
        body_for_sig = await request.body()

    if _SETTINGS.max_body_bytes and len(body_for_sig) > _SETTINGS.max_body_bytes:
        raise _unauthorized("request body too large")

    body_sha256 = _sha256_hex(body_for_sig)

    # 生成正規化字串
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

    # 驗證簽章（hex）
    sig_ok = False
    try:
        sig_bytes = bytes.fromhex(signature)
        sig_ok = hmac.compare_digest(sig_bytes, expected)
    except Exception:
        sig_ok = False

    # 若有 gzip middleware，且 raw 驗簽失敗，改用「解壓後 bytes」再試一次（相容）
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