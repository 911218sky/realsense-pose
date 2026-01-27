import json
import os
from functools import wraps
from typing import Any, Callable, Optional, Sequence

import redis.asyncio as aioredis
from fastapi import Request
from fastapi.encoders import jsonable_encoder

from logger import setup_logger

logger = setup_logger("api.utils.cache")

# 快取控制：
# 1. 若 IS_PROD=0（開發模式），強制關閉快取
# 2. 若 IS_PROD=1（生產模式），依 USE_REDIS_CACHE 設定決定
IS_PROD = os.getenv("IS_PROD", "0").lower() in {"1", "true", "on", "yes"}
USE_REDIS_CACHE_ENV = os.getenv("USE_REDIS_CACHE", "").lower() in {"1", "true", "on", "yes"}
USE_REDIS_CACHE = IS_PROD and USE_REDIS_CACHE_ENV

if not IS_PROD:
    logger.info("Development mode (IS_PROD=0): Redis cache is disabled")
elif not USE_REDIS_CACHE_ENV:
    logger.info("Production mode but USE_REDIS_CACHE not enabled: Redis cache is disabled")
else:
    logger.info("Production mode with USE_REDIS_CACHE enabled: Redis cache is active")

def redis_cache(
    expire: int = 30,
    prefix: str = "rehab-analyzer",
    *,
    key_fields: Optional[Sequence[str]] = None,
    key_builder: Optional[Callable[[Callable, Request, tuple, dict], str]] = None,
) -> Callable:
    """
    簡單的 Redis 快取裝飾器。

    依賴：
      - FastAPI lifespan 已經把 redis client 掛在 app.state.redis
      - endpoint 需要有 request: Request 參數

    參數：
      - expire: 快取存活秒數
      - prefix: key 前綴
      - key_fields: 想拿哪些 kwargs 當 key，一律使用 json 序列化後拼入 key
      - key_builder: 完全客製化的 key 生成函式
                     介面為 (func, request, args, kwargs) -> str
                     若提供此參數，會覆蓋 key_fields 與預設邏輯
    """

    def default_build_key(func: Callable, request: Request, args: tuple, kwargs: dict) -> str:
        # 自訂 key_builder 優先
        if key_builder is not None:
            return key_builder(func, request, args, kwargs)

        parts = [prefix, func.__name__]

        if key_fields:
            # 只用指定欄位組 key
            for name in key_fields:
                if name in kwargs:
                    value = kwargs[name]
                    value_json = json.dumps(
                        jsonable_encoder(value),
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    parts.append(f"{name}={value_json}")
        else:
            # 預設行為：session_name + config
            session_name = kwargs.get("session_name")
            config = kwargs.get("config")

            if session_name is not None:
                parts.append(str(session_name))
            if config is not None:
                try:
                    conf_dict = config.model_dump()
                except Exception as e:
                    logger.exception("model_dump config failed: %s", e)
                    conf_dict = jsonable_encoder(config)
                parts.append(
                    json.dumps(
                        conf_dict,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                )

        return ":".join(parts)

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any):
            if not USE_REDIS_CACHE:
                return await func(*args, **kwargs)

            request: Request | None = kwargs.get("request")
            if request is None:
                # 沒有 request 無法拿到 redis，直接執行原函式
                return await func(*args, **kwargs)

            redis: Optional[aioredis.Redis] = getattr(request.app.state, "redis", None)
            if redis is None:
                logger.warning("no redis client found")
                # 沒有 redis client，直接執行原函式
                return await func(*args, **kwargs)

            cache_key = default_build_key(func, request, args, kwargs)

            # 嘗試從 Redis 取得
            try:
                cached_bytes = await redis.get(cache_key)
                if cached_bytes is not None:
                    cached_json = cached_bytes.decode("utf-8") if isinstance(
                        cached_bytes, (bytes, bytearray)
                    ) else cached_bytes
                    data = json.loads(cached_json)
                    logger.info("redis_cache HIT key=%s", cache_key)
                    return data
            except Exception as e:
                logger.exception("redis_cache get failed: %s", e)

            # 執行實際函式
            result = await func(*args, **kwargs)

            # 寫回 Redis
            try:
                value_json = json.dumps(
                    jsonable_encoder(result),
                    separators=(",", ":"),
                )
                await redis.set(cache_key, value_json, ex=expire)
                logger.info("redis_cache SET key=%s", cache_key)
            except Exception as e:
                logger.exception("redis_cache set failed: %s", e)

            return result

        return wrapper

    return decorator


# example usage

# default key builder: session_name + config
# @router.post("/stage_durations")
# @redis_cache(expire=30, key_fields=["session_name"])
# async def stage_durations(
#     session_name: str,
#     config: Optional[StageDurationsRequest] = Body(None),
#     request: Request = None,
# ):

# example usage with custom key builder
# def my_key_builder(func, request: Request, args, kwargs) -> str:
#     session_name = kwargs.get("session_name", "")
#     return f"mycache:{request.method}:{request.url.path}:{session_name}"

# @router.post("/stage_durations")
# @redis_cache(expire=30, key_builder=my_key_builder)
# async def stage_durations(
#     session_name: str,
#     config: Optional[StageDurationsRequest] = Body(None),
#     request: Request = None,
# ):
#     ...