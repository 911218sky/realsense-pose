"""步態分析工具（步頻、步長、站立/擺動期）。"""

from functools import partial
from operator import attrgetter
from typing import Tuple

import numpy as np
from cachetools import cachedmethod
from scipy.signal import butter, filtfilt, find_peaks

from .entities import FootStepCycle, GaitSummary, IntervalGaitMetrics
from .constants import (
    DEFAULT_FLAT_FRAC,
    DEFAULT_INTERVAL_SEC,
    DEFAULT_MIN_V_ABS,
    DEFAULT_PROJECTION,
    DEFAULT_SMOOTH_WINDOW_S,
    MIN_STEP_DISTANCE_RATIO,
    PROMINENCE_MULTIPLIER,
    STEP_MERGE_TOLERANCE_RATIO,
    MIN_STEP_INTERVAL_RATIO,
)

from .cache_keys import method_key
from .lap_detector import LapDetector

class GaitAnalyzer(LapDetector):
    """計算雙側步態（步頻、步長、站立 / 擺動期）與分段統計。"""

    @cachedmethod(attrgetter("cache"), key=partial(method_key, "compute_gait_summary"))
    def compute_gait_summary(
        self,
        projection: str = DEFAULT_PROJECTION,
        smooth_window_s: float = DEFAULT_SMOOTH_WINDOW_S,
        flat_frac: float = DEFAULT_FLAT_FRAC,
        min_v_abs: float = DEFAULT_MIN_V_ABS,
        *,
        interval_sec: float = DEFAULT_INTERVAL_SEC,
        skip_steps_after_span_start: int = 0,
        skip_steps_before_span_end: int = 0,
    ) -> GaitSummary:
        """計算步態摘要與每分鐘區間指標。

        主要流程：
        * 用腳跟 z 殘差 + 前進速度兩種訊號找 HS/TO
        * 根據步頻粗估結果調整 peak distance / prominence
        * 只在直線段（由圈數分析決定）上統計步態指標
        """
        xyz = self.arr[:, :33, :]
        xzL = xyz[:, self.L_HEEL][:, (0, 2)]
        xzR = xyz[:, self.R_HEEL][:, (0, 2)]

        N = int(self.arr.shape[0])
        t = self.t.astype(float)
        fps = float(self._estimate_fps())

        # 這裡用最小步長 1/fps 矯正成單調遞增的 t，僅用於梯度計算。
        if t.size >= 2:
            eps = 1.0 / max(fps, 1e-6)
            for i in range(1, t.size):
                if t[i] <= t[i - 1]:
                    t[i] = t[i - 1] + eps
        
        # 將秒轉換成帧數
        smooth_window = max(1, int(round(smooth_window_s * fps)))

        # 平滑腳跟 XZ 座標，降低抖動
        xzL = self._moving_average(xzL, smooth_window)
        xzR = self._moving_average(xzR, smooth_window)

        # 以 z 軸殘差偵測腳跟觸地 / 離地事件
        resL = xzL[:, 1]
        resR = xzR[:, 1]

        # HS ≈ 殘差極小值（-res 的峰）
        # TO ≈ 殘差極大值（+res 的峰）
        idx_LHS_res: np.ndarray = find_peaks(-resL)[0]
        idx_RHS_res: np.ndarray = find_peaks(-resR)[0]
        idx_LTO_res: np.ndarray = find_peaks(+resL)[0]
        idx_RTO_res: np.ndarray = find_peaks(+resR)[0]

        # 以腳跟前進速度作為另一組事件候選
        vzL = np.gradient(xzL[:, 1], t)
        vzR = np.gradient(xzR[:, 1], t)

        def bandpass(
            sig: np.ndarray,
            fs: float,
            band: Tuple[float, float] = (0.5, 5.0),
            order: int = 2,
        ) -> np.ndarray:
            """對訊號做簡單帶通濾波（約 0.5-5 Hz）。"""
            lo_n = max(band[0] / (fs / 2.0), 1e-6)
            hi_n = min(band[1] / (fs / 2.0), 0.999999)
            if hi_n <= lo_n + 1e-6:
                # 若 fs 太低導致無法設計帶通，退回去趨勢
                return sig - np.median(sig)
            b, a = butter(order, [lo_n, hi_n], btype="band")
            return filtfilt(b, a, sig, method="gust")

        vzL_f = bandpass(vzL, fps)
        vzR_f = bandpass(vzR, fps)

        def rough_spm(sig: np.ndarray, fs: float) -> float:
            """用自相關粗估步頻（steps/min）。"""
            x = sig - np.median(sig)
            if x.size < int(0.5 * fs) + 3:
                return 0.0
            ac = np.correlate(x, x, mode="full")[len(x) - 1 :]

            min_lag = int(0.25 * fs)
            max_lag = int(2.0 * fs)
            if max_lag <= min_lag + 3:
                return 0.0

            k = min_lag + int(np.argmax(ac[min_lag:max_lag]))
            if k <= 0:
                return 0.0

            step_time = k / fs
            return 60.0 / max(step_time, 1e-6)

        spm_guess_L = rough_spm(vzL_f, fps)
        spm_guess_R = rough_spm(vzR_f, fps)
        spm_guess = float(np.max([spm_guess_L, spm_guess_R, 100.0]))

        # 根據估計步頻限制峰距
        min_dist = int(max(1, MIN_STEP_DISTANCE_RATIO * (60.0 / spm_guess) * fps))

        def adaptive_peaks(x: np.ndarray, distance: int) -> np.ndarray:
            """依據 MAD 自動決定 prominence 的 peak 拿取函式。"""
            mad = np.median(np.abs(x - np.median(x))) + 1e-9
            prom = PROMINENCE_MULTIPLIER * mad
            idx, _ = find_peaks(x, distance=max(1, distance), prominence=prom)
            return idx.astype(int)

        # 在速度訊號上找 HS/TO 候選
        idx_LHS_v = adaptive_peaks(-vzL_f, distance=min_dist)
        idx_RHS_v = adaptive_peaks(-vzR_f, distance=min_dist)
        idx_LTO_v = adaptive_peaks(+vzL_f, distance=min_dist)
        idx_RTO_v = adaptive_peaks(+vzR_f, distance=min_dist)

        def merge_events(
            a: np.ndarray,
            b: np.ndarray,
            tol_frames: int,
        ) -> np.ndarray:
            """合併兩組事件索引，時間上相近者視為同一事件。"""
            if a.size == 0 and b.size == 0:
                return np.array([], dtype=int)
            all_idx = np.sort(np.unique(np.concatenate([a, b]).astype(int)))
            if all_idx.size <= 1:
                return all_idx

            keep = [int(all_idx[0])]
            for j in all_idx[1:]:
                if (j - keep[-1]) <= tol_frames:
                    keep[-1] = int(j)
                else:
                    keep.append(int(j))
            return np.asarray(keep, dtype=int)

        tol_merge = int(max(1, STEP_MERGE_TOLERANCE_RATIO * (60.0 / spm_guess) * fps))
        idx_LHS = merge_events(idx_LHS_res, idx_LHS_v, tol_frames=tol_merge)
        idx_RHS = merge_events(idx_RHS_res, idx_RHS_v, tol_frames=tol_merge)
        idx_LTO = merge_events(idx_LTO_res, idx_LTO_v, tol_frames=tol_merge)
        idx_RTO = merge_events(idx_RTO_res, idx_RTO_v, tol_frames=tol_merge)

        def prune_too_close(idxs: np.ndarray, min_frames: int) -> np.ndarray:
            """移除距離太近的事件（避免過度密集）。"""
            if idxs.size <= 1:
                return idxs
            out = [int(idxs[0])]
            for j in idxs[1:]:
                if int(j) - out[-1] >= min_frames:
                    out.append(int(j))
            return np.asarray(out, dtype=int)

        min_frames = int(max(1, MIN_STEP_INTERVAL_RATIO * (60.0 / spm_guess) * fps))
        idx_LHS = prune_too_close(idx_LHS, min_frames)
        idx_RHS = prune_too_close(idx_RHS, min_frames)
        idx_LTO = prune_too_close(idx_LTO, min_frames)
        idx_RTO = prune_too_close(idx_RTO, min_frames)

        # 由圈數偵測結果推導「直線步行區段」
        allowed_spans: list[tuple[int, int]] = []
        det = self.detect_laps_auto(
            projection=projection,
            smooth_window_s=smooth_window_s,
            flat_frac=flat_frac,
            min_v_abs=min_v_abs,
        )

        for lp in det.laps:
            i0 = int(np.clip(lp.idx_onset_end, 0, N - 1))
            i1 = int(np.clip(lp.idx_turn_cone_start, 0, N - 1))
            i2 = int(np.clip(lp.idx_turn_cone_end, 0, N - 1))
            i3 = int(np.clip(lp.idx_turn_chair_end, 0, N - 1))
            if i0 < i1:
                allowed_spans.append((i0, i1))
            if i2 < i3:
                allowed_spans.append((i2, i3))

        if not allowed_spans:
            allowed_spans = [(0, N - 1)]

        def filter_indices_in_spans(
            idxs: np.ndarray,
            spans: list[tuple[int, int]],
        ) -> np.ndarray:
            """只保留落在任一 span 內的事件索引。"""
            if idxs.size == 0 or not spans:
                return idxs[:0]
            masks = []
            for s, e in spans:
                masks.append((idxs >= s) & (idxs <= e))
            mask = np.logical_or.reduce(masks) if masks else np.zeros_like(
                idxs, bool
            )
            return idxs[mask]
        
        def skip_steps_near_span_edges(
            idxs: np.ndarray,
            spans: list[tuple[int, int]],
        ) -> np.ndarray:
            """在每個 span 內，丟掉前 skip_front 步與後 skip_back 步。"""
            if idxs.size == 0 or not spans:
                return idxs
            if skip_steps_after_span_start <= 0 and skip_steps_before_span_end <= 0:
                return idxs

            keep_mask = np.zeros_like(idxs, dtype=bool)
            for s, e in spans:
                m = (idxs >= s) & (idxs <= e)
                pos = np.flatnonzero(m)  # 這個 span 內的所有步在 idxs 中的位置
                if pos.size == 0:
                    continue

                # 要保留的區間：[skip_front, pos.size - skip_back)
                start = min(skip_steps_after_span_start, pos.size)
                end = max(start, pos.size - skip_steps_before_span_end)
                if end <= start:
                    continue

                keep_mask[pos[start:end]] = True

            return idxs[keep_mask]

        def intersect_spans(
            a: tuple[int, int],
            b: tuple[int, int],
        ) -> tuple[int, int] | None:
            """回傳兩個閉區間的交集，若無交集則回傳 None。"""
            s = max(a[0], b[0])
            e = min(a[1], b[1])
            return (s, e) if s <= e else None

        def clip_spans_to_window(
            spans: list[tuple[int, int]],
            i0: int,
            i1: int,
        ) -> list[tuple[int, int]]:
            """將 spans 裁切到 [i0, i1]，回傳交集區段。"""
            win_span = (i0, i1)
            out: list[tuple[int, int]] = []
            for s, e in spans:
                inter = intersect_spans((s, e), win_span)
                if inter is not None:
                    out.append(inter)
            return out

        def spans_seconds(
            spans: list[tuple[int, int]],
            t_arr: np.ndarray,
        ) -> float:
            """把索引區段換算成總秒數。"""
            if not spans:
                return 0.0
            return float(
                np.sum(
                    [
                        max(0.0, float(t_arr[e]) - float(t_arr[s]))
                        for s, e in spans
                    ]
                )
            )

        def in_same_span(
            a: int,
            b: int,
            spans: list[tuple[int, int]],
        ) -> bool:
            """判斷兩個 index 是否同時落在任一個 span 內。"""
            for s, e in spans:
                if s <= a <= e and s <= b <= e:
                    return True
            return False

        def step_lengths_cross_feet(
            curr_hs: np.ndarray,
            curr_xz: np.ndarray,
            partner_hs: np.ndarray,
            partner_xz: np.ndarray,
            spans: list[tuple[int, int]],
        ) -> np.ndarray:
            """
            計算「跨腳步長」：以前一腳（partner）HS 到當前腳（curr）HS
            之間的距離，代表 Left→Right 或 Right→Left 的步長。

            只保留：
                - partner HS 發生在 curr HS 之前
                - 兩個 HS 同時落在同一個 span 內（避免跨轉彎/禁區）
            """
            if curr_hs.size == 0 or partner_hs.size == 0 or not spans:
                return np.array([], dtype=float)

            # 對每個 curr HS 找「前一個」 partner HS
            j = np.searchsorted(partner_hs, curr_hs) - 1
            valid = j >= 0
            if not np.any(valid):
                return np.array([], dtype=float)

            curr_sel = curr_hs[valid]
            partner_sel = partner_hs[j[valid]]

            out: list[float] = []
            for a, b in zip(curr_sel, partner_sel):
                a_i = int(a)
                b_i = int(b)
                if b_i >= a_i:
                    continue
                if not in_same_span(a_i, b_i, spans):
                    continue
                d = float(np.linalg.norm(curr_xz[a_i] - partner_xz[b_i]))
                if d > 0:
                    out.append(d)

            return np.asarray(out, dtype=float) if out else np.array([], dtype=float)

        # ---------- overall（整體區段） ----------
        LHS_in = filter_indices_in_spans(idx_LHS, allowed_spans)
        RHS_in = filter_indices_in_spans(idx_RHS, allowed_spans)
        LTO_in = filter_indices_in_spans(idx_LTO, allowed_spans)
        RTO_in = filter_indices_in_spans(idx_RTO, allowed_spans)

        def prev_partner_times(
            curr_idx: np.ndarray,
            partner_idx: np.ndarray,
        ) -> np.ndarray:
            """給定一腳 HS 與另一腳 HS，回傳成對的時間差。"""
            if curr_idx.size == 0 or partner_idx.size == 0:
                return np.array([], dtype=float)

            j = np.searchsorted(partner_idx, curr_idx) - 1
            valid = j >= 0
            dt_ = t[curr_idx[valid]] - t[partner_idx[j[valid]]]
            return dt_[dt_ > 0]

        def cadence_from_step_times(step_times_s: np.ndarray) -> float:
            """由單步時間計算步頻（steps/min）。"""
            if step_times_s.size == 0:
                return 0.0
            mean_step = float(np.mean(step_times_s))
            return 60.0 / mean_step if mean_step > 0 else 0.0

        l_step_times = prev_partner_times(LHS_in, RHS_in)
        r_step_times = prev_partner_times(RHS_in, LHS_in)
        l_spm_overall = cadence_from_step_times(l_step_times)
        r_spm_overall = cadence_from_step_times(r_step_times)
        spm_overall = max(l_spm_overall, r_spm_overall)

        # 步長定義改為「跨腳步長」：左腳步長 = 右 HS → 左 HS 的距離；
        # 右腳步長 = 左 HS → 右 HS 的距離。
        l_step_len_all = step_lengths_cross_feet(
            curr_hs=LHS_in,
            curr_xz=xzL,
            partner_hs=RHS_in,
            partner_xz=xzR,
            spans=allowed_spans,
        )
        r_step_len_all = step_lengths_cross_feet(
            curr_hs=RHS_in,
            curr_xz=xzR,
            partner_hs=LHS_in,
            partner_xz=xzL,
            spans=allowed_spans,
        )
        l_mean_step_len = (
            float(np.mean(l_step_len_all)) if l_step_len_all.size else 0.0
        )
        r_mean_step_len = (
            float(np.mean(r_step_len_all)) if r_step_len_all.size else 0.0
        )
        mean_step_len = (l_mean_step_len + r_mean_step_len) / 2.0

        def compute_step_phases_single_foot(
            idx_HS: np.ndarray,
            idx_TO: np.ndarray,
        ) -> list[FootStepCycle]:
            """對單腳 HS / TO 組合計算各步期別。"""
            out: list[FootStepCycle] = []
            if idx_HS.size < 2 or idx_TO.size == 0:
                return out

            HS = filter_indices_in_spans(idx_HS, allowed_spans)
            TO = filter_indices_in_spans(idx_TO, allowed_spans)
            if HS.size < 2 or TO.size == 0:
                return out

            h0 = HS[:-1]
            h1 = HS[1:]

            i_to = np.searchsorted(TO, h0, side="right")
            has_cand = i_to < TO.size
            to_idx = np.full(h0.shape, -1, dtype=np.int64)
            to_idx[has_cand] = TO[i_to[has_cand]]

            for ii in range(h0.size):
                a = int(h0[ii])
                c = int(h1[ii])
                b = int(to_idx[ii])
                if b <= a or b >= c:
                    continue
                if not in_same_span(a, c, allowed_spans):
                    continue

                t_h0, t_to, t_h1 = t[a], t[b], t[c]
                stride = t_h1 - t_h0
                stance = t_to - t_h0
                swing = t_h1 - t_to
                eps = 1e-9
                swing_pct = 100.0 * (swing / max(stride + swing, eps))

                out.append(
                    FootStepCycle(
                        hs0_idx=a,
                        to_idx=b,
                        hs1_idx=c,
                        stride_s=float(stride),
                        stance_s=float(stance),
                        swing_s=float(swing),
                        swing_pct=float(np.clip(swing_pct, 0.0, 100.0)),
                    )
                )
            return out

        l_cycles = compute_step_phases_single_foot(LHS_in, LTO_in)
        r_cycles = compute_step_phases_single_foot(RHS_in, RTO_in)

        l_swing_pct_mean = (
            float(np.mean([c.swing_pct for c in l_cycles])) if l_cycles else 0.0
        )
        r_swing_pct_mean = (
            float(np.mean([c.swing_pct for c in r_cycles])) if r_cycles else 0.0
        )
        l_swing_s_mean = (
            float(np.mean([c.swing_s for c in l_cycles])) if l_cycles else 0.0
        )
        r_swing_s_mean = (
            float(np.mean([c.swing_s for c in r_cycles])) if r_cycles else 0.0
        )
        l_stance_s_mean = (
            float(np.mean([c.stance_s for c in l_cycles])) if l_cycles else 0.0
        )
        r_stance_s_mean = (
            float(np.mean([c.stance_s for c in r_cycles])) if r_cycles else 0.0
        )

        # ---------- 每分鐘區間統計 ----------
        per_interval: list[IntervalGaitMetrics] = []
        t0, t_end = float(t[0]), float(t[-1])
        edges = np.arange(t0, t_end + interval_sec, interval_sec, dtype=float)

        for k_idx in range(edges.size - 1):
            ta = float(edges[k_idx])
            tb = float(edges[k_idx + 1])

            i0 = int(np.searchsorted(t, ta, side="left"))
            i1 = int(np.searchsorted(t, tb, side="right") - 1)
            if i0 >= N or i1 <= i0:
                continue

            spans_win = clip_spans_to_window(allowed_spans, i0, i1)
            if not spans_win:
                continue
            
            # 跳過起始與結束的步數
            LHS_win = filter_indices_in_spans(idx_LHS, spans_win)
            RHS_win = filter_indices_in_spans(idx_RHS, spans_win)
            LTO_win = filter_indices_in_spans(idx_LTO, spans_win)
            RTO_win = filter_indices_in_spans(idx_RTO, spans_win)
            
            # 跳過起始與結束的步數
            LHS_win = skip_steps_near_span_edges(LHS_win, spans_win)
            RHS_win = skip_steps_near_span_edges(RHS_win, spans_win)
            LTO_win = skip_steps_near_span_edges(LTO_win, spans_win)
            RTO_win = skip_steps_near_span_edges(RTO_win, spans_win)

            # 計算有效步數
            dur_eff = spans_seconds(spans_win, t)
            lcnt = int(LHS_win.size)
            rcnt = int(RHS_win.size)

            l_spm_min = float(lcnt / dur_eff * 60.0) if dur_eff > 0 else 0.0
            r_spm_min = float(rcnt / dur_eff * 60.0) if dur_eff > 0 else 0.0
            spm_min = max(l_spm_min, r_spm_min)

            # 計算有效步長（跨腳步長，同 overall 定義）
            l_steps = step_lengths_cross_feet(
                curr_hs=LHS_win,
                curr_xz=xzL,
                partner_hs=RHS_win,
                partner_xz=xzR,
                spans=spans_win,
            )
            r_steps = step_lengths_cross_feet(
                curr_hs=RHS_win,
                curr_xz=xzR,
                partner_hs=LHS_win,
                partner_xz=xzL,
                spans=spans_win,
            )
            l_mean = float(np.mean(l_steps)) if l_steps.size else 0.0
            r_mean = float(np.mean(r_steps)) if r_steps.size else 0.0
            mean_step_len_min = (l_mean + r_mean) / 2.0

            # 計算有效步態
            steps_L = compute_step_phases_single_foot(LHS_win, LTO_win)
            steps_R = compute_step_phases_single_foot(RHS_win, RTO_win)

            l_swing_pct_mean_min = (
                float(np.mean([c.swing_pct for c in steps_L]))
                if steps_L
                else 0.0
            )
            r_swing_pct_mean_min = (
                float(np.mean([c.swing_pct for c in steps_R]))
                if steps_R
                else 0.0
            )
            l_swing_s_mean_min = (
                float(np.mean([c.swing_s for c in steps_L]))
                if steps_L
                else 0.0
            )
            r_swing_s_mean_min = (
                float(np.mean([c.swing_s for c in steps_R]))
                if steps_R
                else 0.0
            )
            l_stance_s_mean_min = (
                float(np.mean([c.stance_s for c in steps_L]))
                if steps_L
                else 0.0
            )
            r_stance_s_mean_min = (
                float(np.mean([c.stance_s for c in steps_R]))
                if steps_R
                else 0.0
            )

            per_interval.append(
                IntervalGaitMetrics(
                    interval_index=k_idx,
                    start_frame=i0,
                    end_frame=i1,
                    start_time_s=float(t[i0]),
                    end_time_s=float(t[i1]),
                    left_step_count=int(lcnt),
                    right_step_count=int(rcnt),
                    l_spm=float(l_spm_min),
                    r_spm=float(r_spm_min),
                    spm=float(spm_min),
                    l_mean_step_len_m=float(l_mean),
                    r_mean_step_len_m=float(r_mean),
                    mean_step_len_m=float(mean_step_len_min),
                    l_swing_pct_mean=float(l_swing_pct_mean_min),
                    r_swing_pct_mean=float(r_swing_pct_mean_min),
                    l_swing_s_mean=float(l_swing_s_mean_min),
                    r_swing_s_mean=float(r_swing_s_mean_min),
                    l_stance_s_mean=float(l_stance_s_mean_min),
                    r_stance_s_mean=float(r_stance_s_mean_min),
                )
            )

        return GaitSummary(
            l_spm=float(l_spm_overall),
            r_spm=float(r_spm_overall),
            spm=float(spm_overall),
            l_mean_step_len=float(l_mean_step_len),
            r_mean_step_len=float(r_mean_step_len),
            mean_step_len=float(mean_step_len),
            l_swing_pct_mean=float(l_swing_pct_mean),
            r_swing_pct_mean=float(r_swing_pct_mean),
            l_swing_s_mean=float(l_swing_s_mean),
            r_swing_s_mean=float(r_swing_s_mean),
            l_stance_s_mean=float(l_stance_s_mean),
            r_stance_s_mean=float(r_stance_s_mean),
            per_interval=per_interval,
        )


# ---------------------------------------------------------------------
# 頻譜分析
# ---------------------------------------------------------------------

