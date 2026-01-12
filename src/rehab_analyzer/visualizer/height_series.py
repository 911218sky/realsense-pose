"""
高度多系列曲線繪製。

繪製關節 Y 軸高度隨時間變化的曲線。
"""
from pathlib import Path
from typing import Any

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator

from utils import add_prefix_to_filename
from ..constants import DEFAULT_SMOOTH_WINDOW_S
from .utils import VisualizerUtilsMixin


class HeightMultiSeriesPlotterMixin(VisualizerUtilsMixin):
    """
    高度多系列曲線：

    - joints: 例如 ["L_HEEL", "R_HEEL"] 或 [29, 30]
    - labels: 每條線的標籤，長度需與 joints 一致

    只畫 Y 軸高度（第 2 維）隨時間變化。
    """

    def save_y_height_diff(
        self,
        left_joint: int | str,
        right_joint: int | str,
        labels: list[str | None] = None,
        *,
        smooth_window_s: float = DEFAULT_SMOOTH_WINDOW_S,
        draw_original: bool = True,
        dpi: int = 150,
        figsize: tuple[float, float] = (11.0, 4.0),
        save_name: str | None = None,
        ylim: tuple[float, float | None] = None,
    ) -> Path:
        """
        畫出單一曲線：「左腳高度 - 右腳高度」隨時間變化。

        - 正值：左腳比右腳高
        - 負值：右腳比左腳高
        """
        t, series = self.compute_y_heigh(
            joints=[left_joint, right_joint],
            smooth_window=smooth_window_s,
        )
        if len(series) != 2:
            raise ValueError("save_y_height_diff 需要剛好兩個關節（左、右）。")

        left, right = series
        diff = left - right

        if labels is None:
            labels = [str(left_joint), str(right_joint)]
        else:
            labels = list(labels) + [None, None]
            labels = labels[:2]
            labels[0] = labels[0] or str(left_joint)
            labels[1] = labels[1] or str(right_joint)

        # 直接用公分顯示
        scale = 100.0
        left_plot = left * scale
        right_plot = right * scale
        diff_plot = diff * scale

        fig, ax = plt.subplots(figsize=figsize, dpi=dpi, layout="constrained")
        if draw_original:
            ax.plot(t, left_plot, lw=1.4, label=labels[0])
            ax.plot(t, right_plot, lw=1.4, label=labels[1])
        ax.plot(t, diff_plot, lw=1.8, label=f"{left_joint}-{right_joint} (L-R)")
        ax.axhline(0.0, color="k", lw=1.0, alpha=0.7)

        # 設定刻度
        major_step, minor_step = self._compute_tick_steps(ylim, left_plot, right_plot, diff_plot)
        ax.yaxis.set_major_locator(MultipleLocator(major_step))
        ax.yaxis.set_minor_locator(MultipleLocator(minor_step))
        ax.grid(True, which="major", alpha=0.28, linestyle="--")
        ax.grid(True, which="minor", axis="y", alpha=0.14, linestyle=":")
        ax.set_xlabel("time (s)")
        axis_label = self._axis_label_for_data_dim(1)
        ax.set_ylabel(f"{axis_label} height / diff (L-R) [cm]")

        ax.legend(loc="upper right", frameon=False)
        joints_str = f"{left_joint},{right_joint}"
        ax.set_title(f"{self.prefix or 'session'} - {axis_label} height & diff (L-R, {joints_str}) [cm]")
        self._apply_limits(ax, ylim=ylim)

        save_name_template = save_name or "y_height_diff_{left}_{right}.png"
        save_name_final = save_name_template.format(left=str(left_joint), right=str(right_joint))
        filename = add_prefix_to_filename(save_name_final, self.prefix)
        out_path = Path(self.out_dir) / filename
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(out_path))
        plt.close(fig)

        return out_path

    @staticmethod
    def _compute_tick_steps(
        ylim: tuple[float, float | None],
        left_plot: np.ndarray[Any, Any],
        right_plot: np.ndarray[Any, Any],
        diff_plot: np.ndarray[Any, Any],
    ) -> tuple[float, float]:
        """計算 Y 軸刻度步長。"""
        if ylim is not None:
            y0, y1 = float(ylim[0]), float(ylim[1])
        else:
            y0 = float(np.nanmin([np.nanmin(left_plot), np.nanmin(right_plot), np.nanmin(diff_plot)]))
            y1 = float(np.nanmax([np.nanmax(left_plot), np.nanmax(right_plot), np.nanmax(diff_plot)]))
        yr = max(1e-6, y1 - y0)

        if yr <= 150.0:
            return 10.0, 1.0
        elif yr <= 350.0:
            return 20.0, 5.0
        elif yr <= 900.0:
            return 50.0, 10.0
        else:
            return 100.0, 20.0
