"""
每圈 lateral offset 診斷圖。

包含 lateral offset vs time 和骨盆朝向 θ(t) 的可視化。
"""
from pathlib import Path
from typing import Any

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


class LateralOffsetPlotterMixin(VisualizerUtilsMixin):
    """
    每圈 lateral offset 診斷圖：

    - 子圖 A：lateral offset vs time（含原始 / 平滑）
    - 子圖 B：骨盆朝向 θ(t)（以圈起點為 0°）
    """

    def _resolve_theta_ylim_for_lap(
        self,
        theta_ylim: list[tuple[float, float | None]],
        theta_values: np.ndarray[Any, Any],
    ) -> tuple[float, float | None]:
        """根據這一圈的 theta(t) 自動決定 y 軸範圍。"""
        if theta_ylim is None:
            return None

        candidates: list[tuple[float, float]] = []

        if isinstance(theta_ylim, (list, tuple)) and len(theta_ylim) == 2 \
           and all(np.isscalar(v) for v in theta_ylim):
            lo, hi = float(theta_ylim[0]), float(theta_ylim[1])
            if np.isfinite(lo) and np.isfinite(hi) and hi > lo:
                candidates.append((lo, hi))
        else:
            for item in theta_ylim:
                if not isinstance(item, (list, tuple)) or len(item) != 2:
                    continue
                lo, hi = float(item[0]), float(item[1])
                if np.isfinite(lo) and np.isfinite(hi) and hi > lo:
                    candidates.append((lo, hi))

        if not candidates:
            return None

        theta_arr = np.asarray(theta_values, dtype=float)
        valid = np.isfinite(theta_arr)
        if not valid.any():
            return candidates[0]

        best_range: tuple[float, float] = candidates[0]
        best_score = -1
        best_span = float("inf")

        for lo, hi in candidates:
            inside = valid & (theta_arr >= lo) & (theta_arr <= hi)
            score = int(inside.sum())
            span = hi - lo

            if score > best_score or (score == best_score and span < best_span):
                best_score = score
                best_span = span
                best_range = (lo, hi)

        if best_score == 0:
            y_min = float(np.nanmin(theta_arr[valid]))
            y_max = float(np.nanmax(theta_arr[valid]))
            if np.isfinite(y_min) and np.isfinite(y_max):
                margin = 0.05 * (y_max - y_min + 1e-6)
                return (y_min - margin, y_max + margin)

        return best_range

    def save_per_lap_offset(
        self,
        projection: str = DEFAULT_PROJECTION,
        smooth_window_s: float = DEFAULT_SMOOTH_WINDOW_S,
        flat_frac: float = DEFAULT_FLAT_FRAC,
        min_v_abs: float = DEFAULT_MIN_V_ABS,
        *,
        k_smooth: int = 1,
        dpi: int = 130,
        num_indices: list[int | None] = None,
        max_points_plot: int | None = 150,
        show_samples: bool = True,
        save_name: str | None = None,
        lat_ylim: tuple[float, float | None] = None,
        theta_ylim: list[tuple[float, float | None]] = None,
    ) -> list[Path]:
        """
        針對每圈產生兩子圖：

        - lat(t) 原始與平滑後曲線
        - θ(t)（以圈起始為 0°）

        會輸出多個檔案，每圈一張。
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

        save_paths: list[Path] = []
        save_name_template = save_name or "lap_{lap_idx}_diagnostics.png"
        save_name_template = add_prefix_to_filename(save_name_template, self.prefix)

        # 整段 lateral offset / heading
        fps = float(self._estimate_fps())
        smooth_window = max(1, int(round(smooth_window_s * fps)))
        L2, R2, _ = self._compute_hip_points(
            projection=projection, smooth_window=smooth_window
        )
        C2 = (L2 + R2) / 2.0

        lat_raw_all, lat_smooth_all = self._lateral_offset_series(
            C2,
            np.array(det.chair_pos),
            np.array(det.cone_pos),
            k_smooth=k_smooth,
        )
        theta_all = self.compute_pelvis_heading_unwrapped(L2=L2, R2=R2)

        for lap_idx, lap in enumerate(laps):
            if num_indices is not None and (lap_idx + 1) not in num_indices:
                continue

            save_path = self._render_single_lap_offset(
                lap_idx, lap, lat_raw_all, lat_smooth_all, theta_all,
                k_smooth, dpi, max_points_plot, show_samples,
                lat_ylim, theta_ylim, save_name_template
            )
            save_paths.append(save_path)

        return save_paths

    def _render_single_lap_offset(
        self,
        lap_idx: int,
        lap,
        lat_raw_all: np.ndarray[Any, Any],
        lat_smooth_all: np.ndarray[Any, Any],
        theta_all: np.ndarray[Any, Any],
        k_smooth: int,
        dpi: int,
        max_points_plot: int | None,
        show_samples: bool,
        lat_ylim: tuple[float, float | None],
        theta_ylim: list[tuple[float, float | None]],
        save_name_template: str,
    ) -> Path:
        """渲染單圈的診斷圖。"""
        start_idx = int(lap.idx_start)
        end_idx = int(lap.idx_end)

        def rel(i: int) -> int:
            return int(i - start_idx)

        t_rel = self.t[start_idx : end_idx + 1]
        lat_rel = lat_smooth_all[start_idx : end_idx + 1]
        lat_raw_rel = lat_raw_all[start_idx : end_idx + 1]
        theta_rel = theta_all[start_idx : end_idx + 1] - theta_all[start_idx]

        tc_start_rel = rel(lap.idx_turn_cone_start)
        tc_end_rel = rel(lap.idx_turn_cone_end)
        th_start_rel = rel(lap.idx_turn_chair_start)
        th_end_rel = rel(lap.idx_turn_chair_end)

        sample_idx = self._compute_sample_idx(len(t_rel), max_points_plot)

        fig = plt.figure(figsize=(11, 8), constrained_layout=True)
        gridspec = fig.add_gridspec(2, 1, height_ratios=[1, 1])

        # 子圖 A：lateral offset vs time
        ax1 = fig.add_subplot(gridspec[0, 0])
        self._draw_lateral_offset_subplot(
            ax1, t_rel, lat_raw_rel, lat_rel, sample_idx,
            tc_start_rel, tc_end_rel, th_start_rel, th_end_rel,
            k_smooth, max_points_plot, show_samples, lat_ylim, lap_idx
        )

        # 子圖 B：θ(t)
        ax2 = fig.add_subplot(gridspec[1, 0])
        self._draw_theta_subplot(
            ax2, t_rel, theta_rel, sample_idx,
            tc_start_rel, tc_end_rel, th_start_rel, th_end_rel,
            max_points_plot, show_samples, theta_ylim, lap
        )

        out_path = Path(self.out_dir) / save_name_template.format(lap_idx=lap_idx + 1)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(out_path), dpi=dpi)
        plt.close(fig)
        return out_path

    @staticmethod
    def _compute_sample_idx(length: int, max_points: int | None) -> np.ndarray[Any, Any]:
        """決定要取樣的索引。"""
        if max_points is None or max_points <= 0 or length <= max_points:
            return np.arange(length, dtype=int)
        indices = np.linspace(0, length - 1, num=int(max_points), dtype=int)
        return np.unique(np.concatenate(([0], indices, [length - 1]))).astype(int)

    @staticmethod
    def _draw_turn_region(
        axis: plt.Axes,
        t: np.ndarray[Any, Any],
        start_idx: int,
        end_idx: int,
        *,
        alpha: float = 0.15,
        label: str | None = None,
    ) -> None:
        """在時間區間上畫出轉身區域底色。"""
        if 0 <= start_idx < len(t) and 0 <= end_idx < len(t) and end_idx >= start_idx:
            axis.axvspan(t[start_idx], t[end_idx], alpha=alpha, label=label)

    def _draw_lateral_offset_subplot(
        self,
        ax: plt.Axes,
        t_rel: np.ndarray[Any, Any],
        lat_raw_rel: np.ndarray[Any, Any],
        lat_rel: np.ndarray[Any, Any],
        sample_idx: np.ndarray[Any, Any],
        tc_start_rel: int,
        tc_end_rel: int,
        th_start_rel: int,
        th_end_rel: int,
        k_smooth: int,
        max_points_plot: int | None,
        show_samples: bool,
        lat_ylim: tuple[float, float | None],
        lap_idx: int,
    ) -> None:
        """繪製 lateral offset 子圖。"""
        ax.plot(t_rel, lat_raw_rel, label="lat_raw")
        ax.plot(t_rel, lat_rel, label=f"lat_smooth (k={k_smooth})")

        self._draw_turn_region(ax, t_rel, tc_start_rel, tc_end_rel, label="cone turn (existing)")
        self._draw_turn_region(ax, t_rel, th_start_rel, th_end_rel, label="chair turn (existing)")

        if show_samples:
            ax.plot(
                t_rel[sample_idx], lat_rel[sample_idx],
                linestyle="none", marker="o",
                label=f"samples (≤{max_points_plot or 'all'})",
            )

        ax.set_title(f"{self.prefix or 'session'} - Lap #{lap_idx + 1} — lateral offset")
        ax.set_xlabel("time (s)")
        ax.set_ylabel("lat(t)")
        ax.grid(True, alpha=0.35)
        ax.margins(x=0.02)
        ax.legend(fontsize=9)
        self._apply_limits(ax, ylim=lat_ylim)

    def _draw_theta_subplot(
        self,
        ax: plt.Axes,
        t_rel: np.ndarray[Any, Any],
        theta_rel: np.ndarray[Any, Any],
        sample_idx: np.ndarray[Any, Any],
        tc_start_rel: int,
        tc_end_rel: int,
        th_start_rel: int,
        th_end_rel: int,
        max_points_plot: int | None,
        show_samples: bool,
        theta_ylim: list[tuple[float, float | None]],
        lap,
    ) -> None:
        """繪製 θ(t) 子圖。"""
        ax.plot(t_rel, theta_rel, label=r"θ(t) (deg) — per-lap relative")

        if show_samples:
            ax.plot(
                t_rel[sample_idx], theta_rel[sample_idx],
                linestyle="none", marker="o",
                label=f"θ samples (≤{max_points_plot or 'all'})",
            )

        self._draw_turn_region(ax, t_rel, tc_start_rel, tc_end_rel, label="cone turn (existing)")
        self._draw_turn_region(ax, t_rel, th_start_rel, th_end_rel, label="chair turn (existing)")

        ax.axhline(0.0, linestyle="--", linewidth=1, label="0° at lap start")

        # 標出轉彎方向資訊
        cone_dir = lap.turn_cone_dir
        chair_dir = lap.turn_chair_dir
        dtheta_cone = lap.delta_theta_cone_deg
        dtheta_chair = lap.delta_theta_chair_deg

        def dir_str(d: int) -> str:
            if d > 0:
                return "+1 (Direction: θ increasing)"
            if d < 0:
                return "-1 (Direction: θ decreasing)"
            return "0 (No significant turning)"

        info_lines = [
            f"cone turn: dir={dir_str(cone_dir)}, Δθ≈{dtheta_cone:.1f}°",
            f"chair turn: dir={dir_str(chair_dir)}, Δθ≈{dtheta_chair:.1f}°",
        ]

        ax.text(
            0.02, 0.98, "\n".join(info_lines),
            transform=ax.transAxes, va="top", ha="left", fontsize=9,
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.6),
        )

        ax.set_title("θ vs. t (pelvis heading, stable-unwrapped, relative to lap start)")
        ax.set_xlabel("time (s)")
        ax.set_ylabel(r"Δθ (deg)")
        ax.grid(True, alpha=0.35)
        ax.margins(x=0.02)
        ax.legend(fontsize=9)

        theta_ylim_this_lap = self._resolve_theta_ylim_for_lap(theta_ylim, theta_rel)
        self._apply_limits(ax, ylim=theta_ylim_this_lap)
