"""
Session 資料收集模組。

提供族群使用者查詢和 session 資料收集功能。
"""
from typing import List, Tuple

from db.mongo.models import UserProfile, RealsensePoseExtractor


async def get_cohort_users(
    cohort_names: List[str],
    intersection: bool = False,
) -> List[UserProfile]:
    """查詢族群使用者。

    根據族群名稱列表查詢符合條件的使用者。支援兩種查詢模式：
    - 聯集模式（預設）：使用者只要屬於任一指定族群即符合
    - 交集模式：使用者必須同時屬於所有指定族群才符合

    使用情境：
    - 聯集：「查詢所有老年人或糖尿病患者」
    - 交集：「查詢同時是老年人且有糖尿病的患者」

    Args:
        cohort_names: 族群名稱列表，例如 ["elderly", "diabetes"]
        intersection:
            - True: 取交集（使用者必須屬於所有指定族群）
            - False: 取聯集（使用者屬於任一指定族群即可）

    Returns:
        符合條件的 UserProfile 文件列表

    Note:
        UserProfile.cohort 欄位為陣列型別，一個使用者可屬於多個族群
    """
    if not cohort_names:
        return []

    if intersection:
        query = {"cohort": {"$all": cohort_names}}
    else:
        query = {"cohort": {"$in": cohort_names}}

    users = await UserProfile.find(query).to_list()
    return users


async def get_user_sessions(user_code: str) -> List[RealsensePoseExtractor]:
    """查詢使用者的所有 session。

    根據使用者代碼查詢該使用者的所有復健 session 紀錄。
    每個 session 代表一次復健訓練的姿態擷取資料。

    Args:
        user_code: 使用者代碼，例如 "U001"

    Returns:
        該使用者的所有 RealsensePoseExtractor session 紀錄列表

    Note:
        回傳的 session 未排序，若需要最新的 session 請另行排序
    """
    sessions = await RealsensePoseExtractor.find(
        RealsensePoseExtractor.user_code == user_code
    ).to_list()
    return sessions


async def collect_cohort_sessions(
    user_codes: List[str],
) -> List[Tuple[str, RealsensePoseExtractor]]:
    """彙整族群所有使用者的 session。

    遍歷族群內所有使用者，收集他們的全部 session 資料。
    回傳的元組包含使用者代碼，方便後續追蹤資料來源。

    此方法是基準值計算的資料收集階段，將分散在各使用者的
    session 資料彙整成單一列表，供後續統計分析使用。

    Args:
        user_codes: 使用者代碼列表，例如 ["U001", "U002", "U003"]

    Returns:
        (user_code, session) 元組列表，每個元組包含：
            - user_code: 該 session 所屬的使用者代碼
            - session: RealsensePoseExtractor session 文件

    Note:
        此方法會對每個使用者發起一次資料庫查詢，
        若使用者數量龐大，可考慮改用批次查詢優化效能
    """
    results: List[Tuple[str, RealsensePoseExtractor]] = []

    for user_code in user_codes:
        sessions = await get_user_sessions(user_code)
        for session in sessions:
            results.append((user_code, session))

    return results
