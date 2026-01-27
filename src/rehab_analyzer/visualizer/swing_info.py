"""
擺動資訊熱力圖與柱狀圖。

包含 swing% 熱力圖和 stance/swing 時間柱狀圖。
"""
from pathlib import Path
from typing import Any

from matplotlib.axes import Axes
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

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
        save_name: str | None = None,
        vmin_pct: float | None = None,
        vmax_pct: float | None = None,
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
        if filename is None:
            filename = "swing_info_heatmap.png"
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
        max_minutes: int | None = None,
        dpi: int = 170,
        figsize_per_minute: float = 0.9,
        row_height: float = 3.1,
        bar_width: float = 0.28,
        group_gap: float = 0.18,
        capsize: float = 3.0,
        save_name: str | None = None,
        stance_ylim: tuple[float, float | None] = None,
        swing_ylim: tuple[float, float | None] = None,
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
        prefixed_filename = add_prefix_to_filename(filename, self.prefix)
        if prefixed_filename is None:
            prefixed_filename = filename
        save_path = self.out_dir / prefixed_filename
        save_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(save_path))
        plt.close(fig)

        return save_path

    @staticmethod
    def _annotate_stance_swing_bars(
        axis: Axes,
        bar_container: Any,
        values: np.ndarray[Any, Any],
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

    def save_gait_swing_timeline(
        self,
        projection: str = DEFAULT_PROJECTION,
        smooth_window_s: float = DEFAULT_SMOOTH_WINDOW_S,
        flat_frac: float = DEFAULT_FLAT_FRAC,
        min_v_abs: float = DEFAULT_MIN_V_ABS,
        *,
        dpi: int = 150,
        figsize: tuple[float, float] = (12, 4),
        save_name: str | None = None,
    ) -> Path:
        """
        繪製左右腳平均步態週期時間軸圖，顯示左右腳交替的節奏。
        
        顯示完整步態週期的各相位：
        - 初始雙支撐期（兩腳同時著地）- 深色
        - 單支撐期（主側腳支撐，對側腳擺動）- 中色
        - 終末雙支撐期（兩腳同時著地）- 深色
        - 擺動期（主側腳離地）- 淺色
        """
        
        # 使用 gait_analyzer 的計算方法
        left_phases, right_phases = self.compute_gait_cycle_phases(
            projection=projection,
            smooth_window_s=smooth_window_s,
            flat_frac=flat_frac,
            min_v_abs=min_v_abs,
        )
        
        if left_phases is None and right_phases is None:
            raise ValueError("No valid gait cycles found for visualization.")
        
        # 顏色設定
        left_ds_color = '#1E3A5F'      # 深藍 - 左腳雙支撐期
        left_ss_color = '#5B9BD5'      # 中藍 - 左腳單支撐期
        left_swing_color = '#DEEBF7'   # 淺藍 - 左腳擺動期
        right_ds_color = '#8B0000'     # 深紅 - 右腳雙支撐期
        right_ss_color = '#E74C3C'     # 中紅 - 右腳單支撐期
        right_swing_color = '#FADBD8'  # 淺紅 - 右腳擺動期
        
        fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
        
        y_left = 1.0
        y_right = 0.0
        bar_height = 0.45
        
        def draw_cycle_bar(
            ax: Axes,
            y: float,
            ds1_pct: float,
            ss_pct: float,
            ds2_pct: float,
            swing_pct: float,
            stance_pct: float,
            avg_time: float,
            ds_color: str,
            ss_color: str,
            swing_color: str,
            is_left: bool,
            offset: float = 0.0,
        ) -> None:
            """繪製單側步態週期的堆疊條形圖。
            
            Left: DS1 → SS → DS2 → Swing（從 HS 開始）
            Right: Swing → DS2 → SS → DS1（反過來，並偏移讓 DS 對齊）
            """
            x = offset
            
            if is_left:
                # 左腳：DS1 → SS → DS2 → Swing
                # DS1（初始雙支撐期）
                if ds1_pct > 0:
                    ax.barh(y, ds1_pct, left=x, height=bar_height,
                           color=ds_color, edgecolor='white', linewidth=0.5)
                    if ds1_pct >= 6:
                        ax.text(x + ds1_pct/2, y, f"{ds1_pct:.0f}%",
                               ha='center', va='center', fontsize=9, color='white', fontweight='bold')
                    x += ds1_pct
                
                # 單支撐期
                if ss_pct > 0:
                    ax.barh(y, ss_pct, left=x, height=bar_height,
                           color=ss_color, edgecolor='white', linewidth=0.5)
                    if ss_pct >= 6:
                        ax.text(x + ss_pct/2, y, f"{ss_pct:.0f}%",
                               ha='center', va='center', fontsize=9, color='white', fontweight='bold')
                    x += ss_pct
                
                # DS2（終末雙支撐期）
                if ds2_pct > 0:
                    ax.barh(y, ds2_pct, left=x, height=bar_height,
                           color=ds_color, edgecolor='white', linewidth=0.5)
                    if ds2_pct >= 6:
                        ax.text(x + ds2_pct/2, y, f"{ds2_pct:.0f}%",
                               ha='center', va='center', fontsize=9, color='white', fontweight='bold')
                    x += ds2_pct
                
                # 擺動期
                if swing_pct > 0:
                    ax.barh(y, swing_pct, left=x, height=bar_height,
                           color=swing_color, edgecolor='#999999', linewidth=0.5)
                    if swing_pct >= 6:
                        ax.text(x + swing_pct/2, y, f"{swing_pct:.0f}%",
                               ha='center', va='center', fontsize=9, color='#333333', fontweight='bold')
                
                # 支撐期標註線（上方）
                bracket_y = y + bar_height/2 + 0.08
                ax.plot([offset, offset + stance_pct], [bracket_y, bracket_y], 'k-', linewidth=1.2)
                ax.plot([offset, offset], [bracket_y - 0.03, bracket_y + 0.03], 'k-', linewidth=1.2)
                ax.plot([offset + stance_pct, offset + stance_pct], [bracket_y - 0.03, bracket_y + 0.03], 'k-', linewidth=1.2)
                ax.text(offset + stance_pct/2, bracket_y + 0.12, f"{stance_pct:.0f}%",
                       ha='center', va='center', fontsize=9, color='#333333')
            else:
                # 右腳：Swing → DS2 → SS → DS1（反過來，讓左腳踩地時右腳離地）
                # 擺動期
                if swing_pct > 0:
                    ax.barh(y, swing_pct, left=x, height=bar_height,
                           color=swing_color, edgecolor='#999999', linewidth=0.5)
                    if swing_pct >= 6:
                        ax.text(x + swing_pct/2, y, f"{swing_pct:.0f}%",
                               ha='center', va='center', fontsize=9, color='#333333', fontweight='bold')
                    x += swing_pct
                
                # DS2（終末雙支撐期，現在變成開頭）
                if ds2_pct > 0:
                    ax.barh(y, ds2_pct, left=x, height=bar_height,
                           color=ds_color, edgecolor='white', linewidth=0.5)
                    if ds2_pct >= 6:
                        ax.text(x + ds2_pct/2, y, f"{ds2_pct:.0f}%",
                               ha='center', va='center', fontsize=9, color='white', fontweight='bold')
                    x += ds2_pct
                
                # 單支撐期
                if ss_pct > 0:
                    ax.barh(y, ss_pct, left=x, height=bar_height,
                           color=ss_color, edgecolor='white', linewidth=0.5)
                    if ss_pct >= 6:
                        ax.text(x + ss_pct/2, y, f"{ss_pct:.0f}%",
                               ha='center', va='center', fontsize=9, color='white', fontweight='bold')
                    x += ss_pct
                
                # DS1（初始雙支撐期，現在變成結尾）
                if ds1_pct > 0:
                    ax.barh(y, ds1_pct, left=x, height=bar_height,
                           color=ds_color, edgecolor='white', linewidth=0.5)
                    if ds1_pct >= 6:
                        ax.text(x + ds1_pct/2, y, f"{ds1_pct:.0f}%",
                               ha='center', va='center', fontsize=9, color='white', fontweight='bold')
                
                # 支撐期標註線（下方）
                bracket_y = y - bar_height/2 - 0.08
                stance_start = offset + swing_pct
                stance_end = stance_start + stance_pct
                ax.plot([stance_start, stance_end], [bracket_y, bracket_y], 'k-', linewidth=1.2)
                ax.plot([stance_start, stance_start], [bracket_y - 0.03, bracket_y + 0.03], 'k-', linewidth=1.2)
                ax.plot([stance_end, stance_end], [bracket_y - 0.03, bracket_y + 0.03], 'k-', linewidth=1.2)
                ax.text(stance_start + stance_pct/2, bracket_y - 0.12, f"{stance_pct:.0f}%",
                       ha='center', va='center', fontsize=9, color='#333333')
            
            # 右側顯示平均週期時間
            ax.text(105, y, f"{avg_time:.2f}s",
                   ha='left', va='center', fontsize=11, color='#333333', fontweight='bold')
        
        # 計算偏移量讓雙支撐期對齊
        # Left: DS1 → SS → DS2 → Swing
        # Right: Swing → DS2 → SS → DS1
        # 
        # Left 的 DS2 開始於 ds1 + ss = stance - ds2
        # Right 的 DS2 開始於 swing
        # 要讓它們對齊：Right 偏移 = Left_DS2_start - Right_DS2_start
        #                        = (left_ds1 + left_ss) - right_swing
        right_offset = 0.0
        if left_phases and right_phases:
            left_ds2_start = left_phases.ds1_pct + left_phases.single_support_pct
            right_ds2_start = right_phases.swing_pct
            right_offset = left_ds2_start - right_ds2_start
        
        # 繪製左腳週期
        if left_phases:
            draw_cycle_bar(ax, y_left, 
                          left_phases.ds1_pct, left_phases.single_support_pct,
                          left_phases.ds2_pct, left_phases.swing_pct,
                          left_phases.stance_pct, left_phases.avg_cycle_time_s,
                          left_ds_color, left_ss_color, left_swing_color, True)
        
        # 繪製右腳週期（帶偏移）
        if right_phases:
            draw_cycle_bar(ax, y_right,
                          right_phases.ds1_pct, right_phases.single_support_pct,
                          right_phases.ds2_pct, right_phases.swing_pct,
                          right_phases.stance_pct, right_phases.avg_cycle_time_s,
                          right_ds_color, right_ss_color, right_swing_color, False,
                          offset=right_offset)
        
        # 軸設定
        ax.set_yticks([y_right, y_left])
        ax.set_yticklabels(['Right', 'Left'], fontsize=12, fontweight='bold')
        ax.set_xlim(-2, 118)
        ax.set_ylim(-0.55, 1.6)
        ax.set_xticks([])
        
        # 圖例
        legend_elements = [
            Rectangle((0, 0), 1, 1, facecolor=left_ds_color, label='Left Double Support'),
            Rectangle((0, 0), 1, 1, facecolor=left_ss_color, label='Left Single Support'),
            Rectangle((0, 0), 1, 1, facecolor=left_swing_color, edgecolor='#999', label='Left Swing'),
            Rectangle((0, 0), 1, 1, facecolor=right_ds_color, label='Right Double Support'),
            Rectangle((0, 0), 1, 1, facecolor=right_ss_color, label='Right Single Support'),
            Rectangle((0, 0), 1, 1, facecolor=right_swing_color, edgecolor='#999', label='Right Swing'),
        ]
        ax.legend(handles=legend_elements, loc='upper center', bbox_to_anchor=(0.5, -0.08),
                 ncol=3, frameon=True, fontsize=8)
        
        # 美化
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['bottom'].set_visible(False)
        
        ax.set_title(f'{self.prefix} - Average Gait Cycle', fontsize=12, fontweight='bold', pad=10)
        
        plt.tight_layout()
        
        # 儲存
        filename = save_name or "gait_swing_timeline.png"
        prefixed_filename = add_prefix_to_filename(filename, self.prefix)
        if prefixed_filename is None:
            prefixed_filename = filename
        save_path = self.out_dir / prefixed_filename
        save_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(save_path), bbox_inches="tight", pad_inches=0.15)
        plt.close(fig)
        
        return save_path
