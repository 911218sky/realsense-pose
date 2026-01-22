from dataclasses import dataclass

@dataclass(frozen=True)
class FPSConfig:
    """根據 FPS 調整的參數設定"""
    
    # 髖點座標平滑視窗（秒）
    smooth_window_s: float
    
    # 需在錐區停留的秒數門檻
    cone_dwell_s: float
    
    # near chair/cone mask 的去抖動時間窗（秒）
    debounce_s: float
    
    # Y 高度差分平滑視窗（秒）
    ydiff_window_s: float
    
    # y' 門檻，絕對值大於此視為上下動作
    sit_pos_thr: float
    
    # 將候選 frame 聚成事件時允許的最大時間間隔（秒）
    group_gap_s: float
    
    # 角速度衰減到峰值的比例即視為轉彎結束
    flat_frac: float
    
    # 檢測轉彎時所需的最小角速度 (deg/s)
    min_v_abs: float
    
    # 轉彎區段至少要持續的秒數
    min_turn_width_s: float
    
    # 高帧率時角速度平滑視窗（秒）
    angular_velocity_smooth_s: float
    
    # lateral offset 平滑階數
    k_smooth: int


# =============================================================================
# 4 FPS 專用參數
# =============================================================================
# 低幀率特性：
# - 時間解析度低，每幀間隔 0.25 秒
# - 訊號較粗糙，需要較寬鬆的門檻
# - 平滑視窗換算成幀數較少

CONFIG_4FPS = FPSConfig(
    smooth_window_s=0.50,       # 2 幀
    cone_dwell_s=0.75,          # 3 幀，較寬鬆
    debounce_s=0.25,            # 1 幀
    ydiff_window_s=0.50,        # 2 幀
    sit_pos_thr=0.15,           # 低幀率訊號變化較大，門檻放寬
    group_gap_s=0.50,           # 2 幀
    flat_frac=0.6,              # 較短的轉彎區段（低解析度）
    min_v_abs=12.0,             # 較低門檻，對慢速轉彎更敏感
    min_turn_width_s=0.50,      # 2 幀
    angular_velocity_smooth_s=0.0,  # 不平滑（幀數太少）
    k_smooth=1,                 # 平滑階數
)


# =============================================================================
# 30 FPS 專用參數
# =============================================================================
# 高幀率特性：
# - 時間解析度高，每幀間隔 ~0.033 秒
# - 訊號較平滑，可使用較嚴格的門檻
# - 平滑視窗換算成幀數較多

CONFIG_30FPS = FPSConfig(
    smooth_window_s=0.25,       # 7-8 幀
    cone_dwell_s=0.60,          # 18 幀
    debounce_s=0.10,            # 3 幀
    ydiff_window_s=0.40,        # 12 幀
    sit_pos_thr=0.20,           # 標準門檻
    group_gap_s=0.25,           # 7-8 幀
    flat_frac=0.7,              # 適中的轉彎區段
    min_v_abs=15.0,             # 標準門檻
    min_turn_width_s=0.40,      # 12 幀
    angular_velocity_smooth_s=0.10,  # 3 幀平滑
    k_smooth=1,                 # 平滑階數
)


# =============================================================================
# 自動選擇 FPS 設定
# =============================================================================

def get_fps_config(fps: float) -> FPSConfig:
    """
    根據輸入的 FPS 自動選擇合適的參數設定。
    
    Parameters
    ----------
    fps : float
        影片或資料的幀率
        
    Returns
    -------
    FPSConfig
        對應的參數設定
        
    Examples
    --------
    >>> cfg = get_fps_config(4)
    >>> cfg.smooth_window_s
    0.5
    
    >>> cfg = get_fps_config(30)
    >>> cfg.smooth_window_s
    0.25
    """
    if fps <= 10:
        return CONFIG_4FPS
    else:
        return CONFIG_30FPS


def interpolate_fps_config(fps: float) -> FPSConfig:
    """
    根據 FPS 線性插值參數（介於 4 FPS 和 30 FPS 之間）。
    
    對於 fps < 4 使用 4 FPS 設定，fps > 30 使用 30 FPS 設定。
    """
    if fps <= 4:
        return CONFIG_4FPS
    if fps >= 30:
        return CONFIG_30FPS
    
    # 線性插值比例
    t = (fps - 4) / (30 - 4)
    
    def lerp(a: float, b: float) -> float:
        return a + (b - a) * t
    
    return FPSConfig(
        smooth_window_s=lerp(CONFIG_4FPS.smooth_window_s, CONFIG_30FPS.smooth_window_s),
        cone_dwell_s=lerp(CONFIG_4FPS.cone_dwell_s, CONFIG_30FPS.cone_dwell_s),
        debounce_s=lerp(CONFIG_4FPS.debounce_s, CONFIG_30FPS.debounce_s),
        ydiff_window_s=lerp(CONFIG_4FPS.ydiff_window_s, CONFIG_30FPS.ydiff_window_s),
        sit_pos_thr=lerp(CONFIG_4FPS.sit_pos_thr, CONFIG_30FPS.sit_pos_thr),
        group_gap_s=lerp(CONFIG_4FPS.group_gap_s, CONFIG_30FPS.group_gap_s),
        flat_frac=lerp(CONFIG_4FPS.flat_frac, CONFIG_30FPS.flat_frac),
        min_v_abs=lerp(CONFIG_4FPS.min_v_abs, CONFIG_30FPS.min_v_abs),
        min_turn_width_s=lerp(CONFIG_4FPS.min_turn_width_s, CONFIG_30FPS.min_turn_width_s),
        angular_velocity_smooth_s=lerp(CONFIG_4FPS.angular_velocity_smooth_s, CONFIG_30FPS.angular_velocity_smooth_s),
        k_smooth=round(lerp(CONFIG_4FPS.k_smooth, CONFIG_30FPS.k_smooth)),
    )


# =============================================================================
# FPS 無關的固定常數（向後相容用）
# =============================================================================

# 默認投影平面 (xz / xy)
DEFAULT_PROJECTION = "xz"

# 每分鐘區間長度（秒）
DEFAULT_INTERVAL_SEC = 60.0

# 默認 DPI
DEFAULT_DPI = 150

# FFT 頻帶
DEFAULT_FFT_BAND = (0.00, 2.0)

# =============================================================================
# 步態分析常數
# =============================================================================

# 最小步距比例：計算步態事件的最小間隔
# min_dist = MIN_STEP_DISTANCE_RATIO * (60.0 / spm_guess) * fps
MIN_STEP_DISTANCE_RATIO = 0.4

# 峰值突出度乘數：自適應峰值檢測
# prominence = PROMINENCE_MULTIPLIER * MAD
PROMINENCE_MULTIPLIER = 2.5

# 步態事件合併容差比例：合併相近的步態事件
# tol_merge = STEP_MERGE_TOLERANCE_RATIO * (60.0 / spm_guess) * fps
STEP_MERGE_TOLERANCE_RATIO = 0.15

# 最小步態事件間隔比例：過濾過於密集的事件
# min_frames = MIN_STEP_INTERVAL_RATIO * (60.0 / spm_guess) * fps
MIN_STEP_INTERVAL_RATIO = 0.25

# =============================================================================
# 圈數偵測常數
# =============================================================================

# 離椅最短持續時間比例：離椅期間至少要持續的幀數比例
# leave_run_needed = LEAVE_RUN_NEEDED_RATIO * fps
LEAVE_RUN_NEEDED_RATIO = 0.25

# 視覺化常數
METERS_GAP_DEFAULT = 0.08  # 距離標籤間隔（公尺）
MIN_METERS_TO_SHOW = 0.03  # 最小顯示距離（公尺）


CONFIG_DEFAULT = CONFIG_4FPS

DEFAULT_SMOOTH_WINDOW_S = CONFIG_DEFAULT.smooth_window_s
DEFAULT_CONE_DWELL_S = CONFIG_DEFAULT.cone_dwell_s
DEFAULT_DEBOUNCE_S = CONFIG_DEFAULT.debounce_s
DEFAULT_YDIFF_WINDOW_S = CONFIG_DEFAULT.ydiff_window_s
DEFAULT_SIT_POS_THR = CONFIG_DEFAULT.sit_pos_thr
DEFAULT_GROUP_GAP_S = CONFIG_DEFAULT.group_gap_s
DEFAULT_FLAT_FRAC = CONFIG_DEFAULT.flat_frac
DEFAULT_MIN_V_ABS = CONFIG_DEFAULT.min_v_abs
DEFAULT_MIN_TURN_WIDTH_S = CONFIG_DEFAULT.min_turn_width_s
DEFAULT_ANGULAR_VELOCITY_SMOOTH_S = CONFIG_DEFAULT.angular_velocity_smooth_s
DEFAULT_K_SMOOTH = CONFIG_DEFAULT.k_smooth