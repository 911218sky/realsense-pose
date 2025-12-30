from datetime import date, datetime
from typing import List, Literal, Optional

#  BaseModel: schema；Field: 驗證/限制；model_validator: 跨欄位檢查
from pydantic import BaseModel, Field, model_validator
from db import DiagnosisInfo, LifestyleInfo, MedicalHistoryInfo, SymptomInfo

# ---------- Request models ----------


class UserCreateRequest(BaseModel):
    """建立使用者（個案）時的請求 body：POST /v1/users"""

    # 可選：個案識別碼（不指定則 DB 會自動產生 UUID 字串）
    user_code: Optional[str] = Field(None, max_length=128)

    # 姓名（必填）
    name: str = Field(..., min_length=1, max_length=128)
    # 問卷/收案日期（可不填）
    assessment_date: Optional[date] = None

    # 性別（可不填；自由字串，例如 "M"/"F"/"男"/"女"）
    sex: Optional[str] = Field(None, max_length=32)
    # 年齡（歲）
    age_years: Optional[int] = Field(None, ge=0, le=130)
    # 身高（cm）
    height_cm: Optional[float] = Field(None, gt=0, le=250)
    # 體重（kg）
    weight_kg: Optional[float] = Field(None, gt=0, le=500)
    # BMI（若不填，DB 端會在建立/更新時嘗試用身高/體重自動推算）
    bmi: Optional[float] = Field(None, gt=0, le=100)
    # 教育程度（自由字串）
    education_level: Optional[str] = Field(None, max_length=128)

    # 診斷資訊（精簡版）
    diagnosis: Optional[DiagnosisInfo] = None
    # 醫療史/用藥/復健治療等（精簡版）
    medical_history: Optional[MedicalHistoryInfo] = None
    # 目前症狀/疼痛/跌倒等（精簡版）
    symptoms: Optional[SymptomInfo] = None
    # 生活習慣（抽菸/喝酒/運動等）（精簡版）
    lifestyle: Optional[LifestyleInfo] = None

    # 其它備註（自由文字）
    notes: Optional[str] = None


class UserUpdateRequest(BaseModel):
    """更新使用者資料的請求 body：PATCH /v1/users/{user_code}

    - 全部欄位都是 Optional：只更新你有提供的欄位（partial update）
    """

    # 姓名（若提供就更新）
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    # 問卷/收案日期（若提供就更新）
    assessment_date: Optional[date] = None

    # 性別
    sex: Optional[str] = Field(None, max_length=32)
    # 年齡（歲）
    age_years: Optional[int] = Field(None, ge=0, le=130)
    # 身高（cm）
    height_cm: Optional[float] = Field(None, gt=0, le=250)
    # 體重（kg）
    weight_kg: Optional[float] = Field(None, gt=0, le=500)
    # BMI（可直接指定；或讓 DB 端自動推算）
    bmi: Optional[float] = Field(None, gt=0, le=100)
    # 教育程度
    education_level: Optional[str] = Field(None, max_length=128)

    # 診斷資訊（若只想更新其中某些欄位，API 端會做 merge，不會整坨覆蓋）
    diagnosis: Optional[DiagnosisInfo] = None
    # 醫療史（merge 更新）
    medical_history: Optional[MedicalHistoryInfo] = None
    # 症狀（merge 更新）
    symptoms: Optional[SymptomInfo] = None
    # 生活習慣（merge 更新）
    lifestyle: Optional[LifestyleInfo] = None

    # 備註
    notes: Optional[str] = None


class UserItem(BaseModel):
    """使用者資料的回傳格式（單一使用者，不含 sessions 列表）。"""

    # 個案識別碼（用來關聯 bag/session）
    user_code: str
    # 姓名
    name: str
    # 問卷/收案日期
    assessment_date: Optional[date] = None

    # 性別
    sex: Optional[str] = None
    # 年齡（歲）
    age_years: Optional[int] = None
    # 身高（cm）
    height_cm: Optional[float] = None
    # 體重（kg）
    weight_kg: Optional[float] = None
    # BMI
    bmi: Optional[float] = None
    # 教育程度
    education_level: Optional[str] = None

    # 診斷資訊
    diagnosis: Optional[DiagnosisInfo] = None
    # 醫療史
    medical_history: Optional[MedicalHistoryInfo] = None
    # 症狀
    symptoms: Optional[SymptomInfo] = None
    # 生活習慣
    lifestyle: Optional[LifestyleInfo] = None

    # 備註
    notes: Optional[str] = None

    # 建立時間（DB 寫入）
    created_at: datetime
    # 更新時間（DB 寫入）
    updated_at: datetime


class UserSessionItem(BaseModel):
    """某個使用者關聯到的 session(bag) 紀錄（精簡欄位）。"""

    # session 名稱（目前系統的唯一識別/顯示名稱）
    session_name: str
    # 此 session 對應的 user_code（可能為 None 表示尚未綁定）
    user_code: Optional[str] = None
    # 產出的 npy 檔路徑（字串）
    npy_path: str
    # bag 檔路徑（字串）
    bag_path: str
    # bag 檔案名稱（例如：1_1_607.bag）
    bag_filename: str
    # bag 內容 hash（用於去重/比對）
    bag_hash: Optional[str] = None
    # 影片檔路徑（可選，若有產出影片）
    video_path: Optional[str] = None
    # 建立時間
    created_at: datetime
    # 更新時間
    updated_at: datetime

class DeleteUserResponse(BaseModel):
    """刪除使用者回傳：DELETE /v1/users/{user_code}"""

    user_code: str
    deleted_user: bool
    unlinked_sessions: int
    deleted_sessions: int


class UserDetailResponse(BaseModel):
    """取得使用者詳細資訊的回傳：GET /v1/users/{user_code}

    - user: 使用者基本資料
    - sessions: 該使用者目前綁定的所有 session(bag) 列表
    """

    user: UserItem
    sessions: List[UserSessionItem]


class UserListItem(BaseModel):
    """使用者列表的單筆資料（比 UserItem 更精簡，適合列表/表格）。"""

    # 個案識別碼（用來後續取得詳細資料 / 綁定 session）
    user_code: str
    # 顯示用姓名
    name: str
    # 建立時間（DB 寫入）
    created_at: datetime
    # 更新時間（DB 寫入）
    updated_at: datetime


class UserListResponse(BaseModel):
    """使用者列表回傳：GET /v1/users（支援簡單分頁）。"""

    total: int
    page: int
    page_size: int
    total_pages: int
    items: List[UserListItem]

class UserSearchSuggestionItem(BaseModel):
    """使用者搜尋建議（精簡資訊）。"""

    # 個案識別碼（常用來做後續查詢/綁定；看起來像「hash/uuid」）
    user_code: str
    # 顯示用姓名
    name: str
    # 建立時間（用來在同名時做辨識/排序）
    created_at: datetime


class UserSearchSuggestionResponse(BaseModel):
    """使用者搜尋建議回傳：GET /v1/users/search（支援分頁、精簡 user 資訊）。"""

    total: int
    page: int
    page_size: int
    total_pages: int
    items: List[UserSearchSuggestionItem]


class LinkSessionRequest(BaseModel):
    """把「某個 session(bag)」綁到使用者的請求 body：POST /v1/users/{user_code}/sessions/link

    你可以用：
    - session_name 來指定要綁哪一筆 session
    - 或 bag_filename 來指定（推薦，最直覺）
    """

    # 以 session_name 指定要綁定的 session
    session_name: Optional[str] = Field(None, max_length=256)
    # 以 bag_filename 指定要綁定的 session（推薦）
    bag_filename: Optional[str] = Field(None, max_length=256)

    @model_validator(mode="after")
    def _ensure_target(self) -> "LinkSessionRequest":
        # 驗證：至少要提供其中之一
        if not self.session_name and not self.bag_filename:
            raise ValueError("Either session_name or bag_filename is required")
        return self


class UnlinkSessionRequest(BaseModel):
    """把「某個 session(bag)」從使用者解除綁定的請求 body：POST /v1/users/{user_code}/sessions/unlink

    你可以用：
    - session_name 來指定要解除哪一筆 session
    - 或 bag_filename 來指定（推薦）
    - 或 unlink_all=true 一次解除該使用者所有 sessions（此時不可同時帶其他參數）
    """

    unlink_all: bool = Field(False, description="若為 True，一次解除該使用者所有 sessions(bag) 綁定")
    session_name: Optional[str] = Field(None, max_length=256)
    bag_filename: Optional[str] = Field(None, max_length=256)

    @model_validator(mode="after")
    def _ensure_target(self) -> "UnlinkSessionRequest":
        if self.unlink_all:
            if self.session_name or self.bag_filename:
                raise ValueError("unlink_all cannot be used together with session_name/bag_filename")
            return self

        if not self.session_name and not self.bag_filename:
            raise ValueError("Either session_name or bag_filename is required (or set unlink_all=true)")
        return self


# ---------- Response models ----------


class UnlinkSessionResponse(BaseModel):
    """解除使用者與 session(bag) 的綁定回傳：POST /v1/users/{user_code}/sessions/unlink

    - mode=single：解除單一 session，會帶 session 欄位
    - mode=all：解除全部，會帶 unlinked_sessions 數量
    """

    user_code: str
    mode: Literal["single", "all"]
    unlinked_sessions: int
    session: Optional[UserSessionItem] = None


class FindUserByBagRequest(BaseModel):
    """透過 BAG 檔案尋找使用者的請求 body：POST /v1/users/find-by-bag"""

    bag_filename: str = Field(..., min_length=1, max_length=256, description="BAG 檔案名稱（例如：1_1_607.bag）")


class FindUserByBagResponse(BaseModel):
    """透過 BAG 檔案尋找使用者的回傳：POST /v1/users/find-by-bag"""

    found: bool = Field(..., description="是否找到使用者")
    user: Optional[UserItem] = Field(None, description="找到的使用者資料（若有）")
    sessions: List[UserSessionItem] = Field(default_factory=list, description="該使用者的所有 session 列表（found=True 時）或使用該 BAG 檔案的 session 列表（found=False 時）")
    total_sessions: int = Field(0, description="該使用者的 session 總數（found=True 時）或使用該 BAG 檔案的 session 總數（found=False 時）")