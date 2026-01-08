import os
from typing import Any, Dict, List, Type

from beanie import init_beanie
from pymongo import AsyncMongoClient

from logger import setup_logger

logger = setup_logger("mongo")

MONGO_URI = os.getenv("MONGO_URI", "mongodb://root:4I0rsokkcCICZNMx@localhost:27015/admin")
MONGO_DB = os.getenv("MONGO_DB", "nycu_rehab")
DB_NAME = os.getenv("DB_NAME", "nycu_rehab")

DB: Dict[str, AsyncMongoClient] = {}


async def _ensure_ttl_index(
    db,
    *,
    collection: str,
    field: str,
    expire_after_seconds: int = 3600,
) -> None:
    """
    Ensure `collection.field` has a TTL index (`expireAfterSeconds`).

    If an index exists with same key but different options/name, this may cause
    IndexOptionsConflict. We drop conflicting indexes then re-create.
    """
    col = db[collection]
    target_key = {field: 1}
    target_name = f"{field}_ttl"

    try:
        indexes = []
        cursor = await col.list_indexes()
        async for idx in cursor:
            indexes.append(idx)
    except Exception as e:
        logger.warning("Could not list indexes for %s: %s", collection, e, exc_info=False)
        return

    idx_by_name = {idx.get("name"): idx for idx in indexes if idx.get("name")}

    def _key(idx) -> Dict:
        try:
            return dict(idx.get("key", {}))
        except Exception:
            return {}

    for idx in indexes:
        if (
            _key(idx) == target_key
            and idx.get("expireAfterSeconds") == expire_after_seconds
            and idx.get("name") == target_name
        ):
            return

    to_drop = set()
    for idx in indexes:
        name = idx.get("name")
        if not name:
            continue
        key = _key(idx)
        ttl = idx.get("expireAfterSeconds", None)

        if name == target_name and (key != target_key or ttl != expire_after_seconds):
            to_drop.add(name)
        if key == target_key and (ttl != expire_after_seconds or name != target_name):
            to_drop.add(name)

    for name in to_drop:
        idx = idx_by_name.get(name, {})
        try:
            await col.drop_index(name)
            logger.info(
                "Dropped conflicting index %s on %s (key=%s, expireAfterSeconds=%s)",
                name,
                collection,
                _key(idx),
                idx.get("expireAfterSeconds", None),
            )
        except Exception as e:
            logger.warning(
                "Failed to drop conflicting index %s on %s: %s",
                name,
                collection,
                e,
                exc_info=False,
            )
            return

    try:
        await col.create_index(
            [(field, 1)],
            expireAfterSeconds=expire_after_seconds,
            name=target_name,
        )
        logger.info(
            "Ensured TTL index on %s.%s (expireAfterSeconds=%s)",
            collection,
            field,
            expire_after_seconds,
        )
    except Exception as e:
        logger.warning(
            "Failed to create TTL index on %s.%s: %s",
            collection,
            field,
            e,
            exc_info=False,
        )


async def get_db(
    *,
    db_name: str = DB_NAME,
    document_models: List[Type] = [],
    timeout_ms: int = 5000,
) -> AsyncMongoClient:
    """Get PyMongo Async client by name (lazy init)."""
    try:
        if db_name not in DB:
            logger.info("Initializing DB %s...", db_name)
            DB[db_name] = await _init_db(document_models, timeout_ms=timeout_ms)
        else:
            logger.info("DB %s already initialized.", db_name)
        return DB[db_name]
    except RuntimeError as e:
        logger.error("Failed to initialize DB: %s", e, exc_info=False)
        raise
    except Exception as e:
        logger.error("Failed to initialize DB: %s", e, exc_info=False)
        raise RuntimeError(
            "Database connection failed. Please ensure MongoDB is running and reachable."
        ) from None


async def _init_db(document_models: List[Type], *, timeout_ms: int = 5000) -> AsyncMongoClient:
    """Init PyMongo Async client and Beanie, with basic validation and TTL index prep."""
    # PyMongo Async (Beanie 2.0 推薦的方式)
    client: AsyncMongoClient[Any] = AsyncMongoClient(
        MONGO_URI,
        serverSelectionTimeoutMS=timeout_ms,
        connectTimeoutMS=timeout_ms,
        socketTimeoutMS=timeout_ms,
        maxIdleTimeMS=5 * 60 * 1000,
        maxPoolSize=10,
        minPoolSize=0,
    )
    try:
        ping = await client.admin.command("ping")
        if not ping or ping.get("ok", 0) != 1:
            raise RuntimeError(f"Mongo ping failed: {ping}")
        logger.info("Mongo ping OK.")
    except Exception as e:
        try:
            await client.close()
        except Exception:
            pass
        logger.error("MongoDB ping failed: %s", e, exc_info=False)
        raise RuntimeError(
            "Database connection failed while pinging MongoDB. Please check connection settings."
        ) from None

    try:
        db = client[MONGO_DB]
        await _ensure_ttl_index(db, collection="admin_session", field="expires_at", expire_after_seconds=3600)
        await _ensure_ttl_index(db, collection="admin_invitation", field="expires_at", expire_after_seconds=3600)
        await _ensure_ttl_index(db, collection="realsense_extract_job", field="expires_at", expire_after_seconds=0)
        await init_beanie(database=db, document_models=document_models)
        logger.info("Beanie init_beanie completed.")
    except Exception as e:
        try:
            await client.close()
        except Exception:
            pass
        logger.error("init_beanie failed: %s", e, exc_info=False)
        raise RuntimeError("Database initialization failed while preparing models.") from None

    try:
        # quick import sanity check
        from beanie import Document as _D  # noqa: F401

        logger.info("DB & Beanie ready.")
    except Exception as e:
        logger.error("Post-init validation failed: %s", e, exc_info=False)
        await client.close()
        raise RuntimeError("Database initialization failed during validation.") from None

    return client
