from pathlib import Path
from typing import Any, Union
from urllib.parse import quote

import httpx
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse, RedirectResponse
from cachetools import TTLCache

from ...auth import require_signed_headers
from ...config import GITHUB_API_URL

_EXT_TO_MEDIA_TYPE: dict[str, str] = {
    ".apk": "application/vnd.android.package-archive",
    ".exe": "application/vnd.microsoft.portable-executable",
}

# 緩存設定：10 分鐘 TTL
_release_cache: TTLCache = TTLCache(maxsize=1, ttl=600)
_CACHE_KEY = "assets"

# 允許的檔案模式
_ALLOWED_PATTERNS = ["_Setup_", "-macOS-", "-Linux-x64-", ".apk"]

router = APIRouter(prefix="/apk", tags=["apk"])


def _external_base(request: Request) -> str:
    """產生對外可用的 base URL（處理反向代理）"""
    proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    host = (request.headers.get("x-forwarded-host") or "").split(",")[0].strip()

    if not proto:
        cf_visitor = request.headers.get("cf-visitor") or ""
        proto = "https" if "https" in cf_visitor.lower() else request.url.scheme

    if not host:
        host = request.headers.get("host") or request.url.netloc

    return f"{proto}://{host}"


def _external_url(request: Request, path: str) -> str:
    return f"{_external_base(request)}{path if path.startswith('/') else '/' + path}"


def _guess_media_type(filename: str) -> str:
    """依副檔名推測 Content-Type"""
    return _EXT_TO_MEDIA_TYPE.get(Path(filename).suffix.lower(), "application/octet-stream")


async def _fetch_github_release_assets() -> list[dict[str, Any]]:
    """從 GitHub Releases 獲取資產列表（帶緩存）"""
    if _CACHE_KEY in _release_cache:
        return _release_cache[_CACHE_KEY]

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                GITHUB_API_URL,
                headers={"Accept": "application/vnd.github+json"},
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()

            # 只保留符合模式的資產，並簡化資料結構
            assets = [
                {
                    "name": asset["name"],
                    "size": asset["size"],
                    "download_url": asset["browser_download_url"],
                    "mtime": int(datetime.fromisoformat(asset.get("updated_at", "").replace("Z", "+00:00")).timestamp())
                    if asset.get("updated_at")
                    else 0,
                }
                for asset in data.get("assets", [])
                if any(pattern in asset["name"] for pattern in _ALLOWED_PATTERNS)
            ]

            _release_cache[_CACHE_KEY] = assets
            return assets

        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Failed to fetch release: {str(e)}")


@router.get("", summary="List available installation files")
async def list_apk_files(
    request: Request,
    _: Any = Depends(require_signed_headers),
) -> dict[str, Any]:
    """列出可下載的安裝檔案"""
    assets = await _fetch_github_release_assets()

    files = [
        {
            "path": asset["name"],
            "name": asset["name"],
            "size_bytes": asset["size"],
            "mtime": asset["mtime"],
            "url": _external_url(request, request.url_for("download_apk", file_path=asset["name"]).path),
        }
        for asset in assets
    ]

    return {"files": files}


@router.get("/{file_path:path}", summary="Download installation file", response_model=None)
async def download_apk(file_path: str, proxy: bool = True) -> Union[StreamingResponse, RedirectResponse]:
    """
    下載安裝檔案
    
    - proxy=true (預設): 透過伺服器代理下載 (隱藏來源但較慢)
    - proxy=false: 直接重定向到 GitHub (最快)
    """
    assets = await _fetch_github_release_assets()

    target_asset = next((a for a in assets if a["name"] == file_path), None)
    if not target_asset:
        raise HTTPException(status_code=404, detail="File not found")

    # 直接重定向模式
    if not proxy:
        return RedirectResponse(url=target_asset["download_url"], status_code=302)

    # 代理模式 (預設)
    async def stream_file():
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(60.0, connect=10.0),
        ) as client:
            async with client.stream("GET", target_asset["download_url"]) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes(chunk_size=131072):  # 128KB chunks
                    yield chunk

    fn = target_asset["name"]
    headers = {
        "Content-Disposition": f'attachment; filename="{fn}"; filename*=UTF-8\'\'{quote(fn)}',
        "X-Content-Type-Options": "nosniff",
        "Content-Length": str(target_asset["size"]),
    }

    return StreamingResponse(
        stream_file(),
        media_type=_guess_media_type(fn),
        headers=headers,
    )