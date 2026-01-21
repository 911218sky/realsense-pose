"""測試 swing_info_heatmap 是否有問題"""

from ...rehab_analyzer import RehabilitationSessionAnalyzer
from ...rehab_analyzer.visualizer import RehabSummaryVisualizer


def main() -> None:
    files = [
        ("data/npy/1_1_1031.npy", "1_1_1031_stroke"),
        ("data/npy/4_1_1208.npy", "4_1_1208_normal"),
        ("data/npy/1_1_607.npy", "1_1_607_normal"),
    ]

    for path, label in files:
        print(f"\n{'='*60}")
        print(f"處理: {path} ({label})")
        print('='*60)
        
        # 使用 RehabilitationSessionAnalyzer 計算步態摘要
        analyzer = RehabilitationSessionAnalyzer(path)
        summary = analyzer.compute_gait_summary()
        print(f"Left cycles: {len(summary.left_cycles)}, Right cycles: {len(summary.right_cycles)}")
        
        # 使用 RehabSummaryVisualizer 生成 heatmap
        visualizer = RehabSummaryVisualizer(
            npy_path=path,
            out_dir="outputs/test_swing",
            prefix=label,
        )
        
        visualizer.save_swing_info_heatmap(
            projection="xz",
            smooth_window_s=2.0,
            flat_frac=0.3,
            min_v_abs=0.1,
        )
        print(f"Heatmap 已儲存")
        
        # 檢查數據是否都一樣
        if summary.left_cycles:
            left_swings = [c.swing_pct for c in summary.left_cycles[:10]]
            print(f"Left swing % (前10個): {[f'{x:.1f}' for x in left_swings]}")
            
            # 檢查是否所有值都一樣
            if len(set(left_swings)) == 1:
                print("⚠ WARNING: 所有 left swing 值都一樣！")
            else:
                print(f"✓ Left swing 有變化，範圍: {min(left_swings):.1f}% ~ {max(left_swings):.1f}%")
        
        if summary.right_cycles:
            right_swings = [c.swing_pct for c in summary.right_cycles[:10]]
            print(f"Right swing % (前10個): {[f'{x:.1f}' for x in right_swings]}")
            
            # 檢查是否所有值都一樣
            if len(set(right_swings)) == 1:
                print("⚠ WARNING: 所有 right swing 值都一樣！")
            else:
                print(f"✓ Right swing 有變化，範圍: {min(right_swings):.1f}% ~ {max(right_swings):.1f}%")

    print("\n" + "="*60)
    print("測試完成")
    print("="*60)


if __name__ == "__main__":
    main()
