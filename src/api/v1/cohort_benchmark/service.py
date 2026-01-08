from datetime import datetime
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple

import numpy as np

from logger import setup_logger
from rehab_analyzer.entities import (
    DetectLapsResult,
    GaitSummary,
    Lap,
)
from rehab_analyzer.session_analyzer import RehabilitationSessionAnalyzer

from db.mongo.models import (
    CohortBenchmark,
    GaitBenchmarkEmbed,
    LapTimeBenchmarkEmbed,
    PercentileStatsEmbed,
    RealsensePoseExtractor,
    SpeedDistanceBenchmarkEmbed,
    TurnBenchmarkEmbed,
    UserProfile,
)

from .models import (
    ComparisonResult,
    GaitComparison,
    LapTimeComparison,
    MetricComparison,
    SpeedDistanceComparison,
    TurnComparison,
    PercentileDiff,
)

logger = setup_logger("api.v1.cohort_benchmark.service")

class CohortBenchmarkService:
    """族群基準分析服務。
    主要功能：
    1. 族群使用者管理 - 查詢特定族群的使用者列表
    2. Session 資料收集 - 彙整族群內所有使用者的復健 session
    3. 基準值計算 - 計算各項指標的百分位數統計（P10, P25, P50, P75, P90）
    4. 個人比對 - 將個人數據與族群基準進行比較，判斷是否在正常範圍內
    
    設計考量：
    - 使用 async/await 支援非同步資料庫操作
    - 計算密集型操作（如百分位數計算）使用 NumPy 優化效能
    - 錯誤處理採用 try-except 包裝，避免單一 session 失敗影響整體計算
    
    Attributes:
        DEFAULT_PERCENTILES: 預設計算的百分位數列表 [10, 25, 50, 75, 90]
    """

    # 預設百分位數：P10（低於90%人）、P25（第一四分位）、P50（中位數）、
    # P75（第三四分位）、P90（高於90%人）
    DEFAULT_PERCENTILES = [10, 25, 50, 75, 90]

    def compute_percentiles(
        self,
        values: np.ndarray,
        percentiles: Optional[List[int]] = None,
    ) -> PercentileStatsEmbed:
        """計算百分位數統計。
        
        此方法是基準值計算的核心，將一組數值轉換為百分位數統計資料。
        百分位數可用於了解數值在整體分布中的相對位置。
        
        計算流程：
        1. 將輸入轉換為 NumPy 陣列
        2. 過濾掉無效值（NaN、Inf）
        3. 使用 np.percentile 計算各百分位數
        4. 同時計算平均值和標準差作為輔助統計量

        Args:
            values: 數值陣列，可以是 list 或 np.ndarray
            percentiles: 要計算的百分位數列表，預設為 [10, 25, 50, 75, 90]

        Returns:
            PercentileStatsEmbed: 包含以下欄位的嵌入文件
                - p10, p25, p50, p75, p90: 各百分位數值
                - mean: 平均值
                - std: 標準差
                - count: 有效樣本數
                
        Note:
            若輸入為空或全為無效值，回傳全零的統計結果，count=0
        """
        # 使用預設百分位數列表（若未指定）
        if percentiles is None:
            percentiles = self.DEFAULT_PERCENTILES

        # 確保輸入為 float 型別的 NumPy 陣列
        values = np.asarray(values, dtype=float)
        
        # 過濾無效值：移除 NaN（非數字）和 Inf（無限大）
        valid = values[np.isfinite(values)]

        # 處理空陣列情況：回傳全零統計結果
        if valid.size == 0:
            return PercentileStatsEmbed(
                p10=0.0, p25=0.0, p50=0.0, p75=0.0, p90=0.0,
                mean=0.0, std=0.0, count=0
            )

        # 計算百分位數：np.percentile 回傳與 percentiles 列表對應的數值
        pcts = np.percentile(valid, percentiles)
        
        # 建立並回傳統計結果
        return PercentileStatsEmbed(
            p10=float(pcts[0]),   # 第 10 百分位數
            p25=float(pcts[1]),   # 第 25 百分位數（第一四分位）
            p50=float(pcts[2]),   # 第 50 百分位數（中位數）
            p75=float(pcts[3]),   # 第 75 百分位數（第三四分位）
            p90=float(pcts[4]),   # 第 90 百分位數
            mean=float(np.mean(valid)),  # 算術平均值
            std=float(np.std(valid)),    # 標準差（母體標準差）
            count=int(valid.size),       # 有效樣本數
        )

    # ========================================================================
    # 使用者與 Session 查詢方法
    # ========================================================================

    async def get_cohort_users(
        self,
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
        # 空列表直接回傳空結果
        if not cohort_names:
            return []

        if intersection:
            # 交集查詢：使用 MongoDB $all 運算子
            # $all 要求陣列欄位必須包含所有指定元素
            query = {"cohort": {"$all": cohort_names}}
        else:
            # 聯集查詢：使用 MongoDB $in 運算子
            # $in 要求陣列欄位包含任一指定元素即可
            query = {"cohort": {"$in": cohort_names}}

        # 執行查詢並轉換為列表
        users = await UserProfile.find(query).to_list()
        return users

    async def get_user_sessions(
        self,
        user_code: str,
    ) -> List[RealsensePoseExtractor]:
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
        # 使用 Beanie ODM 的查詢語法
        sessions = await RealsensePoseExtractor.find(
            RealsensePoseExtractor.user_code == user_code
        ).to_list()
        return sessions

    async def collect_cohort_sessions(
        self,
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

        # 逐一查詢每個使用者的 session
        for user_code in user_codes:
            sessions = await self.get_user_sessions(user_code)
            # 將每個 session 與其所屬使用者配對
            for session in sessions:
                results.append((user_code, session))

        return results

    # ========================================================================
    # 輔助方法
    # ========================================================================

    def _resolve_npy_path(self, session: RealsensePoseExtractor) -> Optional[str]:
        """解析 session 的 npy 檔案路徑。
        
        將 session 紀錄中儲存的 npy 路徑轉換為實際可存取的檔案路徑。
        處理以下情況：
        1. 路徑為空或 None
        2. Windows 風格路徑（反斜線）轉換
        3. 相對路徑轉換為絕對路徑
        4. 檔案存在性檢查
        
        npy 檔案包含 session 的姿態資料（NumPy 陣列格式），
        是後續分析的必要輸入。

        Args:
            session: RealsensePoseExtractor session 紀錄

        Returns:
            - str: 有效的 npy 檔案絕對路徑
            - None: 若路徑無效或檔案不存在
        """
        # 取得原始路徑，處理 None 情況
        raw = session.npy_path or ""
        if not raw:
            return None

        # 處理 Windows 路徑：將反斜線轉換為正斜線
        # 這確保跨平台相容性
        if "\\" in raw:
            raw = raw.replace("\\", "/")

        # 建立 Path 物件進行路徑處理
        candidate = Path(raw)
        
        # 若為相對路徑，以當前工作目錄為基準轉換為絕對路徑
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate

        # 檢查檔案是否存在
        if candidate.exists():
            return str(candidate)

        # 檔案不存在，回傳 None
        return None

    def _analyze_session(
        self,
        npy_path: str,
    ) -> Tuple[Optional[DetectLapsResult], Optional[GaitSummary]]:
        """分析單一 session。
        
        使用 RehabilitationSessionAnalyzer 對 session 進行完整分析，
        包含圈數偵測和步態分析兩個主要步驟。
        
        分析流程：
        1. 建立分析器實例，載入 npy 檔案
        2. 執行自動圈數偵測（detect_laps_auto）
        3. 計算步態摘要（compute_gait_summary）
        
        此方法使用 try-except 包裝，確保單一 session 分析失敗
        不會影響整體基準值計算流程。

        Args:
            npy_path: npy 檔案的絕對路徑

        Returns:
            元組 (DetectLapsResult, GaitSummary)：
                - DetectLapsResult: 圈數偵測結果，包含各圈的詳細資料
                - GaitSummary: 步態分析摘要，包含步頻、步長等指標
            若分析失敗則回傳 (None, None)
            
        Note:
            分析失敗時會記錄警告日誌，但不會拋出例外
        """
        try:
            # 建立分析器實例，自動載入 npy 檔案中的姿態資料
            analyzer = RehabilitationSessionAnalyzer(npy_path=npy_path)
            
            # 執行自動圈數偵測
            # detect_laps_auto 會自動判斷起點/終點並切分各圈
            det = analyzer.detect_laps_auto()
            
            # 計算步態摘要
            # 包含步頻(SPM)、步長、擺動期/站立期比例等
            gait = analyzer.compute_gait_summary()
            
            return det, gait
        except Exception as e:
            # 記錄警告但不中斷流程，讓其他 session 可以繼續分析
            logger.warning(f"Failed to analyze session {npy_path}: {e}")
            return None, None

    # ========================================================================
    # 基準值計算方法（各類指標）
    # ========================================================================

    def _compute_lap_time_benchmark(
        self,
        all_laps: List[Lap],
    ) -> LapTimeBenchmarkEmbed:
        """計算圈數時間基準。
        
        將所有圈的時間資料彙整，計算各時間階段的百分位數統計。
        TUG（Timed Up and Go）測試的各階段時間是評估行動能力的重要指標。
        
        時間階段說明：
        - dur_total: 總時間（從起身到坐下完成）
        - dur_stand: 起身時間（從椅子站起）
        - dur_to_cone: 去程時間（走向標誌錐）
        - dur_cone_turn: 錐處轉向時間（在標誌錐處轉身）
        - dur_return: 回程時間（走回椅子）
        - dur_turn_to_sit: 轉身準備坐下時間
        - dur_sit: 坐下時間

        Args:
            all_laps: 所有圈的 Lap 資料列表

        Returns:
            LapTimeBenchmarkEmbed: 包含各時間階段百分位數統計的嵌入文件
            
        Note:
            若 all_laps 為空，回傳全零統計結果
        """
        # 處理空資料情況
        if not all_laps:
            empty = self.compute_percentiles(np.array([]))
            return LapTimeBenchmarkEmbed(
                dur_total=empty, dur_stand=empty, dur_to_cone=empty,
                dur_cone_turn=empty, dur_return=empty, dur_turn_to_sit=empty, dur_sit=empty
            )

        # 對每個時間階段分別計算百分位數統計
        return LapTimeBenchmarkEmbed(
            # 總時間統計
            dur_total=self.compute_percentiles(np.array([lap.dur_total for lap in all_laps])),
            # 起身時間統計
            dur_stand=self.compute_percentiles(np.array([lap.dur_stand for lap in all_laps])),
            # 去程時間統計
            dur_to_cone=self.compute_percentiles(np.array([lap.dur_to_cone for lap in all_laps])),
            # 錐處轉向時間統計
            dur_cone_turn=self.compute_percentiles(np.array([lap.dur_cone_turn for lap in all_laps])),
            # 回程時間統計
            dur_return=self.compute_percentiles(np.array([lap.dur_return for lap in all_laps])),
            # 轉身準備坐下時間統計
            dur_turn_to_sit=self.compute_percentiles(np.array([lap.dur_turn_to_sit for lap in all_laps])),
            # 坐下時間統計
            dur_sit=self.compute_percentiles(np.array([lap.dur_sit for lap in all_laps])),
        )

    def _compute_gait_benchmark(
        self,
        all_gaits: List[GaitSummary],
    ) -> GaitBenchmarkEmbed:
        """計算步態基準。
        
        將所有 session 的步態分析結果彙整，計算各步態指標的百分位數統計。
        步態指標是評估行走品質和對稱性的重要依據。
        
        步態指標說明：
        - spm: 步頻（Steps Per Minute），每分鐘步數
        - mean_step_len: 平均步長（公尺）
        - l_swing_pct: 左腳擺動期百分比（擺動期/步態週期）
        - r_swing_pct: 右腳擺動期百分比
        - l_stance_s: 左腳站立期時間（秒）
        - r_stance_s: 右腳站立期時間（秒）
        
        臨床意義：
        - 左右擺動期/站立期差異可反映步態對稱性
        - 步頻和步長可評估行走效率

        Args:
            all_gaits: 所有 session 的 GaitSummary 列表

        Returns:
            GaitBenchmarkEmbed: 包含各步態指標百分位數統計的嵌入文件
        """
        # 處理空資料情況
        if not all_gaits:
            empty = self.compute_percentiles(np.array([]))
            return GaitBenchmarkEmbed(
                spm=empty, mean_step_len=empty,
                l_swing_pct=empty, r_swing_pct=empty,
                l_stance_s=empty, r_stance_s=empty
            )

        # 對每個步態指標分別計算百分位數統計
        return GaitBenchmarkEmbed(
            # 步頻統計（每分鐘步數）
            spm=self.compute_percentiles(np.array([g.spm for g in all_gaits])),
            # 平均步長統計（公尺）
            mean_step_len=self.compute_percentiles(np.array([g.mean_step_len for g in all_gaits])),
            # 左腳擺動期百分比統計
            l_swing_pct=self.compute_percentiles(np.array([g.l_swing_pct_mean for g in all_gaits])),
            # 右腳擺動期百分比統計
            r_swing_pct=self.compute_percentiles(np.array([g.r_swing_pct_mean for g in all_gaits])),
            # 左腳站立期時間統計（秒）
            l_stance_s=self.compute_percentiles(np.array([g.l_stance_s_mean for g in all_gaits])),
            # 右腳站立期時間統計（秒）
            r_stance_s=self.compute_percentiles(np.array([g.r_stance_s_mean for g in all_gaits])),
        )

    def _compute_speed_distance_benchmark(
        self,
        all_laps: List[Lap],
    ) -> SpeedDistanceBenchmarkEmbed:
        """計算速度距離基準。
        
        將所有圈的速度和距離資料彙整，計算百分位數統計。
        速度和距離指標可評估行走效率和路徑規劃能力。
        
        指標說明：
        - speed_mps: 行走速度（公尺/秒），由 距離/時間 計算
        - dist_lap_path_m: 單圈總路徑長度（公尺）
        - dist_outbound_m: 去程距離（公尺）
        - dist_return_m: 回程距離（公尺）
        - dist_cone_turn_m: 錐處轉向路徑長度（公尺）
        
        臨床意義：
        - 行走速度是預測跌倒風險的重要指標
        - 去程/回程距離差異可反映路徑規劃能力

        Args:
            all_laps: 所有圈的 Lap 資料列表

        Returns:
            SpeedDistanceBenchmarkEmbed: 包含速度距離指標百分位數統計的嵌入文件
        """
        # 處理空資料情況
        if not all_laps:
            empty = self.compute_percentiles(np.array([]))
            return SpeedDistanceBenchmarkEmbed(
                speed_mps=empty, dist_lap_path_m=empty,
                dist_outbound_m=empty, dist_return_m=empty, dist_cone_turn_m=empty
            )

        # 計算每圈的行走速度：距離 / 時間
        # 只計算時間大於 0 的圈，避免除以零
        speeds = []
        for lap in all_laps:
            if lap.dur_total > 0:
                # 速度 = 總路徑長度 / 總時間
                speeds.append(lap.dist_lap_path_m / lap.dur_total)

        # 對各指標分別計算百分位數統計
        return SpeedDistanceBenchmarkEmbed(
            # 行走速度統計（公尺/秒）
            speed_mps=self.compute_percentiles(np.array(speeds) if speeds else np.array([])),
            # 單圈總路徑長度統計
            dist_lap_path_m=self.compute_percentiles(np.array([lap.dist_lap_path_m for lap in all_laps])),
            # 去程距離統計
            dist_outbound_m=self.compute_percentiles(np.array([lap.dist_outbound_m for lap in all_laps])),
            # 回程距離統計
            dist_return_m=self.compute_percentiles(np.array([lap.dist_return_m for lap in all_laps])),
            # 錐處轉向路徑長度統計
            dist_cone_turn_m=self.compute_percentiles(np.array([lap.dist_cone_turn_path_m for lap in all_laps])),
        )

    def _compute_turn_benchmark(
        self,
        all_laps: List[Lap],
    ) -> TurnBenchmarkEmbed:
        """計算轉向基準。
        
        將所有圈的轉向資料彙整，計算轉向角度的百分位數統計，
        以及轉向方向的分布比例。
        
        指標說明：
        - delta_theta_cone_deg: 錐處轉向角度（度）
        - delta_theta_chair_deg: 椅子處轉向角度（度）
        - turn_cone_dir_ratio: 錐處轉向方向分布（+1=右轉, -1=左轉, 0=無轉向）
        - turn_chair_dir_ratio: 椅子處轉向方向分布
        
        臨床意義：
        - 轉向角度可評估轉身的流暢度
        - 轉向方向偏好可能反映身體不對稱性

        Args:
            all_laps: 所有圈的 Lap 資料列表

        Returns:
            TurnBenchmarkEmbed: 包含轉向指標百分位數統計和方向分布的嵌入文件
        """
        # 處理空資料情況
        if not all_laps:
            empty = self.compute_percentiles(np.array([]))
            return TurnBenchmarkEmbed(
                delta_theta_cone_deg=empty, delta_theta_chair_deg=empty,
                turn_cone_dir_ratio={}, turn_chair_dir_ratio={}
            )

        # 收集所有圈的轉向方向資料
        cone_dirs = [lap.turn_cone_dir for lap in all_laps]    # 錐處轉向方向
        chair_dirs = [lap.turn_chair_dir for lap in all_laps]  # 椅子處轉向方向

        def compute_dir_ratio(dirs: List[int]) -> Dict[str, float]:
            """計算轉向方向分布比例。
            
            將轉向方向（+1, -1, 0）統計為比例分布。
            
            Args:
                dirs: 轉向方向列表，值為 +1（右轉）、-1（左轉）或 0（無轉向）
                
            Returns:
                方向分布字典，例如 {"+1": 0.6, "-1": 0.4} 表示 60% 右轉、40% 左轉
            """
            if not dirs:
                return {}
            
            total = len(dirs)
            # 統計各方向的次數
            pos = sum(1 for d in dirs if d > 0)   # 右轉次數（+1）
            neg = sum(1 for d in dirs if d < 0)   # 左轉次數（-1）
            zero = sum(1 for d in dirs if d == 0) # 無轉向次數（0）
            
            # 計算比例，只包含有出現的方向
            result = {}
            if pos > 0:
                result["+1"] = pos / total
            if neg > 0:
                result["-1"] = neg / total
            if zero > 0:
                result["0"] = zero / total
            return result

        # 建立轉向基準嵌入文件
        return TurnBenchmarkEmbed(
            # 錐處轉向角度統計
            delta_theta_cone_deg=self.compute_percentiles(
                np.array([lap.delta_theta_cone_deg for lap in all_laps])
            ),
            # 椅子處轉向角度統計
            delta_theta_chair_deg=self.compute_percentiles(
                np.array([lap.delta_theta_chair_deg for lap in all_laps])
            ),
            # 錐處轉向方向分布
            turn_cone_dir_ratio=compute_dir_ratio(cone_dirs),
            # 椅子處轉向方向分布
            turn_chair_dir_ratio=compute_dir_ratio(chair_dirs),
        )

    # ========================================================================
    # 主方法
    # ========================================================================
    async def calculate_benchmark(
        self,
        cohort_name: str,
        force_recalculate: bool = False,
    ) -> CohortBenchmark:
        """計算族群基準值。
        
        這是族群基準分析的主要入口方法，執行完整的基準值計算流程：
        1. 檢查是否已有現有基準值（可選擇強制重新計算）
        2. 查詢族群內所有使用者
        3. 收集所有使用者的 session 資料
        4. 分析每個 session 取得圈數和步態資料
        5. 計算各類指標的百分位數統計
        6. 儲存基準值到資料庫
        
        狀態管理：
        - "calculating": 計算進行中
        - "completed": 計算完成
        - "failed": 計算失敗（會記錄錯誤訊息）

        Args:
            cohort_name: 族群名稱，例如 "elderly_group"
            force_recalculate: 
                - True: 強制重新計算，即使已有基準值
                - False: 若已有基準值則直接回傳

        Returns:
            CohortBenchmark: 計算完成的基準值文件
            
        Raises:
            Exception: 計算過程中發生錯誤時拋出，同時更新狀態為 "failed"
        """
        # 檢查現有基準值
        existing = await CohortBenchmark.find_one(
            CohortBenchmark.cohort_name == cohort_name
        )

        # 若已有基準值且不強制重新計算，直接回傳
        if existing and not force_recalculate:
            return existing

        # 建立或更新基準值文件，設定狀態為「計算中」
        if existing:
            # 更新現有文件狀態
            existing.status = "calculating"
            existing.updated_at = datetime.now()
            await existing.save()
        else:
            # 建立新文件
            existing = CohortBenchmark(
                cohort_name=cohort_name,
                status="calculating",
            )
            await existing.insert()

        try:
            # 查詢族群使用者
            users = await self.get_cohort_users([cohort_name], intersection=False)
            
            # 若族群無使用者，直接完成
            if not users:
                existing.status = "completed"
                existing.user_count = 0
                existing.session_count = 0
                existing.lap_count = 0
                existing.updated_at = datetime.now()
                await existing.save()
                return existing

            # 取得所有使用者代碼
            user_codes = [u.user_code for u in users]

            # 彙整所有 session 並進行分析
            sessions = await self.collect_cohort_sessions(user_codes)

            # 用於收集所有分析結果的列表
            all_laps: List[Lap] = []        # 所有圈的資料
            all_gaits: List[GaitSummary] = []  # 所有步態摘要
            session_count = 0                # 成功分析的 session 數量

            # 逐一分析每個 session
            for user_code, session in sessions:
                # 解析 npy 檔案路徑
                npy_path = self._resolve_npy_path(session)
                if not npy_path:
                    # 找不到 npy 檔案，跳過此 session
                    continue

                # 執行 session 分析
                det, gait = self._analyze_session(npy_path)
                if det is None:
                    # 分析失敗，跳過此 session
                    continue

                # 累計成功分析的資料
                session_count += 1
                all_laps.extend(det.laps)  # 加入所有圈的資料
                if gait:
                    all_gaits.append(gait)  # 加入步態摘要

            # 計算各類基準值
            lap_time = self._compute_lap_time_benchmark(all_laps)
            gait_benchmark = self._compute_gait_benchmark(all_gaits)
            speed_distance = self._compute_speed_distance_benchmark(all_laps)
            turn = self._compute_turn_benchmark(all_laps)

            # 更新基準值文件並儲存
            existing.version = (existing.version or 0) + 1  # 版本號遞增
            existing.calculated_at = datetime.now()          # 計算完成時間
            existing.user_count = len(users)                 # 使用者數量
            existing.session_count = session_count           # session 數量
            existing.lap_count = len(all_laps)               # 圈數
            existing.user_codes = user_codes                 # 使用者代碼列表
            existing.lap_time = lap_time                     # 圈數時間基準
            existing.gait = gait_benchmark                   # 步態基準
            existing.speed_distance = speed_distance         # 速度距離基準
            existing.turn = turn                             # 轉向基準
            existing.status = "completed"                    # 狀態：完成
            existing.error_message = None                    # 清除錯誤訊息
            existing.updated_at = datetime.now()

            await existing.save()
            return existing

        except Exception as e:
            # 計算失敗：記錄錯誤並更新狀態
            logger.error(f"Failed to calculate benchmark for {cohort_name}: {e}")
            existing.status = "failed"
            existing.error_message = str(e)
            existing.updated_at = datetime.now()
            await existing.save()
            raise  # 重新拋出例外讓呼叫端處理

    # ========================================================================
    # 個人比對方法
    # ========================================================================
    def _compute_percentile_position(
        self,
        value: float,
        stats: PercentileStatsEmbed,
    ) -> float:
        """計算數值在百分位數中的位置。
        
        使用線性插值法估算個人數值在族群分布中的百分位位置。
        這可以直觀地了解個人表現相對於族群的排名。
        
        計算方法：
        1. 建立已知的百分位數對照表（P10, P25, P50, P75, P90）
        2. 找出數值落在哪兩個百分位數之間
        3. 使用線性插值計算精確的百分位位置
        4. 若超出 P10-P90 範圍，使用常態分布 Z-score 外推
        
        範例：
        - 若 P25=10, P50=15，個人數值=12.5
        - 則百分位位置 = 25 + (12.5-10)/(15-10) * (50-25) = 37.5

        Args:
            value: 個人數值
            stats: 族群百分位數統計

        Returns:
            百分位位置（0-100），數值越高表示在族群中排名越高
            
        Note:
            - 若族群無資料（count=0），回傳 50.0（中位數位置）
            - 若數值超出 P10-P90 範圍，使用 Z-score 外推至 0-100
        """
        # 無資料時回傳中位數位置
        if stats.count == 0:
            return 50.0

        # 建立百分位數對照表
        percentiles = [10, 25, 50, 75, 90]
        values = [stats.p10, stats.p25, stats.p50, stats.p75, stats.p90]

        # 處理邊界情況：數值低於 P10，使用 Z-score 外推
        if value < values[0]:
            # 使用 mean 和 std 計算 Z-score，再轉換為百分位
            if stats.std > 0:
                z = (value - stats.mean) / stats.std
                # 簡化的常態分布 CDF 近似：percentile ≈ 50 + 50 * erf(z / sqrt(2))
                # 這裡用更簡單的線性近似：z=-3 對應 0.1%，z=-2 對應 2.3%，z=-1 對應 15.9%
                percentile = 50.0 + z * 34.0  # 近似：每個標準差約 34 百分位
                return max(0.1, min(percentile, 10.0))  # 限制在 0.1-10 之間
            return float(percentiles[0])
        
        # 處理邊界情況：數值高於 P90，使用 Z-score 外推
        if value > values[-1]:
            if stats.std > 0:
                z = (value - stats.mean) / stats.std
                percentile = 50.0 + z * 34.0
                return max(90.0, min(percentile, 99.9))  # 限制在 90-99.9 之間
            return float(percentiles[-1])

        # 線性插值：找出數值落在哪個區間並計算精確位置
        for i in range(len(values) - 1):
            if values[i] <= value <= values[i + 1]:
                # 處理區間內數值相同的情況（避免除以零）
                if values[i + 1] == values[i]:
                    return float(percentiles[i])
                
                # 計算在區間內的比例
                ratio = (value - values[i]) / (values[i + 1] - values[i])
                
                # 線性插值計算百分位位置
                return float(percentiles[i] + ratio * (percentiles[i + 1] - percentiles[i]))

        # 預設回傳中位數位置（理論上不會執行到這裡）
        return 50.0

    def _compute_diff_pct(self, user_val: float, benchmark_val: float) -> float:
        """計算差異百分比。
        
        公式：(user - benchmark) / benchmark * 100
        正值表示使用者高於族群，負值表示低於族群。
        
        Args:
            user_val: 使用者數值
            benchmark_val: 族群基準數值
            
        Returns:
            差異百分比，若 benchmark_val 為 0 則回傳 0.0
        """
        if benchmark_val == 0:
            return 0.0
        return (user_val - benchmark_val) / benchmark_val * 100

    def _create_metric_comparison(
        self,
        user_values: np.ndarray,
        benchmark_stats: PercentileStatsEmbed,
    ) -> MetricComparison:
        """建立單一指標比對結果。
        
        將個人多圈數值計算百分位統計，與族群統計進行比對。
        計算各百分位的差異百分比和在族群中的百分位位置。

        Args:
            user_values: 個人多圈的數值陣列
            benchmark_stats: 族群百分位數統計

        Returns:
            MetricComparison: 包含完整比對資訊的結果物件
        """
        # 計算個人百分位統計
        user_stats = self.compute_percentiles(user_values)
        
        # 計算各百分位在族群中的位置
        p10_pos = self._compute_percentile_position(user_stats.p10, benchmark_stats)
        p25_pos = self._compute_percentile_position(user_stats.p25, benchmark_stats)
        p50_pos = self._compute_percentile_position(user_stats.p50, benchmark_stats)
        p75_pos = self._compute_percentile_position(user_stats.p75, benchmark_stats)
        p90_pos = self._compute_percentile_position(user_stats.p90, benchmark_stats)
        mean_pos = self._compute_percentile_position(user_stats.mean, benchmark_stats)
        
        # 判斷個人 P50 是否在族群正常範圍內（P25-P75）
        in_normal = benchmark_stats.p25 <= user_stats.p50 <= benchmark_stats.p75

        # 判定狀態
        if user_stats.p50 < benchmark_stats.p25:
            status: Literal["below_normal", "normal", "above_normal"] = "below_normal"
        elif user_stats.p50 > benchmark_stats.p75:
            status = "above_normal"
        else:
            status = "normal"

        # 計算各百分位的差異百分比和位置
        from .models import PercentileDiff
        diff = PercentileDiff(
            p10_diff_pct=self._compute_diff_pct(user_stats.p10, benchmark_stats.p10),
            p25_diff_pct=self._compute_diff_pct(user_stats.p25, benchmark_stats.p25),
            p50_diff_pct=self._compute_diff_pct(user_stats.p50, benchmark_stats.p50),
            p75_diff_pct=self._compute_diff_pct(user_stats.p75, benchmark_stats.p75),
            p90_diff_pct=self._compute_diff_pct(user_stats.p90, benchmark_stats.p90),
            mean_diff_pct=self._compute_diff_pct(user_stats.mean, benchmark_stats.mean),
            p10_percentile_position=p10_pos,
            p25_percentile_position=p25_pos,
            p50_percentile_position=p50_pos,
            p75_percentile_position=p75_pos,
            p90_percentile_position=p90_pos,
            mean_percentile_position=mean_pos,
        )

        return MetricComparison(
            user_p10=user_stats.p10,
            user_p25=user_stats.p25,
            user_p50=user_stats.p50,
            user_p75=user_stats.p75,
            user_p90=user_stats.p90,
            user_mean=user_stats.mean,
            user_count=user_stats.count,
            benchmark_p10=benchmark_stats.p10,
            benchmark_p25=benchmark_stats.p25,
            benchmark_p50=benchmark_stats.p50,
            benchmark_p75=benchmark_stats.p75,
            benchmark_p90=benchmark_stats.p90,
            benchmark_mean=benchmark_stats.mean,
            benchmark_count=benchmark_stats.count,
            percentile_position=p50_pos,
            in_normal_range=in_normal,
            status=status,
            diff=diff,
        )

    async def compare_user_to_benchmark(
        self,
        session_name: str,
        cohort_name: str,
    ) -> ComparisonResult:
        """個人與基準比對。
        
        將指定 session 的資料與族群基準值進行比對，產生完整的比對報告。
        個人數值會計算所有圈的百分位統計，然後與族群百分位進行對應比較。
        
        比對流程：
        1. 查詢族群基準值
        2. 查詢 session
        3. 分析 session 取得所有圈數和步態資料
        4. 計算個人各指標的百分位統計
        5. 對應百分位與族群進行比對
        6. 組裝並回傳完整比對結果

        Args:
            session_name: session 名稱
            cohort_name: 要比對的族群名稱

        Returns:
            ComparisonResult: 完整的比對結果，包含各類指標的比對資訊
            
        Raises:
            ValueError: 
                - 族群基準值不存在
                - 找不到 session
                - npy 檔案不存在
                - session 無法分析或無圈數資料
        """
        # 查詢族群基準值
        benchmark = await CohortBenchmark.find_one(
            CohortBenchmark.cohort_name == cohort_name
        )
        if not benchmark:
            raise ValueError(f"Benchmark for cohort {cohort_name} not found")

        # 查詢 session
        session = await RealsensePoseExtractor.find_one(
            RealsensePoseExtractor.session_name == session_name
        )
        if not session:
            raise ValueError(f"Session {session_name} not found")

        # 分析 session
        # 解析 npy 檔案路徑
        npy_path = self._resolve_npy_path(session)
        if not npy_path:
            raise ValueError(f"NPY file not found for session {session.session_name}")

        # 執行 session 分析
        det, gait = self._analyze_session(npy_path)
        if not det or not det.laps:
            raise ValueError(f"No laps detected for session {session.session_name}")

        # 取得所有圈的資料
        all_laps = det.laps

        # 建立各類指標的比對結果
        # 圈數時間比對（使用所有圈的數據計算百分位）
        lap_time_comp = None
        if benchmark.lap_time:
            lap_time_comp = LapTimeComparison(
                dur_total=self._create_metric_comparison(
                    np.array([lap.dur_total for lap in all_laps]), benchmark.lap_time.dur_total),
                dur_stand=self._create_metric_comparison(
                    np.array([lap.dur_stand for lap in all_laps]), benchmark.lap_time.dur_stand),
                dur_to_cone=self._create_metric_comparison(
                    np.array([lap.dur_to_cone for lap in all_laps]), benchmark.lap_time.dur_to_cone),
                dur_cone_turn=self._create_metric_comparison(
                    np.array([lap.dur_cone_turn for lap in all_laps]), benchmark.lap_time.dur_cone_turn),
                dur_return=self._create_metric_comparison(
                    np.array([lap.dur_return for lap in all_laps]), benchmark.lap_time.dur_return),
                dur_turn_to_sit=self._create_metric_comparison(
                    np.array([lap.dur_turn_to_sit for lap in all_laps]), benchmark.lap_time.dur_turn_to_sit),
                dur_sit=self._create_metric_comparison(
                    np.array([lap.dur_sit for lap in all_laps]), benchmark.lap_time.dur_sit),
            )

        # 步態比對（步態是整個 session 的摘要，只有一個值）
        gait_comp = None
        if benchmark.gait and gait:
            gait_comp = GaitComparison(
                spm=self._create_metric_comparison(np.array([gait.spm]), benchmark.gait.spm),
                mean_step_len=self._create_metric_comparison(np.array([gait.mean_step_len]), benchmark.gait.mean_step_len),
                l_swing_pct=self._create_metric_comparison(np.array([gait.l_swing_pct_mean]), benchmark.gait.l_swing_pct),
                r_swing_pct=self._create_metric_comparison(np.array([gait.r_swing_pct_mean]), benchmark.gait.r_swing_pct),
                l_stance_s=self._create_metric_comparison(np.array([gait.l_stance_s_mean]), benchmark.gait.l_stance_s),
                r_stance_s=self._create_metric_comparison(np.array([gait.r_stance_s_mean]), benchmark.gait.r_stance_s),
            )

        # 速度距離比對（使用所有圈的數據）
        speed_dist_comp = None
        if benchmark.speed_distance:
            # 計算每圈的行走速度
            speeds = np.array([lap.dist_lap_path_m / lap.dur_total if lap.dur_total > 0 else 0 for lap in all_laps])
            speed_dist_comp = SpeedDistanceComparison(
                speed_mps=self._create_metric_comparison(speeds, benchmark.speed_distance.speed_mps),
                dist_lap_path_m=self._create_metric_comparison(
                    np.array([lap.dist_lap_path_m for lap in all_laps]), benchmark.speed_distance.dist_lap_path_m),
                dist_outbound_m=self._create_metric_comparison(
                    np.array([lap.dist_outbound_m for lap in all_laps]), benchmark.speed_distance.dist_outbound_m),
                dist_return_m=self._create_metric_comparison(
                    np.array([lap.dist_return_m for lap in all_laps]), benchmark.speed_distance.dist_return_m),
                dist_cone_turn_m=self._create_metric_comparison(
                    np.array([lap.dist_cone_turn_path_m for lap in all_laps]), benchmark.speed_distance.dist_cone_turn_m),
            )

        # 轉向比對（使用所有圈的數據）
        turn_comp = None
        if benchmark.turn:
            turn_comp = TurnComparison(
                delta_theta_cone_deg=self._create_metric_comparison(
                    np.array([lap.delta_theta_cone_deg for lap in all_laps]), benchmark.turn.delta_theta_cone_deg),
                delta_theta_chair_deg=self._create_metric_comparison(
                    np.array([lap.delta_theta_chair_deg for lap in all_laps]), benchmark.turn.delta_theta_chair_deg),
            )

        # 組裝並回傳完整比對結果
        return ComparisonResult(
            session_name=session.session_name,
            user_code=session.user_code,
            cohort_name=cohort_name,
            compared_at=datetime.now(),
            lap_count=len(all_laps),
            lap_time=lap_time_comp,
            gait=gait_comp,
            speed_distance=speed_dist_comp,
            turn=turn_comp,
        )

cohort_benchmark_service = CohortBenchmarkService()