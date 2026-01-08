"""
族群基準分析服務。

主要功能：
1. 族群使用者管理 - 查詢特定族群的使用者列表
2. Session 資料收集 - 彙整族群內所有使用者的復健 session
3. 基準值計算 - 計算各項指標的百分位數統計（P10, P25, P50, P75, P90）
4. 個人比對 - 將個人數據與族群基準進行比較，判斷是否在正常範圍內
"""
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
    UserProfile,
)

from .calculator import compute_percentiles, DEFAULT_PERCENTILES
from .collector import get_cohort_users, get_user_sessions, collect_cohort_sessions
from .comparison import compute_percentile_position, compute_diff_pct, create_metric_comparison
from .models import (
    ComparisonResult,
    GaitComparison,
    LapTimeComparison,
    SpeedDistanceComparison,
    TurnComparison,
)

logger = setup_logger("api.v1.cohort_benchmark.service")


class CohortBenchmarkService:
    """族群基準分析服務。"""

    DEFAULT_PERCENTILES = DEFAULT_PERCENTILES

    # 委託給模組函數
    def compute_percentiles(
        self,
        values: np.ndarray,
        percentiles: Optional[List[int]] = None,
    ) -> PercentileStatsEmbed:
        """計算百分位數統計。"""
        return compute_percentiles(values, percentiles)

    async def get_cohort_users(
        self,
        cohort_names: List[str],
        intersection: bool = False,
    ) -> List[UserProfile]:
        """查詢族群使用者。"""
        return await get_cohort_users(cohort_names, intersection)

    async def get_user_sessions(self, user_code: str) -> List[RealsensePoseExtractor]:
        """查詢使用者的所有 session。"""
        return await get_user_sessions(user_code)

    async def collect_cohort_sessions(
        self,
        user_codes: List[str],
    ) -> List[Tuple[str, RealsensePoseExtractor]]:
        """彙整族群所有使用者的 session。"""
        return await collect_cohort_sessions(user_codes)

    def _compute_percentile_position(
        self,
        value: float,
        stats: PercentileStatsEmbed,
    ) -> float:
        """計算數值在百分位數中的位置。"""
        return compute_percentile_position(value, stats)

    def _compute_diff_pct(self, user_val: float, benchmark_val: float) -> float:
        """計算差異百分比。"""
        return compute_diff_pct(user_val, benchmark_val)

    def _create_metric_comparison(
        self,
        user_values: np.ndarray,
        benchmark_stats: PercentileStatsEmbed,
    ):
        """建立單一指標比對結果。"""
        return create_metric_comparison(user_values, benchmark_stats)

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
        """計算步態基準。"""
        if not all_gaits:
            empty = self.compute_percentiles(np.array([]))
            return GaitBenchmarkEmbed(
                spm=empty, mean_step_len=empty,
                l_swing_pct=empty, r_swing_pct=empty,
                l_stance_s=empty, r_stance_s=empty
            )

        return GaitBenchmarkEmbed(
            spm=self.compute_percentiles(np.array([g.spm for g in all_gaits])),
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

    # ========================================================================
    # 主方法
    # ========================================================================

    async def calculate_benchmark(
        self,
        cohort_name: str,
        force_recalculate: bool = False,
    ) -> CohortBenchmark:
        """計算族群基準值。"""
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

            all_laps: List[Lap] = []
            all_gaits: List[GaitSummary] = []
            session_count = 0

            for user_code, session in sessions:
                npy_path = self._resolve_npy_path(session)
                if not npy_path:
                    continue

                det, gait = self._analyze_session(npy_path)
                if det is None:
                    continue

                session_count += 1
                all_laps.extend(det.laps)
                if gait:
                    all_gaits.append(gait)

            lap_time = self._compute_lap_time_benchmark(all_laps)
            gait_benchmark = self._compute_gait_benchmark(all_gaits)
            speed_distance = self._compute_speed_distance_benchmark(all_laps)
            turn = self._compute_turn_benchmark(all_laps)

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
    ) -> ComparisonResult:
        """個人與基準比對。"""
        benchmark = await CohortBenchmark.find_one(
            CohortBenchmark.cohort_name == cohort_name
        )
        if not benchmark:
            raise ValueError(f"Benchmark for cohort {cohort_name} not found")

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
        lap_time_comp = self._build_lap_time_comparison(all_laps, benchmark)
        gait_comp = self._build_gait_comparison(gait, benchmark)
        speed_dist_comp = self._build_speed_distance_comparison(all_laps, benchmark)
        turn_comp = self._build_turn_comparison(all_laps, benchmark)

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

    def _build_lap_time_comparison(self, all_laps: List[Lap], benchmark: CohortBenchmark):
        """建立圈數時間比對結果。"""
        if not benchmark.lap_time:
            return None
        return LapTimeComparison(
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

    def _build_gait_comparison(self, gait: Optional[GaitSummary], benchmark: CohortBenchmark):
        """建立步態比對結果。"""
        if not benchmark.gait or not gait:
            return None
        return GaitComparison(
            spm=self._create_metric_comparison(np.array([gait.spm]), benchmark.gait.spm),
            mean_step_len=self._create_metric_comparison(np.array([gait.mean_step_len]), benchmark.gait.mean_step_len),
            l_swing_pct=self._create_metric_comparison(np.array([gait.l_swing_pct_mean]), benchmark.gait.l_swing_pct),
            r_swing_pct=self._create_metric_comparison(np.array([gait.r_swing_pct_mean]), benchmark.gait.r_swing_pct),
            l_stance_s=self._create_metric_comparison(np.array([gait.l_stance_s_mean]), benchmark.gait.l_stance_s),
            r_stance_s=self._create_metric_comparison(np.array([gait.r_stance_s_mean]), benchmark.gait.r_stance_s),
        )

    def _build_speed_distance_comparison(self, all_laps: List[Lap], benchmark: CohortBenchmark):
        """建立速度距離比對結果。"""
        if not benchmark.speed_distance:
            return None
        speeds = np.array([lap.dist_lap_path_m / lap.dur_total if lap.dur_total > 0 else 0 for lap in all_laps])
        return SpeedDistanceComparison(
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

    def _build_turn_comparison(self, all_laps: List[Lap], benchmark: CohortBenchmark):
        """建立轉向比對結果。"""
        if not benchmark.turn:
            return None
        return TurnComparison(
            delta_theta_cone_deg=self._create_metric_comparison(
                np.array([lap.delta_theta_cone_deg for lap in all_laps]), benchmark.turn.delta_theta_cone_deg),
            delta_theta_chair_deg=self._create_metric_comparison(
                np.array([lap.delta_theta_chair_deg for lap in all_laps]), benchmark.turn.delta_theta_chair_deg),
        )


cohort_benchmark_service = CohortBenchmarkService()
