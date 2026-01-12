from datetime import datetime
from typing import List, Optional

from beanie import Document
from pydantic import Field
from pymongo import ASCENDING, IndexModel

from ..model_utils import generate_code


class AdminAccount(Document):
    """系統管理員帳號。"""

    admin_code: str = Field(default_factory=generate_code, description="管理員唯一識別碼（UUID 字串）。")
    username: str = Field(..., description="登入用帳號（唯一）。")
    password_hash: str = Field(..., description="密碼雜湊（hash）。")
    password_salt: str = Field(..., description="密碼加鹽（salt），與 password_hash 搭配使用。")
    inviter_chain: List[str] = Field(
        default_factory=list,
        description="邀請鏈（由誰邀請而來的 admin_code 串列），用於追溯邀請關係。",
    )
    invited_by_code: Optional[str] = Field(None, description="直接邀請者的 admin_code，無時為 None。")
    created_at: datetime = Field(default_factory=datetime.now, description="建立時間（server local time）。")
    updated_at: datetime = Field(default_factory=datetime.now, description="最後更新時間（server local time）。")

    class Settings:
        name = "admin_account"
        collection = "admin_account"
        indexes = [
            IndexModel([("admin_code", ASCENDING)], unique=True),
            IndexModel([("username", ASCENDING)], unique=True),
            IndexModel([("created_at", ASCENDING)]),
        ]


class AdminInvitation(Document):
    """邀請碼，可讓被邀請者註冊成為管理員。"""

    code: str = Field(..., description="邀請碼字串（唯一）。")
    inviter_code: str = Field(..., description="邀請者的 admin_code。")
    inviter_username: str = Field(..., description="邀請者的 username（便於查詢/顯示）。")
    expires_at: datetime = Field(..., description="到期時間（Mongo TTL 會在此時間後清理）。")
    used_by_code: Optional[str] = Field(None, description="被邀請者註冊後的 admin_code，未使用時為 None。")
    used_by_username: Optional[str] = Field(None, description="被邀請者註冊後的 username，未使用時為 None。")
    used_at: Optional[datetime] = Field(None, description="邀請碼被使用的時間，未使用時為 None。")
    revoked_at: Optional[datetime] = Field(None, description="邀請碼被撤銷的時間，未撤銷時為 None。")
    created_at: datetime = Field(default_factory=datetime.now, description="建立時間（server local time）。")
    updated_at: datetime = Field(default_factory=datetime.now, description="最後更新時間（server local time）。")

    class Settings:
        name = "admin_invitation"
        collection = "admin_invitation"
        indexes = [
            IndexModel([("code", ASCENDING)], unique=True),
            IndexModel([("inviter_code", ASCENDING)]),
            IndexModel([("expires_at", ASCENDING)], expireAfterSeconds=3600, name="expires_at_ttl"),
        ]

    @property
    def is_active(self) -> bool:
        now = datetime.now()
        return self.revoked_at is None and self.used_at is None and self.expires_at > now


class AdminSession(Document):
    """登入後產生的存續 session token（雜湊儲存）。"""

    admin_code: str = Field(..., description="對應的管理員 admin_code。")
    token_hash: str = Field(..., description="session token 的雜湊值（不儲存明文 token）。")
    expires_at: datetime = Field(..., description="到期時間（Mongo TTL 會在此時間後清理）。")
    last_used_at: datetime = Field(default_factory=datetime.now, description="最後一次使用時間（server local time）。")
    created_at: datetime = Field(default_factory=datetime.now, description="建立時間（server local time）。")
    revoked_at: Optional[datetime] = Field(None, description="撤銷時間，未撤銷時為 None。")

    class Settings:
        name = "admin_session"
        collection = "admin_session"
        indexes = [
            IndexModel([("token_hash", ASCENDING)], unique=True),
            IndexModel([("admin_code", ASCENDING)]),
            IndexModel([("expires_at", ASCENDING)], expireAfterSeconds=3600, name="expires_at_ttl"),
        ]


