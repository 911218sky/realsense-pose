"""MediaPipe 姿態提取與 2D→3D 反投影工具。"""

from typing import List, Optional, Tuple

import mediapipe as mp
import numpy as np
import pyrealsense2 as rs


class PoseOpsMixin:
    """提供姿態座標提取與深度反投影的 mixin 類別。"""

    def _extract_pose_coordinates(
        self,
        results: mp.solutions.pose.PoseLandmark,
        *,
        image_width: int,
        image_height: int,
    ) -> Optional[List[Tuple[int, int]]]:
        """
        從 MediaPipe 結果提取姿態關鍵點的像素座標。

        Args:
            results: MediaPipe Pose 處理結果
            image_width: 影像寬度（像素）
            image_height: 影像高度（像素）

        Returns:
            33 個關鍵點的像素座標 [(x, y), ...]，未偵測到姿態時回傳 None
        """
        if results.pose_landmarks is None:
            return None
        coords = []
        for lm in results.pose_landmarks.landmark:
            # MediaPipe 輸出正規化座標 [0,1]，需轉換為像素座標
            x = int(lm.x * image_width)
            y = int(lm.y * image_height)
            coords.append((x, y))
        return coords
    
    def _get_robust_depth(
        self,
        depth_frame: rs.depth_frame,
        x: int,
        y: int,
        radius: int = 2,
        *,
        min_depth_m: float = 0.1,
        max_depth_m: Optional[float] = 8.0,
    ) -> float:
        """
        取得穩定的深度值，使用周圍像素的中位數降低單點噪聲影響。

        Args:
            depth_frame: RealSense 深度幀
            x: 中心像素 x 座標
            y: 中心像素 y 座標
            radius: 採樣半徑，預設 2 表示 5×5 區域
            min_depth_m: 最小有效深度（公尺）
            max_depth_m: 最大有效深度（公尺），None 表示不限制

        Returns:
            深度值（公尺），無有效深度時回傳 0.0
        """
        # 從 depth_frame 取得實際尺寸，避免越界
        w = int(depth_frame.get_width())
        h = int(depth_frame.get_height())

        depths = []
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h:
                    d = depth_frame.get_distance(nx, ny)
                    if d <= 0:
                        continue
                    # 過濾超出有效範圍的深度值
                    if d < float(min_depth_m):
                        continue
                    if max_depth_m is not None and d > float(max_depth_m):
                        continue
                    depths.append(float(d))

        if not depths:
            return 0.0

        # 中位數對 outlier 更穩健
        med = float(np.median(depths))
        if med < float(min_depth_m):
            return 0.0
        if max_depth_m is not None and med > float(max_depth_m):
            return 0.0
        return med
    
    def _pixel_to_camera_coordinates(
        self,
        pixel_coords: List[Tuple[int, int]],
        depth_frame: rs.depth_frame,
        depth_intrin: rs.intrinsics,
        timestamp: float,
        use_robust_depth: bool = True,
        *,
        min_depth_m: float = 0.1,
        max_depth_m: Optional[float] = 8.0,
    ) -> np.ndarray:
        """
        將像素座標轉換為 3D 相機座標。

        Args:
            pixel_coords: 像素座標列表 [(x, y), ...]
            depth_frame: RealSense 深度幀
            depth_intrin: 深度相機內參
            timestamp: 時間戳（秒）
            use_robust_depth: 是否使用周圍像素中位數取得穩健深度
            min_depth_m: 最小有效深度（公尺）
            max_depth_m: 最大有效深度（公尺）

        Returns:
            shape (34, 3) 的 array，前 33 列為關節點 xyz 座標，
            第 34 列 [0, 0, timestamp] 存放時間戳
        """
        camera_coords = []

        # 取得影像邊界，優先使用 intrinsics 尺寸
        try:
            w = int(getattr(depth_intrin, "width", 0) or depth_frame.get_width())
            h = int(getattr(depth_intrin, "height", 0) or depth_frame.get_height())
        except Exception:
            w = int(self.width)
            h = int(self.height)

        for x, y in pixel_coords:
            if not (0 <= x < w and 0 <= y < h):
                camera_coords.append([0.0, 0.0, 0.0])
                continue

            # 取得深度值
            if use_robust_depth:
                depth = self._get_robust_depth(
                    depth_frame,
                    x,
                    y,
                    radius=2,
                    min_depth_m=min_depth_m,
                    max_depth_m=max_depth_m,
                )
            else:
                depth = float(depth_frame.get_distance(x, y))
                if depth < float(min_depth_m) or (max_depth_m is not None and depth > float(max_depth_m)):
                    depth = 0.0

            if depth > 0:
                # 反投影：像素 + 深度 → 3D 相機座標
                coord_3d = rs.rs2_deproject_pixel_to_point(
                    intrin=depth_intrin,
                    pixel=[x, y],
                    depth=depth
                )
                camera_coords.append(list(coord_3d))
            else:
                camera_coords.append([0.0, 0.0, 0.0])

        # 第 34 列存放時間戳
        camera_coords.append([0.0, 0.0, timestamp])
        return np.array(camera_coords, dtype=np.float32)
    
    def _apply_output_y_axis_up(self, arr: np.ndarray, *, y_axis_up: bool) -> np.ndarray:
        """
        轉換座標系為 y 軸向上。

        RealSense 相機座標預設為 x 向右、y 向下、z 向前。
        當 y_axis_up=True 時，將 y 座標反轉使其向上為正。

        Args:
            arr: shape (N, J, 3) 的姿態座標 array
            y_axis_up: 是否轉換為 y 軸向上

        Returns:
            轉換後的座標 array，第 34 列（timestamp）不受影響
        """
        if not y_axis_up:
            return arr

        a = np.asarray(arr)
        if a.ndim != 3 or a.shape[-1] != 3:
            return arr

        out = a.copy()
        pose_j = min(33, out.shape[1])  # 只處理關節點，保留 timestamp 列
        out[:, :pose_j, 1] *= -1.0
        return out