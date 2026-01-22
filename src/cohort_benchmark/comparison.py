"""
比較服務模組。

提供個人數據與族群基準的比較功能。

指標方向定義（基於 TUG 測試和步態分析研究）：
- 時間類指標：越低越好（完成時間越短表示功能越好）
- 速度類指標：越高越好（行走速度越快表示功能越好）
- 步長類指標：越高越好（步長越長表示功能越好）
- 步頻類指標：越高越好（步頻越高表示功能越好）
- 擺動期百分比：越高越好（擺動期越長表示步態越有效率）
- 支撐期時間：越低越好（支撐期越短表示步態越有效率）
- 距離類指標：越低越好（路徑越短表示動作越有效率）
- 轉向角度：中性（取決於轉向策略）
"""
from dataclasses import dataclass
from typing import Literal

import numpy as np

from db.mongo.models import PercentileStatsEmbed


# 指標方向定義：True = 越高越好，False = 越低越好
METRIC_DIRECTION: dict[str, bool] = {
    # 時間類 - 越低越好
    "dur_total": False,
    "dur_stand": False,
    "dur_to_cone": False,
    "dur_cone_turn": False,
    "dur_return": False,
    "dur_turn_to_sit": False,
    "dur_sit": False,
    "dur_walking": False,  # 總行走時間 - 越低越好
    # 步態類
    "spm": True,              # 步頻 - 越高越好
    "mean_step_len": True,    # 步長 - 越高越好
    "l_swing_pct": True,      # 左擺動期% - 越高越好
    "r_swing_pct": True,      # 右擺動期% - 越高越好
    "l_stance_s": False,      # 左支撐期時間 - 越低越好
    "r_stance_s": False,      # 右支撐期時間 - 越低越好
    # 速度距離類
    "speed_mps": True,        # 速度 - 越高越好
    "dist_lap_path_m": False, # 總路徑距離 - 越低越好（路徑越短越有效率）
    "dist_outbound_m": False, # 去程距離 - 越低越好
    "dist_return_m": False,   # 回程距離 - 越低越好
    "dist_cone_turn_m": False,# 錐子轉身距離 - 越低越好
    "dist_walking_m": False,  # 行走總距離 - 越低越好
    # 轉向類 - 中性，但為了雷達圖統一設為越低越好（轉向角度越小越穩定）
    "delta_theta_cone_deg": False,
    "delta_theta_chair_deg": False,
}


@dataclass
class MetricComparisonResult:
    """單一指標比對結果（內部使用）。"""
    user_value: float
    cohort_value: float
    diff_pct: float
    is_better: bool
    status: Literal["worse", "similar", "better"]


def compute_diff_pct(user_val: float, cohort_val: float) -> float:
    """計算差異百分比：(user - cohort) / cohort * 100"""
    if cohort_val == 0:
        return 0.0
    return (user_val - cohort_val) / cohort_val * 100


def get_percentile_value(values: np.ndarray, percentile: int) -> float:
    """從數值陣列計算指定百分位數。"""
    if len(values) == 0:
        return 0.0
    return float(np.percentile(values, percentile))


def get_cohort_percentile_value(stats: PercentileStatsEmbed, percentile: int) -> float:
    """從族群統計中取得或插值計算指定百分位數值。"""
    known = {10: stats.p10, 25: stats.p25, 50: stats.p50, 75: stats.p75, 90: stats.p90}
    
    if percentile in known:
        return known[percentile]
    
    keys = sorted(known.keys())
    
    # 外推
    if percentile < keys[0] or percentile > keys[-1]:
        if stats.std > 0:
            z = (percentile - 50) / 34.0
            return stats.mean + z * stats.std
        return known[keys[0]] if percentile < keys[0] else known[keys[-1]]
    
    # 線性插值
    for i in range(len(keys) - 1):
        if keys[i] <= percentile <= keys[i + 1]:
            ratio = (percentile - keys[i]) / (keys[i + 1] - keys[i])
            return known[keys[i]] + ratio * (known[keys[i + 1]] - known[keys[i]])
    
    return stats.p50


def create_metric_comparison(
    user_values: np.ndarray,
    benchmark_stats: PercentileStatsEmbed,
    user_percentile: int = 50,
    cohort_percentile: int = 50,
    metric_name: str = "",
) -> MetricComparisonResult:
    """建立單一指標比對結果。

    Args:
        user_values: 使用者多圈的數值陣列
        benchmark_stats: 族群百分位數統計
        user_percentile: 使用者要比較的百分位數
        cohort_percentile: 族群要比較的百分位數
        metric_name: 指標名稱（用於判斷方向）
    
    Returns:
        MetricComparisonResult: 比對結果
        - diff_pct: 正數=比族群高，負數=比族群低
        - is_better: 這個差異對使用者是否有利
        - status: "better" / "similar" / "worse"
    """
    # 計算使用者指定百分位的數值
    user_value = get_percentile_value(user_values, user_percentile)
    
    # 取得族群指定百分位的數值
    cohort_value = get_cohort_percentile_value(benchmark_stats, cohort_percentile)
    
    # 計算差異百分比：正數=比族群高，負數=比族群低
    diff_pct = compute_diff_pct(user_value, cohort_value)
    
    # 取得指標方向（預設為越低越好）
    higher_is_better = METRIC_DIRECTION.get(metric_name, False)
    
    # 判斷這個差異對使用者是否有利
    if higher_is_better:
        is_better = diff_pct > 0
    else:
        is_better = diff_pct < 0
    
    # 判斷狀態（±10% 內視為相近）
    SIMILAR_THRESHOLD = 10.0
    if abs(diff_pct) <= SIMILAR_THRESHOLD:
        status: Literal["worse", "similar", "better"] = "similar"
    elif is_better:
        status = "better"
    else:
        status = "worse"

    return MetricComparisonResult(
        user_value=user_value,
        cohort_value=cohort_value,
        diff_pct=diff_pct,
        is_better=is_better,
        status=status,
    )
