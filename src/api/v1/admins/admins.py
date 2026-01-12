import math
import secrets
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status

from db import AdminAccount, AdminInvitation, AdminSession

from .models import (
    AuthTokenResponse,
    AdminPublic,
    AdminListItem,
    AdminListResponse,
    DeleteAdminResponse,
    InvitationCreateRequest,
    InvitationResponse,
    LoginRequest,
    ChangePasswordRequest,
    AdminUpdateMeRequest,
    RegisterRequest,
    LogoutResponse,
)
from .auth_utils import (
    ADMIN_TOKEN_COOKIE_NAME,
    clear_auth_cookie,
    get_active_session,
    hash_password,
    issue_session,
    set_auth_cookie,
    verify_password,
)
from .dependencies import (
    invalidate_admin_auth_cache_by_admin_code,
    invalidate_admin_auth_cache_by_token,
    require_admin_account,
)

router = APIRouter(prefix="/admins", tags=["admins"])

def _to_public_admin(doc: AdminAccount) -> AdminPublic:
    # 轉為對外回傳的公開欄位
    return AdminPublic(
        admin_code=doc.admin_code,
        username=doc.username,
        invited_by_code=doc.invited_by_code,
        created_at=doc.created_at,
    )

async def _generate_invitation_code() -> str:
    # 生成不重複的邀請碼（簡短 URL-safe）
    for _ in range(5):
        code = secrets.token_urlsafe(9)  # ~12 chars, URL-safe
        exists = await AdminInvitation.find_one(AdminInvitation.code == code)
        if not exists:
            return code
    raise HTTPException(status_code=500, detail="failed to generate invitation code")


async def _revoke_active_invitations(inviter_code: str) -> None:
    # 註銷某個邀請人尚未使用且未過期的邀請碼
    now = datetime.now()
    invites = await AdminInvitation.find(
        AdminInvitation.inviter_code == inviter_code,
        AdminInvitation.revoked_at == None,  # noqa: E711
        AdminInvitation.used_at == None,  # noqa: E711
        AdminInvitation.expires_at > now,
    ).to_list()

    for inv in invites:
        inv.revoked_at = now
        inv.updated_at = now
        await inv.save()


def _can_delete(requester: AdminAccount, target: AdminAccount) -> bool:
    # 刪除權限：自己或屬於自己的邀請鏈才可刪除
    if requester.admin_code == target.admin_code:
        return True
    return requester.admin_code in target.inviter_chain


@router.post("/register", response_model=AuthTokenResponse, status_code=status.HTTP_201_CREATED)
async def register_admin(payload: RegisterRequest, response: Response) -> AuthTokenResponse:
    """註冊管理員。

    - 第一位管理員：若目前沒有任何管理員，可直接註冊（不需邀請碼）
    - 之後的管理員：必須使用有效邀請碼，並記錄邀請鏈
    """
    admin_count = await AdminAccount.count()

    invite_doc: Optional[AdminInvitation] = None
    inviter_chain: List[str] = []
    invited_by_code: Optional[str] = None

    if admin_count > 0:
        if not payload.invite_code:
            raise HTTPException(status_code=400, detail="invite_code is required")

        invite_doc = await AdminInvitation.find_one(AdminInvitation.code == payload.invite_code)
        if not invite_doc or not invite_doc.is_active:
            raise HTTPException(status_code=400, detail="invite_code is invalid or expired")

        inviter: Optional[AdminAccount] = await AdminAccount.find_one(AdminAccount.admin_code == invite_doc.inviter_code)
        if not inviter:
            raise HTTPException(status_code=400, detail="inviter no longer exists")

        inviter_chain = list(inviter.inviter_chain) + [inviter.admin_code]
        invited_by_code = inviter.admin_code

    existing = await AdminAccount.find_one(AdminAccount.username == payload.username)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="username already exists")

    salt_hex, hash_hex = hash_password(payload.password)
    now = datetime.now()

    try:
        admin = AdminAccount(
            username=payload.username,
            password_hash=hash_hex,
            password_salt=salt_hex,
            inviter_chain=inviter_chain,
            invited_by_code=invited_by_code,
            created_at=now,
            updated_at=now,
        )
        await admin.insert()
    except Exception:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="username already exists") from None

    if invite_doc:
        invite_doc.used_at = now
        invite_doc.used_by_code = admin.admin_code
        invite_doc.used_by_username = admin.username
        invite_doc.updated_at = now
        await invite_doc.save()

    token, session = await issue_session(admin)
    set_auth_cookie(response, token, session.expires_at)
    return AuthTokenResponse(token=token, expires_at=session.expires_at, admin=_to_public_admin(admin))


@router.post("/login", response_model=AuthTokenResponse)
async def login_admin(payload: LoginRequest, response: Response) -> AuthTokenResponse:
    """登入：驗證帳號密碼，並簽發新的 session token/cookie。"""
    admin: Optional[AdminAccount] = await AdminAccount.find_one(AdminAccount.username == payload.username)
    if not admin:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="admin is not found")

    if not verify_password(payload.password, admin.password_salt, admin.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="password or username is incorrect")

    token, session = await issue_session(admin)
    set_auth_cookie(response, token, session.expires_at)
    return AuthTokenResponse(token=token, expires_at=session.expires_at, admin=_to_public_admin(admin))


@router.post("/password/change", response_model=AuthTokenResponse)
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    current_admin: AdminAccount = Depends(require_admin_account),
) -> AuthTokenResponse:
    """變更密碼：需舊密碼驗證，變更後會撤銷舊 sessions 並簽發新 token/cookie。"""
    if not verify_password(payload.old_password, current_admin.password_salt, current_admin.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid old password")

    # 更新密碼雜湊
    salt_hex, hash_hex = hash_password(payload.new_password)
    current_admin.password_salt = salt_hex
    current_admin.password_hash = hash_hex
    current_admin.updated_at = datetime.now()
    await current_admin.save()

    # 撤銷所有舊 session
    await AdminSession.find(AdminSession.admin_code == current_admin.admin_code).delete()
    # 清除 auth cache，避免已撤銷 token 在 cache TTL 內仍可使用
    await invalidate_admin_auth_cache_by_admin_code(request, current_admin.admin_code)

    # 簽發新 session
    token, session = await issue_session(current_admin)
    set_auth_cookie(response, token, session.expires_at)
    return AuthTokenResponse(token=token, expires_at=session.expires_at, admin=_to_public_admin(current_admin))


@router.post("/logout", response_model=LogoutResponse)
async def logout_admin(
    request: Request,
    response: Response,
    authorization: Optional[str] = Header(None),
) -> LogoutResponse:
    """登出：撤銷當前 token 並清除 cookie。"""
    token: Optional[str] = None

    # 1) Authorization header (Bearer)
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()

    # 2) Cookie fallback
    if not token:
        token = request.cookies.get(ADMIN_TOKEN_COOKIE_NAME)

    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")

    session = await get_active_session(token)
    if session:
        await session.delete()
    # 清除 auth cache，避免已撤銷 token 在 cache TTL 內仍可使用
    await invalidate_admin_auth_cache_by_token(request, token)

    clear_auth_cookie(response)
    return LogoutResponse(logged_out=True, session_revoked=bool(session))


@router.get("/me", response_model=AdminPublic)
async def get_me(current_admin: AdminAccount = Depends(require_admin_account)) -> AdminPublic:
    return _to_public_admin(current_admin)


@router.patch("/me", response_model=AdminPublic)
async def update_me(
    payload: AdminUpdateMeRequest,
    current_admin: AdminAccount = Depends(require_admin_account),
) -> AdminPublic:
    """更新當前管理員的名稱/帳號（username）。"""
    new_username = payload.username.strip()

    if new_username == current_admin.username:
        return _to_public_admin(current_admin)

    existing = await AdminAccount.find_one(AdminAccount.username == new_username)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="username already exists")

    current_admin.username = new_username
    current_admin.updated_at = datetime.now()

    try:
        await current_admin.save()
    except Exception:
        # 避免 race condition：同一時間有其他人搶先用掉這個 username
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="username already exists") from None

    return _to_public_admin(current_admin)


@router.post("/invitations", response_model=InvitationResponse)
async def create_invitation(
    payload: InvitationCreateRequest,
    current_admin: AdminAccount = Depends(require_admin_account),
) -> InvitationResponse:
    """為當前管理員產生新的邀請碼（會自動註銷舊的有效邀請碼）。"""
    await _revoke_active_invitations(current_admin.admin_code)

    now = datetime.now()
    code = await _generate_invitation_code()
    expires_at = now + timedelta(hours=min(payload.expires_in_hours, 24 * 7))

    invite = AdminInvitation(
        code=code,
        inviter_code=current_admin.admin_code,
        inviter_username=current_admin.username,
        expires_at=expires_at,
        created_at=now,
        updated_at=now,
    )
    await invite.insert()

    return InvitationResponse(code=code, expires_at=expires_at)


@router.get("", response_model=AdminListResponse)
async def list_admins(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_admin: AdminAccount = Depends(require_admin_account),
) -> AdminListResponse:
    """分頁列出所有管理員，並附帶當前登入者是否可刪除該帳號。"""
    page = max(1, page)
    page_size = max(1, min(page_size, 100))

    total = await AdminAccount.count()
    total_pages = math.ceil(total / page_size) if total else 0
    if total_pages and page > total_pages:
        page = total_pages

    skip = (page - 1) * page_size if total else 0
    docs: List[AdminAccount] = await (
        AdminAccount.find_all()
        .sort([("created_at", -1)])
        .skip(skip)
        .limit(page_size)
        .to_list()
    )

    items = [
        AdminListItem(
            admin_code=doc.admin_code,
            username=doc.username,
            invited_by_code=doc.invited_by_code,
            created_at=doc.created_at,
            can_delete=_can_delete(current_admin, doc),
        )
        for doc in docs
    ]

    return AdminListResponse(
        total=total,
        page=page if total else 1,
        page_size=page_size,
        total_pages=total_pages,
        items=items,
    )


@router.delete("/{admin_code}", response_model=DeleteAdminResponse)
async def delete_admin(
    request: Request,
    admin_code: str,
    current_admin: AdminAccount = Depends(require_admin_account),
) -> DeleteAdminResponse:
    target: Optional[AdminAccount] = await AdminAccount.find_one(AdminAccount.admin_code == admin_code)
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="admin not found")

    if not _can_delete(current_admin, target):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="no permission to delete this admin")

    await AdminSession.find(AdminSession.admin_code == target.admin_code).delete()
    # 清除 auth cache，避免已撤銷 token 在 cache TTL 內仍可使用
    await invalidate_admin_auth_cache_by_admin_code(request, target.admin_code)
    await AdminInvitation.find(AdminInvitation.inviter_code == target.admin_code).delete()
    await target.delete()

    return DeleteAdminResponse(admin_code=admin_code, deleted=True)