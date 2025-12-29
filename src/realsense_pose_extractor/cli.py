import argparse
from typing import Optional

from config import load_config
from logger import setup_logger
from utils import ensure_dir, ensure_file
from utils.timing import time_it

from .processor import PoseProcessor


# 命令列參數解析
def parse_args() -> argparse.Namespace:
    """解析命令列參數。"""
    parser = argparse.ArgumentParser(
        description="RealSense 姿勢擷取 CLI",
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
    """
    主程式入口：

    - 優先使用傳入的 args；如無則自行呼叫 parse_args()
    - 載入 pose 模式的設定檔
    - 建立 logger 與 PoseProcessor
    - 呼叫 PoseProcessor.process_bag() 並計時
    """
    # 若外部未傳入 args，則直接由命令列解析
    args = args or parse_args()

    # 讀取設定（mode="pose" 代表此 CLI 的設定區塊）
    config = load_config(path=args.config, mode="pose")

    # 取得 .bag 檔路徑（CLI > config > 若全無則視為錯誤）
    bag_file_path = args.bag or config.get("bag_file_path", "")
    if not bag_file_path:
        raise ValueError("bag_file_path is not set")

    # 準備輸出目錄與檔名前綴
    output_dir_str = args.output or config.get("output_dir", "./outputs")
    output_dir = ensure_dir(output_dir_str)

    prefix_tag = args.tag or config.get("tag", "")

    # 設定 log 檔（可由設定檔控制是否輸出）
    log_file = config.get("log_file", "logs/processing.log")
    if config.get("save_log", False):
        # 確保 log 檔案所在目錄存在（若檔案不存在也會先建立空檔）
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

    # 執行主處理流程（process_bag）
    #   - 使用 time_it 包裝，方便統一記錄耗時
    #   - 具體參數由 YAML/CLI 控制
    time_it(
        processor.process_bag,
        # 每 N 幀回報一次進度
        progress_interval=config.get("progress_interval", 200),
        # 跳過前 N 幀不處理
        skip_frames=config.get("skip_frames", 0),
        # 最多處理幀數（預設：6 分鐘 * 60 秒 * 30 fps）
        max_frames=config.get("max_frames", 6 * 60 * 30),
        # MediaPipe 模型複雜度（0/1/2）
        model_complexity=config.get("model_complexity", 0),
        # 檢測信心閾值
        min_detection_confidence=config.get("min_detection_confidence", 0.5),
        # 追蹤信心閾值
        min_tracking_confidence=config.get("min_tracking_confidence", 0.5),
        # 是否輸出 .npy（骨架座標）
        save_npy=config.get("save_npy", True),
        # 是否輸出 pickle（可額外儲存中介結果）
        save_pickle=config.get("save_pickle", True),
        # 是否校正姿態
        calibrate_pose=config.get("calibrate_pose", True),
        # 是否將輸出座標轉成「y 向上為正」的慣例
        y_axis_up=config.get("y_axis_up", True),
        # 是否輸出標註後影片
        save_video=config.get("save_video", True),
        # 畫點時的圓半徑
        circle_radius=config.get("circle_radius", 3),
        # 畫骨架線段的線寬
        line_thickness=config.get("line_thickness", 2),
        # 自訂輸出 .npy 檔名（None 則使用預設格式）
        output_npy_filename=config.get("output_npy_filename", None),
        # 自訂輸出 pickle 檔名
        output_pickle_filename=config.get("output_pickle_filename", None),
        # 自訂輸出影片檔名
        output_video_filename=config.get("output_video_filename", None),
    )


if __name__ == "__main__":
    main()