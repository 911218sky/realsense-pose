"""圈數偵測與路徑/速度序列工具。"""

from functools import partial
from operator import attrgetter
from typing import List, Optional, Tuple

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
)

from .cache_keys import method_key
from .pose_processor import PoseProcessor

class LapDetector(PoseProcessor):
    """偵測離椅→繞錐→回椅坐下的圈數與相關時空資訊。"""

    def _infer_anchors(
        self,
        C2: np.ndarray,
        valid: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray, float]:
        """利用主軸兩端作為兩個 anchor 點（不預先指定椅子/錐子）。"""
        P = C2[valid]

        if len(P) < 10:
            pmin = np.min(P, axis=0)
            pmax = np.max(P, axis=0)
            return pmin, pmax, float(np.linalg.norm(pmax - pmin))

        P0 = P - np.mean(P, axis=0, keepdims=True)
        _, _, Vt = np.linalg.svd(P0, full_matrices=False)
        axis = Vt[0]

        s = P0 @ axis
        s_min, s_max = np.percentile(s, [5, 95])
        a = np.mean(P[s <= s_min + 1e-6], axis=0)
        b = np.mean(P[s >= s_max - 1e-6], axis=0)
        D = float(np.linalg.norm(b - a))
        return a, b, D

    def _auto_zones(
        self,
        C2: np.ndarray,
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

        dA = np.linalg.norm(C2 - pos_a, axis=1)
        dB = np.linalg.norm(C2 - pos_b, axis=1)

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
    def _speed_series(self, C2: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """根據 2D 中點軌跡計算速度與逐幀位移。"""
        C2 = np.asarray(C2, dtype=float)
        fps = self._estimate_fps()
        t = self.t

        # 逐幀位移長度
        dC = np.linalg.norm(np.diff(C2, axis=0, prepend=C2[[0], :]), axis=1)

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
        C2: np.ndarray,
        chair_pos: np.ndarray,
        cone_pos: np.ndarray,
        k_smooth: int = 1,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """建立以椅子→錐子為前進軸的局部座標，計算 lateral offset。"""
        vec = (cone_pos - chair_pos).astype(float)
        norm = float(np.linalg.norm(vec))

        if norm <= 1e-6:
            lat = C2[:, 0].astype(float)
        else:
            ex = vec / norm
            ey = np.array([-ex[1], ex[0]], dtype=float)
            rel = C2 - chair_pos[None, :]
            lat = rel @ ey

        k = max(1, int(k_smooth))
        if k > 1:
            ker = np.ones(k, dtype=float) / float(k)
            lat_smooth = np.convolve(lat, ker, mode="same")
        else:
            lat_smooth = lat

        return lat, lat_smooth

    @cachedmethod(attrgetter("cache"), key=partial(method_key, "detect_laps_auto"))
    def detect_laps_auto(
        self,
        # 偵測時使用的 2D 投影平面（xz / xy / yz）
        projection: str = DEFAULT_PROJECTION,
        # 髖點座標平滑視窗長度（秒），會根據 fps 自動轉換成帧數
        smooth_window_s: float = DEFAULT_SMOOTH_WINDOW_S,
        # 需在錐區停留的秒數門檻，低於此值不計入一圈
        cone_dwell_s: float = DEFAULT_CONE_DWELL_S,
        # near chair/cone mask 的去抖動時間窗（秒）
        debounce_s: float = DEFAULT_DEBOUNCE_S,
        # Y 高度差分平滑視窗（秒），用來判定站起 / 坐下
        ydiff_window_s: float = DEFAULT_YDIFF_WINDOW_S,
        # y' 門檻，絕對值大於此視為上下動作
        sit_pos_thr: float = DEFAULT_SIT_POS_THR,
        # 將候選 frame 聚成事件時允許的最大時間間隔
        group_gap_s: float = DEFAULT_GROUP_GAP_S,
        # 角速度衰減到峰值 flat_frac 倍即視為轉彎結束
        flat_frac: float = DEFAULT_FLAT_FRAC,
        # 檢測轉彎時所需的最小角速度 (deg/s)
        min_v_abs: float = DEFAULT_MIN_V_ABS,
        # 轉彎區段至少要持續的秒數
        min_turn_width_s: float = DEFAULT_MIN_TURN_WIDTH_S,
        # 指定椅子區域進/出半徑 (r_enter, r_exit)，缺省則自動估計
        rC: Optional[tuple[float, float]] = None,
        # 指定錐區進/出半徑 (r_enter, r_exit)，缺省則自動估計
        rK: Optional[tuple[float, float]] = None,
    ) -> DetectLapsResult:
        """自動偵測圈數（離椅→錐→回椅且坐下）。

        與原本流程相同，但 A/B 轉彎時間窗改用
        `compute_pelvis_heading_unwrapped` 計算出來的骨盆朝向角斜率來決定。
        
        注意：smooth_window_s, ydiff_window_s, min_turn_width_s 皆以秒為單位，
        會根據實際 fps 自動轉換成帧數，確保不同帧率下行為一致。
        """

        def hysteresis_mask(
            dist: np.ndarray,
            r_enter: float,
            r_exit: float,
        ) -> np.ndarray:
            """將距離轉成具有遲滯的進出區域布林 mask。"""
            dist = np.asarray(dist, dtype=float)
            mask = np.empty(dist.shape[0], dtype=bool)
            inside = False

            for i in range(dist.size):
                d = dist[i]

                if not np.isfinite(d):
                    mask[i] = inside
                    continue

                if inside:
                    inside = d < r_exit
                else:
                    inside = d <= r_enter

                mask[i] = inside

            return mask

        def contiguous_run_bounds(mask: np.ndarray, center_idx: int) -> Tuple[int, int]:
            """找出包含某索引的連續 True 段落邊界 [lo, hi]。"""
            n_loc = mask.size

            if not mask[center_idx]:
                return center_idx, center_idx

            lo = center_idx
            while lo - 1 >= 0 and mask[lo - 1]:
                lo -= 1

            hi = center_idx
            while hi + 1 < n_loc and mask[hi + 1]:
                hi += 1

            return lo, hi

        def seg_path_len(P: np.ndarray, start_idx: int, end_idx: int) -> float:
            """計算一段路徑的弧長（含端點）。"""
            start_idx = max(0, int(start_idx))
            end_idx = max(0, int(end_idx))
            if end_idx <= start_idx:
                return 0.0

            seg = P[start_idx:end_idx]
            if seg.shape[0] < 2:
                return 0.0

            diffs = np.diff(seg, axis=0)
            return float(np.sum(np.linalg.norm(diffs, axis=1)))

        def ts_at(i: int) -> float:
            """便利函式：把 frame index 轉成時間秒數。"""
            return float(self.t[i])

        def detect_turn_window_by_heading(
            theta: np.ndarray,
            seg_start: int,
            seg_end: int,
            *,
            flat_frac: float = 0.5,      # |v| < flat_frac * v_peak_dir 視為已變平
            min_v_abs: float = 15.0,     # 峰值若小於這個，就當沒明顯轉彎
            max_v_abs: float = 60.0,    # 峰值若大於這個，就當有明顯轉彎
            min_width_frames: int = 5,    # 最短區段長度
        ) -> tuple[int, int, float]:
            """
            在 [seg_start, seg_end] 找轉彎區段：

            1. 在該 segment 上看 Δθ 的正負，決定「主要轉彎方向」 dir_sign。
            2. 在 segment 上算角速度 v = dθ/dt，僅保留與 dir_sign 相同方向的部分：
               v_dir = v * dir_sign，v_dir < 0 的點設為 0。
            3. 在 v_dir 中找峰值，從峰值往左右擴展，直到 v_dir 掉到
               flat_frac * v_peak_dir 以下為止。
            4. 強制至少 min_width_frames，並對該段做線性回歸，回傳
               (全域 start_idx, 全域 end_idx, 斜率 slope_deg_per_s)。
            """

            seg_start = int(seg_start)
            seg_end = int(seg_end)
            if seg_end <= seg_start:
                return seg_start, seg_end, 0.0

            # 只看這個 segment 內的 θ
            theta_seg = theta[seg_start: seg_end + 1].astype(float)
            n = theta_seg.size
            if n < 3:
                return seg_start, seg_end, 0.0

            # 判斷這一整段 (seg_start ~ seg_end) 的「大方向」
            delta_total = float(theta_seg[-1] - theta_seg[0])
            if not np.isfinite(delta_total) or abs(delta_total) < 1e-3:
                # 幾乎沒變化，就不特別縮窗
                return seg_start, seg_end, 0.0

            dir_sign = 1.0 if delta_total > 0.0 else -1.0

            # 計算角速度 v = dθ/dt（只在 segment 上）
            fps_local = float(self._estimate_fps())
            dt = 1.0 / max(1.0, fps_local)

            v = np.diff(theta_seg, prepend=theta_seg[0]) / dt
            if not np.isfinite(v).any():
                return seg_start, seg_end, 0.0

            # 高帧率時對角速度做平滑，避免噪聲影響
            v_smooth_window = max(1, int(round(DEFAULT_ANGULAR_VELOCITY_SMOOTH_S * fps_local)))
            if v_smooth_window > 1 and n >= v_smooth_window:
                ker = np.ones(v_smooth_window) / v_smooth_window
                v = np.convolve(v, ker, mode="same")

            # 只保留「與整體方向一致」的角速度
            v_dir = v * dir_sign          # 期望方向的速度 > 0
            v_dir[~np.isfinite(v_dir)] = 0.0
            v_dir[v_dir < 0.0] = 0.0      # 反方向一律視為 0（避免被短暫抖動干擾）

            v_peak_dir = float(v_dir.max())
            if v_peak_dir < min_v_abs:
                # 在主要方向上根本沒有明顯轉彎
                return seg_start, seg_end, 0.0

            # 這個 index 是相對於 segment 開頭的 0..n-1
            peak_idx_local = int(np.argmax(v_dir))

            # 設定「變平」門檻，從峰值往左右擴展
            flat_thr = max(min_v_abs, min(v_peak_dir * float(flat_frac), max_v_abs))

            # 往左邊找直到速度小於 flat_thr
            lo = peak_idx_local
            while lo - 1 >= 0 and v_dir[lo - 1] >= flat_thr:
                lo -= 1

            # 往右邊找直到速度小於 flat_thr
            hi = peak_idx_local
            while hi + 1 < n and v_dir[hi + 1] >= flat_thr:
                hi += 1

            # 至少要有 min_width_frames
            length = hi - lo + 1
            min_w = int(min_width_frames)
            if length < min_w:
                need = min_w - length
                extra_left = need // 2
                extra_right = need - extra_left
                lo = max(0, lo - extra_left)
                hi = min(n - 1, hi + extra_right)

            # 對這段做線性回歸估計斜率 (deg/s)
            t_seg = self.t[seg_start: seg_end + 1].astype(float)
            t_win = t_seg[lo: hi + 1]
            y_win = theta_seg[lo: hi + 1]

            if t_win.size >= 2:
                # 用相對時間可以避免時間值太大造成數值問題
                x0 = t_win - t_win[0]
                a, _ = np.polyfit(x0, y_win, 1)
                slope = float(a)
            else:
                slope = 0.0

            # 映回「全域」索引
            st = seg_start + lo 
            ed = seg_start + hi
            st = max(seg_start, min(st, seg_end))
            ed = max(st, min(ed, seg_end))

            return st, ed, slope

        def turn_dir_from_slope(a: float, *, min_abs_deg_per_s: float = 10.0) -> int:
            """
            根據斜率決定轉彎方向：
            +1: θ 隨時間增加（例如向左 / 逆時針）
            -1: θ 隨時間減少（例如向右 / 順時針）
            0: 幾乎沒轉（|a| 太小）
            """
            if not np.isfinite(a) or abs(a) < min_abs_deg_per_s:
                return 0
            return 1 if a > 0 else -1

        # ---------------------- 主流程開始 ---------------------- #
        # 先取得 fps，再將秒轉換成帧數
        fps = self._estimate_fps()
        
        # 將以秒為單位的參數轉換成帧數，並確保至少為 1
        smooth_window = max(1, int(round(smooth_window_s * fps)))
        ydiff_window = max(1, int(round(ydiff_window_s * fps)))
        min_width_frames = max(1, int(round(min_turn_width_s * fps)))
        
        L2, R2, valid = self._compute_hip_points(
            projection=projection,
            smooth_window=smooth_window,
        )
        C2 = (L2 + R2) / 2.0
        N = len(C2)
        group_gap_frames = max(1, int(round(group_gap_s * fps)))

        # 利用同一投影的髖點計算解包後骨盆朝向
        theta = self.compute_pelvis_heading_unwrapped(L2=L2, R2=R2)

        pos_a, pos_b, D = self._infer_anchors(C2, valid)

        xyz = self.arr[:, :33, :]
        y = (xyz[:, self.L_HIP, 1] + xyz[:, self.R_HIP, 1]) / 2.0

        chair_pos, cone_pos, (rC_in, rC_out), (rK_in, rK_out) = self._auto_zones(
            C2,
            pos_a,
            pos_b,
            y,
            ydiff_window=ydiff_window,
            sit_pos_thr=sit_pos_thr,
            base_margin_m=max(0.03, 0.05 * max(D, 0.5)),
            rC=rC,
            rK=rK,
        )

        dist_chair = np.linalg.norm(C2 - chair_pos, axis=1)
        dist_cone = np.linalg.norm(C2 - cone_pos, axis=1)
        near_chair = hysteresis_mask(dist_chair, rC_in, rC_out)
        near_cone = hysteresis_mask(dist_cone, rK_in, rK_out)

        cone_n = max(1, int(round(cone_dwell_s * fps)))
        k_db = max(1, int(round(debounce_s * fps)))
        leave_run_needed = max(1, int(round(0.25 * fps)))

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

        chair_and_sit = near_chair & (yprime >= sit_pos_thr)
        chair_sit_idx = np.where(chair_and_sit)[0]

        onset_mask = near_chair & (yprime <= -sit_pos_thr)
        onset_candidates = np.where(onset_mask)[0]

        laps_list: List[Lap] = []

        for ls, le in zip(leave_starts, leave_ends):
            # 這段離椅期間有沒有在 cone zone 停留夠久
            idx = np.where(cone_valid[ls: le + 1])[0]
            if idx.size == 0:
                continue
            t_cone = ls + idx[0]

            # ---------- 起身段（離椅） ----------
            j = np.searchsorted(onset_candidates, ls, side="left") - 1
            if j >= onset_candidates.size or j < 0:
                continue

            j_start = j
            while ((j_start - 1) >= 0) and (
                (onset_candidates[j_start] - onset_candidates[j_start - 1]) <= group_gap_frames
            ):
                j_start -= 1
            onset_start_idx = int(onset_candidates[j_start])

            j_end = j
            while ((j_end + 1) < onset_candidates.size) and (
                (onset_candidates[j_end + 1] - onset_candidates[j_end]) <= group_gap_frames
            ):
                j_end += 1
            onset_end_idx = int(onset_candidates[j_end])

            # ---------- 回到椅區 + 坐下 ----------
            j = np.searchsorted(chair_sit_idx, t_cone, side="left")
            if j >= chair_sit_idx.size or j < 0:
                continue

            j_end = j
            while ((j_end + 1) < chair_sit_idx.size) and (
                (chair_sit_idx[j_end + 1] - chair_sit_idx[j_end]) <= group_gap_frames
            ):
                j_end += 1
            chair_sit_end_idx = int(chair_sit_idx[j_end])

            j_start = j
            while ((j_start - 1) >= 0) and (
                (chair_sit_idx[j_start] - chair_sit_idx[j_start - 1]) <= group_gap_frames
            ):
                j_start -= 1
            chair_sit_start_idx = int(chair_sit_idx[j_start])

            # 延伸坐下結束點，直到 y' 接近 0
            while (chair_sit_end_idx < N - 1) and (yprime[chair_sit_end_idx] > sit_pos_thr * 0.8):
                chair_sit_end_idx += 1

            # 起身開始點往前找，確保往下動作開始被包含
            while (chair_sit_start_idx > 0) and (yprime[chair_sit_start_idx] > -sit_pos_thr * 1.2):
                chair_sit_start_idx -= 1

            # cone zone 連續 True 片段
            cone_entry_idx, cone_exit_idx = contiguous_run_bounds(
                near_cone,
                t_cone,
            )

            # ---------- A：錐區轉彎（用骨盆角度斜率） ----------
            turn_cone_start_idx, turn_cone_end_idx, slope_cone = detect_turn_window_by_heading(
                theta=theta,
                seg_start=int(cone_entry_idx),
                seg_end=int(cone_exit_idx),
                flat_frac=flat_frac,
                min_v_abs=min_v_abs,
                min_width_frames=min_width_frames,
            )
            dir_cone = turn_dir_from_slope(slope_cone)
            delta_cone = theta[turn_cone_end_idx] - theta[turn_cone_start_idx]

            # ---------- B：椅子附近轉身（用骨盆角度斜率） ----------
            reenter_idx = int(le)
            j = np.searchsorted(chair_sit_idx, reenter_idx, side="left")
            if j >= chair_sit_idx.size or j < 0:
                continue
            sit_start_idx = int(chair_sit_idx[j])

            turn_chair_start_idx, turn_chair_end_idx, slope_chair = detect_turn_window_by_heading(
                theta=theta,
                seg_start=int(reenter_idx),
                seg_end=int(sit_start_idx),
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
                pt_cone_turn_start = C2[turn_cone_start_idx]
                pt_cone_turn_end = C2[turn_cone_end_idx]
                dist_cone_turn_chord_m = float(
                    np.linalg.norm(pt_cone_turn_end - pt_cone_turn_start)
                )
                dist_cone_turn_path_m = seg_path_len(
                    C2,
                    turn_cone_start_idx,
                    turn_cone_end_idx,
                )
                dist_outbound_m = seg_path_len(C2, ls, turn_cone_start_idx)
                dist_return_m = seg_path_len(
                    C2,
                    turn_cone_end_idx,
                    turn_chair_start_idx,
                )
                dist_turn_to_sit_m = seg_path_len(
                    C2,
                    turn_chair_start_idx,
                    turn_chair_end_idx,
                )
                dist_lap_path_m = dist_outbound_m + dist_cone_turn_path_m + dist_return_m + dist_turn_to_sit_m
                dist_chair_cone_centers_m = float(
                    np.linalg.norm(cone_pos - chair_pos)
                )
                laps_list.append(
                    Lap(
                        ts_start=float(ts_start),
                        ts_end=float(ts_end),
                        dur_total=float(dur_total),
                        idx_start=int(onset_start_idx),
                        idx_end=int(chair_sit_end_idx),
                        idx_onset_start=int(onset_start_idx),
                        idx_onset_end=int(onset_end_idx),
                        idx_chair_sit_end=int(chair_sit_end_idx),
                        idx_chair_sit_start=int(chair_sit_start_idx),
                        idx_leave_chair=int(onset_end_idx),
                        idx_reenter_chair=int(reenter_idx),
                        idx_enter_cone=int(cone_entry_idx),
                        idx_exit_cone=int(cone_exit_idx),
                        idx_sit_start=int(sit_start_idx),
                        idx_turn_cone_start=int(turn_cone_start_idx),
                        idx_turn_cone_end=int(turn_cone_end_idx),
                        idx_turn_chair_start=int(turn_chair_start_idx),
                        idx_turn_chair_end=int(turn_chair_end_idx),
                        dur_stand=float(dur_stand),
                        dur_to_cone=float(dur_to_cone),
                        dur_cone_turn=float(dur_cone_turn),
                        dur_return=float(dur_return),
                        dur_turn_to_sit=float(dur_turn_to_sit),
                        dur_sit=float(dur_sit),
                        ts_turn_cone_start=float(ts_turn_cone_start),
                        ts_turn_cone_end=float(ts_turn_cone_end),
                        ts_turn_chair_start=float(ts_turn_chair_start),
                        ts_turn_chair_end=float(ts_turn_chair_end),
                        dist_cone_turn_chord_m=float(dist_cone_turn_chord_m),
                        dist_cone_turn_path_m=float(dist_cone_turn_path_m),
                        dist_outbound_m=float(dist_outbound_m),
                        dist_return_m=float(dist_return_m),
                        dist_lap_path_m=float(dist_lap_path_m),
                        dist_turn_to_sit_m=float(dist_turn_to_sit_m),
                        dist_chair_cone_centers_m=float(
                            dist_chair_cone_centers_m
                        ),
                        turn_cone_dir=dir_cone,
                        turn_chair_dir=dir_chair,
                        delta_theta_cone_deg=delta_cone,
                        delta_theta_chair_deg=delta_chair,
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


# 步態分析

