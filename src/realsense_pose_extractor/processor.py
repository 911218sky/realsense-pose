"""RealSense pose extraction orchestrator (public `PoseProcessor`)."""

import gc
import pickle
import time
from collections import deque
from logging import Logger
from pathlib import Path
from typing import Optional

import cv2
import mediapipe as mp
import numpy as np

from logger import setup_logger
from utils.npy_calibration import CalibrationConfig, PoseNpyCalibrator

from .bag_io import BagIOMixin, OutputMixin
from .pipeline import TimeTrackingMixin, PipelineMixin
from .pose_ops import PoseOpsMixin
from .video_overlay import VideoOverlayMixin

class PoseProcessor(
    BagIOMixin,
    OutputMixin,
    TimeTrackingMixin,
    PipelineMixin,
    PoseOpsMixin,
    VideoOverlayMixin,
):
    """
    RealSense 姿態處理器
    用於從 bag 檔案中提取人體姿態關鍵點並轉換為 3D 座標
    """
    def __init__(
        self,
        bag_file_path: str,
        output_dir: str,
        *,
        log_file: Optional[str] = None,
        logger: Optional[Logger] = None,
        prefix: Optional[str] = None,
    ):
        # 原始輸入路徑（可能是 .bag 也可能是壓縮檔）
        self.original_bag_file_path = Path(bag_file_path)

        # 暫存解壓後檔案路徑（如果有的話）
        self._temp_bag_path: Optional[Path] = None
        
        # 設定日誌
        self.logger = logger or setup_logger("realsense_pose.processor", log_file=log_file)

        # 給 RealSense 用的實際 bag 檔案路徑（字串）
        self.bag_file_path = self._prepare_bag_file(self.original_bag_file_path)

        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.prefix = prefix or ""

        # MediaPipe 設定
        self.mp_pose = mp.solutions.pose
        
        # 相機參數配置
        self.width, self.height = 640, 480
        self.fps = 30

        # 是否需要轉換格式
        self._need_bgr2rgb = False
        self._need_yuyv2rgb = False

        # time-tracking state (initialized in process_bag)
        self._first_frame_number = None
        self._processed_frames = 0
        
    def process_bag(
        self, 
        progress_interval: int = 1000,
        skip_frames: int = 0,
        max_frames: int = 6 * 60 * 30,
        *,
        # 輸出座標慣例：y_axis_up=True 時輸出 y 向上為正
        y_axis_up: bool = True,
        # 是否校正姿態
        calibrate_pose: bool = True,
        calibrate_pose_config: Optional[CalibrationConfig] = None,
        # 輸出選項
        save_npy: bool = True,
        save_pickle: bool = False,
        save_video: bool = False,
        output_npy_filename: Optional[str] = None,
        output_pickle_filename: Optional[str] = None,
        output_video_filename: Optional[str] = None,
        # 深度門檻：避免誤取到遠處背景深度造成 3D 座標爆掉（例如 z=20m）
        min_depth_m: float = 0.1,
        max_depth_m: Optional[float] = 8.0,
        # 延遲：讓 pipeline stop / 資源釋放更穩，避免下一次 init 卡死（Windows 常見）
        pre_pipeline_delay_s: float = 0.5,
        post_pipeline_delay_s: float = 1.0,
        **kwargs,
    ) -> np.ndarray:
        """
        從 .bag 擷取 MediaPipe Pose，輸出：
        - 3D 相機座標 (N, 34, 3)（最後一個元素為 [0,0,timestamp]）
        - （選擇性）overlay 視訊，人物含關節點與連線
        
        新增後處理選項：
        - temporal_smooth: 是否進行時序平滑（減少單幀跳動）
        - temporal_smooth_window: 時序平滑窗口大小
        - fix_lr_swap: 是否檢測並修復左右關節交換
        """
        pipeline = None
        writer = None

        # 初始化時間追蹤
        self._init_time_tracking()

        # 統計與暫存
        camera_coordinate_list = []
        valid_pose_frames = 0
        frame_idx = 0
        last_frame_number = -1

        start_time = time.time()
        max_recent_time = 1
        recent_frames = deque(maxlen=1024) 

        try:
            # Force gc before init to help release lingering pyrealsense2 resources.
            gc.collect()

            if pre_pipeline_delay_s and pre_pipeline_delay_s > 0:
                self.logger.info(f"[process_bag] Pre-pipeline delay: {pre_pipeline_delay_s}s...")
                time.sleep(float(pre_pipeline_delay_s))

            # 初始化管道
            self.logger.info("[process_bag] Calling _setup_pipeline()...")
            pipeline, align = self._setup_pipeline()
            self.logger.info("[process_bag] Pipeline initialized.")

            # 視訊輸出
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

                video_path = self.output_dir / output_video_filename
                writer = self._init_video_writer(
                    width=self.width,
                    height=self.height,
                    video_path=str(video_path),
                    eff_fps=eff_fps,
                )

            # MediaPipe Pose
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

                    # 避免重複幀
                    if frames.frame_number == last_frame_number:
                        continue
                    last_frame_number = frames.frame_number

                    now = time.time()
                    recent_frames.append(now)
                    while recent_frames and now - recent_frames[0] > max_recent_time:
                        recent_frames.popleft()
                    fps = 0.0 if len(recent_frames) < 2 else len(recent_frames) / max(
                        now - recent_frames[0], 1e-6
                    )

                    # 進度
                    if frame_idx % progress_interval == 0 and frame_idx > 0:
                        self.logger.info(
                            f"Processed {frame_idx} frames | Recent FPS (1s): {fps:.2f}"
                        )

                    # 幀計數與跳幀
                    frame_idx += 1
                    if skip_frames != 0 and frame_idx % skip_frames != 0:
                        continue

                    # 彩色幀
                    color_frame = frames.get_color_frame()
                    if not color_frame:
                        continue

                    color_image = np.asanyarray(color_frame.get_data())
                    img_h, img_w = color_image.shape[:2]

                    # 只算一次 RGB，後面全部重用
                    if self._need_bgr2rgb:
                        rgb_image = cv2.cvtColor(color_image, cv2.COLOR_BGR2RGB)
                    elif self._need_yuyv2rgb:
                        rgb_image = cv2.cvtColor(color_image, cv2.COLOR_YUV2RGB_YUY2)
                    else:
                        rgb_image = color_image

                    # color frame intrinsics（若 depth 已對齊到 color，通常應使用這組內參做 deproject）
                    color_intrin = None
                    try:
                        color_intrin = (
                            color_frame.profile.as_video_stream_profile().intrinsics
                        )
                    except Exception:
                        color_intrin = None

                    # 先跑 Pose（未對齊）
                    results = pose.process(rgb_image)

                    # 2D 關鍵點（彩色座標） (33, 2)
                    pixel_coords = self._extract_pose_coordinates(
                        results, image_width=img_w, image_height=img_h
                    )
                    if pixel_coords is None:
                        continue

                    # 對齊以取得對應的深度
                    try:
                        aligned = align.process(frames) if align is not None else frames
                        depth_frame = aligned.get_depth_frame()
                    except Exception as e:
                        self.logger.warning(f"Failed to align frame {frame_idx}: {e}")
                        depth_frame = frames.get_depth_frame()

                    if not depth_frame:
                        continue

                    # 內參
                    try:
                        depth_intrin = (
                            depth_frame.profile.as_video_stream_profile().intrinsics
                        )
                    except Exception as e:
                        self.logger.warning(
                            f"Failed to get depth intrinsics: {e}"
                        )
                        continue

                    # 若對齊後 depth 的 intrinsics 尺寸與 color 不一致，優先使用 color intrinsics
                    # （可避免 bag stream profile 不一致造成的 X/Y 換算偏差）
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

                    # 時間戳
                    timestamp = self._get_frame_timestamp(frames, frame_idx)

                    # 彩色像素 → 3D 相機座標 (34, 3)
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

                    # 視訊寫入
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

            # 統計
            processing_time = time.time() - start_time
            self.logger.info("Processing completed:")
            self.logger.info(f"  - Processing time: {processing_time:.2f} seconds")
            self.logger.info(f"  - Valid pose frames: {valid_pose_frames}")

            # 轉 numpy 並保存
            raw_arr = np.array(
                camera_coordinate_list, dtype=np.float32
            )

            # 若不做校正，則先套用輸出座標慣例再保存（npy / pickle）
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

            # 需要校正時：
            # - npy 會由「校正後」結果寫入
            # - pickle：若 y_axis_up=True，讓 pickle 與 npy 保持相同座標慣例（避免一個翻一個沒翻）
            save_pickle_now = bool(save_pickle) and (not bool(y_axis_up))
            npy_path, pickle_path = self._save_results(
                raw_arr,
                save_npy=False,
                save_pickle=save_pickle_now,
                output_npy_filename=output_npy_filename,
                output_pickle_filename=output_pickle_filename,
            )
            
            # 校正姿態
            if calibrate_pose:
                # 防呆：外部若傳入 None，使用預設設定，避免 'NoneType' object has no attribute 'mode'
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

            return out_arr
        finally:
            # 釋放視訊寫入器
            if writer is not None:
                try:
                    writer.release()
                except Exception as e:
                    self.logger.warning(f"Failed to release VideoWriter: {e}")

                if save_video and output_video_filename is not None:
                    self.logger.info(
                        f"Overlay video saved to: {output_video_filename}"
                    )

            # 釋放管道（更激進地清理，避免 Windows 上資源殘留導致 N 次後卡死）
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

            # 顯式刪除 pipeline/align 引用，讓 Python 可以回收底層 C++ 資源
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

            # 清理暫存 bag 檔（如果有的話，不管前面成功失敗都會執行）
            if self._temp_bag_path is not None:
                try:
                    if self._temp_bag_path.exists():
                        self._temp_bag_path.unlink()
                        self.logger.info(
                            f"Temporary bag file removed: {self._temp_bag_path}"
                        )
                except Exception as e:
                    self.logger.warning(
                        f"Failed to remove temporary bag file "
                        f"{self._temp_bag_path}: {e}"
                    )

            # Optional delay after cleanup.
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
        output_video_filename="{filename}_overlay.mp4",
        # MediaPipe 參數
        model_complexity=0,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
        progress_interval=200,
    )
