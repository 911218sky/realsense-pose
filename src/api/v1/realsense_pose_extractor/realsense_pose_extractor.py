import asyncio
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union

import aiofiles
from bson import ObjectId
from fastapi import APIRouter, Body, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse

from api.config import BAG_DIR, NPY_DIR, VIDEO_DIR
from config import load_config
from db import RealsenseExtractJob, RealsensePoseExtractor, UserProfile
from logger import setup_logger
from .bags import router as bags_router
from .extract_utils import (
    parse_bag_input,
    resolve_bag_path_obj,
    run_extraction_pipeline,
    validate_extract_business_rules,
)
from .models import (
    DeleteSessionResponse,
    DeleteSessionsRequest,
    DeleteSessionsResponse,
    ExtractRequest,
    ExtractJobCreatedResponse,
    ExtractJobStatusResponse,
    ExtractResponse,
    RealsensePoseExtractorItem,
    RealsensePoseExtractorListResponse,
    SessionNameSuggestionResponse,
    VideoAvailabilityResponse,
)

logger = setup_logger(__name__)

default_config = load_config(mode="pose")

router = APIRouter(
    prefix="/realsense-pose-extractor",
    tags=["realsense-pose-extractor"]
)

# 公開路由 - 用於影片串流
public_router = APIRouter(
    prefix="/realsense-pose-extractor",
    tags=["realsense-pose-extractor-public"]
)

router.include_router(bags_router)

# 保留本進程內的背景任務參考（best-effort；job 本體會持久化在 MongoDB）。
_JOB_TASKS: Dict[str, asyncio.Task] = {}


@router.get("/sessions", response_model=RealsensePoseExtractorListResponse)
async def list_realsense_pose_sessions(
    page: int = 1,
    page_size: int = 20,
    user_code: Optional[str] = Query(
        None, max_length=128, description="只回傳指定 user_code 的 sessions（精準比對）"
    ),
    exclude_user_code: Optional[str] = Query(
        None, max_length=128, description="排除某個 user_code 的 sessions（避免列表出現該使用者）"
    ),
    user_name: Optional[str] = Query(
        None, min_length=1, max_length=128, description="只回傳指定使用者姓名的 sessions（搭配 match）"
    ),
    exclude_user_name: Optional[str] = Query(
        None, min_length=1, max_length=128, description="排除指定使用者姓名的 sessions（搭配 match）"
    ),
    match: str = Query(
        "exact",
        description="姓名比對方式：exact / prefix / contains（不分大小寫）",
        pattern="^(exact|prefix|contains)$",
    ),
    limit_users: int = Query(
        100, ge=1, le=500, description="最多匹配的使用者數（避免同名/模糊匹配過多）"
    ),
    exclude_bound_bags: bool = Query(
        False, description="若為 True，排除已綁定使用者的 bag（只顯示未綁定的 sessions）"
    ),
) -> RealsensePoseExtractorListResponse:
    """
    取得 RealsensePoseExtractor 紀錄列表，支援簡單分頁。
    """
    page = max(1, page)
    page_size = max(1, min(page_size, 100))

    # 篩選規則（避免互斥/模糊的組合）
    if user_code and exclude_user_code:
        raise HTTPException(status_code=400, detail="user_code and exclude_user_code cannot be used together")
    if user_name and exclude_user_name:
        raise HTTPException(status_code=400, detail="user_name and exclude_user_name cannot be used together")
    if (user_code or exclude_user_code) and (user_name or exclude_user_name):
        raise HTTPException(
            status_code=400,
            detail="user_code/exclude_user_code cannot be used together with user_name/exclude_user_name",
        )
    
    # exclude_bound_bags 不能與 user_code/user_name 一起使用（邏輯衝突）
    if exclude_bound_bags and (user_code or user_name):
        raise HTTPException(
            status_code=400,
            detail="exclude_bound_bags cannot be used together with user_code/user_name",
        )

    # 建立查詢條件
    if user_code:
        query = RealsensePoseExtractor.find(RealsensePoseExtractor.user_code == user_code)
    elif exclude_user_code:
        query = RealsensePoseExtractor.find({"user_code": {"$nin": [exclude_user_code]}})
    elif user_name or exclude_user_name:
        query_text = (user_name or exclude_user_name or "").strip()
        if not query_text:
            raise HTTPException(status_code=400, detail="user_name cannot be empty")

        escaped = re.escape(query_text)
        if match == "exact":
            name_pattern = f"^{escaped}$"
        elif match == "prefix":
            name_pattern = f"^{escaped}"
        else:  # contains：任意位置包含
            name_pattern = escaped

        users: List[UserProfile] = await (
            UserProfile.find({"name": {"$regex": name_pattern, "$options": "i"}})
            .sort([("created_at", -1)])
            .limit(limit_users)
            .to_list()
        )
        user_codes = [u.user_code for u in users]

        if user_name:
            # 沒找到 user -> 直接回空（符合「只回傳指定使用者」的直覺）
            if not user_codes:
                return RealsensePoseExtractorListResponse(
                    total=0,
                    page=1,
                    page_size=page_size,
                    total_pages=0,
                    items=[],
                )
            query = RealsensePoseExtractor.find({"user_code": {"$in": user_codes}})
        else:
            # 排除：若沒找到 user，等同不排除任何資料
            if not user_codes:
                query = RealsensePoseExtractor.find_all()
            else:
                query = RealsensePoseExtractor.find({"user_code": {"$nin": user_codes}})
    else:
        query = RealsensePoseExtractor.find_all()

    # 若要排除已綁定的 bag，使用 aggregation 優化查詢
    if exclude_bound_bags:
        # 使用 distinct 直接取得所有已綁定的 bag_hash（更快）
        bound_bag_hashes = await RealsensePoseExtractor.find(
            RealsensePoseExtractor.user_code != None,
            RealsensePoseExtractor.bag_hash != None,
        ).distinct("bag_hash")
        
        if bound_bag_hashes:
            # 排除這些 bag_hash
            query = query.find({"bag_hash": {"$nin": bound_bag_hashes}})

    total = await query.count()
    total_pages = math.ceil(total / page_size) if total else 0

    if total_pages and page > total_pages:
        page = total_pages

    skip = (page - 1) * page_size if total else 0

    docs: List[RealsensePoseExtractor] = await (
        query.sort([("created_at", -1)]).skip(skip).limit(page_size).to_list()
    )

    items = [
        RealsensePoseExtractorItem(
            session_name=doc.session_name,
            npy_path=doc.npy_path,
            video_path=doc.video_path,
            bag_path=doc.bag_path,
            bag_filename=doc.bag_filename,
            bag_hash=doc.bag_hash,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
        )
        for doc in docs
    ]

    return RealsensePoseExtractorListResponse(
        total=total,
        page=page if total else 1,
        page_size=page_size,
        total_pages=total_pages,
        items=items,
    )


@router.get("/sessions/search", response_model=SessionNameSuggestionResponse)
async def search_session_names(
    keyword: str = Query(..., min_length=1, max_length=128),
    limit: int = Query(10, ge=1, le=50),
) -> SessionNameSuggestionResponse:
    """
    依 session_name 前綴搜尋 RealsensePoseExtractor 紀錄，回傳自動完成建議。
    """
    query_text = keyword.strip()
    if not query_text:
        return SessionNameSuggestionResponse(items=[])

    escaped = re.escape(query_text)
    pattern = f"^{escaped}"

    docs: List[RealsensePoseExtractor] = await (
        RealsensePoseExtractor.find(
            {"session_name": {"$regex": pattern, "$options": "i"}}
        )
        .sort([("created_at", -1)])
        .limit(limit)
        .to_list()
    )

    return SessionNameSuggestionResponse(
        items=[doc.session_name for doc in docs],
    )


@router.get("/sessions/{session_name}", response_model=RealsensePoseExtractorItem)
async def get_session_detail(
    session_name: str,
) -> RealsensePoseExtractorItem:
    """
    取得指定 session 的詳細資訊。
    """
    doc: Optional[RealsensePoseExtractor] = await RealsensePoseExtractor.find_one(
        RealsensePoseExtractor.session_name == session_name
    )
    
    if not doc:
        raise HTTPException(status_code=404, detail=f"session not found: {session_name}")
    
    return RealsensePoseExtractorItem(
        session_name=doc.session_name,
        npy_path=doc.npy_path,
        video_path=doc.video_path,
        bag_path=doc.bag_path,
        bag_filename=doc.bag_filename,
        bag_hash=doc.bag_hash,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


@router.get("/sessions/{session_name}/video-availability", response_model=VideoAvailabilityResponse)
async def check_video_availability(
    session_name: str,
) -> VideoAvailabilityResponse:
    """
    檢查指定 session 是否有影片可用。
    
    - 檢查 DB 中是否有 video_path 記錄
    - 檢查影片檔案是否實際存在於磁碟上
    - 輕量級查詢，適合前端快速檢查影片可用性
    """
    doc: Optional[RealsensePoseExtractor] = await RealsensePoseExtractor.find_one(
        RealsensePoseExtractor.session_name == session_name
    )
    
    if not doc:
        raise HTTPException(status_code=404, detail=f"session not found: {session_name}")
    
    has_video = bool(doc.video_path)
    video_exists = False
    
    if has_video:
        video_file = Path(doc.video_path)
        video_exists = video_file.exists()
    
    return VideoAvailabilityResponse(
        session_name=session_name,
        has_video=has_video,
        video_exists=video_exists,
        video_path=doc.video_path,
    )


async def _safe_unlink_if_allowed(
    file_path: Path,
    *,
    allowed_base_dir: Path,
) -> bool:
    """
    安全刪檔：
    - 只允許刪除位於 allowed_base_dir 之下的檔案，避免刪到不該刪的路徑
    """
    try:
        p = file_path.resolve()
        base = allowed_base_dir.resolve()
    except Exception:
        # resolve 失敗時，不做刪除
        return False

    if base not in p.parents and p != base:
        return False

    if not p.exists():
        return False

    # Windows 下若檔案被占用會丟例外；由呼叫端決定要不要擋掉
    await asyncio.to_thread(p.unlink)
    return True


@public_router.get("/sessions/{session_name}/video")
async def get_session_video(
    session_name: str,
    request: Request,
):
    """
    取得指定 session 的影片檔案（串流播放，支援 Range Requests）。
    
    - 檢查 DB 是否有該 session
    - 檢查是否有 video_path 且檔案存在
    - 支援 HTTP Range Requests（讓瀏覽器可以 seek）
    - 回傳影片檔案供前端播放
    """
    doc: Optional[RealsensePoseExtractor] = await RealsensePoseExtractor.find_one(
        RealsensePoseExtractor.session_name == session_name
    )
    
    if not doc:
        raise HTTPException(status_code=404, detail=f"session not found: {session_name}")
    
    if not doc.video_path:
        raise HTTPException(
            status_code=404, 
            detail=f"video not available for session: {session_name} (video was not generated during extraction)"
        )
    
    video_file = Path(doc.video_path)
    
    # 安全檢查：確保檔案在允許的目錄內
    try:
        video_file_resolved = video_file.resolve()
        video_dir_resolved = Path(VIDEO_DIR).resolve()
        if video_dir_resolved not in video_file_resolved.parents and video_file_resolved.parent != video_dir_resolved:
            raise HTTPException(status_code=403, detail="access denied: invalid video path")
    except Exception:
        raise HTTPException(status_code=500, detail="failed to resolve video path")
    
    if not video_file.exists():
        raise HTTPException(
            status_code=404, 
            detail=f"video file not found: {session_name} (file may have been deleted)"
        )
    
    # 取得檔案大小（同步操作，但很快）
    file_size = video_file.stat().st_size
    
    # 處理 Range Request
    range_header = request.headers.get("range")
    
    async def create_file_iterator(start: int, length: int):
        """建立檔案迭代器，處理各種中斷情況"""
        f = None
        try:
            f = await aiofiles.open(video_file, "rb")
            await f.seek(start)
            remaining = length
            while remaining > 0:
                # 檢查客戶端是否已斷線
                if await request.is_disconnected():
                    break
                read_size = min(1048576, remaining)  # 1MB chunk
                data = await f.read(read_size)
                if not data:
                    break
                remaining -= len(data)
                yield data
        except (asyncio.CancelledError, GeneratorExit):
            # 客戶端取消或 generator 關閉，正常結束
            pass
        except ConnectionResetError:
            # 連線被重置
            pass
        except BrokenPipeError:
            # 管道中斷
            pass
        except Exception:
            # 其他錯誤也要確保資源釋放
            pass
        finally:
            if f is not None:
                try:
                    await f.close()
                except Exception:
                    pass
    
    if range_header:
        # 解析 Range header (格式: "bytes=start-end")
        try:
            range_match = range_header.replace("bytes=", "").split("-")
            start = int(range_match[0]) if range_match[0] else 0
            end = int(range_match[1]) if len(range_match) > 1 and range_match[1] else file_size - 1
            end = min(end, file_size - 1)
            start = max(0, min(start, file_size - 1))
        except (ValueError, IndexError):
            raise HTTPException(status_code=416, detail="Invalid Range header")
        
        if start > end:
            raise HTTPException(status_code=416, detail="Range Not Satisfiable")
        
        chunk_size = end - start + 1
        
        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(chunk_size),
            "Content-Type": "video/mp4",
        }
        
        return StreamingResponse(
            create_file_iterator(start, chunk_size),
            status_code=206,
            headers=headers,
        )
    
    # 沒有 Range Request，回傳完整檔案
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(file_size),
        "Content-Type": "video/mp4",
        "Cache-Control": "public, max-age=3600",
    }
    
    return StreamingResponse(
        create_file_iterator(0, file_size),
        headers=headers,
        media_type="video/mp4",
    )


async def _delete_single_session(session_name: str) -> DeleteSessionResponse:
    """
    刪除單個 session 的內部函數（供單一刪除和批量刪除共用）。
    
    Returns:
        DeleteSessionResponse: 刪除結果
    
    Raises:
        HTTPException: 當 session 不存在時
    """
    doc: Optional[RealsensePoseExtractor] = await RealsensePoseExtractor.find_one(
        RealsensePoseExtractor.session_name == session_name
    )
    if not doc:
        raise HTTPException(status_code=404, detail=f"session not found: {session_name}")

    deleted_npy = False
    deleted_video = False
    deleted_bag = False

    # npy：通常每個 session 都是獨立的檔案
    try:
        deleted_npy = await _safe_unlink_if_allowed(
            Path(doc.npy_path),
            allowed_base_dir=Path(NPY_DIR),
        )
    except Exception:
        # 保持與舊行為一致：刪檔失敗不影響刪 DB
        pass

    # video：每個 session 獨立的影片檔
    if doc.video_path:
        try:
            deleted_video = await _safe_unlink_if_allowed(
                Path(doc.video_path),
                allowed_base_dir=Path(VIDEO_DIR),
            )
        except Exception:
            pass

    # bag：可能被多個 session 共用（依 bag_hash），避免誤刪
    try:
        can_delete_bag = True
        if doc.bag_hash:
            remaining = await RealsensePoseExtractor.count(
                RealsensePoseExtractor.bag_hash == doc.bag_hash,
                RealsensePoseExtractor.session_name != doc.session_name,
            )
            if remaining > 0:
                logger.info(f"bag {doc.bag_path} is shared with {remaining} sessions, cannot delete")
                can_delete_bag = False

        if can_delete_bag:
            deleted_bag = await _safe_unlink_if_allowed(
                Path(doc.bag_path),
                allowed_base_dir=Path(BAG_DIR),
            )
    except Exception:
        # 保持與舊行為一致：刪檔失敗不影響刪 DB
        pass

    # 最後刪 DB（即使檔案刪除失敗，也允許刪 DB）
    await doc.delete()

    return DeleteSessionResponse(
        session_name=session_name,
        deleted_db=True,
        deleted_npy=deleted_npy,
        deleted_video=deleted_video,
        deleted_bag=deleted_bag,
    )


@router.post("/sessions/delete", response_model=DeleteSessionsResponse)
async def delete_realsense_pose_sessions(
    request: DeleteSessionsRequest,
) -> DeleteSessionsResponse:
    """
    刪除一個或多個 session：
    - 刪除 DB 紀錄
    - 會嘗試刪除對應的 npy 檔
    - 會嘗試刪除對應的 video 檔（若有）
    - bag 檔只有在沒有其他 session 使用相同 bag_hash 時才會刪
    - 即使部分刪除失敗，也會繼續處理其他 session
    
    Returns:
        DeleteSessionsResponse: 包含總體統計和每個 session 的詳細結果
    """
    total_requested = len(request.session_names)
    deleted_sessions = 0
    deleted_db = 0
    deleted_npy = 0
    deleted_video = 0
    deleted_bag = 0
    failed: List[str] = []
    details: List[DeleteSessionResponse] = []

    for session_name in request.session_names:
        try:
            result = await _delete_single_session(session_name)
            details.append(result)
            deleted_sessions += 1
            if result.deleted_db:
                deleted_db += 1
            if result.deleted_npy:
                deleted_npy += 1
            if result.deleted_video:
                deleted_video += 1
            if result.deleted_bag:
                deleted_bag += 1
        except HTTPException as e:
            logger.warning(f"Failed to delete session {session_name}: {e.detail}")
            failed.append(session_name)
        except Exception as e:
            logger.error(f"Unexpected error deleting session {session_name}: {e}")
            failed.append(session_name)

    return DeleteSessionsResponse(
        total_requested=total_requested,
        deleted_sessions=deleted_sessions,
        deleted_db=deleted_db,
        deleted_npy=deleted_npy,
        deleted_video=deleted_video,
        deleted_bag=deleted_bag,
        failed=failed,
        details=details,
    )


def _job_to_status_response(job: RealsenseExtractJob) -> ExtractJobStatusResponse:
    result: Optional[ExtractResponse] = None
    if job.status == "succeeded" and job.bag_path and job.npy_path and job.session_name:
        from pathlib import Path
        result = ExtractResponse(
            bag_path=job.bag_path,
            bag_filename=Path(job.bag_path).name,
            npy_path=job.npy_path,
            session_name=job.session_name,
            bag_hash=job.bag_hash,
            success=True,
        )

    return ExtractJobStatusResponse(
        job_id=str(job.id),
        status=job.status,
        created_at=job.created_at,
        updated_at=job.updated_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        error=job.error,
        result=result,
    )


@router.get("/extract/jobs/{job_id}", response_model=ExtractJobStatusResponse, name="get_extract_job")
async def get_extract_job(job_id: str) -> ExtractJobStatusResponse:
    try:
        oid = ObjectId(job_id)
    except Exception:
        raise HTTPException(status_code=400, detail=f"invalid job_id: {job_id}")

    job = await RealsenseExtractJob.get(oid)
    if not job:
        raise HTTPException(status_code=404, detail=f"job not found: {job_id}")
    return _job_to_status_response(job)


async def _run_extract_job(job_id: str) -> None:
    """
    在背景執行提取任務。

    - best-effort：若 API 服務重啟，正在執行中的 job 可能會停在 running（目前未做自動續跑/恢復）。
    """
    try:
        try:
            oid = ObjectId(job_id)
        except Exception:
            return

        job = await RealsenseExtractJob.get(oid)
        if not job:
            return

        now = datetime.now()
        job.status = "running"
        job.started_at = now
        job.updated_at = now
        await job.save()

        # 重新驗證當前狀態（避免以過期假設寫壞資料/覆蓋不該覆蓋的紀錄）
        await validate_extract_business_rules(
            session_name=job.session_name,
            user_code=job.user_code,
            force=job.force,
        )

        bag_path_obj = Path(job.bag_resolved_path)
        result = await run_extraction_pipeline(
            default_config=default_config,
            bag_source_path=bag_path_obj,
            session_name=job.session_name,
            user_code=job.user_code,
            config_dict=(job.config or {}),
        )

        now = datetime.now()
        job.status = "succeeded"
        job.error = None
        job.bag_hash = result.bag_hash
        job.bag_path = result.bag_path
        job.npy_path = result.npy_path
        job.updated_at = now
        job.finished_at = now
        await job.save()
    except Exception as e:
        try:
            job = await RealsenseExtractJob.get(ObjectId(job_id))
            if job:
                now = datetime.now()
                job.status = "failed"
                # HTTPException 會有更乾淨的訊息；一般 Exception 就用 str(e)
                if isinstance(e, HTTPException):
                    job.error = str(getattr(e, "detail", str(e)))
                else:
                    job.error = str(e)
                job.updated_at = now
                job.finished_at = now
                await job.save()
        except Exception:
            pass
    finally:
        _JOB_TASKS.pop(job_id, None)


@router.post("/extract", response_model=Union[ExtractResponse, ExtractJobCreatedResponse])
async def extract_realsense_pose(
    request: Request,
    response: Response,
    bag_path: Optional[str] = None,
    bag_id: Optional[str] = None,
    session_name: Optional[str] = None,
    user_code: Optional[str] = None,
    background: bool = Query(
        True,
        description="若為 True，建立背景任務並立刻回 202 + job_id（避免長任務造成連線 timeout）。",
    ),
    config: Optional[ExtractRequest] = Body(None),
):
    config = config or ExtractRequest()
    bag_input = parse_bag_input(bag_path=bag_path, bag_id=bag_id)

    # 預設 session_name 為輸入檔名（bag_id/bag_path 皆可）
    if session_name is None:
        session_name = f"{Path(bag_input).stem}"

    bag_path_obj = await resolve_bag_path_obj(bag_input)
    await validate_extract_business_rules(
        session_name=session_name,
        user_code=user_code,
        force=bool(config.force),
    )

    if background:
        now = datetime.now()
        job = RealsenseExtractJob(
            status="pending",
            bag_input=bag_input,
            bag_resolved_path=str(bag_path_obj),
            session_name=session_name,
            user_code=user_code,
            force=bool(config.force),
            config=config.model_dump(),
            created_at=now,
            updated_at=now,
        )
        await job.insert()

        job_id = str(job.id)
        _JOB_TASKS[job_id] = asyncio.create_task(_run_extract_job(job_id))

        # 背景任務：回 202 Accepted（已接受請求，稍後完成）
        response.status_code = 202
        status_url = str(request.url_for("get_extract_job", job_id=job_id))
        return ExtractJobCreatedResponse(
            job_id=job_id,
            status=job.status,
            created_at=job.created_at,
            status_url=status_url,
        )

    try:
        return await run_extraction_pipeline(
            default_config=default_config,
            bag_source_path=bag_path_obj,
            session_name=session_name,
            user_code=user_code,
            config_dict=config.model_dump(),
        )
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"processing failed: {e}")