"""
百分位數計算模組。

提供百分位數統計計算功能，是基準值計算的核心。
"""
from typing import List, Optional

import numpy as np

from db.mongo.models import PercentileStatsEmbed

# 預設百分位數：P10（低於90%人）、P25（第一四分位）、P50（中位數）、
# P75（第三四分位）、P90（高於90%人）
DEFAULT_PERCENTILES = [10, 25, 50, 75, 90]


def compute_percentiles(
    values: np.ndarray,
    percentiles: Optional[List[int]] = None,
) -> PercentileStatsEmbed:
    """計算百分位數統計。

    此方法是基準值計算的核心，將一組數值轉換為百分位數統計資料。
    百分位數可用於了解數值在整體分布中的相對位置。

    計算流程：
    1. 將輸入轉換為 NumPy 陣列
    2. 過濾掉無效值（NaN、Inf）
    3. 使用 np.percentile 計算各百分位數
    4. 同時計算平均值和標準差作為輔助統計量

    Args:
        values: 數值陣列，可以是 list 或 np.ndarray
        percentiles: 要計算的百分位數列表，預設為 [10, 25, 50, 75, 90]

    Returns:
        PercentileStatsEmbed: 包含以下欄位的嵌入文件
            - p10, p25, p50, p75, p90: 各百分位數值
            - mean: 平均值
            - std: 標準差
            - count: 有效樣本數

    Note:
        若輸入為空或全為無效值，回傳全零的統計結果，count=0
    """
    if percentiles is None:
        percentiles = DEFAULT_PERCENTILES
    
    if len(percentiles) != 5:
        raise ValueError("percentiles must contain exactly 5 values")

    values = np.asarray(values, dtype=float)
    valid = values[np.isfinite(values)]

    if valid.size == 0:
        return PercentileStatsEmbed(
            p10=0.0, p25=0.0, p50=0.0, p75=0.0, p90=0.0,
            mean=0.0, std=0.0, count=0
        )

    pcts = np.percentile(valid, percentiles)

    return PercentileStatsEmbed(
        p10=float(pcts[0]),
        p25=float(pcts[1]),
        p50=float(pcts[2]),
        p75=float(pcts[3]),
        p90=float(pcts[4]),
        mean=float(np.mean(valid)),
        std=float(np.std(valid)),
        count=int(valid.size),
    )
