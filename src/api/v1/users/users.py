import math
import re
from datetime import datetime
from typing import Dict, List, Optional, Type

from fastapi import APIRouter, HTTPException, Query
from pymongo.errors import DuplicateKeyError

from db import (
    DiagnosisInfo,
    LifestyleInfo,
    MedicalHistoryInfo,
    RealsensePoseExtractor,
    SymptomInfo,
    UserProfile,
)

from .models import (
    CohortStatItem,
    CohortStatsResponse,
    DeleteUserResult,
    DeleteUsersRequest,
    DeleteUsersResponse,
    FindUserByBagRequest,
    FindUserByBagResponse,
    LinkSessionRequest,
    UnlinkSessionRequest,
    UnlinkSessionResponse,
    UserCreateRequest,
    UserDetailResponse,
    UserItem,
    UserListItem,
    UserListResponse,
    UserSearchSuggestionResponse,
    UserSessionItem,
    UserUpdateRequest,
)

router = APIRouter(prefix="/users", tags=["users"])

def _to_user_item(doc: UserProfile) -> UserItem:
    """把 DB 的 UserProfile 轉成對外回傳用的 UserItem。"""
    return UserItem(
        user_code=doc.user_code,
        name=doc.name,
        assessment_date=doc.assessment_date,
        sex=doc.sex,
        age_years=doc.age_years,
        height_cm=doc.height_cm,
        weight_kg=doc.weight_kg,
        bmi=doc.bmi,
        education_level=doc.education_level,
        cohort=doc.cohort,
        diagnosis=doc.diagnosis,
        medical_history=doc.medical_history,
        symptoms=doc.symptoms,
        lifestyle=doc.lifestyle,
        notes=doc.notes,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


def _to_session_item(doc: RealsensePoseExtractor) -> UserSessionItem:
    """把 DB 的 RealsensePoseExtractor 轉成對外回傳用的 UserSessionItem。"""
    return UserSessionItem(
        session_name=doc.session_name,
        user_code=doc.user_code,
        npy_path=doc.npy_path,
        bag_path=doc.bag_path,
        bag_filename=doc.bag_filename,
        bag_hash=doc.bag_hash,
        video_path=doc.video_path,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


def _deep_merge(a: dict, b: dict) -> dict:
    """遞迴合併 dict（b 覆蓋 a）。

    用途：PATCH 更新 nested 結構時，保留未提供的欄位。
    例：existing.diagnosis = {"diagnosis":"stroke","affected_side":"L"}
        patch.diagnosis    = {"affected_side":"R"}
        => merged          = {"diagnosis":"stroke","affected_side":"R"}
    """
    out = dict(a)
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


# nested 欄位對應的 Pydantic 類別（用來把合併後的 dict 轉回正確型別）
_NESTED_MODEL_CLS: Dict[str, Type] = {
    "diagnosis": DiagnosisInfo,
    "medical_history": MedicalHistoryInfo,
    "symptoms": SymptomInfo,
    "lifestyle": LifestyleInfo,
}


@router.post("", response_model=UserItem)
async def create_user(payload: UserCreateRequest) -> UserItem:
    """建立使用者（個案）。

    - 若 payload.user_code 沒提供，DB 端會自動產生 UUID 字串
    - user_code 重複時回 409（Conflict）
    - name 重複時回 409（Conflict）
    """
    data = payload.model_dump(exclude_unset=True)

    try:
        doc = UserProfile(**data)
        await doc.insert()
        return _to_user_item(doc)
    except DuplicateKeyError as e:
        # 判斷是 user_code 還是 name 重複
        error_msg = str(e)
        if "uq_name" in error_msg or "name" in error_msg:
            raise HTTPException(status_code=409, detail="name already exists") from None
        raise HTTPException(status_code=409, detail="user_code already exists") from None


@router.get("", response_model=UserListResponse)
async def list_users(
    page: int = 1,
    page_size: int = 20,
) -> UserListResponse:
    """
    取得使用者列表，支援簡單分頁（類似 /sessions）。
    """
    page = max(1, page)
    page_size = max(1, min(page_size, 100))

    total = await UserProfile.count()
    total_pages = math.ceil(total / page_size) if total else 0

    if total_pages and page > total_pages:
        page = total_pages

    skip = (page - 1) * page_size if total else 0

    docs: List[UserProfile] = await (
        UserProfile.find_all()
        .sort([("created_at", -1)])
        .skip(skip)
        .limit(page_size)
        .to_list()
    )

    items = [
        UserListItem(
            user_code=doc.user_code,
            name=doc.name,
            cohort=doc.cohort,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
        )
        for doc in docs
    ]

    return UserListResponse(
        total=total,
        page=page if total else 1,
        page_size=page_size,
        total_pages=total_pages,
        items=items,
    )


@router.get("/cohorts", response_model=CohortStatsResponse)
async def get_cohort_stats() -> CohortStatsResponse:
    """
    取得所有族群的統計資訊。

    使用 MongoDB aggregation 統計每個族群的使用者數量。
    由於 cohort 是陣列，一個使用者可屬於多個族群，
    各族群人數總和可能超過總使用者數。
    """
    pipeline = [
        # 若 cohort 不存在或為空陣列，設為預設值
        {"$project": {
            "cohort": {
                "$ifNull": [
                    {"$cond": [{"$gt": [{"$size": {"$ifNull": ["$cohort", []]}}, 0]}, "$cohort", None]},
                    ["正常人"]
                ]
            }
        }},
        {"$unwind": "$cohort"},
        {"$group": {"_id": "$cohort", "count": {"$sum": 1}}},
        {"$sort": {"count": -1, "_id": -1}},
    ]

    try:
        results = await UserProfile.aggregate(pipeline).to_list()
        return CohortStatsResponse(
            cohorts=[CohortStatItem(cohort=r["_id"], user_count=r["count"]) for r in results],
            total_cohorts=len(results),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from None



@router.get("/search", response_model=UserSearchSuggestionResponse)
async def search_user_names(
    keyword: Optional[str] = Query(None, max_length=128, description="姓名關鍵字（前綴匹配）"),
    cohort: Optional[List[str]] = Query(None, description="族群篩選列表（例如：['中風', '高齡']），會篩選同時屬於所有指定族群的使用者"),
    page: int = Query(1, ge=1, description="頁碼（從 1 開始）"),
    page_size: int = Query(20, ge=1, le=200, description="每頁筆數"),
) -> UserSearchSuggestionResponse:
    """
    搜尋使用者，支援姓名關鍵字和族群篩選。

    - **keyword**: 姓名前綴匹配（可選）
    - **cohort**: 族群篩選列表，會篩選同時屬於所有指定族群的使用者（可選）
    - 兩者都不填則回傳所有使用者
    - 兩者都填則同時滿足兩個條件
    """
    # 建立查詢條件
    conditions = []

    # 姓名關鍵字篩選
    if keyword:
        query_text = keyword.strip()
        if query_text:
            escaped = re.escape(query_text)
            pattern = f"^{escaped}"
            conditions.append({"name": {"$regex": pattern, "$options": "i"}})

    # 族群篩選（cohort 是陣列，使用 $all 確保使用者屬於所有指定的族群）
    if cohort:
        # 過濾掉空字串
        valid_cohorts = [c.strip() for c in cohort if c and c.strip()]
        if valid_cohorts:
            # $all 會篩選陣列包含所有指定元素的文件
            conditions.append({"cohort": {"$all": valid_cohorts}})

    # 組合查詢條件
    if conditions:
        if len(conditions) == 1:
            filter_dict = conditions[0]
        else:
            filter_dict = {"$and": conditions}
        query = UserProfile.find(filter_dict)
    else:
        # 沒有任何篩選條件，回傳所有使用者
        query = UserProfile.find_all()

    total = await query.count()
    skip = (page - 1) * page_size
    total_pages = int(math.ceil(total / page_size)) if total else 0

    docs: List[UserProfile] = await (
        query.sort([("created_at", -1)]).skip(skip).limit(page_size).to_list()
    )

    return UserSearchSuggestionResponse(
        total=total,
        page=page if total else 1,
        page_size=page_size,
        total_pages=total_pages,
        items=[
            {
                "user_code": doc.user_code,
                "name": doc.name,
                "cohort": doc.cohort,
                "created_at": doc.created_at,
            }
            for doc in docs
        ],
    )

@router.post("/find-by-bag", response_model=FindUserByBagResponse)
async def find_user_by_bag(payload: FindUserByBagRequest) -> FindUserByBagResponse:
    """透過 BAG 檔案名稱尋找使用者。

    - 使用 bag_filename 精確比對，找出所有使用此 BAG 檔案的 sessions
    - 由於一個 bag 只能綁定一個使用者，最多只會找到一個使用者
    - 使用索引優化查詢效能
    """
    # 優化查詢：先找有綁定使用者的 session（利用索引）
    first_session_with_user: Optional[RealsensePoseExtractor] = await (
        RealsensePoseExtractor.find(
            RealsensePoseExtractor.bag_filename == payload.bag_filename,
            RealsensePoseExtractor.user_code != None,
        )
        .sort([("created_at", -1)])
        .first_or_none()
    )

    # 若沒有綁定使用者的 session，查詢所有 sessions（含未綁定的）
    if not first_session_with_user:
        all_sessions: List[RealsensePoseExtractor] = await (
            RealsensePoseExtractor.find(
                RealsensePoseExtractor.bag_filename == payload.bag_filename
            )
            .to_list()
        )
        return FindUserByBagResponse(
            found=False,
            user=None,
            sessions=[_to_session_item(s) for s in all_sessions],
            total_sessions=len(all_sessions),
        )

    # 找到綁定的使用者，取得完整資料
    user_code = first_session_with_user.user_code
    user: Optional[UserProfile] = await UserProfile.find_one(
        UserProfile.user_code == user_code
    )

    if not user:
        # 資料一致性問題：session 有 user_code 但找不到對應的 user
        return FindUserByBagResponse(
            found=False,
            user=None,
            sessions=[_to_session_item(first_session_with_user)],
            total_sessions=1,
        )

    # 取得該使用者的所有 sessions（不限於這個 BAG 檔案）
    all_user_sessions: List[RealsensePoseExtractor] = await (
        RealsensePoseExtractor.find(
            RealsensePoseExtractor.user_code == user_code,
        )
        .sort([("created_at", -1)])
        .to_list()
    )
    
    return FindUserByBagResponse(
        found=True,
        user=_to_user_item(user),
        sessions=[_to_session_item(s) for s in all_user_sessions],
        total_sessions=len(all_user_sessions),
    )


@router.get("/{user_code}", response_model=UserDetailResponse)
async def get_user_detail(user_code: str) -> UserDetailResponse:
    """取得使用者 + 其綁定的 sessions(bag) 列表。"""
    user: Optional[UserProfile] = await UserProfile.find_one(UserProfile.user_code == user_code)
    if not user:
        raise HTTPException(status_code=404, detail=f"user not found: {user_code}")

    # 依使用者的 user_code 查出所有 session（由新到舊）
    sessions = await (
        RealsensePoseExtractor.find(RealsensePoseExtractor.user_code == user_code)
        .sort([("created_at", -1)])
        .to_list()
    )

    return UserDetailResponse(
        user=_to_user_item(user),
        sessions=[_to_session_item(s) for s in sessions],
    )


@router.patch("/{user_code}", response_model=UserItem)
async def update_user(user_code: str, payload: UserUpdateRequest) -> UserItem:
    """更新使用者資料（partial update）。"""
    user: Optional[UserProfile] = await UserProfile.find_one(UserProfile.user_code == user_code)
    if not user:
        raise HTTPException(status_code=404, detail=f"user not found: {user_code}")

    # exclude_unset=True：只拿使用者有傳的欄位（PATCH 語意）
    patch = payload.model_dump(exclude_unset=True)

    # nested sections: merge instead of overwriting whole object
    for field, model_cls in _NESTED_MODEL_CLS.items():
        if field not in patch:
            continue

        value = patch.pop(field)
        if value is None:
            setattr(user, field, None)
            continue

        existing = getattr(user, field, None)
        existing_dict = existing.model_dump() if existing is not None else {}
        merged = _deep_merge(existing_dict, value)
        setattr(user, field, model_cls(**merged))

    # simple fields
    for k, v in patch.items():
        setattr(user, k, v)

    # 手動更新 updated_at（created_at/updated_at 目前是我們自管，而不是 DB trigger）
    user.updated_at = datetime.now()
    
    try:
        await user.save()
    except DuplicateKeyError as e:
        error_msg = str(e)
        if "uq_name" in error_msg or "name" in error_msg:
            raise HTTPException(status_code=409, detail="name already exists") from None
        raise HTTPException(status_code=409, detail="duplicate key error") from None
    
    return _to_user_item(user)


@router.post("/{user_code}/sessions/link", response_model=UserSessionItem)
async def link_user_to_session(user_code: str, payload: LinkSessionRequest) -> UserSessionItem:
    """把某個 session(bag) 綁定到指定使用者。

    - payload 允許用 session_name 或 bag_filename 來定位 session（擇一）
    - 綁定方式：把 session.user_code 設成 user_code
    - 限制：一個 bag（bag_filename）只能綁定一個使用者
    """
    user: Optional[UserProfile] = await UserProfile.find_one(UserProfile.user_code == user_code)
    if not user:
        raise HTTPException(status_code=404, detail=f"user not found: {user_code}")

    session: Optional[RealsensePoseExtractor] = None
    if payload.session_name:
        # 以 session_name 定位 session
        session = await RealsensePoseExtractor.find_one(
            RealsensePoseExtractor.session_name == payload.session_name
        )
    elif payload.bag_filename:
        # 以 bag_filename 定位 session（推薦）
        session = await RealsensePoseExtractor.find_one(
            RealsensePoseExtractor.bag_filename == payload.bag_filename
        )

    if not session:
        raise HTTPException(status_code=404, detail="session not found")

    # 檢查此 session 是否已被其他使用者綁定（一個 session 只能綁定一個使用者）
    if session.user_code and session.user_code != user_code:
        raise HTTPException(
            status_code=409,
            detail=f"session is already linked to another user: {session.user_code}",
        )

    # 執行綁定
    session.user_code = user_code
    session.updated_at = datetime.now()
    await session.save()

    return _to_session_item(session)


@router.post("/{user_code}/sessions/unlink", response_model=UnlinkSessionResponse)
async def unlink_user_from_session(
    user_code: str,
    payload: UnlinkSessionRequest,
    force: bool = Query(
        False,
        description="若為 True，允許解除任何 user_code（即使目前不是綁在這個 user 上）；預設 False 會檢查一致性。",
    ),
) -> UnlinkSessionResponse:
    """把一個或多個 session(bag) 從指定使用者解除綁定（批量操作）。

    - payload 用 session_names 或 bag_filenames 列表來指定要解除的 sessions（擇一，支援單一或多個）
    - 若 payload.unlink_all=true，會一次解除該 user 綁定的所有 sessions
    - 預設會要求 session.user_code == user_code；不符合會略過並記錄在 failed 列表
    - 解除綁定方式：把 session.user_code 設成 None
    """
    user: Optional[UserProfile] = await UserProfile.find_one(UserProfile.user_code == user_code)
    if not user:
        raise HTTPException(status_code=404, detail=f"user not found: {user_code}")

    # 一次解除全部（只影響目前綁在此 user_code 的 sessions，安全）
    if payload.unlink_all:
        sessions: List[RealsensePoseExtractor] = await (
            RealsensePoseExtractor.find(RealsensePoseExtractor.user_code == user_code).to_list()
        )
        unlinked = 0
        now = datetime.now()
        for s in sessions:
            s.user_code = None
            s.updated_at = now
            await s.save()
            unlinked += 1

        return UnlinkSessionResponse(
            user_code=user_code,
            mode="all",
            unlinked_sessions=unlinked,
            failed=None,
        )

    # 批量解除（統一使用 list，支援單一或多個）
    unlinked = 0
    failed: List[str] = []
    now = datetime.now()
    
    if payload.session_names:
        for session_name in payload.session_names:
            try:
                session = await RealsensePoseExtractor.find_one(
                    RealsensePoseExtractor.session_name == session_name
                )
                if not session:
                    failed.append(session_name)
                    continue
                
                # 一致性檢查
                if (not force) and (session.user_code != user_code):
                    failed.append(session_name)
                    continue
                
                session.user_code = None
                session.updated_at = now
                await session.save()
                unlinked += 1
            except Exception:
                failed.append(session_name)
                continue
    
    elif payload.bag_filenames:
        for bag_filename in payload.bag_filenames:
            try:
                session = await RealsensePoseExtractor.find_one(
                    RealsensePoseExtractor.bag_filename == bag_filename
                )
                if not session:
                    failed.append(bag_filename)
                    continue
                
                # 一致性檢查
                if (not force) and (session.user_code != user_code):
                    failed.append(bag_filename)
                    continue
                
                session.user_code = None
                session.updated_at = now
                await session.save()
                unlinked += 1
            except Exception:
                failed.append(bag_filename)
                continue
    
    return UnlinkSessionResponse(
        user_code=user_code,
        mode="batch",
        unlinked_sessions=unlinked,
        failed=failed if failed else None,
    )


@router.post("/delete", response_model=DeleteUsersResponse)
async def delete_users(
    payload: DeleteUsersRequest,
) -> DeleteUsersResponse:
    """
    批量刪除使用者。

    預設行為（delete_sessions=false）：
    - 刪除 UserProfile
    - 將此 user_code 綁定的 RealsensePoseExtractor.user_code 設為 None（解除綁定）
    
    若 delete_sessions=true：
    - 刪除 UserProfile
    - 連同該使用者綁定的 sessions(DB 紀錄) 一併刪除
    """
    total_requested = len(payload.user_codes)
    deleted_users = 0
    total_unlinked_sessions = 0
    total_deleted_sessions = 0
    failed: List[str] = []
    details: List[DeleteUserResult] = []

    for user_code in payload.user_codes:
        try:
            user: Optional[UserProfile] = await UserProfile.find_one(
                UserProfile.user_code == user_code
            )
            if not user:
                failed.append(user_code)
                continue

            sessions: List[RealsensePoseExtractor] = await (
                RealsensePoseExtractor.find(RealsensePoseExtractor.user_code == user_code)
                .to_list()
            )

            unlinked = 0
            deleted = 0
            now = datetime.now()

            if payload.delete_sessions:
                for s in sessions:
                    await s.delete()
                    deleted += 1
            else:
                for s in sessions:
                    s.user_code = None
                    s.updated_at = now
                    await s.save()
                    unlinked += 1

            await user.delete()

            details.append(DeleteUserResult(
                user_code=user_code,
                deleted_user=True,
                unlinked_sessions=unlinked,
                deleted_sessions=deleted,
            ))
            deleted_users += 1
            total_unlinked_sessions += unlinked
            total_deleted_sessions += deleted

        except Exception:
            failed.append(user_code)
            continue

    return DeleteUsersResponse(
        total_requested=total_requested,
        deleted_users=deleted_users,
        total_unlinked_sessions=total_unlinked_sessions,
        total_deleted_sessions=total_deleted_sessions,
        failed=failed,
        details=details,
    )
