"""測試從 bag 檔案偵測錨點。

處理 bag 檔案並驗證深度偵測的錨點是否正確。

使用方法：
    python -m src.tests.lap.test_bag_anchor_detection
"""

from pathlib import Path
import numpy as np

from ...realsense_pose_extractor.processor import PoseProcessor
from ...realsense_pose_extractor.anchor_detector import load_anchor_config
from ...rehab_analyzer import RehabilitationSessionAnalyzer

def process_single_bag(bag_file: str, output_dir: str = "outputs") -> None:
    """處理單個 bag 檔案並驗證錨點。"""
    if not Path(bag_file).exists():
        print(f"  [跳過] bag 檔案不存在: {bag_file}")
        return
    
    print(f"\n{'='*70}")
    print(f"處理: {bag_file}")
    print(f"{'='*70}")
    
    processor = PoseProcessor(
        bag_file_path=bag_file,
        output_dir=output_dir,
    )
    
    arr = processor.process_bag(
        skip_frames=4,
        max_frames=6*60*30,
        save_npy=True,
        save_pickle=False,
        save_video=True,
        detect_anchors=True,
        save_anchors=True,
        progress_interval=500,
    )
    
    print(f"\n處理完成: {len(arr)} 幀")
    
    # 從軌跡推算錨點作為參考
    hip_center = (arr[:, 23, :] + arr[:, 24, :]) / 2
    traj_chair, traj_cone = PoseProcessor._estimate_chair_cone_from_trajectory(hip_center)
    
    print(f"\n軌跡估算結果:")
    print(f"  椅子: ({traj_chair[0]:.2f}, {traj_chair[1]:.2f})")
    print(f"  錐子: ({traj_cone[0]:.2f}, {traj_cone[1]:.2f})")
    
    # 使用 detect_laps_auto 的結果作為參考
    npy_path = Path(output_dir) / f"{Path(bag_file).stem}_pose.npy"
    analyzer = RehabilitationSessionAnalyzer(str(npy_path))
    det = analyzer.detect_laps_auto()
    
    if det and det.laps:
        ref_chair = det.chair_pos
        ref_cone = det.cone_pos
        
        print(f"\ndetect_laps_auto 結果:")
        print(f"  椅子: ({ref_chair[0]:.2f}, {ref_chair[1]:.2f})")
        print(f"  錐子: ({ref_cone[0]:.2f}, {ref_cone[1]:.2f})")
    
    # 檢查保存的錨點配置
    config = load_anchor_config(npy_path)
    if config:
        print(f"\n保存的錨點配置:")
        print(f"  椅子: ({config.chair_pos[0]:.2f}, {config.chair_pos[1]:.2f})")
        print(f"  錐子: ({config.cone_pos[0]:.2f}, {config.cone_pos[1]:.2f})")
        
        # 計算誤差
        chair_error = np.linalg.norm(np.array(config.chair_pos) - np.array(traj_chair))
        cone_error = np.linalg.norm(np.array(config.cone_pos) - np.array(traj_cone))
        
        print(f"\n與軌跡估算的誤差:")
        print(f"  椅子誤差: {chair_error:.3f}m")
        print(f"  錐子誤差: {cone_error:.3f}m")
        
        if chair_error < 0.1 and cone_error < 0.1:
            print(f"  [OK] 誤差極小，錨點偵測準確")
        elif chair_error < 0.5 and cone_error < 0.5:
            print(f"  [OK] 誤差在合理範圍內")
        else:
            print(f"  [WARNING] 誤差較大")
    else:
        print(f"\n[WARNING] 錨點配置未保存")


def main() -> None:
    """主函數：測試所有 bag 檔案。"""
    print("=" * 70)
    print("測試: 批量處理 bag 檔案並偵測錨點")
    print("=" * 70)
    
    bag_files = [
        "dataset/1_1_1031.bag",  # 中風患者
        "dataset/4_1_1208.bag",  # 正常人
        "dataset/1_1_607.bag",   # 正常人
    ]
    
    existing_bags = [f for f in bag_files if Path(f).exists()]
    
    if not existing_bags:
        print("\n[跳過] 沒有找到 bag 檔案")
        return
    
    print(f"\n找到 {len(existing_bags)} 個 bag 檔案:")
    for bag in existing_bags:
        print(f"  - {bag}")
    
    for bag_file in existing_bags:
        try:
            process_single_bag(bag_file)
        except Exception as e:
            print(f"\n[ERROR] 處理 {bag_file} 時發生錯誤: {e}")
    
    print(f"\n{'='*70}")
    print("所有測試完成")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
