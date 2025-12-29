"""Backward-compatible facade for rehab analyzer.

The implementation was split into smaller modules for maintainability.
"""

from .entities import (
    Lap,
    DetectLapsResult,
    OffsetFFTResult,
    FootStepCycle,
    IntervalGaitMetrics,
    GaitSummary,
)
from .data_loader import DataLoader
from .pose_processor import PoseProcessor
from .lap_detector import LapDetector
from .gait_analyzer import GaitAnalyzer
from .fft_analyzer import FftAnalyzer
from .session_analyzer import RehabilitationSessionAnalyzer

__all__ = [
    "DataLoader",
    "PoseProcessor",
    "LapDetector",
    "GaitAnalyzer",
    "FftAnalyzer",
    "RehabilitationSessionAnalyzer",
    "Lap",
    "DetectLapsResult",
    "OffsetFFTResult",
    "FootStepCycle",
    "IntervalGaitMetrics",
    "GaitSummary",
]


if __name__ == "__main__":
    from utils.timing import time_it

    npy = "./outputs/4_1_1208/4_1_1208_pose.npy"

    analyzer = RehabilitationSessionAnalyzer(npy)

    # 簡單測試：自動偵測圈數
    result = time_it(analyzer.detect_laps_auto)
    print(f"總共 {result.num_laps} 圈")
    for i, lap in enumerate(result.laps, 1):
        print(f"第 {i} 圈：{lap.dur_total:.1f} 秒  {lap.ts_start:.2f} → {lap.ts_end:.2f}")

    # 其他方法可依需求自行呼叫測試：
    # time_it(analyzer.compute_gait_summary)
    # time_it(analyzer.compute_lateral_offset_fft)
