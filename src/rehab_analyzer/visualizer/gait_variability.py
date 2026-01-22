"""
步態變異性與對稱性圖表。

顯示對稱性指標 (SI) 和變異係數 (CV) 的柱狀圖。
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


def calc_symmetry_index(left_val: float, right_val: float) -> float:
    """計算對稱性指數 (SI)。"""
    avg = (left_val + right_val) / 2
    if avg == 0:
        return 0.0
    return abs(left_val - right_val) / avg * 100


def calc_cv(values: list[float]) -> float:
    """計算變異係數 (CV)。"""
    if len(values) < 2:
        return 0.0
    mean = np.mean(values)
    if mean == 0:
        return 0.0
    return float(np.std(values) / mean * 100)


# 統一配色
COLORS = {
    "good": "#10b981",      # 綠色
    "fair": "#f59e0b",      # 橙色
    "poor": "#ef4444",      # 紅色
    "primary": "#3b82f6",   # 藍色
    "secondary": "#8b5cf6", # 紫色
    "text": "#374151",      # 深灰
    "grid": "#e5e7eb",      # 淺灰
}


class GaitVariabilityMixin(VisualizerUtilsMixin):
    """步態變異性與對稱性視覺化 Mixin。"""

    def save_gait_variability_chart(
        self,
        projection: str = DEFAULT_PROJECTION,
        smooth_window_s: float = DEFAULT_SMOOTH_WINDOW_S,
        flat_frac: float = DEFAULT_FLAT_FRAC,
        min_v_abs: float = DEFAULT_MIN_V_ABS,
        *,
        dpi: int = 150,
        figsize: tuple[float, float] = (11, 4.5),
        save_name: str | None = None,
    ) -> Path:
        """產生步態變異性與對稱性圖表。"""
        summary = self.compute_gait_summary(
            smooth_window_s=smooth_window_s,
            projection=projection,
            flat_frac=flat_frac,
            min_v_abs=min_v_abs,
        )
        
        # 計算對稱性指標
        si_spm = calc_symmetry_index(summary.l_spm, summary.r_spm)
        si_step_len = calc_symmetry_index(summary.l_mean_step_len, summary.r_mean_step_len)
        si_swing = calc_symmetry_index(summary.l_swing_pct_mean, summary.r_swing_pct_mean)
        si_stance = calc_symmetry_index(summary.l_stance_s_mean, summary.r_stance_s_mean)
        
        # 計算變異係數
        l_stride = [c.stride_s for c in summary.left_cycles if 0.5 <= c.stride_s <= 3.0]
        r_stride = [c.stride_s for c in summary.right_cycles if 0.5 <= c.stride_s <= 3.0]
        l_swing = [c.swing_s for c in summary.left_cycles if 0.5 <= c.stride_s <= 3.0]
        r_swing = [c.swing_s for c in summary.right_cycles if 0.5 <= c.stride_s <= 3.0]
        
        cv_l_stride = calc_cv(l_stride)
        cv_r_stride = calc_cv(r_stride)
        cv_l_swing = calc_cv(l_swing)
        cv_r_swing = calc_cv(r_swing)
        
        # 創建圖表
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=figsize, dpi=dpi)
        fig.patch.set_facecolor('white')
        
        self._draw_si_chart(ax1, si_spm, si_step_len, si_swing, si_stance)
        self._draw_cv_chart(ax2, cv_l_stride, cv_r_stride, cv_l_swing, cv_r_swing)
        
        fig.suptitle(f"{self.prefix} - Gait Symmetry & Variability", 
                    fontsize=13, fontweight='bold', color=COLORS["text"], y=0.98)
        fig.tight_layout(rect=[0, 0, 1, 0.93])
        
        filename = add_prefix_to_filename(save_name or "gait_variability.png", self.prefix)
        save_path = Path(self.out_dir) / (filename or "gait_variability.png")
        save_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(save_path), facecolor='white', edgecolor='none')
        plt.close(fig)
        
        return save_path

    def _draw_si_chart(self, ax: Axes, si_spm: float, si_step_len: float, 
                       si_swing: float, si_stance: float) -> None:
        """繪製對稱性指標圖。"""
        labels = ["Cadence", "Step Len", "Swing", "Stance"]
        values = [si_spm, si_step_len, si_swing, si_stance]
        x = np.arange(len(labels))
        
        colors = [self._get_si_color(v) for v in values]
        bars = ax.bar(x, values, color=colors, width=0.55, edgecolor='white', linewidth=2)
        
        # 參考線
        ax.axhline(y=10, color=COLORS["good"], linestyle='--', alpha=0.6, linewidth=1.5)
        ax.axhline(y=20, color=COLORS["fair"], linestyle='--', alpha=0.6, linewidth=1.5)
        
        # 標註
        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.8,
                   f'{val:.1f}%', ha='center', va='bottom', 
                   fontsize=11, fontweight='bold', color=COLORS["text"])
        
        ax.set_ylabel("Symmetry Index (%)", fontsize=10, color=COLORS["text"])
        ax.set_title("Left-Right Symmetry\n(lower = better)", fontsize=11, pad=8, color=COLORS["text"])
        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=10)
        ax.set_ylim(bottom=0)
        ax.grid(True, axis='y', linestyle='-', alpha=0.3, color=COLORS["grid"])
        
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.tick_params(colors=COLORS["text"])

    def _draw_cv_chart(self, ax: Axes, cv_l_stride: float, cv_r_stride: float,
                       cv_l_swing: float, cv_r_swing: float) -> None:
        """繪製變異係數圖。"""
        labels = ["L Stride", "R Stride", "L Swing", "R Swing"]
        values = [cv_l_stride, cv_r_stride, cv_l_swing, cv_r_swing]
        x = np.arange(len(labels))
        
        colors = [self._get_cv_color(v) for v in values]
        bars = ax.bar(x, values, color=colors, width=0.55, edgecolor='white', linewidth=2)
        
        # 參考線
        ax.axhline(y=15, color=COLORS["good"], linestyle='--', alpha=0.6, linewidth=1.5)
        ax.axhline(y=30, color=COLORS["fair"], linestyle='--', alpha=0.6, linewidth=1.5)
        
        # 標註
        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.8,
                   f'{val:.1f}%', ha='center', va='bottom',
                   fontsize=11, fontweight='bold', color=COLORS["text"])
        
        ax.set_ylabel("CV (%)", fontsize=10, color=COLORS["text"])
        ax.set_title("Gait Variability\n(lower = more stable)", fontsize=11, pad=8, color=COLORS["text"])
        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=10)
        ax.set_ylim(bottom=0)
        ax.grid(True, axis='y', linestyle='-', alpha=0.3, color=COLORS["grid"])
        
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.tick_params(colors=COLORS["text"])

    @staticmethod
    def _get_si_color(value: float) -> str:
        if value < 10:
            return COLORS["good"]
        elif value < 20:
            return COLORS["fair"]
        return COLORS["poor"]

    @staticmethod
    def _get_cv_color(value: float) -> str:
        if value < 15:
            return COLORS["good"]
        elif value < 30:
            return COLORS["fair"]
        return COLORS["poor"]
