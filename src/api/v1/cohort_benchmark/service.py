"""
族群基準分析 API 服務層。

此模組作為 API 層與核心業務邏輯的橋接，
將核心服務的結果轉換為 API 回應模型。
"""
from datetime import datetime
from typing import List, Optional

import numpy as np

from logger import setup_logger
from rehab_analyzer.entities import GaitSummary, Lap

from db.mongo.models import (
    CohortBenchmark,
    PercentileStatsEmbed,
    RealsensePoseExtractor,
    UserProfile,
)

# 從核心模組導入
from cohort_benchmark import cohort_benchmark_service as _core_service
from cohort_benchmark.comparison import MetricComparisonResult

from .models import (
    BalanceAssessment,
    ComparisonResult,
    EnduranceAssessment,
    FunctionalAssessment,
    FunctionalMetric,
    GaitComparison,
    LapTimeComparison,
    MetricComparison,
    MuscleEnduranceAssessment,
    SpeedDistanceComparison,
    TurnComparison,
)

logger = setup_logger("api.v1.cohort_benchmark.service")


# ============================================================================
# 論文參考標準值（健康成人 TUG 測試）
# ============================================================================
REFERENCE_VALUES = {
    "walk_to_cone_s": 2.264,
    "walk_back_and_sit_s": 2.283,
    "cone_turn_s": 1.354,
    "stand_up_s": 0.945,
}


def _convert_comparison_result(result: MetricComparisonResult) -> MetricComparison:
    """將核心模組的比對結果轉換為 API 模型。"""
    return MetricComparison(
        user_value=result.user_value,
        cohort_value=result.cohort_value,
        diff_pct=result.diff_pct,
        is_better=result.is_better,
        status=result.status,
    )


class CohortBenchmarkAPIService:
    """族群基準分析 API 服務。
    
    封裝核心服務，提供 API 層所需的轉換和額外功能。
    """

    # ========================================================================
    # 委託給核心服務的方法
    # ========================================================================

    async def get_cohort_users(
        self,
        cohort_names: List[str],
        intersection: bool = False,
    ) -> List[UserProfile]:
        """查詢族群使用者。"""
        return await _core_service.get_cohort_users(cohort_names, intersection)

    async def calculate_benchmark(
        self,
        cohort_name: str,
        force_recalculate: bool = False,
        max_workers: Optional[int] = None,
    ) -> CohortBenchmark:
        """計算族群基準值。"""
        return await _core_service.calculate_benchmark(
            cohort_name, force_recalculate, max_workers
        )

    # ========================================================================
    # API 專用方法
    # ========================================================================

    async def compare_user_to_benchmark(
        self,
        session_name: str,
        cohort_name: str,
        user_percentile: int = 50,
        cohort_percentile: int = 50,
    ) -> ComparisonResult:
        """個人與基準比對（API 版本）。"""
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
                f"Benchmark for cohort '{cohort_name}' has no data"
            )

        session = await RealsensePoseExtractor.find_one(
            RealsensePoseExtractor.session_name == session_name
        )
        if not session:
            raise ValueError(f"Session {session_name} not found")

        npy_path = _core_service._resolve_npy_path(session)
        if not npy_path:
            raise ValueError(f"NPY file not found for session {session.session_name}")

        det, gait = _core_service._analyze_session(npy_path)
        if not det or not det.laps:
            raise ValueError(f"No laps detected for session {session.session_name}")

        all_laps = det.laps

        # 使用核心服務建立比對結果，然後轉換為 API 模型
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
        user_pct: int,
        cohort_pct: int,
    ) -> Optional[LapTimeComparison]:
        """建立圈數時間比對結果（API 模型）。"""
        result = _core_service.build_lap_time_comparison(
            all_laps, benchmark, user_pct, cohort_pct
        )
        if not result:
            return None
        return LapTimeComparison(
            dur_total=_convert_comparison_result(result["dur_total"]),
            dur_stand=_convert_comparison_result(result["dur_stand"]),
            dur_to_cone=_convert_comparison_result(result["dur_to_cone"]),
            dur_cone_turn=_convert_comparison_result(result["dur_cone_turn"]),
            dur_return=_convert_comparison_result(result["dur_return"]),
            dur_turn_to_sit=_convert_comparison_result(result["dur_turn_to_sit"]),
            dur_sit=_convert_comparison_result(result["dur_sit"]),
            dur_walking=_convert_comparison_result(result["dur_walking"]),
        )

    def _build_gait_comparison(
        self,
        gait: Optional[GaitSummary],
        benchmark: CohortBenchmark,
        user_pct: int,
        cohort_pct: int,
    ) -> Optional[GaitComparison]:
        """建立步態比對結果（API 模型）。"""
        result = _core_service.build_gait_comparison(gait, benchmark, user_pct, cohort_pct)
        if not result:
            return None
        return GaitComparison(
            spm=_convert_comparison_result(result["spm"]),
            mean_step_len=_convert_comparison_result(result["mean_step_len"]),
            l_swing_pct=_convert_comparison_result(result["l_swing_pct"]),
            r_swing_pct=_convert_comparison_result(result["r_swing_pct"]),
            l_stance_s=_convert_comparison_result(result["l_stance_s"]),
            r_stance_s=_convert_comparison_result(result["r_stance_s"]),
        )

    def _build_speed_distance_comparison(
        self,
        all_laps: List[Lap],
        benchmark: CohortBenchmark,
        user_pct: int,
        cohort_pct: int,
    ) -> Optional[SpeedDistanceComparison]:
        """建立速度距離比對結果（API 模型）。"""
        result = _core_service.build_speed_distance_comparison(
            all_laps, benchmark, user_pct, cohort_pct
        )
        if not result:
            return None
        return SpeedDistanceComparison(
            speed_mps=_convert_comparison_result(result["speed_mps"]),
            dist_lap_path_m=_convert_comparison_result(result["dist_lap_path_m"]),
            dist_outbound_m=_convert_comparison_result(result["dist_outbound_m"]),
            dist_return_m=_convert_comparison_result(result["dist_return_m"]),
            dist_cone_turn_m=_convert_comparison_result(result["dist_cone_turn_m"]),
            dist_walking_m=_convert_comparison_result(result["dist_walking_m"]),
        )

    def _build_turn_comparison(
        self,
        all_laps: List[Lap],
        benchmark: CohortBenchmark,
        user_pct: int,
        cohort_pct: int,
    ) -> Optional[TurnComparison]:
        """建立轉向比對結果（API 模型）。"""
        result = _core_service.build_turn_comparison(all_laps, benchmark, user_pct, cohort_pct)
        if not result:
            return None
        return TurnComparison(
            delta_theta_cone_deg=_convert_comparison_result(result["delta_theta_cone_deg"]),
            delta_theta_chair_deg=_convert_comparison_result(result["delta_theta_chair_deg"]),
        )

    def _build_functional_assessment(
        self,
        all_laps: List[Lap],
        benchmark: CohortBenchmark,
        user_pct: int,
        cohort_pct: int,
    ) -> FunctionalAssessment:
        """建立功能評估（基於論文標準值）。"""
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
            
            diff_from_ref = 0.0
            if reference_value > 0:
                diff_from_ref = (user_value - reference_value) / reference_value * 100
            
            if higher_is_better:
                if reference_value > 0:
                    ratio = user_value / reference_value
                    radar_score = min(100, max(0, 50 * ratio))
                else:
                    radar_score = 50.0
            else:
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
        
        walk_to_cone_values = [lap.dur_to_cone for lap in all_laps]
        walk_back_and_sit_values = [
            lap.dur_return + lap.dur_turn_to_sit + lap.dur_sit for lap in all_laps
        ]
        cone_turn_values = [lap.dur_cone_turn for lap in all_laps]
        stand_up_values = [lap.dur_stand for lap in all_laps]
        
        cohort_to_cone = benchmark.lap_time.dur_to_cone if benchmark.lap_time else None
        cohort_cone_turn = benchmark.lap_time.dur_cone_turn if benchmark.lap_time else None
        cohort_stand = benchmark.lap_time.dur_stand if benchmark.lap_time else None
        cohort_return = benchmark.lap_time.dur_return if benchmark.lap_time else None
        cohort_walking = benchmark.lap_time.dur_walking if benchmark.lap_time else None
        
        # 計算純行走時間 (dur_to_cone + dur_return)
        total_walking_values = [lap.dur_to_cone + lap.dur_return for lap in all_laps]
        
        endurance = EnduranceAssessment(
            walk_to_cone_s=create_functional_metric(
                walk_to_cone_values, REFERENCE_VALUES["walk_to_cone_s"],
                cohort_to_cone, higher_is_better=False,
            ),
            walk_back_and_sit_s=create_functional_metric(
                walk_back_and_sit_values, REFERENCE_VALUES["walk_back_and_sit_s"],
                cohort_return, higher_is_better=False,
            ),
            total_walking_s=create_functional_metric(
                total_walking_values,
                REFERENCE_VALUES["walk_to_cone_s"] + REFERENCE_VALUES["walk_back_and_sit_s"],
                cohort_walking, higher_is_better=False,
            ),
        )
        
        balance = BalanceAssessment(
            cone_turn_s=create_functional_metric(
                cone_turn_values, REFERENCE_VALUES["cone_turn_s"],
                cohort_cone_turn, higher_is_better=False,
            ),
        )
        
        muscle_endurance = MuscleEnduranceAssessment(
            stand_up_s=create_functional_metric(
                stand_up_values, REFERENCE_VALUES["stand_up_s"],
                cohort_stand, higher_is_better=False,
            ),
            return_and_sit_s=create_functional_metric(
                walk_back_and_sit_values, REFERENCE_VALUES["walk_back_and_sit_s"],
                cohort_return, higher_is_better=False,
            ),
        )
        
        return FunctionalAssessment(
            endurance=endurance,
            balance=balance,
            muscle_endurance=muscle_endurance,
        )


cohort_benchmark_service = CohortBenchmarkAPIService()
