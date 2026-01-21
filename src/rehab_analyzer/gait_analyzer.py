"""步態分析工具（步頻、步長、站立/擺動期）。"""

from functools import partial
from operator import attrgetter
from typing import Tuple

import numpy as np
from cachetools import cachedmethod
from scipy.signal import butter, filtfilt, find_peaks

from .entities import FootStepCycle, GaitCyclePhases, GaitSummary, IntervalGaitMetrics
from .constants import (
    DEFAULT_FLAT_FRAC,
    DEFAULT_INTERVAL_SEC,
    DEFAULT_MIN_V_ABS,
    DEFAULT_PROJECTION,
    DEFAULT_SMOOTH_WINDOW_S,
)

from .cache_keys import method_key
from .lap_detector import LapDetector


class GaitAnalyzer(LapDetector):
    """計算雙側步態（步頻、步長、站立 / 擺動期）與分段統計。"""

    # 關節索引
    L_TOE = 31  # LEFT_FOOT_INDEX
    R_TOE = 32  # RIGHT_FOOT_INDEX

    def _bandpass(
        self,
        sig: np.ndarray,
        fs: float,
        band: Tuple[float, float] = (0.3, 5.0),
    ) -> np.ndarray:
        """帶通濾波。"""
        lo_n = max(band[0] / (fs / 2.0), 1e-6)
        hi_n = min(band[1] / (fs / 2.0), 0.999999)
        if hi_n <= lo_n + 1e-6:
            return sig - np.median(sig)
        b, a = butter(2, [lo_n, hi_n], btype="band")  # type: ignore[misc]
        return filtfilt(b, a, sig, method="gust")

    def _estimate_cadence(self, sig: np.ndarray, fs: float) -> float:
        """用自相關粗估步頻（steps/min）。"""
        x = sig - np.median(sig)
        if x.size < int(0.5 * fs) + 3:
            return 80.0
        ac = np.correlate(x, x, mode="full")[len(x) - 1:]
        min_lag, max_lag = int(0.25 * fs), int(2.0 * fs)
        if max_lag <= min_lag + 3:
            return 80.0
        k = min_lag + int(np.argmax(ac[min_lag:max_lag]))
        return 60.0 / (k / fs) if k > 0 else 80.0

    def _detect_hs_to(
        self,
        heel_y: np.ndarray,
        toe_y: np.ndarray,
        fps: float,
        min_distance: int,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        使用腳跟高度最低點偵測 HS，腳趾高度上升速度峰偵測 TO。
        
        步態週期時序：
        - HS (0%): 腳跟著地 → 腳跟高度最低
        - TO (60%): 腳趾離地 → 腳趾高度開始快速上升
        
        正常步態中，stance ≈ 60%，swing ≈ 40%
        
        TO 偵測策略：以腳趾高度上升速度的峰值為主，
        若找不到峰值，再退回腳趾最低點或估算位置。
        """
        # 平滑處理
        smooth_win = max(3, int(0.05 * fps))
        heel_smooth = self._moving_average(heel_y.reshape(-1, 1), smooth_win).flatten()
        toe_smooth = self._moving_average(toe_y.reshape(-1, 1), smooth_win).flatten()
        
        # 帶通濾波
        heel_f = self._bandpass(heel_smooth, fps, band=(0.3, 4.0))
        toe_f = self._bandpass(toe_smooth, fps, band=(0.3, 4.0))
        toe_vel = np.gradient(toe_smooth) * fps
        toe_vel_f = self._bandpass(toe_vel, fps, band=(0.5, 6.0))
        
        mad_heel = np.median(np.abs(heel_f - np.median(heel_f))) + 1e-9
        mad_toe = np.median(np.abs(toe_f - np.median(toe_f))) + 1e-9
        mad_vel = np.median(np.abs(toe_vel_f - np.median(toe_vel_f))) + 1e-9
        
        # HS: 腳跟高度最低點
        idx_hs, _ = find_peaks(-heel_f, distance=min_distance, prominence=mad_heel * 0.25)
        
        # 腳趾高度最低點（候選 TO，備援）
        idx_toe_min, _ = find_peaks(-toe_f, distance=min_distance, prominence=mad_toe * 0.20)
        # 腳趾上升速度峰值（主要 TO）
        idx_toe_vel, _ = find_peaks(toe_vel_f, distance=min_distance, prominence=mad_vel * 0.20)
        
        idx_to_list = []
        for i in range(len(idx_hs) - 1):
            hs0, hs1 = idx_hs[i], idx_hs[i + 1]
            cycle_len = hs1 - hs0
            
            # TO 應該在 HS 後 55-85% 位置
            to_min_pos = hs0 + int(cycle_len * 0.55)
            to_max_pos = hs0 + int(cycle_len * 0.85)
            
            # 先找這個範圍內的腳趾上升速度峰值
            candidates_vel = idx_toe_vel[(idx_toe_vel > to_min_pos) & (idx_toe_vel < to_max_pos)]
            if len(candidates_vel) > 0:
                # 取最接近 68% 位置的
                target = hs0 + int(cycle_len * 0.68)
                best = candidates_vel[np.argmin(np.abs(candidates_vel - target))]
                idx_to_list.append(best)
            else:
                # 找不到速度峰則退回腳趾最低點
                candidates_min = idx_toe_min[(idx_toe_min > to_min_pos) & (idx_toe_min < to_max_pos)]
                if len(candidates_min) > 0:
                    target = hs0 + int(cycle_len * 0.68)
                    best = candidates_min[np.argmin(np.abs(candidates_min - target))]
                    idx_to_list.append(best)
                else:
                    # 如果都沒有找到，用估算值
                    idx_to_list.append(hs0 + int(cycle_len * 0.68))
        
        idx_to = np.array(idx_to_list, dtype=int) if idx_to_list else np.array([], dtype=int)
        
        return idx_hs.astype(int), idx_to

    def _enforce_alternation(
        self,
        idx_hs: np.ndarray,
        idx_to: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """確保 HS 和 TO 交替出現（HS → TO → HS → TO...）。"""
        if idx_hs.size == 0 or idx_to.size == 0:
            return idx_hs, idx_to
        
        all_events = [(int(i), 'HS') for i in idx_hs] + [(int(i), 'TO') for i in idx_to]
        all_events.sort(key=lambda x: x[0])
        
        hs_list, to_list = [], []
        last_type = None
        for idx, evt_type in all_events:
            if evt_type == 'HS' and last_type != 'HS':
                hs_list.append(idx)
                last_type = 'HS'
            elif evt_type == 'TO' and last_type == 'HS':
                to_list.append(idx)
                last_type = 'TO'
        
        return np.array(hs_list, dtype=int), np.array(to_list, dtype=int)

    def _filter_in_spans(
        self,
        idxs: np.ndarray,
        spans: list[tuple[int, int]],
    ) -> np.ndarray:
        """只保留落在任一 span 內的索引。"""
        if idxs.size == 0 or not spans:
            return idxs[:0]
        masks = [(idxs >= s) & (idxs <= e) for s, e in spans]
        return idxs[np.logical_or.reduce(masks)]

    def _in_same_span(
        self,
        a: int,
        b: int,
        spans: list[tuple[int, int]],
    ) -> bool:
        """判斷兩個 index 是否在同一個 span 內。"""
        return any(s <= a <= e and s <= b <= e for s, e in spans)

    def _get_allowed_spans(
        self,
        projection: str,
        smooth_window_s: float,
        flat_frac: float,
        min_v_abs: float,
    ) -> list[tuple[int, int]]:
        """取得直線步行區段（排除轉彎）。"""
        N = int(self.arr.shape[0])
        det = self.detect_laps_auto(
            projection=projection,
            smooth_window_s=smooth_window_s,
            flat_frac=flat_frac,
            min_v_abs=min_v_abs,
        )
        
        spans: list[tuple[int, int]] = []
        for lp in det.laps:
            i0 = int(np.clip(lp.idx_onset_end, 0, N - 1))
            i1 = int(np.clip(lp.idx_turn_cone_start, 0, N - 1))
            i2 = int(np.clip(lp.idx_turn_cone_end, 0, N - 1))
            i3 = int(np.clip(lp.idx_turn_chair_end, 0, N - 1))
            if i0 < i1:
                spans.append((i0, i1))
            if i2 < i3:
                spans.append((i2, i3))
        
        return spans if spans else [(0, N - 1)]

    # ========== 主要公開方法 ==========

    @cachedmethod(attrgetter("cache"), key=partial(method_key, "compute_gait_summary"))
    def compute_gait_summary(
        self,
        projection: str = DEFAULT_PROJECTION,
        smooth_window_s: float = DEFAULT_SMOOTH_WINDOW_S,
        flat_frac: float = DEFAULT_FLAT_FRAC,
        min_v_abs: float = DEFAULT_MIN_V_ABS,
        *,
        interval_sec: float = DEFAULT_INTERVAL_SEC,
    ) -> GaitSummary:
        """計算步態摘要。
        
        使用腳跟-腳趾高度差檢測 HS/TO，只在直線段統計。
        """
        xyz = self.arr[:, :33, :]
        N = int(xyz.shape[0])
        t = self.t.astype(float)
        fps = float(self._estimate_fps())
        
        # 修正時間戳單調性
        eps = 1.0 / max(fps, 1e-6)
        for i in range(1, t.size):
            if t[i] <= t[i - 1]:
                t[i] = t[i - 1] + eps
        
        smooth_win = max(1, int(round(smooth_window_s * fps)))
        
        # 取得腳跟/腳趾座標
        heel_L, heel_R = xyz[:, self.L_HEEL], xyz[:, self.R_HEEL]
        toe_L, toe_R = xyz[:, self.L_TOE], xyz[:, self.R_TOE]
        xzL = self._moving_average(heel_L[:, (0, 2)], smooth_win)
        xzR = self._moving_average(heel_R[:, (0, 2)], smooth_win)
        
        # 估計步頻並設定最小峰距
        heel_L_f = self._bandpass(heel_L[:, 1], fps)
        heel_R_f = self._bandpass(heel_R[:, 1], fps)
        spm_guess = max(self._estimate_cadence(heel_L_f, fps), self._estimate_cadence(heel_R_f, fps), 80.0)
        min_dist = int(max(1, (60.0 / (spm_guess * 1.5)) * fps * 0.35))
        
        # 檢測 HS/TO 並確保交替
        idx_LHS, idx_LTO = self._enforce_alternation(*self._detect_hs_to(
            heel_L[:, 1], toe_L[:, 1], fps, min_dist))
        idx_RHS, idx_RTO = self._enforce_alternation(*self._detect_hs_to(
            heel_R[:, 1], toe_R[:, 1], fps, min_dist))
        
        # 取得直線步行區段
        allowed_spans = self._get_allowed_spans(projection, smooth_window_s, flat_frac, min_v_abs)
        
        # 過濾到直線段內
        LHS_in = self._filter_in_spans(idx_LHS, allowed_spans)
        RHS_in = self._filter_in_spans(idx_RHS, allowed_spans)
        LTO_in = self._filter_in_spans(idx_LTO, allowed_spans)
        RTO_in = self._filter_in_spans(idx_RTO, allowed_spans)
        
        # 計算步頻（依照相鄰 HS 的步間時間）
        def cadence_from_intervals(step_times_s: np.ndarray) -> float:
            if step_times_s.size == 0:
                return 0.0
            median_step = float(np.median(step_times_s))
            return 60.0 / median_step if median_step > 0 else 0.0

        def collect_step_intervals(
            lhs: np.ndarray,
            rhs: np.ndarray,
            spans: list[tuple[int, int]],
        ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
            """收集相鄰 HS 的步間時間（總體、L、R）。"""
            events = [(int(i), "L") for i in lhs] + [(int(i), "R") for i in rhs]
            if len(events) < 2:
                empty = np.array([], dtype=float)
                return empty, empty, empty
            events.sort(key=lambda x: x[0])
            all_dt: list[float] = []
            l_dt: list[float] = []
            r_dt: list[float] = []
            prev_idx = events[0][0]
            for curr_idx, curr_side in events[1:]:
                if self._in_same_span(prev_idx, curr_idx, spans):
                    dt = float(t[curr_idx] - t[prev_idx])
                    if dt > 0:
                        all_dt.append(dt)
                        if curr_side == "L":
                            l_dt.append(dt)
                        else:
                            r_dt.append(dt)
                prev_idx = curr_idx
            return np.asarray(all_dt), np.asarray(l_dt), np.asarray(r_dt)

        all_dt, l_dt, r_dt = collect_step_intervals(LHS_in, RHS_in, allowed_spans)
        l_spm = cadence_from_intervals(l_dt)
        r_spm = cadence_from_intervals(r_dt)
        spm_overall = cadence_from_intervals(all_dt)
        
        # 計算步長（跨腳距離）
        def calc_step_len(curr_hs: np.ndarray, curr_xz: np.ndarray,
                          partner_hs: np.ndarray, partner_xz: np.ndarray) -> float:
            if curr_hs.size == 0 or partner_hs.size == 0:
                return 0.0
            j = np.searchsorted(partner_hs, curr_hs) - 1
            valid = j >= 0
            lengths = []
            for a, b in zip(curr_hs[valid], partner_hs[j[valid]]):
                if b < a and self._in_same_span(int(a), int(b), allowed_spans):
                    d = float(np.linalg.norm(curr_xz[a] - partner_xz[b]))
                    if d > 0:
                        lengths.append(d)
            return float(np.mean(lengths)) if lengths else 0.0
        
        l_step_len = calc_step_len(LHS_in, xzL, RHS_in, xzR)
        r_step_len = calc_step_len(RHS_in, xzR, LHS_in, xzL)
        
        # 計算步態週期（HS → TO → HS）
        def calc_cycles(hs: np.ndarray, to: np.ndarray) -> list[FootStepCycle]:
            cycles = []
            if hs.size < 2 or to.size == 0:
                return cycles
            
            for i in range(hs.size - 1):
                h0, h1 = int(hs[i]), int(hs[i + 1])
                # 找 h0 和 h1 之間的 TO
                to_between = to[(to > h0) & (to < h1)]
                if to_between.size == 0:
                    continue
                to_idx = int(to_between[0])
                
                if not self._in_same_span(h0, h1, allowed_spans):
                    continue
                
                stride = t[h1] - t[h0]
                stance = t[to_idx] - t[h0]
                swing = t[h1] - t[to_idx]
                swing_pct = 100.0 * (swing / max(stride, 1e-9))
                
                cycles.append(FootStepCycle(
                    hs0_idx=h0, to_idx=to_idx, hs1_idx=h1,
                    stride_s=float(stride), stance_s=float(stance),
                    swing_s=float(swing), swing_pct=float(np.clip(swing_pct, 0, 100)),
                ))
            return cycles
        
        l_cycles = calc_cycles(LHS_in, LTO_in)
        r_cycles = calc_cycles(RHS_in, RTO_in)
        
        # 計算平均值
        def mean_attr(cycles: list[FootStepCycle], attr: str) -> float:
            vals = [getattr(c, attr) for c in cycles]
            return float(np.mean(vals)) if vals else 0.0
        
        # 計算該時間區間內的步長
        def calc_step_len_win(
            curr_hs: np.ndarray,
            curr_xz: np.ndarray,
            partner_hs: np.ndarray,
            partner_xz: np.ndarray
        ) -> float:
            if curr_hs.size == 0 or partner_hs.size == 0:
                return 0.0
            j = np.searchsorted(partner_hs, curr_hs) - 1
            valid = j >= 0
            lengths = []
            for a, b in zip(curr_hs[valid], partner_hs[j[valid]]):
                if b < a and self._in_same_span(int(a), int(b), spans_win):
                    d = float(np.linalg.norm(curr_xz[a] - partner_xz[b]))
                    if d > 0:
                        lengths.append(d)
            return float(np.mean(lengths)) if lengths else 0.0
        
        # 每分鐘區間統計
        per_interval: list[IntervalGaitMetrics] = []
        t0, t_end = float(t[0]), float(t[-1])
        
        for k, ta in enumerate(np.arange(t0, t_end, interval_sec)):
            tb = ta + interval_sec
            i0 = int(np.searchsorted(t, ta, side="left"))
            i1 = int(np.searchsorted(t, tb, side="right") - 1)
            if i0 >= N or i1 <= i0:
                continue
            
            # 裁切 spans 到此區間
            spans_win = [(max(s, i0), min(e, i1)) for s, e in allowed_spans if s <= i1 and e >= i0]
            spans_win = [(s, e) for s, e in spans_win if s <= e]
            if not spans_win:
                continue
            
            dur = sum(t[e] - t[s] for s, e in spans_win)
            if dur <= 0:
                continue
            
            LHS_win = self._filter_in_spans(idx_LHS, spans_win)
            RHS_win = self._filter_in_spans(idx_RHS, spans_win)
            
            # 篩選該時間區間內的 cycles（使用 hs0_idx 判斷週期起始點是否在區間內）
            l_cycles_win = [c for c in l_cycles if i0 <= c.hs0_idx < i1]
            r_cycles_win = [c for c in r_cycles if i0 <= c.hs0_idx < i1]
            
            l_step_len_win = calc_step_len_win(LHS_win, xzL, RHS_win, xzR)
            r_step_len_win = calc_step_len_win(RHS_win, xzR, LHS_win, xzL)
            
            per_interval.append(IntervalGaitMetrics(
                interval_index=k,
                start_frame=i0, end_frame=i1,
                start_time_s=float(t[i0]), end_time_s=float(t[i1]),
                left_step_count=int(LHS_win.size), right_step_count=int(RHS_win.size),
                l_spm=float(LHS_win.size / dur * 60) if dur > 0 else 0.0,
                r_spm=float(RHS_win.size / dur * 60) if dur > 0 else 0.0,
                spm=float(max(LHS_win.size, RHS_win.size) / dur * 60) if dur > 0 else 0.0,
                l_mean_step_len_m=l_step_len_win, r_mean_step_len_m=r_step_len_win,
                mean_step_len_m=(l_step_len_win + r_step_len_win) / 2,
                l_swing_pct_mean=mean_attr(l_cycles_win, 'swing_pct'),
                r_swing_pct_mean=mean_attr(r_cycles_win, 'swing_pct'),
                l_swing_s_mean=mean_attr(l_cycles_win, 'swing_s'),
                r_swing_s_mean=mean_attr(r_cycles_win, 'swing_s'),
                l_stance_s_mean=mean_attr(l_cycles_win, 'stance_s'),
                r_stance_s_mean=mean_attr(r_cycles_win, 'stance_s'),
            ))
        
        return GaitSummary(
            l_spm=l_spm, r_spm=r_spm, spm=spm_overall,
            l_mean_step_len=l_step_len, r_mean_step_len=r_step_len,
            mean_step_len=(l_step_len + r_step_len) / 2,
            l_swing_pct_mean=mean_attr(l_cycles, 'swing_pct'),
            r_swing_pct_mean=mean_attr(r_cycles, 'swing_pct'),
            l_swing_s_mean=mean_attr(l_cycles, 'swing_s'),
            r_swing_s_mean=mean_attr(r_cycles, 'swing_s'),
            l_stance_s_mean=mean_attr(l_cycles, 'stance_s'),
            r_stance_s_mean=mean_attr(r_cycles, 'stance_s'),
            per_interval=per_interval,
            left_cycles=l_cycles,
            right_cycles=r_cycles,
        )

    @cachedmethod(attrgetter("cache"), key=partial(method_key, "compute_gait_cycle_phases"))
    def compute_gait_cycle_phases(
        self,
        projection: str = DEFAULT_PROJECTION,
        smooth_window_s: float = DEFAULT_SMOOTH_WINDOW_S,
        flat_frac: float = DEFAULT_FLAT_FRAC,
        min_v_abs: float = DEFAULT_MIN_V_ABS,
    ) -> tuple[GaitCyclePhases | None, GaitCyclePhases | None]:
        """計算左右腳步態週期相位百分比。
        
        從 FootStepCycle 計算 stance/swing 比例，
        雙支撐期用典型比例估算
        """
        summary = self.compute_gait_summary(
            projection=projection,
            smooth_window_s=smooth_window_s,
            flat_frac=flat_frac,
            min_v_abs=min_v_abs,
        )
        
        def calc_phases(cycles: list[FootStepCycle], side: str) -> GaitCyclePhases | None:
            # 過濾有效週期（0.5s ~ 3.0s）
            if not cycles:
                return None
            stride = np.asarray([c.stride_s for c in cycles], dtype=float)
            stance = np.asarray([c.stance_s for c in cycles], dtype=float)
            swing = np.asarray([c.swing_s for c in cycles], dtype=float)
            valid_mask = (stride >= 0.5) & (stride <= 3.0) & (stance > 0) & (swing > 0)
            n_valid = int(np.sum(valid_mask))
            if n_valid < 3:
                return None
            
            avg_stance = float(np.mean(stance[valid_mask]))
            avg_swing = float(np.mean(swing[valid_mask]))
            avg_cycle = float(np.mean(stride[valid_mask]))
            
            # 正確公式：擺動期/站立期應該用 stride（步態週期）作為分母
            # 正常步態：swing ≈ 40%, stance ≈ 60%
            swing_pct = (avg_swing / avg_cycle) * 100 if avg_cycle > 0 else 40.0
            stance_pct = (avg_stance / avg_cycle) * 100 if avg_cycle > 0 else 60.0
            
            # 雙支撐期估算：正常步態 DS 約佔 20%（DS1 + DS2 各 10%）
            # DS 約佔 stance 的 36%（55% stance × 0.36 ≈ 20% DS）
            ds_total = stance_pct * 0.36
            ds1_pct = ds2_pct = ds_total / 2
            ss_pct = stance_pct - ds1_pct - ds2_pct
            
            return GaitCyclePhases(
                side=side,
                ds1_pct=ds1_pct, single_support_pct=ss_pct, ds2_pct=ds2_pct,
                swing_pct=swing_pct, stance_pct=stance_pct,
                avg_cycle_time_s=avg_cycle, n_cycles=n_valid,
            )
        
        return (
            calc_phases(summary.left_cycles, 'L') if summary.left_cycles else None,
            calc_phases(summary.right_cycles, 'R') if summary.right_cycles else None,
        )
