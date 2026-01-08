"""
擺動資訊熱力圖與柱狀圖。

包含 swing% 熱力圖和 stance/swing 時間柱狀圖。
"""
from pathlib import Path
from typing import Optional, Tuple

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


class SwingInfoHeatmapMixin(VisualizerUtilsMixin):
    """
    擺動百分比與秒數（每分鐘區間）的可視化：

    - 熱力圖：左/右腳 swing% 與秒數文字標註
    - 柱狀圖：左/右腳 stance / swing 時間
    """

    def save_swing_info_heatmap(
        self,
        projection: str = DEFAULT_PROJECTION,
        smooth_window_s: float = DEFAULT_SMOOTH_WINDOW_S,
        flat_frac: float = DEFAULT_FLAT_FRAC,
        min_v_abs: float = DEFAULT_MIN_V_ABS,
        *,
        dpi: int = 150,
        figsize_per_col: float = 0.9,
        save_name: Optional[str] = None,
        vmin_pct: Optional[float] = None,
        vmax_pct: Optional[float] = None,
    ) -> Path:
        """
        使用 compute_gait_summary().per_interval 製作 swing% 熱力圖，
        每格同時顯示 swing% 與 swing 秒數。
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

        L = len(per_interval)

        H_pct = np.full((2, L), np.nan, dtype=float)
        H_sec = np.full((2, L), np.nan, dtype=float)

        for j, interval in enumerate(per_interval):
            H_pct[0, j] = interval.l_swing_pct_mean
            H_pct[1, j] = interval.r_swing_pct_mean
            H_sec[0, j] = interval.l_swing_s_mean
            H_sec[1, j] = interval.r_swing_s_mean

        fig_width = max(6.0, L * figsize_per_col + 2.0)
        fig_height = 4.0
        fig, ax = plt.subplots(figsize=(fig_width, fig_height), dpi=dpi, layout="constrained")

        image = ax.imshow(H_pct, aspect="auto", vmin=vmin_pct, vmax=vmax_pct)
        ax.set_yticks([0, 1])
        ax.set_yticklabels(["Left", "Right"])

        xticklabels = [f"Min {k}" for k in range(L)]
        ax.set_xticks(np.arange(L))
        ax.set_xticklabels(xticklabels)

        ax.set_xticks(np.arange(-0.5, L, 1), minor=True)
        ax.set_yticks(np.arange(-0.5, 2, 1), minor=True)
        ax.grid(which="minor", linewidth=0.8, alpha=0.6)
        ax.tick_params(which="minor", bottom=False, left=False)

        for row in range(2):
            for col in range(L):
                pct = H_pct[row, col]
                sec = H_sec[row, col]
                if np.isfinite(pct) and np.isfinite(sec):
                    text = f"{pct:.1f}%\n{sec:.2f}s"
                elif np.isfinite(pct):
                    text = f"{pct:.1f}%"
                else:
                    text = "n/a"
                ax.text(col, row, text, ha="center", va="center", fontsize=10)

        colorbar = fig.colorbar(image, ax=ax, shrink=0.9)
        colorbar.set_label("Swing (% of stride)")

        ax.set_title(f"{self.prefix} - Swing percentage (per minute)")

        filename = add_prefix_to_filename(save_name or "swing_info_heatmap.png", self.prefix)
        save_path = Path(self.out_dir) / filename
        save_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(save_path))
        plt.close(fig)

        return save_path

    def save_minutely_stance_swing_bars(
        self,
        projection: str = DEFAULT_PROJECTION,
        smooth_window_s: float = DEFAULT_SMOOTH_WINDOW_S,
        flat_frac: float = DEFAULT_FLAT_FRAC,
        min_v_abs: float = DEFAULT_MIN_V_ABS,
        *,
        max_minutes: Optional[int] = None,
        dpi: int = 170,
        figsize_per_minute: float = 0.9,
        row_height: float = 3.1,
        bar_width: float = 0.28,
        group_gap: float = 0.18,
        capsize: float = 3.0,
        save_name: Optional[str] = None,
        stance_ylim: Optional[Tuple[float, float]] = None,
        swing_ylim: Optional[Tuple[float, float]] = None,
    ) -> Path:
        """
        使用 compute_gait_summary().per_interval 直接繪製：

        - 站立期 (stance) 時間
        - 擺動期 (swing) 時間

        左 / 右腳並列柱狀圖。
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
        minutes = np.arange(M, dtype=int)

        mu_ls = np.array([float(interval.l_stance_s_mean) for interval in per_interval], dtype=float)
        mu_rs = np.array([float(interval.r_stance_s_mean) for interval in per_interval], dtype=float)
        mu_lw = np.array([float(interval.l_swing_s_mean) for interval in per_interval], dtype=float)
        mu_rw = np.array([float(interval.r_swing_s_mean) for interval in per_interval], dtype=float)

        color_left = "#2563eb"
        color_right = "#ef4444"

        fig_width = max(7.0, float(M) * float(figsize_per_minute))
        fig_height = row_height * 2.0

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(fig_width, fig_height), dpi=dpi, sharex=True, layout="constrained")

        x = minutes.astype(float)
        offset = bar_width + group_gap / 2.0

        x_ls = x - offset / 2.0
        x_rs = x + offset / 2.0

        bars_ls = ax1.bar(x_ls, mu_ls, width=bar_width, capsize=capsize, label="Left", color=color_left)
        bars_rs = ax1.bar(x_rs, mu_rs, width=bar_width, capsize=capsize, label="Right", color=color_right)
        ax1.set_title("Stance time")
        ax1.set_ylabel("Duration (s)")
        ax1.grid(True, axis="y", linestyle="--", alpha=0.25)
        for side in ("top", "right"):
            ax1.spines[side].set_visible(False)
        self._apply_limits(ax1, ylim=stance_ylim)

        bars_lw = ax2.bar(x_ls, mu_lw, width=bar_width, capsize=capsize, label="Left", color=color_left)
        bars_rw = ax2.bar(x_rs, mu_rw, width=bar_width, capsize=capsize, label="Right", color=color_right)
        ax2.set_title("Swing time")
        ax2.set_ylabel("Duration (s)")
        ax2.grid(True, axis="y", linestyle="--", alpha=0.25)
        for side in ("top", "right"):
            ax2.spines[side].set_visible(False)
        self._apply_limits(ax2, ylim=swing_ylim)

        ax2.set_xlabel("Minute (from start)")
        ax2.set_xticks(x)

        n_per_minute = np.array([int(interval.left_step_count + interval.right_step_count) for interval in per_interval], dtype=int)
        ax2.set_xticklabels([f"{m}\n(n={int(count)})" for m, count in zip(minutes, n_per_minute)])

        self._annotate_stance_swing_bars(ax1, bars_ls, mu_ls)
        self._annotate_stance_swing_bars(ax1, bars_rs, mu_rs)
        self._annotate_stance_swing_bars(ax2, bars_lw, mu_lw)
        self._annotate_stance_swing_bars(ax2, bars_rw, mu_rw)

        fig.suptitle(f"{self.prefix} - Per-minute stance/swing durations", y=0.995)

        for axis in (ax1, ax2):
            box = axis.get_position()
            axis.set_position([box.x0, box.y0, box.width * 0.83, box.height])

        ax1.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), frameon=False, ncol=1, title="Side")
        ax2.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), frameon=False, ncol=1, title="Side")

        filename = save_name or "minutely_stance_swing_bars.png"
        save_path = self.out_dir / add_prefix_to_filename(filename, self.prefix)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(save_path))
        plt.close(fig)

        return save_path

    @staticmethod
    def _annotate_stance_swing_bars(
        axis: plt.Axes,
        bar_container,
        values: np.ndarray,
    ) -> None:
        """在柱頂顯示秒數。"""
        if not np.isfinite(values).any():
            return

        ypad = 0.02 * float(np.nanmax(values))

        for rect, value in zip(bar_container, values):
            if not np.isfinite(value):
                continue
            top = float(value)
            axis.text(
                rect.get_x() + rect.get_width() / 2.0,
                top + ypad,
                f"{value:.2f}s",
                ha="center",
                va="bottom",
                fontsize=9,
                color="#222",
            )
