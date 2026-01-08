"""
每分鐘區間的三段分組柱狀圖。

以每圈開始時間所屬的分鐘為分箱，統計去程/迴轉/回程的平均耗時。
"""
from pathlib import Path
from typing import Optional, Tuple, List, Callable

import numpy as np
import matplotlib.pyplot as plt

from utils import add_prefix_to_filename
from ..constants import (
    DEFAULT_PROJECTION,
    DEFAULT_SMOOTH_WINDOW_S,
    DEFAULT_FLAT_FRAC,
    DEFAULT_MIN_V_ABS,
)
from .utils import VisualizerUtilsMixin


class MinutelyStageDurationBarsMixin(VisualizerUtilsMixin):
    """
    每分鐘區間的三段分組柱狀圖：

    以每圈開始時間所屬的分鐘 (相對第一圈) 為分箱，統計：
    - Walk to cone
    - Turn at cone
    - Walk back

    每分鐘的柱子高度 = 該分鐘內圈數的「平均耗時」。
    """

    def save_minutely_stage_duration_bars(
        self,
        projection: str = DEFAULT_PROJECTION,
        smooth_window_s: float = DEFAULT_SMOOTH_WINDOW_S,
        flat_frac: float = DEFAULT_FLAT_FRAC,
        min_v_abs: float = DEFAULT_MIN_V_ABS,
        *,
        max_minutes: Optional[int] = None,
        dpi: int = 170,
        figsize_per_minute: float = 0.75,
        bar_width: float = 0.22,
        group_gap: float = 0.06,
        save_name: Optional[str] = None,
        ylim: Optional[Tuple[float, float]] = None,
    ) -> Path:
        """
        以每分鐘為單位繪製：
        - Walk to cone
        - Turn at cone
        - Walk back

        這三個階段的平均耗時柱狀圖。
        """
        det = self.detect_laps_auto(
            projection=projection,
            smooth_window_s=smooth_window_s,
            flat_frac=flat_frac,
            min_v_abs=min_v_abs,
        )
        laps = det.laps
        if not laps:
            raise ValueError("沒有圈數可視覺化（laps 為空）。")

        # 第一圈開始時間作為時間零點
        t0 = float(laps[0].ts_start)
        lap_starts = np.array([lap.ts_start for lap in laps], dtype=float)

        # 每圈所屬第幾分鐘（相對第一圈）
        minute_idx = np.floor((lap_starts - t0) / 60.0).astype(int)
        minute_idx = np.maximum(minute_idx, 0)

        # 計算總分鐘數（包含最後一圈結束時間）
        last_t = float(laps[-1].ts_end)
        total_minutes = int(np.floor((last_t - t0) / 60.0)) + 1

        if max_minutes is not None:
            total_minutes = max(1, min(int(max_minutes), total_minutes))

        M = total_minutes
        minutes = np.arange(M, dtype=int)

        # 每圈三個階段的耗時（負值轉成 0）
        v_to = np.array([max(0.0, float(lap.dur_to_cone)) for lap in laps], dtype=float)
        v_turn = np.array([max(0.0, float(lap.dur_cone_turn)) for lap in laps], dtype=float)
        v_ret = np.array([max(0.0, float(lap.dur_return)) for lap in laps], dtype=float)

        # 依分鐘分桶
        bins = self._bin_by_minute(minute_idx, M, v_to, v_turn, v_ret)

        def mean_or_nan(values: List[float]) -> float:
            if not values:
                return float("nan")
            return float(np.mean(np.asarray(values, dtype=float)))

        means_to = np.array([mean_or_nan(bins["to"][m]) for m in minutes], dtype=float)
        means_turn = np.array([mean_or_nan(bins["turn"][m]) for m in minutes], dtype=float)
        means_ret = np.array([mean_or_nan(bins["ret"][m]) for m in minutes], dtype=float)

        # 每分鐘的樣本數
        counts = np.array([
            max(len(bins["to"][m]), len(bins["turn"][m]), len(bins["ret"][m]))
            for m in minutes
        ], dtype=int)

        # 繪圖
        fig, ax = self._create_minutely_figure(M, figsize_per_minute, dpi)
        bars_to, bars_turn, bars_ret = self._draw_minutely_bars(
            ax, minutes, means_to, means_turn, means_ret, bar_width, group_gap
        )

        self._style_minutely_axes(ax, minutes, counts, ylim)
        self._annotate_minutely_bars(ax, bars_to, bars_turn, bars_ret, means_to, means_turn, means_ret)

        ax.set_title(f"{self.prefix} - Per-minute stage durations")
        ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5), frameon=False)

        filename = add_prefix_to_filename(save_name or "minutely_stage_duration_bars.png", self.prefix)
        save_path = Path(self.out_dir) / filename
        save_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(save_path))
        plt.close(fig)

        return save_path

    def _bin_by_minute(
        self,
        minute_idx: np.ndarray,
        M: int,
        v_to: np.ndarray,
        v_turn: np.ndarray,
        v_ret: np.ndarray,
    ) -> dict:
        """依分鐘分桶。"""
        bins = {
            "to": [[] for _ in range(M)],
            "turn": [[] for _ in range(M)],
            "ret": [[] for _ in range(M)],
        }
        for idx, minute in enumerate(minute_idx):
            if 0 <= minute < M:
                if v_to[idx] > 0.0:
                    bins["to"][minute].append(float(v_to[idx]))
                if v_turn[idx] > 0.0:
                    bins["turn"][minute].append(float(v_turn[idx]))
                if v_ret[idx] > 0.0:
                    bins["ret"][minute].append(float(v_ret[idx]))
        return bins

    def _create_minutely_figure(
        self, M: int, figsize_per_minute: float, dpi: int
    ) -> Tuple[plt.Figure, plt.Axes]:
        """創建每分鐘統計圖的 Figure。"""
        fig_width = max(7.0, float(M) * float(figsize_per_minute))
        fig_height = 4.2
        return plt.subplots(figsize=(fig_width, fig_height), dpi=dpi, layout="constrained")

    def _draw_minutely_bars(
        self,
        ax: plt.Axes,
        minutes: np.ndarray,
        means_to: np.ndarray,
        means_turn: np.ndarray,
        means_ret: np.ndarray,
        bar_width: float,
        group_gap: float,
    ) -> Tuple:
        """繪製三組柱狀圖。"""
        color_to = "#F58518"
        color_turn = "#E45756"
        color_ret = "#72B7B2"

        x = minutes.astype(float)
        offset = bar_width + group_gap / 2.0

        bars_to = ax.bar(x - offset, means_to, width=bar_width, label="Walk to cone", color=color_to)
        bars_turn = ax.bar(x, means_turn, width=bar_width, label="Turn at cone", color=color_turn)
        bars_ret = ax.bar(x + offset, means_ret, width=bar_width, label="Walk back", color=color_ret)

        return bars_to, bars_turn, bars_ret

    def _style_minutely_axes(
        self,
        ax: plt.Axes,
        minutes: np.ndarray,
        counts: np.ndarray,
        ylim: Optional[Tuple[float, float]],
    ) -> None:
        """設定軸樣式。"""
        ax.grid(True, axis="y", linestyle="--", alpha=0.25)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)

        ax.set_ylabel("Duration (s)")
        ax.set_xlabel("Minute (from first lap start)")
        ax.set_xticks(minutes.astype(float))
        ax.set_xticklabels([f"{m + 1}\n(n={int(n)})" for m, n in zip(minutes, counts)])

        self._apply_limits(ax, ylim=ylim)

    def _annotate_minutely_bars(
        self,
        ax: plt.Axes,
        bars_to,
        bars_turn,
        bars_ret,
        means_to: np.ndarray,
        means_turn: np.ndarray,
        means_ret: np.ndarray,
    ) -> None:
        """在柱子上方標示數值。"""
        def annotate_bars(
            axis: plt.Axes,
            bar_container,
            values: np.ndarray,
            fmt: Callable[[float], str],
        ) -> None:
            if not np.isfinite(values).any():
                return

            ymax = float(np.nanmax(values))
            ypad = 0.02 * ymax if np.isfinite(ymax) and ymax > 0 else 0.05

            for rect, value in zip(bar_container, values):
                if not np.isfinite(value):
                    continue

                axis.text(
                    rect.get_x() + rect.get_width() / 2.0,
                    float(value) + ypad,
                    fmt(float(value)),
                    ha="center",
                    va="bottom",
                    fontsize=9,
                    color="#222",
                )

        fmt = lambda v: f"{v:.2f}s"
        annotate_bars(ax, bars_to, means_to, fmt)
        annotate_bars(ax, bars_turn, means_turn, fmt)
        annotate_bars(ax, bars_ret, means_ret, fmt)
