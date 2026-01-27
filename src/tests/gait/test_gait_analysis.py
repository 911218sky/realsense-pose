"""步態分析測試腳本。

測試三個樣本檔案的步態分析結果。

使用方法：
    python -m src.tests.gait.test_gait_analysis
"""

import numpy as np
from ...rehab_analyzer import RehabilitationSessionAnalyzer


def calc_symmetry_index(left_val: float, right_val: float) -> float:
    """計算對稱性指數 (SI)。
    
    SI = |L - R| / (0.5 * (L + R)) * 100
    完美對稱 = 0%, 越高越不對稱
    """
    avg = (left_val + right_val) / 2
    if avg == 0:
        return 0.0
    return abs(left_val - right_val) / avg * 100


def calc_cv(values: list[float]) -> float:
    """計算變異係數 (CV)。
    
    CV = std / mean * 100
    越低越穩定，正常人通常 < 10%
    """
    if len(values) < 2:
        return 0.0
    mean = np.mean(values)
    if mean == 0:
        return 0.0
    return float(np.std(values) / mean * 100)


def main() -> None:
    files = [
        ("data/npy/1_1_1031.npy", "中風患者"),
        ("data/npy/4_1_1208.npy", "正常人"),
        ("data/npy/1_1_607.npy", "正常人"),
    ]

    for path, label in files:
        print(f"=== {path} ({label}) ===")
        analyzer = RehabilitationSessionAnalyzer(path)

        summary = analyzer.compute_gait_summary()
        print(f"Left cycles: {len(summary.left_cycles)}, Right cycles: {len(summary.right_cycles)}")
        print(f"L SPM: {summary.l_spm:.1f}, R SPM: {summary.r_spm:.1f}")
        print(f"L step length: {summary.l_mean_step_len:.2f}m, R step length: {summary.r_mean_step_len:.2f}m")

        left_phases, right_phases = analyzer.compute_gait_cycle_phases()
        if left_phases:
            print(
                f"L: stance={left_phases.stance_pct:.1f}%, "
                f"swing={left_phases.swing_pct:.1f}%, "
                f"DS={left_phases.ds1_pct + left_phases.ds2_pct:.1f}%, "
                f"SS={left_phases.single_support_pct:.1f}%, "
                f"cycle={left_phases.avg_cycle_time_s:.2f}s (n={left_phases.n_cycles})"
            )
        else:
            print("L: No valid phases")
        if right_phases:
            print(
                f"R: stance={right_phases.stance_pct:.1f}%, "
                f"swing={right_phases.swing_pct:.1f}%, "
                f"DS={right_phases.ds1_pct + right_phases.ds2_pct:.1f}%, "
                f"SS={right_phases.single_support_pct:.1f}%, "
                f"cycle={right_phases.avg_cycle_time_s:.2f}s (n={right_phases.n_cycles})"
            )
        else:
            print("R: No valid phases")
        
        # 對稱性指標
        print("\n--- 對稱性指標 (SI, 0%=完美對稱) ---")
        si_spm = calc_symmetry_index(summary.l_spm, summary.r_spm)
        si_step_len = calc_symmetry_index(summary.l_mean_step_len, summary.r_mean_step_len)
        si_swing = calc_symmetry_index(summary.l_swing_pct_mean, summary.r_swing_pct_mean)
        si_stance = calc_symmetry_index(summary.l_stance_s_mean, summary.r_stance_s_mean)
        print(f"  SPM SI: {si_spm:.1f}%")
        print(f"  Step Length SI: {si_step_len:.1f}%")
        print(f"  Swing SI: {si_swing:.1f}%")
        print(f"  Stance SI: {si_stance:.1f}%")
        
        # 變異係數 (步態穩定性)
        print("\n--- 變異係數 (CV, <10%=穩定) ---")
        l_stride_times = [c.stride_s for c in summary.left_cycles if 0.5 <= c.stride_s <= 3.0]
        r_stride_times = [c.stride_s for c in summary.right_cycles if 0.5 <= c.stride_s <= 3.0]
        l_swing_times = [c.swing_s for c in summary.left_cycles if 0.5 <= c.stride_s <= 3.0]
        r_swing_times = [c.swing_s for c in summary.right_cycles if 0.5 <= c.stride_s <= 3.0]
        
        print(f"  L Stride Time CV: {calc_cv(l_stride_times):.1f}%")
        print(f"  R Stride Time CV: {calc_cv(r_stride_times):.1f}%")
        print(f"  L Swing Time CV: {calc_cv(l_swing_times):.1f}%")
        print(f"  R Swing Time CV: {calc_cv(r_swing_times):.1f}%")
        
        print("\n")


if __name__ == "__main__":
    main()
