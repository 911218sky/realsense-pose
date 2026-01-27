"""
每分鐘趨勢圖：速度與圈數。

顯示每分鐘的平均速度和完成圈數趨勢。
"""
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.axes import Axes

from utils import add_prefix_to_filename
from ..constants import (
    DEFAULT_PROJECTION,
    DEFAULT_SMOOTH_WINDOW_S,
    DEFAULT_FLAT_FRAC,
    DEFAULT_MIN_V_ABS,
)
from .utils import VisualizerUtilsMixin


# 統一配色
COLORS = {
    "primary": "#3b82f6",   # 藍色
    "secondary": "#10b981", # 綠色
    "accent": "#ef4444",    # 紅色
    "text": "#374151",      # 深灰
    "grid": "#e5e7eb",      # 淺灰
    "fill": "#dbeafe",      # 淺藍
}


class TrendChartsMixin(VisualizerUtilsMixin):
    """每分鐘趨勢圖 Mixin。"""

    def save_minutely_trend_chart(
        self,
        projection: str = DEFAULT_PROJECTION,
        smooth_window_s: float = DEFAULT_SMOOTH_WINDOW_S,
        flat_frac: float = DEFAULT_FLAT_FRAC,
        min_v_abs: float = DEFAULT_MIN_V_ABS,
        *,
        dpi: int = 150,
        figsize: tuple[float, float] = (10, 5),
        save_name: str | None = None,
    ) -> Path:
        """產生每分鐘速度與圈數趨勢圖。"""
        det = self.detect_laps_auto(
            projection=projection,
            smooth_window_s=smooth_window_s,
            flat_frac=flat_frac,
            min_v_abs=min_v_abs,
        )
        laps = det.laps
        if not laps:
            raise ValueError("沒有圈數可視覺化（laps 為空）。")

        t0 = float(laps[0].ts_start)
        last_t = float(laps[-1].ts_end)
        total_minutes = max(1, int(np.ceil((last_t - t0) / 60.0)))
        
        # 統計每分鐘數據
        minute_speeds: list[list[float]] = [[] for _ in range(total_minutes)]
        minute_lap_counts: list[int] = [0] * total_minutes
        
        for lap in laps:
            m = min(int((lap.ts_start - t0) / 60.0), total_minutes - 1)
            m = max(0, m)
            if lap.dur_total > 0 and lap.dist_lap_path_m > 0:
                minute_speeds[m].append(lap.dist_lap_path_m / lap.dur_total)
            minute_lap_counts[m] += 1
        
        avg_speeds = [float(np.mean(s)) if s else float('nan') for s in minute_speeds]
        minutes = np.arange(1, total_minutes + 1)
        
        # 創建圖表
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=figsize, dpi=dpi, sharex=True)
        fig.patch.set_facecolor('white')
        
        self._draw_speed_chart(ax1, minutes, np.array(avg_speeds))
        self._draw_lap_chart(ax2, minutes, np.array(minute_lap_counts))
        
        ax2.set_xlabel("Minute", fontsize=10, color=COLORS["text"])
        
        fig.suptitle(f"{self.prefix} - Speed & Lap Count Trend", 
                    fontsize=13, fontweight='bold', color=COLORS["text"], y=0.98)
        fig.tight_layout(rect=[0, 0, 1, 0.93])
        
        filename = add_prefix_to_filename(save_name or "minutely_trend.png", self.prefix)
        save_path = Path(self.out_dir) / (filename or "minutely_trend.png")
        save_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(save_path), facecolor='white', edgecolor='none')
        plt.close(fig)
        
        return save_path

    def _draw_speed_chart(self, ax: Axes, minutes: np.ndarray, speeds: np.ndarray) -> None:
        """繪製速度趨勢圖。"""
        valid = np.isfinite(speeds)
        
        # 折線 + 填充
        ax.plot(minutes[valid], speeds[valid], 'o-', color=COLORS["primary"], 
                linewidth=2.5, markersize=8, markerfacecolor='white', markeredgewidth=2)
        ax.fill_between(minutes[valid], 0, speeds[valid], color=COLORS["fill"], alpha=0.5)
        
        # 平均線
        avg = float(np.nanmean(speeds))
        if np.isfinite(avg):
            ax.axhline(y=avg, color=COLORS["accent"], linestyle='--', linewidth=1.5, alpha=0.7)
            ax.text(minutes[-1] + 0.3, avg, f'Avg: {avg:.2f}', va='center', 
                   fontsize=9, color=COLORS["accent"], fontweight='bold')
        
        # 標註數值
        for m, s in zip(minutes[valid], speeds[valid]):
            ax.text(m, s + 0.02, f'{s:.2f}', ha='center', va='bottom',
                   fontsize=9, fontweight='bold', color=COLORS["text"])
        
        ax.set_ylabel("Speed (m/s)", fontsize=10, color=COLORS["text"])
        ax.set_title("Walking Speed per Minute", fontsize=11, pad=6, color=COLORS["text"])
        ax.set_ylim(bottom=0)
        ax.grid(True, axis='y', linestyle='-', alpha=0.3, color=COLORS["grid"])
        
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.tick_params(colors=COLORS["text"])

    def _draw_lap_chart(self, ax: Axes, minutes: np.ndarray, counts: np.ndarray) -> None:
        """繪製圈數趨勢圖。"""
        bars = ax.bar(minutes, counts, color=COLORS["secondary"], width=0.55, 
                     edgecolor='white', linewidth=2)
        
        # 平均線
        avg = float(np.mean(counts))
        ax.axhline(y=avg, color=COLORS["accent"], linestyle='--', linewidth=1.5, alpha=0.7)
        ax.text(minutes[-1] + 0.3, avg, f'Avg: {avg:.1f}', va='center',
               fontsize=9, color=COLORS["accent"], fontweight='bold')
        
        # 標註數值
        for bar, cnt in zip(bars, counts):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.15,
                   str(int(cnt)), ha='center', va='bottom',
                   fontsize=10, fontweight='bold', color=COLORS["text"])
        
        ax.set_ylabel("Laps", fontsize=10, color=COLORS["text"])
        ax.set_title("Completed Laps per Minute", fontsize=11, pad=6, color=COLORS["text"])
        ax.set_ylim(bottom=0, top=max(counts) * 1.3 if max(counts) > 0 else 5)
        ax.set_xticks(minutes)
        ax.grid(True, axis='y', linestyle='-', alpha=0.3, color=COLORS["grid"])
        
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.tick_params(colors=COLORS["text"])
