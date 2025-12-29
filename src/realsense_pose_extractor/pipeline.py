"""RealSense pipeline setup and timestamp utilities."""

import threading
from typing import Optional, Tuple

import pyrealsense2 as rs


def _start_pipeline_with_timeout(pipeline: rs.pipeline, config: rs.config, timeout_s: float = 10.0):
    """
    Call pipeline.start(config) with a timeout.
    Raises TimeoutError if it hangs longer than timeout_s.
    """
    result = {"profile": None, "error": None}

    def _do_start():
        try:
            result["profile"] = pipeline.start(config)
        except Exception as e:
            result["error"] = e

    t = threading.Thread(target=_do_start, daemon=True)
    t.start()
    t.join(timeout=timeout_s)

    if t.is_alive():
        # Thread is still running -> pipeline.start() is hanging
        raise TimeoutError(
            f"pipeline.start() did not complete within {timeout_s}s. "
            "This usually means pyrealsense2 is in a bad state after processing multiple bags. "
            "Consider restarting the API/container."
        )
    if result["error"] is not None:
        raise result["error"]
    return result["profile"]

class TimeTrackingMixin:
    def _init_time_tracking(self):
        """
        初始化時間追蹤
        """
        self._first_frame_number = None
        self._processed_frames = 0
    def _get_frame_timestamp(self, frames, frame_idx: int) -> float:
        """
        以 frame_number / fps 建立單調時間（秒）。
        如果 frame_number 不可得或回退，使用內部 processed_frames / fps 作為 fallback。
        回傳 float(seconds)。
        """
        # 盡量取得 frame_number，否則 fallback 用 frame_idx
        if hasattr(frames, 'frame_number') and frames.frame_number is not None:
            cur_frame_number = int(frames.frame_number)
        else:
            cur_frame_number = int(frame_idx)

        # 當 first 尚未設時，用第一個可用的 frame_number 作為基準
        if self._first_frame_number is None:
            self._first_frame_number = cur_frame_number

        # 計算 frame 差
        delta = cur_frame_number - self._first_frame_number

        # 若 delta 負（frame_number 回退或 wrap），則使用 processed_frames 作為估計
        if delta < 0:
            # fps 若是無效（<= 0），會使用預設 30.0 fps 來避免除以 0
            t_sec = float(self._processed_frames) / self.fps
        else:
            t_sec = float(delta) / self.fps

        return float(t_sec)

class PipelineMixin:
    def _setup_pipeline(self) -> Tuple[rs.pipeline, Optional[rs.align]]:
        """
        初始化 RealSense 管道和配置
        
        Returns:
            pipeline: RealSense 管道對象
            align: 對齊對象，用於對齊深度和彩色圖像
        """
        self.logger.info("[_setup_pipeline] Creating rs.pipeline()...")
        pipeline = rs.pipeline()
        self.logger.info("[_setup_pipeline] Creating rs.config()...")
        config = rs.config()

        # 只指定從檔案播放，不強制任何 stream profile
        # True 表示自動循環播放；若不想循環可改為 False
        self.logger.info(f"[_setup_pipeline] enable_device_from_file: {self.bag_file_path}")
        rs.config.enable_device_from_file(config, self.bag_file_path, repeat_playback=False)

        try:
            self.logger.info("[_setup_pipeline] Calling pipeline.start(config) with timeout...")
            profile = _start_pipeline_with_timeout(pipeline, config, timeout_s=15.0)
            self.logger.info("[_setup_pipeline] pipeline.start() succeeded.")

            # 檢查有哪些串流
            streams = profile.get_streams()
            stream_types = {s.stream_type(): s for s in streams}

            # 取得解析度 / FPS（用於 MediaPipe 2D 座標換算與輸出影片）
            # 優先使用 color stream；若 bag 沒有 color 才退回 depth。
            picked = False
            for stream in streams:
                if stream.stream_type() == rs.stream.color:
                    video_stream = stream.as_video_stream_profile()
                    self.width = int(video_stream.width())
                    self.height = int(video_stream.height())
                    self.fps = float(video_stream.fps())
                    self.logger.info(
                        f"Color stream: {self.width}x{self.height} @ {self.fps} FPS"
                    )
                    picked = True
                    break
            if not picked:
                for stream in streams:
                    if stream.stream_type() == rs.stream.depth:
                        video_stream = stream.as_video_stream_profile()
                        self.width = int(video_stream.width())
                        self.height = int(video_stream.height())
                        self.fps = float(video_stream.fps())
                        self.logger.info(
                            f"Depth stream: {self.width}x{self.height} @ {self.fps} FPS"
                        )
                        break

            # 設定對齊：若有 color 就對齊到 color，否則對齊到 depth
            if rs.stream.color in stream_types and rs.stream.depth in stream_types:
                align = rs.align(rs.stream.color)
            elif rs.stream.depth in stream_types:
                align = rs.align(rs.stream.depth)
            else:
                align = None

            # 確認 color 的像素格式，決定是否需要轉換
            if rs.stream.color in stream_types:
                csp = stream_types[rs.stream.color].as_video_stream_profile()
                fmt = csp.format()
                # 常見：bag 多為 bgr8/yuyv；mediapipe 要 RGB
                if fmt == rs.format.bgr8:
                    self._need_bgr2rgb = True
                elif fmt == rs.format.yuyv:
                    # 之後用 YUY2->RGB 轉換
                    self._need_yuyv2rgb = True

            # 設定播放模式
            playback = profile.get_device().as_playback()
            playback.set_real_time(False)

            return pipeline, align

        except Exception as e:
            # IMPORTANT:
            # If anything fails after pipeline.start(), the pipeline may remain in a running/locked
            # state. Always stop to avoid deadlocks/hangs on the next initialization.
            try:
                pipeline.stop()
            except Exception:
                pass
            self.logger.error(f"Failed to initialize pipeline: {e}")
            raise

