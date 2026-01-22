from datetime import datetime
from pathlib import Path
from typing import Optional

from beanie import Document
from pydantic import Field, ValidationInfo, field_validator
from pymongo import ASCENDING, IndexModel

from ..model_utils import generate_code


class RealsensePoseExtractor(Document):
    session_name: str = Field(default_factory=generate_code, description="session 唯一識別碼（UUID 字串）。")
    user_code: Optional[str] = Field(
        None,
        description="對應 UserProfile.user_code（1 使用者 -> 多個 bag/session；未知或未綁定則為 None）。",
    )
    npy_path: str = Field(..., description="提取後的 npy 輸出路徑（server 路徑字串）。")
    video_path: Optional[str] = Field(None, description="提取後的影片輸出路徑（若有啟用 save_video）。")
    bag_path: str = Field(..., description="輸入 bag 檔路徑（server 路徑字串）。")
    bag_filename: Optional[str] = Field(None, description="BAG 檔案名稱，從 bag_path 提取。")
    bag_hash: Optional[str] = Field(None, description="bag 檔內容雜湊，未計算時為 None。")
    created_at: datetime = Field(default_factory=datetime.now, description="建立時間（server local time）。")
    updated_at: datetime = Field(default_factory=datetime.now, description="最後更新時間（server local time）。")

    @field_validator("bag_filename", mode="before")
    @classmethod
    def _extract_bag_filename(cls, v: Optional[str], info: ValidationInfo) -> str:
        """從 bag_path 自動提取 bag_filename（若未提供）。"""
        if v:   
            return v
        # 如果沒有提供 bag_filename，從 bag_path 提取
        bag_path = info.data.get("bag_path")
        if bag_path:
            return Path(bag_path).name
        raise ValueError("bag_filename is required and cannot be extracted from bag_path")

    class Settings:
        name = "realsense_pose_extractor"
        collection = "realsense_pose_extractor"
        indexes = [
            IndexModel([("session_name", ASCENDING)], unique=True),
            IndexModel([("bag_path", ASCENDING)]),
            IndexModel([("bag_filename", ASCENDING)]),
            IndexModel([("bag_hash", ASCENDING)]),
            IndexModel([("user_code", ASCENDING)]),
            IndexModel(
                [("bag_hash", ASCENDING), ("user_code", ASCENDING)],
                name="idx_bag_hash_user_code",
            ),
        ]


