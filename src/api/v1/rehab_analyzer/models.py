from typing import List, Optional, Tuple, Union, Literal
from pydantic import BaseModel, Field

from rehab_analyzer.constants import (
   DEFAULT_PROJECTION,
   DEFAULT_SMOOTH_WINDOW_S,
   DEFAULT_MIN_V_ABS,
   DEFAULT_FLAT_FRAC,
   DEFAULT_K_SMOOTH,
)

class AnalyzerBaseParams(BaseModel):
   """共享的通用參數，避免每個 API 重複定義。"""

   projection: str = Field(
      DEFAULT_PROJECTION,
      description="使用的投影平面（xz / xy）。",
   )
   smooth_window_s: float = Field(
      DEFAULT_SMOOTH_WINDOW_S,
      description="平滑視窗秒數；會依 fps 轉換成 frames。",
   )
   min_v_abs: float = Field(
      DEFAULT_MIN_V_ABS,
      description="步態檢測用的速度閾值（abs）。",
   )
   flat_frac: float = Field(
      DEFAULT_FLAT_FRAC,
      description="速度平坦度比例閾值（步態檢測用）。",
   )


class FFTPeriodogramParams(BaseModel):
   """FFT / periodogram 相關可調設定。"""

   window: str = Field(
      "hann",
      description="scipy.signal.periodogram 的 window 參數；例如 hann、hamming 等。",
   )
   detrend: Literal["none", "constant", "linear"] = Field(
      "none",
      description="FFT 前的 detrend 模式。",
   )
   scaling: Literal["spectrum", "density"] = Field(
      "spectrum",
      description="periodogram scaling 參數（spectrum 或 density）。",
   )
   min_nfft: int = Field(
      512,
      ge=8,
      description="最小 FFT 點數；不足會自動補零。",
   )
   pad_to_pow2: bool = Field(
      True,
      description="是否將 nfft 補到 2 的次方，利於加速。",
   )
   zero_pad_factor: float = Field(
      1.0,
      ge=1.0,
      description="額外零填充倍率，例如 2.0 代表至少補到原長度兩倍。",
   )
   remove_dc: bool = Field(
      False,
      description="FFT 前是否扣除平均值以移除 DC 成分。",
   )


# ---------- Request models ----------

class StageDurationsRequest(AnalyzerBaseParams):
   """每圈六段耗時圖請求。"""


class PerLapOffsetRequest(AnalyzerBaseParams):
   """每圈左右偏移診斷請求。"""

   k_smooth: int = Field(
      DEFAULT_K_SMOOTH,
      description="lateral offset 平滑階數（Savitzky–Golay）。",
   )


class MinutelyCadenceStepLengthBarsRequest(AnalyzerBaseParams):
   """每分鐘步頻與步長柱狀圖請求。"""

   max_minutes: Optional[int] = Field(
      None,
      description="限制輸出前 N 分鐘；None 表示全部。",
   )


class MultiFFTFromSeriesRequest(BaseModel):
   """多系列 FFT 請求。"""

   joints: List[Union[int, str, List[Union[int, str]]]] = Field(
      default_factory=lambda: [[27, 28]],
      description="單一或群組關節 ID/名稱；群組會先取平均再做 FFT。",
   )
   component: str = Field(
      "z",
      description="使用的軸 x / y / z。",
   )
   top_k: Optional[int] = Field(
      None,
      description="每條曲線最多標註的峰數；None 不限制。",
   )
   min_peak_distance_ratio: float = Field(
      0.01,
      description="峰間最小距比例（相對頻率範圍）。",
   )
   min_db: float = Field(
      -60.0,
      description="峰值最低 dB（相對全域最大）。",
   )
   min_freq: float = Field(
      0.05,
      description="最低頻率 (Hz)；低於此值不計。",
   )
   fft_params: FFTPeriodogramParams = Field(
      default_factory=FFTPeriodogramParams,
      description="FFT / PSD 計算設定。",
   )


class FloatArrayF32ZlibB64(BaseModel):
   """
   壓縮過的一維 float array：
   - 先轉成 little-endian float32（C order）
   - zlib 壓縮後 base64
   """

   f32_zlib_b64: str = Field(
      ...,
      description=(
         "zlib 壓縮後再 base64 的 bytes。解壓後可視為 little-endian float32 array。"
      ),
   )
   endian: Literal["little"] = Field(
      "little", description="解壓後 float32 的位元序（目前固定 little）。"
   )
   n: int = Field(..., description="解壓後 float32 元素個數。")


class YHeightDiffRequest(BaseModel):
   """左右關節高度差請求。"""

   smooth_window_s: float = Field(
      DEFAULT_SMOOTH_WINDOW_S,
      description="平滑視窗秒數；會依 fps 轉換成 frames。",
   )
   left_joint: Union[int, str] = Field(
      29,
      description="左側關節 ID 或名稱。",
   )
   right_joint: Union[int, str] = Field(
      30,
      description="右側關節 ID 或名稱。",
   )
   shift_to_zero: bool = Field(
      True,
      description="是否將 Y 高度序列平移到 0（使用腳部點估計地面作為共同 0 基準，腳≈0、膝/髖會比腳高）。",
   )

class SpatialSpectrumRequest(BaseModel):
   """空間頻譜請求：X(Z) 或 Y(Z)。"""

   pair: List[str] = Field(
      default_factory=lambda: ["xz", "yz"],
      description="要計算的平面組列表（如 xz / yz）。",
   )
   k_smooth: int = Field(
      2,
      description="空間頻譜平滑階數。",
   )
   top_k: Optional[int] = Field(
      None,
      description="取前幾大峰；None 表示不限制。",
   )
   min_peak_distance_ratio: float = Field(
      0.01,
      description="峰間最小距比例（相對頻率範圍）。",
   )
   min_db: float = Field(
      -60.0,
      description="最低 dB 門檻（相對每條曲線最大值）。",
   )
   min_freq: float = Field(
      0.5,
      description="最低頻率 (Hz)。",
   )
   spec_ylim: Optional[List[Tuple[float, float]]] = Field(
      None,
      description="每條頻譜的 y 軸範圍 (dB)；None 代表自動。",
   )


class SpeedHeatmapRequest(AnalyzerBaseParams):
   """每圈速度時空熱圖請求。"""

   width: int = Field(300, description="重採樣後的寬度（x 軸點數）。")
   vmin: Optional[float] = Field(
      None,
      description="顏色下限；None 則依資料自動取值。",
   )
   vmax: Optional[float] = Field(
      None,
      description="顏色上限；None 則依資料自動取值。",
   )


class SwingInfoHeatmapRequest(AnalyzerBaseParams):
   """每分鐘 Swing%（左/右）熱力圖資料請求（供前端自行渲染）。"""

   max_minutes: Optional[int] = Field(
      None,
      description="限制輸出前 N 分鐘；None 表示全部。",
   )


# ---------- Response models ----------

class StageDurationEntry(BaseModel):
   label: str = Field(..., description="階段標籤（固定 1~6）。")
   duration_s: float = Field(..., description="該階段耗時 (s)。")
   distance_m: Optional[float] = Field(
      None,
      description="該階段行走距離 (m)，若不適用則為 None。",
   )


class StageDurationLap(BaseModel):
   lap_index: int = Field(..., description="圈次（從 1 開始）。")
   ts_start: float = Field(..., description="圈起始時間戳 (s)。")
   ts_end: float = Field(..., description="圈結束時間戳 (s)。")
   total_duration_s: float = Field(..., description="該圈總耗時 (s)。")
   total_distance_m: float = Field(..., description="該圈路徑距離 (m)。")
   stage_durations: List[StageDurationEntry] = Field(
      ..., description="六個階段的耗時/距離明細。"
   )


class StageDurationsResponse(BaseModel):
   laps: List[StageDurationLap] = Field(..., description="各圈的耗時資料。")


class IndexRange(BaseModel):
   start_idx: int = Field(..., description="區段起始 index（相對圈起點）。")
   end_idx: int = Field(..., description="區段結束 index（相對圈起點）。")


class TurnRegions(BaseModel):
   cone: IndexRange = Field(..., description="錐標轉彎區段 index。")
   chair: IndexRange = Field(..., description="椅子轉彎區段 index。")


class PerLapOffsetLap(BaseModel):
   lap_index: int = Field(..., description="圈次（從 1 開始）。")
   # Series fields are returned in compact form (float32 little-endian + zlib + base64)
   time_s_f32_zlib_b64: FloatArrayF32ZlibB64 = Field(
      ...,
      description="時間軸 (s) 壓縮表示（float32 little-endian + zlib + base64）。",
   )
   lat_raw_f32_zlib_b64: FloatArrayF32ZlibB64 = Field(
      ...,
      description="lat_raw 壓縮表示（float32 little-endian + zlib + base64）。",
   )
   lat_smooth_f32_zlib_b64: FloatArrayF32ZlibB64 = Field(
      ...,
      description="lat_smooth 壓縮表示（float32 little-endian + zlib + base64）。",
   )
   theta_deg_f32_zlib_b64: FloatArrayF32ZlibB64 = Field(
      ...,
      description="theta_deg 壓縮表示（float32 little-endian + zlib + base64）。",
   )
   turn_regions: TurnRegions = Field(..., description="錐標/椅子轉彎區段。")
   walk_region: IndexRange = Field(..., description="走路區段 index。")


class PerLapOffsetResponse(BaseModel):
   laps: List[PerLapOffsetLap] = Field(..., description="每圈 lateral offset 資訊。")


class MinutelyCadenceStepLengthBarsResponse(BaseModel):
   minutes: List[int] = Field(..., description="分鐘序號（1-based）。")
   cadence_spm: List[float] = Field(..., description="各分鐘步頻 (steps/min)。")
   step_length_m: List[float] = Field(..., description="各分鐘平均步長 (m)。")
   step_counts: List[int] = Field(..., description="各分鐘步數總計。")


class YHeightDiffResponse(BaseModel):
   time_s_f32_zlib_b64: FloatArrayF32ZlibB64 = Field(
      ...,
      description="時間軸 (s) 壓縮表示（float32 little-endian + zlib + base64）。",
   )
   left_f32_zlib_b64: FloatArrayF32ZlibB64 = Field(
      ...,
      description="左關節 Y 高度序列壓縮表示（float32 little-endian + zlib + base64）。",
   )
   right_f32_zlib_b64: FloatArrayF32ZlibB64 = Field(
      ...,
      description="右關節 Y 高度序列壓縮表示（float32 little-endian + zlib + base64）。",
   )
   diff_f32_zlib_b64: FloatArrayF32ZlibB64 = Field(
      ...,
      description="左-右 高度差序列壓縮表示（float32 little-endian + zlib + base64）。",
   )
   left_joint: Union[int, str] = Field(..., description="左關節 ID/名稱。")
   right_joint: Union[int, str] = Field(..., description="右關節 ID/名稱。")


class SpectrumPeak(BaseModel):
   freq: float = Field(..., description="峰值頻率 (Hz)。")
   db: float = Field(..., description="峰值幅度 (dB，相對該曲線最大值)。")


class SpectrumPayload(BaseModel):
   pair: str = Field(..., description="平面組名稱（如 xz / yz）。")
   freq_f32_zlib_b64: FloatArrayF32ZlibB64 = Field(
      ...,
      description="頻率軸 (Hz) 壓縮表示（float32 little-endian + zlib + base64）。",
   )
   psd_db_f32_zlib_b64: FloatArrayF32ZlibB64 = Field(
      ...,
      description="頻譜 dB 值壓縮表示（float32 little-endian + zlib + base64；相對該曲線最大值）。",
   )
   peaks: List[SpectrumPeak] = Field(..., description="篩選後的峰列表。")


class SpatialSpectrumResponse(BaseModel):
   spectrums: List[SpectrumPayload] = Field(..., description="各平面組的頻譜資訊。")


class FFTPeak(BaseModel):
   freq_hz: float = Field(..., description="峰值頻率 (Hz)。")
   db: float = Field(..., description="峰值功率 (dB，相對全域最大)。")


class MultiFFTSeries(BaseModel):
   joint_spec: Union[int, str, List[Union[int, str]]] = Field(
      ..., description="原始 joints 輸入（單一或群組）。"
   )
   freq_hz_f32_zlib_b64: FloatArrayF32ZlibB64 = Field(
      ...,
      description="freq_hz 的壓縮表示（float32 little-endian + zlib + base64）。",
   )
   psd_db_f32_zlib_b64: FloatArrayF32ZlibB64 = Field(
      ...,
      description="psd_db 的壓縮表示（float32 little-endian + zlib + base64）。",
   )
   peaks: List[FFTPeak] = Field(..., description="篩選後的峰列表。")


class MultiFFTFromSeriesResponse(BaseModel):
   component: str = Field(..., description="使用的軸 x / y / z。")
   series: List[MultiFFTSeries] = Field(..., description="每條輸入 joints 的頻譜結果。")


class SpeedHeatmapMark(BaseModel):
   lap_index: int = Field(..., description="圈次（從 1 開始）。")
   cone_start_frac: float = Field(..., description="錐桶轉彎起點（相對圈長 0~1）。")
   cone_end_frac: float = Field(..., description="錐桶轉彎終點（相對圈長 0~1）。")
   chair_start_frac: float = Field(..., description="椅子轉彎起點（相對圈長 0~1）。")
   chair_end_frac: float = Field(..., description="椅子轉彎終點（相對圈長 0~1）。")


class SpeedHeatmapResponse(BaseModel):
   width: int = Field(..., description="熱圖寬度（每圈重採樣點數）。")
   heatmap: List[List[Optional[float]]] = Field(
      ..., description="速度值矩陣（row=lap-1，col=進度索引）；None 表示缺值。"
   )
   marks: List[SpeedHeatmapMark] = Field(..., description="各圈錐桶轉身區間位置。")
   vmin: Optional[float] = Field(None, description="顏色下限（若自動則回傳實際計算值）。")
   vmax: Optional[float] = Field(None, description="顏色上限（若自動則回傳實際計算值）。")


class SwingInfoHeatmapResponse(BaseModel):
   """
   Swing%（及 swing 秒數）每分鐘彙整的熱力圖資料。

   - row 0 = Left
   - row 1 = Right
   - col 對應 minute index（1-based minutes）
   """

   minutes: List[int] = Field(..., description="分鐘序號（1-based）。")
   swing_pct: List[List[Optional[float]]] = Field(
      ...,
      description="swing% 矩陣（2×N）；None 表示缺值。",
   )
   swing_s: List[List[Optional[float]]] = Field(
      ...,
      description="swing 秒數矩陣（2×N）；None 表示缺值。",
   )

# ---------- Trajectory payload (frontend-rendered "video") ----------

class TrajectoryPayloadRequest(AnalyzerBaseParams):
   """
   讓前端自行渲染 top-down 軌跡動畫所需的最小資料包。

   設計理念：
   - 後端不再輸出 mp4；只輸出「每幀左右關節投影座標 + 場景(椅/錐) + 圈段/轉身 marker」
   - 前端可用 Canvas/WebGL 依據 `bounds` 做座標映射、依 `time_s` 播放
   """

   left_joint: Union[int, str] = Field(
      "L_HIP", description="左側關節 ID/名稱（預設 L_HIP）。"
   )
   right_joint: Union[int, str] = Field(
      "R_HIP", description="右側關節 ID/名稱（預設 R_HIP）。"
   )

   fps_out: int = Field(24, ge=1, le=120, description="建議前端播放用 fps。")
   speed: float = Field(
      1.0,
      gt=0.0,
      description="播放速度倍率（和 visualizer 一致，用於決定下採樣 stride；越大代表取樣越稀疏）。",
   )
   frame_jump: int = Field(
      3,
      ge=1,
      description="額外每 N 幀取 1 幀（和 visualizer 同名參數；用來再做一次下採樣）。",
   )

   rotate_180: bool = Field(
      True,
      description="是否以 bounds 的中心旋轉 180°（讓椅/錐上下互換，對齊既有影片）。",
   )
   pad_scale: float = Field(
      0.08,
      ge=0.0,
      le=1.0,
      description="視窗 padding，比例乘上資料 span（與 visualizer 相同；用於產生 meta.bounds）。",
   )


class TrajectoryBounds(BaseModel):
   """世界座標範圍（投影平面上的 x/y；單位通常是 m）。"""
   xmin: float = Field(..., description="世界座標最小 x。")
   xmax: float = Field(..., description="世界座標最大 x。")
   ymin: float = Field(..., description="世界座標最小 y（注意：這裡的 y 是投影平面第二軸，不一定是 3D 的 Y）。")
   ymax: float = Field(..., description="世界座標最大 y。")


class TrajectoryScene(BaseModel):
   chair_xy_u16: List[int] = Field(
      ...,
      description=(
         "椅子中心 [x_u16, y_u16]（uint16，0~65535）。"
         "需用 meta.bounds 反量化回世界座標："
         "x = xmin + (x_u16/65535)*(xmax-xmin)，y 同理。"
      ),
   )
   cone_xy_u16: List[int] = Field(
      ...,
      description="錐桶中心 [x_u16, y_u16]（uint16，0~65535；反量化方式同 chair_xy_u16）。",
   )
   r_chair: float = Field(..., description="椅子 enter 半徑（世界座標單位；通常是 m）。")
   r_cone: float = Field(..., description="錐桶 enter 半徑（世界座標單位；通常是 m）。")


class TrajectoryFrames(BaseModel):
   """
   最小化座標 payload：
   - 先把 (x,y) 依 bounds 線性量化到 uint16（0~65535）
   - 依序打包成 [xL, yL, xR, yR] * n_frames
   - 以 zlib 壓縮後再 base64
   """
   xy_lr_u16_zlib_b64: str = Field(
      ...,
      description=(
         "zlib 壓縮後再 base64 的 bytes。解壓後是 little-endian uint16 array，"
         "長度 = meta.n_frames * 4，排列為 [xL,yL,xR,yR] 連續重複。"
      ),
   )


class TrajectoryLapMarkers(BaseModel):
   """轉身點在 payload frames 中的索引 k（可為 None 代表找不到有效點）。"""
   cone_start_k: Optional[int] = Field(
      None, description="錐桶轉身開始點對應的 payload frame 索引 k（0-based）。"
   )
   cone_end_k: Optional[int] = Field(
      None, description="錐桶轉身結束點對應的 payload frame 索引 k（0-based）。"
   )
   chair_start_k: Optional[int] = Field(
      None, description="椅子前對位轉身開始點對應的 payload frame 索引 k（0-based）。"
   )
   chair_end_k: Optional[int] = Field(
      None, description="椅子前對位轉身結束點對應的 payload frame 索引 k（0-based）。"
   )


class TrajectoryLap(BaseModel):
   lap_index: int = Field(..., description="圈次（1-based）。")
   payload_start_k: Optional[int] = Field(
      None,
      description="此圈在 payload frames 中的起點索引 k（0-based；若此圈沒有落在 payload 內則為 None）。",
   )
   payload_end_k: Optional[int] = Field(
      None,
      description="此圈在 payload frames 中的終點索引 k（0-based；若此圈沒有落在 payload 內則為 None）。",
   )
   markers: TrajectoryLapMarkers


class TrajectoryMeta(BaseModel):
   projection: str = Field(..., description="投影平面（xz / xy）。")
   fps_out: int = Field(..., description="建議前端播放 fps（可用來推導每幀時間：t = k / fps_out）。")
   rotate_180: bool = Field(..., description="是否已對輸出座標做 180° 旋轉（前端不需再旋轉）。")
   bounds: TrajectoryBounds = Field(
      ...,
      description="世界座標 bounds（用於把 uint16 反量化回世界座標，也可用於畫布映射）。",
   )
   encoding: Literal["u16_xy_lr_zlib_b64"] = Field(
      "u16_xy_lr_zlib_b64",
      description="frames 的編碼格式標記（目前固定）。",
   )
   endian: Literal["little"] = Field(
      "little", description="frames 解壓後 uint16 的位元序（目前固定 little）。"
   )
   n_frames: int = Field(..., description="payload 幀數（解壓後可重建 frames 長度；每幀有 4 個 uint16）。")


class TrajectoryPayloadResponse(BaseModel):
   meta: TrajectoryMeta
   scene: TrajectoryScene
   frames: TrajectoryFrames
   laps: List[TrajectoryLap]