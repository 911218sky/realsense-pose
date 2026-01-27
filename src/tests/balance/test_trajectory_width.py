"""軌跡寬度分析測試腳本。

分析走圈軌跡的寬度（左右偏移範圍），用於評估步態穩定性。

使用方法：
    python -m src.tests.balance.test_trajectory_width
"""

import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

from ...rehab_analyzer import RehabilitationSessionAnalyzer


def compute_trajectory_width(
    analyzer: RehabilitationSessionAnalyzer,
    projection: str = "xz",
) -> dict:
    """計算軌跡寬度統計。
    
    Args:
        analyzer: 分析器實例
        projection: 投影平面 ('xz' 或 'xy')
    
    Returns:
        包含軌跡寬度統計的字典
    """
    # 取得髖部中心軌跡
    l2, r2, valid = analyzer._compute_hip_points(projection=projection)
    center = (l2 + r2) / 2  # 髖部中心 (N, 2)
    center = center[valid]
    
    if len(center) < 10:
        return {"error": "Not enough valid data"}
    
    # 計算主軸方向（使用 PCA）
    center_mean = np.mean(center, axis=0)
    centered = center - center_mean
    cov = np.cov(centered.T)
    _, eigenvectors = np.linalg.eigh(cov)
    
    # 主軸（最大變異方向）和次軸（垂直方向）
    main_axis = eigenvectors[:, 1]  # 主軸
    perp_axis = eigenvectors[:, 0]  # 垂直軸（寬度方向）
    
    # 投影到主軸和垂直軸
    proj_main = centered @ main_axis  # 沿主軸的位置
    proj_perp = centered @ perp_axis  # 垂直偏移（寬度）
    
    # 計算寬度統計
    width_max = float(np.max(proj_perp))
    width_min = float(np.min(proj_perp))
    width_range = width_max - width_min
    width_std = float(np.std(proj_perp))
    width_mean = float(np.mean(np.abs(proj_perp)))
    
    return {
        "center": center,
        "center_mean": center_mean,
        "main_axis": main_axis,
        "perp_axis": perp_axis,
        "proj_main": proj_main,
        "proj_perp": proj_perp,
        "width_max": width_max,
        "width_min": width_min,
        "width_range": width_range,
        "width_std": width_std,
        "width_mean_abs": width_mean,
        "length_range": float(np.max(proj_main) - np.min(proj_main)),
    }


def plot_trajectory_width(
    analyzer: RehabilitationSessionAnalyzer,
    result: dict,
    title: str,
    save_path: Path | None = None,
) -> None:
    """繪製軌跡寬度分析圖。
    
    Args:
        analyzer: 分析器實例
        result: compute_trajectory_width 的結果
        title: 圖表標題
        save_path: 儲存路徑（可選）
    """
    if "error" in result:
        print(f"  Error: {result['error']}")
        return
    
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    
    # 1. 軌跡俯視圖
    ax1 = axes[0]
    center = result["center"]
    center_mean = result["center_mean"]
    main_axis = result["main_axis"]
    perp_axis = result["perp_axis"]
    
    ax1.plot(center[:, 0], center[:, 1], 'b-', alpha=0.5, linewidth=0.5, label='Trajectory')
    ax1.scatter(center[0, 0], center[0, 1], c='green', s=100, marker='o', label='Start', zorder=5)
    ax1.scatter(center[-1, 0], center[-1, 1], c='red', s=100, marker='x', label='End', zorder=5)
    
    # 繪製主軸和垂直軸
    scale = result["length_range"] / 2
    ax1.arrow(center_mean[0], center_mean[1], 
              main_axis[0] * scale, main_axis[1] * scale,
              head_width=0.05, head_length=0.02, fc='red', ec='red', label='Main axis')
    ax1.arrow(center_mean[0], center_mean[1],
              perp_axis[0] * scale * 0.3, perp_axis[1] * scale * 0.3,
              head_width=0.05, head_length=0.02, fc='orange', ec='orange', label='Width axis')
    
    ax1.set_xlabel('X (m)')
    ax1.set_ylabel('Z (m)')
    ax1.set_title('Trajectory Top View')
    ax1.legend(loc='upper right', fontsize=8)
    ax1.set_aspect('equal')
    ax1.grid(True, alpha=0.3)
    
    # 2. 寬度隨時間變化
    ax2 = axes[1]
    t = np.arange(len(result["proj_perp"])) / analyzer._estimate_fps()
    ax2.plot(t, result["proj_perp"] * 100, 'b-', linewidth=0.5)  # 轉換為 cm
    ax2.axhline(y=result["width_max"] * 100, color='r', linestyle='--', label=f'Max: {result["width_max"]*100:.1f} cm')
    ax2.axhline(y=result["width_min"] * 100, color='g', linestyle='--', label=f'Min: {result["width_min"]*100:.1f} cm')
    ax2.axhline(y=0, color='k', linestyle='-', alpha=0.3)
    ax2.fill_between(t, result["proj_perp"] * 100, 0, alpha=0.3)
    
    ax2.set_xlabel('Time (s)')
    ax2.set_ylabel('Lateral Offset (cm)')
    ax2.set_title('Lateral Deviation Over Time')
    ax2.legend(loc='upper right', fontsize=8)
    ax2.grid(True, alpha=0.3)
    
    # 3. 寬度分布直方圖
    ax3 = axes[2]
    ax3.hist(result["proj_perp"] * 100, bins=50, edgecolor='black', alpha=0.7)
    ax3.axvline(x=0, color='k', linestyle='-', linewidth=2)
    ax3.axvline(x=result["width_max"] * 100, color='r', linestyle='--', linewidth=2, label=f'Max: {result["width_max"]*100:.1f} cm')
    ax3.axvline(x=result["width_min"] * 100, color='g', linestyle='--', linewidth=2, label=f'Min: {result["width_min"]*100:.1f} cm')
    
    ax3.set_xlabel('Lateral Offset (cm)')
    ax3.set_ylabel('Frequency')
    ax3.set_title('Lateral Offset Distribution')
    ax3.legend(loc='upper right', fontsize=8)
    ax3.grid(True, alpha=0.3)
    
    fig.suptitle(f'{title}\nWidth Range: {result["width_range"]*100:.1f} cm, Std: {result["width_std"]*100:.1f} cm', 
                 fontsize=12, fontweight='bold')
    
    plt.tight_layout()
    
    if save_path:
        save_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(save_path), dpi=150, bbox_inches='tight')
        print(f"  Saved: {save_path}")
    
    plt.close(fig)


def main() -> None:
    files = [
        ("data/npy/1_1_1031.npy", "中風患者"),
        ("data/npy/4_1_1208.npy", "正常人"),
        ("data/npy/1_1_607.npy", "正常人"),
    ]
    
    out_dir = Path("outputs/trajectory_width")
    
    print("\n" + "=" * 70)
    print("軌跡寬度分析 - 用於評估步態穩定性")
    print("=" * 70)
    
    all_results = []
    
    for path, label in files:
        print(f"\n=== {path} ({label}) ===")
        analyzer = RehabilitationSessionAnalyzer(path)
        
        result = compute_trajectory_width(analyzer)
        result["path"] = path
        result["label"] = label
        all_results.append(result)
        
        if "error" not in result:
            print(f"  軌跡長度: {result['length_range']:.2f} m")
            print(f"  最大右偏: {result['width_max']*100:.1f} cm")
            print(f"  最大左偏: {result['width_min']*100:.1f} cm")
            print(f"  總寬度範圍: {result['width_range']*100:.1f} cm")
            print(f"  寬度標準差: {result['width_std']*100:.1f} cm")
            print(f"  平均絕對偏移: {result['width_mean_abs']*100:.1f} cm")
            
            # 繪製圖表
            prefix = Path(path).stem
            # 使用英文標籤避免字體問題
            label_en = "Stroke" if "中風" in label else "Normal"
            save_path = out_dir / f"{prefix}_trajectory_width.png"
            plot_trajectory_width(analyzer, result, f"{prefix} ({label_en})", save_path)
    
    # 比較摘要
    print("\n" + "=" * 70)
    print("比較摘要")
    print("=" * 70)
    print(f"{'File':<25} {'Label':<10} {'Width(cm)':<12} {'Std(cm)':<10} {'AbsMean(cm)':<12}")
    print("-" * 70)
    
    for r in all_results:
        if "error" not in r:
            name = Path(r["path"]).stem
            print(f"{name:<25} {r['label']:<10} {r['width_range']*100:>8.1f}     {r['width_std']*100:>6.1f}     {r['width_mean_abs']*100:>8.1f}")
    
    # 建立基準值
    normal_results = [r for r in all_results if "正常人" in r["label"] and "error" not in r]
    if normal_results:
        print("\n" + "=" * 70)
        print("正常人基準值（可用於異常檢測）")
        print("=" * 70)
        
        widths = [r["width_range"] for r in normal_results]
        stds = [r["width_std"] for r in normal_results]
        
        print(f"  寬度範圍: {np.mean(widths)*100:.1f} ± {np.std(widths)*100:.1f} cm")
        print(f"  寬度標準差: {np.mean(stds)*100:.1f} ± {np.std(stds)*100:.1f} cm")
        print(f"  建議異常閾值: > {(np.mean(widths) + 2*np.std(widths))*100:.1f} cm")


if __name__ == "__main__":
    main()
