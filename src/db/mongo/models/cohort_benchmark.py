"""族群基準值 MongoDB 文件模型。

用於儲存各族群的統計基準值，包含：
- 圈數時間基準（LapTimeBenchmark）
- 步態基準（GaitBenchmark）
- 速度距離基準（SpeedDistanceBenchmark）
- 轉向基準（TurnBenchmark）
"""

from datetime import datetime
from typing import Dict, List, Optional

from beanie import Document
from pydantic import BaseModel, Field
from pymongo import ASCENDING, IndexModel


class PercentileStatsEmbed(BaseModel):
    """百分位數統計嵌入文件。
    
    包含 P10, P25, P50(中位數), P75, P90 以及平均值、標準差、樣本數。
    """
    p10: float = Field(..., description="第 10 百分位數")
    p25: float = Field(..., description="第 25 百分位數")
    p50: float = Field(..., description="第 50 百分位數（中位數）")
    p75: float = Field(..., description="第 75 百分位數")
    p90: float = Field(..., description="第 90 百分位數")
    mean: float = Field(..., description="平均值")
    std: float = Field(..., description="標準差")
    count: int = Field(..., ge=0, description="樣本數")


class LapTimeBenchmarkEmbed(BaseModel):
    """圈數時間基準嵌入文件。
    
    包含每圈總時間及六個分段時間的統計值。
    """
    dur_total: PercentileStatsEmbed = Field(..., description="每圈總時間統計")
    dur_stand: PercentileStatsEmbed = Field(..., description="起身時間統計")
    dur_to_cone: PercentileStatsEmbed = Field(..., description="走向錐子時間統計")
    dur_cone_turn: PercentileStatsEmbed = Field(..., description="錐子轉身時間統計")
    dur_return: PercentileStatsEmbed = Field(..., description="返回時間統計")
    dur_turn_to_sit: PercentileStatsEmbed = Field(..., description="對位轉身時間統計")
    dur_sit: PercentileStatsEmbed = Field(..., description="坐下時間統計")


class GaitBenchmarkEmbed(BaseModel):
    """步態基準嵌入文件。
    
    包含步頻、步長、擺動期、支撐期等指標的統計值。
    """
    spm: PercentileStatsEmbed = Field(..., description="步頻統計（steps/min）")
    mean_step_len: PercentileStatsEmbed = Field(..., description="平均步長統計（m）")
    l_swing_pct: PercentileStatsEmbed = Field(..., description="左腳擺動期百分比統計")
    r_swing_pct: PercentileStatsEmbed = Field(..., description="右腳擺動期百分比統計")
    l_stance_s: PercentileStatsEmbed = Field(..., description="左腳支撐期時間統計（s）")
    r_stance_s: PercentileStatsEmbed = Field(..., description="右腳支撐期時間統計（s）")


class SpeedDistanceBenchmarkEmbed(BaseModel):
    """速度距離基準嵌入文件。
    
    包含行走速度與各分段距離的統計值。
    """
    speed_mps: PercentileStatsEmbed = Field(..., description="行走速度統計（m/s）")
    dist_lap_path_m: PercentileStatsEmbed = Field(..., description="每圈總距離統計（m）")
    dist_outbound_m: PercentileStatsEmbed = Field(..., description="去程距離統計（m）")
    dist_return_m: PercentileStatsEmbed = Field(..., description="回程距離統計（m）")
    dist_cone_turn_m: PercentileStatsEmbed = Field(..., description="錐子轉身路徑統計（m）")


class TurnBenchmarkEmbed(BaseModel):
    """轉向基準嵌入文件。
    
    包含轉身角度與轉向方向分布的統計值。
    """
    delta_theta_cone_deg: PercentileStatsEmbed = Field(..., description="錐子轉身角度統計（度）")
    delta_theta_chair_deg: PercentileStatsEmbed = Field(..., description="椅子轉身角度統計（度）")
    turn_cone_dir_ratio: Dict[str, float] = Field(
        default_factory=dict,
        description="錐子轉向方向分布（如 {'+1': 0.6, '-1': 0.4}）"
    )
    turn_chair_dir_ratio: Dict[str, float] = Field(
        default_factory=dict,
        description="椅子轉向方向分布（如 {'+1': 0.5, '-1': 0.5}）"
    )


class CohortBenchmark(Document):
    """族群基準值文件。
    
    儲存特定族群的統計基準值，用於後續個人數據比對。
    每個族群只會有一筆紀錄，重新計算時會更新而非新增。
    """
    cohort_name: str = Field(..., description="族群名稱（如：正常人、中風、巴金森）")
    version: int = Field(default=1, description="計算版本號，用於追蹤計算方法變更")
    calculated_at: datetime = Field(default_factory=datetime.now, description="計算完成時間")
    
    # 統計來源資訊
    user_count: int = Field(default=0, ge=0, description="參與計算的使用者數量")
    session_count: int = Field(default=0, ge=0, description="參與計算的 session 數量")
    lap_count: int = Field(default=0, ge=0, description="參與計算的圈數")
    user_codes: List[str] = Field(default_factory=list, description="參與計算的使用者代碼列表")
    
    # 基準數據（各類別可選，允許部分計算）
    lap_time: Optional[LapTimeBenchmarkEmbed] = Field(None, description="圈數時間基準")
    gait: Optional[GaitBenchmarkEmbed] = Field(None, description="步態基準")
    speed_distance: Optional[SpeedDistanceBenchmarkEmbed] = Field(None, description="速度距離基準")
    turn: Optional[TurnBenchmarkEmbed] = Field(None, description="轉向基準")
    
    # 計算狀態
    status: str = Field(
        default="completed",
        description="計算狀態：pending（等待中）、calculating（計算中）、completed（完成）、failed（失敗）"
    )
    error_message: Optional[str] = Field(None, description="錯誤訊息（當 status=failed 時）")
    
    created_at: datetime = Field(default_factory=datetime.now, description="建立時間")
    updated_at: datetime = Field(default_factory=datetime.now, description="最後更新時間")

    class Settings:
        name = "cohort_benchmark"
        collection = "cohort_benchmark"
        indexes = [
            IndexModel([("cohort_name", ASCENDING)], unique=True, name="uq_cohort_name"),
            IndexModel([("calculated_at", ASCENDING)], name="idx_calculated_at"),
            IndexModel([("status", ASCENDING)], name="idx_status"),
        ]
