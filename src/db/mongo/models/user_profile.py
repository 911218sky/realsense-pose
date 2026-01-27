from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from beanie import Document
from pydantic import BaseModel, Field, model_validator
from pymongo import ASCENDING, IndexModel

from ..model_utils import generate_code


class DiagnosisInfo(BaseModel):
    """診斷資訊，可依需求再擴充。"""

    diagnosis: Optional[str] = Field(None, description="診斷（文字）。")
    body_part: Optional[str] = Field(None, description="部位（文字）。")
    disease: Optional[str] = Field(None, description="疾病/病名（文字）。")
    diagnosis_type: Optional[str] = Field(None, description="診斷類型（文字）。")
    affected_side: Optional[str] = Field(None, description="患側，例如 left/right/bilateral。")
    onset_date: Optional[date] = Field(None, description="發病日期。")
    is_recurrent: Optional[bool] = Field(None, description="是否復發。")
    has_aphasia: Optional[bool] = Field(None, description="是否有失語症。")


class SurgeryInfo(BaseModel):
    had_surgery: Optional[bool] = Field(None, description="是否有開刀史。")
    surgery_date: Optional[date] = Field(None, description="開刀日期，未知可為 None。")
    surgery_type: Optional[str] = Field(None, description="開刀類型（文字）。")


class RehabTreatmentInfo(BaseModel):
    pt: Optional[bool] = Field(None, description="是否接受物理治療（PT）。")
    ot: Optional[bool] = Field(None, description="是否接受職能治療（OT）。")
    st: Optional[bool] = Field(None, description="是否接受語言治療（ST）。")
    self_pay_items: Optional[str] = Field(None, description="自費項目（文字）。")
    other_items: Optional[str] = Field(None, description="其它治療/項目（文字）。")


class SymptomInfo(BaseModel):
    symptoms: Optional[List[str]] = Field(None, description="目前困擾的症狀（字串陣列）。")
    pain_location: Optional[str] = Field(None, description="疼痛部位（文字）。")
    pain_side: Optional[str] = Field(None, description="疼痛側別，例如 left/right/bilateral。")
    pain_score: Optional[int] = Field(None, ge=0, le=10, description="疼痛分數（0~10）。")
    fall_count: Optional[int] = Field(None, ge=0, description="跌倒次數，期間依問卷定義。")
    last_fall_date: Optional[date] = Field(None, description="最近一次跌倒日期。")


class LifestyleInfo(BaseModel):
    regular_health_check: Optional[bool] = Field(None, description="是否定期健康檢查。")
    regular_dental_check: Optional[bool] = Field(None, description="是否定期牙科檢查。")
    smoking: Optional[bool] = Field(None, description="是否抽菸。")
    drinking: Optional[bool] = Field(None, description="是否喝酒。")
    drinking_frequency: Optional[str] = Field(None, description="飲酒頻率（文字）。")
    drinking_amount: Optional[str] = Field(None, description="飲酒量/程度（文字）。")
    exercise_habit: Optional[str] = Field(None, description="運動習慣（簡述文字）。")
    exercise_types: Optional[List[str]] = Field(None, description="運動類型（字串陣列）。")
    vigorous_10min: Optional[bool] = Field(None, description="是否曾有費力運動 >=10 分鐘。")
    vigorous_60min_per_week: Optional[bool] = Field(None, description="每週費力運動累積是否 >=60 分鐘。")
    moderate_10min: Optional[bool] = Field(None, description="是否曾有中等費力運動 >=10 分鐘。")
    moderate_days_per_week: Optional[int] = Field(None, ge=0, le=7, description="每週中等費力運動天數（0~7）。")
    moderate_minutes_per_day: Optional[int] = Field(None, ge=0, description="每天中等費力運動分鐘數。")


class MedicalHistoryInfo(BaseModel):
    relevant_exams: Optional[str] = Field(None, description="相關醫學檢查（文字）。")
    exam_notes: Optional[str] = Field(None, description="承上題備註（文字）。")
    other_diseases: Optional[str] = Field(None, description="其它疾病史（文字）。")
    surgery: Optional[SurgeryInfo] = Field(None, description="手術史（結構化欄位）。")
    rehab_treatment: Optional[RehabTreatmentInfo] = Field(None, description="復健治療史（結構化欄位）。")
    medications: Optional[List[str]] = Field(None, description="目前服用藥物（字串陣列）。")
    medication_adherence: Optional[bool] = Field(None, description="是否規律服藥。")
    family_history: Optional[str] = Field(None, description="家族病史（文字）。")


class UserProfile(Document):
    """使用者（個案）基本資料 + 問卷欄位。"""

    user_code: str = Field(default_factory=generate_code, description="使用者唯一識別碼（UUID 字串）。")
    name: str = Field(..., description="姓名或代稱（可用於搜尋/顯示）。")
    assessment_date: Optional[date] = Field(None, description="問卷/收案日期。")

    sex: Optional[str] = Field(None, description="性別（文字；依問卷/系統定義）。")
    age_years: Optional[int] = Field(None, ge=0, le=130, description="年齡（歲）。")
    height_cm: Optional[float] = Field(None, gt=0, le=250, description="身高（cm）。")
    weight_kg: Optional[float] = Field(None, gt=0, le=500, description="體重（kg）。")
    bmi: Optional[float] = Field(None, gt=0, le=100, description="BMI；可由身高/體重自動推算。")
    education_level: Optional[str] = Field(None, description="教育程度（文字）。")

    cohort: List[str] = Field(default_factory=lambda: ["正常人"], description="族群分類列表，一個人可屬於多個族群，預設為 ['正常人']。")

    diagnosis: Optional[DiagnosisInfo] = Field(None, description="診斷資訊（結構化欄位）。")
    medical_history: Optional[MedicalHistoryInfo] = Field(None, description="病史資訊（結構化欄位）。")
    symptoms: Optional[SymptomInfo] = Field(None, description="症狀資訊（結構化欄位）。")
    lifestyle: Optional[LifestyleInfo] = Field(None, description="生活習慣資訊（結構化欄位）。")

    notes: Optional[str] = Field(None, description="備註（自由文字）。")

    created_at: datetime = Field(default_factory=datetime.now, description="建立時間（server local time）。")
    updated_at: datetime = Field(default_factory=datetime.now, description="最後更新時間（server local time）。")

    @model_validator(mode="after")
    def _auto_bmi(self) -> "UserProfile":
        if self.bmi is None and self.height_cm and self.weight_kg:
            h_m = self.height_cm / 100.0
            if h_m > 0:
                self.bmi = round(self.weight_kg / (h_m * h_m), 2)
        return self

    class Settings:
        name = "user_profile"
        collection = "user_profile"
        indexes = [
            IndexModel([("user_code", ASCENDING)], unique=True),
            IndexModel([("name", ASCENDING)], unique=True, name="uq_name"),
            IndexModel([("created_at", ASCENDING)]),
            # Multikey index for cohort array - optimizes queries like {"cohort": "stroke"}
            IndexModel([("cohort", ASCENDING)], name="idx_cohort"),
        ]


