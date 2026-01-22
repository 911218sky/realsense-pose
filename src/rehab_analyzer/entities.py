"""rehab_analyzer 模組的資料結構定義。

這裡集中放所有「對外傳遞」的 dataclass，設計原則：
- 欄位命名要能一眼看懂是什麼、單位是什麼
- 都有 to_dict() 方便轉 JSON 給 API 或前端用
- 只放資料結構，不放計算邏輯
"""

import numpy as np
from dataclasses import dataclass, asdict, field
from typing import List, Tuple, TypedDict

__all__ = [
    "Lap",
    "DetectLapsResult",
    "OffsetFFTResult",
    "FootStepCycle",
    "IntervalGaitMetrics",
    "GaitSummary",
    "GaitCyclePhases",
    "LapPhaseTimes",
    "SitStandEvent",
    "XYZPair",
]

@dataclass
class Lap:
    """單次 TUG-like 任務中的「一圈」分析結果。

    一圈通常包含：起身 → 走向錐子 → 錐子轉身 → 走回椅子 → 對位轉身 → 坐下。
    此結構會同時保存「事件索引（frame）」與「對應時間戳（秒）」及「距離/角度統計」。
    """
    # 基本時間與總覽
    ts_start: float        # 起身開始時間
    ts_end: float          # 坐下完成時間
    dur_total: float       # 總時間

    # 關鍵影格索引
    idx_start: int               # 起身開始
    idx_end: int                 # 坐下完成
    idx_onset_start: int         # 站起來的第一瞬間
    idx_onset_end: int           # 站起來的最後一瞬間
    idx_chair_sit_end: int       # 坐下的第一瞬間
    idx_chair_sit_start: int     # 坐下的最後一瞬間
    idx_leave_chair: int         # 離開椅子區域
    idx_reenter_chair: int       # 回到椅子區域
    idx_enter_cone: int          # 進入錐子區域
    idx_exit_cone: int           # 離開錐子區域
    idx_sit_start: int           # 準備坐下開始

    # 轉身（以臀距定義的轉身窗口）
    idx_turn_cone_start: int     # 在錐區內開始轉身
    idx_turn_cone_end: int       # 在錐區內結束轉身
    idx_turn_chair_start: int    # 在椅區內開始轉身
    idx_turn_chair_end: int      # 在椅區內結束轉身

    # 分段時長（秒）
    dur_stand: float        # 起身所花時間（離椅前）
    dur_to_cone: float      # 從離椅到進入錐區
    dur_cone_turn: float    # 在錐內轉彎（以轉身窗口或錐內停留定義）
    dur_return: float       # 從離開錐區到回到椅區
    dur_turn_to_sit: float  # 回椅後坐下前的轉身（椅邊轉身窗口）
    dur_sit: float          # 坐下所花時間

    # 轉身窗口的時間戳
    ts_turn_cone_start: float
    ts_turn_cone_end: float
    ts_turn_chair_start: float
    ts_turn_chair_end: float

    # 距離量測（公尺）
    dist_cone_turn_chord_m: float   # 錐內轉身窗口的直線距離（弦長），即錐內轉身窗口的兩端點之間的直線距離
    dist_cone_turn_path_m: float    # 錐內轉身窗口沿路徑的長度
    dist_outbound_m: float          # 離椅→錐區（至錐內轉身開始）的路徑長
    dist_return_m: float            # 錐內轉身結束→回椅（至椅邊轉身開始）的路徑長
    dist_turn_to_sit_m: float       # 椅邊轉身結束→坐下（至坐下開始）的路徑長
    dist_lap_path_m: float          # 整圈路徑長
    dist_chair_cone_centers_m: float# 椅心與錐心的固定直線距
    
    # 轉彎方向與整體角度變化
    turn_cone_dir: int              # 錐內轉彎方向：+1=θ 隨時間整體上升，-1=整體下降，0=幾乎沒轉
    turn_chair_dir: int             # 椅邊轉身方向：+1 / -1 / 0，定義同上
    delta_theta_cone_deg: float     # 錐內轉身窗口 θ 的淨變化量（end-start，單位：度）
    delta_theta_chair_deg: float    # 椅邊轉身窗口 θ 的淨變化量（end-start，單位：度）
    
    # 整圈方向判別
    lap_direction: str              # 整圈方向："clockwise"（順時針）、"counterclockwise"（逆時針）、"unknown"（無法判別）

    def to_dict(self) -> dict:
        """轉為可 JSON 序列化的 dict（numpy 以外的型別）。"""
        return asdict(self)

@dataclass
class DetectLapsResult:
    """圈數偵測結果。

    - `laps`：依序排列的圈資料
    - `chair_pos` / `cone_pos`：2D 投影平面（通常為 xz）下估計出來的中心點
    - `r_*`：進出區域半徑（含遲滯 enter/exit）
    """
    # 一圈段列表
    laps: List[Lap] = field(default_factory=list)  # 圈列表（每圈是一個 `Lap`）
    num_laps: int = 0  # 圈數（通常等於 len(laps)）

    # 椅子與錐子位置
    chair_pos: Tuple[float, float] = (0.0, 0.0)  # 椅子中心 (x, z) 或 (x, y)（視 projection）
    cone_pos: Tuple[float, float] = (0.0, 0.0)  # 錐子中心 (x, z) 或 (x, y)（視 projection）

    # 進/出椅距離 (圓有多大)
    r_chair_enter: float = 0.0  # 進入椅子區域半徑（公尺；enter 門檻）
    r_chair_exit: float = 0.0  # 離開椅子區域半徑（公尺；exit 門檻，通常 > enter）
    # 進/出錐距離 (圓有多大)
    r_cone_enter: float = 0.0  # 進入錐子區域半徑（公尺；enter 門檻）
    r_cone_exit: float = 0.0  # 離開錐子區域半徑（公尺；exit 門檻，通常 > enter）

    fps: float = 30.0  # 估計幀率（frames/sec）

    def to_dict(self) -> dict:
        """轉為可 JSON 序列化的 dict（包含 laps 的展開）。"""
        d = asdict(self)
        d["laps"] = [lap.to_dict() for lap in self.laps]
        return d

@dataclass
class OffsetFFTResult:
    """左右偏移（lateral offset）的 FFT/PSD 結果包。

    用途：
    - `FftAnalyzer.compute_lateral_offset_fft()` 會回傳此結構
    - API/Visualizer 常把它序列化後丟給前端畫頻譜
    """
    f: np.ndarray          # (nfreq,) 頻率（Hz）
    Pxx: np.ndarray        # (nfreq,) 單邊功率譜密度（視 scaling，常見為 spectrum/density）
    f_peak: float          # 主峰頻率（Hz；無有效頻譜時為 NaN）
    p_peak: float          # 主峰的 PSD 值（與 Pxx 同單位）

    def to_dict(self) -> dict:
        """轉為 dict（保留 numpy array；上層若要 JSON 需再轉成 list）。"""
        return asdict(self)

@dataclass
class FootStepCycle:
    """
    描述單腳一次「腳跟著地→腳趾離地→下一次腳跟著地」的完整週期。

    索引皆對應到原始序列 self.arr / self.t 的索引。
    時間長度為秒數；百分比為 0~100。
    """
    hs0_idx: int           # 本步開始：Heel-Strike(腳跟著地) 的影格索引
    to_idx: int            # 本步中段：Toe-Off(腳趾離地) 的影格索引
    hs1_idx: int           # 本步結束：下一次 Heel-Strike 的影格索引

    stride_s: float        # 一步的總時間（hs0→hs1）
    stance_s: float        # 支撐期（hs0→to）
    swing_s: float         # 擺動期（to→hs1）
    swing_pct: float       # 擺動期百分比（100 * swing_s / stride_s；已裁至 0~100）

    def to_dict(self) -> dict:
        """轉為可 JSON 序列化的 dict。"""
        return asdict(self)

@dataclass
class IntervalGaitMetrics:
    """
    描述某個時間區間內（例如 60 秒）的左右腳步態統計。
    建議 interval_index = 0,1,2,... 對應第幾個區間。
    """
    interval_index: int  # 第幾個區間（0-based）

    # 區間對應的資料邊界
    start_frame: int  # 起始 frame index（含）
    end_frame: int  # 結束 frame index
    start_time_s: float  # 區間起始時間（秒）
    end_time_s: float  # 區間結束時間（秒）

    # 步頻（steps/min）
    l_spm: float  # 左腳 steps/min
    r_spm: float  # 右腳 steps/min
    spm: float             # 整體步頻（通常取左右中較高者或自訂定義）

    # 平均步長（單步弧長；單位視你的 xz 座標單位而定，通常是公尺）
    l_mean_step_len_m: float  # 左腳平均步長（m）
    r_mean_step_len_m: float  # 右腳平均步長（m）
    mean_step_len_m: float  # 整體平均步長（m）

    # 期別統計（平均）
    l_swing_pct_mean: float  # 左腳擺動期百分比（0~100）
    r_swing_pct_mean: float  # 右腳擺動期百分比（0~100）
    l_swing_s_mean: float  # 左腳擺動期平均秒數
    r_swing_s_mean: float  # 右腳擺動期平均秒數
    l_stance_s_mean: float  # 左腳支撐期平均秒數
    r_stance_s_mean: float  # 右腳支撐期平均秒數

    # 保留步數，用於品質檢查或 UI 顯示
    left_step_count: int = 0  # 左腳步數（count）
    right_step_count: int = 0  # 右腳步數（count）
    
    def to_dict(self) -> dict:
        """轉為可 JSON 序列化的 dict。"""
        return asdict(self)

@dataclass
class GaitSummary:
    """
    全段紀錄的步態彙整 + 每個時間區間（例如每分鐘）的細項。
    """
    # overall 步頻（steps/min）
    l_spm: float  # 左腳 overall steps/min
    r_spm: float  # 右腳 overall steps/min
    spm: float  # 整體 overall steps/min

    # overall 平均步長
    l_mean_step_len: float  # 左腳 overall 平均步長（m）
    r_mean_step_len: float  # 右腳 overall 平均步長（m）
    mean_step_len: float  # 整體 overall 平均步長（m）

    # overall 期別統計（平均）
    l_swing_pct_mean: float  # 左腳擺動期百分比（0~100）
    r_swing_pct_mean: float  # 右腳擺動期百分比（0~100）
    l_swing_s_mean: float  # 左腳擺動期平均秒數
    r_swing_s_mean: float  # 右腳擺動期平均秒數
    l_stance_s_mean: float  # 左腳支撐期平均秒數
    r_stance_s_mean: float  # 右腳支撐期平均秒數

    # 各時間區間（例如每分鐘）的彙整
    per_interval: List[IntervalGaitMetrics] = field(default_factory=list)  # 每個 interval 的統計列表
    
    # 詳細的步態週期數據（用於可視化）
    left_cycles: List[FootStepCycle] = field(default_factory=list)  # 左腳步態週期
    right_cycles: List[FootStepCycle] = field(default_factory=list)  # 右腳步態週期
    
    def to_dict(self) -> dict:
        """轉為可 JSON 序列化的 dict。"""
        return asdict(self)


@dataclass
class LapPhaseTimes:
    """一圈的「階段切分」時間戳與摘要。

    注意：此結構偏向 UI/前端顯示用途（時間線/分段條）。
    欄位命名沿用既有前端/legacy 使用習慣。
    """
    sit_down: float  # 坐下事件時間（秒）
    stand_up: float  # 站起事件時間（秒）
    go: float  # 起身後往錐子方向走的起點（秒）
    turn1: float  # 錐子處轉身事件（秒）
    back: float  # 回程起點（秒）
    turn2: float  # 椅子前對位轉身事件（秒）
    start: float  # 一圈開始時間（秒）
    half: float  # 半程時間（秒）
    end: float  # 一圈結束時間（秒）
    lap_duration: float  # 一圈總秒數

    def to_dict(self) -> dict:
        """轉為可 JSON 序列化的 dict。"""
        return asdict(self)


@dataclass
class SitStandEvent:
    """站起/坐下事件（用於偵測與 debug/可視化）。

    `kind` 常見值：'sit' / 'stand'（依呼叫端定義）。
    """
    kind: str  # 事件種類（例如 'sit' / 'stand'）
    frame: int  # 事件發生的 frame index
    time_s: float  # 事件發生時間（秒）
    height_m: float  # 觸發事件的高度特徵值（m；通常是髖/關節高度）
    threshold: float  # 判斷門檻（同 height 的單位）
    fps: float  # 偵測時使用的 fps（frames/sec）
    t_lo: float = 0.0  # 事件視窗下界（秒）

    def to_dict(self) -> dict:
        """轉為可 JSON 序列化的 dict。"""
        return asdict(self)

@dataclass
class GaitCyclePhases:
    """
    單側完整步態週期的相位百分比。
    
    完整步態週期（以右腳為例）：
    RHS -> DS1 -> LTO -> SS -> LHS -> DS2 -> RTO -> Swing -> RHS
    
    其中：
    - DS1: 初始雙支撐期（兩腳同時著地）
    - SS: 單支撐期（主側腳支撐，對側腳擺動）
    - DS2: 終末雙支撐期（兩腳同時著地）
    - Swing: 擺動期（主側腳離地）
    """
    side: str                    # 'L' 或 'R'
    ds1_pct: float               # 初始雙支撐期百分比
    single_support_pct: float    # 單支撐期百分比
    ds2_pct: float               # 終末雙支撐期百分比
    swing_pct: float             # 擺動期百分比
    stance_pct: float            # 總支撐期百分比 (ds1 + ss + ds2)
    avg_cycle_time_s: float      # 平均步態週期時間（秒）
    n_cycles: int                # 用於計算平均的有效週期數
    
    def to_dict(self) -> dict:
        """轉為可 JSON 序列化的 dict。"""
        return asdict(self)


@dataclass
class XYZPair:
    """用於顯示/映射 X/Y/Z 軸名稱的輔助結構（主要給 visualizer 用）。"""

    x: str  # X 軸顯示文字
    y: str  # Y 軸顯示文字
    z: str  # Z 軸顯示文字
    
    class XYZDict(TypedDict):
        """`XYZPair.to_dict()` 的回傳型別（TypedDict 便於型別檢查）。"""
        x: str
        y: str
        z: str
    
    def to_dict(self) -> XYZDict:
        """轉為 dict（TypedDict）。"""
        return asdict(self)