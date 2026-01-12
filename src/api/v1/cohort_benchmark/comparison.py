"""
比較服務模組。

提供個人數據與族群基準的比較功能。
"""
from typing import Literal

import numpy as np

from db.mongo.models import PercentileStatsEmbed

from .calculator import compute_percentiles
from .models import MetricComparison, PercentileDiff


def compute_percentile_position(
    value: float,
    stats: PercentileStatsEmbed,
) -> float:
    """計算數值在百分位數中的位置。

    使用線性插值法估算個人數值在族群分布中的百分位位置。
    這可以直觀地了解個人表現相對於族群的排名。

    計算方法：
    1. 建立已知的百分位數對照表（P10, P25, P50, P75, P90）
    2. 找出數值落在哪兩個百分位數之間
    3. 使用線性插值計算精確的百分位位置
    4. 若超出 P10-P90 範圍，使用常態分布 Z-score 外推

    Args:
        value: 個人數值
        stats: 族群百分位數統計

    Returns:
        百分位位置（0-100），數值越高表示在族群中排名越高

    Note:
        - 若族群無資料（count=0），回傳 50.0（中位數位置）
        - 若數值超出 P10-P90 範圍，使用 Z-score 外推至 0-100
    """
    if stats.count == 0:
        return 50.0

    percentiles = [10, 25, 50, 75, 90]
    values = [stats.p10, stats.p25, stats.p50, stats.p75, stats.p90]

    # 處理邊界情況：數值低於 P10
    if value < values[0]:
        if stats.std > 0:
            z = (value - stats.mean) / stats.std
            percentile = 50.0 + z * 34.0
            return max(0.1, min(percentile, 10.0))
        return float(percentiles[0])

    # 處理邊界情況：數值高於 P90
    if value > values[-1]:
        if stats.std > 0:
            z = (value - stats.mean) / stats.std
            percentile = 50.0 + z * 34.0
            return max(90.0, min(percentile, 99.9))
        return float(percentiles[-1])

    # 線性插值
    for i in range(len(values) - 1):
        if values[i] <= value <= values[i + 1]:
            if values[i + 1] == values[i]:
                return float(percentiles[i])
            ratio = (value - values[i]) / (values[i + 1] - values[i])
            return float(percentiles[i] + ratio * (percentiles[i + 1] - percentiles[i]))

    return 50.0


def compute_diff_pct(user_val: float, benchmark_val: float) -> float:
    """計算差異百分比。

    公式：(user - benchmark) / benchmark * 100
    正值表示使用者高於族群，負值表示低於族群。

    Args:
        user_val: 使用者數值
        benchmark_val: 族群基準數值

    Returns:
        差異百分比，benchmark_val 為 0 時回傳 0.0
    """
    if benchmark_val == 0:
        return 0.0
    return (user_val - benchmark_val) / benchmark_val * 100


def create_metric_comparison(
    user_values: np.ndarray,
    benchmark_stats: PercentileStatsEmbed,
) -> MetricComparison:
    """建立單一指標比對結果。

    將個人多圈數值計算百分位統計，與族群統計進行比對。
    計算各百分位的差異百分比和在族群中的百分位位置。

    Args:
        user_values: 個人多圈的數值陣列
        benchmark_stats: 族群百分位數統計

    Returns:
        MetricComparison: 包含完整比對資訊的結果物件
    """
    user_stats = compute_percentiles(user_values)

    # 計算各百分位在族群中的位置
    p10_pos = compute_percentile_position(user_stats.p10, benchmark_stats)
    p25_pos = compute_percentile_position(user_stats.p25, benchmark_stats)
    p50_pos = compute_percentile_position(user_stats.p50, benchmark_stats)
    p75_pos = compute_percentile_position(user_stats.p75, benchmark_stats)
    p90_pos = compute_percentile_position(user_stats.p90, benchmark_stats)
    mean_pos = compute_percentile_position(user_stats.mean, benchmark_stats)

    # 判斷個人 P50 是否在族群正常範圍內（P25-P75）
    in_normal = benchmark_stats.p25 <= user_stats.p50 <= benchmark_stats.p75

    # 判定狀態
    if user_stats.p50 < benchmark_stats.p25:
        status: Literal["below_normal", "normal", "above_normal"] = "below_normal"
    elif user_stats.p50 > benchmark_stats.p75:
        status = "above_normal"
    else:
        status = "normal"

    # 計算各百分位的差異百分比
    diff = PercentileDiff(
        p10_diff_pct=compute_diff_pct(user_stats.p10, benchmark_stats.p10),
        p25_diff_pct=compute_diff_pct(user_stats.p25, benchmark_stats.p25),
        p50_diff_pct=compute_diff_pct(user_stats.p50, benchmark_stats.p50),
        p75_diff_pct=compute_diff_pct(user_stats.p75, benchmark_stats.p75),
        p90_diff_pct=compute_diff_pct(user_stats.p90, benchmark_stats.p90),
        mean_diff_pct=compute_diff_pct(user_stats.mean, benchmark_stats.mean),
        p10_percentile_position=p10_pos,
        p25_percentile_position=p25_pos,
        p50_percentile_position=p50_pos,
        p75_percentile_position=p75_pos,
        p90_percentile_position=p90_pos,
        mean_percentile_position=mean_pos,
    )

    return MetricComparison(
        user_p10=user_stats.p10,
        user_p25=user_stats.p25,
        user_p50=user_stats.p50,
        user_p75=user_stats.p75,
        user_p90=user_stats.p90,
        user_mean=user_stats.mean,
        user_count=user_stats.count,
        benchmark_p10=benchmark_stats.p10,
        benchmark_p25=benchmark_stats.p25,
        benchmark_p50=benchmark_stats.p50,
        benchmark_p75=benchmark_stats.p75,
        benchmark_p90=benchmark_stats.p90,
        benchmark_mean=benchmark_stats.mean,
        benchmark_count=benchmark_stats.count,
        percentile_position=p50_pos,
        in_normal_range=in_normal,
        status=status,
        diff=diff,
    )
