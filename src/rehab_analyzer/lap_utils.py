"""圈數偵測輔助函數。

此模組包含從 lap_detector.py 提取的純函數工具，
用於遲滯 mask、路徑計算、轉彎方向判斷等。
"""

from typing import Tuple
import numpy as np


def hysteresis_mask(
    dist: np.ndarray,
    r_enter: float,
    r_exit: float,
) -> np.ndarray:
    """將距離轉成具有遲滯的進出區域布林 mask。
    
    Parameters
    ----------
    dist : np.ndarray
        距離序列
    r_enter : float
        進入區域的距離門檻
    r_exit : float
        離開區域的距離門檻（通常 > r_enter）
        
    Returns
    -------
    np.ndarray
        布林 mask，True 表示在區域內
        
    Raises
    ------
    ValueError
        如果 dist 不是 1D 陣列或 r_enter/r_exit 為負數
    """
    dist = np.asarray(dist, dtype=float)
    if dist.ndim != 1:
        raise ValueError(f"dist 必須是 1D 陣列，取得 ndim={dist.ndim}")
    if r_enter < 0 or r_exit < 0:
        raise ValueError(f"r_enter 和 r_exit 必須為非負數，取得 r_enter={r_enter}, r_exit={r_exit}")
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
    """找出包含某索引的連續 True 段落邊界 [lo, hi]。
    
    Parameters
    ----------
    mask : np.ndarray
        布林 mask
    center_idx : int
        中心索引
        
    Returns
    -------
    Tuple[int, int]
        (lo, hi) 邊界索引
    """
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
    """計算一段路徑的弧長（含端點）。
    
    Parameters
    ----------
    P : np.ndarray
        路徑點序列，形狀 (N, 2)
    start_idx : int
        起始索引
    end_idx : int
        結束索引
        
    Returns
    -------
    float
        路徑弧長（公尺）
        
    Raises
    ------
    ValueError
        如果 P 不是 2D 陣列
    """
    p = np.asarray(P, dtype=float)
    if p.ndim != 2:
        raise ValueError(f"P 必須是 2D 陣列，取得 ndim={P.ndim}")
    
    start_idx = max(0, int(start_idx))
    end_idx = max(0, int(end_idx))
    if end_idx <= start_idx:
        return 0.0

    seg = P[start_idx:end_idx]
    if seg.shape[0] < 2:
        return 0.0

    diffs = np.diff(seg, axis=0)
    return float(np.sum(np.linalg.norm(diffs, axis=1)))


def turn_dir_from_slope(a: float, *, min_abs_deg_per_s: float = 10.0) -> int:
    """根據斜率決定轉彎方向。
    
    Parameters
    ----------
    a : float
        角度變化斜率（度/秒）
    min_abs_deg_per_s : float
        最小有效斜率門檻
        
    Returns
    -------
    int
        +1: θ 隨時間增加（例如向左 / 逆時針）
        -1: θ 隨時間減少（例如向右 / 順時針）
        0: 幾乎沒轉（|a| 太小）
    """
    if not np.isfinite(a) or abs(a) < min_abs_deg_per_s:
        return 0
    return 1 if a > 0 else -1


def detect_turn_window_by_heading(
    theta: np.ndarray,
    t_arr: np.ndarray,
    seg_start: int,
    seg_end: int,
    fps: float,
    angular_velocity_smooth_s: float = 0.0,
    *,
    flat_frac: float = 0.5,
    min_v_abs: float = 15.0,
    max_v_abs: float = 60.0,
    min_width_frames: int = 5,
) -> Tuple[int, int, float]:
    """在 [seg_start, seg_end] 找轉彎區段。

    流程：
    1. 在該 segment 上看 Δθ 的正負，決定「主要轉彎方向」 dir_sign。
    2. 在 segment 上算角速度 v = dθ/dt，僅保留與 dir_sign 相同方向的部分。
    3. 在 v_dir 中找峰值，從峰值往左右擴展，直到 v_dir 掉到
       flat_frac * v_peak_dir 以下為止。
    4. 強制至少 min_width_frames，並對該段做線性回歸。

    Parameters
    ----------
    theta : np.ndarray
        解包後的骨盆朝向角序列（度）
    t_arr : np.ndarray
        時間序列（秒）
    seg_start : int
        區段起始索引
    seg_end : int
        區段結束索引
    fps : float
        幀率
    angular_velocity_smooth_s : float
        角速度平滑視窗（秒）
    flat_frac : float
        |v| < flat_frac * v_peak_dir 視為已變平
    min_v_abs : float
        峰值若小於這個，就當沒明顯轉彎
    max_v_abs : float
        峰值若大於這個，就當有明顯轉彎
    min_width_frames : int
        最短區段長度

    Returns
    -------
    Tuple[int, int, float]
        (全域 start_idx, 全域 end_idx, 斜率 slope_deg_per_s)
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
        return seg_start, seg_end, 0.0

    dir_sign = 1.0 if delta_total > 0.0 else -1.0

    # 計算角速度 v = dθ/dt（只在 segment 上）
    fps_local = float(fps)
    dt = 1.0 / max(1.0, fps_local)

    v = np.diff(theta_seg, prepend=theta_seg[0]) / dt
    if not np.isfinite(v).any():
        return seg_start, seg_end, 0.0

    # 高帧率時對角速度做平滑，避免噪聲影響
    v_smooth_window = max(1, int(round(angular_velocity_smooth_s * fps_local)))
    if v_smooth_window > 1 and n >= v_smooth_window:
        ker = np.ones(v_smooth_window) / v_smooth_window
        v = np.convolve(v, ker, mode="same")

    # 只保留「與整體方向一致」的角速度
    v_dir = v * dir_sign
    v_dir[~np.isfinite(v_dir)] = 0.0
    v_dir[v_dir < 0.0] = 0.0

    v_peak_dir = float(v_dir.max())
    if v_peak_dir < min_v_abs:
        return seg_start, seg_end, 0.0

    peak_idx_local = int(np.argmax(v_dir))

    # 設定「變平」門檻，從峰值往左右擴展
    flat_thr = max(min_v_abs, min(v_peak_dir * float(flat_frac), max_v_abs))

    lo = peak_idx_local
    while lo - 1 >= 0 and v_dir[lo - 1] >= flat_thr:
        lo -= 1

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
    t_seg = t_arr[seg_start: seg_end + 1].astype(float)
    t_win = t_seg[lo: hi + 1]
    y_win = theta_seg[lo: hi + 1]

    if t_win.size >= 2:
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
