"""錨點（椅子/錐子）偵測模組。

提供從行走軌跡估算椅子和錐子位置的功能。
使用 PCA 方法分析軌跡，準確度高（誤差 < 0.06m）。
使用 Mixin 模式讓 PoseProcessor 可以繼承此功能。
"""

import json
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Optional, Tuple

import numpy as np

from config import load_config

# 載入預設配置
_default_config = load_config(mode="pose")

def _get_default_chair_radius() -> Tuple[float, float]:
    """從配置文件獲取椅子半徑預設值。"""
    radius = _default_config.get("chair_radius", [1.5, 1.7])
    return tuple(radius)

def _get_default_cone_radius() -> Tuple[float, float]:
    """從配置文件獲取錐桶半徑預設值。"""
    radius = _default_config.get("cone_radius", [1.5, 1.7])
    return tuple(radius)

@dataclass
class AnchorConfig:
    """錨點配置資料結構。
    
    Attributes:
        chair_pos: 椅子位置 (x, z)
        cone_pos: 錐子位置 (x, z)
        chair_radius: 椅子區域半徑 (enter, exit)
        cone_radius: 錐子區域半徑 (enter, exit)
    """
    chair_pos: Tuple[float, float] = (0.0, 0.0)
    cone_pos: Tuple[float, float] = (0.0, 0.0)
    chair_radius: Tuple[float, float] = field(default_factory=_get_default_chair_radius)
    cone_radius: Tuple[float, float] = field(default_factory=_get_default_cone_radius)

    def to_dict(self) -> dict:
        """轉換為字典格式。"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "AnchorConfig":
        """從字典建立配置。"""
        return cls(
            chair_pos=tuple(data.get("chair_pos", (0.0, 0.0))),
            cone_pos=tuple(data.get("cone_pos", (0.0, 0.0))),
            chair_radius=tuple(data.get("chair_radius", _get_default_chair_radius())),
            cone_radius=tuple(data.get("cone_radius", _get_default_cone_radius())),
        )


def load_anchor_config(npy_path: Path | str) -> Optional[AnchorConfig]:
    """從配置檔載入錨點配置。
    
    搜尋順序：
    1. {npy_path}.anchors.json
    2. {npy_dir}/anchors.json
    3. configs/anchors/{stem}.json
    """
    npy_path = Path(npy_path)
    stem = npy_path.stem
    
    search_paths = [
        npy_path.with_suffix(npy_path.suffix + ".anchors.json"),
        npy_path.parent / "anchors.json",
        Path("configs/anchors") / f"{stem}.json",
    ]
    
    for config_path in search_paths:
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                config = AnchorConfig.from_dict(data)
                return config
            except Exception:
                continue
    return None


def save_anchor_config(
    npy_path: Path | str,
    config: AnchorConfig,
    save_mode: str = "alongside",
) -> Path:
    """儲存錨點配置。
    
    Args:
        npy_path: npy 檔案路徑
        config: 錨點配置
        save_mode: "alongside" 或 "central"
    """
    npy_path = Path(npy_path)
    
    if save_mode == "central":
        config_dir = Path("configs/anchors")
        config_dir.mkdir(parents=True, exist_ok=True)
        config_path = config_dir / f"{npy_path.stem}.json"
    else:
        config_path = npy_path.with_suffix(npy_path.suffix + ".anchors.json")
    
    # 轉換 numpy 類型為 Python 原生類型
    def convert_to_native(obj: Any):
        if isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, dict):
            return {k: convert_to_native(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [convert_to_native(item) for item in obj]
        return obj
    
    data = convert_to_native(config.to_dict())
    
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    return config_path



class AnchorDetectorMixin:
    """錨點偵測 Mixin，提供從軌跡估算椅子/錐子位置的功能。
    
    使用 PCA 方法分析行走軌跡，自動識別椅子和錐子位置。
    此方法準確度高（誤差 < 0.06m），不受深度相機限制。
    
    此 Mixin 設計用於被 PoseProcessor 繼承。
    """
    
    _anchor_config: Optional[AnchorConfig]
    
    def _init_anchor_detection(self) -> None:
        """初始化錨點偵測狀態。"""
        self._anchor_config = None
    
    @staticmethod
    def _estimate_anchors_from_trajectory(
        trajectory: np.ndarray,
        method: str = "pca",
    ) -> Tuple[Tuple[float, float], Tuple[float, float]]:
        """從軌跡推算錨點位置。
        
        Args:
            trajectory: 軌跡點 (N, 2) 或 (N, 3)
            method: "pca" 或 "minmax"
        """
        traj_2d = trajectory[:, [0, 2]] if trajectory.shape[1] == 3 else trajectory
        
        if method == "pca":
            centered = traj_2d - np.mean(traj_2d, axis=0)
            _, _, Vt = np.linalg.svd(centered, full_matrices=False)
            proj = centered @ Vt[0]
            p5, p95 = np.percentile(proj, [5, 95])
            anchor_a = np.mean(traj_2d[proj <= p5 + 0.1], axis=0)
            anchor_b = np.mean(traj_2d[proj >= p95 - 0.1], axis=0)
        else:
            anchor_a = np.min(traj_2d, axis=0)
            anchor_b = np.max(traj_2d, axis=0)
        
        return tuple(anchor_a), tuple(anchor_b)
    
    @staticmethod
    def _estimate_chair_cone_from_trajectory(
        trajectory: np.ndarray,
    ) -> Tuple[Tuple[float, float], Tuple[float, float]]:
        """從軌跡推算椅子和錐子位置。
        
        使用 Y 高度變化識別椅子（坐下時 Y 變化大）。
        錐子位置使用轉彎區域的中心點（使用者繞過錐子的位置）。
        
        Returns:
            (chair_pos, cone_pos)
        """
        # 提取 2D 軌跡 (X, Z) 和 Y 高度
        traj_2d = trajectory[:, [0, 2]]
        y_height = trajectory[:, 1]
        
        # 使用 PCA 找出軌跡主軸方向
        centered = traj_2d - np.mean(traj_2d, axis=0)
        _, _, Vt = np.linalg.svd(centered, full_matrices=False)
        proj = centered @ Vt[0]  # 投影到主軸
        
        # 找出軌跡兩端（椅子端和錐子端）
        p5, p95 = np.percentile(proj, [5, 95])
        mask_high_end = proj >= p95 - 0.1  # 高投影值端
        mask_low_end = proj <= p5 + 0.1    # 低投影值端
        
        high_end_center = np.mean(traj_2d[mask_high_end], axis=0)
        low_end_center = np.mean(traj_2d[mask_low_end], axis=0)
        
        # 判斷哪一端是椅子（使用 Y 高度變化）
        # 計算兩端的 Y 高度標準差
        y_std_high = np.std(y_height[mask_high_end])
        y_std_low = np.std(y_height[mask_low_end])
        
        # Y 變化大的那一端是椅子（因為坐下起立會有高度變化）
        if y_std_high > y_std_low * 1.2:
            chair_is_high_end = True
        elif y_std_low > y_std_high * 1.2:
            chair_is_high_end = False
        else:
            # Y 高度差異不明顯，用起點/終點判斷
            # 椅子端應該同時接近起點和終點
            start_pos = np.mean(traj_2d[:10], axis=0)
            end_pos = np.mean(traj_2d[-10:], axis=0)
            
            dist_high_max = max(
                np.linalg.norm(high_end_center - start_pos),
                np.linalg.norm(high_end_center - end_pos)
            )
            dist_low_max = max(
                np.linalg.norm(low_end_center - start_pos),
                np.linalg.norm(low_end_center - end_pos)
            )
            
            chair_is_high_end = dist_high_max < dist_low_max
        
        # 確定椅子位置和錐子區域
        if chair_is_high_end:
            chair_pos = tuple(high_end_center)
            cone_region_mask = proj <= p5 + 0.6  # 錐子在低投影值端
        else:
            chair_pos = tuple(low_end_center)
            cone_region_mask = proj >= p95 - 0.6  # 錐子在高投影值端
        
        # 計算錐子位置（轉彎區域的中心）
        cone_region_points = traj_2d[cone_region_mask]
        
        if len(cone_region_points) > 10:
            # 找到 Z 值的 80 百分位（轉彎開始位置）
            z_values = cone_region_points[:, 1]
            z_target = np.percentile(z_values, 80)
            
            # 選取 Z 值接近目標的點（±0.2m）
            near_target_mask = np.abs(z_values - z_target) < 0.2
            near_target_points = cone_region_points[near_target_mask]
            
            if len(near_target_points) > 5:
                # 使用修剪平均值（移除極端值後計算平均）
                x_values = near_target_points[:, 0]
                z_values = near_target_points[:, 1]
                
                # 移除最極端的 20% 點（左右各 10%）
                x_sorted_idx = np.argsort(x_values)
                trim_count = max(1, len(x_values) // 10)
                trimmed_idx = x_sorted_idx[trim_count:-trim_count]
                
                cone_x = np.mean(x_values[trimmed_idx])
                cone_z = np.mean(z_values[trimmed_idx])
                cone_pos = (float(cone_x), float(cone_z))
            else:
                # 使用整個錐子區域的平均值
                cone_pos = tuple(np.mean(cone_region_points, axis=0))
        else:
            # 使用另一端的中心
            cone_pos = tuple(low_end_center if chair_is_high_end else high_end_center)
        
        return chair_pos, cone_pos
    
    
    def _save_anchor_config(
        self,
        npy_path: Path,
        config: Optional[AnchorConfig] = None,
    ) -> Optional[Path]:
        """儲存錨點配置到 npy 檔案旁邊。"""
        config = config or self._anchor_config
        if config is None:
            return None
        
        try:
            anchor_path = save_anchor_config(npy_path, config, save_mode="alongside")
            self.logger.info(f"[Anchor] Config saved to: {anchor_path}")
            return anchor_path
        except Exception as e:
            self.logger.warning(f"[Anchor] Failed to save config: {e}")
            return None