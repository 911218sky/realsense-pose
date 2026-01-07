"""影片輸出與骨架疊圖繪製。"""

import os
import shutil
import subprocess
from typing import List, Literal, Optional, Tuple

import cv2
import numpy as np

VideoCodec = Literal["h264", "mp4v", "xvid", "mjpg", "auto"]

# fourcc 對應表，H.264 有多個別名所以列出優先順序
_CODEC_FOURCC_MAP = {
    "h264": ["H264", "X264", "avc1"],
    "mp4v": ["mp4v"],
    "xvid": ["XVID"],
    "mjpg": ["MJPG"],
}

class FFmpegConverter:
    """FFmpeg 影片轉換工具。"""
    
    @staticmethod
    def is_available() -> bool:
        """檢查系統是否有 FFmpeg。"""
        return shutil.which("ffmpeg") is not None
    
    @staticmethod
    def convert_to_h264(
        input_path: str,
        output_path: Optional[str] = None,
        preset: str = "fast",
        crf: int = 23,
        timeout: int = 600,
    ) -> bool:
        """轉換影片為 H.264 編碼。
        
        Args:
            input_path: 輸入影片路徑
            output_path: 輸出路徑，None 則覆蓋原檔
            preset: 編碼速度 (ultrafast/fast/medium/slow)
            crf: 品質 (0-51，越小越好，預設 23)
            timeout: 超時秒數
        
        Returns:
            轉換是否成功
        """
        if not FFmpegConverter.is_available():
            return False
        
        if output_path is None:
            temp_path = input_path + ".h264.tmp.mp4"
            final_path = input_path
        else:
            temp_path = output_path
            final_path = output_path
        
        try:
            result = subprocess.run(
                [
                    "ffmpeg", "-y", "-i", input_path,
                    "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
                    "-movflags", "+faststart",
                    temp_path
                ],
                capture_output=True,
                timeout=timeout,
            )
            
            if result.returncode == 0:
                if temp_path != final_path:
                    os.replace(temp_path, final_path)
                return True
            else:
                FFmpegConverter._cleanup_temp(temp_path, final_path)
                return False
        except Exception:
            FFmpegConverter._cleanup_temp(temp_path, final_path)
            return False
    
    @staticmethod
    def _cleanup_temp(temp_path: str, final_path: str) -> None:
        """清理暫存檔。"""
        if temp_path != final_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


class VideoOverlayMixin:
    def _pick_fourcc(self, path: str, codec: VideoCodec = "auto") -> int:
        """選擇影片編碼 fourcc。
        
        Args:
            path: 輸出路徑
            codec: 編碼格式
                - "h264": 瀏覽器支援最好
                - "mp4v": 相容性好但瀏覽器支援差
                - "xvid": 適合 .avi
                - "mjpg": 適合 .mov/.mkv
                - "auto": 依副檔名自動選擇
        
        Returns:
            OpenCV fourcc 值
        """
        ext = os.path.splitext(path)[1].lower()
        
        # 依副檔名或指定 codec 決定嘗試順序
        if codec == "auto":
            if ext in (".mp4", ""):
                codec_list = _CODEC_FOURCC_MAP["h264"] + _CODEC_FOURCC_MAP["mp4v"]
            elif ext == ".avi":
                codec_list = _CODEC_FOURCC_MAP["xvid"]
            elif ext in (".mov", ".mkv"):
                codec_list = _CODEC_FOURCC_MAP["mjpg"]
            else:
                codec_list = _CODEC_FOURCC_MAP["h264"] + _CODEC_FOURCC_MAP["mp4v"]
        else:
            codec_list = _CODEC_FOURCC_MAP.get(codec, _CODEC_FOURCC_MAP["mp4v"])
        
        # 逐一測試編碼器是否可用
        for codec_name in codec_list:
            fourcc = cv2.VideoWriter_fourcc(*codec_name)
            test_path = os.path.join(os.path.dirname(path) or ".", "__codec_test__.mp4")
            test_writer = cv2.VideoWriter(test_path, fourcc, 30, (64, 64))
            if test_writer.isOpened():
                test_writer.release()
                try:
                    os.remove(test_path)
                except Exception:
                    pass
                return fourcc
        
        # 全部失敗則 fallback 到 mp4v
        return cv2.VideoWriter_fourcc(*"mp4v")

    def _init_video_writer(
        self,
        width: int,
        height: int,
        video_path: str,
        eff_fps: float,
        codec: VideoCodec = "auto",
    ) -> cv2.VideoWriter:
        """初始化 VideoWriter。
        
        Args:
            width: 影片寬度
            height: 影片高度
            video_path: 輸出路徑
            eff_fps: 幀率
            codec: 編碼格式，預設 auto 優先使用 H.264
            
        Returns:
            初始化完成的 VideoWriter
            
        Raises:
            RuntimeError: VideoWriter 開啟失敗
        """
        fourcc = self._pick_fourcc(video_path, codec=codec)
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

        # 繪製骨架連線
        connections = self.mp_pose.POSE_CONNECTIONS
        if connections is not None:
            for a, b in connections:
                if a < len(pixel_coords) and b < len(pixel_coords):
                    xa, ya = pixel_coords[a]
                    xb, yb = pixel_coords[b]
                    if 0 <= xa < w and 0 <= ya < h and 0 <= xb < w and 0 <= yb < h:
                        cv2.line(bgr, (xa, ya), (xb, yb), (0, 255, 0), line_thickness, cv2.LINE_AA)

        # 繪製關節點
        for (x, y) in pixel_coords:
            if 0 <= x < w and 0 <= y < h:
                cv2.circle(bgr, (x, y), circle_radius, (0, 0, 255), -1, cv2.LINE_AA)

        # 疊加文字
        if overlay_text:
            cv2.putText(bgr, overlay_text, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2, cv2.LINE_AA)

        writer.write(bgr)

