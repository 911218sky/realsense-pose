"""高度不對稱性測試腳本。

測試不同關節點組合的左右高度差異，找出最適合用於步態不平衡監測的點位。

使用方法：
    python -m src.tests.balance.test_height_asymmetry

MediaPipe Pose 關節點索引：
- 11: LEFT_SHOULDER, 12: RIGHT_SHOULDER
- 23: LEFT_HIP, 24: RIGHT_HIP
- 25: LEFT_KNEE, 26: RIGHT_KNEE
- 27: LEFT_ANKLE, 28: RIGHT_ANKLE
- 29: LEFT_HEEL, 30: RIGHT_HEEL
- 31: LEFT_FOOT_INDEX, 32: RIGHT_FOOT_INDEX
"""

import numpy as np
from ...rehab_analyzer import RehabilitationSessionAnalyzer


# 關節點定義
JOINT_PAIRS = {
    "Shoulder": (11, 12),      # 肩膀
    "Hip": (23, 24),           # 髖部
    "Knee": (25, 26),          # 膝蓋
    "Ankle": (27, 28),         # 腳踝
    "Heel": (29, 30),          # 腳跟
    "Toe": (31, 32),           # 腳趾
}


def analyze_height_asymmetry(arr: np.ndarray, joint_name: str, left_idx: int, right_idx: int) -> dict:
    """分析指定關節點的左右高度差異。
    
    Args:
        arr: 姿態數據 (N, 33, 3)
        joint_name: 關節名稱
        left_idx: 左側關節索引
        right_idx: 右側關節索引
    
    Returns:
        包含統計數據的字典
    """
    # Y 軸是高度（MediaPipe 中 Y 向上為負）
    left_y = arr[:, left_idx, 1]
    right_y = arr[:, right_idx, 1]
    
    # 高度差 = 左 - 右（正值表示左側較低/較高取決於座標系）
    diff = left_y - right_y
    
    # 統計指標
    return {
        "joint": joint_name,
        "mean_diff": float(np.mean(diff)),           # 平均差異
        "std_diff": float(np.std(diff)),             # 標準差（變異程度）
        "abs_mean": float(np.mean(np.abs(diff))),    # 絕對值平均
        "max_diff": float(np.max(diff)),             # 最大差異
        "min_diff": float(np.min(diff)),             # 最小差異
        "range": float(np.max(diff) - np.min(diff)), # 範圍
        "cv": float(np.std(diff) / (np.abs(np.mean(diff)) + 1e-9)),  # 變異係數
    }


def main() -> None:
    files = [
        ("data/npy/1_1_1031.npy", "中風患者"),
        ("data/npy/4_1_1208.npy", "正常人"),
        ("data/npy/1_1_607.npy", "正常人"),
    ]

    for path, label in files:
        print(f"\n{'='*60}")
        print(f"=== {path} ({label}) ===")
        print(f"{'='*60}")
        
        analyzer = RehabilitationSessionAnalyzer(path)
        arr = analyzer.arr
        
        print(f"\nData shape: {arr.shape}")
        print(f"Duration: {analyzer.t[-1] - analyzer.t[0]:.1f}s")
        
        # 分析每個關節點組合
        results = []
        for joint_name, (left_idx, right_idx) in JOINT_PAIRS.items():
            result = analyze_height_asymmetry(arr, joint_name, left_idx, right_idx)
            results.append(result)
        
        # 按標準差排序（標準差大 = 變化明顯 = 更適合監測）
        results.sort(key=lambda x: x["std_diff"], reverse=True)
        
        print("\n關節點高度差異分析（按變異程度排序）:")
        print("-" * 80)
        print(f"{'Joint':<12} {'Mean(m)':<12} {'Std(m)':<12} {'AbsMean(m)':<12} {'Range(m)':<12}")
        print("-" * 80)
        
        for r in results:
            print(
                f"{r['joint']:<12} "
                f"{r['mean_diff']:>+.4f}     "
                f"{r['std_diff']:.4f}       "
                f"{r['abs_mean']:.4f}       "
                f"{r['range']:.4f}"
            )
        
        # 推薦
        print("\n推薦用於步態不平衡監測的關節點:")
        top3 = results[:3]
        for i, r in enumerate(top3, 1):
            print(f"  {i}. {r['joint']} (std={r['std_diff']:.4f}m, range={r['range']:.4f}m)")
        
        # 額外分析：組合指標
        print("\n組合高度差異分析:")
        
        # 肩膀-髖部組合（軀幹傾斜）
        shoulder_l, shoulder_r = arr[:, 11, 1], arr[:, 12, 1]
        hip_l, hip_r = arr[:, 23, 1], arr[:, 24, 1]
        trunk_tilt = (shoulder_l - shoulder_r) - (hip_l - hip_r)
        print(f"  軀幹傾斜 (Shoulder-Hip): std={np.std(trunk_tilt):.4f}m")
        
        # 髖部-膝蓋組合（大腿傾斜）
        knee_l, knee_r = arr[:, 25, 1], arr[:, 26, 1]
        thigh_tilt = (hip_l - hip_r) - (knee_l - knee_r)
        print(f"  大腿傾斜 (Hip-Knee): std={np.std(thigh_tilt):.4f}m")
        
        # 膝蓋-腳踝組合（小腿傾斜）
        ankle_l, ankle_r = arr[:, 27, 1], arr[:, 28, 1]
        shank_tilt = (knee_l - knee_r) - (ankle_l - ankle_r)
        print(f"  小腿傾斜 (Knee-Ankle): std={np.std(shank_tilt):.4f}m")
        
        # 骨盆傾斜（髖部左右差）
        pelvis_tilt = hip_l - hip_r
        print(f"  骨盆傾斜 (Hip L-R): std={np.std(pelvis_tilt):.4f}m")


if __name__ == "__main__":
    main()
