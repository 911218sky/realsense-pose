from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

USERNAME_PATTERN = r"^[A-Za-z0-9._-]{3,64}$"  # 帳號格式限制


class AdminPublic(BaseModel):
    admin_code: str            # 管理員唯一代碼
    username: str              # 帳號
    invited_by_code: Optional[str] = None  # 誰邀請的（第一位為 None）
    created_at: datetime       # 建立時間


class RegisterRequest(BaseModel):
    username: str = Field(
        ...,
        min_length=3,
        max_length=64,
        pattern=USERNAME_PATTERN,
        description="帳號（限英數 . _ -，3-64 字）",
    )
    password: str = Field(..., min_length=8, max_length=128, description="密碼")
    invite_code: Optional[str] = Field(
        None, max_length=128, description="邀請碼（第一位管理員可不填）"
    )


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=8, max_length=128)


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=8, max_length=128, description="舊密碼")
    new_password: str = Field(..., min_length=8, max_length=128, description="新密碼")


class AdminUpdateMeRequest(BaseModel):
    """更新當前登入的管理員資訊：PATCH /v1/admins/me"""
    username: str = Field(
        ...,
        min_length=3,
        max_length=64,
        pattern=USERNAME_PATTERN,
        description="新的登入帳號/名稱（限英數 . _ -，3-64 字）",
    )

class AuthTokenResponse(BaseModel):
    token: str            # Bearer token（明文回給前端）
    expires_at: datetime  # token 過期時間
    admin: AdminPublic    # 登入的管理員資訊


class InvitationCreateRequest(BaseModel):
    expires_in_hours: int = Field(
        24,
        ge=1,
        le=24 * 7,
        description="邀請碼有效時間（小時），上限 7 天。",
    )


class InvitationResponse(BaseModel):
    code: str          # 邀請碼
    expires_at: datetime


class DeleteAdminResponse(BaseModel):
    admin_code: str  # 被刪除的管理員代碼
    deleted: bool


class LogoutResponse(BaseModel):
    logged_out: bool
    session_revoked: bool


class AdminListItem(AdminPublic):
    can_delete: bool  # 當前登入者是否能刪除此人


class AdminListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    items: list[AdminListItem]  # 分頁結果

