"""錨點（椅子/錐子）偵測模組。

提供從行走軌跡估算椅子和錐子位置的功能。
使用 PCA 方法分析軌跡，準確度高（誤差 < 0.06m）。
使用 Mixin 模式讓 PoseProcessor 可以繼承此功能。
"""

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional, Tuple

import numpy as np

@dataclass
class AnchorConfig:
    """錨點配置資料結構。
    
    Attributes:
        chair_pos: 椅子位置 (x, z)
        cone_pos: 錐子位置 (x, z)
        chair_radius: 椅子區域半徑 (enter, exit)
        cone_radius: 錐子區域半徑 (enter, exit)
        confidence: 偵測信心度 (0.0-1.0)
        metadata: 額外的元資料
    """
    chair_pos: Tuple[float, float] = (0.0, 0.0)
    cone_pos: Tuple[float, float] = (0.0, 0.0)
    chair_radius: Tuple[float, float] = (0.5, 0.7)
    cone_radius: Tuple[float, float] = (0.5, 0.7)
    confidence: float = 0.0
    metadata: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """轉換為字典格式。"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "AnchorConfig":
        """從字典建立配置。"""
        return cls(
            chair_pos=tuple(data.get("chair_pos", (0.0, 0.0))),
            cone_pos=tuple(data.get("cone_pos", (0.0, 0.0))),
            chair_radius=tuple(data.get("chair_radius", (0.5, 0.7))),
            cone_radius=tuple(data.get("cone_radius", (0.5, 0.7))),
            confidence=data.get("confidence", 0.0),
            metadata=data.get("metadata", {}),
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
                config.metadata["config_path"] = str(config_path)
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
    ) -> Tuple[Tuple[float, float], Tuple[float, float], float]:
        """從軌跡推算椅子和錐子位置，並計算信心度。
        
        使用 Y 高度變化識別椅子（坐下時 Y 變化大）。
        錐子位置使用轉彎區域的中心點（使用者繞過錐子的位置）。
        
        Returns:
            (chair_pos, cone_pos, confidence)
            confidence: 0.0-1.0，基於多個指標計算
        """
        traj_2d = trajectory[:, [0, 2]] if trajectory.shape[1] == 3 else trajectory
        y_height = trajectory[:, 1] if trajectory.shape[1] == 3 else None
        
        n_points = len(traj_2d)
        
        # PCA 找主軸方向
        centered = traj_2d - np.mean(traj_2d, axis=0)
        _, S, Vt = np.linalg.svd(centered, full_matrices=False)
        proj = centered @ Vt[0]
        
        # 計算 PCA 解釋變異比例（第一主成分）
        explained_variance_ratio = S[0]**2 / np.sum(S**2) if len(S) > 0 else 0.0
        
        # 找出軌跡的兩個極端區域（椅子端和錐子端）
        p5, p95 = np.percentile(proj, [5, 95])
        mask_chair_end = proj >= p95 - 0.1  # 椅子端（較大的投影值）
        mask_cone_end = proj <= p5 + 0.1    # 錐子端（較小的投影值）
        
        chair_end_center = np.mean(traj_2d[mask_chair_end], axis=0)
        cone_end_center = np.mean(traj_2d[mask_cone_end], axis=0)
        
        # 計算 X 軸對齊度（兩端點 X 軸偏移）
        x_offset = abs(chair_end_center[0] - cone_end_center[0])
        z_distance = abs(chair_end_center[1] - cone_end_center[1])
        alignment_score = 1.0 - min(x_offset / max(z_distance, 0.1), 1.0)
        
        # 用 Y 高度變化判斷椅子端
        chair_detection_confidence = 0.5  # 預設中等信心
        chair_is_high_proj = True  # 預設椅子在高投影值端
        
        if y_height is not None:
            y_std_chair = np.std(y_height[mask_chair_end]) if np.sum(mask_chair_end) > 1 else 0
            y_std_cone = np.std(y_height[mask_cone_end]) if np.sum(mask_cone_end) > 1 else 0
            
            # Y 高度差異比例越大，信心度越高
            y_ratio = max(y_std_chair, y_std_cone) / (min(y_std_chair, y_std_cone) + 1e-6)
            chair_detection_confidence = min(y_ratio / 2.0, 1.0)  # 比例 2.0 以上為滿分
            
            if y_std_chair > y_std_cone * 1.2:
                # 高投影值端的 Y 變化大 → 椅子在高投影值端
                chair_is_high_proj = True
            elif y_std_cone > y_std_chair * 1.2:
                # 低投影值端的 Y 變化大 → 椅子在低投影值端
                chair_is_high_proj = False
            else:
                # Y 高度差異不明顯，用軌跡起點/終點判斷
                start_pos = np.mean(traj_2d[:10], axis=0)
                end_pos = np.mean(traj_2d[-10:], axis=0)
                
                # 椅子端：起點和終點都應該接近
                dist_chair_to_start = np.linalg.norm(chair_end_center - start_pos)
                dist_chair_to_end = np.linalg.norm(chair_end_center - end_pos)
                dist_cone_to_start = np.linalg.norm(cone_end_center - start_pos)
                dist_cone_to_end = np.linalg.norm(cone_end_center - end_pos)
                
                max_dist_chair = max(dist_chair_to_start, dist_chair_to_end)
                max_dist_cone = max(dist_cone_to_start, dist_cone_to_end)
                
                # 選擇距離起點和終點都較近的那一端作為椅子
                chair_is_high_proj = max_dist_chair < max_dist_cone
                chair_detection_confidence *= 0.8  # 稍微降低信心度
        else:
            # 沒有 Y 高度資訊，用軌跡起點/終點判斷
            start_pos = np.mean(traj_2d[:10], axis=0)
            end_pos = np.mean(traj_2d[-10:], axis=0)
            
            dist_chair_to_start = np.linalg.norm(chair_end_center - start_pos)
            dist_chair_to_end = np.linalg.norm(chair_end_center - end_pos)
            dist_cone_to_start = np.linalg.norm(cone_end_center - start_pos)
            dist_cone_to_end = np.linalg.norm(cone_end_center - end_pos)
            
            max_dist_chair = max(dist_chair_to_start, dist_chair_to_end)
            max_dist_cone = max(dist_cone_to_start, dist_cone_to_end)
            
            chair_is_high_proj = max_dist_chair < max_dist_cone
            chair_detection_confidence = 0.7  # 沒有 Y 資訊，信心度較低
        
        # 確定椅子位置
        if chair_is_high_proj:
            chair_pos = tuple(chair_end_center)
            cone_region_mask = proj <= p5 + 0.5  # 錐子端的轉彎區域（擴大範圍）
        else:
            chair_pos = tuple(cone_end_center)
            cone_region_mask = proj >= p95 - 0.5  # 錐子端的轉彎區域（擴大範圍）
        
        # 關鍵修正：錐子位置應該是轉彎區域的中心點
        # 使用者會繞過錐子，所以錐子應該在轉彎區域的中心，而不是端點
        cone_region_points = traj_2d[cone_region_mask]
        if len(cone_region_points) > 10:
            # 直接使用整個轉彎區域的中位數作為錐子位置
            # 中位數比平均值更穩定，不受極端值影響
            cone_pos = tuple(np.median(cone_region_points, axis=0))
        else:
            # 備用方案：使用另一端的中心
            cone_pos = tuple(cone_end_center)
        
        # 綜合信心度計算
        # 1. 軌跡點數量分數（300 幀以上為滿分）
        point_score = min(n_points / 300.0, 1.0)
        
        # 2. PCA 解釋變異比例（0.9 以上為滿分）
        pca_score = min(explained_variance_ratio / 0.9, 1.0)
        
        # 3. X 軸對齊分數
        # alignment_score 已經是 0-1
        
        # 4. 椅子偵測信心度
        # chair_detection_confidence 已經是 0-1
        
        # 加權平均
        confidence = (
            point_score * 0.15 +           # 15% 權重
            pca_score * 0.35 +             # 35% 權重（最重要）
            alignment_score * 0.20 +       # 20% 權重
            chair_detection_confidence * 0.30  # 30% 權重
        )
        
        return chair_pos, cone_pos, float(confidence)
    
    
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