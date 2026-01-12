"""
Top-down 行走軌跡影片輸出。

使用髖點在投影平面上的 2D 軌跡，顯示全程軌跡、尾巴軌跡、椅子/錐桶位置等。
"""
from pathlib import Path
from typing import Any

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.axes import Axes
from matplotlib.lines import Line2D
from matplotlib.patches import Circle
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas

from utils import FFmpegPipe, add_prefix_to_filename
from ..constants import (
    DEFAULT_PROJECTION,
    DEFAULT_SMOOTH_WINDOW_S,
    DEFAULT_FLAT_FRAC,
    DEFAULT_MIN_V_ABS,
)
from .utils import VisualizerUtilsMixin


class TrajectoryVideoExporterMixin(VisualizerUtilsMixin):
    """
    Top-down 行走軌跡影片輸出：

    - 使用髖點（或自訂關節）在投影平面上的 2D 軌跡
    - 顯示：
      - 全程軌跡
      - 尾巴軌跡（最近 trail_sec 秒）
      - 左右髖點位置
      - 骨盆線段
      - 椅子 / 錐桶位置與半徑
      - 每圈轉身區段的標記
      - 目前時間與滑動平均速度
    """

    def save_trajectory_video(
        self,
        projection: str = DEFAULT_PROJECTION,
        smooth_window_s: float = DEFAULT_SMOOTH_WINDOW_S,
        flat_frac: float = DEFAULT_FLAT_FRAC,
        min_v_abs: float = DEFAULT_MIN_V_ABS,
        save_name: str | None = None,
        *,
        left_joint: int | str = "L_HIP",
        right_joint: int | str = "R_HIP",
        fps_out: int = 24,
        speed: float = 1.0,
        dpi: int = 110,
        figsize: tuple[float, float] = (7.6, 7.2),
        draw_radius: bool = False,
        draw_turn_markers: bool = True,
        bg_color: str = "#ffffff",
        path_color_L: str = "#cfcfcf",
        path_color_R: str = "#cdcdcd",
        trail_color_L: str = "#3b82f6",
        trail_color_R: str = "#22c55e",
        dot_color_L: str = "#1f2937",
        dot_color_R: str = "#111827",
        chair_color: str = "#22c55e",
        cone_color: str = "#f97316",
        turn_cone_start_color: str = "#ef4444",
        turn_cone_end_color: str = "#b91c1c",
        turn_chair_start_color: str = "#0ea5e9",
        turn_chair_end_color: str = "#0369a1",
        pad_scale: float = 0.08,
        rotate_180: bool = True,
        frame_jump: int = 3,
        avg_window_s: float = 1.0,
        ffmpeg_preset: str = "veryfast",
        ffmpeg_crf: int = 28,
    ) -> Path:
        """
        匯出 top-down 軌跡影片，顯示左右髖位置、每圈尾巴、轉身標記與即時速度文字。

        尾巴邏輯：
            - 在某一圈內：顯示「該圈從起點到目前幀」的整圈軌跡。
            - 不屬於任何圈：尾巴為空，不畫軌跡。
            - 進入下一圈時：上一圈尾巴整條消失，只顯示新那一圈。

        rotate_180:
            True -> 以整體畫面中心為軸，將繪圖結果旋轉 180°（椅/錐上下互換）。
        """
        # 取得髖點投影座標與有效 mask
        fps_in = float(self._estimate_fps())
        smooth_window = max(1, int(round(smooth_window_s * fps_in)))
        L2, R2, valid = self._compute_hip_points(
            projection=projection,
            smooth_window=smooth_window,
            left_joint=left_joint,
            right_joint=right_joint,
        )
        C2 = (L2 + R2) / 2.0
        num_frames = C2.shape[0]

        det = self.detect_laps_auto(
            projection=projection,
            smooth_window_s=smooth_window_s,
            flat_frac=flat_frac,
            min_v_abs=min_v_abs,
        )
        chair_pos = np.array(det.chair_pos, dtype=float)
        cone_pos = np.array(det.cone_pos, dtype=float)
        rC = float(det.r_chair_enter)
        rK = float(det.r_cone_enter)

        if not np.any(valid):
            raise ValueError("沒有有效的髖點座標。")

        # 畫面可見範圍
        all_points = np.vstack([L2[valid], R2[valid], chair_pos[None, :], cone_pos[None, :]])
        xmin, ymin = np.min(all_points, axis=0)
        xmax, ymax = np.max(all_points, axis=0)
        span = max(xmax - xmin, ymax - ymin, 1e-6)
        pad_abs = pad_scale * span
        xmin -= pad_abs; xmax += pad_abs; ymin -= pad_abs; ymax += pad_abs

        if rotate_180:
            cx = 0.5 * (xmin + xmax)
            cy = 0.5 * (ymin + ymax)
            L2, R2, C2, chair_pos, cone_pos = self._rotate_all_coords(  # pyright: ignore[reportConstantRedefinition]
                L2, R2, C2, chair_pos, cone_pos, cx, cy
            )

        # 按 speed 與輸出 fps 決定取樣步距
        stride = max(1, int(round((fps_in * float(speed)) / float(fps_out))))
        idxs_full = np.arange(0, num_frames, stride, dtype=int)
        idxs_full = idxs_full[valid[idxs_full]]

        if idxs_full.size < 2:
            raise ValueError("有效影格太少，無法產生影片。")

        if frame_jump > 1:
            idxs_full = idxs_full[::frame_jump]
        M = idxs_full.size

        L2_sub = L2[idxs_full]
        R2_sub = R2[idxs_full]

        # 時間軸處理
        t_all = self._interpolate_time(num_frames, fps_in)
        t_sub = t_all[idxs_full]

        # 計算瞬時速度
        speed_sub, spd_avg_arr = self._compute_speed_arrays(
            C2, t_all, idxs_full, fps_in, stride, avg_window_s, M
        )

        # 文字時間標籤
        minutes = (t_sub // 60).astype(int)
        seconds = t_sub % 60.0
        time_labels = np.array([f"{m}:{s:05.2f}" for m, s in zip(minutes, seconds)])

        # 建立 figure 與 axes
        fig, ax_legend, ax_main, ax_info = self._create_trajectory_figure(
            figsize, dpi, bg_color
        )
        canvas = FigureCanvas(fig)

        # 設置圖例
        legend_handles = self._build_legend_handles(
            path_color_L, path_color_R, chair_color, cone_color,
            trail_color_L, trail_color_R, draw_radius, draw_turn_markers,
            rC, rK, turn_cone_start_color, turn_cone_end_color,
            turn_chair_start_color, turn_chair_end_color
        )
        ax_legend.legend(handles=legend_handles, loc="upper left", frameon=False, fontsize=9)

        # 繪製靜態元素
        self._draw_static_elements(
            ax_main, L2, R2, valid, chair_pos, cone_pos,
            path_color_L, path_color_R, chair_color, cone_color,
            draw_radius, rC, rK
        )

        # 轉身標記 scatter
        turn_scatters = self._create_turn_scatters(
            ax_main, turn_cone_start_color, turn_cone_end_color,
            turn_chair_start_color, turn_chair_end_color
        )

        # 全域 frame -> lap 映射
        frame_to_lap = self._build_frame_to_lap_map(det, num_frames)
        lap_idx_sub = frame_to_lap[idxs_full]
        num_laps = len(det.laps)
        lap_first = self._compute_lap_first_indices(lap_idx_sub, num_laps)

        # 設置 main axes 外觀
        self._style_main_axes(ax_main, xmin, xmax, ymin, ymax, projection)

        # 底部資訊區
        text_time, text_speed = self._setup_info_axes(ax_info)

        # 動態物件
        tail_L, tail_R, head_L, head_R, pelvis_line = self._create_dynamic_artists(
            ax_main, trail_color_L, trail_color_R, dot_color_L, dot_color_R
        )

        # 預先擷取背景
        fig.canvas.draw()
        bg_main = fig.canvas.copy_from_bbox(ax_main.bbox)  # pyright: ignore[reportAttributeAccessIssue]
        bg_info = fig.canvas.copy_from_bbox(ax_info.bbox)  # pyright: ignore[reportAttributeAccessIssue]

        # FFmpeg 管線
        save_path = self._setup_video_output(
            save_name, left_joint, right_joint, figsize, dpi, fps_out, ffmpeg_preset, ffmpeg_crf
        )
        width = int(round(figsize[0] * dpi))
        height = int(round(figsize[1] * dpi))
        pipe = FFmpegPipe(
            out_path=str(save_path), width=width, height=height, fps=fps_out,
            preset=ffmpeg_preset, crf=ffmpeg_crf, pixel_format="rgb24",
            extra_args=["-pix_fmt", "yuv420p"], loglevel="error",
        )

        try:
            self._render_frames(
                fig, canvas, pipe, M, idxs_full, L2_sub, R2_sub, C2,
                lap_idx_sub, lap_first, num_laps, frame_to_lap, det,
                tail_L, tail_R, head_L, head_R, pelvis_line,
                turn_scatters, draw_turn_markers, num_frames,
                ax_main, ax_info, bg_main, bg_info,
                time_labels, spd_avg_arr, avg_window_s, text_time, text_speed
            )
        finally:
            pipe.close()
            plt.close(fig)

        return save_path

    def _rotate_all_coords(
        self, L2: np.ndarray[Any, Any], R2: np.ndarray[Any, Any], C2: np.ndarray[Any, Any],
        chair_pos: np.ndarray[Any, Any], cone_pos: np.ndarray[Any, Any], cx: float, cy: float
    ) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any], np.ndarray[Any, Any], np.ndarray[Any, Any], np.ndarray[Any, Any]]:
        """旋轉所有座標 180 度。"""
        def _rotate(arr: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
            rotated = np.array(arr, dtype=float, copy=True)
            rotated[..., 0] = 2 * cx - rotated[..., 0]
            rotated[..., 1] = 2 * cy - rotated[..., 1]
            return rotated
        return _rotate(L2), _rotate(R2), _rotate(C2), _rotate(chair_pos), _rotate(cone_pos)

    def _interpolate_time(self, num_frames: int, fps_in: float) -> np.ndarray[Any, Any]:
        """處理時間軸（若有缺值則線性內插）。"""
        if self.t is not None and np.isfinite(self.t).any():
            finite_mask = np.isfinite(self.t)
            indices_all = np.arange(num_frames)
            known_indices = np.where(finite_mask)[0]
            known_times = self.t[finite_mask].astype(float)
            interpolated = np.interp(indices_all, known_indices, known_times)
            return np.where(finite_mask, self.t, interpolated).astype(float)
        return np.arange(num_frames, dtype=float) / max(1.0, fps_in)

    def _compute_speed_arrays(
        self, C2: np.ndarray[Any, Any], t_all: np.ndarray[Any, Any], idxs_full: np.ndarray[Any, Any],
        fps_in: float, stride: int, avg_window_s: float, M: int
    ) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any]]:
        """計算瞬時速度和滑動平均速度。"""
        dt = np.diff(t_all, prepend=t_all[0])
        positive_dt_mask = np.isfinite(dt) & (dt > 0)
        dt_median = float(np.median(dt[positive_dt_mask])) if np.any(positive_dt_mask) else 1.0 / max(1.0, fps_in)
        dt[~np.isfinite(dt) | (dt <= 0)] = dt_median
        dC = np.sqrt(np.sum(np.diff(C2, axis=0, prepend=C2[[0], :]) ** 2, axis=1))
        speed_inst = dC / dt
        speed_sub = speed_inst[idxs_full].astype(float)

        window_size = max(1, int(round(avg_window_s * (fps_in / stride))))
        if M >= window_size:
            csum = np.cumsum(np.insert(speed_sub, 0, 0.0))
            counts = np.cumsum(np.insert(np.isfinite(speed_sub).astype(np.int32), 0, 0))
            spd_avg_arr = (csum[window_size:] - csum[:-window_size]) / np.maximum(1, (counts[window_size:] - counts[:-window_size]))
            head = np.full(window_size - 1, 0.0, dtype=float)
            spd_avg_arr = np.concatenate([head, spd_avg_arr])
        else:
            spd_avg_arr = np.full(M, 0.0, dtype=float)

        return speed_sub, spd_avg_arr

    def _create_trajectory_figure(
        self, figsize: tuple[float, float], dpi: int, bg_color: str
    ) -> tuple[Figure, Axes, Axes, Axes]:
        """建立軌跡影片的 Figure 和 Axes。"""
        fig = plt.figure(figsize=figsize, dpi=dpi)
        left_margin = 0.02
        ax_legend = fig.add_axes((left_margin, 0.18, 0.10, 0.76), facecolor=bg_color)
        ax_main = fig.add_axes((left_margin + 0.12, 0.18, 1.0 - (left_margin + 0.14), 0.76), facecolor=bg_color)
        ax_info = fig.add_axes((0.00, 0.02, 1.00, 0.12), facecolor=bg_color)
        ax_legend.set_axis_off()
        return fig, ax_legend, ax_main, ax_info

    def _build_legend_handles(
        self, path_color_L: str, path_color_R: str, chair_color: str, cone_color: str,
        trail_color_L: str, trail_color_R: str, draw_radius: bool, draw_turn_markers: bool,
        rC: float, rK: float, turn_cone_start_color: str, turn_cone_end_color: str,
        turn_chair_start_color: str, turn_chair_end_color: str
    ) -> list[Line2D]:
        """建立圖例項目。"""
        handles: list[Line2D] = [
            Line2D([], [], color=path_color_L, lw=1.4, label="L hip (full)"),
            Line2D([], [], color=path_color_R, lw=1.4, label="R hip (full)"),
            Line2D([], [], marker="s", markersize=8, color=chair_color, lw=0, label="Chair"),
            Line2D([], [], marker="^", markersize=8, color=cone_color, lw=0, label="Cone"),
            Line2D([], [], color=trail_color_L, lw=2.2, label="L hip (tail)"),
            Line2D([], [], color=trail_color_R, lw=2.2, label="R hip (tail)"),
            Line2D([], [], color="#2b2b2b", lw=2.0, label="Pelvis"),
        ]
        if draw_radius:
            if np.isfinite(rC) and rC > 0:
                handles.append(Line2D([], [], color=chair_color, lw=1.5, ls="--", label=f"Chair radius ({rC:.2f} m)"))
            if np.isfinite(rK) and rK > 0:
                handles.append(Line2D([], [], color=cone_color, lw=1.5, ls="--", label=f"Cone radius ({rK:.2f} m)"))
        if draw_turn_markers:
            handles.extend([
                Line2D([], [], marker="o", markersize=8, color=turn_cone_start_color, lw=0, label="Cone-turn start"),
                Line2D([], [], marker="X", markersize=8, color=turn_cone_end_color, lw=0, label="Cone-turn end"),
                Line2D([], [], marker="D", markersize=8, color=turn_chair_start_color, lw=0, label="Chair-turn start"),
                Line2D([], [], marker="P", markersize=8, color=turn_chair_end_color, lw=0, label="Chair-turn end"),
            ])
        return handles

    def _draw_static_elements(
        self, ax: Axes, L2: np.ndarray[Any, Any], R2: np.ndarray[Any, Any], valid: np.ndarray[Any, Any],
        chair_pos: np.ndarray[Any, Any], cone_pos: np.ndarray[Any, Any],
        path_color_L: str, path_color_R: str, chair_color: str, cone_color: str,
        draw_radius: bool, rC: float, rK: float
    ) -> None:
        """繪製靜態軌跡與椅/錐位置。"""
        ax.plot(L2[valid, 0], L2[valid, 1], lw=1.0, alpha=0.55, color=path_color_L, zorder=1)
        ax.plot(R2[valid, 0], R2[valid, 1], lw=1.0, alpha=0.50, color=path_color_R, zorder=1)
        ax.scatter([chair_pos[0]], [chair_pos[1]], s=80, color=chair_color, marker="s", zorder=4)
        ax.scatter([cone_pos[0]], [cone_pos[1]], s=80, color=cone_color, marker="^", zorder=4)

        if draw_radius:
            if np.isfinite(rC) and rC > 0:
                ax.add_patch(Circle(tuple(chair_pos), rC, fill=False, lw=1.5, ls="--", color=chair_color, alpha=0.9, clip_on=False))
            if np.isfinite(rK) and rK > 0:
                ax.add_patch(Circle(tuple(cone_pos), rK, fill=False, lw=1.5, ls="--", color=cone_color, alpha=0.9, clip_on=False))

    def _create_turn_scatters(
        self, ax: Axes,
        turn_cone_start_color: str, turn_cone_end_color: str,
        turn_chair_start_color: str, turn_chair_end_color: str
    ) -> dict[str, Any]:
        """創建轉身標記的 scatter 物件。"""
        return {
            "cone_start": ax.scatter([], [], s=70, marker="o", color=turn_cone_start_color, alpha=0.95, zorder=6),
            "cone_end": ax.scatter([], [], s=70, marker="X", color=turn_cone_end_color, alpha=0.95, zorder=6),
            "chair_start": ax.scatter([], [], s=70, marker="D", color=turn_chair_start_color, alpha=0.95, zorder=6),
            "chair_end": ax.scatter([], [], s=70, marker="P", color=turn_chair_end_color, alpha=0.95, zorder=6),
        }

    def _build_frame_to_lap_map(self, det, num_frames: int) -> np.ndarray[Any, Any]:
        """建立 frame -> lap 映射。"""
        frame_to_lap = np.full(num_frames, -1, dtype=int)
        for lap_idx, lap in enumerate(det.laps):
            start_idx_lap = max(0, int(lap.idx_start))
            end_idx_lap = min(num_frames - 1, int(lap.idx_end))
            if end_idx_lap >= start_idx_lap:
                frame_to_lap[start_idx_lap : end_idx_lap + 1] = lap_idx
        return frame_to_lap

    def _compute_lap_first_indices(self, lap_idx_sub: np.ndarray[Any, Any], num_laps: int) -> np.ndarray[Any, Any]:
        """計算每圈在子序列中的第一個索引。"""
        lap_first = np.full(num_laps, -1, dtype=int)
        for li in range(num_laps):
            idxs = np.where(lap_idx_sub == li)[0]
            if idxs.size:
                lap_first[li] = int(idxs[0])
        return lap_first

    def _style_main_axes(
        self, ax: Axes, xmin: float, xmax: float, ymin: float, ymax: float, projection: str
    ) -> None:
        """設置主軸外觀。"""
        ax.set_title("Trajectory - chair & cone", fontsize=13, pad=6, color="#111")
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlim(xmin, xmax)
        ax.set_ylim(ymin, ymax)
        ax.xaxis.set_label_position("top")

        proj = (projection or "xz").lower()
        if proj == "xz":
            dim_x, dim_y = 0, 2
        elif proj == "xy":
            dim_x, dim_y = 0, 1
        else:
            dim_x, dim_y = 0, 2

        ax.set_xlabel(self._axis_label_for_data_dim(dim_x))
        ax.set_ylabel(self._axis_label_for_data_dim(dim_y))
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        ax.grid(True, linestyle="--", alpha=0.18)

    def _setup_info_axes(self, ax: Axes) -> tuple[Any, Any]:
        """設置底部資訊區。"""
        ax.set_xticks([]); ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(False)
        box_kwargs = dict(boxstyle="round,pad=0.33,rounding_size=0.20", fc="#ffffff", ec="#dddddd", lw=1.0, alpha=0.96)
        text_time = ax.text(0.5, 0.64, "", transform=ax.transAxes, ha="center", va="center", fontsize=12, color="#111", bbox=box_kwargs)
        text_speed = ax.text(0.5, 0.30, "", transform=ax.transAxes, ha="center", va="center", fontsize=12, color="#111")
        return text_time, text_speed

    def _create_dynamic_artists(
        self, ax: Axes, trail_color_L: str, trail_color_R: str, dot_color_L: str, dot_color_R: str
    ) -> tuple[Any, Any, Any, Any, Any]:
        """創建動態繪圖物件。"""
        tail_L, = ax.plot([], [], lw=2.4, color=trail_color_L, zorder=3, animated=True)
        tail_R, = ax.plot([], [], lw=2.4, color=trail_color_R, zorder=3, animated=True)
        head_L = ax.scatter([], [], s=36, color=dot_color_L, zorder=5)
        head_R = ax.scatter([], [], s=36, color=dot_color_R, zorder=5)
        pelvis_line, = ax.plot([], [], lw=2.0, color="#2b2b2b", zorder=4, alpha=0.9, animated=True)
        return tail_L, tail_R, head_L, head_R, pelvis_line

    def _setup_video_output(
        self, save_name: str | None, left_joint, right_joint,
        figsize: tuple[float, float], dpi: int, fps_out: int,
        ffmpeg_preset: str, ffmpeg_crf: int
    ) -> Path:
        """設置影片輸出路徑。"""
        save_name_template = save_name or "trajectory_{left_joint}_{right_joint}.mp4"
        save_name_final = save_name_template.format(left_joint=left_joint, right_joint=right_joint)
        filename = add_prefix_to_filename(save_name_final, self.prefix)
        if filename is None:
            filename = save_name_final
        save_path = Path(self.out_dir) / filename
        save_path.parent.mkdir(parents=True, exist_ok=True)
        return save_path

    def _render_frames(
        self, fig, canvas, pipe, M: int, idxs_full: np.ndarray[Any, Any],
        L2_sub: np.ndarray[Any, Any], R2_sub: np.ndarray[Any, Any], C2: np.ndarray[Any, Any],
        lap_idx_sub: np.ndarray[Any, Any], lap_first: np.ndarray[Any, Any], num_laps: int,
        frame_to_lap: np.ndarray[Any, Any], det,
        tail_L, tail_R, head_L, head_R, pelvis_line,
        turn_scatters: dict[str, Any], draw_turn_markers: bool, num_frames: int,
        ax_main, ax_info, bg_main, bg_info,
        time_labels: np.ndarray[Any, Any], spd_avg_arr: np.ndarray[Any, Any], avg_window_s: float,
        text_time, text_speed
    ) -> None:
        """渲染所有影格。"""
        tmp_offset = np.empty((1, 2), dtype=float)
        empty_points = np.empty((0, 2), dtype=float)

        for k in range(M):
            frame_idx = idxs_full[k]
            fig.canvas.restore_region(bg_main)
            fig.canvas.restore_region(bg_info)

            # 尾巴區間
            lap_id = lap_idx_sub[k]
            if 0 <= lap_id < num_laps and lap_first[lap_id] >= 0:
                seg_slice = slice(lap_first[lap_id], k + 1)
                tail_L.set_data(L2_sub[seg_slice, 0], L2_sub[seg_slice, 1])
                tail_R.set_data(R2_sub[seg_slice, 0], R2_sub[seg_slice, 1])
            else:
                tail_L.set_data([], [])
                tail_R.set_data([], [])

            # 更新左右點位置
            tmp_offset[0, 0], tmp_offset[0, 1] = L2_sub[k, 0], L2_sub[k, 1]
            head_L.set_offsets(tmp_offset)
            tmp_offset[0, 0], tmp_offset[0, 1] = R2_sub[k, 0], R2_sub[k, 1]
            head_R.set_offsets(tmp_offset)

            # 更新骨盆線段
            pelvis_line.set_data([L2_sub[k, 0], R2_sub[k, 0]], [L2_sub[k, 1], R2_sub[k, 1]])

            # 更新轉身標記
            if draw_turn_markers and det.laps:
                self._update_turn_markers(
                    frame_idx, frame_to_lap, det, C2, num_frames,
                    turn_scatters, empty_points, ax_main
                )

            ax_main.draw_artist(tail_L)
            ax_main.draw_artist(tail_R)
            ax_main.draw_artist(pelvis_line)
            ax_main.draw_artist(head_L)
            ax_main.draw_artist(head_R)

            spd_avg = spd_avg_arr[k] if k < spd_avg_arr.size else float("nan")
            text_time.set_text(f"t = {time_labels[k]} (avg over {avg_window_s:g}s)")
            speed_str = f"{spd_avg:.2f}" if np.isfinite(spd_avg) else "--.--"
            text_speed.set_text(f"speed {speed_str} m/s")
            ax_info.draw_artist(text_time)
            ax_info.draw_artist(text_speed)

            fig.canvas.blit(ax_main.bbox)
            fig.canvas.blit(ax_info.bbox)
            pipe.write_frame_from_canvas(canvas)

    def _update_turn_markers(
        self, frame_idx: int, frame_to_lap: np.ndarray[Any, Any], det,
        C2: np.ndarray[Any, Any], num_frames: int, turn_scatters: dict[str, Any],
        empty_points: np.ndarray[Any, Any], ax_main
    ) -> None:
        """更新轉身標記位置。"""
        lap_id_mark = frame_to_lap[frame_idx]
        if 0 <= lap_id_mark < len(det.laps):
            lap = det.laps[lap_id_mark]

            def _get_point(idx: int) -> np.ndarray[Any, Any] | None:
                return C2[idx] if 0 <= idx < num_frames else None

            pts = {
                "cone_start": _get_point(int(lap.idx_turn_cone_start)),
                "cone_end": _get_point(int(lap.idx_turn_cone_end)),
                "chair_start": _get_point(int(lap.idx_turn_chair_start)),
                "chair_end": _get_point(int(lap.idx_turn_chair_end)),
            }

            for key, scatter in turn_scatters.items():
                pt = pts.get(key)
                scatter.set_offsets(np.asarray(pt)[None, :] if pt is not None else empty_points)
                ax_main.draw_artist(scatter)
        else:
            for scatter in turn_scatters.values():
                scatter.set_offsets(empty_points)
