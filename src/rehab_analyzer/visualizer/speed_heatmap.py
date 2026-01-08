"""
每圈速度時空熱圖。

X 軸為規一化進度，Y 軸為圈數，顏色為速度值。
"""
from pathlib import Path
from typing import Optional, List, Tuple

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


class SpeedHeatmapMixin(VisualizerUtilsMixin):
    """
    每圈速度時空熱圖：

    - X 軸：規一化的進度（從離椅 → 回到椅）
    - Y 軸：圈數（Lap 1, Lap 2, ...）
    - 顏色：速度值（m/s）
    """

    def save_spatiotemporal_speed_heatmap(
        self,
        projection: str = DEFAULT_PROJECTION,
        smooth_window_s: float = DEFAULT_SMOOTH_WINDOW_S,
        flat_frac: float = DEFAULT_FLAT_FRAC,
        min_v_abs: float = DEFAULT_MIN_V_ABS,
        *,
        width: int = 300,
        dpi: int = 150,
        save_name: Optional[str] = None,
        vmin: Optional[float] = None,
        vmax: Optional[float] = None,
    ) -> Path:
        """對每圈做索引重採樣後，畫出速度時空熱圖（每列一圈）。"""
        fps = float(self._estimate_fps())
        smooth_window = max(1, int(round(smooth_window_s * fps)))
        L2, R2, _ = self._compute_hip_points(projection=projection, smooth_window=smooth_window)
        C2 = (L2 + R2) / 2.0
        _, speed, _ = self._speed_series(C2)

        det = self.detect_laps_auto(
            projection=projection,
            smooth_window_s=smooth_window_s,
            flat_frac=flat_frac,
            min_v_abs=min_v_abs,
        )
        laps = det.laps
        if not laps:
            raise ValueError("沒有圈數可視覺化。")

        num_laps = len(laps)
        width = int(max(50, width))

        mat = np.full((num_laps, width), np.nan, dtype=float)
        marks: List[Tuple[float, float]] = []

        for row, lap in enumerate(laps):
            start_idx = int(lap.idx_onset_end)
            end_idx = int(lap.idx_chair_sit_end)
            if end_idx <= start_idx:
                continue

            mat[row] = self._resample_1d(speed, start_idx, end_idx, width)
            denom = max(1, end_idx - start_idx)
            a = (lap.idx_turn_cone_start - start_idx) / denom
            b = (lap.idx_turn_cone_end - start_idx) / denom
            marks.append((a, b))

        fig = plt.figure(figsize=(12, max(3.6, 0.36 * num_laps)), dpi=dpi)
        ax = plt.gca()

        image = ax.imshow(mat, aspect="auto", interpolation="nearest", origin="upper", vmin=vmin, vmax=vmax)
        colorbar = fig.colorbar(image, ax=ax)
        colorbar.set_label("Speed (m/s)")

        # 在每圈上畫錐桶轉身區間的線
        for row, (a, b) in enumerate(marks):
            x1 = a * (width - 1)
            x2 = b * (width - 1)
            ax.plot([x1, x1], [row - 0.5, row + 0.5], ls="--", lw=1.0, c="w", alpha=0.8)
            ax.plot([x2, x2], [row - 0.5, row + 0.5], ls="--", lw=1.0, c="w", alpha=0.8)

        ax.set_yticks(np.arange(num_laps))
        ax.set_yticklabels([f"Lap {idx + 1}" for idx in range(num_laps)])

        xticks_pos = np.linspace(0, width - 1, 11)
        xticks_lbl = [f"{int(p)}%" for p in np.linspace(0, 100, 11)]
        ax.set_xticks(xticks_pos)
        ax.set_xticklabels(xticks_lbl)

        ax.set_xlabel("Normalized progress (leave → re-enter)")
        ax.set_title(f"{self.prefix} - Spatiotemporal speed heatmap")

        fig.tight_layout(pad=0.3)

        filename = add_prefix_to_filename(save_name or "speed_heatmap.png", self.prefix)
        save_path = Path(self.out_dir) / filename
        save_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(save_path))
        plt.close(fig)

        return save_path

    @staticmethod
    def _resample_1d(arr: np.ndarray, i0: int, i1: int, m: int) -> np.ndarray:
        """以索引為自變數，將 arr[i0:i1] 線性插值重採樣成 m 個點。"""
        i0 = max(0, int(i0))
        i1 = max(0, int(i1))
        if i1 <= i0:
            raise ValueError("i1 必須大於 i0。")
        idx_src = np.linspace(i0, i1, num=(i1 - i0 + 1))
        idx_dst = np.linspace(i0, i1, num=m)
        return np.interp(idx_dst, idx_src, arr[i0 : i1 + 1])
