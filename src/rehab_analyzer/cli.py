"""復健分析 CLI。"""

import argparse
from pathlib import Path
from typing import Optional

from config import load_config
from utils import ensure_dir
from utils.timing import time_it
from .visualizer import RehabSummaryVisualizer
from .constants import (
    DEFAULT_PROJECTION,
    DEFAULT_SMOOTH_WINDOW_S,
    DEFAULT_FLAT_FRAC,
    DEFAULT_MIN_V_ABS,
)

from logger import setup_logger

logger = setup_logger("rehab_analyzer.cli")


def parse_args() -> argparse.Namespace:
    """解析 CLI 參數。"""
    parser = argparse.ArgumentParser(
        description="復健分析 CLI",
    )
    # 輸入姿態資料（.npy）
    parser.add_argument(
        "--npy",
        help="Path to input .npy file containing pose data",
    )
    # 輸出目錄
    parser.add_argument(
        "--output",
        help="Output directory for results",
    )
    # YAML 設定檔路徑（可選）
    parser.add_argument(
        "--config",
        help="Optional YAML config file",
    )
    # 輸出檔名前綴 tag
    parser.add_argument(
        "--tag",
        help="Prefix tag to be added to all output file names",
    )
    return parser.parse_args()


def main(args: Optional[argparse.Namespace] = None) -> None:
    """CLI 進入點，載入設定並執行分析與繪圖。"""
    args = args or parse_args()

    cfg = load_config(path=args.config, mode="analyzer")

    # CLI 參數優先於 config
    npy_path = args.npy or cfg.get("npy_file_path")
    if not npy_path:
        raise ValueError("npy_file_path is not set")

    out_dir = Path(args.output or cfg.get("output_dir", "./outputs"))
    out_dir = ensure_dir(out_dir)

    tag = args.tag or cfg.get("tag", "")
    axis_convention = cfg.get("axis_convention", "anatomical")

    # 建立可視化/分析主物件
    analyzer = RehabSummaryVisualizer(
        npy_path=npy_path,
        out_dir=str(out_dir),
        prefix=tag,
        axis_convention=axis_convention,
    )

    # 共用參數（多數圖表會共用）
    projection = cfg.get("projection", DEFAULT_PROJECTION)
    smooth_window_s = cfg.get("smooth_window_s")
    if smooth_window_s is None:
        smooth_window_s = cfg.get("smooth_window", DEFAULT_SMOOTH_WINDOW_S)
    flat_frac = cfg.get("flat_frac", DEFAULT_FLAT_FRAC)
    min_v_abs = cfg.get("min_v_abs", DEFAULT_MIN_V_ABS)
    
    save_images = cfg.get("save_images", False)
    
    # 繪製Y高度曲線及差值曲線
    if cfg.get("save_y_height_diff", save_images):
        y_height_diff_cfg = cfg.get("y_height_diff_config", [])
        
        for c in y_height_diff_cfg:
            left_joint = c.get("left_joint", None)
            right_joint = c.get("right_joint", None)
            labels = c.get("labels", None)
            draw_original = c.get("draw_original", True)
            ylim = c.get("ylim", None)
            save_name = c.get("save_name", None)
            
            if left_joint is None or right_joint is None:
                logger.warning(
                    "left_joint or right_joint is not provided, skip save_y_height_diff",
                )
                continue

            time_it(
                analyzer.save_y_height_diff,
                left_joint=left_joint,
                right_joint=right_joint,
                labels=labels,
                smooth_window_s=smooth_window_s,
                draw_original=draw_original,
                ylim=ylim,
                save_name=save_name,
            )
        

    # 空間頻譜 X(Z) / Y(Z)
    if cfg.get("save_spatial_spectrum", save_images):
        ss_cfg = cfg.get("spatial_spectrum_config", {})
        time_it(
            analyzer.save_spatial_spectrum,
            pair=list(ss_cfg.get("pair", ["xz", "yz"])),
            spec_ylim=ss_cfg.get("spec_ylim", None),
            k_smooth=ss_cfg.get("k_smooth", 2),
            top_k=ss_cfg.get("top_k", None),
            dpi=ss_cfg.get("dpi", 150),
            save_name=ss_cfg.get(
                "save_name",
                "{pair}_spatial_spectrum_db.png",
            ),
        )

    # 多系列 FFT
    if cfg.get("save_multi_fft_from_series", save_images):
        mfft_cfg = cfg.get("multi_fft_from_series_config", {})

        time_it(
            analyzer.save_multi_fft_from_series,
            joints=mfft_cfg.get("joints", []),
            labels=mfft_cfg.get("labels", []),
            component=mfft_cfg.get("component", "z"),
            max_peaks=mfft_cfg.get("max_peaks", 3),
            dpi=mfft_cfg.get("dpi", 150),
            figsize=tuple(mfft_cfg.get("figsize", (11.0, 4.0))),
            min_peak_distance_ratio=mfft_cfg.get(
                "min_peak_distance_ratio",
                0.01,
            ),
            min_db=mfft_cfg.get("min_db", -40.0),
            min_freq=mfft_cfg.get("min_freq", 0.05),
            save_name=mfft_cfg.get("save_name", "{joints}_multi_fft.png"),
            xlim=mfft_cfg.get("xlim", None),
            ylim=mfft_cfg.get("ylim", None),
            fft_params=mfft_cfg.get("fft_params", None),
        )

    # 每圈 lateral offset / θ 診斷圖
    if cfg.get("save_per_lap_offset", save_images):
        offset_cfg = cfg.get("per_lap_offset_config", {})
        time_it(
            analyzer.save_per_lap_offset,
            projection=projection,
            smooth_window_s=smooth_window_s,
            flat_frac=flat_frac,
            min_v_abs=min_v_abs,
            k_smooth=offset_cfg.get("k_smooth", 1),
            lat_ylim=offset_cfg.get("lat_ylim", None),
            theta_ylim=offset_cfg.get("theta_ylim", None),
            max_points_plot=offset_cfg.get("max_points_plot", 150),
            show_samples=offset_cfg.get("show_samples", True),
            dpi=offset_cfg.get("dpi", 150),
            save_name=offset_cfg.get(
                "save_name",
                "per_lap/lap_{lap_idx}_diagnostics.png",
            ),
        )

    # 每分鐘步頻/步長柱狀圖
    if cfg.get("save_minutely_cadence_step_length_bars", save_images):
        cadence_cfg = cfg.get("minutely_cadence_step_length_bars_config", {})
        time_it(
            analyzer.save_minutely_cadence_step_length_bars,
            projection=projection,
            smooth_window_s=smooth_window_s,
            flat_frac=flat_frac,
            min_v_abs=min_v_abs,
            max_minutes=cadence_cfg.get("max_minutes", None),
            dpi=cadence_cfg.get("dpi", 170),
            figsize_per_minute=cadence_cfg.get("figsize_per_minute", 1.0),
            row_height=cadence_cfg.get("row_height", 3.2),
            bar_width=cadence_cfg.get("bar_width", 0.28),
            capsize=cadence_cfg.get("capsize", 3.0),
            spm_ylim=cadence_cfg.get("spm_ylim", None),
            steplen_ylim=cadence_cfg.get("steplen_ylim", None),
            save_name=cadence_cfg.get(
                "save_name",
                "minutely_cadence_step_length_bars.png",
            ),
        )

    # 每分鐘站立/擺動時間柱狀圖
    if cfg.get("save_minutely_stance_swing_bars", save_images):
        stance_cfg = cfg.get("minutely_stance_swing_bars_config", {})
        time_it(
            analyzer.save_minutely_stance_swing_bars,
            projection=projection,
            smooth_window_s=smooth_window_s,
            flat_frac=flat_frac,
            min_v_abs=min_v_abs,
            max_minutes=stance_cfg.get("max_minutes", None),
            dpi=stance_cfg.get("dpi", 170),
            figsize_per_minute=stance_cfg.get("figsize_per_minute", 0.9),
            row_height=stance_cfg.get("row_height", 3.1),
            bar_width=stance_cfg.get("bar_width", 0.28),
            group_gap=stance_cfg.get("group_gap", 0.18),
            capsize=stance_cfg.get("capsize", 3.0),
            stance_ylim=stance_cfg.get("stance_ylim", None),
            swing_ylim=stance_cfg.get("swing_ylim", None),
            save_name=stance_cfg.get(
                "save_name",
                "minutely_stance_swing_bars.png",
            ),
        )

    # 每分鐘左右擺動百分比/秒數熱力圖
    if cfg.get("save_swing_info_heatmap", save_images):
        swing_cfg = cfg.get("swing_info_heatmap_config", {})
        time_it(
            analyzer.save_swing_info_heatmap,
            projection=projection,
            smooth_window_s=smooth_window_s,
            flat_frac=flat_frac,
            min_v_abs=min_v_abs,
            vmin_pct=swing_cfg.get("vmin_pct", None),
            vmax_pct=swing_cfg.get("vmax_pct", None),
            dpi=swing_cfg.get("dpi", 150),
            save_name=swing_cfg.get(
                "save_name",
                "swing_info_heatmap.png",
            ),
        )

    # 每分鐘三段(去程/迴轉/回程)耗時柱狀圖
    if cfg.get("save_minutely_stage_duration_bars", save_images):
        stage_cfg = cfg.get("minutely_stage_duration_bars_config", {})
        time_it(
            analyzer.save_minutely_stage_duration_bars,
            projection=projection,
            smooth_window_s=smooth_window_s,
            flat_frac=flat_frac,
            min_v_abs=min_v_abs,
            max_minutes=stage_cfg.get("max_minutes", None),
            dpi=stage_cfg.get("dpi", 170),
            figsize_per_minute=stage_cfg.get("figsize_per_minute", 0.75),
            bar_width=stage_cfg.get("bar_width", 0.22),
            group_gap=stage_cfg.get("group_gap", 0.06),
            ylim=stage_cfg.get("ylim", None),
            save_name=stage_cfg.get(
                "save_name",
                "minutely_stage_duration_bars.png",
            ),
        )

    # 每圈速度時空熱圖
    if cfg.get("save_speed_heatmap", save_images):
        heat_cfg = cfg.get("speed_heatmap_config", {})
        time_it(
            analyzer.save_spatiotemporal_speed_heatmap,
            projection=projection,
            smooth_window_s=smooth_window_s,
            flat_frac=flat_frac,
            min_v_abs=min_v_abs,
            width=heat_cfg.get("width", 300),
            dpi=heat_cfg.get("dpi", 150),
            vmin=heat_cfg.get("vmin", None),
            vmax=heat_cfg.get("vmax", None),
            save_name=heat_cfg.get(
                "save_name",
                "speed_heatmap.png",
            ),
        )

    # 每圈六段耗時堆疊橫條圖
    if cfg.get("save_stage_durations_image", save_images):
        sd_cfg = cfg.get("save_stage_durations_image_config", {})
        time_it(
            analyzer.save_stage_durations_image,
            projection=projection,
            smooth_window_s=smooth_window_s,
            flat_frac=flat_frac,
            min_v_abs=min_v_abs,
            dpi=sd_cfg.get("dpi", 190),
            show_seconds=sd_cfg.get("show_seconds", True),
            show_meters=sd_cfg.get("show_meters", True),
            row_height=sd_cfg.get("row_height", 1),
            bar_height=sd_cfg.get("bar_height", 0.5),
            min_width_sec=sd_cfg.get("min_width_sec", 0.5),
            meters_gap=sd_cfg.get("meters_gap", 0.08),
            min_meters_to_show=sd_cfg.get("min_meters_to_show", 0.03),
            save_name=sd_cfg.get(
                "save_name",
                "minutely_stage_duration_bars.png",
            ),
        )

    # 軌跡影片輸出（可對多組左右關節生成）
    if cfg.get("save_trajectory_video", save_images):
        tv_cfg = cfg.get("trajectory_video_config", {})
        joints_cfg = tv_cfg.get("joints", [])

        for joint_pair in joints_cfg:
            left_joint = joint_pair.get("left_joint", None)
            right_joint = joint_pair.get("right_joint", None)

            # 若設定不完整則略過
            if left_joint is None or right_joint is None:
                logger.warning(
                    "left_joint or right_joint is None, skip save_trajectory_video",
                )
                continue

            time_it(
                analyzer.save_trajectory_video,
                time_it_label=f"save_trajectory_video_{left_joint}_{right_joint}",
                # 左右關節索引
                left_joint=left_joint,
                right_joint=right_joint,
                save_name=joint_pair.get(
                    "save_name",
                    "trajectory_{left_joint}_{right_joint}.mp4",
                ),
                # 共用參數
                projection=projection,
                smooth_window_s=smooth_window_s,
                flat_frac=flat_frac,
                min_v_abs=min_v_abs,
                dpi=tv_cfg.get("dpi", 110),
                figsize=tuple(tv_cfg.get("figsize", (7.6, 7.2))),
                fps_out=tv_cfg.get("fps_out", 24),
                speed=tv_cfg.get("speed", 1.0),
                ffmpeg_preset=tv_cfg.get("ffmpeg_preset", "veryfast"),
                ffmpeg_crf=tv_cfg.get("ffmpeg_crf", 28),
                draw_radius=tv_cfg.get("draw_radius", True),
                draw_turn_markers=tv_cfg.get("draw_turn_markers", True),
                rotate_180=joint_pair.get("rotate_180", tv_cfg.get("rotate_180", True)),
            )


if __name__ == "__main__":
    main()