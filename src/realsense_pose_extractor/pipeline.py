"""RealSense pipeline 初始化與時間戳處理。"""

import threading
from typing import Any, Optional, Tuple

import pyrealsense2 as rs


def _start_pipeline_with_timeout(pipeline: rs.pipeline, config: rs.config, timeout_s: float = 10.0):
    """
    帶 timeout 的 pipeline.start()。

    Args:
        pipeline: RealSense pipeline 物件
        config: pipeline 設定
        timeout_s: 超時秒數

    Returns:
        pipeline_profile

    Raises:
        TimeoutError: 超時未完成
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
        raise TimeoutError(
            f"pipeline.start() 超過 {timeout_s} 秒未完成，"
            "pyrealsense2 可能處於異常狀態，建議重啟服務。"
        )
    if result["error"] is not None:
        raise result["error"]
    return result["profile"]


def _fmt_enum(v: Any) -> str:
    """將 enum 轉為字串，失敗時回傳 repr。"""
    try:
        return str(v)
    except Exception:
        return repr(v)


def _log_bag_metadata(logger: Any, profile: "rs.pipeline_profile") -> None:
    """輸出 bag 檔的 metadata：device info、stream 格式與 intrinsics。"""
    lines = []
    try:
        dev = profile.get_device()
    except Exception as e:
        logger.info(f"[bag_info] 無法取得 device: {e}")
        return

    # Device info
    try:
        info_keys = [
            rs.camera_info.name,
            rs.camera_info.serial_number,
            rs.camera_info.product_line,
            rs.camera_info.firmware_version,
            rs.camera_info.usb_type_descriptor,
        ]
        for k in info_keys:
            try:
                if dev.supports(k):
                    lines.append(f"[bag_info] device.{k}: {dev.get_info(k)}")
            except Exception:
                continue
    except Exception:
        pass

    # Playback info
    try:
        pb = dev.as_playback()
        try:
            dur = pb.get_duration()
            lines.append(f"[bag_info] playback.duration: {dur}")
        except Exception:
            pass
        try:
            pos = pb.get_position()
            lines.append(f"[bag_info] playback.position: {pos}")
        except Exception:
            pass
        try:
            rt = pb.is_real_time()
            lines.append(f"[bag_info] playback.real_time: {rt}")
        except Exception:
            pass
    except Exception:
        pass

    # Stream profiles
    try:
        streams = profile.get_streams()
    except Exception as e:
        lines.append(f"[bag_info] 無法取得 streams: {e}")
        logger.info("\n".join(lines) if lines else "[bag_info] (無資訊)")
        return

    lines.append(f"[bag_info] streams.count: {len(streams)}")
    for i, s in enumerate(streams):
        try:
            st = _fmt_enum(s.stream_type())
        except Exception:
            st = "unknown"
        try:
            fmt = _fmt_enum(s.format())
        except Exception:
            fmt = "unknown"

        idx = None
        uid = None
        try:
            idx = s.stream_index()
        except Exception:
            pass
        try:
            uid = s.unique_id()
        except Exception:
            pass

        # Video stream 解析度、fps、intrinsics
        whfps = ""
        intr = ""
        try:
            vsp = s.as_video_stream_profile()
            w = int(vsp.width())
            h = int(vsp.height())
            fps = float(vsp.fps())
            whfps = f"{w}x{h}@{fps}"

            try:
                intr_obj = vsp.get_intrinsics() if hasattr(vsp, "get_intrinsics") else vsp.intrinsics
                intr = (
                    f" intrinsics(fx={getattr(intr_obj,'fx',None)}, fy={getattr(intr_obj,'fy',None)}, "
                    f"ppx={getattr(intr_obj,'ppx',None)}, ppy={getattr(intr_obj,'ppy',None)}, "
                    f"model={getattr(intr_obj,'model',None)})"
                )
            except Exception:
                intr = ""
        except Exception:
            pass

        lines.append(
            f"[bag_info] stream[{i}]: type={st} format={fmt}"
            + (f" index={idx}" if idx is not None else "")
            + (f" uid={uid}" if uid is not None else "")
            + (f" {whfps}" if whfps else "")
            + intr
        )

    logger.info("\n".join(lines))


class TimeTrackingMixin:
    """時間戳追蹤 mixin，計算每幀的時間。"""

    def _init_time_tracking(self):
        """初始化時間追蹤狀態。"""
        self._first_frame_number = None
        self._processed_frames = 0

    def _get_frame_timestamp(self, frames: Any, frame_idx: int) -> float:
        """
        計算單調遞增的時間戳（秒）。

        優先使用 frame_number，若不可用或發生回退則用 processed_frames。
        """
        if hasattr(frames, 'frame_number') and frames.frame_number is not None:
            cur_frame_number = int(frames.frame_number)
        else:
            cur_frame_number = int(frame_idx)

        if self._first_frame_number is None:
            self._first_frame_number = cur_frame_number

        delta = cur_frame_number - self._first_frame_number

        if delta < 0:
            # frame_number 回退時用 processed_frames 估計
            t_sec = float(self._processed_frames) / self.fps
        else:
            t_sec = float(delta) / self.fps

        return float(t_sec)


class PipelineMixin:
    """RealSense pipeline 初始化 mixin。"""

    def _setup_pipeline(self) -> Tuple[rs.pipeline, Optional[rs.align]]:
        """
        初始化 RealSense pipeline。

        Returns:
            (pipeline, align) tuple，align 可能為 None
        """
        self.logger.info("[_setup_pipeline] 建立 rs.pipeline...")
        pipeline = rs.pipeline()
        self.logger.info("[_setup_pipeline] 建立 rs.config...")
        config = rs.config()

        self.logger.info(f"[_setup_pipeline] 載入 bag 檔: {self.bag_file_path}")
        rs.config.enable_device_from_file(config, self.bag_file_path, repeat_playback=False)

        try:
            self.logger.info("[_setup_pipeline] 啟動 pipeline（帶 timeout）...")
            profile = _start_pipeline_with_timeout(pipeline, config, timeout_s=15.0)
            self.logger.info("[_setup_pipeline] pipeline 啟動成功")

            _log_bag_metadata(self.logger, profile)

            streams = profile.get_streams()
            stream_types = {s.stream_type(): s for s in streams}

            # 從 color stream 取得解析度和 fps，沒有則用 depth
            picked = False
            for stream in streams:
                if stream.stream_type() == rs.stream.color:
                    video_stream = stream.as_video_stream_profile()
                    actual_w = int(video_stream.width())
                    actual_h = int(video_stream.height())
                    actual_fps = float(video_stream.fps())
                    if self.width != actual_w or self.height != actual_h or self.fps != actual_fps:
                        self.logger.warning(
                            f"Color stream: 預期 {self.width}x{self.height}@{self.fps} != 實際 {actual_w}x{actual_h}@{actual_fps}"
                        )
                    self.width, self.height, self.fps = actual_w, actual_h, actual_fps
                    picked = True
                    break
            if not picked:
                for stream in streams:
                    if stream.stream_type() == rs.stream.depth:
                        video_stream = stream.as_video_stream_profile()
                        actual_w = int(video_stream.width())
                        actual_h = int(video_stream.height())
                        actual_fps = float(video_stream.fps())
                        if self.width != actual_w or self.height != actual_h or self.fps != actual_fps:
                            self.logger.warning(
                                f"Depth stream: 預期 {self.width}x{self.height}@{self.fps} != 實際 {actual_w}x{actual_h}@{actual_fps}"
                            )
                        self.width, self.height, self.fps = actual_w, actual_h, actual_fps
                        break

            # 設定 depth 對齊目標
            if rs.stream.color in stream_types and rs.stream.depth in stream_types:
                align = rs.align(rs.stream.color)
            elif rs.stream.depth in stream_types:
                align = rs.align(rs.stream.depth)
            else:
                align = None

            # 檢查 color 格式，決定色彩空間轉換方式
            if rs.stream.color in stream_types:
                csp = stream_types[rs.stream.color].as_video_stream_profile()
                fmt = csp.format()
                if fmt == rs.format.bgr8:
                    self._need_bgr2rgb = True
                elif fmt == rs.format.yuyv:
                    self._need_yuyv2rgb = True

            # 關閉 real-time 模式以最快速度播放 bag
            playback = profile.get_device().as_playback()
            playback.set_real_time(False)

            return pipeline, align

        except Exception as e:
            try:
                pipeline.stop()
            except Exception:
                pass
            self.logger.error(f"Pipeline 初始化失敗: {e}")
            raise

