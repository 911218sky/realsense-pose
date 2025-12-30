from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


# ---------- Request models ----------

class ExtractRequest(BaseModel):
    """提取請求參數。"""

    force: bool = Field(False, description="若為 True，強制重新處理即便已有結果。")
    skip_frames: int = Field(4, description="每處理一幀時跳過的帧數（降頻用）。")
    max_frames: int = Field(10800, description="最多處理的帧數上限。")
    model_complexity: int = Field(1, description="MediaPipe pose model complexity 等級。")
    min_detection_confidence: float = Field(0.5, description="偵測最小信心分數。")
    min_tracking_confidence: float = Field(0.5, description="追蹤最小信心分數。")
    calibrate_pose: bool = Field(True, description="是否執行姿勢校正。")
    y_axis_up: bool = Field(True, description="若為 True，輸出座標會把 y 軸翻轉成向上為正（更直覺好解讀）。")
    save_video: bool = Field(True, description="是否匯出帶有骨架標註的影片檔。")


# ---------- Response models ----------

class ExtractResponse(BaseModel):
    """提取結果回傳。"""

    bag_path: str = Field(..., description="原始 .bag 檔路徑。")
    npy_path: str = Field(..., description="輸出的關節序列檔路徑。")
    video_path: Optional[str] = Field(None, description="輸出的影片檔路徑（若有啟用 save_video）。")
    session_name: str = Field(..., description="此處理任務的 session 名稱。")
    bag_hash: Optional[str] = Field(None, description=".bag 內容 hash（去重用）。")
    success: bool = Field(..., description="是否提取成功。")


class ExtractJobCreatedResponse(BaseModel):
    """非同步提取：建立 job 後立刻回傳。"""

    job_id: str = Field(..., description="背景任務 ID，可用來查詢狀態。")
    status: Literal["pending", "running", "succeeded", "failed"] = Field(..., description="任務狀態。")
    created_at: datetime = Field(..., description="任務建立時間。")
    status_url: str = Field(..., description="查詢任務狀態的 URL。")


class ExtractJobStatusResponse(BaseModel):
    """非同步提取：查詢 job 狀態。"""

    job_id: str = Field(..., description="背景任務 ID。")
    status: Literal["pending", "running", "succeeded", "failed"] = Field(..., description="任務狀態。")
    created_at: datetime = Field(..., description="任務建立時間。")
    updated_at: datetime = Field(..., description="最後更新時間。")
    started_at: Optional[datetime] = Field(None, description="開始執行時間。")
    finished_at: Optional[datetime] = Field(None, description="結束時間。")
    error: Optional[str] = Field(None, description="失敗原因（若 failed）。")
    result: Optional[ExtractResponse] = Field(None, description="成功結果（若 succeeded）。")


class RealsensePoseExtractorItem(BaseModel):
    """單筆 session 紀錄。"""

    session_name: str = Field(..., description="Session 名稱。")
    npy_path: str = Field(..., description="輸出 npy 路徑。")
    video_path: Optional[str] = Field(None, description="輸出影片路徑（若有）。")
    bag_path: str = Field(..., description="來源 bag 路徑。")
    bag_hash: Optional[str] = Field(None, description="bag 內容 hash。")
    created_at: datetime = Field(..., description="建立時間。")
    updated_at: datetime = Field(..., description="更新時間。")


class RealsensePoseExtractorListResponse(BaseModel):
    """Session 列表回傳。"""

    total: int = Field(..., description="總筆數。")
    page: int = Field(..., description="當前頁碼（1-based）。")
    page_size: int = Field(..., description="每頁筆數。")
    total_pages: int = Field(..., description="總頁數。")
    items: List[RealsensePoseExtractorItem] = Field(..., description="列表項目。")


class SessionNameSuggestionResponse(BaseModel):
    """session_name 自動完成建議。"""

    items: List[str] = Field(..., description="建議的 session_name 清單。")


class DeleteSessionResponse(BaseModel):
    """刪除 session 的結果回傳。"""

    session_name: str = Field(..., description="被刪除的 session 名稱。")
    deleted_db: bool = Field(..., description="是否已刪除 DB 紀錄。")
    deleted_npy: bool = Field(..., description="是否已刪除 npy 檔案。")
    deleted_bag: bool = Field(..., description="是否已刪除 bag 檔案。")


# ---------- Bag list models ----------

class BagFileItem(BaseModel):
    """伺服器上的 bag 檔案資訊（用於列表）。"""

    bag_id: str = Field(..., description="給 API 使用的識別（通常是相對路徑，如 'subdir/1.bag'）。")
    name: str = Field(..., description="檔名（不含路徑）。")
    size_bytes: int = Field(..., description="檔案大小（bytes）。")
    modified_at: datetime = Field(..., description="最後修改時間。")


class BagFileListResponse(BaseModel):
    """伺服器 bag 檔列表回傳（分頁）。"""

    total: int = Field(..., description="總筆數。")
    page: int = Field(..., description="當前頁碼（1-based）。")
    page_size: int = Field(..., description="每頁筆數。")
    total_pages: int = Field(..., description="總頁數。")
    items: List[BagFileItem] = Field(..., description="列表項目。")