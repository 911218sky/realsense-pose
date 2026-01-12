"""子進程執行 PoseProcessor，完全隔離 pyrealsense2 資源。

pyrealsense2 在同一進程內反覆處理多個 .bag 容易資源洩漏或卡死，
尤其在 Windows 上。透過子進程隔離，卡住時可直接 kill，
讓 OS 回收所有底層資源（C++ 物件/handle/threads）。
"""

import multiprocessing as mp
import sys
from pathlib import Path

# 確保 src 在 sys.path，子進程才能 import 專案模組
_SRC_DIR = Path(__file__).resolve().parent.parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))


from typing import Any

import multiprocessing as mp


def _worker(
    bag_file_path: str,
    output_npy_path: str,
    result_queue: mp.Queue,
    **process_bag_kwargs: Any,
) -> None:
    """子進程 worker，執行完畢後透過 queue 回傳結果。"""
    try:
        # import 放在子進程內，避免與父進程共享狀態
        from realsense_pose_extractor import PoseProcessor

        processor = PoseProcessor(
            bag_file_path=bag_file_path,
            output_dir=".",
            width=process_bag_kwargs.get("width", None),
            height=process_bag_kwargs.get("height", None),
            fps=process_bag_kwargs.get("fps", None),
        )
        # 子進程已隔離，不需要全域鎖或長延遲
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


from typing import Any


def run_process_bag_in_subprocess(
    bag_file_path: str,
    output_npy_path: str,
    timeout_s: float = 300.0,
    **process_bag_kwargs: Any,
) -> None:
    """在隔離子進程中執行 process_bag。

    Args:
        bag_file_path: .bag 檔案路徑
        output_npy_path: 輸出 .npy 路徑
        timeout_s: 超時秒數，預設 5 分鐘
        **process_bag_kwargs: 傳給 process_bag() 的參數

    Raises:
        TimeoutError: 超時，子進程已被 kill
        RuntimeError: 子進程失敗（pyrealsense2 crash 或例外）
    """
    # spawn 確保完全隔離，fork 可能繼承 FD/狀態導致不穩定
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
        p.kill()
        p.join(timeout=5)
        raise TimeoutError(
            f"process_bag subprocess did not complete within {timeout_s}s. "
            "The subprocess has been killed. You may retry the request."
        )

    if result_queue.empty():
        raise RuntimeError(
            "process_bag subprocess ended without returning a result. "
            "This may indicate a crash or segfault in pyrealsense2/MediaPipe."
        )

    result = result_queue.get_nowait()
    if not result["success"]:
        raise RuntimeError(f"process_bag failed: {result['error']}")


if __name__ == "__main__":
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

