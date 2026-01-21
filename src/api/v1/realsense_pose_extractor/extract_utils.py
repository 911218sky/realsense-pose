import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import HTTPException

from api.config import BAG_DIR, HOST_DATASET_DIR, NPY_DIR
from api.utils.bag_path_resolver import resolve_bag_path
from db import RealsensePoseExtractor, UserProfile
from realsense_pose_extractor.subprocess_runner import run_process_bag_in_subprocess

from .bags import get_dataset_dir
from .models import ExtractResponse
from .utils import compute_file_hash


async def save_paths_to_db(
    *,
    session_name: str,
    user_code: Optional[str] = None,
    npy_path: str,
    video_path: Optional[str] = None,
    bag_path: str,
    bag_hash: str,
) -> None:
    existing: Optional[RealsensePoseExtractor] = await RealsensePoseExtractor.find_one(
        RealsensePoseExtractor.session_name == session_name
    )
    if existing:
        session_name = existing.session_name
        if user_code:
            existing.user_code = user_code
        existing.npy_path = npy_path
        existing.video_path = video_path
        existing.bag_path = bag_path
        existing.bag_hash = bag_hash
        existing.updated_at = datetime.now()
        await existing.save()
    else:
        doc = RealsensePoseExtractor(
            session_name=session_name,
            user_code=user_code,
            npy_path=npy_path,
            video_path=video_path,
            bag_path=bag_path,
            bag_hash=bag_hash,
            updated_at=datetime.now(),
        )
        await doc.insert()


def normalize_optional_str(s: Optional[str]) -> Optional[str]:
    s2 = (s or "").strip()
    return s2 or None


def parse_bag_input(*, bag_path: Optional[str], bag_id: Optional[str]) -> str:
    """
    解析 bag 來源參數：
    - 二選一：bag_id（建議）或 bag_path（相容舊版）
    """
    bag_path_n = normalize_optional_str(bag_path)
    bag_id_n = normalize_optional_str(bag_id)

    if bag_id_n and bag_path_n:
        raise HTTPException(
            status_code=400,
            detail="please provide either bag_id or bag_path (not both)",
        )

    bag_input = bag_id_n or bag_path_n
    if not bag_input:
        raise HTTPException(status_code=400, detail="missing bag_id or bag_path")
    return bag_input


async def resolve_bag_path_obj(bag_input: str) -> Path:
    """把輸入的 bag_id/bag_path 解析成實際可讀取的檔案路徑。"""
    try:
        dataset_dir = get_dataset_dir()
        return resolve_bag_path(
            bag_input,
            host_dataset_dir=HOST_DATASET_DIR,
            dataset_mount_dir=dataset_dir,
            search_dirs=[dataset_dir, Path(BAG_DIR)],
        )
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))


async def validate_extract_business_rules(
    *,
    session_name: str,
    user_code: Optional[str],
    force: bool,
) -> None:
    """檢查 session 是否可用 + user_code 是否存在。"""
    existing = await RealsensePoseExtractor.find_one(
        RealsensePoseExtractor.session_name == session_name
    )
    if existing and not force:
        raise HTTPException(status_code=400, detail=f"session {session_name} already exists")

    if user_code:
        user = await UserProfile.find_one(UserProfile.user_code == user_code)
        if not user:
            raise HTTPException(status_code=400, detail=f"user not found: {user_code}")


async def choose_and_copy_bag_file(
    *,
    bag_source_path: Path,
    bag_hash: str,
) -> Path:
    """
    決定要使用/複製到 `data/bag` 的哪個檔案：
    - 若同 hash 已存在：沿用舊紀錄的 bag_path（避免重複存檔）
    - 若檔名衝突但內容不同：用 hash suffix 避免誤用舊檔
    """
    existing_by_hash: Optional[RealsensePoseExtractor] = await RealsensePoseExtractor.find_one(
        RealsensePoseExtractor.bag_hash == bag_hash
    )

    if existing_by_hash and existing_by_hash.bag_path:
        bag_path_copy = Path(existing_by_hash.bag_path)
        if not bag_path_copy.exists():
            # DB 有紀錄但檔案已不在（可能被手動刪除）-> 退回複製新檔
            bag_path_copy = Path(BAG_DIR) / bag_source_path.name
    else:
        # 沒有找到相同 hash 的紀錄，使用預設路徑
        bag_path_copy = Path(BAG_DIR) / bag_source_path.name

    return bag_path_copy


def _is_within_dir(p: Path, base_dir: Path) -> bool:
    """
    判斷 `p` 是否位於 `base_dir` 之下（含相同目錄）。
    - 若 resolve 失敗，回傳 False（保守）
    """
    try:
        rp = p.resolve()
        rb = base_dir.resolve()
    except Exception:
        return False
    return (rb == rp) or (rb in rp.parents)


async def run_extraction_pipeline(
    *,
    default_config: Dict[str, Any],
    bag_source_path: Path,
    session_name: str,
    user_code: Optional[str],
    config_dict: Dict[str, Any],
) -> ExtractResponse:
    """
    提取核心流程（同步 / 背景共用）：
    - 計算 hash
    - 決定是否需要複製 bag 檔（避免重複 I/O）
    - 執行子進程提取
    - 寫入 DB

    備註：若來源 bag 已經在伺服器資料集目錄（dataset_dir）或已在 BAG_DIR，
    則不做複製，直接使用原檔案路徑。

    另外：若來源不在上述目錄，但 BAG_DIR 內「已存在同名檔案」，也會直接使用該檔案，
    以避免重複複製（依你的需求：只要資料夾裡存在這個檔案就不複製）。
    """
    bag_hash = await compute_file_hash(bag_source_path)
    dataset_dir = get_dataset_dir()

    # 預設直接用原始檔案；只有在「來源不在 dataset_dir / BAG_DIR」且「BAG_DIR 也沒有同名檔」時才複製。
    bag_path_to_use = bag_source_path
    in_server_dirs = _is_within_dir(bag_source_path, dataset_dir)
    same_name_in_bag_dir = Path(BAG_DIR) / bag_source_path.name

    if (not in_server_dirs) and same_name_in_bag_dir.exists():
        bag_path_to_use = same_name_in_bag_dir

    # 採用既有策略（依 hash 去重 + 同名防撞）
    if (not in_server_dirs) and (not same_name_in_bag_dir.exists()):
        bag_path_to_use = await choose_and_copy_bag_file(
            bag_source_path=bag_source_path,
            bag_hash=bag_hash,
        )

    npy_path = Path(NPY_DIR) / f"{session_name}.npy"
    
    cfg: Dict[str, Any] = {**default_config, **(config_dict or {})}
    save_video = cfg.get("save_video", False)
    
    # 若啟用影片輸出，準備影片路徑（使用相對路徑，與 npy 一致）
    video_path: Optional[Path] = None
    output_video_filename: Optional[str] = None
    if save_video:
        from api.config import VIDEO_DIR
        video_path = Path(VIDEO_DIR) / f"{session_name}.mp4"
        # 傳入相對路徑（如 data/video/xxx.mp4），_resolve_output_path 會保持原樣
        output_video_filename = str(video_path)

    # 在獨立子進程中執行，確保每次處理後資源完全釋放
    await asyncio.to_thread(
        run_process_bag_in_subprocess,
        bag_file_path=str(bag_path_to_use),
        output_npy_path=str(npy_path),
        output_video_filename=output_video_filename,
        timeout_s=60*20,  # 每個檔案最多 20 分鐘
        skip_frames=cfg.get("skip_frames", 0),
        max_frames=cfg.get("max_frames", 10800),
        progress_interval=cfg.get("progress_interval", 200),
        model_complexity=cfg.get("model_complexity", 1),
        min_detection_confidence=cfg.get("min_detection_confidence", 0.5),
        min_tracking_confidence=cfg.get("min_tracking_confidence", 0.5),
        calibrate_pose=cfg.get("calibrate_pose", True),
        y_axis_up=cfg.get("y_axis_up", False),
        # 解析度設定
        width=cfg.get("width", None),
        height=cfg.get("height", None),
        fps=cfg.get("fps", None),
        # 輸出選項
        # 保存 npy 檔案
        save_npy=True,
        save_pickle=False,
        # 保存影片
        save_video=save_video,
        # 保存預測出來的 anchors
        detect_anchors=True,
        save_anchors=True,
    )

    # 保存 npy 和 bag 檔案路徑到 DB
    await save_paths_to_db(
        session_name=session_name,
        user_code=user_code,
        npy_path=str(npy_path),
        video_path=str(video_path) if (video_path and video_path.exists()) else None,
        bag_path=str(bag_path_to_use),
        bag_hash=bag_hash,
    )

    return ExtractResponse(
        bag_path=str(bag_path_to_use),
        bag_filename=bag_path_to_use.name,
        npy_path=str(npy_path),
        video_path=str(video_path) if (video_path and video_path.exists()) else None,
        session_name=session_name,
        bag_hash=bag_hash,
        success=True,
    )


