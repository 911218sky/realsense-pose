"""
可視化模組 - 保持原有 API 兼容性。

使用延遲導入（lazy import）避免在導入時載入 matplotlib/PIL/cv2 等重型依賴。
"""
from typing import TYPE_CHECKING

__all__ = [
    # 主要入口類別
    "RehabSummaryVisualizer",
    # 核心類別
    "VisualizerCore",
    "VisualizerUtilsMixin",
    "AXIS_DISPLAY_NAMES",
    # Mixin 類別
    "StageDurationsPlotterMixin",
    "MinutelyStageDurationBarsMixin",
    "TrajectoryVideoExporterMixin",
    "SpeedHeatmapMixin",
    "StepLengthBarsMixin",
    "SwingInfoHeatmapMixin",
    "LateralOffsetPlotterMixin",
    "TimeFrequencyMixin",
    "HeightMultiSeriesPlotterMixin",
    # 工具函數
    "fmt_timestamp",
    "imread_rgb",
    "canvas_to_numpy_rgba",
]

if TYPE_CHECKING:
    from .core import VisualizerCore, AXIS_DISPLAY_NAMES
    from .utils import VisualizerUtilsMixin, fmt_timestamp, imread_rgb, canvas_to_numpy_rgba
    from .session_visualizer import RehabSummaryVisualizer
    from .stage_durations import StageDurationsPlotterMixin
    from .minutely_stats import MinutelyStageDurationBarsMixin
    from .trajectory import TrajectoryVideoExporterMixin
    from .speed_heatmap import SpeedHeatmapMixin
    from .step_length import StepLengthBarsMixin
    from .swing_info import SwingInfoHeatmapMixin
    from .lateral_offset import LateralOffsetPlotterMixin
    from .time_frequency import TimeFrequencyMixin
    from .height_series import HeightMultiSeriesPlotterMixin


def __getattr__(name: str):
    """延遲導入可視化類別和工具函數。"""
    # 主要入口類別
    if name == "RehabSummaryVisualizer":
        from .session_visualizer import RehabSummaryVisualizer
        return RehabSummaryVisualizer
    # 核心類別
    if name == "VisualizerCore":
        from .core import VisualizerCore
        return VisualizerCore
    if name == "VisualizerUtilsMixin":
        from .utils import VisualizerUtilsMixin
        return VisualizerUtilsMixin
    if name == "AXIS_DISPLAY_NAMES":
        from .core import AXIS_DISPLAY_NAMES
        return AXIS_DISPLAY_NAMES
    # Mixin 類別
    if name == "StageDurationsPlotterMixin":
        from .stage_durations import StageDurationsPlotterMixin
        return StageDurationsPlotterMixin
    if name == "MinutelyStageDurationBarsMixin":
        from .minutely_stats import MinutelyStageDurationBarsMixin
        return MinutelyStageDurationBarsMixin
    if name == "TrajectoryVideoExporterMixin":
        from .trajectory import TrajectoryVideoExporterMixin
        return TrajectoryVideoExporterMixin
    if name == "SpeedHeatmapMixin":
        from .speed_heatmap import SpeedHeatmapMixin
        return SpeedHeatmapMixin
    if name == "StepLengthBarsMixin":
        from .step_length import StepLengthBarsMixin
        return StepLengthBarsMixin
    if name == "SwingInfoHeatmapMixin":
        from .swing_info import SwingInfoHeatmapMixin
        return SwingInfoHeatmapMixin
    if name == "LateralOffsetPlotterMixin":
        from .lateral_offset import LateralOffsetPlotterMixin
        return LateralOffsetPlotterMixin
    if name == "TimeFrequencyMixin":
        from .time_frequency import TimeFrequencyMixin
        return TimeFrequencyMixin
    if name == "HeightMultiSeriesPlotterMixin":
        from .height_series import HeightMultiSeriesPlotterMixin
        return HeightMultiSeriesPlotterMixin
    # 工具函數
    if name == "fmt_timestamp":
        from .utils import fmt_timestamp
        return fmt_timestamp
    if name == "imread_rgb":
        from .utils import imread_rgb
        return imread_rgb
    if name == "canvas_to_numpy_rgba":
        from .utils import canvas_to_numpy_rgba
        return canvas_to_numpy_rgba
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")