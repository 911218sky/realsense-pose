import os
from datetime import datetime, timedelta
from typing import Any, Dict, Literal, Optional

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, IndexModel

# 保留 job 的時數（30 分鐘）
REALSENSE_EXTRACT_JOB_RETENTION_MINUTES = int(os.getenv("REALSENSE_EXTRACT_JOB_RETENTION_MINUTES", str(30)))


class RealsenseExtractJob(Document):
    """
    `/realsense_pose_extractor/extract` 的背景提取任務（Job）。

    用途：
    - 支援非同步 job 模式（先回 202 + job_id，後續輪詢狀態）
    - 避免長時間處理 bag 時，瀏覽器/反向代理/Load Balancer 連線逾時
    """

    status: Literal["pending", "running", "succeeded", "failed"] = Field(
        "pending",
        description="任務狀態：pending(未開始)/running(進行中)/succeeded(成功)/failed(失敗)。",
    )
    error: Optional[str] = Field(None, description="失敗原因（status=failed 時才會有）。")

    bag_input: str = Field(..., description="原始輸入的 bag 參數（可能是相對路徑/ID）。")
    bag_resolved_path: str = Field(..., description="resolve 後的 bag 絕對路徑（server 路徑字串）。")
    session_name: str = Field(..., description="本次提取對應的 session_name（UUID 字串）。")
    user_code: Optional[str] = Field(None, description="對應 UserProfile.user_code，未知/未綁定時為 None。")
    force: bool = Field(False, description="是否強制重跑（忽略既有結果/快取）。")
    config: Dict[str, Any] = Field(default_factory=dict, description="提取設定（原封不動存下，方便追溯）。")

    bag_hash: Optional[str] = Field(None, description="成功後填入：bag 檔內容雜湊（去重/快取用）。")
    bag_path: Optional[str] = Field(None, description="成功後填入：實際使用的 bag 路徑（server 路徑字串）。")
    npy_path: Optional[str] = Field(None, description="成功後填入：輸出的 npy 路徑（server 路徑字串）。")

    created_at: datetime = Field(default_factory=datetime.now, description="建立時間（server local time）。")
    updated_at: datetime = Field(default_factory=datetime.now, description="最後更新時間（server local time）。")
    started_at: Optional[datetime] = Field(None, description="實際開始跑任務的時間，尚未開始時為 None。")
    finished_at: Optional[datetime] = Field(None, description="任務完成時間（成功/失敗），尚未結束時為 None。")

    expires_at: datetime = Field(
        default_factory=lambda: datetime.now() + timedelta(minutes=REALSENSE_EXTRACT_JOB_RETENTION_MINUTES),
        description="TTL 到期時間（Mongo TTL 會在此時間後清理該 job）。",
    )

    class Settings:
        name = "realsense_extract_job"
        collection = "realsense_extract_job"
        indexes = [
            IndexModel([("status", ASCENDING), ("created_at", ASCENDING)], name="idx_status_created"),
            IndexModel([("session_name", ASCENDING)], name="idx_session"),
            IndexModel([("expires_at", ASCENDING)], expireAfterSeconds=0, name="expires_at_ttl"),
        ]


