"""
RehabSummaryVisualizer 使用範例

這個文件展示了如何使用 RehabSummaryVisualizer 來生成各種復健分析的可視化圖表。
包含基本使用、進階參數調整、批次處理等範例。

使用方法：
    python -m src.examples.visualizer_examples
"""

# 確保可以 import src 下的模組
import sys
from pathlib import Path
_SRC_DIR = Path(__file__).resolve().parent.parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from rehab_analyzer.visualizer import RehabSummaryVisualizer

if __name__ == "__main__":
    # 範例使用方式：RehabSummaryVisualizer
    
    # 設定輸入檔案路徑和輸出目錄
    # 使用已經處理過並包含錨點配置的檔案
    npy_path = "outputs/4_1_1208_pose.npy"  # 正常人範例
    npy_path = "outputs/1_1_1031_pose.npy"  # 中風患者範例
    npy_path = "outputs/1_1_607_pose.npy"   # 正常人範例
    out_dir = "outputs/visualization_examples"
    prefix = "example"
    
    # 建立可視化器實例
    # axis_convention: "standard" 或 "anatomical"，影響圖表軸標籤顯示
    visualizer = RehabSummaryVisualizer(
        npy_path=npy_path,
        out_dir=out_dir,
        prefix=prefix,
        axis_convention="standard"
    )
    
    print(f"開始處理檔案: {npy_path}")
    print(f"輸出目錄: {out_dir}")
    print("=" * 50)
    
    # 階段耗時分析圖表
    print("生成階段耗時堆疊圖...")
    # 每圈六段耗時堆疊圖（站起→走向錐桶→轉身→返回→對準坐下→坐下）
    visualizer.save_stage_durations_image(
        projection="xz",  # 投影平面：xz, xy, yz
        smooth_window_s=2.0,  # 平滑窗口（秒）
        flat_frac=0.3,  # 平坦區間比例
        min_v_abs=0.1,  # 最小速度閾值
    )
    print("   ✓ 階段耗時圖已生成")

    # 分鐘統計圖表
    print("生成分鐘統計圖表...")
    # 每分鐘階段耗時統計
    visualizer.save_minutely_stage_duration_bars(
        projection="xz",
        smooth_window_s=2.0,
        flat_frac=0.3,
        min_v_abs=0.1,
    )
    print("   ✓ 分鐘階段耗時統計已生成")
    
    # 每分鐘步頻和步長統計
    visualizer.save_minutely_cadence_step_length_bars(
        projection="xz",
        smooth_window_s=2.0,
        flat_frac=0.3,
        min_v_abs=0.1,
    )
    print("   ✓ 分鐘步頻步長統計已生成")
    
    # 每分鐘站立/擺動期統計
    visualizer.save_minutely_stance_swing_bars(
        projection="xz",
        smooth_window_s=2.0,
        flat_frac=0.3,
        min_v_abs=0.1,
    )
    print("   ✓ 分鐘站立擺動期統計已生成")
    
    # 軌跡影片輸出
    print("生成軌跡影片...")
    # Top-down 行走軌跡影片 - 使用最簡單的參數
    visualizer.save_trajectory_video(
        projection="xz",
        smooth_window_s=1.0,
        flat_frac=0.3,
        min_v_abs=0.1,
        rotate_180=False,
        draw_radius=True,
    )
    print("   ✓ 軌跡影片已生成")
    
    # 速度熱力圖
    print("生成速度熱力圖...")
    # 時空速度熱力圖 - 移除不支援的參數
    visualizer.save_spatiotemporal_speed_heatmap(
        projection="xz",
        smooth_window_s=2.0,
        flat_frac=0.3,
        min_v_abs=0.1,
        width=300,
    )
    print("   ✓ 速度熱力圖已生成")

    # 擺動資訊熱力圖
    print("生成擺動資訊熱力圖...")
    # 擺動期資訊熱力圖 - 移除不支援的 grid_size 參數
    visualizer.save_swing_info_heatmap(
        projection="xz",
        smooth_window_s=2.0,
        flat_frac=0.3,
        min_v_abs=0.1,
    )
    print("   ✓ 擺動資訊熱力圖已生成")
    
    # 步態搖擺時間軸圖
    print("生成步態搖擺時間軸圖...")
    # 左右腳平均步態週期圖（顯示雙支撐期、單支撐期、擺動期百分比）
    visualizer.save_gait_swing_timeline(
        projection="xz",
        smooth_window_s=2.0,
        flat_frac=0.3,
        min_v_abs=0.1,
    )
    print("   ✓ 步態搖擺時間軸圖已生成")
    
    # 步態變異性與對稱性圖表
    print("生成步態變異性與對稱性圖表...")
    # 顯示對稱性指標 (SI) 和變異係數 (CV)
    visualizer.save_gait_variability_chart(
        projection="xz",
        smooth_window_s=2.0,
        flat_frac=0.3,
        min_v_abs=0.1,
    )
    print("   ✓ 步態變異性與對稱性圖表已生成")
    
    # 每分鐘速度與圈數趨勢圖
    print("生成每分鐘速度與圈數趨勢圖...")
    # 上圖：每分鐘平均速度 (m/s)，下圖：每分鐘完成圈數
    visualizer.save_minutely_trend_chart(
        projection="xz",
        smooth_window_s=2.0,
        flat_frac=0.3,
        min_v_abs=0.1,
    )
    print("   ✓ 每分鐘速度與圈數趨勢圖已生成")
    
    # # 側向偏移分析
    # print("生成側向偏移分析...")
    # # 每圈側向偏移分析
    # visualizer.save_per_lap_offset(
    #     projection="xz",
    #     smooth_window_s=2.0,
    #     flat_frac=0.3,
    #     min_v_abs=0.1,
    # )
    # print("   ✓ 側向偏移分析已生成")
    
    # 時頻分析
    print("生成時頻分析...")
    # 空間頻譜分析 - 使用正確的參數
    visualizer.save_spatial_spectrum(
        pair=["xz"],  # 使用 pair 參數而不是 joints
        save_name="spatial_spectrum.png",
        dpi=150,
    )
    print("   ✓ 空間頻譜分析已生成")
    
    # 高度差異分析
    print("生成高度差異分析...")
    # Y 軸高度差異分析（左右關節對比）- 移除不支援的參數
    visualizer.save_y_height_diff(
        left_joint=23,  # 左髖關節
        right_joint=24,  # 右髖關節
        # smooth_window_s=2.0,  # 只保留支援的參數
    )
    print("   ✓ 高度差異分析已生成")
    
    print("=" * 50)
    print("所有可視化範例已完成！")
    print(f"請檢查輸出目錄: {out_dir}")