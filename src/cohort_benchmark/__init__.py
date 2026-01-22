"""
族群基準分析核心模組。
"""

from .calculator import compute_percentiles, DEFAULT_PERCENTILES
from .comparison import (
    METRIC_DIRECTION,
    compute_diff_pct,
    get_percentile_value,
    get_cohort_percentile_value,
    create_metric_comparison,
)
from .service import CohortBenchmarkService, cohort_benchmark_service

__all__ = [
    # calculator
    "compute_percentiles",
    "DEFAULT_PERCENTILES",
    # comparison
    "METRIC_DIRECTION",
    "compute_diff_pct",
    "get_percentile_value",
    "get_cohort_percentile_value",
    "create_metric_comparison",
    # service
    "CohortBenchmarkService",
    "cohort_benchmark_service",
]
