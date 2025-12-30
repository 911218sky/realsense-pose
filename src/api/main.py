import os
import time
import uuid
from pathlib import Path
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi import Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from redis import asyncio as aioredis

from db import get_db
from db import (
    AdminAccount,
    AdminInvitation,
    AdminSession,
    BagFile,
    RealsenseExtractJob,
    RealsensePoseExtractor,
    UserProfile,
)
from logger import setup_logger

from .auth import require_signed_headers
from .middlewares.payload_decode import PayloadDecodeMiddleware
from .utils.precompressed_staticfiles import PrecompressedStaticFiles
from .utils.env import env_bool, env_csv
from .v1.admins import require_admin
from .v1 import (
    admins_router,
    rehab_analyzer_router,
    users_router,
    realsense_pose_extractor_router,
    realsense_pose_extractor_public_router,
    apk_router,
)

IS_PROD = env_bool("IS_PROD", False)
HOST = os.getenv("HOST", "localhost")
PORT = int(os.getenv("PORT", 3000))
PREFIX = os.getenv("PREFIX", "/v1")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
CORS_ALLOW_ORIGINS = env_csv("CORS_ALLOW_ORIGINS")
CORS_ALLOW_ORIGIN_REGEX = os.getenv("CORS_ALLOW_ORIGIN_REGEX", "").strip() or None
SERVE_WEB = env_bool("SERVE_WEB", True)
WEB_DIR = Path(os.getenv("WEB_DIR", "./web"))
WEB_INDEX = WEB_DIR / "index.html"

logger = setup_logger("api")

# 後端啟動識別（每次服務重啟都會改變）
# - 用於前端偵測「後端已重啟」並清理 service worker / CacheStorage
BOOT_ID = os.getenv("BOOT_ID", "").strip() or uuid.uuid4().hex
BOOT_TS = int(time.time())

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    在 app 啟動時被呼叫 (先於任何 router 處理)
    - 初始化 DB
    - 初始化 Redis 並放到 app.state.redis
    在 app 關閉時會執行 finally 裡的清理
    """
    client = getattr(app.state, "mongo_client", None)
    redis = None

    if client is None:
        try:
            client = await get_db(
                document_models=[
                    RealsensePoseExtractor,
                    RealsenseExtractJob,
                    UserProfile,
                    AdminAccount,
                    AdminInvitation,
                    AdminSession,
                    BagFile,
                ],
            )
        except Exception as e:
            # Keep startup logs concise; propagate a clean error message.
            logger.error("DB initialization failed in lifespan: %s", e, exc_info=False)
            raise

    try:
        # 初始化 Redis 並掛到 app.state
        try:
            redis = aioredis.from_url(REDIS_URL)
            app.state.redis = redis
            logger.info(f"Redis client initialized with URL={REDIS_URL}")
        except Exception:
            logger.exception("Redis initialization failed in lifespan")
            raise

        yield
    finally:
        # 關閉 Mongo
        try:
            if client is not None:
                client.close()
                logger.info("Mongo client closed (lifespan shutdown)")
        except Exception:
            logger.exception("Error while closing mongo client in lifespan")

        # 關閉 Redis
        try:
            if redis is not None:
                await redis.close()
                logger.info("Redis client closed (lifespan shutdown)")
        except Exception:
            logger.exception("Error while closing redis client in lifespan")


app = FastAPI(
    title="Rehabilitation Session Analyzer API",
    version="1.0.0",
    description="Analyze rehabilitation session data",
    docs_url=None    if IS_PROD else "/docs",
    redoc_url=None   if IS_PROD else "/redoc",
    openapi_url=None if IS_PROD else "/openapi.json",
    lifespan=lifespan,
)

# Decode compressed binary request bodies (e.g., gzip sent as application/octet-stream)
app.add_middleware(PayloadDecodeMiddleware)

# Minimal public endpoints (helpful for load balancers / smoke tests)
@app.get("/", include_in_schema=False)
async def root() -> dict:
    if SERVE_WEB and WEB_INDEX.is_file():
        return FileResponse(WEB_INDEX)
    return {
        "ok": True,
        "service": "realsense_pose_api",
        "prod": IS_PROD,
        "prefix": PREFIX,
        "hint": f"Try {PREFIX} (e.g. {PREFIX}/users)",
    }


@app.get("/boot.json", include_in_schema=False)
async def boot_info() -> JSONResponse:
    """
    回傳後端啟動資訊（每次服務重啟都會改變）。

    目的：讓前端可以在偵測到後端重啟後，主動清理 service worker / CacheStorage，確保重新抓取檔案。
    """
    resp = JSONResponse({"boot_id": BOOT_ID, "boot_ts": BOOT_TS})
    resp.headers["Cache-Control"] = "no-store, max-age=0"
    return resp

# CORS
# - Dev default: allow all
# - Prod default: allow a safe set provided via env; if omitted, allow all (so it won't mysteriously break)
allow_origins = CORS_ALLOW_ORIGINS if CORS_ALLOW_ORIGINS else ["*"]
allow_credentials = bool(CORS_ALLOW_ORIGINS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_origin_regex=CORS_ALLOW_ORIGIN_REGEX,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# include routers
app.include_router(
    apk_router,
    prefix=PREFIX,
    tags=[PREFIX.replace("/", "")],
)

app.include_router(
    admins_router,
    prefix=PREFIX,
    dependencies=[Depends(require_signed_headers)],
    tags=[PREFIX.replace("/", "")]
)

app.include_router(
    realsense_pose_extractor_router,
    prefix=PREFIX,
    dependencies=[Depends(require_signed_headers), Depends(require_admin)],
    tags=[PREFIX.replace("/", "")],
)

# 公開路由：影片串流（不需要認證）
app.include_router(
    realsense_pose_extractor_public_router,
    prefix=PREFIX,
    tags=["public"],
)

app.include_router(
    rehab_analyzer_router,
    prefix=PREFIX,
    dependencies=[Depends(require_signed_headers), Depends(require_admin)],
    tags=[PREFIX.replace("/", "")]
)

app.include_router(
    users_router,
    prefix=PREFIX,
    dependencies=[Depends(require_signed_headers), Depends(require_admin)],
    tags=[PREFIX.replace("/", "")]
)

# Serve Flutter Web at "/" (after API routes are registered so "/v1/..." keeps working)
if SERVE_WEB and WEB_INDEX.is_file():
    app.mount("/", PrecompressedStaticFiles(directory=str(WEB_DIR), html=True), name="web")
    logger.info("Serving web UI from %s", str(WEB_DIR))
else:
    logger.info("Web UI disabled or missing (SERVE_WEB=%s, WEB_DIR=%s)", SERVE_WEB, str(WEB_DIR))

base_url = f"http://{HOST}:{PORT}"
if not IS_PROD:
    logger.info("API 已啟動 (開發模式)")
    logger.info(f"DOCS   URL: {base_url}{app.docs_url}")
    logger.info(f"REDOC  URL: {base_url}{app.redoc_url}")
else:
    logger.info("API 已啟動 (生產模式)，文件已關閉")