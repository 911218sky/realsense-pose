from datetime import datetime
from typing import Optional

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, IndexModel

from ..model_utils import generate_code


class RealsensePoseExtractor(Document):
    session_name: str = Field(default_factory=generate_code, description="session 唯一識別碼（UUID 字串）。")
    user_code: Optional[str] = Field(
        None,
        description="對應 UserProfile.user_code（1 使用者 -> 多個 bag/session；未知或未綁定則為 None）。",
    )
    npy_path: str = Field(..., description="提取後的 npy 輸出路徑（server 路徑字串）。")
    bag_path: str = Field(..., description="輸入 bag 檔路徑（server 路徑字串）。")
    bag_hash: Optional[str] = Field(None, description="bag 檔內容雜湊（用於去重/快取；若未計算則 None）。")
    created_at: datetime = Field(default_factory=datetime.now, description="建立時間（server local time）。")
    updated_at: datetime = Field(default_factory=datetime.now, description="最後更新時間（server local time）。")

    class Settings:
        name = "realsense_pose_extractor"
        collection = "realsense_pose_extractor"
        indexes = [
            IndexModel([("session_name", ASCENDING)], unique=True),
            IndexModel([("bag_hash", ASCENDING)]),
            IndexModel([("user_code", ASCENDING)]),
        ]


