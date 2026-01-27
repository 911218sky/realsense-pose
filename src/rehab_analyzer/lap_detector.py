"""圈數偵測與路徑/速度序列工具。"""

from functools import partial
from numpy._typing._array_like import NDArray
from operator import attrgetter
from typing import Any, List, Optional, Tuple

import numpy as np
from cachetools import cachedmethod

from .entities import DetectLapsResult, Lap
from .constants import (
    DEFAULT_PROJECTION,
    DEFAULT_SMOOTH_WINDOW_S,
    DEFAULT_CONE_DWELL_S,
    DEFAULT_DEBOUNCE_S,
    DEFAULT_YDIFF_WINDOW_S,
    DEFAULT_SIT_POS_THR,
    DEFAULT_GROUP_GAP_S,
    DEFAULT_FLAT_FRAC,
    DEFAULT_MIN_V_ABS,
    DEFAULT_MIN_TURN_WIDTH_S,
    DEFAULT_ANGULAR_VELOCITY_SMOOTH_S,
    LEAVE_RUN_NEEDED_RATIO,
)

from .cache_keys import method_key
from .pose_processor import PoseProcessor
from .lap_utils import (
    hysteresis_mask,
    contiguous_run_bounds,
    seg_path_len,
    turn_dir_from_slope,
    detect_turn_window_by_heading,
)


class LapDetector(PoseProcessor):
    """偵測離椅→繞錐→回椅坐下的圈數與相關時空資訊。"""

    def _infer_anchors(
        self,
        c2: np.ndarray,
        valid: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray, float]:
        """利用主軸兩端作為兩個 anchor 點（不預先指定椅子/錐子）。"""
        p = c2[valid]

        if len(p) < 10:
            pmin = np.min(p, axis=0)
            pmax = np.max(p, axis=0)
            return pmin, pmax, float(np.linalg.norm(pmax - pmin))

        p0 = p - np.mean(p, axis=0, keepdims=True)
        _, _, Vt = np.linalg.svd(p0, full_matrices=False)
        axis = Vt[0]

        s = p0 @ axis
        s_min, s_max = np.percentile(s, [5, 95])
        a = np.mean(p[s <= s_min + 1e-6], axis=0)
        b = np.mean(p[s >= s_max - 1e-6], axis=0)
        D = float(np.linalg.norm(b - a))
        return a, b, D

    def _auto_zones(
        self,
        c2: np.ndarray,
        pos_a: np.ndarray,
        pos_b: np.ndarray,
        y: np.ndarray,
        ydiff_window: int = 5,
        sit_pos_thr: float = 0.2,
        base_margin_m: float = 0.05,
        rC: Optional[tuple[float, float]] = None,
        rK: Optional[tuple[float, float]] = None,
    ) -> Tuple[np.ndarray, np.ndarray, Tuple[float, float], Tuple[float, float]]:
        """自動估算椅子與錐子的中心與進出半徑（含遲滯）。"""
        k = max(1, int(ydiff_window))
        ker = np.ones(k) / k
        yprime = np.convolve(self._compute_yprime(y), ker, mode="same")

        dA = np.linalg.norm(c2 - pos_a, axis=1)
        dB = np.linalg.norm(c2 - pos_b, axis=1)

        # 坐下時段：用 y' >= sit_pos_thr 當作坐下
        sit_mask = yprime >= sit_pos_thr

        def chair_side(dist_a: np.ndarray, dist_b: np.ndarray) -> bool:
            """判斷哪一側比較像椅子（坐下時離哪個 anchor 比較近）。"""
            vals_a = dist_a[sit_mask]
            vals_b = dist_b[sit_mask]
            if vals_a.size == 0 or vals_b.size == 0:
                vals_a = dist_a
                vals_b = dist_b
            return np.median(vals_a) < np.median(vals_b)

        is_a_chair = chair_side(dA, dB)
        chair_pos = pos_a if is_a_chair else pos_b
        cone_pos = pos_b if is_a_chair else pos_a
        dist_chair = dA if is_a_chair else dB
        dist_cone = dB if is_a_chair else dA

        if rC is not None and rC[0] > 0.0:
            rC_enter, rC_exit = float(rC[0]), float(rC[1])
        else:
            rC_enter = float(np.percentile(dist_chair, 50)) + base_margin_m
            rC_exit = rC_enter + base_margin_m

        if rK is not None and rK[0] > 0.0:
            rK_enter, rK_exit = float(rK[0]), float(rK[1])
        else:
            rK_enter = float(np.percentile(dist_cone, 30)) + base_margin_m
            rK_exit = rK_enter + base_margin_m

        # 做一層合理上限，避免半徑被 outlier 撐太大
        finite_all = np.concatenate([dist_chair, dist_cone])
        if np.any(finite_all):
            mask_chair = dist_chair != 0
            mask_cone = dist_cone != 0
            vals = np.concatenate([dist_chair[mask_chair], dist_cone[mask_cone]])
            typical = float(np.percentile(vals, 45))
            cap = max(typical * 3.0, 0.5)

            rC_enter = float(np.clip(rC_enter, 0.03, cap))
            rC_exit = float(np.clip(rC_exit, 0.04, cap + 0.3))
            rK_enter = float(np.clip(rK_enter, 0.03, cap))
            rK_exit = float(np.clip(rK_exit, 0.04, cap + 0.3))

        return chair_pos, cone_pos, (rC_enter, rC_exit), (rK_enter, rK_exit)

    @cachedmethod(attrgetter("cache"), key=partial(method_key, "_speed_series"))
    def _speed_series(self, c2: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """根據 2D 中點軌跡計算速度與逐幀位移。"""
        c2_arr = np.asarray(c2, dtype=float)
        fps = self._estimate_fps()
        t = self.t

        # 逐幀位移長度
        dC = np.linalg.norm(np.diff(c2_arr, axis=0, prepend=c2_arr[[0], :]), axis=1)

        dt = np.diff(t, prepend=t[0])
        pos_dt = dt[np.isfinite(dt) & (dt > 0)]
        dt_med = np.median(pos_dt) if pos_dt.size else 1.0 / fps
        floor_dt = max(dt_med * 0.1, 1.0 / (10.0 * fps))
        dt[(~np.isfinite(dt)) | (dt <= 0) | (dt < floor_dt)] = dt_med

        speed = dC / dt

        # 基於 MAD 將極端位移視為 outlier，對應速度改為 NaN
        if dC.size:
            med = np.median(dC)
            mad = 1.4826 * np.median(np.abs(dC - med)) if dC.size > 1 else 0.0
            hi = med + 6.0 * mad
            bad = dC > hi
            speed[bad] = np.nan

        # 線性內插補 NaN
        if np.any(np.isnan(speed)):
            nans = np.isnan(speed)
            good = ~nans
            if good.sum() >= 2:
                speed[nans] = np.interp(
                    np.flatnonzero(nans),
                    np.flatnonzero(good),
                    speed[good],
                )
            else:
                speed = np.nan_to_num(speed, nan=0.0)

        return t, speed, dC

    @cachedmethod(
        attrgetter("cache"), key=partial(method_key, "_lateral_offset_series")
    )
    def _lateral_offset_series(
        self,
        c2: np.ndarray,
        chair_pos: np.ndarray,
        cone_pos: np.ndarray,
        k_smooth: int = 1,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """建立以椅子→錐子為前進軸的局部座標，計算 lateral offset。"""
        vec = (cone_pos - chair_pos).astype(float)
        norm = float(np.linalg.norm(vec))

        if norm <= 1e-6:
            lat = c2[:, 0].astype(float)
        else:
            ex = vec / norm
            ey = np.array([-ex[1], ex[0]], dtype=float)
            rel = c2 - chair_pos[None, :]
            lat = rel @ ey

        k = max(1, int(k_smooth))
        if k > 1:
            ker = np.ones(k, dtype=float) / float(k)
            lat_smooth = np.convolve(lat, ker, mode="same")
        else:
            lat_smooth = lat

        return lat, lat_smooth

    def _compute_lap_direction(
        self,
        c2: np.ndarray,
        chair_pos: np.ndarray,
        cone_pos: np.ndarray,
        idx_start: int,
        idx_end: int,
        turn_cone_dir: int,
        turn_chair_dir: int,
        delta_theta_cone_deg: float,
        delta_theta_chair_deg: float,
    ) -> str:
        """
        計算整圈的方向（順時針/逆時針）。
        
        判別邏輯：
        1. 主要依據錐區和椅區的轉身方向
        2. 輔助使用整圈的角度變化
        3. 考慮椅子到錐子的向量方向
        
        Parameters
        ----------
        c2 : np.ndarray
            2D 軌跡點
        chair_pos : np.ndarray
            椅子位置
        cone_pos : np.ndarray
            錐子位置
        idx_start : int
            圈開始索引
        idx_end : int
            圈結束索引
        turn_cone_dir : int
            錐區轉身方向
        turn_chair_dir : int
            椅區轉身方向
        delta_theta_cone_deg : float
            錐區角度變化
        delta_theta_chair_deg : float
            椅區角度變化
            
        Returns
        -------
        str
            "clockwise", "counterclockwise", 或 "unknown"
        """
        # 方法1：基於轉身方向判別
        # 在標準的順時針圈中：
        # - 錐區轉身通常是順時針（+1）
        # - 椅區轉身通常是順時針（+1）
        # 在逆時針圈中則相反
        
        direction_votes = []
        
        # 投票1：錐區轉身方向
        if abs(delta_theta_cone_deg) > 30:  # 只有在顯著轉身時才考慮
            if turn_cone_dir > 0:
                direction_votes.append("clockwise")
            elif turn_cone_dir < 0:
                direction_votes.append("counterclockwise")
        
        # 投票2：椅區轉身方向
        if abs(delta_theta_chair_deg) > 30:  # 只有在顯著轉身時才考慮
            if turn_chair_dir > 0:
                direction_votes.append("clockwise")
            elif turn_chair_dir < 0:
                direction_votes.append("counterclockwise")
        
        # 基於軌跡的幾何分析
        # 計算從椅子到錐子的向量，以及軌跡相對於這個向量的偏移
        if idx_end > idx_start + 10:  # 確保有足夠的軌跡點
            chair_to_cone: NDArray[Any] = cone_pos - chair_pos
            chair_to_cone_norm = np.linalg.norm(chair_to_cone)
            
            if chair_to_cone_norm > 1e-6:
                # 建立局部座標系：椅子到錐子為 x 軸
                ex = chair_to_cone / chair_to_cone_norm
                ey = np.array([-ex[1], ex[0]])  # 垂直向量
                
                # 計算軌跡在局部座標系中的位置
                traj_segment = c2[idx_start:idx_end+1]
                rel_pos = traj_segment - chair_pos[None, :]
                
                # 投影到垂直軸（y軸）
                y_coords = rel_pos @ ey
                
                # 分析軌跡的偏移模式
                # 順時針：從椅子出發時向右偏移（y > 0），回來時向左偏移（y < 0）
                # 逆時針：從椅子出發時向左偏移（y < 0），回來時向右偏移（y > 0）
                mid_point = len(y_coords) // 2
                outbound_y = np.mean(y_coords[:mid_point])
                return_y = np.mean(y_coords[mid_point:])
                
                # 判別邏輯：如果出發時偏右，回來時偏左，則為順時針
                if outbound_y > 0.05 and return_y < -0.05:
                    direction_votes.append("clockwise")
                elif outbound_y < -0.05 and return_y > 0.05:
                    direction_votes.append("counterclockwise")
        
        # 統計投票結果
        if not direction_votes:
            return "unknown"
        
        clockwise_votes = direction_votes.count("clockwise")
        counterclockwise_votes = direction_votes.count("counterclockwise")
        
        if clockwise_votes > counterclockwise_votes:
            return "clockwise"
        elif counterclockwise_votes > clockwise_votes:
            return "counterclockwise"
        else:
            # 使用整圈的總角度變化
            # 計算整圈的總角度變化（錐區 + 椅區）
            total_delta = delta_theta_cone_deg + delta_theta_chair_deg
            
            # 如果總角度變化顯著，使用其符號判斷方向
            if abs(total_delta) > 60:  # 總角度變化超過 60 度才可靠
                if total_delta > 0:
                    return "clockwise"
                else:
                    return "counterclockwise"
            
            # 如果總角度變化也不顯著，使用較大的單區角度變化
            if abs(delta_theta_cone_deg) > abs(delta_theta_chair_deg):
                # 錐區角度變化較大，使用錐區方向
                if turn_cone_dir > 0:
                    return "clockwise"
                elif turn_cone_dir < 0:
                    return "counterclockwise"
            else:
                # 椅區角度變化較大，使用椅區方向
                if turn_chair_dir > 0:
                    return "clockwise"
                elif turn_chair_dir < 0:
                    return "counterclockwise"
            
            # 最後的 fallback：如果所有方法都無法判斷，返回 unknown
            return "unknown"

    @cachedmethod(attrgetter("cache"), key=partial(method_key, "detect_laps_auto"))
    def detect_laps_auto(
        self,
        projection: str = DEFAULT_PROJECTION,
        smooth_window_s: float = DEFAULT_SMOOTH_WINDOW_S,
        cone_dwell_s: float = DEFAULT_CONE_DWELL_S,
        debounce_s: float = DEFAULT_DEBOUNCE_S,
        ydiff_window_s: float = DEFAULT_YDIFF_WINDOW_S,
        sit_pos_thr: float = DEFAULT_SIT_POS_THR,
        group_gap_s: float = DEFAULT_GROUP_GAP_S,
        flat_frac: float = DEFAULT_FLAT_FRAC,
        min_v_abs: float = DEFAULT_MIN_V_ABS,
        min_turn_width_s: float = DEFAULT_MIN_TURN_WIDTH_S,
        rC: Optional[Tuple[float, float]] = None,
        rK: Optional[Tuple[float, float]] = None,
        detect_direction: bool = True,
    ) -> DetectLapsResult:
        """自動偵測圈數（離椅→錐→回椅且坐下）。

        使用 PoseProcessor 處理 bag 檔案時生成的錨點配置。

        Parameters
        ----------
        projection : str
            偵測時使用的 2D 投影平面（xz / xy）
        smooth_window_s : float
            髖點座標平滑視窗長度（秒）
        cone_dwell_s : float
            需在錐區停留的秒數門檻
        debounce_s : float
            near chair/cone mask 的去抖動時間窗（秒）
        ydiff_window_s : float
            Y 高度差分平滑視窗（秒）
        sit_pos_thr : float
            y' 門檻，絕對值大於此視為上下動作
        group_gap_s : float
            將候選 frame 聚成事件時允許的最大時間間隔
        flat_frac : float
            角速度衰減到峰值 flat_frac 倍即視為轉彎結束
        min_v_abs : float
            檢測轉彎時所需的最小角速度 (deg/s)
        min_turn_width_s : float
            轉彎區段至少要持續的秒數
        rC : Optional[Tuple[float, float]]
            指定椅子區域進/出半徑 (r_enter, r_exit)，覆蓋配置中的值
        rK : Optional[Tuple[float, float]]
            指定錐區進/出半徑 (r_enter, r_exit)，覆蓋配置中的值
        detect_direction : bool
            是否計算圈數方向（順時針/逆時針），預設為 True

        Returns
        -------
        DetectLapsResult
            偵測結果，包含圈數列表與區域參數
        """
        # 把 frame index 轉成時間秒數
        def ts_at(i: int) -> float:
            return float(self.t[i])

        # ---------------------- 主流程開始 ---------------------- #
        fps = self._estimate_fps()

        # 將以秒為單位的參數轉換成帧數
        smooth_window = max(1, int(round(smooth_window_s * fps)))
        ydiff_window = max(1, int(round(ydiff_window_s * fps)))
        min_width_frames = max(1, int(round(min_turn_width_s * fps)))

        l2, r2, _ = self._compute_hip_points(
            projection=projection,
            smooth_window=smooth_window,
        )
        c2 = (l2 + r2) / 2.0
        N = len(c2)
        group_gap_frames = max(1, int(round(group_gap_s * fps)))

        # 利用同一投影的髖點計算解包後骨盆朝向
        theta = self.compute_pelvis_heading_unwrapped(L2=l2, R2=r2)

        # 使用已儲存的錨點配置
        chair_pos = np.array(self.anchor_config.chair_pos, dtype=float)
        cone_pos = np.array(self.anchor_config.cone_pos, dtype=float)
        
        # 使用配置中的半徑，或使用參數覆蓋
        if rC is not None and rC[0] > 0.0:
            rC_in, rC_out = float(rC[0]), float(rC[1])
        else:
            rC_in, rC_out = self.anchor_config.chair_radius
        
        if rK is not None and rK[0] > 0.0:
            rK_in, rK_out = float(rK[0]), float(rK[1])
        else:
            rK_in, rK_out = self.anchor_config.cone_radius
        
        # 計算 Y 高度（用於判斷站起、坐下）
        xyz = self.arr[:, :33, :]
        y = (xyz[:, self.L_HIP, 1] + xyz[:, self.R_HIP, 1]) / 2.0

        dist_chair = np.linalg.norm(c2 - chair_pos, axis=1)
        dist_cone = np.linalg.norm(c2 - cone_pos, axis=1)
        near_chair = hysteresis_mask(dist_chair, rC_in, rC_out)
        near_cone = hysteresis_mask(dist_cone, rK_in, rK_out)

        cone_n = max(1, int(round(cone_dwell_s * fps)))
        k_db = max(1, int(round(debounce_s * fps)))
        leave_run_needed = max(1, int(round(LEAVE_RUN_NEEDED_RATIO * fps)))

        # 對 near_chair / near_cone 做去抖動
        if k_db > 1:
            ones = np.ones(k_db, dtype=np.int32)
            thr = (k_db + 1) // 2
            near_chair = (
                np.convolve(near_chair.astype(np.int32), ones, mode="same") >= thr
            )
            near_cone = (
                np.convolve(near_cone.astype(np.int32), ones, mode="same") >= thr
            )

        # Y 高度導數，用來判斷站起、坐下
        yprime = self._compute_yprime(y)
        k = max(1, int(ydiff_window))
        yprime = np.convolve(yprime, np.ones(k) / k, mode="same")

        # 找離開椅區與回到椅區的幀
        nc = near_chair.astype(np.int8)
        diff = np.diff(nc, prepend=nc[0])
        leave_starts = np.where((diff == -1) & (nc == 0))[0]

        if leave_starts.size == 0:
            return DetectLapsResult(
                [],
                0,
                (float(chair_pos[0]), float(chair_pos[1])),
                (float(cone_pos[0]), float(cone_pos[1])),
                float(rC_in),
                float(rC_out),
                float(rK_in),
                float(rK_out),
                float(fps),
            )

        true_returns = np.where((diff == 1) & (nc == 1))[0]
        rr = np.searchsorted(true_returns, leave_starts, side="left")
        leave_ends = np.empty_like(leave_starts)
        leave_ends[:] = N - 1
        valid_rr = rr < true_returns.size
        leave_ends[valid_rr] = true_returns[rr[valid_rr]]

        leave_len = leave_ends - leave_starts + 1
        good_mask = leave_len >= leave_run_needed
        leave_starts = leave_starts[good_mask]
        leave_ends = leave_ends[good_mask]

        if leave_starts.size == 0:
            return DetectLapsResult(
                [],
                0,
                (float(chair_pos[0]), float(chair_pos[1])),
                (float(cone_pos[0]), float(cone_pos[1])),
                float(rC_in),
                float(rC_out),
                float(rK_in),
                float(rK_out),
                float(fps),
            )

        # 錐區停留時間判斷
        if cone_n <= 1:
            cone_valid = near_cone.copy()
        else:
            conv = np.convolve(
                near_cone.astype(np.int32),
                np.ones(cone_n, dtype=np.int32),
                mode="same",
            )
            cone_valid = conv >= cone_n

        # 坐下動作：在椅區且 y' <= -sit_pos_thr（身體下降）
        chair_sitdown_mask = near_chair & (yprime <= -sit_pos_thr)
        chair_sitdown_idx = np.where(chair_sitdown_mask)[0]

        # 起身動作：在椅區且 y' >= sit_pos_thr（身體上升）
        standup_mask = near_chair & (yprime >= sit_pos_thr)
        standup_candidates = np.where(standup_mask)[0]

        laps_list: List[Lap] = []

        for ls, le in zip(leave_starts, leave_ends):
            # 這段離椅期間有沒有在 cone zone 停留夠久
            idx = np.where(cone_valid[ls: le + 1])[0]
            if idx.size == 0:
                continue
            t_cone = ls + idx[0]

            # 起身段（離椅前的身體上升動作）
            # 找離開椅區前最近的起身動作
            j = np.searchsorted(standup_candidates, ls, side="left") - 1
            if j >= standup_candidates.size or j < 0:
                continue
            
            # 確保這個起身動作是在離開椅區之前，且時間上合理（不超過 45 秒）
            standup_idx = standup_candidates[j]
            if standup_idx >= ls or (ls - standup_idx) > 45 * fps:
                continue

            j_start = j
            while ((j_start - 1) >= 0) and (
                (standup_candidates[j_start] - standup_candidates[j_start - 1]) <= group_gap_frames
            ):
                j_start -= 1
            onset_start_idx = int(standup_candidates[j_start])
            
            j_end = j
            while ((j_end + 1) < standup_candidates.size) and (
                (standup_candidates[j_end + 1] - standup_candidates[j_end]) <= group_gap_frames
            ):
                j_end += 1
            onset_end_idx = int(standup_candidates[j_end])

            # ---------- 回到椅區 + 坐下 ----------
            # 找回到椅區後的坐下動作（身體下降）
            j = np.searchsorted(chair_sitdown_idx, t_cone, side="left")
            if j >= chair_sitdown_idx.size or j < 0:
                continue

            j_end = j
            while ((j_end + 1) < chair_sitdown_idx.size) and (
                (chair_sitdown_idx[j_end + 1] - chair_sitdown_idx[j_end]) <= group_gap_frames
            ):
                j_end += 1
            chair_sit_end_idx = int(chair_sitdown_idx[j_end])

            j_start = j
            while ((j_start - 1) >= 0) and (
                (chair_sitdown_idx[j_start] - chair_sitdown_idx[j_start - 1]) <= group_gap_frames
            ):
                j_start -= 1
            chair_sit_start_idx = int(chair_sitdown_idx[j_start])

            # 延伸坐下結束點，直到 y' 接近 0（身體下降動作結束）
            while (chair_sit_end_idx < N - 1) and (yprime[chair_sit_end_idx] < -sit_pos_thr * 0.5):
                chair_sit_end_idx += 1

            # 起身開始點往前找，確保往下動作開始被包含
            while (chair_sit_start_idx > 0) and (yprime[chair_sit_start_idx] > -sit_pos_thr * 0.5):
                chair_sit_start_idx -= 1

            # cone zone 連續 True 片段
            cone_entry_idx, cone_exit_idx = contiguous_run_bounds(
                near_cone,
                t_cone,
            )

            # A：錐區轉彎（用骨盆角度斜率）
            turn_cone_start_idx, turn_cone_end_idx, slope_cone = detect_turn_window_by_heading(
                theta=theta,
                t_arr=self.t,
                seg_start=int(cone_entry_idx),
                seg_end=int(cone_exit_idx),
                fps=fps,
                angular_velocity_smooth_s=DEFAULT_ANGULAR_VELOCITY_SMOOTH_S,
                flat_frac=flat_frac,
                min_v_abs=min_v_abs,
                min_width_frames=min_width_frames,
            )
            dir_cone = turn_dir_from_slope(slope_cone)
            delta_cone = theta[turn_cone_end_idx] - theta[turn_cone_start_idx]

            # B：椅子附近轉身（用骨盆角度斜率）
            reenter_idx = int(le)
            j = np.searchsorted(chair_sitdown_idx, reenter_idx, side="left")
            if j >= chair_sitdown_idx.size or j < 0:
                continue
            sit_start_idx = int(chair_sitdown_idx[j])

            turn_chair_start_idx, turn_chair_end_idx, slope_chair = detect_turn_window_by_heading(
                theta=theta,
                t_arr=self.t,
                seg_start=int(reenter_idx),
                seg_end=int(sit_start_idx),
                fps=fps,
                angular_velocity_smooth_s=DEFAULT_ANGULAR_VELOCITY_SMOOTH_S,
                flat_frac=flat_frac,
                min_v_abs=min_v_abs,
                min_width_frames=min_width_frames,
            )
            dir_chair = turn_dir_from_slope(slope_chair)
            delta_chair = theta[turn_chair_end_idx] - theta[turn_chair_start_idx]

            # ---------- 計算各時段時間與距離 ----------
            ts_start = ts_at(onset_start_idx)
            ts_leave_chair = ts_at(onset_end_idx)
            ts_enter_cone = ts_at(cone_entry_idx)
            ts_exit_cone = ts_at(cone_exit_idx)
            ts_turn_cone_start = ts_at(turn_cone_start_idx)
            ts_turn_cone_end = ts_at(turn_cone_end_idx)
            ts_turn_chair_start = ts_at(turn_chair_start_idx)
            ts_turn_chair_end = ts_at(turn_chair_end_idx)
            ts_reenter_chair = ts_at(reenter_idx)
            ts_sit_start = ts_at(sit_start_idx)
            ts_end = ts_at(chair_sit_end_idx)

            dur_stand = max(0.0, ts_leave_chair - ts_start)
            dur_to_cone = max(0.0, ts_enter_cone - ts_leave_chair)
            dur_cone_turn = max(0.0, ts_turn_cone_end - ts_turn_cone_start)
            dur_return = max(0.0, ts_reenter_chair - ts_exit_cone)
            dur_turn_to_sit = max(0.0, ts_turn_chair_end - ts_turn_chair_start)
            dur_sit = max(0.0, ts_end - ts_sit_start)
            dur_total = max(0.0, ts_end - ts_start)

            if ts_end > ts_start and dur_sit > 0.0:
                pt_cone_turn_start = c2[turn_cone_start_idx]
                pt_cone_turn_end = c2[turn_cone_end_idx]
                dist_cone_turn_chord_m = float(
                    np.linalg.norm(pt_cone_turn_end - pt_cone_turn_start)
                )
                dist_cone_turn_path_m = seg_path_len(
                    c2,
                    turn_cone_start_idx,
                    turn_cone_end_idx,
                )
                dist_outbound_m = seg_path_len(c2, ls, turn_cone_start_idx)
                dist_return_m = seg_path_len(
                    c2,
                    turn_cone_end_idx,
                    turn_chair_start_idx,
                )
                dist_turn_to_sit_m = seg_path_len(
                    c2,
                    turn_chair_start_idx,
                    turn_chair_end_idx,
                )
                dist_lap_path_m = dist_outbound_m + dist_cone_turn_path_m + dist_return_m + dist_turn_to_sit_m
                dist_chair_cone_centers_m = float(
                    np.linalg.norm(cone_pos - chair_pos)
                )
                
                # 計算圈數方向
                if detect_direction:
                    lap_direction = self._compute_lap_direction(
                        c2=c2,
                        chair_pos=chair_pos,
                        cone_pos=cone_pos,
                        idx_start=onset_start_idx,
                        idx_end=chair_sit_end_idx,
                        turn_cone_dir=dir_cone,
                        turn_chair_dir=dir_chair,
                        delta_theta_cone_deg=delta_cone,
                        delta_theta_chair_deg=delta_chair,
                    )
                else:
                    lap_direction = "unknown"
                
                laps_list.append(
                    Lap(
                        # ===== 時間戳記 (秒) =====
                        ts_start=float(ts_start),           # 圈開始時間（起身動作開始）
                        ts_end=float(ts_end),               # 圈結束時間（坐下動作結束）
                        dur_total=float(dur_total),         # 整圈總耗時 (秒)

                        # ===== 幀索引 (frame index) =====
                        idx_start=int(onset_start_idx),         # 圈開始幀（= idx_onset_start）
                        idx_end=int(chair_sit_end_idx),         # 圈結束幀（= idx_chair_sit_end）
                        idx_onset_start=int(onset_start_idx),   # 起身動作開始幀
                        idx_onset_end=int(onset_end_idx),       # 起身動作結束幀（離開椅區）
                        idx_chair_sit_end=int(chair_sit_end_idx),   # 坐下動作結束幀
                        idx_chair_sit_start=int(chair_sit_start_idx), # 坐下動作開始幀
                        idx_leave_chair=int(onset_end_idx),     # 離開椅區幀（= idx_onset_end）
                        idx_reenter_chair=int(reenter_idx),     # 重新進入椅區幀
                        idx_enter_cone=int(cone_entry_idx),     # 進入錐區幀
                        idx_exit_cone=int(cone_exit_idx),       # 離開錐區幀
                        idx_sit_start=int(sit_start_idx),       # 開始坐下幀
                        idx_turn_cone_start=int(turn_cone_start_idx),   # 錐區轉身開始幀
                        idx_turn_cone_end=int(turn_cone_end_idx),       # 錐區轉身結束幀
                        idx_turn_chair_start=int(turn_chair_start_idx), # 椅區轉身開始幀
                        idx_turn_chair_end=int(turn_chair_end_idx),     # 椅區轉身結束幀

                        # ===== 各階段耗時 (秒) =====
                        dur_stand=float(dur_stand),         # 起身階段耗時（從開始起身到離開椅區）
                        dur_to_cone=float(dur_to_cone),     # 去程耗時（從離開椅區到進入錐區）
                        dur_cone_turn=float(dur_cone_turn), # 錐區轉身耗時
                        dur_return=float(dur_return),       # 回程耗時（從離開錐區到重新進入椅區）
                        dur_turn_to_sit=float(dur_turn_to_sit), # 椅區轉身耗時
                        dur_sit=float(dur_sit),             # 坐下階段耗時

                        # ===== 轉身時間戳記 (秒) =====
                        ts_turn_cone_start=float(ts_turn_cone_start),   # 錐區轉身開始時間
                        ts_turn_cone_end=float(ts_turn_cone_end),       # 錐區轉身結束時間
                        ts_turn_chair_start=float(ts_turn_chair_start), # 椅區轉身開始時間
                        ts_turn_chair_end=float(ts_turn_chair_end),     # 椅區轉身結束時間

                        # ===== 距離 (公尺) =====
                        dist_cone_turn_chord_m=float(dist_cone_turn_chord_m), # 錐區轉身弦長（起點到終點直線距離）
                        dist_cone_turn_path_m=float(dist_cone_turn_path_m),   # 錐區轉身路徑長（實際走過的距離）
                        dist_outbound_m=float(dist_outbound_m),   # 去程距離（椅區到錐區轉身開始）
                        dist_return_m=float(dist_return_m),       # 回程距離（錐區轉身結束到椅區轉身開始）
                        dist_lap_path_m=float(dist_lap_path_m),   # 整圈總路徑長度 (去程+錐區轉身+回程+椅區轉身)
                        dist_turn_to_sit_m=float(dist_turn_to_sit_m), # 椅區轉身距離
                        dist_chair_cone_centers_m=float(
                            dist_chair_cone_centers_m               # 椅子中心到錐子中心的直線距離
                        ),

                        # ===== 轉身方向與角度 =====
                        turn_cone_dir=dir_cone,             # 錐區轉身方向 (+1=順時針, -1=逆時針, 0=未知)
                        turn_chair_dir=dir_chair,           # 椅區轉身方向 (+1=順時針, -1=逆時針, 0=未知)
                        delta_theta_cone_deg=delta_cone,    # 錐區轉身角度變化 (度)
                        delta_theta_chair_deg=delta_chair,  # 椅區轉身角度變化 (度)
                        lap_direction=lap_direction,        # 整圈方向 ("clockwise"/"counterclockwise"/"unknown")
                    )
                )

        return DetectLapsResult(
            laps=laps_list,
            num_laps=len(laps_list),
            chair_pos=(float(chair_pos[0]), float(chair_pos[1])),
            cone_pos=(float(cone_pos[0]), float(cone_pos[1])),
            r_chair_enter=float(rC_in),
            r_chair_exit=float(rC_out),
            r_cone_enter=float(rK_in),
            r_cone_exit=float(rK_out),
            fps=float(fps),
        )