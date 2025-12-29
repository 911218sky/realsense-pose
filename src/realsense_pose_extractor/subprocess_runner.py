"""
在子進程中執行 PoseProcessor.process_bag()，達到「完全隔離」。

目的：
- 避免 pyrealsense2 / librealsense 在同一個 Python 進程內反覆處理多個 .bag 後，
  發生資源洩漏或 pipeline.start() 卡死（Windows 特別常見）。
- 若子進程卡住，可直接 kill，OS 會回收所有底層資源（C++ 物件/handle/threads）。
"""

import multiprocessing as mp
import sys
from pathlib import Path

# 確保 src 目錄在 sys.path，讓子進程可以 import 專案模組
_SRC_DIR = Path(__file__).resolve().parent.parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))


def _worker(
    bag_file_path: str,
    output_npy_path: str,
    result_queue: mp.Queue,
    **process_bag_kwargs,
):
    """
    子進程中的 worker。

    - 成功：回傳 {"success": True}
    - 失敗：回傳 {"success": False, "error": "..."}
    """
    try:
        # 注意：import 放在子進程內，避免和父進程共享任何狀態
        from realsense_pose_extractor import PoseProcessor

        processor = PoseProcessor(
            bag_file_path=bag_file_path,
            output_dir=".",
        )
        # 子進程本身已隔離，通常不需要全局鎖或很長的延遲
        processor.process_bag(
            output_npy_filename=output_npy_path,
            pre_pipeline_delay_s=0.1,
            post_pipeline_delay_s=0.1,
            **process_bag_kwargs,
        )
        result_queue.put({"success": True, "error": None})
    except Exception as e:
        import traceback
        result_queue.put({"success": False, "error": f"{e}\n{traceback.format_exc()}"})


def run_process_bag_in_subprocess(
    bag_file_path: str,
    output_npy_path: str,
    timeout_s: float = 300.0,  # 5 minutes default
    **process_bag_kwargs,
) -> None:
    """
    在隔離的子進程中執行 process_bag。

    Args:
        bag_file_path: .bag 檔案路徑
        output_npy_path: 輸出 .npy 路徑
        timeout_s: 子進程最長允許執行時間（秒）
        **process_bag_kwargs: 傳遞給 process_bag() 的額外參數

    Raises:
        TimeoutError: 子進程超時仍未完成（會被 kill）
        RuntimeError: 子進程失敗（包含 pyrealsense2 crash/例外）
    """
    # 使用 'spawn' 確保完全隔離（不共享父進程狀態）
    # Linux 下若用 fork 可能繼承 FD/狀態，反而增加不穩定因素
    ctx = mp.get_context("spawn")
    result_queue = ctx.Queue()

    p = ctx.Process(
        target=_worker,
        args=(bag_file_path, output_npy_path, result_queue),
        kwargs=process_bag_kwargs,
    )
    p.start()
    p.join(timeout=timeout_s)

    if p.is_alive():
        # 子進程仍在跑 -> timeout
        p.kill()
        p.join(timeout=5)  # 稍等一下讓 OS 清理
        raise TimeoutError(
            f"process_bag subprocess did not complete within {timeout_s}s. "
            "The subprocess has been killed. You may retry the request."
        )

    # 取得回傳結果
    if result_queue.empty():
        raise RuntimeError(
            "process_bag subprocess ended without returning a result. "
            "This may indicate a crash or segfault in pyrealsense2/MediaPipe."
        )

    result = result_queue.get_nowait()
    if not result["success"]:
        raise RuntimeError(f"process_bag failed: {result['error']}")


if __name__ == "__main__":
    # 簡易測試（CLI）
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--bag", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeout", type=float, default=300.0)
    args = parser.parse_args()

    run_process_bag_in_subprocess(
        bag_file_path=args.bag,
        output_npy_path=args.output,
        timeout_s=args.timeout,
        skip_frames=0,
        max_frames=10800,
        save_npy=True,
        save_pickle=False,
        save_video=False,
    )
    print("Done!")

