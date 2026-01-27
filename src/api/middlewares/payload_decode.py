"""Payload 解碼 middleware，處理 gzip 壓縮的請求 body。"""

import gzip
import io
from typing import Iterable, List, Tuple

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

Header = Tuple[bytes, bytes]


def _remove_headers(headers: Iterable[Header], names: set[bytes]) -> List[Header]:
    """移除指定的 headers。"""
    names_l = {n.lower() for n in names}
    out: List[Header] = []
    for k, v in headers:
        if k.lower() in names_l:
            continue
        out.append((k, v))
    return out


def _gunzip_limited(data: bytes, max_bytes: int) -> bytes:
    """解壓 gzip，帶上限避免 gzip bomb。
    
    max_bytes <= 0 表示不限制。
    """
    if max_bytes <= 0:
        return gzip.decompress(data)

    with gzip.GzipFile(fileobj=io.BytesIO(data)) as f:
        out = f.read(max_bytes + 1)
    if len(out) > max_bytes:
        raise ValueError("decompressed too large")
    return out


class PayloadDecodeMiddleware:
    """解碼前端送來的 gzip 壓縮 payload。

    支援 X-Payload-Encoding: gzip 或 Content-Encoding: gzip。
    壓縮前的 raw bytes 會存到 scope['state']['raw_body']，
    request body 會換成解壓後的內容。
    """

    def __init__(self, app: ASGIApp, *, max_decompressed_bytes: int = 0) -> None:
        self.app = app
        self.max_decompressed_bytes = max(0, int(max_decompressed_bytes))

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # 只有偵測到 gzip header 時才做 body 讀取/解壓
        headers_raw: List[Header] = list(scope.get("headers") or [])
        headers = Headers(raw=headers_raw)

        x_enc = (headers.get("x-payload-encoding") or "").strip().lower()
        c_enc = (headers.get("content-encoding") or "").strip().lower()
        is_gzip = (x_enc == "gzip") or ("gzip" in c_enc)

        if not is_gzip:
            await self.app(scope, receive, send)
            return

        # 只讀 body 一次，後面用 receive2 把解壓後 bytes 餵回去
        body = b""
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] != "http.request":
                continue
            body += message.get("body", b"")
            more_body = bool(message.get("more_body", False))

        scope.setdefault("state", {})
        scope["state"]["raw_body"] = body
        scope["state"]["payload_encoding"] = "gzip"

        try:
            decoded = _gunzip_limited(body, self.max_decompressed_bytes)
        except Exception:
            resp = JSONResponse({"detail": "invalid gzip body"}, status_code=400)
            await resp(scope, receive, send)
            return

        # 重寫 headers：移除 encoding 相關提示，恢復 Content-Type
        new_headers = _remove_headers(
            headers_raw,
            {
                b"x-payload-encoding",
                b"x-payload-content-type",
                b"content-encoding",
                b"content-length",
            },
        )

        # 若有 X-Payload-Content-Type，恢復 Content-Type
        payload_ct = headers.get("x-payload-content-type")
        if payload_ct:
            new_headers = _remove_headers(new_headers, {b"content-type"})
            new_headers.append((b"content-type", payload_ct.encode("latin-1")))

        # 更新 Content-Length
        new_headers.append((b"content-length", str(len(decoded)).encode("ascii")))
        scope["headers"] = new_headers

        sent = False

        async def receive2():
            nonlocal sent
            if sent:
                return {"type": "http.request", "body": b"", "more_body": False}
            sent = True
            return {"type": "http.request", "body": decoded, "more_body": False}

        await self.app(scope, receive2, send)