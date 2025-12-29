from datetime import datetime
from typing import Optional

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, DESCENDING, IndexModel


class BagFile(Document):
    """
    用於儲存伺服器上 .bag 檔案清單的資料模型（存 MongoDB），以便：
    - 快速分頁
    - 快速搜尋（搭配索引）
    - 每次查詢前同步資料夾與資料庫狀態
    """

    base_dir: str = Field(..., description="dataset 根目錄（resolve 後的絕對路徑字串）。")
    recursive: bool = Field(True, description="是否遞迴掃描 base_dir 子資料夾。")

    bag_id: str = Field(..., description="相對於 base_dir 的路徑（POSIX 風格，例如 'subdir/1.bag'）。")
    name: str = Field(..., description="檔名（不含路徑）。")
    bag_id_lc: str = Field(..., description="bag_id 的小寫版（用於大小寫無關搜尋與索引）。")
    name_lc: str = Field(..., description="name 的小寫版（用於大小寫無關搜尋與索引）。")

    size_bytes: int = Field(..., description="檔案大小（bytes）。")
    modified_at: datetime = Field(..., description="檔案最後修改時間（從檔案系統讀取）。")

    scan_id: Optional[str] = Field(
        None,
        description=(
            "掃描同步批次識別：每次同步寫入新的 scan_id；同步完成後刪掉 scan_id != 本次的舊資料。"
        ),
    )

    created_at: datetime = Field(default_factory=datetime.now, description="建立時間（server local time）。")
    updated_at: datetime = Field(default_factory=datetime.now, description="最後更新時間（server local time）。")

    class Settings:
        name = "bag_file"
        collection = "bag_file"
        indexes = [
            IndexModel(
                [("base_dir", ASCENDING), ("recursive", ASCENDING), ("bag_id", ASCENDING)],
                unique=True,
                name="uq_base_recursive_bagid",
            ),
            IndexModel(
                [("base_dir", ASCENDING), ("recursive", ASCENDING), ("modified_at", DESCENDING)],
                name="idx_base_recursive_modified",
            ),
            IndexModel(
                [("bag_id", "text"), ("name", "text")],
                name="idx_bag_text",
                default_language="none",
            ),
            IndexModel(
                [("base_dir", ASCENDING), ("recursive", ASCENDING), ("name_lc", ASCENDING)],
                name="idx_base_recursive_name_lc",
            ),
            IndexModel(
                [("base_dir", ASCENDING), ("recursive", ASCENDING), ("bag_id_lc", ASCENDING)],
                name="idx_base_recursive_bag_id_lc",
            ),
            IndexModel(
                [("base_dir", ASCENDING), ("recursive", ASCENDING), ("scan_id", ASCENDING)],
                name="idx_base_recursive_scanid",
            ),
        ]


