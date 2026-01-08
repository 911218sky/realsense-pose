"""族群基準分析 API 路由。

提供族群使用者查詢、基準值計算、查詢與個人比對功能。
"""

from typing import List, Optional

from fastapi import APIRouter, Body, HTTPException

from api.utils.cache import redis_cache
from db.mongo.models import CohortBenchmark, PercentileStatsEmbed
from logger import setup_logger

from .models import (
    BenchmarkResponse,
    CalculateBenchmarkRequest,
    CohortListItem,
    CohortListResponse,
    CohortUsersRequest,
    CohortUsersResponse,
    CompareRequest,
    ComparisonResult,
    PercentileStats,
    LapTimeBenchmark,
    GaitBenchmark,
    SpeedDistanceBenchmark,
    TurnBenchmark,
)
from .service import cohort_benchmark_service

router = APIRouter(
    prefix="/cohort-benchmark",
    tags=["cohort-benchmark"],
)

logger = setup_logger("api.v1.cohort_benchmark")


def _convert_percentile_stats(embed: Optional[PercentileStatsEmbed]) -> Optional[PercentileStats]:
    """轉換 PercentileStatsEmbed 為 Pydantic 模型。"""
    if embed is None:
        return None
    return PercentileStats(
        p10=embed.p10,
        p25=embed.p25,
        p50=embed.p50,
        p75=embed.p75,
        p90=embed.p90,
        mean=embed.mean,
        std=embed.std,
        count=embed.count,
    )


def _convert_benchmark_to_response(benchmark: CohortBenchmark) -> BenchmarkResponse:
    """轉換 CohortBenchmark 文件為 API 回應模型。"""
    lap_time = None
    if benchmark.lap_time:
        lap_time = LapTimeBenchmark(
            dur_total=_convert_percentile_stats(benchmark.lap_time.dur_total),
            dur_stand=_convert_percentile_stats(benchmark.lap_time.dur_stand),
            dur_to_cone=_convert_percentile_stats(benchmark.lap_time.dur_to_cone),
            dur_cone_turn=_convert_percentile_stats(benchmark.lap_time.dur_cone_turn),
            dur_return=_convert_percentile_stats(benchmark.lap_time.dur_return),
            dur_turn_to_sit=_convert_percentile_stats(benchmark.lap_time.dur_turn_to_sit),
            dur_sit=_convert_percentile_stats(benchmark.lap_time.dur_sit),
        )

    gait = None
    if benchmark.gait:
        gait = GaitBenchmark(
            spm=_convert_percentile_stats(benchmark.gait.spm),
            mean_step_len=_convert_percentile_stats(benchmark.gait.mean_step_len),
            l_swing_pct=_convert_percentile_stats(benchmark.gait.l_swing_pct),
            r_swing_pct=_convert_percentile_stats(benchmark.gait.r_swing_pct),
            l_stance_s=_convert_percentile_stats(benchmark.gait.l_stance_s),
            r_stance_s=_convert_percentile_stats(benchmark.gait.r_stance_s),
        )

    speed_distance = None
    if benchmark.speed_distance:
        speed_distance = SpeedDistanceBenchmark(
            speed_mps=_convert_percentile_stats(benchmark.speed_distance.speed_mps),
            dist_lap_path_m=_convert_percentile_stats(benchmark.speed_distance.dist_lap_path_m),
            dist_outbound_m=_convert_percentile_stats(benchmark.speed_distance.dist_outbound_m),
            dist_return_m=_convert_percentile_stats(benchmark.speed_distance.dist_return_m),
            dist_cone_turn_m=_convert_percentile_stats(benchmark.speed_distance.dist_cone_turn_m),
        )

    turn = None
    if benchmark.turn:
        turn = TurnBenchmark(
            delta_theta_cone_deg=_convert_percentile_stats(benchmark.turn.delta_theta_cone_deg),
            delta_theta_chair_deg=_convert_percentile_stats(benchmark.turn.delta_theta_chair_deg),
            turn_cone_dir_ratio=benchmark.turn.turn_cone_dir_ratio or {},
            turn_chair_dir_ratio=benchmark.turn.turn_chair_dir_ratio or {},
        )

    return BenchmarkResponse(
        cohort_name=benchmark.cohort_name,
        version=benchmark.version or 1,
        calculated_at=benchmark.calculated_at,
        user_count=benchmark.user_count or 0,
        session_count=benchmark.session_count or 0,
        lap_count=benchmark.lap_count or 0,
        lap_time=lap_time,
        gait=gait,
        speed_distance=speed_distance,
        turn=turn,
    )


@router.post("/users", response_model=CohortUsersResponse)
@redis_cache(expire=30)
async def get_cohort_users(
    request: CohortUsersRequest = Body(...),
) -> CohortUsersResponse:
    """查詢族群使用者。

    根據族群名稱列表查詢使用者，支援聯集或交集查詢。

    - **cohort_names**: 族群名稱列表
    - **intersection**: True=取交集（同時屬於所有族群），False=取聯集（屬於任一族群）
    """
    try:
        users = await cohort_benchmark_service.get_cohort_users(
            cohort_names=request.cohort_names,
            intersection=request.intersection,
        )

        return CohortUsersResponse(
            cohort_names=request.cohort_names,
            intersection=request.intersection,
            user_codes=[u.user_code for u in users],
            count=len(users),
        )
    except Exception as e:
        logger.error(f"Failed to get cohort users: {e}")
        raise HTTPException(status_code=500, detail=f"查詢族群使用者失敗: {e}")


@router.post("/calculate", response_model=BenchmarkResponse)
async def calculate_benchmark(
    request: CalculateBenchmarkRequest = Body(...),
) -> BenchmarkResponse:
    """計算族群基準值。

    觸發指定族群的基準值計算，包含圈數時間、步態、速度距離、轉向等指標。

    - cohort_name: 族群名稱
    - force_recalculate: 是否強制重新計算（即使已有基準值）
    """
    try:
        benchmark = await cohort_benchmark_service.calculate_benchmark(
            cohort_name=request.cohort_name,
            force_recalculate=request.force_recalculate,
        )
        # 計算基準值後，需要更新族群使用者數量
        return _convert_benchmark_to_response(benchmark)
    except Exception as e:
        logger.error(f"Failed to calculate benchmark for {request.cohort_name}: {e}")
        raise HTTPException(status_code=500, detail=f"計算基準值失敗: {e}")


@router.get("/list", response_model=CohortListResponse)
@redis_cache(expire=30)
async def list_cohorts() -> CohortListResponse:
    """列出所有已計算基準值的族群。

    回傳所有已完成基準值計算的族群名稱列表。
    """
    benchmarks = await CohortBenchmark.find(
        CohortBenchmark.status == "completed"
    ).to_list()

    cohorts = []
    for b in benchmarks:
        cohorts.append(CohortListItem(
            cohort_name=b.cohort_name,
            user_count=b.user_count or 0,
            session_count=b.session_count or 0,
            lap_count=b.lap_count or 0,
            calculated_at=b.calculated_at,
            version=b.version or 1,
        ))

    return CohortListResponse(cohorts=cohorts, count=len(cohorts))


@router.get("/{cohort_name}", response_model=BenchmarkResponse)
async def get_benchmark(
    cohort_name: str,
) -> BenchmarkResponse:
    """查詢族群基準值。

    查詢指定族群的已計算基準值。

    - cohort_name: 族群名稱
    """
    benchmark = await CohortBenchmark.find_one(
        CohortBenchmark.cohort_name == cohort_name
    )

    if not benchmark:
        raise HTTPException(
            status_code=404,
            detail=f"族群 {cohort_name} 的基準值不存在",
        )

    if benchmark.status != "completed":
        raise HTTPException(
            status_code=400,
            detail=f"族群 {cohort_name} 的基準值尚未計算完成（狀態: {benchmark.status}）",
        )

    return _convert_benchmark_to_response(benchmark)


@router.post("/delete")
async def delete_benchmarks(
    cohort_names: List[str] = Body(..., embed=True),
) -> dict:
    """刪除族群基準值（支援單一或批量）。

    - cohort_names: 要刪除的族群名稱列表
    """
    deleted = []
    not_found = []

    for name in cohort_names:
        benchmark = await CohortBenchmark.find_one(
            CohortBenchmark.cohort_name == name
        )
        if benchmark:
            await benchmark.delete()
            deleted.append(name)
            logger.info(f"Deleted benchmark for cohort: {name}")
        else:
            not_found.append(name)

    return {
        "ok": True,
        "deleted": deleted,
        "deleted_count": len(deleted),
        "not_found": not_found if not_found else None,
    }


@router.post("/compare", response_model=ComparisonResult)
@redis_cache(expire=30)
async def compare_user_to_benchmark(
    request: CompareRequest = Body(...),
) -> ComparisonResult:
    """個人與基準比對。

    將 session 的數據與族群基準值進行比對，計算各指標的百分位統計並比較。

    - **session_name**: session 名稱
    - **cohort_name**: 要比對的族群名稱
    """
    try:
        result = await cohort_benchmark_service.compare_user_to_benchmark(
            session_name=request.session_name,
            cohort_name=request.cohort_name,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to compare session {request.session_name}: {e}")
        raise HTTPException(status_code=500, detail=f"比對失敗: {e}")
