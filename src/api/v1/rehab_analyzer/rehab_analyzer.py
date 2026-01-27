from typing import Any, Optional, Union
import numpy as np

from fastapi import APIRouter, Body, HTTPException

from api.utils.cache import redis_cache
from api.utils.array_codec import pack_1d_f32_zlib_b64, pack_1d_u16_le_zlib_b64
from api.v1.rehab_analyzer.models import (
    MultiFFTFromSeriesRequest,
    MultiFFTFromSeriesResponse,
    MinutelyCadenceStepLengthBarsRequest,
    MinutelyCadenceStepLengthBarsResponse,
    PerLapOffsetRequest,
    PerLapOffsetResponse,
    SpatialSpectrumRequest,
    SpatialSpectrumResponse,
    StageDurationsRequest,
    StageDurationsResponse,
    YHeightDiffRequest,
    YHeightDiffResponse,
    SpeedHeatmapRequest,
    SpeedHeatmapResponse,
    TrajectoryPayloadRequest,
    TrajectoryPayloadResponse,
    SwingInfoHeatmapRequest,
    SwingInfoHeatmapResponse,
    MinutelyTrendRequest,
    MinutelyTrendResponse,
    GaitCyclePhasesRequest,
    GaitCyclePhasesResponse,
)
from api.v1.rehab_analyzer.utils import resolve_session_npy_path, select_peak_indices
from config import load_config
from logger import setup_logger
from rehab_analyzer.rehab_analyzer import RehabilitationSessionAnalyzer
from rehab_analyzer.entities import DetectLapsResult, OffsetFFTResult, OffsetFFTResult

default_config = load_config(mode="analyzer")

router = APIRouter(
    prefix="/rehab-analyzer",
    tags=["rehab-analyzer"]
)

logger = setup_logger("api.v1.rehab_analyzer")

@router.post("/stage_durations", response_model=StageDurationsResponse)
@redis_cache(expire=30)
async def stage_durations(
    session_name: str,
    config: Optional[StageDurationsRequest] = Body(None),
) -> StageDurationsResponse:
    config = config or StageDurationsRequest()

    npy_path = await resolve_session_npy_path(session_name) if session_name else None

    try:
        # 開始分析
        analyzer = RehabilitationSessionAnalyzer(npy_path=npy_path)
        det: DetectLapsResult = analyzer.detect_laps_auto(
            projection=config.projection,
            smooth_window_s=config.smooth_window_s,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"stage durations analysis failed: {e}")

    labels = [
        "1 Stand up",
        "2 Walk to cone",
        "3 Turn at cone",
        "4 Walk back",
        "5 Align to sit",
        "6 Sit down",
    ]
    keys = [
        "dur_stand",
        "dur_to_cone",
        "dur_cone_turn",
        "dur_return",
        "dur_turn_to_sit",
        "dur_sit",
    ]
    meters_idx = {
        2: "dist_outbound_m",          # 2 Walk to cone
        3: "dist_cone_turn_path_m",    # 3 Turn at cone
        4: "dist_return_m",            # 4 Walk back
        5: "dist_turn_to_sit_m",       # 5 Align to sit
    }

    laps_payload = []
    for idx, lap in enumerate(det.laps, start=1):
        stages = []
        for stage_idx, (label, key) in enumerate(zip(labels, keys), start=1):
            entry = {
                "label": label,
                "duration_s": float(getattr(lap, key, 0.0)),
            }
            if meters_idx.get(stage_idx):
                entry["distance_m"] = float(getattr(lap, meters_idx[stage_idx], 0.0))
            stages.append(entry)

        laps_payload.append(
            {
                "lap_index": idx,
                "ts_start": float(lap.ts_start),
                "ts_end": float(lap.ts_end),
                "total_duration_s": float(lap.dur_total), 
                "total_distance_m": float(lap.dist_lap_path_m),
                "lap_direction": str(lap.lap_direction),
                "stage_durations": stages,
            }
        )
        
    result = {"laps": laps_payload}

    return result

@router.post(
    "/per_lap_offset",
    response_model=PerLapOffsetResponse,
    response_model_exclude_none=True,
)
@redis_cache(expire=30)
async def per_lap_offset(
    session_name: str,
    config: Optional[PerLapOffsetRequest] = Body(None),
) -> PerLapOffsetResponse:
    """
    與 visualizer.save_per_lap_offset 使用相同公式計算每圈 lateral offset / heading。
    回傳 JSON 給前端畫兩個子圖用。
    """
    
    config = config or PerLapOffsetRequest()

    npy_path = await resolve_session_npy_path(session_name)

    try:
        # 建立 analyzer，做圈數偵測（與 visualizer.save_per_lap_offset 相同）
        analyzer = RehabilitationSessionAnalyzer(npy_path=npy_path)
        det: DetectLapsResult = analyzer.detect_laps_auto(
            projection=config.projection,
            smooth_window_s=config.smooth_window_s,
        )
        laps = det.laps
        if not laps:
            raise ValueError("no laps detected")

        # 取得左右髖點、中心點 C2（同 visualizer）
        fps = float(analyzer._estimate_fps())
        smooth_window = max(1, int(round(config.smooth_window_s * fps)))
        l2, r2, _ = analyzer._compute_hip_points(
            projection=config.projection,
            smooth_window=smooth_window,
        )
        c2 = (l2 + r2) / 2.0

        # lateral offset 全程序列（raw + smooth）
        chair_pos = np.array(det.chair_pos, dtype=float)
        cone_pos = np.array(det.cone_pos, dtype=float)
        lat_raw_all, lat_smooth_all = analyzer._lateral_offset_series(
            c2=c2,
            chair_pos=np.array(chair_pos),
            cone_pos=np.array(cone_pos),
            k_smooth=config.k_smooth,
        )

        # pelvis heading（解包後角度），整段 theta_all
        theta_all = analyzer.compute_pelvis_heading_unwrapped(L2=l2, R2=r2)
        t_all = analyzer.t.astype(float)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"per_lap_offset analysis failed: {e}",
        )


    # 處理每一圈
    laps_payload = []

    for lap_idx, lap in enumerate(laps, start=1):
        start_idx = int(lap.idx_start)
        end_idx = int(lap.idx_end)

        def rel(i: int) -> int:
            return int(i - start_idx)

        # 這一圈的 time / lat / theta（相對圈起點）
        t_rel = t_all[start_idx : end_idx + 1]
        lat_rel = lat_smooth_all[start_idx : end_idx + 1]
        lat_raw_rel = lat_raw_all[start_idx : end_idx + 1]
        theta_rel = theta_all[start_idx : end_idx + 1] - theta_all[start_idx]

        n_rel = len(t_rel)

        # 轉彎區段 index（相對於圈起點）
        tc_start_rel = rel(lap.idx_turn_cone_start)
        tc_end_rel = rel(lap.idx_turn_cone_end)
        th_start_rel = rel(lap.idx_turn_chair_start)
        th_end_rel = rel(lap.idx_turn_chair_end)

        # 走路區段：離開椅子 -> 再次進入椅區
        walk_start_rel = rel(lap.idx_leave_chair)
        walk_end_rel = rel(lap.idx_reenter_chair)

        # 夾在合法範圍內，確保 index 不會超出
        walk_start_rel = max(0, min(walk_start_rel, n_rel - 1))
        walk_end_rel = max(0, min(walk_end_rel, n_rel - 1))
        if walk_end_rel < walk_start_rel:
            walk_start_rel, walk_end_rel = walk_end_rel, walk_start_rel

        laps_payload.append(
            {
                "lap_index": lap_idx,
                "lap_direction": str(lap.lap_direction),
                # 時間與訊號（compact: float32+zlib+b64）
                "time_s_f32_zlib_b64": pack_1d_f32_zlib_b64(t_rel),
                "lat_raw_f32_zlib_b64": pack_1d_f32_zlib_b64(lat_raw_rel),
                "lat_smooth_f32_zlib_b64": pack_1d_f32_zlib_b64(lat_rel),
                "theta_deg_f32_zlib_b64": pack_1d_f32_zlib_b64(theta_rel),
                # 區段 index（相對於本圈起點）
                "turn_regions": {
                    "cone": {
                        "start_idx": int(tc_start_rel),
                        "end_idx": int(tc_end_rel),
                    },
                    "chair": {
                        "start_idx": int(th_start_rel),
                        "end_idx": int(th_end_rel),
                    },
                },
                "walk_region": {
                    "start_idx": int(walk_start_rel),
                    "end_idx": int(walk_end_rel),
                },
            }
        )

    return {"laps": laps_payload}

@router.post(
    "/minutely_cadence_step_length_bars",
    response_model=MinutelyCadenceStepLengthBarsResponse,
)
@redis_cache(expire=30)
async def minutely_cadence_step_length_bars(
    session_name: str,
    config: Optional[MinutelyCadenceStepLengthBarsRequest] = Body(None),
) -> MinutelyCadenceStepLengthBarsResponse:
    """
    回傳每分鐘步頻（cadence）與步長（step length）的長條圖資料。
    """
    
    config = config or MinutelyCadenceStepLengthBarsRequest()

    npy_path = await resolve_session_npy_path(session_name)

    try:
        analyzer = RehabilitationSessionAnalyzer(npy_path=npy_path)
        summary = analyzer.compute_gait_summary(
            smooth_window_s=config.smooth_window_s,
            projection=config.projection,
        )
        per_interval = summary.per_interval or []
        if not per_interval:
            raise ValueError("沒有每分鐘區間可視覺化（per_interval 為空）。")
        if config.max_minutes is not None:
            max_minutes = max(1, int(config.max_minutes))
            per_interval = per_interval[:max_minutes]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"minutely_cadence_step_length_bars analysis failed: {e}",
        )

    minutes = list(range(1, len(per_interval) + 1))
    cadence_spm = [float(interval.spm) for interval in per_interval]
    step_length_m = [float(interval.mean_step_len_m) for interval in per_interval]
    step_counts = [
        int(interval.left_step_count + interval.right_step_count)
        for interval in per_interval
    ]

    return {
        "minutes": minutes,
        "cadence_spm": cadence_spm,
        "step_length_m": step_length_m,
        "step_counts": step_counts,
    }

@router.post("/y_height_diff", response_model=YHeightDiffResponse)
@redis_cache(expire=30)
async def y_height_diff(
    session_name: str,
    config: Optional[YHeightDiffRequest] = Body(None),
) -> YHeightDiffResponse:
    """
    回傳左右關節的 Y 高度與差值序列，給前端直接畫三條線用。
    """
    
    config = config or YHeightDiffRequest()

    npy_path = await resolve_session_npy_path(session_name)

    try:
        analyzer = RehabilitationSessionAnalyzer(npy_path=npy_path)
        fps = float(analyzer._estimate_fps())
        smooth_window = max(1, int(round(config.smooth_window_s * fps)))
        t, series = analyzer.compute_y_heigh(
            joints=[config.left_joint, config.right_joint],
            smooth_window=smooth_window,
            shift_to_zero=config.shift_to_zero,
        )

        if len(series) != 2:
            raise ValueError("需要剛好兩條關節高度序列（左、右）。")

        left, right = series
        diff = left - right
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"y_height_diff analysis failed: {e}"
        )
    
        
    return {
        "time_s_f32_zlib_b64": pack_1d_f32_zlib_b64(t),
        "left_f32_zlib_b64": pack_1d_f32_zlib_b64(left),
        "right_f32_zlib_b64": pack_1d_f32_zlib_b64(right),
        "diff_f32_zlib_b64": pack_1d_f32_zlib_b64(diff),
        "left_joint": config.left_joint,
        "right_joint": config.right_joint,
    }


@router.post("/speed_heatmap", response_model=SpeedHeatmapResponse)
@redis_cache(expire=30)
async def speed_heatmap(
    session_name: str,
    config: Optional[SpeedHeatmapRequest] = Body(None),
) -> SpeedHeatmapResponse:
    """
    每圈速度時空熱圖
    """
    
    config = config or SpeedHeatmapRequest()

    npy_path = await resolve_session_npy_path(session_name)

    try:
        analyzer = RehabilitationSessionAnalyzer(npy_path=npy_path)
        fps = float(analyzer._estimate_fps())
        smooth_window = max(1, int(round(config.smooth_window_s * fps)))
        l2, r2, _ = analyzer._compute_hip_points(
            projection=config.projection,
            smooth_window=smooth_window,
        )
        c2 = (l2 + r2) / 2.0
        _, speed, _ = analyzer._speed_series(c2)

        det = analyzer.detect_laps_auto(
            projection=config.projection,
            smooth_window_s=config.smooth_window_s,
            flat_frac=config.flat_frac,
            min_v_abs=config.min_v_abs,
        )
        laps = det.laps
        if not laps:
            raise ValueError("沒有圈數可視覺化。")

        width = int(max(50, config.width))
        num_laps = len(laps)
        mat = np.full((num_laps, width), np.nan, dtype=float)
        marks: list[dict[str, Any]] = []

        def _safe_frac(idx: int, start_idx: int, denom: int) -> float:
            """把 session index 轉成相對圈長的 0~1 位置。"""
            if denom <= 0:
                return 0.0
            f = (float(idx) - float(start_idx)) / float(denom)
            # 避免極端 index 造成前端畫圖超出範圍
            return float(np.clip(f, 0.0, 1.0))

        def resample_1d(arr: np.ndarray, i0: int, i1: int, m: int) -> np.ndarray:
            """以索引為自變數，將 arr[i0:i1] 線性插值重採樣成 m 個點（含端點）。"""
            i0 = max(0, int(i0))
            i1 = max(0, int(i1))
            if i1 <= i0:
                raise ValueError("i1 必須大於 i0。")
            idx_src = np.linspace(i0, i1, num=(i1 - i0 + 1))
            idx_dst = np.linspace(i0, i1, num=m)
            return np.interp(idx_dst, idx_src, arr[i0 : i1 + 1])

        for row, lap in enumerate(laps):
            start_idx = int(lap.idx_onset_end)
            end_idx = int(lap.idx_chair_sit_end)
            if end_idx <= start_idx:
                continue

            mat[row] = resample_1d(speed, start_idx, end_idx, width)
            denom = max(1, end_idx - start_idx)
            cone_start_idx = int(lap.idx_turn_cone_start)
            cone_end_idx = int(lap.idx_turn_cone_end)
            chair_start_idx = int(lap.idx_turn_chair_start)
            chair_end_idx = int(lap.idx_turn_chair_end)

            a = _safe_frac(cone_start_idx, start_idx, denom)
            b = _safe_frac(cone_end_idx, start_idx, denom)
            c = _safe_frac(chair_start_idx, start_idx, denom)
            d = _safe_frac(chair_end_idx, start_idx, denom)
            marks.append(
                {
                    "lap_index": row + 1,
                    "lap_direction": str(lap.lap_direction),
                    "cone_start_frac": float(a),
                    "cone_end_frac": float(b),
                    "chair_start_frac": float(c),
                    "chair_end_frac": float(d),
                }
            )

        finite_vals = mat[np.isfinite(mat)]
        auto_vmin = float(np.min(finite_vals)) if finite_vals.size else None
        auto_vmax = float(np.max(finite_vals)) if finite_vals.size else None
        vmin = config.vmin if config.vmin is not None else auto_vmin
        vmax = config.vmax if config.vmax is not None else auto_vmax

        heatmap = [
            [float(x) if np.isfinite(x) else None for x in row] for row in mat
        ]

        return {
            "width": width,
            "heatmap": heatmap,
            "marks": marks,
            "vmin": vmin,
            "vmax": vmax,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"speed_heatmap analysis failed: {e}"
        )


@router.post("/swing_info_heatmap", response_model=SwingInfoHeatmapResponse)
@redis_cache(expire=30)
async def swing_info_heatmap(
    session_name: str,
    config: Optional[SwingInfoHeatmapRequest] = Body(None),
) -> SwingInfoHeatmapResponse:
    """
    對應 visualizer.save_swing_info_heatmap 的資料版：
    回傳每分鐘區間的 Left/Right swing% 與 swing 秒數矩陣，供前端自行渲染熱力圖。
    """
    config = config or SwingInfoHeatmapRequest()
    npy_path = await resolve_session_npy_path(session_name)

    try:
        analyzer = RehabilitationSessionAnalyzer(npy_path=npy_path)
        summary = analyzer.compute_gait_summary(
            smooth_window_s=config.smooth_window_s,
            projection=config.projection,
            flat_frac=config.flat_frac,
            min_v_abs=config.min_v_abs,
        )
        per_interval = summary.per_interval or []
        if not per_interval:
            raise ValueError("沒有每分鐘區間可視覺化（per_interval 為空）。")
        if config.max_minutes is not None:
            per_interval = per_interval[: max(1, int(config.max_minutes))]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"swing_info_heatmap analysis failed: {e}",
        )

    L = len(per_interval)
    H_pct = np.full((2, L), np.nan, dtype=float)
    H_sec = np.full((2, L), np.nan, dtype=float)

    for j, interval in enumerate(per_interval):
        H_pct[0, j] = float(interval.l_swing_pct_mean)
        H_pct[1, j] = float(interval.r_swing_pct_mean)
        H_sec[0, j] = float(interval.l_swing_s_mean)
        H_sec[1, j] = float(interval.r_swing_s_mean)

    return {
        "minutes": list(range(1, L + 1)),
        "swing_pct": H_pct,
        "swing_s": H_sec,
    }


@router.post("/minutely_trend", response_model=MinutelyTrendResponse)
@redis_cache(expire=30)
async def minutely_trend(
    session_name: str,
    config: Optional[MinutelyTrendRequest] = Body(None),
) -> MinutelyTrendResponse:
    """
    回傳每分鐘速度與圈數趨勢資料，供前端自行渲染趨勢圖。
    
    包含：
    - 每分鐘平均速度
    - 每分鐘完成圈數
    - 每分鐘包含的圈數索引列表
    """
    config = config or MinutelyTrendRequest()
    npy_path = await resolve_session_npy_path(session_name)

    try:
        analyzer = RehabilitationSessionAnalyzer(npy_path=npy_path)
        det = analyzer.detect_laps_auto(
            projection=config.projection,
            smooth_window_s=config.smooth_window_s,
            flat_frac=config.flat_frac,
            min_v_abs=config.min_v_abs,
        )
        laps = det.laps
        if not laps:
            raise ValueError("沒有圈數可視覺化（laps 為空）。")

        t0 = float(laps[0].ts_start)
        last_t = float(laps[-1].ts_end)
        total_minutes = max(1, int(np.ceil((last_t - t0) / 60.0)))
        
        # 限制輸出分鐘數
        if config.max_minutes is not None:
            total_minutes = min(total_minutes, max(1, int(config.max_minutes)))
        
        # 統計每分鐘數據
        minute_speeds: list[list[float]] = [[] for _ in range(total_minutes)]
        minute_lap_counts: list[int] = [0] * total_minutes
        minute_lap_indices: list[list[int]] = [[] for _ in range(total_minutes)]
        
        for lap_idx, lap in enumerate(laps, start=1):
            m = min(int((lap.ts_start - t0) / 60.0), total_minutes - 1)
            m = max(0, m)
            if lap.dur_total > 0 and lap.dist_lap_path_m > 0:
                minute_speeds[m].append(lap.dist_lap_path_m / lap.dur_total)
            minute_lap_counts[m] += 1
            minute_lap_indices[m].append(lap_idx)
        
        avg_speeds = [
            float(np.mean(s)) if s else None 
            for s in minute_speeds
        ]
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"minutely_trend analysis failed: {e}",
        )
    
    return {
        "minutes": list(range(1, total_minutes + 1)),
        "avg_speeds": avg_speeds,
        "lap_counts": minute_lap_counts,
        "lap_details": minute_lap_indices,
    }


@router.post("/spatial_spectrum", response_model=SpatialSpectrumResponse)
@redis_cache(expire=30)
async def spatial_spectrum(
    session_name: str,
    config: Optional[SpatialSpectrumRequest] = Body(None),
) -> SpatialSpectrumResponse:
    """
    回傳 X(Z) / Y(Z) 的空間頻譜（dB，相對各曲線最大值）與峰值位置。
    """
    
    config = config or SpatialSpectrumRequest()
    npy_path = await resolve_session_npy_path(session_name)

    try:
        analyzer = RehabilitationSessionAnalyzer(npy_path=npy_path)
        payload: list[dict[str, Any]] = []

        for p in config.pair:
            f, spec = analyzer.compute_spatial_spectrum_zind(
                pair=p,
                k_smooth=config.k_smooth
            )
            f = np.asarray(f, dtype=float)
            spec = np.asarray(spec, dtype=float)

            eps = np.finfo(float).tiny
            max_spec = float(spec.max()) if spec.size else 0.0
            if max_spec <= 0.0:
                spec_db = np.full_like(spec, -300.0)
            else:
                spec_db = 10.0 * np.log10(np.maximum(spec / max_spec, eps))

            # 選擇峰值索引
            peak_idx = select_peak_indices(
                f,
                spec_db,
                max_peaks=config.top_k,
                min_peak_distance_ratio=config.min_peak_distance_ratio,
                min_db=config.min_db,
                min_freq=config.min_freq,
            )

            peaks: list[dict[str, float]] = [
                {"freq": float(f[i]), "db": float(spec_db[i])} for i in peak_idx
            ]

            payload.append(
                {
                    "pair": p,
                    "freq_f32_zlib_b64": pack_1d_f32_zlib_b64(f),
                    "psd_db_f32_zlib_b64": pack_1d_f32_zlib_b64(spec_db),
                    "peaks": peaks,
                }
            )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"spatial_spectrum analysis failed: {e}"
        )

    return {"spectrums": payload}


@router.post(
    "/multi_fft_from_series",
    response_model=MultiFFTFromSeriesResponse,
)
@redis_cache(expire=30)
async def multi_fft_from_series(
    session_name: str,
    config: Optional[MultiFFTFromSeriesRequest] = Body(None),
) -> MultiFFTFromSeriesResponse:
    """
    回傳多條關節序列的 FFT/PSD（dB，相對全域最大），含峰值列表，方便前端畫頻譜。
    """
    
    config = config or MultiFFTFromSeriesRequest()

    if not config.joints:
        raise HTTPException(status_code=400, detail="joints 不能為空")

    # 解析 component -> 對應軸索引
    component = config.component.lower()
    match component:
        case "x":
            component_idx = 0
        case "y":
            component_idx = 1
        case "z":
            component_idx = 2
        case _:
            raise HTTPException(
                status_code=400, detail="component 必須是 x / y / z"
            )

    npy_path = await resolve_session_npy_path(session_name)

    # 從關節序列中計算平均值的輔助函數（支援單一或群組關節）
    def _series_from_joint_spec(
        analyzer: RehabilitationSessionAnalyzer,
        spec: Union[int, str, list, tuple, np.ndarray],
    ) -> np.ndarray:
        # 若為群組指定，先轉索引後取平均
        if isinstance(spec, (list, tuple, np.ndarray)):
            # 群組不可為空
            if not spec:
                raise ValueError("joint group 不能是空的。")
            # 將每個關節標識轉成索引
            idxs = [analyzer.resolve_joint(j) for j in spec]
            # 取出指定軸的資料並在關節維度做平均
            arr_group = analyzer.arr[:, idxs, component_idx]
            return np.mean(arr_group, axis=1)
        # 單一關節，轉索引後取該軸序列
        idx = analyzer.resolve_joint(spec)
        return analyzer.arr[:, idx, component_idx]

    try:
        analyzer = RehabilitationSessionAnalyzer(npy_path=npy_path)
        results = []
        max_power = 0.0

        # 先跑 FFT，找出全域最大功率供 dB 正規化
        fft_outputs: list[OffsetFFTResult] = []
        for joint_spec in config.joints:
            series = _series_from_joint_spec(analyzer, joint_spec)
            res = analyzer.compute_lateral_offset_fft(
                lat=np.asarray(series, dtype=float),
                t=analyzer.t,
            )
            fft_outputs.append(res)
            if res.Pxx.size:
                pmax = float(np.nanmax(res.Pxx))
                if np.isfinite(pmax):
                    max_power = max(max_power, pmax)

        eps = np.finfo(float).tiny
        if not np.isfinite(max_power) or max_power <= 0.0:
            max_power = 1.0

        for res in fft_outputs:
            f = np.asarray(res.f, dtype=float)
            Pxx = np.asarray(res.Pxx, dtype=float)
            
            # 避免全部都是 0 或 NaN，空資料時直接回報空頻譜
            if f.size == 0 or Pxx.size == 0:
                results.append(
                    {
                        "joint_spec": config.joints[len(results)],
                        "freq_hz_f32_zlib_b64": pack_1d_f32_zlib_b64(f),
                        "psd_db_f32_zlib_b64": pack_1d_f32_zlib_b64(np.asarray([], dtype=np.float32)),
                        "peaks": [],
                    }
                )
                continue

            # 把 PSD 轉成 dB（相對全域最大值）
            psd_db = 10.0 * np.log10(np.maximum(Pxx / max_power, eps))
            peak_idx = select_peak_indices(
                f,
                psd_db,
                max_peaks=config.top_k,
                min_peak_distance_ratio=config.min_peak_distance_ratio,
                min_db=config.min_db,
                min_freq=config.min_freq,
                ensure_global_peak=True,
            )
            
            peaks = [
                {"freq_hz": float(f[i]), "db": float(psd_db[i])} for i in peak_idx
            ]

            results.append(
                {
                    "joint_spec": config.joints[len(results)],
                    "freq_hz_f32_zlib_b64": pack_1d_f32_zlib_b64(f),
                    "psd_db_f32_zlib_b64": pack_1d_f32_zlib_b64(psd_db),
                    # 頻譜峰值列表
                    "peaks": peaks,
                }
            )
            
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"multi_fft_from_series analysis failed: {e}"
        )   

    return {
        "component": component,
        "series": results,
    }


@router.post("/trajectory_payload", response_model=TrajectoryPayloadResponse)
@redis_cache(expire=30)
async def trajectory_payload(
    session_name: str,
    config: Optional[TrajectoryPayloadRequest] = Body(None),
) -> TrajectoryPayloadResponse:
    """
    回傳 top-down 軌跡動畫資料包（給前端自行渲染），取代 `save_trajectory_video` 的 mp4 輸出。

    包含：
    - 座標：量化為 uint16（用 bounds 做 0..65535 mapping），zlib 壓縮後 base64
    - 場景：椅子/錐桶（也用同一套 bounds 量化為 uint16）與半徑
    - 圈段：每圈在 payload frames 中的 [start_k, end_k] 與轉身點 marker 的 k
    - meta：fps_out + bounds + encoding + n_frames

    不回傳（因為前端可推導/重建）：
    - frame_idx / time_s / speed_mps / lap_index / marker_xy 等
    """
    config = config or TrajectoryPayloadRequest()
    npy_path = await resolve_session_npy_path(session_name)

    try:
        analyzer = RehabilitationSessionAnalyzer(npy_path=npy_path)

        fps_in = float(analyzer._estimate_fps())
        smooth_window = max(1, int(round(config.smooth_window_s * fps_in)))

        l2, r2, valid = analyzer._compute_hip_points(
            projection=config.projection,
            smooth_window=smooth_window,
            left_joint=config.left_joint,
            right_joint=config.right_joint,
        )
        c2 = (l2 + r2) / 2.0
        num_frames = int(c2.shape[0])
        if not np.any(valid):
            raise ValueError("沒有有效的關節座標。")

        det: DetectLapsResult = analyzer.detect_laps_auto(
            projection=config.projection,
            smooth_window_s=config.smooth_window_s,
            flat_frac=config.flat_frac,
            min_v_abs=config.min_v_abs,
        )

        chair_pos = np.array(det.chair_pos, dtype=float)
        cone_pos = np.array(det.cone_pos, dtype=float)
        rC = float(det.r_chair_enter)
        rK = float(det.r_cone_enter)

        # bounds：以所有有效點與椅、錐位置決定
        all_points = np.vstack(
            [l2[valid], r2[valid], chair_pos[None, :], cone_pos[None, :]]
        )
        xmin, ymin = np.min(all_points, axis=0)
        xmax, ymax = np.max(all_points, axis=0)
        span = max(float(xmax - xmin), float(ymax - ymin), 1e-6)
        pad_abs = float(config.pad_scale) * span
        xmin -= pad_abs
        xmax += pad_abs
        ymin -= pad_abs
        ymax += pad_abs

        # 旋轉 180°：椅/錐上下互換
        if config.rotate_180:
            # 旋轉中心
            cx = 0.5 * (xmin + xmax)
            cy = 0.5 * (ymin + ymax)

            # 旋轉座標
            def _rotate_coords(arr: np.ndarray) -> np.ndarray:
                rotated = np.array(arr, dtype=float, copy=True)
                rotated[..., 0] = 2 * cx - rotated[..., 0]
                rotated[..., 1] = 2 * cy - rotated[..., 1]
                return rotated

            l2 = _rotate_coords(l2)
            r2 = _rotate_coords(r2)
            chair_pos = _rotate_coords(chair_pos)
            cone_pos = _rotate_coords(cone_pos)

        # 下採樣：和 visualizer 保持一致
        stride = max(1, int(round((fps_in * float(config.speed)) / float(config.fps_out))))
        idxs_full = np.arange(0, num_frames, stride, dtype=int)
        idxs_full = idxs_full[valid[idxs_full]]
        if idxs_full.size < 2:
            raise ValueError("有效影格太少，無法產生 trajectory payload。")
        if int(config.frame_jump) > 1:
            idxs_full = idxs_full[:: int(config.frame_jump)]

        l2_sub = l2[idxs_full]
        r2_sub = r2[idxs_full]

        n_frames = int(idxs_full.size)
        idxs_full_i64 = idxs_full.astype(np.int64, copy=False)

        # 量化到 uint16（用 bounds 做線性 mapping：0..65535）
        dx = float(xmax - xmin) if float(xmax - xmin) > 1e-9 else 1e-9
        dy = float(ymax - ymin) if float(ymax - ymin) > 1e-9 else 1e-9

        # 量化到 uint16
        def _quantize_u16(arr2: np.ndarray) -> np.ndarray:
            a = np.asarray(arr2, dtype=float)
            qx = np.clip((a[:, 0] - float(xmin)) / dx, 0.0, 1.0)
            qy = np.clip((a[:, 1] - float(ymin)) / dy, 0.0, 1.0)
            ux = np.rint(qx * 65535.0).astype(np.uint16)
            uy = np.rint(qy * 65535.0).astype(np.uint16)
            return np.stack([ux, uy], axis=1)

        # 找到最接近的影格索引
        def _nearest_k(frame_idx: int) -> Optional[int]:
            if n_frames <= 0:
                return None
            j = int(np.searchsorted(idxs_full_i64, int(frame_idx), side="left"))
            if j <= 0:
                return 0
            if j >= n_frames:
                return n_frames - 1
            left = int(idxs_full_i64[j - 1])
            right = int(idxs_full_i64[j])
            return j - 1 if abs(int(frame_idx) - left) <= abs(right - int(frame_idx)) else j

        lq = _quantize_u16(l2_sub)
        rq = _quantize_u16(r2_sub)
        # 打包成 [xL, yL, xR, yR] * n_frames
        packed_u16 = np.empty((n_frames, 4), dtype=np.uint16)
        packed_u16[:, 0:2] = lq
        packed_u16[:, 2:4] = rq

        # 壓縮
        b64 = pack_1d_u16_le_zlib_b64(packed_u16)

        # 椅/錐座標量化 [x_u16, y_u16]
        chair_u16 = _quantize_u16(np.asarray(chair_pos, dtype=float)[None, :])[0]
        cone_u16 = _quantize_u16(np.asarray(cone_pos, dtype=float)[None, :])[0]

        # 計算軌跡寬度的輔助函數
        def _calc_trajectory_width(
            c2_lap: np.ndarray,
            chair: np.ndarray,
            cone: np.ndarray,
        ) -> float:
            """計算單圈軌跡寬度（垂直於椅-錐連線的最大偏移範圍）。"""
            if c2_lap.shape[0] < 2:
                return 0.0
            # 椅-錐連線方向向量
            direction = cone - chair
            dir_len = float(np.linalg.norm(direction))
            if dir_len < 1e-9:
                return 0.0
            direction = direction / dir_len
            # 垂直方向（法向量）
            normal = np.array([-direction[1], direction[0]])
            # 計算每個點相對於椅子的偏移
            offsets = c2_lap - chair
            # 投影到法向量上得到橫向偏移
            lateral = np.dot(offsets, normal)
            # 軌跡寬度 = 最大偏移 - 最小偏移
            return float(np.max(lateral) - np.min(lateral))

        # 圈段/轉身 marker 索引 k
        laps_payload = []
        lap_widths: list[float] = []
        
        for lap_i, lap in enumerate(det.laps, start=1):
            start_f = int(lap.idx_start)
            end_f = int(lap.idx_end)
            # 在下採樣後的 idxs_full_i64 裡，找落在 [start_f, end_f] 範圍內的第一/最後一筆。
            payload_start_k: Optional[int] = None
            payload_end_k: Optional[int] = None
            
            if n_frames > 0:
                # 在 idxs_full_i64 裡，找落在 [start_f, end_f] 範圍內的第一/最後一筆。
                k0 = int(np.searchsorted(idxs_full_i64, start_f, side="left"))
                k1 = int(np.searchsorted(idxs_full_i64, end_f, side="right")) - 1
                if (0 <= k0 < n_frames) and (0 <= k1 < n_frames) and (k0 <= k1):
                    payload_start_k = k0
                    payload_end_k = k1

            # 計算此圈的軌跡寬度（使用原始座標，非量化後的）
            lap_width: Optional[float] = None
            if start_f < end_f and start_f >= 0 and end_f < num_frames:
                c2_lap = c2[start_f:end_f + 1]
                if c2_lap.shape[0] >= 2:
                    lap_width = _calc_trajectory_width(c2_lap, chair_pos, cone_pos)
                    lap_widths.append(lap_width)

            laps_payload.append(
                {
                    "lap_index": int(lap_i),
                    "lap_direction": str(lap.lap_direction),
                    "payload_start_k": payload_start_k,
                    "payload_end_k": payload_end_k,
                    "markers": {
                        "cone_start_k": _nearest_k(int(lap.idx_turn_cone_start)),
                        "cone_end_k": _nearest_k(int(lap.idx_turn_cone_end)),
                        "chair_start_k": _nearest_k(int(lap.idx_turn_chair_start)),
                        "chair_end_k": _nearest_k(int(lap.idx_turn_chair_end)),
                    },
                    "trajectory_width_m": float(lap_width) if lap_width is not None else None,
                }
            )

        # 計算軌跡寬度統計
        width_stats: Optional[dict] = None
        if lap_widths:
            widths_arr = np.array(lap_widths, dtype=float)
            widest_idx = int(np.argmax(widths_arr))
            narrowest_idx = int(np.argmin(widths_arr))
            mean_w = float(np.mean(widths_arr))
            std_w = float(np.std(widths_arr)) if len(widths_arr) > 1 else 0.0
            cv_pct = (std_w / mean_w * 100) if mean_w > 1e-9 else 0.0
            
            # 找到對應的 lap_index（1-based）
            valid_lap_indices = [
                lp["lap_index"] for lp in laps_payload 
                if lp["trajectory_width_m"] is not None
            ]
            
            width_stats = {
                "widest_lap_index": valid_lap_indices[widest_idx] if valid_lap_indices else None,
                "widest_lap_width_m": float(widths_arr[widest_idx]),
                "narrowest_lap_index": valid_lap_indices[narrowest_idx] if valid_lap_indices else None,
                "narrowest_lap_width_m": float(widths_arr[narrowest_idx]),
                "mean_width_m": mean_w,
                "std_width_m": std_w,
                "cv_pct": cv_pct,
            }

        return {
            "meta": {
                "projection": str(config.projection),
                "fps_out": int(config.fps_out),
                "rotate_180": bool(config.rotate_180),
                "bounds": {
                    "xmin": float(xmin),
                    "xmax": float(xmax),
                    "ymin": float(ymin),
                    "ymax": float(ymax),
                },
                "encoding": "u16_xy_lr_zlib_b64",
                "endian": "little",
                "n_frames": int(n_frames),
            },
            "scene": {
                "chair_xy_u16": [int(chair_u16[0]), int(chair_u16[1])],
                "cone_xy_u16": [int(cone_u16[0]), int(cone_u16[1])],
                "r_chair": float(rC),
                "r_cone": float(rK),
            },
            "frames": {"xy_lr_u16_zlib_b64": b64},
            "laps": laps_payload,
            "width_stats": width_stats,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"trajectory payload analysis failed: {e}"
        )


@router.post("/gait_cycle_phases", response_model=GaitCyclePhasesResponse)
@redis_cache(expire=30)
async def gait_cycle_phases(
    session_name: str,
    config: Optional[GaitCyclePhasesRequest] = Body(None),
) -> GaitCyclePhasesResponse:
    """
    回傳左右腳步態週期相位百分比，供前端繪製步態時間軸圖。
    
    完整步態週期（以左腳為例）：
    - DS1: 初始雙支撐期（兩腳同時著地）
    - SS: 單支撐期（主側腳支撐，對側腳擺動）
    - DS2: 終末雙支撐期（兩腳同時著地）
    - Swing: 擺動期（主側腳離地）
    
    前端繪製建議：
    - 左腳：DS1 → SS → DS2 → Swing（從 0% 開始）
    - 右腳：Swing → DS2 → SS → DS1（反過來，並偏移讓 DS 對齊）
    - 右腳偏移量 = left.ds1_pct + left.single_support_pct - right.swing_pct
    
    顏色建議：
    - 左腳：深藍(DS) / 中藍(SS) / 淺藍(Swing)
    - 右腳：深紅(DS) / 中紅(SS) / 淺紅(Swing)
    """
    config = config or GaitCyclePhasesRequest()
    npy_path = await resolve_session_npy_path(session_name)

    try:
        analyzer = RehabilitationSessionAnalyzer(npy_path=npy_path)
        left_phases, right_phases = analyzer.compute_gait_cycle_phases(
            projection=config.projection,
            smooth_window_s=config.smooth_window_s,
            flat_frac=config.flat_frac,
            min_v_abs=config.min_v_abs,
        )
        
        # 轉換為 response 格式
        left_data = None
        right_data = None
        right_offset = None
        
        if left_phases:
            left_data = {
                "side": left_phases.side,
                "ds1_pct": float(left_phases.ds1_pct),
                "single_support_pct": float(left_phases.single_support_pct),
                "ds2_pct": float(left_phases.ds2_pct),
                "swing_pct": float(left_phases.swing_pct),
                "stance_pct": float(left_phases.stance_pct),
                "avg_cycle_time_s": float(left_phases.avg_cycle_time_s),
                "n_cycles": int(left_phases.n_cycles),
            }
        
        if right_phases:
            right_data = {
                "side": right_phases.side,
                "ds1_pct": float(right_phases.ds1_pct),
                "single_support_pct": float(right_phases.single_support_pct),
                "ds2_pct": float(right_phases.ds2_pct),
                "swing_pct": float(right_phases.swing_pct),
                "stance_pct": float(right_phases.stance_pct),
                "avg_cycle_time_s": float(right_phases.avg_cycle_time_s),
                "n_cycles": int(right_phases.n_cycles),
            }
        
        # 計算右腳偏移量讓雙支撐期對齊
        if left_phases and right_phases:
            # Left 的 DS2 開始於 ds1 + ss
            # Right 的 DS2 開始於 swing（因為右腳順序是 Swing → DS2 → SS → DS1）
            left_ds2_start = left_phases.ds1_pct + left_phases.single_support_pct
            right_ds2_start = right_phases.swing_pct
            right_offset = float(left_ds2_start - right_ds2_start)
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"gait_cycle_phases analysis failed: {e}",
        )

    return {
        "left": left_data,
        "right": right_data,
        "right_offset_pct": right_offset,
    }
