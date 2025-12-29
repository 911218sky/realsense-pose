import asyncio
import math
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Query
from pymongo import UpdateOne

from api.config import BAG_DIR, DATASET_DIR, HOST_DATASET_DIR
from db import BagFile
from .models import BagFileItem, BagFileListResponse

router = APIRouter()

_SYNC_LOCKS: Dict[str, asyncio.Lock] = {}

def _sync_lock_key(base_dir: Path, recursive: bool) -> str:
    return f"{str(base_dir.resolve())}|recursive={int(bool(recursive))}"

def _get_sync_lock(base_dir: Path, recursive: bool) -> asyncio.Lock:
    key = _sync_lock_key(base_dir, recursive)
    lock = _SYNC_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _SYNC_LOCKS[key] = lock
    return lock

def get_dataset_dir() -> Path:
    """
    取得「當前執行環境」實際可讀的 dataset 目錄：
    - 若 HOST_DATASET_DIR 在此環境存在（常見於非 Docker 直接跑在 host / Windows）：用它
    - 否則若 DATASET_DIR 存在（常見於 Docker 容器 / 掛載點）：用它（預設 /app/dataset，可用 env DATASET_DIR 覆寫）
    - 否則 fallback 到 BAG_DIR（等同把 cache 當作 dataset 來源）
    """
    if HOST_DATASET_DIR:
        try:
            p = Path(HOST_DATASET_DIR).resolve()
            if p.exists() and p.is_dir():
                return p
        except Exception:
            pass
    try:
        p = Path(DATASET_DIR).resolve()
        if p.exists() and p.is_dir():
            return p
    except Exception:
        pass
    return Path(BAG_DIR)

def _iter_bag_entries(base_dir: Path, recursive: bool):
    """
    用 os.scandir 做較快的遞迴掃描（比 Path.rglob 省資源）。
    """
    stack = [str(base_dir)]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for entry in it:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if recursive:
                                stack.append(entry.path)
                            continue
                        if entry.is_file(follow_symlinks=False) and entry.name.lower().endswith(".bag"):
                            yield entry
                    except Exception:
                        continue
        except Exception:
            continue


async def _sync_bag_files_to_mongo(
    *,
    base_dir: Path,
    recursive: bool,
    scan_id: str,
) -> None:
    """
    同步資料夾到 MongoDB（不先把 DB 全量讀出來）：
    - 掃描時對每個檔案做 upsert，並寫入本次 scan_id
    - 掃描完成後，把 scan_id 不等於本次的舊資料刪掉

    這種「scan_id 標記法」的優點：
    - 避免先把 DB 既有資料全量拉回來做 set 差集（省時間/省記憶體）
    - 避免建出超大的 $nin 列表（可能超過 Mongo 16MB 限制）
    """
    # 統一使用 resolve 後的 base_dir，避免因相對/絕對或大小寫差異導致
    # 同一個資料夾被當成不同 base_dir 存進 DB，進而影響「刪除消失檔案」的同步邏輯。
    base_dir = base_dir.resolve()
    base_dir_str = str(base_dir)
    col = BagFile.get_pymongo_collection()

    now = datetime.now()
    ops: list[UpdateOne] = []

    # 掃描資料夾並批次 upsert
    chunk_size = 1000
    for entry in _iter_bag_entries(base_dir, recursive):
        try:
            rp = Path(entry.path).resolve()
            if base_dir not in rp.parents and rp != base_dir:
                continue

            rel = rp.relative_to(base_dir).as_posix()
            st = entry.stat(follow_symlinks=False)

            ops.append(
                UpdateOne(
                    {"base_dir": base_dir_str, "recursive": bool(recursive), "bag_id": rel},
                    {
                        "$set": {
                            "name": rp.name,
                            "name_lc": rp.name.lower(),
                            "bag_id_lc": rel.lower(),
                            "size_bytes": int(st.st_size),
                            "modified_at": datetime.fromtimestamp(st.st_mtime),
                            "updated_at": now,
                            "scan_id": scan_id,
                        },
                        "$setOnInsert": {
                            "created_at": now,
                        },
                    },
                    upsert=True,
                )
            )
        except Exception:
            continue

        if len(ops) >= chunk_size:
            # 不依賴順序，改用 unordered 以提升 bulk write 效能。
            await col.bulk_write(ops, ordered=False)
            ops = []

    if ops:
        await col.bulk_write(ops, ordered=False)

    # 刪掉這次掃描沒有出現的舊資料：
    # - scan_id != 本次 scan_id：代表本次沒掃到（檔案已消失或 recursive 切換導致）
    # - scan_id 欄位不存在：兼容非常舊的資料格式/手動寫入的資料
    await col.delete_many(
        {
            "base_dir": base_dir_str,
            "recursive": bool(recursive),
            "$or": [{"scan_id": {"$ne": scan_id}}, {"scan_id": {"$exists": False}}],
        }
    )


@router.get("/bags", response_model=BagFileListResponse)
async def list_server_bags(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    recursive: bool = Query(True, description="是否遞迴搜尋子資料夾"),
    q: Optional[str] = Query(
        None,
        max_length=256,
        description="關鍵字搜尋（優化版）：預設用「前綴匹配」走索引（name/bag_id），例如輸入 '1' 可快速匹配 '1_*.bag'。",
    ),
) -> BagFileListResponse:
    """
    分頁列出伺服器上的 .bag 檔案清單。
    """
    page = max(1, page)
    page_size = max(1, min(page_size, 200))
    q = (q or "").strip() or None

    base_dir = get_dataset_dir().resolve()

    # 同步到 Mongo（不使用 redis）
    # - recursive=true：遞迴掃描整棵樹
    # - recursive=false：只掃 base_dir 第一層
    scan_id = uuid4().hex
    lock = _get_sync_lock(base_dir, bool(recursive))
    async with lock:
        # 讓出 event loop，避免高併發時單一請求佔用太久
        await asyncio.sleep(0)
        await _sync_bag_files_to_mongo(base_dir=base_dir, recursive=bool(recursive), scan_id=scan_id)

    # 透過 Mongo 做分頁與搜尋
    base_dir_str = str(base_dir.resolve())
    col = BagFile.get_pymongo_collection()

    query: dict[str, Any] = {"base_dir": base_dir_str, "recursive": bool(recursive)}
    sort = [("modified_at", -1), ("bag_id", 1)]
    projection = {"_id": 0, "bag_id": 1, "name": 1, "size_bytes": 1, "modified_at": 1}

    if q:
        q_str = q.strip()
        q_lc = q_str.lower()
        esc = re.escape(q_lc)
        # 前綴匹配（regex 以 ^ 開頭）可利用索引加速
        query["$or"] = [
            {"name_lc": {"$regex": f"^{esc}"}},
            {"bag_id_lc": {"$regex": f"^{esc}"}},
        ]

    total = await col.count_documents(query)
    total_pages = math.ceil(total / page_size) if total else 0
    if total_pages and page > total_pages:
        page = total_pages

    skip = (page - 1) * page_size if total else 0
    docs: List[BagFile] = await (
        col.find(query, projection)
        .sort(sort)
        .skip(skip)
        .limit(page_size)
        .to_list(length=page_size)
    )

    page_items = [BagFileItem.model_validate(d) for d in docs]

    return BagFileListResponse(
        total=total,
        page=page if total else 1,
        page_size=page_size,
        total_pages=total_pages,
        items=page_items,
    )