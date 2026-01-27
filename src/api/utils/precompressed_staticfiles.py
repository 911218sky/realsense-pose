import mimetypes
from os import stat_result as StatResult
from pathlib import Path
from datetime import datetime, timezone
from email.utils import format_datetime, parsedate_to_datetime

from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

_EXTRA_MIME_TYPES: dict[str, str] = {
    ".wasm": "application/wasm",
    ".js": "application/javascript",
    ".symbols": "text/plain; charset=utf-8",
}


def _guess_media_type(original_path: str) -> str | None:
    ext = Path(original_path).suffix.lower()
    if ext in _EXTRA_MIME_TYPES:
        return _EXTRA_MIME_TYPES[ext]
    mime, _ = mimetypes.guess_type(original_path)
    return mime


def _parse_accept_encoding(scope: dict) -> str:
    # ASGI headers 會以「小寫 bytes」形式提供。
    for k, v in scope.get("headers") or []:
        if k == b"accept-encoding":
            try:
                return v.decode("latin-1").lower()
            except Exception:
                return ""
    return ""

def _get_header(scope: dict, header_name: bytes) -> str:
    """
    從 ASGI scope.headers 取出 header（小寫 bytes key），回傳 decoded string（若不存在回空字串）。
    """
    for k, v in scope.get("headers") or []:
        if k == header_name:
            try:
                return v.decode("latin-1")
            except Exception:
                return ""
    return ""


def _append_vary(existing: str | None, token: str) -> str:
    """
    讓 Vary 可「追加」而不覆蓋：例如原本是 "Origin"，追加後變成 "Origin, Accept-Encoding"。
    """
    if not existing:
        return token
    parts = [p.strip() for p in existing.split(",") if p.strip()]
    lowered = {p.lower() for p in parts}
    if token.lower() not in lowered:
        parts.append(token)
    return ", ".join(parts)

def _weak_etag_from_stat(stat_result: StatResult, encoding: str) -> str:
    # 以檔案大小 + mtime 生成 weak etag；並把 encoding 納入，避免 br/gzip 互相誤命中。
    mtime_ns = getattr(stat_result, "st_mtime_ns", None)
    if mtime_ns is None:
        mtime_ns = int(stat_result.st_mtime * 1_000_000_000)
    return f'W/"{int(stat_result.st_size):x}-{int(mtime_ns):x}-{encoding}"'


def _not_modified(scope: dict, etag: str, last_modified: datetime) -> bool:
    inm = _get_header(scope, b"if-none-match")
    if inm:
        # 允許 header 內包含多個 etag（逗號分隔）
        candidates = [c.strip() for c in inm.split(",") if c.strip()]
        if "*" in candidates or etag in candidates:
            return True

    ims = _get_header(scope, b"if-modified-since")
    if ims:
        try:
            dt = parsedate_to_datetime(ims)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            # RFC 行為：若資源最後修改時間 <= IMS，視為 not modified
            if last_modified <= dt:
                return True
        except Exception:
            pass

    return False


def _set_cache_headers(resp: Response, request_path: str) -> None:
    """
    Flutter Web 的快取策略：
    - index.html / version.json：不要快取（必須每次都能拿到最新 build）
    - canvaskit/*, *.wasm, *.symbols：檔案很大，長時間快取
    - main.dart.js / flutter_bootstrap.js / flutter.js：重要但檔名通常不含 hash，
      因此可快取但不要設 immutable（避免更新後長時間卡舊版）
    """
    raw = request_path or ""
    p = raw.lstrip("/")

    # html=True 時，目錄請求（含 "/"）等同 index.html
    if raw.endswith("/") or p in {"", ".", "./", "index.html"}:
        resp.headers["Cache-Control"] = "no-store, max-age=0"
        return

    if p == "version.json":
        resp.headers["Cache-Control"] = "no-cache, max-age=0, must-revalidate"
        return

    if p in {"main.dart.js", "flutter_bootstrap.js", "flutter.js"}:
        # 折衷：允許快取提升速度，但要求重新驗證避免長期卡舊版
        resp.headers["Cache-Control"] = "public, max-age=86400, must-revalidate"
        return

    if p.startswith("canvaskit/") or p.endswith((".wasm", ".symbols")):
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return

    if p.startswith("assets/"):
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return

    # 其他靜態資源的預設快取策略
    resp.headers["Cache-Control"] = "public, max-age=604800"


class PrecompressedStaticFiles(StaticFiles):
    """
    優先回傳「預先壓縮」版本的 StaticFiles：
    - 若 client 支援 "br"：回傳 `/path/file.ext.br`
    - 若 client 支援 "gzip"：回傳 `/path/file.ext.gz`

    這可避免 runtime 動態壓縮造成的 CPU 成本，同時提供 Flutter Web（main.dart.js / canvaskit / wasm）
    很好的首次載入效能。
    """

    async def get_response(self, path: str, scope: dict) -> Response:
        method = scope.get("method", "GET").upper()
        accept = _parse_accept_encoding(scope)

        # 只在一般靜態檔案的 GET/HEAD 時嘗試回傳預壓縮版本
        if method in {"GET", "HEAD"} and ("br" in accept or "gzip" in accept):
            full_path, stat_result = self.lookup_path(path)
            if stat_result is not None and Path(full_path).is_file():
                # 優先使用 brotli，其次 gzip
                candidates: list[tuple[str, str]] = []
                if "br" in accept:
                    candidates.append(("br", str(full_path) + ".br"))
                if "gzip" in accept:
                    candidates.append(("gzip", str(full_path) + ".gz"))

                for encoding, candidate in candidates:
                    cpath = Path(candidate)
                    try:
                        cstat = cpath.stat()
                    except OSError:
                        continue
                    if not cpath.is_file():
                        continue

                    media_type = _guess_media_type(path)
                    etag = _weak_etag_from_stat(cstat, encoding)
                    last_modified = datetime.fromtimestamp(cstat.st_mtime, tz=timezone.utc)

                    # 命中快取驗證：回 304，避免重複下載（特別是 main.dart.js 這類 must-revalidate）
                    if _not_modified(scope, etag=etag, last_modified=last_modified):
                        resp = Response(status_code=304)
                        resp.headers["ETag"] = etag
                        resp.headers["Last-Modified"] = format_datetime(last_modified, usegmt=True)
                        resp.headers["Content-Encoding"] = encoding
                        resp.headers["Vary"] = _append_vary(resp.headers.get("Vary"), "Accept-Encoding")
                        _set_cache_headers(resp, path)
                        return resp

                    resp = FileResponse(
                        path=str(cpath),
                        stat_result=cstat,
                        media_type=media_type,
                    )
                    # 額外補齊 validator headers，讓中介快取/瀏覽器更可靠
                    resp.headers["ETag"] = etag
                    resp.headers["Last-Modified"] = format_datetime(last_modified, usegmt=True)
                    resp.headers["Content-Encoding"] = encoding
                    resp.headers["Vary"] = _append_vary(resp.headers.get("Vary"), "Accept-Encoding")
                    _set_cache_headers(resp, path)
                    return resp

        resp = await super().get_response(path, scope)
        # 錯誤回應不要快取（避免部署切換期間的暫時性 404 被快取）
        if getattr(resp, "status_code", 200) >= 400:
            resp.headers["Cache-Control"] = "no-store, max-age=0"
        else:
            # 即使回傳未壓縮版本，也要補上快取 header 以提升效能
            _set_cache_headers(resp, path)
        # 為了中介節點/快取正確性：回應會因 Accept-Encoding 而不同
        resp.headers["Vary"] = _append_vary(resp.headers.get("Vary"), "Accept-Encoding")
        return resp