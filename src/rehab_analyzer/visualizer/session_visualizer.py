"""
對外整合類：統一入口。

RehabSummaryVisualizer 繼承所有 Mixin，可呼叫所有繪圖/影片輸出方法。
"""


from .stage_durations import StageDurationsPlotterMixin
from .minutely_stats import MinutelyStageDurationBarsMixin
from .trajectory import TrajectoryVideoExporterMixin
from .speed_heatmap import SpeedHeatmapMixin
from .step_length import StepLengthBarsMixin
from .swing_info import SwingInfoHeatmapMixin
from .lateral_offset import LateralOffsetPlotterMixin
from .time_frequency import TimeFrequencyMixin
from .height_series import HeightMultiSeriesPlotterMixin
from .gait_variability import GaitVariabilityMixin
from .trend_charts import TrendChartsMixin


class RehabSummaryVisualizer(
    StageDurationsPlotterMixin,
    MinutelyStageDurationBarsMixin,
    TrajectoryVideoExporterMixin,
    SpeedHeatmapMixin,
    StepLengthBarsMixin,
    SwingInfoHeatmapMixin,
    LateralOffsetPlotterMixin,
    TimeFrequencyMixin,
    HeightMultiSeriesPlotterMixin,
    GaitVariabilityMixin,
    TrendChartsMixin,
):
    """
    對外使用的入口類別：

    - 繼承所有 Mixin，可呼叫所有繪圖 / 影片輸出方法
    - 建構子與 VisualizerCore 相同
    """

    def __init__(
        self,
        npy_path: str,
        out_dir: str,
        prefix: str | None = None,
        axis_convention: str = "standard",
    ) -> None:
        super().__init__(npy_path, out_dir, prefix, axis_convention=axis_convention)