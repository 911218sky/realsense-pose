"""錨點配置測試腳本。

測試從 npy 檔案生成錨點（椅子/錐子）位置配置。

使用方法：
    python -m src.tests.lap.test_anchor_config
"""

import numpy as np
from pathlib import Path

from ...rehab_analyzer import RehabilitationSessionAnalyzer
from ...realsense_pose_extractor.anchor_detector import (
    AnchorConfig,
    AnchorDetectorMixin,
    load_anchor_config,
    save_anchor_config,
)


def test_generate_anchors_from_npy() -> None:
    """測試從 npy 檔案生成錨點配置。"""
    print("=" * 70)
    print("測試 1: 從 npy 檔案生成錨點配置")
    print("=" * 70)
    
    files = [
        ("outputs/1_1_1031_pose.npy", "中風患者"),
        ("outputs/4_1_1208_pose.npy", "正常人"),
        ("outputs/1_1_607_pose.npy", "正常人"),
    ]
    
    for npy_file, label in files:
        if not Path(npy_file).exists():
            print(f"\n跳過不存在的檔案: {npy_file}")
            continue
        
        print(f"\n=== {npy_file} ({label}) ===")
        
        # 載入 npy 檔案
        arr = np.load(npy_file)
        print(f"  載入 npy: {arr.shape[0]} 幀")
        
        # 計算髖部中心軌跡
        hip_center = (arr[:, 23, :] + arr[:, 24, :]) / 2
        
        # 估算錨點
        chair_pos, cone_pos = AnchorDetectorMixin._estimate_chair_cone_from_trajectory(hip_center)
        
        print(f"  軌跡估算結果:")
        print(f"    椅子: ({chair_pos[0]:.2f}, {chair_pos[1]:.2f})")
        print(f"    錐子: ({cone_pos[0]:.2f}, {cone_pos[1]:.2f})")
        
        # 建立並儲存配置
        # AnchorConfig 會自動從 default_pose.yaml 讀取 chair_radius 和 cone_radius
        config = AnchorConfig(
            chair_pos=chair_pos,
            cone_pos=cone_pos,
        )
        
        config_path = save_anchor_config(npy_file, config, save_mode="alongside")
        print(f"  配置已儲存: {config_path}")
        
        # 驗證：使用 RehabilitationSessionAnalyzer 測試
        analyzer = RehabilitationSessionAnalyzer(npy_file)
        det = analyzer.detect_laps_auto()
        
        if det and det.laps:
            print(f"  detect_laps_auto 驗證:")
            print(f"    椅子: ({det.chair_pos[0]:.2f}, {det.chair_pos[1]:.2f})")
            print(f"    錐子: ({det.cone_pos[0]:.2f}, {det.cone_pos[1]:.2f})")
            print(f"    椅子-錐子距離: {det.laps[0].dist_chair_cone_centers_m:.2f}m")
            print(f"    偵測到 {det.num_laps} 圈")


def test_config_save_load() -> None:
    """測試配置儲存和載入。"""
    print("\n" + "=" * 70)
    print("測試 2: 配置儲存和載入")
    print("=" * 70)
    
    npy_file = "outputs/4_1_1208_pose.npy"
    
    if not Path(npy_file).exists():
        print(f"  跳過：檔案不存在 {npy_file}")
        return
    
    # 載入已有的錨點配置
    loaded_config = load_anchor_config(npy_file)
    if loaded_config:
        print(f"  已載入配置:")
        print(f"    椅子: {loaded_config.chair_pos}")
        print(f"    錐子: {loaded_config.cone_pos}")
    else:
        print(f"  未找到配置檔案")


def main() -> None:
    """主函數。"""
    test_generate_anchors_from_npy()
    test_config_save_load()


if __name__ == "__main__":
    main()
