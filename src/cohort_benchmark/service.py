"""
族群基準分析核心服務。

提供族群基準值計算、個人比對等核心業務邏輯。
此模組不依賴 API 層，可被 API 或 CLI 調用。
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
from .comparison import (
    compute_diff_pct,
    create_metric_comparison,
    MetricComparisonResult,
)

logger = setup_logger("cohort_benchmark.service")


# ============================================================================
# 多進程分析函數
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
    """族群基準分析核心服務。"""

    DEFAULT_PERCENTILES: List[int] = DEFAULT_PERCENTILES

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
    ) -> MetricComparisonResult:
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
                dur_cone_turn=empty, dur_return=empty, dur_turn_to_sit=empty,
                dur_sit=empty, dur_walking=empty
            )

        # 計算 dur_walking = dur_to_cone + dur_return
        dur_walking_values = np.array([lap.dur_to_cone + lap.dur_return for lap in all_laps])

        return LapTimeBenchmarkEmbed(
            dur_total=self.compute_percentiles(np.array([lap.dur_total for lap in all_laps])),
            dur_stand=self.compute_percentiles(np.array([lap.dur_stand for lap in all_laps])),
            dur_to_cone=self.compute_percentiles(np.array([lap.dur_to_cone for lap in all_laps])),
            dur_cone_turn=self.compute_percentiles(np.array([lap.dur_cone_turn for lap in all_laps])),
            dur_return=self.compute_percentiles(np.array([lap.dur_return for lap in all_laps])),
            dur_turn_to_sit=self.compute_percentiles(np.array([lap.dur_turn_to_sit for lap in all_laps])),
            dur_sit=self.compute_percentiles(np.array([lap.dur_sit for lap in all_laps])),
            dur_walking=self.compute_percentiles(dur_walking_values),
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
                dist_outbound_m=empty, dist_return_m=empty, dist_cone_turn_m=empty,
                dist_walking_m=empty
            )

        speeds = [lap.dist_lap_path_m / lap.dur_total for lap in all_laps if lap.dur_total > 0]
        
        # 計算 dist_walking_m = dist_outbound_m + dist_return_m
        dist_walking_values = np.array([lap.dist_outbound_m + lap.dist_return_m for lap in all_laps])

        return SpeedDistanceBenchmarkEmbed(
            speed_mps=self.compute_percentiles(np.array(speeds) if speeds else np.array([])),
            dist_lap_path_m=self.compute_percentiles(np.array([lap.dist_lap_path_m for lap in all_laps])),
            dist_outbound_m=self.compute_percentiles(np.array([lap.dist_outbound_m for lap in all_laps])),
            dist_return_m=self.compute_percentiles(np.array([lap.dist_return_m for lap in all_laps])),
            dist_cone_turn_m=self.compute_percentiles(np.array([lap.dist_cone_turn_path_m for lap in all_laps])),
            dist_walking_m=self.compute_percentiles(dist_walking_values),
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

    def _compute_user_metrics(self, user_data: Dict[str, Dict]) -> List[UserMetricsEmbed]:
        """計算每個使用者的統計值（中位數）。"""
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
            
            # 計算 dur_walking_p50 = median(dur_to_cone + dur_return)
            dur_walking_values = [lap.dur_to_cone + lap.dur_return for lap in laps]
            dur_walking_p50 = float(np.median(dur_walking_values))
            
            # 計算速度距離中位數
            speeds = [lap.dist_lap_path_m / lap.dur_total for lap in laps if lap.dur_total > 0]
            speed_mps_p50 = float(np.median(speeds)) if speeds else None
            dist_lap_path_m_p50 = float(np.median([lap.dist_lap_path_m for lap in laps]))
            dist_outbound_m_p50 = float(np.median([lap.dist_outbound_m for lap in laps]))
            dist_return_m_p50 = float(np.median([lap.dist_return_m for lap in laps]))
            dist_cone_turn_m_p50 = float(np.median([lap.dist_cone_turn_path_m for lap in laps]))
            
            # 計算 dist_walking_m_p50 = median(dist_outbound_m + dist_return_m)
            dist_walking_values = [lap.dist_outbound_m + lap.dist_return_m for lap in laps]
            dist_walking_m_p50 = float(np.median(dist_walking_values))
            
            # 計算轉向中位數
            delta_theta_cone_deg_p50 = float(np.median([lap.delta_theta_cone_deg for lap in laps]))
            delta_theta_chair_deg_p50 = float(np.median([lap.delta_theta_chair_deg for lap in laps]))
            
            # 計算步態中位數
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
                dur_walking_p50=dur_walking_p50,
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
                dist_walking_m_p50=dist_walking_m_p50,
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
        """計算族群基準值（多進程並行分析）。"""
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

            tasks: List[Tuple[str, str]] = []
            for user_code, session in sessions:
                npy_path = self._resolve_npy_path(session)
                if npy_path:
                    tasks.append((user_code, npy_path))

            user_data: Dict[str, Dict] = {}
            all_laps: List[Lap] = []
            all_gaits: List[GaitSummary] = []
            session_count = 0

            loop = asyncio.get_event_loop()
            with ProcessPoolExecutor(max_workers=max_workers) as executor:
                futures = [
                    loop.run_in_executor(executor, _analyze_session_worker, npy_path)
                    for _, npy_path in tasks
                ]
                results = await asyncio.gather(*futures)

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

                if user_code not in user_data:
                    user_data[user_code] = {"laps": [], "gaits": [], "session_count": 0}
                user_data[user_code]["laps"].extend(det.laps)
                user_data[user_code]["session_count"] += 1
                if gait:
                    user_data[user_code]["gaits"].append(gait)

            lap_time = self._compute_lap_time_benchmark(all_laps)
            gait_benchmark = self._compute_gait_benchmark(all_gaits)
            speed_distance = self._compute_speed_distance_benchmark(all_laps)
            turn = self._compute_turn_benchmark(all_laps)
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
    # 比對結果資料結構
    # ========================================================================

    def build_lap_time_comparison(
        self,
        all_laps: List[Lap],
        benchmark: CohortBenchmark,
        user_pct: int = 50,
        cohort_pct: int = 50,
    ) -> Optional[Dict[str, MetricComparisonResult]]:
        """建立圈數時間比對結果。"""
        if not benchmark.lap_time:
            return None
        
        # 計算 dur_walking
        dur_walking_values = np.array([lap.dur_to_cone + lap.dur_return for lap in all_laps])
        
        return {
            "dur_total": self._create_metric_comparison(
                np.array([lap.dur_total for lap in all_laps]),
                benchmark.lap_time.dur_total, user_pct, cohort_pct, "dur_total"),
            "dur_stand": self._create_metric_comparison(
                np.array([lap.dur_stand for lap in all_laps]),
                benchmark.lap_time.dur_stand, user_pct, cohort_pct, "dur_stand"),
            "dur_to_cone": self._create_metric_comparison(
                np.array([lap.dur_to_cone for lap in all_laps]),
                benchmark.lap_time.dur_to_cone, user_pct, cohort_pct, "dur_to_cone"),
            "dur_cone_turn": self._create_metric_comparison(
                np.array([lap.dur_cone_turn for lap in all_laps]),
                benchmark.lap_time.dur_cone_turn, user_pct, cohort_pct, "dur_cone_turn"),
            "dur_return": self._create_metric_comparison(
                np.array([lap.dur_return for lap in all_laps]),
                benchmark.lap_time.dur_return, user_pct, cohort_pct, "dur_return"),
            "dur_turn_to_sit": self._create_metric_comparison(
                np.array([lap.dur_turn_to_sit for lap in all_laps]),
                benchmark.lap_time.dur_turn_to_sit, user_pct, cohort_pct, "dur_turn_to_sit"),
            "dur_sit": self._create_metric_comparison(
                np.array([lap.dur_sit for lap in all_laps]),
                benchmark.lap_time.dur_sit, user_pct, cohort_pct, "dur_sit"),
            "dur_walking": self._create_metric_comparison(
                dur_walking_values,
                benchmark.lap_time.dur_walking, user_pct, cohort_pct, "dur_walking"),
        }

    def build_gait_comparison(
        self,
        gait: Optional[GaitSummary],
        benchmark: CohortBenchmark,
        user_pct: int = 50,
        cohort_pct: int = 50,
    ) -> Optional[Dict[str, MetricComparisonResult]]:
        """建立步態比對結果。"""
        if not benchmark.gait or not gait:
            return None
        
        def calc_spm_from_cycles(cycles: list) -> float:
            if not cycles:
                return 0.0
            valid_strides = [c.stride_s for c in cycles if 0.5 <= c.stride_s <= 3.0]
            if not valid_strides:
                return 0.0
            avg_stride = float(np.mean(valid_strides))
            return 60.0 / avg_stride if avg_stride > 0 else 0.0
        
        l_spm = calc_spm_from_cycles(gait.left_cycles)
        r_spm = calc_spm_from_cycles(gait.right_cycles)
        user_spm = (l_spm + r_spm) / 2 if l_spm > 0 and r_spm > 0 else max(l_spm, r_spm)
        
        return {
            "spm": self._create_metric_comparison(
                np.array([user_spm]) if user_spm > 0 else np.array([gait.spm]),
                benchmark.gait.spm, user_pct, cohort_pct, "spm"),
            "mean_step_len": self._create_metric_comparison(
                np.array([gait.mean_step_len]), benchmark.gait.mean_step_len, user_pct, cohort_pct, "mean_step_len"),
            "l_swing_pct": self._create_metric_comparison(
                np.array([gait.l_swing_pct_mean]), benchmark.gait.l_swing_pct, user_pct, cohort_pct, "l_swing_pct"),
            "r_swing_pct": self._create_metric_comparison(
                np.array([gait.r_swing_pct_mean]), benchmark.gait.r_swing_pct, user_pct, cohort_pct, "r_swing_pct"),
            "l_stance_s": self._create_metric_comparison(
                np.array([gait.l_stance_s_mean]), benchmark.gait.l_stance_s, user_pct, cohort_pct, "l_stance_s"),
            "r_stance_s": self._create_metric_comparison(
                np.array([gait.r_stance_s_mean]), benchmark.gait.r_stance_s, user_pct, cohort_pct, "r_stance_s"),
        }

    def build_speed_distance_comparison(
        self,
        all_laps: List[Lap],
        benchmark: CohortBenchmark,
        user_pct: int = 50,
        cohort_pct: int = 50,
    ) -> Optional[Dict[str, MetricComparisonResult]]:
        """建立速度距離比對結果。"""
        if not benchmark.speed_distance:
            return None
        speeds = np.array([lap.dist_lap_path_m / lap.dur_total if lap.dur_total > 0 else 0 for lap in all_laps])
        
        # 計算 dist_walking_m
        dist_walking_values = np.array([lap.dist_outbound_m + lap.dist_return_m for lap in all_laps])
        
        return {
            "speed_mps": self._create_metric_comparison(
                speeds, benchmark.speed_distance.speed_mps, user_pct, cohort_pct, "speed_mps"),
            "dist_lap_path_m": self._create_metric_comparison(
                np.array([lap.dist_lap_path_m for lap in all_laps]),
                benchmark.speed_distance.dist_lap_path_m, user_pct, cohort_pct, "dist_lap_path_m"),
            "dist_outbound_m": self._create_metric_comparison(
                np.array([lap.dist_outbound_m for lap in all_laps]),
                benchmark.speed_distance.dist_outbound_m, user_pct, cohort_pct, "dist_outbound_m"),
            "dist_return_m": self._create_metric_comparison(
                np.array([lap.dist_return_m for lap in all_laps]),
                benchmark.speed_distance.dist_return_m, user_pct, cohort_pct, "dist_return_m"),
            "dist_cone_turn_m": self._create_metric_comparison(
                np.array([lap.dist_cone_turn_path_m for lap in all_laps]),
                benchmark.speed_distance.dist_cone_turn_m, user_pct, cohort_pct, "dist_cone_turn_m"),
            "dist_walking_m": self._create_metric_comparison(
                dist_walking_values,
                benchmark.speed_distance.dist_walking_m, user_pct, cohort_pct, "dist_walking_m"),
        }

    def build_turn_comparison(
        self,
        all_laps: List[Lap],
        benchmark: CohortBenchmark,
        user_pct: int = 50,
        cohort_pct: int = 50,
    ) -> Optional[Dict[str, MetricComparisonResult]]:
        """建立轉向比對結果。"""
        if not benchmark.turn:
            return None
        return {
            "delta_theta_cone_deg": self._create_metric_comparison(
                np.array([lap.delta_theta_cone_deg for lap in all_laps]),
                benchmark.turn.delta_theta_cone_deg, user_pct, cohort_pct, "delta_theta_cone_deg"),
            "delta_theta_chair_deg": self._create_metric_comparison(
                np.array([lap.delta_theta_chair_deg for lap in all_laps]),
                benchmark.turn.delta_theta_chair_deg, user_pct, cohort_pct, "delta_theta_chair_deg"),
        }


cohort_benchmark_service = CohortBenchmarkService()
