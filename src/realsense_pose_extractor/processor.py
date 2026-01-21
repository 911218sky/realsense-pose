"""RealSense 姿態提取主處理器。"""

import gc
import pickle
import time
from collections import deque
from logging import Logger
from pathlib import Path
from typing import Any, Optional

import cv2
import mediapipe as mp
import numpy as np

from utils.npy_calibration import CalibrationConfig, PoseNpyCalibrator
from logger import setup_logger

from .bag_io import BagIOMixin, OutputMixin
from .pipeline import TimeTrackingMixin, PipelineMixin
from .pose_ops import PoseOpsMixin
from .video_overlay import VideoOverlayMixin, FFmpegConverter
from .anchor_detector import AnchorDetectorMixin, AnchorConfig

class PoseProcessor(
    BagIOMixin,
    OutputMixin,
    TimeTrackingMixin,
    PipelineMixin,
    PoseOpsMixin,
    VideoOverlayMixin,
    AnchorDetectorMixin,
):
    """從 RealSense bag 檔提取人體姿態並轉換為 3D 座標。"""

    def __init__(
        self,
        bag_file_path: str,
        output_dir: str,
        *,
        width: Optional[int] = None,
        height: Optional[int] = None,
        fps: Optional[int] = None,
        log_file: Optional[str] = None,
        logger: Optional[Logger] = None,
        prefix: Optional[str] = None,
    ):
        self.original_bag_file_path = Path(bag_file_path)
        self._temp_bag_path: Optional[Path] = None

        self.logger = logger or setup_logger("realsense_pose.processor", log_file=log_file)

        # 準備 bag 檔（若為壓縮檔會先解壓）
        self.bag_file_path = self._prepare_bag_file(self.original_bag_file_path)

        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.prefix = prefix or ""

        self.mp_pose = mp.solutions.pose

        # 預設相機參數
        if width is None or height is None or fps is None:
            width, height, fps = 640, 480, 30

        self.logger.info(
            f"[PoseProcessor] Camera parameters - "
            f"Width: {width} px | Height: {height} px | FPS: {fps}"
        )

        self.width, self.height, self.fps = width, height, float(fps)

        self._need_bgr2rgb = False
        self._need_yuyv2rgb = False
        self._first_frame_number = None
        self._processed_frames = 0
        
        # 初始化錨點偵測
        self._init_anchor_detection()
        
    def process_bag(
        self,
        progress_interval: int = 1000,
        skip_frames: int = 0,
        max_frames: int = 6 * 60 * 30,
        *,
        dump_bag_info: bool = False,
        y_axis_up: bool = True,
        calibrate_pose: bool = True,
        calibrate_pose_config: Optional[CalibrationConfig] = None,
        save_npy: bool = True,
        save_pickle: bool = False,
        save_video: bool = False,
        output_npy_filename: Optional[str] = None,
        output_pickle_filename: Optional[str] = None,
        output_video_filename: Optional[str] = None,
        video_codec: str = "auto",
        min_depth_m: float = 0.1,
        max_depth_m: Optional[float] = 8.0,
        pre_pipeline_delay_s: float = 0.5,
        post_pipeline_delay_s: float = 1.0,
        detect_anchors: bool = True,
        save_anchors: bool = True,
        **kwargs: Any,
    ) -> np.ndarray:
        """
        從 bag 檔提取 MediaPipe Pose 並輸出 3D 座標。

        Args:
            progress_interval: 每處理多少幀輸出一次進度
            skip_frames: 跳幀間隔，0 表示不跳幀
            max_frames: 最大處理幀數
            dump_bag_info: 是否輸出 bag 的 stream 資訊（除錯用）
            y_axis_up: 輸出座標是否轉換為 y 軸向上
            calibrate_pose: 是否進行姿態校正
            calibrate_pose_config: 校正設定
            save_npy: 是否儲存 npy 檔
            save_pickle: 是否儲存 pickle 檔
            save_video: 是否儲存 overlay 影片
            output_npy_filename: npy 檔名
            output_pickle_filename: pickle 檔名
            output_video_filename: 影片檔名
            video_codec: 影片編碼（h264/mp4v/xvid/mjpg/auto）
            min_depth_m: 最小有效深度（公尺）
            max_depth_m: 最大有效深度（公尺）
            pre_pipeline_delay_s: pipeline 初始化前延遲（秒）
            post_pipeline_delay_s: pipeline 關閉後延遲（秒）
            detect_anchors: 是否偵測錨點（椅子/錐子位置）
            save_anchors: 是否儲存錨點配置檔

        Returns:
            shape (N, 34, 3) 的姿態座標 array
        """
        pipeline = None
        writer = None

        self._dump_bag_info = bool(dump_bag_info)
        self._init_time_tracking()

        camera_coordinate_list = []
        valid_pose_frames = 0
        frame_idx = 0
        last_frame_number = -1

        start_time = time.time()
        max_recent_time = 1
        recent_frames = deque(maxlen=1024)
        video_path = None

        try:
            # 釋放可能殘留的 pyrealsense2 資源
            gc.collect()

            if pre_pipeline_delay_s and pre_pipeline_delay_s > 0:
                self.logger.info(f"[process_bag] Pre-pipeline delay: {pre_pipeline_delay_s}s...")
                time.sleep(float(pre_pipeline_delay_s))

            self.logger.info("[process_bag] Calling _setup_pipeline()...")
            pipeline, align = self._setup_pipeline()
            self.logger.info("[process_bag] Pipeline initialized.")

            # 設定影片輸出
            target_fps = float(self.fps)
            eff_fps = target_fps / max(1, skip_frames) if skip_frames else target_fps
            if save_video:
                if output_video_filename is None:
                    output_video_filename = (
                        f"{self.prefix}_{Path(self.bag_file_path).stem}.mp4"
                    )
                elif "{filename}" in output_video_filename:
                    output_video_filename = output_video_filename.format(
                        filename=Path(self.bag_file_path).stem
                    )

                video_path = self._resolve_output_path(
                    output_video_filename,
                    f"{self.prefix}_{Path(self.bag_file_path).stem}.mp4"
                )
                writer = self._init_video_writer(
                    width=self.width,
                    height=self.height,
                    video_path=str(video_path),
                    eff_fps=eff_fps,
                    codec=video_codec,
                )

            # MediaPipe Pose 處理迴圈
            with self.mp_pose.Pose(
                model_complexity=kwargs.get("model_complexity", 0),
                enable_segmentation=False,
                smooth_landmarks=True,
                min_detection_confidence=kwargs.get("min_detection_confidence", 0.5),
                min_tracking_confidence=kwargs.get("min_tracking_confidence", 0.5),
            ) as pose:
                while frame_idx < max_frames:
                    try:
                        frames = pipeline.wait_for_frames()
                    except Exception as e:
                        self.logger.warning(f"Failed to get frame {frame_idx}: {e}")
                        continue

                    # 跳過重複幀
                    if frames.frame_number == last_frame_number:
                        continue
                    last_frame_number = frames.frame_number

                    # 計算即時 FPS
                    now = time.time()
                    recent_frames.append(now)
                    while recent_frames and now - recent_frames[0] > max_recent_time:
                        recent_frames.popleft()
                    fps = 0.0 if len(recent_frames) < 2 else len(recent_frames) / max(
                        now - recent_frames[0], 1e-6
                    )

                    if frame_idx % progress_interval == 0 and frame_idx > 0:
                        self.logger.info(
                            f"Processed {frame_idx} frames | Recent FPS (1s): {fps:.2f}"
                        )

                    frame_idx += 1
                    if skip_frames != 0 and frame_idx % skip_frames != 0:
                        continue

                    color_frame = frames.get_color_frame()
                    if not color_frame:
                        continue

                    color_image = np.asanyarray(color_frame.get_data())
                    img_h, img_w = color_image.shape[:2]

                    # 色彩空間轉換
                    if self._need_bgr2rgb:
                        rgb_image = cv2.cvtColor(color_image, cv2.COLOR_BGR2RGB)
                    elif self._need_yuyv2rgb:
                        rgb_image = cv2.cvtColor(color_image, cv2.COLOR_YUV2RGB_YUY2)
                    else:
                        rgb_image = color_image

                    # 取得 color frame intrinsics
                    color_intrin = None
                    try:
                        color_intrin = (
                            color_frame.profile.as_video_stream_profile().intrinsics
                        )
                    except Exception:
                        color_intrin = None

                    results = pose.process(rgb_image)

                    pixel_coords = self._extract_pose_coordinates(
                        results, image_width=img_w, image_height=img_h
                    )
                    if pixel_coords is None:
                        continue

                    # 對齊深度幀
                    try:
                        aligned = align.process(frames) if align is not None else frames
                        depth_frame = aligned.get_depth_frame()
                    except Exception as e:
                        self.logger.warning(f"Failed to align frame {frame_idx}: {e}")
                        depth_frame = frames.get_depth_frame()

                    if not depth_frame:
                        continue

                    try:
                        depth_intrin = (
                            depth_frame.profile.as_video_stream_profile().intrinsics
                        )
                    except Exception as e:
                        self.logger.warning(f"Failed to get depth intrinsics: {e}")
                        continue

                    # 若 depth/color intrinsics 尺寸不一致，使用 color intrinsics
                    intrin_for_deproj = depth_intrin
                    try:
                        if (
                            color_intrin is not None
                            and (
                                int(getattr(depth_intrin, "width", 0)) != int(getattr(color_intrin, "width", 0))
                                or int(getattr(depth_intrin, "height", 0)) != int(getattr(color_intrin, "height", 0))
                            )
                        ):
                            self.logger.warning(
                                "Depth intrinsics size != color intrinsics size after alignment; "
                                "use color intrinsics for deprojection to fix X/Y mapping."
                            )
                            intrin_for_deproj = color_intrin
                    except Exception:
                        intrin_for_deproj = depth_intrin

                    timestamp = self._get_frame_timestamp(frames, frame_idx)

                    camera_coords = self._pixel_to_camera_coordinates(
                        pixel_coords,
                        depth_frame,
                        intrin_for_deproj,
                        timestamp,
                        min_depth_m=min_depth_m,
                        max_depth_m=max_depth_m,
                    )
                    camera_coordinate_list.append(camera_coords)
                    valid_pose_frames += 1

                    if save_video and writer is not None:
                        try:
                            self._write_overlay_frame(
                                writer,
                                rgb_image,
                                pixel_coords,
                                circle_radius=kwargs.get("circle_radius", 3),
                                line_thickness=kwargs.get("line_thickness", 2),
                                overlay_text=f"Frames (pose): {valid_pose_frames}",
                            )
                        except Exception as e:
                            self.logger.error(f"Write video failed: {e}")
                            save_video = False

            processing_time = time.time() - start_time
            self.logger.info("Processing completed:")
            self.logger.info(f"  - Processing time: {processing_time:.2f} seconds")
            self.logger.info(f"  - Valid pose frames: {valid_pose_frames}")

            raw_arr = np.array(camera_coordinate_list, dtype=np.float32)

            # 不校正時直接輸出
            if not calibrate_pose:
                out_arr = self._apply_output_y_axis_up(raw_arr, y_axis_up=y_axis_up)
                npy_path, _ = self._save_results(
                    out_arr,
                    save_npy=save_npy,
                    save_pickle=save_pickle,
                    output_npy_filename=output_npy_filename,
                    output_pickle_filename=output_pickle_filename,
                )
                return out_arr

            # 校正流程：先存原始資料，再校正後覆寫
            save_pickle_now = bool(save_pickle) and (not bool(y_axis_up))
            npy_path, pickle_path = self._save_results(
                raw_arr,
                save_npy=False,
                save_pickle=save_pickle_now,
                output_npy_filename=output_npy_filename,
                output_pickle_filename=output_pickle_filename,
            )

            if calibrate_pose:
                cfg = calibrate_pose_config or CalibrationConfig()
                calibrator = PoseNpyCalibrator(cfg=cfg)

                calib_arr = calibrator.calibrate_array(raw_arr)
                out_arr = self._apply_output_y_axis_up(calib_arr, y_axis_up=y_axis_up)
                np.save(npy_path, out_arr)
                self.logger.info(f"Pose calibrated and saved to: {npy_path}")

                if save_pickle and y_axis_up:
                    with open(pickle_path, "wb") as f:
                        pickle.dump(out_arr, f)
                    self.logger.info(f"Results saved to: {pickle_path}")

            # 偵測並儲存錨點配置（使用軌跡估算）
            if detect_anchors and save_npy:                
                # 使用軌跡估算錨點位置
                hip_center = (out_arr[:, 23, :] + out_arr[:, 24, :]) / 2
                chair_pos, cone_pos = self._estimate_chair_cone_from_trajectory(hip_center)
                
                # AnchorConfig 會自動從 default_pose.yaml 讀取 chair_radius 和 cone_radius
                anchor_config = AnchorConfig(
                    chair_pos=chair_pos,
                    cone_pos=cone_pos,
                )
                
                self.logger.info(
                    f"[Anchor] Trajectory estimation: "
                    f"chair=({chair_pos[0]:.2f}, {chair_pos[1]:.2f}), "
                    f"cone=({cone_pos[0]:.2f}, {cone_pos[1]:.2f}), "
                )
                
                if save_anchors:
                    self._save_anchor_config(npy_path, anchor_config)

            return out_arr
        finally:
            # 釋放 VideoWriter
            if writer is not None:
                try:
                    writer.release()
                except Exception as e:
                    self.logger.warning(f"Failed to release VideoWriter: {e}")

                if save_video and video_path is not None:
                    self.logger.info(f"Overlay video saved to: {video_path}")

                    # 轉換為 H.264 以提升瀏覽器相容性
                    if FFmpegConverter.convert_to_h264(str(video_path)):
                        self.logger.info(f"Video converted to H.264: {video_path}")
                    else:
                        self.logger.warning(
                            f"FFmpeg not available or conversion failed. "
                            f"Video may not play in browser: {video_path}"
                        )

            # 釋放 pipeline（Windows 上需多次嘗試以確保資源釋放）
            if pipeline is not None:
                self.logger.info("[process_bag] Stopping pipeline...")
                stopped = False
                last_err: Optional[Exception] = None
                for attempt in range(3):
                    try:
                        pipeline.stop()
                        stopped = True
                        self.logger.info(f"[process_bag] Pipeline stopped (attempt {attempt + 1}).")
                        break
                    except Exception as e:
                        last_err = e
                        self.logger.warning(f"[process_bag] pipeline.stop() attempt {attempt + 1} failed: {e}")
                        time.sleep(0.3)
                if not stopped:
                    self.logger.warning(f"Failed to stop pipeline after retries: {last_err}")

            # 刪除參考以協助 GC 回收 C++ 資源
            self.logger.info("[process_bag] Deleting pipeline/align references...")
            try:
                del pipeline
            except Exception:
                pass
            try:
                del align
            except Exception:
                pass
            self.logger.info("[process_bag] References deleted.")

            # 清理暫存 bag 檔
            if self._temp_bag_path is not None:
                try:
                    if self._temp_bag_path.exists():
                        self._temp_bag_path.unlink()
                        self.logger.info(f"Temporary bag file removed: {self._temp_bag_path}")
                except Exception as e:
                    self.logger.warning(f"Failed to remove temporary bag file {self._temp_bag_path}: {e}")

            if post_pipeline_delay_s and post_pipeline_delay_s > 0:
                time.sleep(float(post_pipeline_delay_s))


if __name__ == "__main__":
    bag_file_path = "dataset/4_1_1208.bag"
    output_dir = "outputs"
    processor = PoseProcessor(
        bag_file_path=bag_file_path,
        output_dir=output_dir,
    )
    processor.process_bag(
        skip_frames=4,
        max_frames=6*60*30,
        # 輸出選項
        save_npy=True,
        save_pickle=False,
        save_video=True,
        detect_anchors=True,
        save_anchors=True,
        output_video_filename="{filename}_overlay.mp4",
        # MediaPipe 參數
        model_complexity=0,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
        progress_interval=200,
    )
