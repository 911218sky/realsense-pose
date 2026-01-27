"""
每圈六段耗時堆疊圖。

利用 detect_laps_auto() 的 Lap 結果，將每圈分為 6 個階段並畫成堆疊橫條圖。
"""
from pathlib import Path
from typing import Any

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.patches import Rectangle

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
        row_height: float = 1.0,
        bar_height: float = 0.5,
        min_width_sec: float = 0.5,
    ) -> Path:
        """
        繪製每圈六段耗時的魚骨圖並輸出 PNG。
        
        順時針圈從左邊延伸，逆時針圈從右邊延伸。

        Returns
        -------
        Path
            輸出檔案路徑
        """
        det: DetectLapsResult = self.detect_laps_auto(
            projection=projection,
            smooth_window_s=smooth_window_s,
            flat_frac=flat_frac,
            min_v_abs=min_v_abs,
            detect_direction=True,
        )
        laps = det.laps
        if not laps:
            raise ValueError("沒有可視覺化的圈數（laps 為空）。")

        return self._save_fishbone_layout(
            laps, save_name, dpi, show_seconds,
            row_height, bar_height, min_width_sec
        )

    def _save_fishbone_layout(
        self,
        laps: list,
        save_name: str | None,
        dpi: int,
        show_seconds: bool,
        row_height: float,
        bar_height: float,
        min_width_sec: float,
    ) -> Path:
        """魚骨圖布局：所有圈按時間順序排列，順時針從左開始，逆時針從右開始"""
        
        # 準備所有圈的資料
        durations = []
        lap_directions = []
        lap_objects = []
        
        for lap in laps:
            row = [max(0.0, getattr(lap, key, 0.0)) for key in STAGE_KEYS]
            durations.append(row)
            direction = getattr(lap, 'lap_direction', 'unknown')
            lap_directions.append(direction)
            lap_objects.append(lap)
        
        sec = np.array(durations, dtype=float)
        totals = sec.sum(axis=1)
        
        num_laps = len(laps)
        
        # 統計順時針/逆時針圈數
        cw_count = sum(1 for d in lap_directions if d == 'clockwise')
        ccw_count = sum(1 for d in lap_directions if d == 'counterclockwise')
        total_count = cw_count + ccw_count
        cw_pct = (cw_count / total_count * 100) if total_count > 0 else 0
        ccw_pct = (ccw_count / total_count * 100) if total_count > 0 else 0
        
        # 計算各方向的時間統計
        cw_times = [totals[i] for i, d in enumerate(lap_directions) if d == 'clockwise']
        ccw_times = [totals[i] for i, d in enumerate(lap_directions) if d == 'counterclockwise']
        
        cw_mean = float(np.mean(cw_times)) if cw_times else 0
        ccw_mean = float(np.mean(ccw_times)) if ccw_times else 0
        cw_cv = (float(np.std(cw_times)) / cw_mean * 100) if cw_mean > 0 and len(cw_times) > 1 else 0
        ccw_cv = (float(np.std(ccw_times)) / ccw_mean * 100) if ccw_mean > 0 and len(ccw_times) > 1 else 0
        
        # 計算最大時間用於設定比例
        max_total = float(np.nanmax(totals)) if np.isfinite(totals).any() else 1.0
        
        # 設定圖表尺寸 - 更寬更高
        fig_height = max(10, row_height * num_laps * 0.6 + 4)
        fig, ax = plt.subplots(figsize=(18, fig_height), dpi=dpi)
        
        # 設定背景色
        ax.set_facecolor('#fafafa')
        fig.patch.set_facecolor('white')
        
        # 計算 y 位置（從上到下）
        y_positions = np.arange(num_laps)[::-1]
        
        # 設定 x 軸範圍：以 0 為中心
        x_margin = max_total * 0.3
        ax.set_xlim(-max_total - x_margin, max_total + x_margin)
        
        # 繪製中央分隔線（更美觀的樣式）
        ax.axvline(x=0, color='#cccccc', linestyle='-', linewidth=1.5, zorder=1)
        
        # 繪製淺色背景區域
        ax.axvspan(-max_total - x_margin, 0, alpha=0.03, color='blue', zorder=0)
        ax.axvspan(0, max_total + x_margin, alpha=0.03, color='red', zorder=0)
        
        # 為每一圈繪製條形圖
        for lap_idx in range(num_laps):
            direction = lap_directions[lap_idx]
            lap = lap_objects[lap_idx]
            y_pos = y_positions[lap_idx]
            
            # 根據方向決定繪製方向
            if direction == 'clockwise':
                self._draw_fishbone_bar(
                    ax, y_pos, sec[lap_idx], lap, 
                    start_from_left=True, bar_height=bar_height * 0.7,
                    show_seconds=show_seconds, min_width_sec=min_width_sec
                )
            elif direction == 'counterclockwise':
                self._draw_fishbone_bar(
                    ax, y_pos, sec[lap_idx], lap,
                    start_from_left=False, bar_height=bar_height * 0.7,
                    show_seconds=show_seconds, min_width_sec=min_width_sec
                )
            else:
                # 未知方向：預設放左邊，用較淺的顏色
                self._draw_fishbone_bar(
                    ax, y_pos, sec[lap_idx], lap,
                    start_from_left=True, bar_height=bar_height * 0.5,
                    show_seconds=show_seconds, min_width_sec=min_width_sec,
                    alpha=0.5
                )
        
        # Y 軸設定 - 簡潔的標籤
        ax.set_yticks(y_positions)
        lap_labels = []
        for i, direction in enumerate(lap_directions):
            symbol = "↻" if direction == "clockwise" else "↺" if direction == "counterclockwise" else "?"
            lap_labels.append(f"{i + 1} {symbol}")
        ax.set_yticklabels(lap_labels, fontsize=10, fontweight='medium')
        
        # 設定 y 軸範圍
        ax.set_ylim(y_positions.min() - 0.8, y_positions.max() + 1.5)
        
        # X 軸設定
        ax.set_xlabel("Duration (seconds)", fontsize=11, labelpad=10)
        
        # 設定 x 軸刻度為對稱的
        max_tick = int(np.ceil(max_total / 2) * 2)
        ticks = np.arange(-max_tick, max_tick + 1, 2)
        ax.set_xticks(ticks)
        ax.set_xticklabels([str(abs(t)) for t in ticks], fontsize=9)
        
        # 標題
        ax.set_title(f"{self.prefix}\nStage Durations by Direction", 
                    fontsize=14, fontweight='bold', pad=15)
        
        # 添加方向標籤 + 統計資訊
        # 順時針統計（左側）
        cw_stats = f"← Clockwise ↻\n{cw_count} laps ({cw_pct:.0f}%)\nAvg: {cw_mean:.1f}s | CV: {cw_cv:.1f}%"
        ax.text(-max_total * 0.5, y_positions.max() + 1.3, cw_stats,
               ha='center', va='bottom', fontsize=11, fontweight='bold', 
               color='#1f77b4', linespacing=1.4)
        
        # 逆時針統計（右側）
        ccw_stats = f"Counterclockwise ↺ →\n{ccw_count} laps ({ccw_pct:.0f}%)\nAvg: {ccw_mean:.1f}s | CV: {ccw_cv:.1f}%"
        ax.text(max_total * 0.5, y_positions.max() + 1.3, ccw_stats,
               ha='center', va='bottom', fontsize=11, fontweight='bold', 
               color='#d62728', linespacing=1.4)
        
        # 外觀調整
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_color('#cccccc')
        ax.spines['bottom'].set_color('#cccccc')
        
        # 網格線
        ax.grid(True, axis='x', linestyle='--', alpha=0.3, color='#999999')
        ax.set_axisbelow(True)
        
        # 圖例 - 放在底部，緊貼 x 軸標籤下方
        handles = [Rectangle((0,0), 1, 1, color=STAGE_COLORS[i], ec='white', lw=0.5) 
                   for i in range(6)]
        ax.legend(
            handles=handles,
            labels=STAGE_LABELS,
            ncols=6,
            loc='upper center',
            bbox_to_anchor=(0.5, -0.08),
            frameon=True,
            fancybox=True,
            shadow=False,
            fontsize=9,
            handlelength=1.2,
            handletextpad=0.5,
            columnspacing=1.0,
            edgecolor='#cccccc',
        )
        
        plt.tight_layout()
        
        # 儲存
        filename = add_prefix_to_filename(save_name or "stage_durations_fishbone.png", self.prefix)
        save_path = Path(self.out_dir) / (filename or "stage_durations_fishbone.png")
        save_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(save_path), bbox_inches="tight", pad_inches=0.05, facecolor='white')
        plt.close(fig)
        
        return save_path

    def _draw_fishbone_bar(
        self,
        ax: Axes,
        y_pos: float,
        durations: np.ndarray,
        lap: Any,
        start_from_left: bool,
        bar_height: float,
        show_seconds: bool,
        min_width_sec: float,
        alpha: float = 1.0,
    ) -> None:
        """繪製單個圈的魚骨條形圖 - 優化版本"""
        
        total_duration = np.sum(durations)
        
        if start_from_left:
            # 順時針：從 0 向左延伸（負值方向）
            current_x = 0
            for stage_idx in range(6):
                if durations[stage_idx] <= 0:
                    continue
                width = durations[stage_idx]
                left = current_x - width
                
                ax.barh(
                    y_pos, width, left=left,
                    color=STAGE_COLORS[stage_idx],
                    edgecolor='white', linewidth=0.8,
                    height=bar_height, alpha=alpha, zorder=2
                )
                
                # 永遠顯示秒數
                if show_seconds:
                    cx = left + width / 2
                    ax.text(cx, y_pos, f"{width:.1f}", 
                           ha='center', va='center',
                           fontsize=6, color='white', fontweight='bold', zorder=3)
                
                current_x = left
            
            # 在右側顯示時間資訊
            time_text = f"{self._fmt_ts(lap.ts_start)} → {self._fmt_ts(lap.ts_end)}"
            info_text = f"{total_duration:.1f}s · {lap.dist_lap_path_m:.2f}m"
            ax.text(0.3, y_pos + bar_height * 0.3, time_text, 
                   ha='left', va='center', fontsize=8, color='#333333')
            ax.text(0.3, y_pos - bar_height * 0.3, info_text, 
                   ha='left', va='center', fontsize=8, color='#666666')
        else:
            # 逆時針：從 0 向右延伸（正值方向）
            current_x = 0
            for stage_idx in range(6):
                if durations[stage_idx] <= 0:
                    continue
                width = durations[stage_idx]
                
                ax.barh(
                    y_pos, width, left=current_x,
                    color=STAGE_COLORS[stage_idx],
                    edgecolor='white', linewidth=0.8,
                    height=bar_height, alpha=alpha, zorder=2
                )
                
                # 顯示秒數
                if show_seconds:
                    cx = current_x + width / 2
                    ax.text(cx, y_pos, f"{width:.1f}", 
                           ha='center', va='center',
                           fontsize=6, color='white', fontweight='bold', zorder=3)
                
                current_x += width
            
            # 在左側顯示時間資訊
            time_text = f"{self._fmt_ts(lap.ts_start)} → {self._fmt_ts(lap.ts_end)}"
            info_text = f"{total_duration:.1f}s · {lap.dist_lap_path_m:.2f}m"
            ax.text(-0.3, y_pos + bar_height * 0.3, time_text, 
                   ha='right', va='center', fontsize=8, color='#333333')
            ax.text(-0.3, y_pos - bar_height * 0.3, info_text, 
                   ha='right', va='center', fontsize=8, color='#666666')
