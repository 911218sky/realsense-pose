"""RealSense 姿態擷取 CLI。"""

import argparse
from typing import Optional

from config import load_config
from logger import setup_logger
from utils import ensure_dir, ensure_file
from utils.timing import time_it

from .processor import PoseProcessor


def parse_args() -> argparse.Namespace:
    """解析 CLI 參數。"""
    parser = argparse.ArgumentParser(
        description="RealSense 姿態擷取 CLI",
    )
    parser.add_argument(
        "--bag",
        help="Path to .bag file",
    )
    parser.add_argument(
        "--output",
        help="Output directory",
    )
    parser.add_argument(
        "--config",
        help="Optional YAML config",
    )
    parser.add_argument(
        "--tag",
        help="Prefix tag to be added to all output file names",
    )
    return parser.parse_args()


def main(args: Optional[argparse.Namespace] = None) -> None:
    """主程式入口，載入設定並執行姿態擷取。"""
    args = args or parse_args()

    config = load_config(path=args.config, mode="pose")

    # CLI 參數優先於 config
    bag_file_path = args.bag or config.get("bag_file_path", "")
    if not bag_file_path:
        raise ValueError("bag_file_path is not set")

    output_dir_str = args.output or config.get("output_dir", "./outputs")
    output_dir = ensure_dir(output_dir_str)
    prefix_tag = args.tag or config.get("tag", "")

    # Log 檔設定
    log_file = config.get("log_file", "logs/processing.log")
    if config.get("save_log", False):
        ensure_file(log_file)
    else:
        log_file = None

    logger = setup_logger(
        "realsense_pose.processor",
        log_file=log_file,
    )

    processor = PoseProcessor(
        bag_file_path=bag_file_path,
        output_dir=str(output_dir),
        log_file=log_file,
        logger=logger,
        prefix=prefix_tag,
    )

    # 執行處理並計時
    time_it(
        processor.process_bag,
        dump_bag_info=config.get("dump_bag_info", False),
        progress_interval=config.get("progress_interval", 200),
        skip_frames=config.get("skip_frames", 0),
        max_frames=config.get("max_frames", 6 * 60 * 30),
        model_complexity=config.get("model_complexity", 0),
        min_detection_confidence=config.get("min_detection_confidence", 0.5),
        min_tracking_confidence=config.get("min_tracking_confidence", 0.5),
        save_npy=config.get("save_npy", True),
        save_pickle=config.get("save_pickle", True),
        calibrate_pose=config.get("calibrate_pose", True),
        y_axis_up=config.get("y_axis_up", True),
        save_video=config.get("save_video", True),
        circle_radius=config.get("circle_radius", 3),
        line_thickness=config.get("line_thickness", 2),
        output_npy_filename=config.get("output_npy_filename", None),
        output_pickle_filename=config.get("output_pickle_filename", None),
        output_video_filename=config.get("output_video_filename", None),
    )


if __name__ == "__main__":
    main()