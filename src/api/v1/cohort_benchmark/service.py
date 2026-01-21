"""
族群基準分析服務。

主要功能：
1. 族群使用者管理 - 查詢特定族群的使用者列表
2. Session 資料收集 - 彙整族群內所有使用者的復健 session
3. 基準值計算 - 計算各項指標的百分位數統計（P10, P25, P50, P75, P90）
4. 個人比對 - 將個人數據與族群基準進行比較，判斷是否在正常範圍內
"""
import asyncio
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from logger import setup_logger
from rehab_analyzer.entities import DetectLapsResult, GaitSummary, Lap
from rehab_analyzer.session_analyzer import RehabilitationSessionAnalyzer

from db.mongo.models import (
    CohortBenchmark,
    GaitBenchmarkEmbed,
    LapTimeBenchmarkEmbed,
    PercentileStatsEmbed,
    RealsensePoseExtractor,
    SpeedDistanceBenchmarkEmbed,
    TurnBenchmarkEmbed,
    UserMetricsEmbed,
    UserProfile,
)

from .calculator import compute_percentiles, DEFAULT_PERCENTILES
from .comparison import compute_diff_pct, create_metric_comparison
from .models import (
    BalanceAssessment,
    ComparisonResult,
    EnduranceAssessment,
    FunctionalAssessment,
    FunctionalMetric,
    GaitComparison,
    LapTimeComparison,
    MuscleEnduranceAssessment,
    SpeedDistanceComparison,
    TurnComparison,
)

logger = setup_logger("api.v1.cohort_benchmark.service")


# ============================================================================
# 多進程分析函數（必須在模組層級定義）
# ============================================================================

def _analyze_session_worker(npy_path: str) -> Optional[Tuple[DetectLapsResult, Optional[GaitSummary]]]:
    """多進程 worker：分析單一 session（在子進程中執行）。"""
    try:
        analyzer = RehabilitationSessionAnalyzer(npy_path=npy_path)
        det = analyzer.detect_laps_auto()
        gait = analyzer.compute_gait_summary()
        return (det, gait)
    except Exception:
        return None


# ============================================================================
# 論文參考標準值（健康成人 TUG 測試）
# ============================================================================
REFERENCE_VALUES = {
    "walk_to_cone_s": 2.264,      # 走向角錐時間（秒）
    "walk_back_and_sit_s": 2.283, # 走回+轉身坐下時間（秒）
    "cone_turn_s": 1.354,         # 三角錐轉身時間（秒）
    "stand_up_s": 0.945,          # 站起時間（秒）
}


class CohortBenchmarkService:
    """族群基準分析服務。"""

    DEFAULT_PERCENTILES: List[int] = DEFAULT_PERCENTILES

    # 委託給模組函數
    def compute_percentiles(
        self,
        values: np.ndarray,
        percentiles: Optional[List[int]] = None,
    ) -> PercentileStatsEmbed:
        """計算百分位數統計。"""
        return compute_percentiles(values, percentiles)

    # ========================================================================
    # 資料庫查詢方法
    # ========================================================================

    async def get_cohort_users(
        self,
        cohort_names: List[str],
        intersection: bool = False,
    ) -> List[UserProfile]:
        """查詢族群使用者（單次查詢）。"""
        if not cohort_names:
            return []
        if intersection:
            query = {"cohort": {"$all": cohort_names}}
        else:
            query = {"cohort": {"$in": cohort_names}}
        return await UserProfile.find(query).to_list()

    async def get_user_sessions(self, user_code: str) -> List[RealsensePoseExtractor]:
        """查詢單一使用者的所有 session。"""
        return await RealsensePoseExtractor.find(
            RealsensePoseExtractor.user_code == user_code
        ).to_list()

    async def collect_cohort_sessions(
        self,
        user_codes: List[str],
    ) -> List[Tuple[str, RealsensePoseExtractor]]:
        """批量查詢族群所有 session。"""
        if not user_codes:
            return []
        sessions = await RealsensePoseExtractor.find(
            {"user_code": {"$in": user_codes}}
        ).to_list()
        return [(s.user_code, s) for s in sessions]

    def _compute_diff_pct(self, user_val: float, benchmark_val: float) -> float:
        """計算差異百分比。"""
        return compute_diff_pct(user_val, benchmark_val)

    def _create_metric_comparison(
        self,
        user_values: np.ndarray,
        benchmark_stats: PercentileStatsEmbed,
        user_pct: int = 50,
        cohort_pct: int = 50,
        metric_name: str = "",
    ):
        """建立單一指標比對結果。"""
        return create_metric_comparison(user_values, benchmark_stats, user_pct, cohort_pct, metric_name)

    # ========================================================================
    # 輔助方法
    # ========================================================================

    def _resolve_npy_path(self, session: RealsensePoseExtractor) -> Optional[str]:
        """解析 session 的 npy 檔案路徑。"""
        raw = session.npy_path or ""
        if not raw:
            return None

        if "\\" in raw:
            raw = raw.replace("\\", "/")

        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate

        if candidate.exists():
            return str(candidate)
        return None

    def _analyze_session(
        self,
        npy_path: str,
    ) -> Tuple[Optional[DetectLapsResult], Optional[GaitSummary]]:
        """分析單一 session。"""
        try:
            analyzer = RehabilitationSessionAnalyzer(npy_path=npy_path)
            det = analyzer.detect_laps_auto()
            gait = analyzer.compute_gait_summary()
            return det, gait
        except Exception as e:
            logger.warning(f"Failed to analyze session {npy_path}: {e}")
            return None, None

    # ========================================================================
    # 基準值計算方法
    # ========================================================================

    def _compute_lap_time_benchmark(self, all_laps: List[Lap]) -> LapTimeBenchmarkEmbed:
        """計算圈數時間基準。"""
        if not all_laps:
            empty = self.compute_percentiles(np.array([]))
            return LapTimeBenchmarkEmbed(
                dur_total=empty, dur_stand=empty, dur_to_cone=empty,
                dur_cone_turn=empty, dur_return=empty, dur_turn_to_sit=empty, dur_sit=empty
            )

        return LapTimeBenchmarkEmbed(
            dur_total=self.compute_percentiles(np.array([lap.dur_total for lap in all_laps])),
            dur_stand=self.compute_percentiles(np.array([lap.dur_stand for lap in all_laps])),
            dur_to_cone=self.compute_percentiles(np.array([lap.dur_to_cone for lap in all_laps])),
            dur_cone_turn=self.compute_percentiles(np.array([lap.dur_cone_turn for lap in all_laps])),
            dur_return=self.compute_percentiles(np.array([lap.dur_return for lap in all_laps])),
            dur_turn_to_sit=self.compute_percentiles(np.array([lap.dur_turn_to_sit for lap in all_laps])),
            dur_sit=self.compute_percentiles(np.array([lap.dur_sit for lap in all_laps])),
        )

    def _compute_gait_benchmark(self, all_gaits: List[GaitSummary]) -> GaitBenchmarkEmbed:
        """計算步態基準。
        
        spm 使用步態週期時間計算（60 / avg_stride_s），與 gait_cycle_phases 一致。
        """
        if not all_gaits:
            empty = self.compute_percentiles(np.array([]))
            return GaitBenchmarkEmbed(
                spm=empty, mean_step_len=empty,
                l_swing_pct=empty, r_swing_pct=empty,
                l_stance_s=empty, r_stance_s=empty
            )
        
        # 計算 spm：使用步態週期時間（stride_s）而非步間時間
        def calc_spm_from_cycles(cycles: list) -> float:
            if not cycles:
                return 0.0
            valid_strides = [c.stride_s for c in cycles if 0.5 <= c.stride_s <= 3.0]
            if not valid_strides:
                return 0.0
            avg_stride = float(np.mean(valid_strides))
            return 60.0 / avg_stride if avg_stride > 0 else 0.0
        
        spm_values = []
        for g in all_gaits:
            l_spm = calc_spm_from_cycles(g.left_cycles)
            r_spm = calc_spm_from_cycles(g.right_cycles)
            if l_spm > 0 and r_spm > 0:
                spm_values.append((l_spm + r_spm) / 2)
            elif l_spm > 0 or r_spm > 0:
                spm_values.append(max(l_spm, r_spm))
            # 如果都沒有 cycles，fallback 到原本的 spm（但這種情況應該很少）
            elif g.spm > 0:
                spm_values.append(g.spm)

        return GaitBenchmarkEmbed(
            spm=self.compute_percentiles(np.array(spm_values) if spm_values else np.array([])),
            mean_step_len=self.compute_percentiles(np.array([g.mean_step_len for g in all_gaits])),
            l_swing_pct=self.compute_percentiles(np.array([g.l_swing_pct_mean for g in all_gaits])),
            r_swing_pct=self.compute_percentiles(np.array([g.r_swing_pct_mean for g in all_gaits])),
            l_stance_s=self.compute_percentiles(np.array([g.l_stance_s_mean for g in all_gaits])),
            r_stance_s=self.compute_percentiles(np.array([g.r_stance_s_mean for g in all_gaits])),
        )

    def _compute_speed_distance_benchmark(self, all_laps: List[Lap]) -> SpeedDistanceBenchmarkEmbed:
        """計算速度距離基準。"""
        if not all_laps:
            empty = self.compute_percentiles(np.array([]))
            return SpeedDistanceBenchmarkEmbed(
                speed_mps=empty, dist_lap_path_m=empty,
                dist_outbound_m=empty, dist_return_m=empty, dist_cone_turn_m=empty
            )

        speeds = [lap.dist_lap_path_m / lap.dur_total for lap in all_laps if lap.dur_total > 0]

        return SpeedDistanceBenchmarkEmbed(
            speed_mps=self.compute_percentiles(np.array(speeds) if speeds else np.array([])),
            dist_lap_path_m=self.compute_percentiles(np.array([lap.dist_lap_path_m for lap in all_laps])),
            dist_outbound_m=self.compute_percentiles(np.array([lap.dist_outbound_m for lap in all_laps])),
            dist_return_m=self.compute_percentiles(np.array([lap.dist_return_m for lap in all_laps])),
            dist_cone_turn_m=self.compute_percentiles(np.array([lap.dist_cone_turn_path_m for lap in all_laps])),
        )

    def _compute_turn_benchmark(self, all_laps: List[Lap]) -> TurnBenchmarkEmbed:
        """計算轉向基準。"""
        if not all_laps:
            empty = self.compute_percentiles(np.array([]))
            return TurnBenchmarkEmbed(
                delta_theta_cone_deg=empty, delta_theta_chair_deg=empty,
                turn_cone_dir_ratio={}, turn_chair_dir_ratio={}
            )

        cone_dirs = [lap.turn_cone_dir for lap in all_laps]
        chair_dirs = [lap.turn_chair_dir for lap in all_laps]

        def compute_dir_ratio(dirs: List[int]) -> Dict[str, float]:
            """計算轉向方向比例。
            
            Args:
                dirs: 轉向方向列表，每個值為 +1（右轉）、-1（左轉）或 0（無明顯轉向）
            
            Returns:
                各方向的比例，例如 {"+1": 0.6, "-1": 0.3, "0": 0.1}
                表示 60% 右轉、30% 左轉、10% 無轉向
            """
            if not dirs:
                return {}
            total = len(dirs)
            pos = sum(1 for d in dirs if d > 0)
            neg = sum(1 for d in dirs if d < 0)
            zero = sum(1 for d in dirs if d == 0)
            result = {}
            if pos > 0:
                result["+1"] = pos / total
            if neg > 0:
                result["-1"] = neg / total
            if zero > 0:
                result["0"] = zero / total
            return result

        return TurnBenchmarkEmbed(
            delta_theta_cone_deg=self.compute_percentiles(
                np.array([lap.delta_theta_cone_deg for lap in all_laps])
            ),
            delta_theta_chair_deg=self.compute_percentiles(
                np.array([lap.delta_theta_chair_deg for lap in all_laps])
            ),
            turn_cone_dir_ratio=compute_dir_ratio(cone_dirs),
            turn_chair_dir_ratio=compute_dir_ratio(chair_dirs),
        )

    def _compute_user_metrics(self, user_data: Dict[str, Dict]) -> List[UserMetricsEmbed]:
        """計算每個使用者的統計值（中位數）。
        
        用於後續計算使用者在族群中的百分位排名。
        """
        user_metrics: List[UserMetricsEmbed] = []
        
        for user_code, data in user_data.items():
            laps: List[Lap] = data["laps"]
            gaits: List[GaitSummary] = data["gaits"]
            
            if not laps:
                continue
            
            # 計算圈數時間中位數
            dur_total_p50 = float(np.median([lap.dur_total for lap in laps]))
            dur_stand_p50 = float(np.median([lap.dur_stand for lap in laps]))
            dur_to_cone_p50 = float(np.median([lap.dur_to_cone for lap in laps]))
            dur_cone_turn_p50 = float(np.median([lap.dur_cone_turn for lap in laps]))
            dur_return_p50 = float(np.median([lap.dur_return for lap in laps]))
            dur_turn_to_sit_p50 = float(np.median([lap.dur_turn_to_sit for lap in laps]))
            dur_sit_p50 = float(np.median([lap.dur_sit for lap in laps]))
            
            # 計算速度距離中位數
            speeds = [lap.dist_lap_path_m / lap.dur_total for lap in laps if lap.dur_total > 0]
            speed_mps_p50 = float(np.median(speeds)) if speeds else None
            dist_lap_path_m_p50 = float(np.median([lap.dist_lap_path_m for lap in laps]))
            dist_outbound_m_p50 = float(np.median([lap.dist_outbound_m for lap in laps]))
            dist_return_m_p50 = float(np.median([lap.dist_return_m for lap in laps]))
            dist_cone_turn_m_p50 = float(np.median([lap.dist_cone_turn_path_m for lap in laps]))
            
            # 計算轉向中位數
            delta_theta_cone_deg_p50 = float(np.median([lap.delta_theta_cone_deg for lap in laps]))
            delta_theta_chair_deg_p50 = float(np.median([lap.delta_theta_chair_deg for lap in laps]))
            
            # 計算步態中位數（如果有的話）
            spm_p50 = None
            mean_step_len_p50 = None
            l_swing_pct_p50 = None
            r_swing_pct_p50 = None
            l_stance_s_p50 = None
            r_stance_s_p50 = None
            
            if gaits:
                spm_p50 = float(np.median([g.spm for g in gaits]))
                mean_step_len_p50 = float(np.median([g.mean_step_len for g in gaits]))
                l_swing_pct_p50 = float(np.median([g.l_swing_pct_mean for g in gaits]))
                r_swing_pct_p50 = float(np.median([g.r_swing_pct_mean for g in gaits]))
                l_stance_s_p50 = float(np.median([g.l_stance_s_mean for g in gaits]))
                r_stance_s_p50 = float(np.median([g.r_stance_s_mean for g in gaits]))
            
            user_metrics.append(UserMetricsEmbed(
                user_code=user_code,
                session_count=data["session_count"],
                lap_count=len(laps),
                dur_total_p50=dur_total_p50,
                dur_stand_p50=dur_stand_p50,
                dur_to_cone_p50=dur_to_cone_p50,
                dur_cone_turn_p50=dur_cone_turn_p50,
                dur_return_p50=dur_return_p50,
                dur_turn_to_sit_p50=dur_turn_to_sit_p50,
                dur_sit_p50=dur_sit_p50,
                spm_p50=spm_p50,
                mean_step_len_p50=mean_step_len_p50,
                l_swing_pct_p50=l_swing_pct_p50,
                r_swing_pct_p50=r_swing_pct_p50,
                l_stance_s_p50=l_stance_s_p50,
                r_stance_s_p50=r_stance_s_p50,
                speed_mps_p50=speed_mps_p50,
                dist_lap_path_m_p50=dist_lap_path_m_p50,
                dist_outbound_m_p50=dist_outbound_m_p50,
                dist_return_m_p50=dist_return_m_p50,
                dist_cone_turn_m_p50=dist_cone_turn_m_p50,
                delta_theta_cone_deg_p50=delta_theta_cone_deg_p50,
                delta_theta_chair_deg_p50=delta_theta_chair_deg_p50,
            ))
        
        return user_metrics

    # ========================================================================
    # 主方法
    # ========================================================================

    async def calculate_benchmark(
        self,
        cohort_name: str,
        force_recalculate: bool = False,
        max_workers: Optional[int] = None,
    ) -> CohortBenchmark:
        """計算族群基準值（多進程並行分析）。
        
        Args:
            cohort_name: 族群名稱
            force_recalculate: 是否強制重新計算
            max_workers: 最大並行進程數（預設為 CPU 核心數）
        """
        existing = await CohortBenchmark.find_one(
            CohortBenchmark.cohort_name == cohort_name
        )

        if existing and not force_recalculate:
            return existing

        if existing:
            existing.status = "calculating"
            existing.updated_at = datetime.now()
            await existing.save()
        else:
            existing = CohortBenchmark(cohort_name=cohort_name, status="calculating")
            await existing.insert()

        try:
            users = await self.get_cohort_users([cohort_name], intersection=False)

            if not users:
                existing.status = "completed"
                existing.user_count = 0
                existing.session_count = 0
                existing.lap_count = 0
                existing.updated_at = datetime.now()
                await existing.save()
                return existing

            user_codes = [u.user_code for u in users]
            sessions = await self.collect_cohort_sessions(user_codes)

            # 準備要分析的 session 列表
            tasks: List[Tuple[str, str]] = []  # (user_code, npy_path)
            for user_code, session in sessions:
                npy_path = self._resolve_npy_path(session)
                if npy_path:
                    tasks.append((user_code, npy_path))

            # 多進程並行分析
            user_data: Dict[str, Dict] = {}
            all_laps: List[Lap] = []
            all_gaits: List[GaitSummary] = []
            session_count = 0

            loop = asyncio.get_event_loop()
            with ProcessPoolExecutor(max_workers=max_workers) as executor:
                # 提交所有任務
                futures = [
                    loop.run_in_executor(executor, _analyze_session_worker, npy_path)
                    for _, npy_path in tasks
                ]
                # 等待所有結果
                results = await asyncio.gather(*futures)

            # 處理結果
            for (user_code, _), result in zip(tasks, results):
                if result is None:
                    continue
                det, gait = result
                if det is None:
                    continue

                session_count += 1
                all_laps.extend(det.laps)
                if gait:
                    all_gaits.append(gait)

                # 收集每個使用者的數據
                if user_code not in user_data:
                    user_data[user_code] = {
                        "laps": [],
                        "gaits": [],
                        "session_count": 0,
                    }
                user_data[user_code]["laps"].extend(det.laps)
                user_data[user_code]["session_count"] += 1
                if gait:
                    user_data[user_code]["gaits"].append(gait)

            lap_time = self._compute_lap_time_benchmark(all_laps)
            gait_benchmark = self._compute_gait_benchmark(all_gaits)
            speed_distance = self._compute_speed_distance_benchmark(all_laps)
            turn = self._compute_turn_benchmark(all_laps)

            # 計算每個使用者的統計值
            user_metrics = self._compute_user_metrics(user_data)

            existing.version = (existing.version or 0) + 1
            existing.calculated_at = datetime.now()
            existing.user_count = len(users)
            existing.session_count = session_count
            existing.lap_count = len(all_laps)
            existing.user_codes = user_codes
            existing.lap_time = lap_time
            existing.gait = gait_benchmark
            existing.speed_distance = speed_distance
            existing.turn = turn
            existing.user_metrics = user_metrics
            existing.status = "completed"
            existing.error_message = None
            existing.updated_at = datetime.now()

            await existing.save()
            return existing

        except Exception as e:
            logger.error(f"Failed to calculate benchmark for {cohort_name}: {e}")
            existing.status = "failed"
            existing.error_message = str(e)
            existing.updated_at = datetime.now()
            await existing.save()
            raise

    # ========================================================================
    # 個人比對方法
    # ========================================================================

    async def compare_user_to_benchmark(
        self,
        session_name: str,
        cohort_name: str,
        user_percentile: int = 50,
        cohort_percentile: int = 50,
    ) -> ComparisonResult:
        """個人與基準比對。
        
        Args:
            session_name: session 名稱
            cohort_name: 族群名稱
            user_percentile: 使用者要比較的百分位數（預設 50）
            cohort_percentile: 族群要比較的百分位數（預設 50）
        """
        benchmark = await CohortBenchmark.find_one(
            CohortBenchmark.cohort_name == cohort_name
        )
        if not benchmark:
            raise ValueError(f"Benchmark for cohort '{cohort_name}' not found")
        
        if benchmark.status != "completed":
            raise ValueError(
                f"Benchmark for cohort '{cohort_name}' is not ready (status: {benchmark.status})"
            )
        
        if not benchmark.lap_count or benchmark.lap_count == 0:
            raise ValueError(
                f"Benchmark for cohort '{cohort_name}' has no data "
                f"(user_count={benchmark.user_count}, session_count={benchmark.session_count}, lap_count={benchmark.lap_count}). "
                "Please ensure the cohort has users with valid sessions."
            )

        session = await RealsensePoseExtractor.find_one(
            RealsensePoseExtractor.session_name == session_name
        )
        if not session:
            raise ValueError(f"Session {session_name} not found")

        npy_path = self._resolve_npy_path(session)
        if not npy_path:
            raise ValueError(f"NPY file not found for session {session.session_name}")

        det, gait = self._analyze_session(npy_path)
        if not det or not det.laps:
            raise ValueError(f"No laps detected for session {session.session_name}")

        all_laps = det.laps

        # 建立各類指標的比對結果
        lap_time_comp = self._build_lap_time_comparison(
            all_laps, benchmark, user_percentile, cohort_percentile
        )
        gait_comp = self._build_gait_comparison(
            gait, benchmark, user_percentile, cohort_percentile
        )
        speed_dist_comp = self._build_speed_distance_comparison(
            all_laps, benchmark, user_percentile, cohort_percentile
        )
        turn_comp = self._build_turn_comparison(
            all_laps, benchmark, user_percentile, cohort_percentile
        )
        
        # 建立功能評估（基於論文標準值）
        functional_comp = self._build_functional_assessment(
            all_laps, benchmark, user_percentile, cohort_percentile
        )

        return ComparisonResult(
            session_name=session.session_name,
            user_code=session.user_code,
            cohort_name=cohort_name,
            compared_at=datetime.now(),
            lap_count=len(all_laps),
            user_percentile=user_percentile,
            cohort_percentile=cohort_percentile,
            lap_time=lap_time_comp,
            gait=gait_comp,
            speed_distance=speed_dist_comp,
            turn=turn_comp,
            functional=functional_comp,
        )

    def _build_lap_time_comparison(
        self,
        all_laps: List[Lap],
        benchmark: CohortBenchmark,
        user_pct: int = 50,
        cohort_pct: int = 50,
    ):
        """建立圈數時間比對結果。"""
        if not benchmark.lap_time:
            return None
        return LapTimeComparison(
            dur_total=self._create_metric_comparison(
                np.array([lap.dur_total for lap in all_laps]),
                benchmark.lap_time.dur_total, user_pct, cohort_pct, "dur_total"),
            dur_stand=self._create_metric_comparison(
                np.array([lap.dur_stand for lap in all_laps]),
                benchmark.lap_time.dur_stand, user_pct, cohort_pct, "dur_stand"),
            dur_to_cone=self._create_metric_comparison(
                np.array([lap.dur_to_cone for lap in all_laps]),
                benchmark.lap_time.dur_to_cone, user_pct, cohort_pct, "dur_to_cone"),
            dur_cone_turn=self._create_metric_comparison(
                np.array([lap.dur_cone_turn for lap in all_laps]),
                benchmark.lap_time.dur_cone_turn, user_pct, cohort_pct, "dur_cone_turn"),
            dur_return=self._create_metric_comparison(
                np.array([lap.dur_return for lap in all_laps]),
                benchmark.lap_time.dur_return, user_pct, cohort_pct, "dur_return"),
            dur_turn_to_sit=self._create_metric_comparison(
                np.array([lap.dur_turn_to_sit for lap in all_laps]),
                benchmark.lap_time.dur_turn_to_sit, user_pct, cohort_pct, "dur_turn_to_sit"),
            dur_sit=self._create_metric_comparison(
                np.array([lap.dur_sit for lap in all_laps]),
                benchmark.lap_time.dur_sit, user_pct, cohort_pct, "dur_sit"),
        )

    def _build_gait_comparison(
        self,
        gait: Optional[GaitSummary],
        benchmark: CohortBenchmark,
        user_pct: int = 50,
        cohort_pct: int = 50,
    ):
        """建立步態比對結果。
        
        spm 使用步態週期時間計算（60 / avg_stride_s），與 gait_cycle_phases 一致。
        """
        if not benchmark.gait or not gait:
            return None
        
        # 計算 spm：使用步態週期時間（stride_s）而非步間時間
        # 這與 gait_cycle_phases 的計算方式一致
        def calc_spm_from_cycles(cycles: list) -> float:
            if not cycles:
                return 0.0
            # 過濾有效週期（0.5s ~ 3.0s）
            valid_strides = [c.stride_s for c in cycles if 0.5 <= c.stride_s <= 3.0]
            if not valid_strides:
                return 0.0
            avg_stride = float(np.mean(valid_strides))
            return 60.0 / avg_stride if avg_stride > 0 else 0.0
        
        # 使用左右腳步態週期計算 spm
        l_spm = calc_spm_from_cycles(gait.left_cycles)
        r_spm = calc_spm_from_cycles(gait.right_cycles)
        # 取平均或較大值
        user_spm = (l_spm + r_spm) / 2 if l_spm > 0 and r_spm > 0 else max(l_spm, r_spm)
        
        return GaitComparison(
            spm=self._create_metric_comparison(
                np.array([user_spm]) if user_spm > 0 else np.array([gait.spm]),
                benchmark.gait.spm, user_pct, cohort_pct, "spm"),
            mean_step_len=self._create_metric_comparison(
                np.array([gait.mean_step_len]), benchmark.gait.mean_step_len, user_pct, cohort_pct, "mean_step_len"),
            l_swing_pct=self._create_metric_comparison(
                np.array([gait.l_swing_pct_mean]), benchmark.gait.l_swing_pct, user_pct, cohort_pct, "l_swing_pct"),
            r_swing_pct=self._create_metric_comparison(
                np.array([gait.r_swing_pct_mean]), benchmark.gait.r_swing_pct, user_pct, cohort_pct, "r_swing_pct"),
            l_stance_s=self._create_metric_comparison(
                np.array([gait.l_stance_s_mean]), benchmark.gait.l_stance_s, user_pct, cohort_pct, "l_stance_s"),
            r_stance_s=self._create_metric_comparison(
                np.array([gait.r_stance_s_mean]), benchmark.gait.r_stance_s, user_pct, cohort_pct, "r_stance_s"),
        )

    def _build_speed_distance_comparison(
        self,
        all_laps: List[Lap],
        benchmark: CohortBenchmark,
        user_pct: int = 50,
        cohort_pct: int = 50,
    ):
        """建立速度距離比對結果。"""
        if not benchmark.speed_distance:
            return None
        speeds = np.array([lap.dist_lap_path_m / lap.dur_total if lap.dur_total > 0 else 0 for lap in all_laps])
        return SpeedDistanceComparison(
            speed_mps=self._create_metric_comparison(
                speeds, benchmark.speed_distance.speed_mps, user_pct, cohort_pct, "speed_mps"),
            dist_lap_path_m=self._create_metric_comparison(
                np.array([lap.dist_lap_path_m for lap in all_laps]),
                benchmark.speed_distance.dist_lap_path_m, user_pct, cohort_pct, "dist_lap_path_m"),
            dist_outbound_m=self._create_metric_comparison(
                np.array([lap.dist_outbound_m for lap in all_laps]),
                benchmark.speed_distance.dist_outbound_m, user_pct, cohort_pct, "dist_outbound_m"),
            dist_return_m=self._create_metric_comparison(
                np.array([lap.dist_return_m for lap in all_laps]),
                benchmark.speed_distance.dist_return_m, user_pct, cohort_pct, "dist_return_m"),
            dist_cone_turn_m=self._create_metric_comparison(
                np.array([lap.dist_cone_turn_path_m for lap in all_laps]),
                benchmark.speed_distance.dist_cone_turn_m, user_pct, cohort_pct, "dist_cone_turn_m"),
        )

    def _build_turn_comparison(
        self,
        all_laps: List[Lap],
        benchmark: CohortBenchmark,
        user_pct: int = 50,
        cohort_pct: int = 50,
    ):
        """建立轉向比對結果。"""
        if not benchmark.turn:
            return None
        return TurnComparison(
            delta_theta_cone_deg=self._create_metric_comparison(
                np.array([lap.delta_theta_cone_deg for lap in all_laps]),
                benchmark.turn.delta_theta_cone_deg, user_pct, cohort_pct, "delta_theta_cone_deg"),
            delta_theta_chair_deg=self._create_metric_comparison(
                np.array([lap.delta_theta_chair_deg for lap in all_laps]),
                benchmark.turn.delta_theta_chair_deg, user_pct, cohort_pct, "delta_theta_chair_deg"),
        )

    def _build_functional_assessment(
        self,
        all_laps: List[Lap],
        benchmark: CohortBenchmark,
        user_pct: int = 50,
        cohort_pct: int = 50,
    ) -> FunctionalAssessment:
        """建立功能評估（基於論文標準值）。
        
        體能（Endurance）：走向角錐時間 + 走回椅子時間
        平衡（Balance）：三角錐轉身時間
        肌耐力（Muscle Endurance）：站起時間 + 走回+轉身坐下時間
        """
        def get_percentile_value(values: List[float], pct: int) -> float:
            if not values:
                return 0.0
            return float(np.percentile(values, pct))
        
        def get_cohort_value(stats: Optional[PercentileStatsEmbed], pct: int) -> Optional[float]:
            if not stats or stats.count == 0:
                return None
            known = {10: stats.p10, 25: stats.p25, 50: stats.p50, 75: stats.p75, 90: stats.p90}
            if pct in known:
                return known[pct]
            # 線性插值
            keys = sorted(known.keys())
            for i in range(len(keys) - 1):
                if keys[i] <= pct <= keys[i + 1]:
                    ratio = (pct - keys[i]) / (keys[i + 1] - keys[i])
                    return known[keys[i]] + ratio * (known[keys[i + 1]] - known[keys[i]])
            return stats.p50
        
        def create_functional_metric(
            user_values: List[float],
            reference_value: float,
            cohort_stats: Optional[PercentileStatsEmbed],
            higher_is_better: bool,
        ) -> FunctionalMetric:
            user_value = get_percentile_value(user_values, user_pct)
            cohort_value = get_cohort_value(cohort_stats, cohort_pct) if cohort_stats else None
            
            # 計算與參考值的差異百分比
            diff_from_ref = 0.0
            if reference_value > 0:
                diff_from_ref = (user_value - reference_value) / reference_value * 100
            
            # 計算雷達圖分數（與參考值比較）
            # 分數範圍 0-100，50 表示與參考值相同
            if higher_is_better:
                # 越高越好：user > ref 時分數 > 50
                if reference_value > 0:
                    ratio = user_value / reference_value
                    radar_score = min(100, max(0, 50 * ratio))
                else:
                    radar_score = 50.0
            else:
                # 越低越好：user < ref 時分數 > 50
                if user_value > 0:
                    ratio = reference_value / user_value
                    radar_score = min(100, max(0, 50 * ratio))
                else:
                    radar_score = 100.0 if reference_value > 0 else 50.0
            
            return FunctionalMetric(
                user_value=user_value,
                reference_value=reference_value,
                cohort_value=cohort_value,
                diff_from_reference_pct=diff_from_ref,
                higher_is_better=higher_is_better,
                radar_score=radar_score,
            )
        
        # 收集各項數據
        walk_to_cone_values = [lap.dur_to_cone for lap in all_laps]
        # 走回+轉身坐下 = dur_return + dur_turn_to_sit + dur_sit
        walk_back_and_sit_values = [
            lap.dur_return + lap.dur_turn_to_sit + lap.dur_sit for lap in all_laps
        ]
        cone_turn_values = [lap.dur_cone_turn for lap in all_laps]
        stand_up_values = [lap.dur_stand for lap in all_laps]
        
        # 取得族群基準值
        cohort_to_cone = benchmark.lap_time.dur_to_cone if benchmark.lap_time else None
        cohort_cone_turn = benchmark.lap_time.dur_cone_turn if benchmark.lap_time else None
        cohort_stand = benchmark.lap_time.dur_stand if benchmark.lap_time else None
        # 走回+轉身坐下 需要合併計算（這裡用 dur_return 近似）
        cohort_return = benchmark.lap_time.dur_return if benchmark.lap_time else None
        
        # 體能評估
        endurance = EnduranceAssessment(
            walk_to_cone_s=create_functional_metric(
                walk_to_cone_values,
                REFERENCE_VALUES["walk_to_cone_s"],
                cohort_to_cone,
                higher_is_better=False,  # 越短越好
            ),
            walk_back_and_sit_s=create_functional_metric(
                walk_back_and_sit_values,
                REFERENCE_VALUES["walk_back_and_sit_s"],
                cohort_return,  # 近似值
                higher_is_better=False,
            ),
            total_walking_s=create_functional_metric(
                [a + b for a, b in zip(walk_to_cone_values, walk_back_and_sit_values)],
                REFERENCE_VALUES["walk_to_cone_s"] + REFERENCE_VALUES["walk_back_and_sit_s"],
                None,
                higher_is_better=False,
            ),
        )
        
        # 平衡能力評估
        balance = BalanceAssessment(
            cone_turn_s=create_functional_metric(
                cone_turn_values,
                REFERENCE_VALUES["cone_turn_s"],
                cohort_cone_turn,
                higher_is_better=False,
            ),
        )
        
        # 肌耐力評估
        muscle_endurance = MuscleEnduranceAssessment(
            stand_up_s=create_functional_metric(
                stand_up_values,
                REFERENCE_VALUES["stand_up_s"],
                cohort_stand,
                higher_is_better=False,
            ),
            return_and_sit_s=create_functional_metric(
                walk_back_and_sit_values,
                REFERENCE_VALUES["walk_back_and_sit_s"],
                cohort_return,
                higher_is_better=False,
            ),
        )
        
        return FunctionalAssessment(
            endurance=endurance,
            balance=balance,
            muscle_endurance=muscle_endurance,
        )


cohort_benchmark_service = CohortBenchmarkService()
