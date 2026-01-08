"""
每分鐘步頻與步長柱狀圖。

上圖為 cadence (spm)，下圖為 mean step length (m)。
"""
from pathlib import Path
from typing import Optional, Tuple, Callable

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


class StepLengthBarsMixin(VisualizerUtilsMixin):
    """
    每分鐘步頻與步長：

    - 上圖：cadence (spm, steps/min)
    - 下圖：mean step length (m)

    資料來源：compute_gait_summary().per_interval
    """

    def save_minutely_cadence_step_length_bars(
        self,
        projection: str = DEFAULT_PROJECTION,
        smooth_window_s: float = DEFAULT_SMOOTH_WINDOW_S,
        flat_frac: float = DEFAULT_FLAT_FRAC,
        min_v_abs: float = DEFAULT_MIN_V_ABS,
        *,
        max_minutes: Optional[int] = None,
        dpi: int = 170,
        figsize_per_minute: float = 1.0,
        row_height: float = 3.2,
        bar_width: float = 0.28,
        capsize: float = 3.0,
        save_name: Optional[str] = None,
        spm_ylim: Optional[Tuple[float, float]] = None,
        steplen_ylim: Optional[Tuple[float, float]] = None,
    ) -> Path:
        """
        產生單張圖（上：步頻 spm、下：步長 m），每分鐘一根柱。

        使用 compute_gait_summary().per_interval 的彙整結果。
        """
        summary = self.compute_gait_summary(
            smooth_window_s=smooth_window_s,
            projection=projection,
            flat_frac=flat_frac,
            min_v_abs=min_v_abs,
        )
        per_interval = summary.per_interval or []
        if not per_interval:
            raise ValueError("沒有每分鐘區間可視覺化（per_interval 為空）。")

        if max_minutes is not None:
            per_interval = per_interval[: max(1, int(max_minutes))]

        M = len(per_interval)
        minutes = np.arange(1, M + 1, dtype=int)

        mu_spm = np.array([float(interval.spm) for interval in per_interval], dtype=float)
        mu_len = np.array([float(interval.mean_step_len_m) for interval in per_interval], dtype=float)
        n_spm = np.array([int(interval.left_step_count + interval.right_step_count) for interval in per_interval], dtype=int)

        color_bar = "#2563eb"
        fig_width = max(7.5, float(M) * float(figsize_per_minute))
        fig_height = row_height * 2.0

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(fig_width, fig_height), dpi=dpi, sharex=True)

        x = minutes.astype(float)

        # 上圖：步頻
        bars_spm = ax1.bar(x, mu_spm, width=bar_width, capsize=capsize, color=color_bar)
        ax1.set_title("Cadence (SPM)", pad=8)
        ax1.set_ylabel("Steps/min")
        ax1.grid(True, axis="y", linestyle="--", alpha=0.25)
        for side in ("top", "right"):
            ax1.spines[side].set_visible(False)
        self._apply_limits(ax1, ylim=spm_ylim)

        # 下圖：步長
        bars_len = ax2.bar(x, mu_len, width=bar_width, capsize=capsize, color=color_bar)
        ax2.set_title("Step length (m)", pad=8)
        ax2.set_ylabel("Meters")
        ax2.grid(True, axis="y", linestyle="--", alpha=0.25)
        for side in ("top", "right"):
            ax2.spines[side].set_visible(False)
        self._apply_limits(ax2, ylim=steplen_ylim)

        ax2.set_xlabel("Minute (from start)")
        ax2.set_xticks(x)
        ax2.set_xticklabels([f"{m}\n(n={int(n)})" for m, n in zip(minutes, n_spm)])

        self._annotate_bars(ax1, bars_spm, mu_spm, fmt=lambda v: f"{v:.1f}")
        self._annotate_bars(ax2, bars_len, mu_len, fmt=lambda v: f"{v:.2f} m")

        fig.suptitle(f"{self.prefix} - Per-minute cadence & step length", y=0.995)

        filename = add_prefix_to_filename(save_name or "minutely_cadence_step_length_bars.png", self.prefix)
        save_path = Path(self.out_dir) / filename
        save_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(save_path))
        plt.close(fig)

        return save_path

    @staticmethod
    def _annotate_bars(
        axis: plt.Axes,
        bar_container,
        values: np.ndarray,
        fmt: Callable[[float], str],
    ) -> None:
        """在柱頂標註數值。"""
        if not np.isfinite(values).any():
            return

        ymax = float(np.nanmax(values))
        ypad = 0.02 * ymax if np.isfinite(ymax) and ymax > 0 else 0.05

        for rect, value in zip(bar_container, values):
            if not np.isfinite(value):
                continue
            top = float(value)
            axis.text(
                rect.get_x() + rect.get_width() / 2.0,
                top + ypad,
                fmt(float(value)),
                ha="center",
                va="bottom",
                fontsize=9,
                color="#222",
            )
