"""Pose (MediaPipe) extraction and 2D->3D deprojection helpers."""

from typing import List, Optional, Tuple

import mediapipe as mp
import numpy as np
import pyrealsense2 as rs

class PoseOpsMixin:
    def _extract_pose_coordinates(
        self, 
        results: mp.solutions.pose.PoseLandmark,
        *,
        image_width: int,
        image_height: int,
    ) -> Optional[List[Tuple[int, int]]]:
        """
        從 MediaPipe 結果中提取姿態關鍵點座標
        
        Args:
            results: MediaPipe 處理結果
            
        Returns:
            關鍵點像素座標列表，如果沒有檢測到姿態則返回 None
        """
        if results.pose_landmarks is None:
            return None
        coords = []
        for lm in results.pose_landmarks.landmark:
            # MediaPipe 的 lm.x/lm.y 為 [0,1] 的正規化座標，需乘上「實際影像尺寸」
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
        取得更穩定的深度值：使用周圍像素的中位數，避免單點噪聲。
        
        Args:
            depth_frame: 深度幀
            x, y: 中心像素座標
            radius: 採樣半徑（預設 2，即 5x5 區域）
            
        Returns:
            穩定的深度值（公尺），若無有效深度則回傳 0.0
        """
        # depth_frame 的實際尺寸（避免使用固定 self.width/self.height 造成越界或取樣偏移）
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
                    # 避免 MediaPipe 把腳點偵測到遠處背景（會造成 z/y 爆到好幾公尺）
                    if d < float(min_depth_m):
                        continue
                    if max_depth_m is not None and d > float(max_depth_m):
                        continue
                    depths.append(float(d))
        
        if not depths:
            return 0.0
        
        # 使用中位數更穩定
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
        將像素座標轉換為 3D 相機座標系座標
        
        Args:
            pixel_coords: 像素座標列表 [(x, y), ...]
            depth_frame: 深度幀
            depth_intrin: 深度相機內參
            timestamp: 時間戳
            use_robust_depth: 是否使用穩健深度採樣（周圍像素中位數）
            
        Returns:
            3D 相機座標列表 (34, 3)
            33 個關鍵點，每個關鍵點有 x, y, z 三個座標，最後一個元素是時間戳
        """
        camera_coords = []

        # 以 intrinsics / depth_frame 尺寸做 bounds（避免固定 self.width/self.height 導致的座標判斷錯誤）
        try:
            w = int(getattr(depth_intrin, "width", 0) or depth_frame.get_width())
            h = int(getattr(depth_intrin, "height", 0) or depth_frame.get_height())
        except Exception:
            w = int(self.width)
            h = int(self.height)
        
        for x, y in pixel_coords:
            # 檢查座標是否在有效範圍內
            if not (0 <= x < w and 0 <= y < h):
                camera_coords.append([0.0, 0.0, 0.0])
                continue
            
            # 獲取該像素點的深度值
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
            
            if depth > 0:  # 有效深度值
                # 將像素座標和深度轉換為 3D 相機座標 (x, y, z)
                coord_3d = rs.rs2_deproject_pixel_to_point(
                    intrin=depth_intrin, 
                    pixel=[x, y], 
                    depth=depth
                )
                camera_coords.append(list(coord_3d))
            else:
                # 無效深度值，填入零座標
                camera_coords.append([0.0, 0.0, 0.0])
        
        # 添加時間戳作為最後一個元素
        camera_coords.append([0.0, 0.0, timestamp])
        camera_coords_np = np.array(camera_coords, dtype=np.float32)
        
        return camera_coords_np
    
    def _apply_output_y_axis_up(self, arr: np.ndarray, *, y_axis_up: bool) -> np.ndarray:
        """
        將輸出座標轉成「y 向上為正」的慣例（y_axis_up=True 時）。

        注意：
        - RealSense rs2_deproject_pixel_to_point 的相機座標常見慣例為：x 向右、y 向下、z 向前
        - 本專案 npy 格式可能含 timestamp row (index 33) = [0, 0, t]，這列不應做座標翻轉
        """
        if not y_axis_up:
            return arr

        a = np.asarray(arr)
        if a.ndim != 3 or a.shape[-1] != 3:
            # 不符合本專案 (N,J,3) 格式就不處理
            return arr

        out = a.copy()
        pose_j = min(33, out.shape[1])  # 只處理關節點（保留 timestamp row）
        out[:, :pose_j, 1] *= -1.0
        return out