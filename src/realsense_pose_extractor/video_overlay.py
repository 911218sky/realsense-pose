"""Video writer helpers for drawing pose overlay frames."""

import os
from typing import List, Optional, Tuple

import cv2
import numpy as np

class VideoOverlayMixin:
    def _pick_fourcc(self, path: str) -> int:
        ext = os.path.splitext(path)[1].lower()
        match ext:
            case ".mp4":
                return cv2.VideoWriter_fourcc(*"mp4v")
            case ".avi":
                return cv2.VideoWriter_fourcc(*"XVID")
            case ".mov":
                return cv2.VideoWriter_fourcc(*"MJPG")
            case ".mkv":
                return cv2.VideoWriter_fourcc(*"MJPG")
            case _:
                return cv2.VideoWriter_fourcc(*"mp4v")
    def _init_video_writer(
        self,
        width: int,
        height: int,
        video_path: str,
        eff_fps: float
    ) -> cv2.VideoWriter:
        """初始化視頻寫入器
        
        Args:
            sample_rgb_image: 樣本RGB圖像，用於獲取寬高
            video_path: 輸出視頻文件路徑
            eff_fps: 有效幀率
            
        Returns:
            cv2.VideoWriter: 初始化好的視頻寫入器
            
        Raises:
            RuntimeError: 當視頻寫入器打開失敗時拋出
        """
        fourcc = self._pick_fourcc(video_path)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        writer = cv2.VideoWriter(video_path, fourcc, eff_fps, (width, height))
        if not writer.isOpened():
            raise RuntimeError(f"VideoWriter open failed: {video_path}")
        return writer
    def _write_overlay_frame(
        self,
        writer: cv2.VideoWriter,
        rgb_image: np.ndarray,
        pixel_coords: List[Tuple[int, int]],
        circle_radius: int = 3,
        line_thickness: int = 2,
        overlay_text: Optional[str] = None,
    ) -> None:
        bgr = cv2.cvtColor(rgb_image, cv2.COLOR_RGB2BGR)
        h, w = bgr.shape[:2]

        # 畫骨架：連線
        connections = self.mp_pose.POSE_CONNECTIONS
        if connections is not None:
            for a, b in connections:
                if a < len(pixel_coords) and b < len(pixel_coords):
                    xa, ya = pixel_coords[a]
                    xb, yb = pixel_coords[b]
                    if 0 <= xa < w and 0 <= ya < h and 0 <= xb < w and 0 <= yb < h:
                        cv2.line(bgr, (xa, ya), (xb, yb), (0, 255, 0), line_thickness, cv2.LINE_AA)

        # 畫骨架：點
        for (x, y) in pixel_coords:
            if 0 <= x < w and 0 <= y < h:
                cv2.circle(bgr, (x, y), circle_radius, (0, 0, 255), -1, cv2.LINE_AA)

        # 疊字（可選）
        if overlay_text:
            cv2.putText(bgr, overlay_text, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)

        writer.write(bgr)

