"""
每圈六段耗時堆疊圖。

利用 detect_laps_auto() 的 Lap 結果，將每圈分為 6 個階段並畫成堆疊橫條圖。
"""
from pathlib import Path
from typing import Any

import numpy as np
import matplotlib.pyplot as plt

from utils import add_prefix_to_filename
from ..rehab_analyzer import DetectLapsResult
from ..constants import (
    DEFAULT_PROJECTION,
    DEFAULT_SMOOTH_WINDOW_S,
    DEFAULT_FLAT_FRAC,
    DEFAULT_MIN_V_ABS,
)
from .utils import VisualizerUtilsMixin

# 6 個階段的顯示文字
STAGE_LABELS: list[str] = [
    "1 Stand up",
    "2 Walk to cone",
    "3 Turn at cone",
    "4 Walk back",
    "5 Align to sit",
    "6 Sit down",
]

# 對應 Lap 欄位名稱
STAGE_KEYS: list[str] = [
    "dur_stand",
    "dur_to_cone",
    "dur_cone_turn",
    "dur_return",
    "dur_turn_to_sit",
    "dur_sit",
]

# 固定用一組顏色，依序對應 6 段
STAGE_COLORS: list[str] = [
    "#4C78A8",
    "#F58518",
    "#E45756",
    "#72B7B2",
    "#54A24B",
    "#EECA3B",
]


class StageDurationsPlotterMixin(VisualizerUtilsMixin):
    """
    每圈六段耗時堆疊圖：

    利用 detect_laps_auto() 的 Lap 結果，
    將每圈分為 6 個階段並畫成堆疊橫條圖：
    1. Stand up
    2. Walk to cone
    3. Turn at cone
    4. Walk back
    5. Align to sit
    6. Sit down
    """

    def save_stage_durations_image(
        self,
        projection: str = DEFAULT_PROJECTION,
        smooth_window_s: float = DEFAULT_SMOOTH_WINDOW_S,
        flat_frac: float = DEFAULT_FLAT_FRAC,
        min_v_abs: float = DEFAULT_MIN_V_ABS,
        *,
        save_name: str | None = None,
        dpi: int = 190,
        show_seconds: bool = True,
        show_meters: bool = True,
        row_height: float = 1.0,
        bar_height: float = 0.5,
        min_width_sec: float = 0.5,
        meters_gap: float = 0.08,
        min_meters_to_show: float = 0.03,
    ) -> Path:
        """
        繪製每圈六段耗時的堆疊橫條圖並輸出 PNG。

        回傳：
            Path：輸出檔案路徑
        """
        det: DetectLapsResult = self.detect_laps_auto(
            projection=projection,
            smooth_window_s=smooth_window_s,
            flat_frac=flat_frac,
            min_v_abs=min_v_abs,
        )
        laps = det.laps
        if not laps:
            raise ValueError("沒有可視覺化的圈數（laps 為空）。")

        # 收集每圈各階段秒數 (N × 6)
        durations: list[list[float]] = []
        for lap in laps:
            row = [max(0.0, getattr(lap, key, 0.0)) for key in STAGE_KEYS]
            durations.append(row)
        sec = np.array(durations, dtype=float)

        totals = sec.sum(axis=1)
        start_ts = np.array([lap.ts_start for lap in laps], dtype=float)
        end_ts = np.array([lap.ts_end for lap in laps], dtype=float)
        lap_len = np.array([lap.dist_lap_path_m for lap in laps], dtype=float)

        # 距離資訊（只顯示在 2 / 3 / 4 / 5 段）
        outbound = np.array([lap.dist_outbound_m for lap in laps], dtype=float)
        turnpath = np.array([lap.dist_cone_turn_path_m for lap in laps], dtype=float)
        retpath = np.array([lap.dist_return_m for lap in laps], dtype=float)
        turn_to_sit = np.array([lap.dist_turn_to_sit_m for lap in laps], dtype=float)

        meters_map = np.stack(
            [
                np.zeros_like(outbound),  # 段 1：無距離
                outbound,                 # 段 2：離椅→錐
                turnpath,                 # 段 3：錐內轉身弦長
                retpath,                  # 段 4：錐→椅
                turn_to_sit,              # 段 5：椅邊轉身距離
                np.zeros_like(outbound),  # 段 6：無距離
            ],
            axis=1,
        )

        num_laps = len(laps)
        fig_height = max(2.5, row_height * num_laps)
        fig, ax = plt.subplots(figsize=(12, fig_height), dpi=dpi)

        ypos = np.arange(num_laps)[::-1]
        left = np.zeros(num_laps, dtype=float)
        bars = []

        # 依序堆疊 6 段
        for idx in range(6):
            bar = ax.barh(
                ypos,
                sec[:, idx],
                left=left,
                color=STAGE_COLORS[idx],
                label=STAGE_LABELS[idx],
                edgecolor="none",
                height=bar_height,
            )
            bars.append(bar)
            left += sec[:, idx]

        # 繪製標註
        self._draw_stage_annotations(
            ax, bars, sec, meters_map, show_seconds, show_meters,
            min_width_sec, meters_gap, min_meters_to_show
        )

        # 右側標註每圈起訖時間與路徑長度
        max_x = float(np.nanmax(totals)) if np.isfinite(totals).any() else 1.0
        ax.set_xlim(0, max_x + max_x * 0.36)

        for lap_idx in range(num_laps):
            tail_x = totals[lap_idx]
            text = (
                f"{self._fmt_ts(start_ts[lap_idx])} → "
                f"{self._fmt_ts(end_ts[lap_idx])} · {lap_len[lap_idx]:.2f} m"
            )
            ax.text(
                tail_x + 0.28,
                ypos[lap_idx],
                text,
                ha="left",
                va="center",
                fontsize=10,
                color="#2b2b2b",
            )

        # Y 軸設定
        ax.set_yticks(ypos)
        ax.set_yticklabels([f"Lap {idx + 1}" for idx in range(num_laps)], fontsize=11)

        ymin, ymax = ypos.min() - 0.5, ypos.max() + 0.5
        if show_meters:
            ymin -= meters_gap * 1.2
        ax.set_ylim(ymin, ymax)

        # 標題與外觀調整
        ax.set_xlabel("Time (s)")
        ax.set_title(f"{self.prefix} - Stage durations", fontsize=14, pad=6)

        for side in ("top", "right"):
            ax.spines[side].set_visible(False)

        ax.grid(True, axis="x", linestyle="--", alpha=0.22)
        ax.set_axisbelow(True)
        ax.margins(x=0.01, y=0.02)

        # 圖例放在下方
        handles = [bars[i][0] for i in range(len(bars))]
        fig.legend(
            handles=handles,
            labels=STAGE_LABELS,
            ncols=6,
            loc="lower center",
            bbox_to_anchor=(0.5, 0.01),
            frameon=False,
            fontsize=9,
            handlelength=1.1,
            handletextpad=0.4,
        )

        fig.tight_layout(rect=[0, 0.06, 1, 1])

        # 檔名與儲存
        filename = add_prefix_to_filename(save_name or "stage_durations.png", self.prefix)
        save_path = Path(self.out_dir) / filename
        save_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(save_path), bbox_inches="tight", pad_inches=0.02)
        plt.close(fig)

        return save_path

    def _draw_stage_annotations(
        self,
        ax: plt.Axes,
        bars: list,
        sec: np.ndarray[Any, Any],
        meters_map: np.ndarray[Any, Any],
        show_seconds: bool,
        show_meters: bool,
        min_width_sec: float,
        meters_gap: float,
        min_meters_to_show: float,
    ) -> None:
        """繪製階段標註（秒數和距離）。"""
        def put_text(
            x: float,
            y: float,
            text: str,
            *,
            ha: str = "center",
            va: str = "center",
            fontsize: int = 9,
            color: str = "white",
            bold: bool = True,
            clip: bool = True,
        ) -> None:
            ax.text(
                x, y, text,
                ha=ha, va=va, fontsize=fontsize, color=color,
                fontweight="bold" if bold else None,
                clip_on=clip,
            )

        # 每段中顯示秒數
        if show_seconds:
            for j, bar in enumerate(bars):
                for lap_idx, rect in enumerate(bar):
                    width = rect.get_width()
                    if width <= 0 or width < min_width_sec:
                        continue

                    if j == 2:
                        dist_val = meters_map[lap_idx, j]
                        dist_val = dist_val if np.isfinite(dist_val) else 0.0
                        label = f"{sec[lap_idx, j]:.2f}s·{dist_val:.2f} m"
                    else:
                        label = f"{sec[lap_idx, j]:.2f}s"

                    cx = rect.get_x() + width / 2.0
                    cy = rect.get_y() + rect.get_height() / 2.0
                    put_text(cx, cy, label)

        # 距離標註
        if show_meters:
            for j in (1, 2, 3, 4):
                bar = bars[j]
                for lap_idx, rect in enumerate(bar):
                    dist_val = float(meters_map[lap_idx, j])
                    if dist_val < min_meters_to_show:
                        continue

                    width = rect.get_width()
                    cx = rect.get_x() + width / 2.0
                    cy = rect.get_y() - meters_gap
                    put_text(
                        cx, cy, f"{dist_val:.2f} m",
                        va="top", fontsize=9, color="#2b2b2b", clip=False,
                    )
