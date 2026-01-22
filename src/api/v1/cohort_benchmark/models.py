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
    dur_walking: PercentileStats = Field(..., description="總行走時間統計（秒）= dur_to_cone + dur_return")


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
    dist_walking_m: PercentileStats = Field(..., description="行走總距離統計（m）= dist_outbound_m + dist_return_m")


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
    user_percentile: int = Field(
        default=50, ge=0, le=100,
        description="使用者的第幾百分位數（預設 50，即中位數）"
    )
    cohort_percentile: int = Field(
        default=50, ge=0, le=100,
        description="要比較的族群第幾百分位數（預設 50，即中位數）"
    )


class GetBenchmarkRequest(BaseModel):
    """查詢基準值請求，用於過濾指標類別。"""
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

class MetricComparison(BaseModel):
    """單一指標比對結果（簡化版）。
    
    前端只需關注：
    - diff_pct: 正數表示比族群高，負數表示比族群低
    - is_better: 這個差異對使用者是好是壞
    """
    user_value: float = Field(..., description="使用者數值")
    cohort_value: float = Field(..., description="族群基準值")
    diff_pct: float = Field(
        ..., 
        description="差異百分比：正數=比族群高，負數=比族群低"
    )
    is_better: bool = Field(
        ..., 
        description="這個差異對使用者是否有利（考慮指標方向）"
    )
    status: Literal["worse", "similar", "better"] = Field(
        ..., description="狀態：worse=較差, similar=相近, better=較好"
    )


class LapTimeComparison(BaseModel):
    """圈數時間比對結果。"""
    dur_total: MetricComparison
    dur_stand: MetricComparison
    dur_to_cone: MetricComparison
    dur_cone_turn: MetricComparison
    dur_return: MetricComparison
    dur_turn_to_sit: MetricComparison
    dur_sit: MetricComparison
    dur_walking: MetricComparison = Field(..., description="總行走時間比對")


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
    dist_walking_m: MetricComparison = Field(..., description="行走總距離比對")


class TurnComparison(BaseModel):
    """轉向比對結果。"""
    delta_theta_cone_deg: MetricComparison
    delta_theta_chair_deg: MetricComparison


# ============================================================================
# 功能評估模型（基於 TUG 測試論文標準值）
# ============================================================================

class FunctionalMetric(BaseModel):
    """功能評估單一指標。"""
    user_value: float = Field(..., description="使用者數值")
    reference_value: float = Field(..., description="論文參考標準值（健康成人）")
    cohort_value: Optional[float] = Field(None, description="族群基準值（若有）")
    diff_from_reference_pct: float = Field(..., description="與參考值的差異百分比")
    higher_is_better: bool = Field(..., description="該指標是否越高越好")
    radar_score: float = Field(
        ..., ge=0, le=100,
        description="雷達圖分數（0-100），統一為越高越好"
    )


class EnduranceAssessment(BaseModel):
    """體能評估（Endurance）。
    
    基於論文：健康成人 6 分鐘步行距離約 239m
    指標：走向角錐時間 + 走回椅子時間
    """
    walk_to_cone_s: FunctionalMetric = Field(..., description="走向角錐時間（秒），參考值 2.264s")
    walk_back_and_sit_s: FunctionalMetric = Field(..., description="走回+轉身坐下時間（秒），參考值 2.283s")
    total_walking_s: FunctionalMetric = Field(..., description="總行走時間（秒）")


class BalanceAssessment(BaseModel):
    """平衡能力評估（Balance）。
    
    基於論文：三角錐轉身時間約 1.354 秒
    """
    cone_turn_s: FunctionalMetric = Field(..., description="三角錐轉身時間（秒），參考值 1.354s")


class MuscleEnduranceAssessment(BaseModel):
    """肌耐力評估（Muscle Endurance）。
    
    基於論文：站起時間約 0.945 秒，走回+轉身坐下約 2.283 秒
    """
    stand_up_s: FunctionalMetric = Field(..., description="站起時間（秒），參考值 0.945s")
    return_and_sit_s: FunctionalMetric = Field(..., description="走回+轉身坐下時間（秒），參考值 2.283s")


class FunctionalAssessment(BaseModel):
    """功能評估總覽。
    
    基於 TUG 測試論文的健康成人標準值進行比較。
    """
    endurance: EnduranceAssessment = Field(..., description="體能評估")
    balance: BalanceAssessment = Field(..., description="平衡能力評估")
    muscle_endurance: MuscleEnduranceAssessment = Field(..., description="肌耐力評估")


class ComparisonResult(BaseModel):
    """個人與基準比對結果。"""
    session_name: str = Field(..., description="session 名稱")
    user_code: Optional[str] = Field(None, description="使用者代碼（若 session 有綁定）")
    cohort_name: str = Field(..., description="比對的族群名稱")
    compared_at: datetime = Field(..., description="比對時間")
    lap_count: int = Field(..., ge=0, description="個人圈數")
    # 自訂百分位參數
    user_percentile: int = Field(default=50, description="使用者選擇的百分位數")
    cohort_percentile: int = Field(default=50, description="族群選擇的百分位數")
    lap_time: Optional[LapTimeComparison] = Field(None, description="圈數時間比對")
    gait: Optional[GaitComparison] = Field(None, description="步態比對")
    speed_distance: Optional[SpeedDistanceComparison] = Field(None, description="速度距離比對")
    turn: Optional[TurnComparison] = Field(None, description="轉向比對")
    # 功能評估（基於論文標準值）
    functional: Optional[FunctionalAssessment] = Field(None, description="功能評估（體能/平衡/肌耐力）")