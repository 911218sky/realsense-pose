"""族群基準分析 API 的 Pydantic 請求/回應模型。"""

from datetime import datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# ============================================================================
# 統計結構模型
# ============================================================================

class PercentileStats(BaseModel):
    """百分位數統計結構。"""
    p10: float = Field(..., description="第 10 百分位數")
    p25: float = Field(..., description="第 25 百分位數")
    p50: float = Field(..., description="第 50 百分位數（中位數）")
    p75: float = Field(..., description="第 75 百分位數")
    p90: float = Field(..., description="第 90 百分位數")
    mean: float = Field(..., description="平均值")
    std: float = Field(..., description="標準差")
    count: int = Field(..., ge=0, description="樣本數")


class LapTimeBenchmark(BaseModel):
    """圈數時間基準回應模型。"""
    dur_total: PercentileStats = Field(..., description="每圈總時間統計")
    dur_stand: PercentileStats = Field(..., description="起身時間統計")
    dur_to_cone: PercentileStats = Field(..., description="走向錐子時間統計")
    dur_cone_turn: PercentileStats = Field(..., description="錐子轉身時間統計")
    dur_return: PercentileStats = Field(..., description="返回時間統計")
    dur_turn_to_sit: PercentileStats = Field(..., description="對位轉身時間統計")
    dur_sit: PercentileStats = Field(..., description="坐下時間統計")


class GaitBenchmark(BaseModel):
    """步態基準回應模型。"""
    spm: PercentileStats = Field(..., description="步頻統計（steps/min）")
    mean_step_len: PercentileStats = Field(..., description="平均步長統計（m）")
    l_swing_pct: PercentileStats = Field(..., description="左腳擺動期百分比統計")
    r_swing_pct: PercentileStats = Field(..., description="右腳擺動期百分比統計")
    l_stance_s: PercentileStats = Field(..., description="左腳支撐期時間統計（s）")
    r_stance_s: PercentileStats = Field(..., description="右腳支撐期時間統計（s）")


class SpeedDistanceBenchmark(BaseModel):
    """速度距離基準回應模型。"""
    speed_mps: PercentileStats = Field(..., description="行走速度統計（m/s）")
    dist_lap_path_m: PercentileStats = Field(..., description="每圈總距離統計（m）")
    dist_outbound_m: PercentileStats = Field(..., description="去程距離統計（m）")
    dist_return_m: PercentileStats = Field(..., description="回程距離統計（m）")
    dist_cone_turn_m: PercentileStats = Field(..., description="錐子轉身路徑統計（m）")


class TurnBenchmark(BaseModel):
    """轉向基準回應模型。"""
    delta_theta_cone_deg: PercentileStats = Field(..., description="錐子轉身角度統計（度）")
    delta_theta_chair_deg: PercentileStats = Field(..., description="椅子轉身角度統計（度）")
    turn_cone_dir_ratio: Dict[str, float] = Field(..., description="錐子轉向方向分布")
    turn_chair_dir_ratio: Dict[str, float] = Field(..., description="椅子轉向方向分布")


# ============================================================================
# 請求模型
# ============================================================================

class CohortUsersRequest(BaseModel):
    """查詢族群使用者請求。"""
    cohort_names: List[str] = Field(..., min_length=1, description="族群名稱列表")
    intersection: bool = Field(
        default=False,
        description="是否取交集（True=同時屬於所有族群，False=屬於任一族群）"
    )


class CalculateBenchmarkRequest(BaseModel):
    """計算基準值請求。"""
    cohort_name: str = Field(..., min_length=1, description="族群名稱")
    force_recalculate: bool = Field(
        default=False,
        description="是否強制重新計算（即使已有基準值）"
    )


class CompareRequest(BaseModel):
    """個人與基準比對請求。"""
    session_name: str = Field(..., min_length=1, description="session 名稱")
    cohort_name: str = Field(..., min_length=1, description="要比對的族群名稱")


class GetBenchmarkRequest(BaseModel):
    """查詢基準值請求（用於過濾指標類別）。"""
    categories: Optional[List[Literal["lap_time", "gait", "speed_distance", "turn"]]] = Field(
        None,
        description="要回傳的指標類別（可選，預設回傳全部）"
    )


# ============================================================================
# 回應模型
# ============================================================================

class CohortUserInfo(BaseModel):
    """族群使用者資訊。"""
    user_code: str = Field(..., description="使用者代碼")
    name: str = Field(..., description="使用者名稱")
    cohort: List[str] = Field(..., description="所屬族群列表")


class CohortUsersResponse(BaseModel):
    """查詢族群使用者回應。"""
    cohort_names: List[str] = Field(..., description="查詢的族群名稱")
    intersection: bool = Field(..., description="是否為交集查詢")
    user_codes: List[str] = Field(..., description="使用者代碼列表")
    count: int = Field(..., ge=0, description="使用者數量")


class BenchmarkResponse(BaseModel):
    """族群基準值回應。"""
    cohort_name: str = Field(..., description="族群名稱")
    calculated_at: datetime = Field(..., description="計算時間")
    version: int = Field(..., description="版本號")
    user_count: int = Field(..., ge=0, description="參與計算的使用者數量")
    session_count: int = Field(..., ge=0, description="參與計算的 session 數量")
    lap_count: int = Field(..., ge=0, description="參與計算的圈數")
    lap_time: Optional[LapTimeBenchmark] = Field(None, description="圈數時間基準")
    gait: Optional[GaitBenchmark] = Field(None, description="步態基準")
    speed_distance: Optional[SpeedDistanceBenchmark] = Field(None, description="速度距離基準")
    turn: Optional[TurnBenchmark] = Field(None, description="轉向基準")


class CohortListItem(BaseModel):
    """族群列表項目。"""
    cohort_name: str = Field(..., description="族群名稱")
    calculated_at: Optional[datetime] = Field(None, description="計算時間")
    user_count: int = Field(default=0, ge=0, description="使用者數量")
    session_count: int = Field(default=0, ge=0, description="session 數量")
    lap_count: int = Field(default=0, ge=0, description="圈數")
    version: int = Field(default=1, ge=1, description="版本號")


class CohortListResponse(BaseModel):
    """族群列表回應。"""
    cohorts: List[CohortListItem] = Field(..., description="已計算基準值的族群列表")
    count: int = Field(..., ge=0, description="族群數量")


class CalculateStatusResponse(BaseModel):
    """計算狀態回應。"""
    cohort_name: str = Field(..., description="族群名稱")
    status: Literal["pending", "calculating", "completed", "failed"] = Field(
        ..., description="計算狀態"
    )
    message: Optional[str] = Field(None, description="狀態訊息")


# ============================================================================
# 比對結果模型
# ============================================================================

class PercentileDiff(BaseModel):
    """各百分位的差異比較。
    
    diff_pct 計算公式：(user - benchmark) / benchmark * 100
    正值表示使用者高於族群，負值表示低於族群。
    
    percentile_position 表示該數值在族群中的百分位位置（0-100）。
    """
    p10_diff_pct: float = Field(..., description="P10 差異百分比")
    p25_diff_pct: float = Field(..., description="P25 差異百分比")
    p50_diff_pct: float = Field(..., description="P50 差異百分比（中位數比較）")
    p75_diff_pct: float = Field(..., description="P75 差異百分比")
    p90_diff_pct: float = Field(..., description="P90 差異百分比")
    mean_diff_pct: float = Field(..., description="平均值差異百分比")
    p10_percentile_position: float = Field(..., ge=0, le=100, description="使用者 P10 在族群中的百分位位置")
    p25_percentile_position: float = Field(..., ge=0, le=100, description="使用者 P25 在族群中的百分位位置")
    p50_percentile_position: float = Field(..., ge=0, le=100, description="使用者 P50 在族群中的百分位位置")
    p75_percentile_position: float = Field(..., ge=0, le=100, description="使用者 P75 在族群中的百分位位置")
    p90_percentile_position: float = Field(..., ge=0, le=100, description="使用者 P90 在族群中的百分位位置")
    mean_percentile_position: float = Field(..., ge=0, le=100, description="使用者平均值在族群中的百分位位置")


class MetricComparison(BaseModel):
    """單一指標比對結果。"""
    user_p10: float = Field(..., description="個人 P10")
    user_p25: float = Field(..., description="個人 P25")
    user_p50: float = Field(..., description="個人 P50（中位數）")
    user_p75: float = Field(..., description="個人 P75")
    user_p90: float = Field(..., description="個人 P90")
    user_mean: float = Field(..., description="個人平均值")
    user_count: int = Field(..., ge=0, description="個人樣本數（圈數）")
    benchmark_p10: float = Field(..., description="族群 P10")
    benchmark_p25: float = Field(..., description="族群 P25")
    benchmark_p50: float = Field(..., description="族群 P50（中位數）")
    benchmark_p75: float = Field(..., description="族群 P75")
    benchmark_p90: float = Field(..., description="族群 P90")
    benchmark_mean: float = Field(..., description="族群平均值")
    benchmark_count: int = Field(..., ge=0, description="族群樣本數")
    percentile_position: float = Field(
        ..., ge=0, le=100, description="個人 P50 在族群中的百分位位置（0-100）"
    )
    in_normal_range: bool = Field(..., description="個人 P50 是否在族群正常範圍（P25-P75）內")
    status: Literal["below_normal", "normal", "above_normal"] = Field(
        ..., description="狀態：低於正常、正常、高於正常"
    )
    diff: PercentileDiff = Field(..., description="各百分位的差異百分比")


class LapTimeComparison(BaseModel):
    """圈數時間比對結果。"""
    dur_total: MetricComparison
    dur_stand: MetricComparison
    dur_to_cone: MetricComparison
    dur_cone_turn: MetricComparison
    dur_return: MetricComparison
    dur_turn_to_sit: MetricComparison
    dur_sit: MetricComparison


class GaitComparison(BaseModel):
    """步態比對結果。"""
    spm: MetricComparison
    mean_step_len: MetricComparison
    l_swing_pct: MetricComparison
    r_swing_pct: MetricComparison
    l_stance_s: MetricComparison
    r_stance_s: MetricComparison


class SpeedDistanceComparison(BaseModel):
    """速度距離比對結果。"""
    speed_mps: MetricComparison
    dist_lap_path_m: MetricComparison
    dist_outbound_m: MetricComparison
    dist_return_m: MetricComparison
    dist_cone_turn_m: MetricComparison


class TurnComparison(BaseModel):
    """轉向比對結果。"""
    delta_theta_cone_deg: MetricComparison
    delta_theta_chair_deg: MetricComparison


class ComparisonResult(BaseModel):
    """個人與基準比對結果。"""
    session_name: str = Field(..., description="session 名稱")
    user_code: Optional[str] = Field(None, description="使用者代碼（若 session 有綁定）")
    cohort_name: str = Field(..., description="比對的族群名稱")
    compared_at: datetime = Field(..., description="比對時間")
    lap_count: int = Field(..., ge=0, description="個人圈數")
    lap_time: Optional[LapTimeComparison] = Field(None, description="圈數時間比對")
    gait: Optional[GaitComparison] = Field(None, description="步態比對")
    speed_distance: Optional[SpeedDistanceComparison] = Field(None, description="速度距離比對")
    turn: Optional[TurnComparison] = Field(None, description="轉向比對")