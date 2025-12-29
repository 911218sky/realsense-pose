from pathlib import Path
from typing import (
    Optional,
    Tuple,
    List,
    Sequence,
    Callable,
    Union,
    Literal,
    Dict,
    Mapping,
    Any,
)

import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Circle
from matplotlib.ticker import MultipleLocator
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from PIL import Image
import cv2

from utils import FFmpegPipe, add_prefix_to_filename
from .entities import XYZPair
from .rehab_analyzer import (
    RehabilitationSessionAnalyzer,
    DetectLapsResult,
)
from .constants import (
    DEFAULT_PROJECTION,
    DEFAULT_SMOOTH_WINDOW_S,
    DEFAULT_FLAT_FRAC,
    DEFAULT_MIN_V_ABS,
)

# 使用無頭後端
matplotlib.use("Agg")

# 軸標籤顯示名稱設定（僅作為說明用途；實際標籤由 axis_convention 決定）
# - standard   : X = 左右（lateral, left+, right-）
#                Y = 上下（vertical, up+, down-）
#                Z = 前後/深度（antero‑posterior, forward+, backward-）
# - anatomical : X = 前後（antero‑posterior, forward+, backward-）
#                Y = 左右（lateral, left+, right-）
#                Z = 上下（vertical, up+, down-）
AXIS_DISPLAY_NAMES: Dict[str, XYZPair] = {
    "standard": XYZPair(x="X", y="Y", z="Z"),
    "anatomical": XYZPair(x="X", y="Y", z="Z"),
}

# 基礎類別：共用 prefix / out_dir / 軸顯示設定
class VisualizerCore(RehabilitationSessionAnalyzer):
    """
    可視化核心類別：

    - 繼承 RehabilitationSessionAnalyzer（裡面包含所有分析方法）
    - 新增：
      - prefix：輸出檔名的前綴
      - axis_convention：只影響圖上的 X/Y/Z 文字，不影響計算座標系
    """

    def __init__(
        self,
        npy_path: str,
        out_dir: str,
        prefix: Optional[str] = None,
        axis_convention: str = "standard",
    ) -> None:
        super().__init__(npy_path)
        
        # 輸出目錄
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)

        # 輸出檔案前綴名稱（預設使用檔名，不含副檔名）
        self.prefix = prefix or Path(npy_path).stem or "session"

        # 軸顯示慣例設定
        if axis_convention not in AXIS_DISPLAY_NAMES:
            raise ValueError(f"未知的 axis_convention='{axis_convention}'，可用：{list(AXIS_DISPLAY_NAMES)}")
        self.axis_convention = axis_convention
        self.xyz_pair = AXIS_DISPLAY_NAMES[axis_convention]

    # ------------------------------------------------------------------
    # 座標軸標籤工具：根據 axis_convention 把「資料座標軸」映射到 X/Y/Z 文字
    # ------------------------------------------------------------------
    def _axis_label_for_data_dim(self, dim: int) -> str:
        """
        給定「原始資料軸」(0:X 左右, 1:Y 上下, 2:Z 前後)，回傳在目前
        axis_convention 下應顯示的軸名稱（'X' / 'Y' / 'Z'）。

        - standard   : (0,1,2) -> ('X', 'Y', 'Z')
        - anatomical : (0,1,2) -> ('Y', 'Z', 'X')
            * 0 (左右)   -> Y（lateral）
            * 1 (上下)   -> Z（vertical）
            * 2 (前後)   -> X（antero‑posterior）
        """
        if dim not in (0, 1, 2):
            raise ValueError(f"dim 必須是 0/1/2，收到 {dim}")

        if getattr(self, "axis_convention", "standard") == "anatomical":
            mapping = ("Y", "Z", "X")
        else:
            mapping = ("X", "Y", "Z")
        return mapping[dim]

    def _axis_labels_for_pair(self, pair: str) -> Tuple[str, str]:
        """
        依據 pair（例如 'xz', 'yz'）回傳 (dependent, independent) 軸的顯示文字。

        約定（配合 FftAnalyzer / _compute_hip_points 等實作）：
        - 'xz': 依序代表 (raw X, raw Z)
        - 'yz': 依序代表 (raw Y, raw Z)
        """
        p = (pair or "").lower()
        if p == "xz":
            dep_dim = 0  # raw X
            indep_dim = 2  # raw Z
        elif p == "yz":
            dep_dim = 1  # raw Y
            indep_dim = 2  # raw Z
        else:
            raise ValueError("pair 只能是 'xz' 或 'yz'")

        return self._axis_label_for_data_dim(dep_dim), self._axis_label_for_data_dim(indep_dim)

    def _apply_limits(
        self,
        ax: plt.Axes,
        *,
        xlim: Optional[Tuple[float, float]] = None,
        ylim: Optional[Tuple[float, float]] = None,
    ) -> None:
        """
        設定圖形座標軸範圍。
        若傳入 None 則保持原本 Matplotlib 自動範圍。
        """
        if xlim is not None:
            ax.set_xlim(*xlim)
        if ylim is not None:
            ax.set_ylim(*ylim)


# 共用工具 Mixin：影像 / 圖形轉換等
class VisualizerUtilsMixin(VisualizerCore):
    """
    共用工具類別：

    - 時間字串格式
    - 影像讀取、補白/裁切
    - Matplotlib Figure 轉 numpy 陣列
    """

    def _fmt_ts(self, t: float) -> str:
        """秒數格式化為 mm:ss.ss 文字。"""
        minutes = int(t // 60)
        seconds = t % 60.0
        return f"{minutes}:{seconds:05.2f}"

    def _imread_rgb(self, path: str) -> np.ndarray:
        """使用 PIL 讀取影像並轉成 RGB uint8 numpy 陣列。"""
        img = Image.open(path).convert("RGB")
        return np.asarray(img, dtype=np.uint8)

    def _pad_or_crop_even(self, img: np.ndarray, H: int, W: int) -> np.ndarray:
        """
        將影像補白或裁切到指定大小 (H, W)。

        通常搭配 ffmpeg 使用：
        - 一些編碼格式要求影格尺寸需為偶數。
        """
        h, w = img.shape[:2]
        pad_bottom = max(0, H - h)
        pad_right = max(0, W - w)

        # 補白到至少 H×W
        if pad_bottom or pad_right:
            img = cv2.copyMakeBorder(
                img,
                top=0,
                bottom=pad_bottom,
                left=0,
                right=pad_right,
                borderType=cv2.BORDER_CONSTANT,
                value=(255, 255, 255),
            )
            h, w = img.shape[:2]

        # 若過大則裁切
        if h > H or w > W:
            img = img[:H, :W]

        return img

    def _canvas_to_numpy_rgba(self, fig: plt.Figure) -> np.ndarray:
        """
        將 Matplotlib Figure 轉成 RGBA uint8 numpy 陣列 (H, W, 4)。

        會優先使用 tostring_argb，如沒有則退而求其次使用 tostring_rgb。
        """
        fig.canvas.draw()

        # 優先使用 ARGB
        if hasattr(fig.canvas, "tostring_argb"):
            width, height = fig.canvas.get_width_height()
            argb = np.frombuffer(fig.canvas.tostring_argb(), dtype=np.uint8).reshape(height, width, 4)
            rgba = argb[:, :, [1, 2, 3, 0]]  # ARGB -> RGBA
            return rgba

        # 次選使用 RGB，再補一個 alpha 通道
        if hasattr(fig.canvas, "tostring_rgb"):
            width, height = fig.canvas.get_width_height()
            rgb = np.frombuffer(fig.canvas.tostring_rgb(), dtype=np.uint8).reshape(height, width, 3)
            alpha = np.full((height, width, 1), 255, dtype=np.uint8)
            rgba = np.concatenate([rgb, alpha], axis=2)
            return rgba

        raise RuntimeError("無法擷取 Matplotlib 畫布內容。")


# 每圈六段耗時圖（堆疊橫條）
class StageDurationsPlotterMixin(VisualizerUtilsMixin):
    """
    每圈六段耗時堆疊圖：

    利用 detect_laps_auto() 的 Lap 結果，
    將每圈分為 6 個階段並畫成堆疊橫條圖：
    1. Stand up
    2. Walk to cone
    3. Turn at cone
    4. Walk back
    5. Align to sit
    6. Sit down
    """

    def save_stage_durations_image(
        self,
        projection: str = DEFAULT_PROJECTION,
        smooth_window_s: float = DEFAULT_SMOOTH_WINDOW_S,
        flat_frac: float = DEFAULT_FLAT_FRAC,
        min_v_abs: float = DEFAULT_MIN_V_ABS,
        *,
        save_name: Optional[str] = None,
        dpi: int = 190,
        show_seconds: bool = True,
        show_meters: bool = True,
        row_height: float = 1.0,
        bar_height: float = 0.5,
        min_width_sec: float = 0.5,
        meters_gap: float = 0.08,
        min_meters_to_show: float = 0.03,
    ) -> Path:
        """
        繪製每圈六段耗時的堆疊橫條圖並輸出 PNG。

        回傳：
            Path：輸出檔案路徑
        """
        det: DetectLapsResult = self.detect_laps_auto(
            projection=projection,
            smooth_window_s=smooth_window_s,
            flat_frac=flat_frac,
            min_v_abs=min_v_abs,
        )
        laps = det.laps
        if not laps:
            raise ValueError("沒有可視覺化的圈數（laps 為空）。")

        # 6 個階段的顯示文字與對應 Lap 欄位名稱
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

        # 收集每圈各階段秒數 (N × 6)
        durations: list[list[float]] = []
        for lap in laps:
            row = [max(0.0, getattr(lap, key, 0.0)) for key in keys]
            durations.append(row)
        sec = np.array(durations, dtype=float)

        totals = sec.sum(axis=1)
        start_ts = np.array([lap.ts_start for lap in laps], dtype=float)
        end_ts = np.array([lap.ts_end for lap in laps], dtype=float)
        lap_len = np.array([lap.dist_lap_path_m for lap in laps], dtype=float)

        # 距離資訊（只顯示在 2 / 3 / 4 / 5 段）
        outbound = np.array([lap.dist_outbound_m for lap in laps], dtype=float)
        turnpath = np.array([lap.dist_cone_turn_path_m for lap in laps], dtype=float)
        retpath = np.array([lap.dist_return_m for lap in laps], dtype=float)
        turn_to_sit = np.array([lap.dist_turn_to_sit_m for lap in laps], dtype=float)

        meters_map = np.stack(
            [
                np.zeros_like(outbound),  # 段 1：無距離
                outbound,                 # 段 2：離椅→錐
                turnpath,                 # 段 3：錐內轉身弦長
                retpath,                  # 段 4：錐→椅
                turn_to_sit,              # 段 5：椅邊轉身距離
                np.zeros_like(outbound),  # 段 6：無距離
            ],
            axis=1,
        )

        num_laps = len(laps)

        # 固定用一組顏色，依序對應 6 段
        colors = [
            "#4C78A8",
            "#F58518",
            "#E45756",
            "#72B7B2",
            "#54A24B",
            "#EECA3B",
        ]

        fig_height = max(2.5, row_height * num_laps)
        # 不用 constrained_layout，改用 tight_layout + figure legend 來控制底部空白
        fig, ax = plt.subplots(figsize=(12, fig_height), dpi=dpi)

        ypos = np.arange(num_laps)[::-1]
        left = np.zeros(num_laps, dtype=float)
        bars = []

        # 依序堆疊 6 段
        for idx in range(6):
            bar = ax.barh(
                ypos,
                sec[:, idx],
                left=left,
                color=colors[idx],
                label=labels[idx],
                edgecolor="none",
                height=bar_height,
            )
            bars.append(bar)
            left += sec[:, idx]

        def put_text(
            x: float,
            y: float,
            text: str,
            *,
            ha: str = "center",
            va: str = "center",
            fontsize: int = 9,
            color: str = "white",
            bold: bool = True,
            clip: bool = True,
        ) -> None:
            """小工具：在指定座標放文字。"""
            ax.text(
                x,
                y,
                text,
                ha=ha,
                va=va,
                fontsize=fontsize,
                color=color,
                fontweight="bold" if bold else None,
                clip_on=clip,
            )

        # 每段中顯示秒數／或秒數加距離
        if show_seconds:
            for j, bar in enumerate(bars):
                for lap_idx, rect in enumerate(bar):
                    width = rect.get_width()
                    if width <= 0 or width < min_width_sec:
                        continue

                    if j == 2:
                        # 第 3 段：秒數 + 移動距離
                        dist_val = meters_map[lap_idx, j]
                        dist_val = dist_val if np.isfinite(dist_val) else 0.0
                        label = f"{sec[lap_idx, j]:.2f}s·{dist_val:.2f} m"
                    else:
                        label = f"{sec[lap_idx, j]:.2f}s"

                    cx = rect.get_x() + width / 2.0
                    cy = rect.get_y() + rect.get_height() / 2.0
                    put_text(cx, cy, label)

        # 距離標註：第 一、二、三、四段放在 bar 下方
        if show_meters:
            for j in (1, 2, 3, 4):
                bar = bars[j]
                for lap_idx, rect in enumerate(bar):
                    dist_val = float(meters_map[lap_idx, j])
                    if dist_val < min_meters_to_show:
                        continue

                    width = rect.get_width()
                    cx = rect.get_x() + width / 2.0
                    cy = rect.get_y() - meters_gap
                    put_text(
                        cx,
                        cy,
                        f"{dist_val:.2f} m",
                        va="top",
                        fontsize=9,
                        color="#2b2b2b",
                        clip=False,
                    )

        # 右側標註每圈起訖時間與路徑長度
        max_x = float(np.nanmax(totals)) if np.isfinite(totals).any() else 1.0
        ax.set_xlim(0, max_x + max_x * 0.36)

        for lap_idx in range(num_laps):
            tail_x = totals[lap_idx]
            text = (
                f"{self._fmt_ts(start_ts[lap_idx])} → "
                f"{self._fmt_ts(end_ts[lap_idx])} · {lap_len[lap_idx]:.2f} m"
            )
            ax.text(
                tail_x + 0.28,
                ypos[lap_idx],
                text,
                ha="left",
                va="center",
                fontsize=10,
                color="#2b2b2b",
            )

        # Y 軸設定
        ax.set_yticks(ypos)
        ax.set_yticklabels([f"Lap {idx + 1}" for idx in range(num_laps)], fontsize=11)

        ymin, ymax = ypos.min() - 0.5, ypos.max() + 0.5
        if show_meters:
            ymin -= meters_gap * 1.2
        ax.set_ylim(ymin, ymax)

        # 標題與外觀調整
        ax.set_xlabel("Time (s)")
        ax.set_title(f"{self.prefix} - Stage durations", fontsize=14, pad=6)

        for side in ("top", "right"):
            ax.spines[side].set_visible(False)

        ax.grid(True, axis="x", linestyle="--", alpha=0.22)
        ax.set_axisbelow(True)
        ax.margins(x=0.01, y=0.02)

        # 圖例放在下方（figure-level legend，避免額外預留太多底部空白）
        handles = [bars[i][0] for i in range(len(bars))]
        fig.legend(
            handles=handles,
            labels=labels,
            ncols=6,
            loc="lower center",
            bbox_to_anchor=(0.5, 0.01),
            frameon=False,
            fontsize=9,
            handlelength=1.1,
            handletextpad=0.4,
        )

        # 主圖區域緊縮，上方/左右留一點空間，底部約 6% 給 legend
        fig.tight_layout(rect=[0, 0.06, 1, 1])

        # 檔名與儲存
        filename = add_prefix_to_filename(save_name or "stage_durations.png", self.prefix)
        save_path = Path(self.out_dir) / filename
        save_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(save_path), bbox_inches="tight", pad_inches=0.02)
        plt.close(fig)

        return save_path


# 每分鐘三段分組柱狀圖：去程 / 迴轉 / 回程
class MinutelyStageDurationBarsMixin(VisualizerUtilsMixin):
    """
    每分鐘區間的三段分組柱狀圖：

    以每圈開始時間所屬的分鐘 (相對第一圈) 為分箱，統計：
    - Walk to cone
    - Turn at cone
    - Walk back

    每分鐘的柱子高度 = 該分鐘內圈數的「平均耗時」。
    """

    def save_minutely_stage_duration_bars(
        self,
        projection: str = DEFAULT_PROJECTION,
        smooth_window_s: float = DEFAULT_SMOOTH_WINDOW_S,
        flat_frac: float = DEFAULT_FLAT_FRAC,
        min_v_abs: float = DEFAULT_MIN_V_ABS,
        *,
        max_minutes: Optional[int] = None,
        dpi: int = 170,
        figsize_per_minute: float = 0.75,
        bar_width: float = 0.22,
        group_gap: float = 0.06,
        save_name: Optional[str] = None,
        ylim: Optional[Tuple[float, float]] = None,
    ) -> Path:
        """
        以每分鐘為單位繪製：
        - Walk to cone
        - Turn at cone
        - Walk back

        這三個階段的平均耗時柱狀圖。
        """
        det = self.detect_laps_auto(
            projection=projection,
            smooth_window_s=smooth_window_s,
            flat_frac=flat_frac,
            min_v_abs=min_v_abs,
        )
        laps = det.laps
        if not laps:
            raise ValueError("沒有圈數可視覺化（laps 為空）。")

        # 第一圈開始時間作為時間零點
        t0 = float(laps[0].ts_start)
        lap_starts = np.array([lap.ts_start for lap in laps], dtype=float)

        # 每圈所屬第幾分鐘（相對第一圈）
        minute_idx = np.floor((lap_starts - t0) / 60.0).astype(int)
        minute_idx = np.maximum(minute_idx, 0)

        # 計算總分鐘數（包含最後一圈結束時間）
        last_t = float(laps[-1].ts_end)
        total_minutes = int(np.floor((last_t - t0) / 60.0)) + 1

        if max_minutes is not None:
            total_minutes = max(1, min(int(max_minutes), total_minutes))

        M = total_minutes
        minutes = np.arange(M, dtype=int)

        # 每圈三個階段的耗時（負值轉成 0）
        v_to = np.array([max(0.0, float(lap.dur_to_cone)) for lap in laps], dtype=float)
        v_turn = np.array([max(0.0, float(lap.dur_cone_turn)) for lap in laps], dtype=float)
        v_ret = np.array([max(0.0, float(lap.dur_return)) for lap in laps], dtype=float)

        # 依分鐘分桶
        bins = {
            "to": [[] for _ in range(M)],
            "turn": [[] for _ in range(M)],
            "ret": [[] for _ in range(M)],
        }
        for idx, minute in enumerate(minute_idx):
            if 0 <= minute < M:
                if v_to[idx] > 0.0:
                    bins["to"][minute].append(float(v_to[idx]))
                if v_turn[idx] > 0.0:
                    bins["turn"][minute].append(float(v_turn[idx]))
                if v_ret[idx] > 0.0:
                    bins["ret"][minute].append(float(v_ret[idx]))

        def mean_or_nan(values: List[float]) -> float:
            """若清單為空，回傳 NaN；否則回傳平均值。"""
            if not values:
                return float("nan")
            return float(np.mean(np.asarray(values, dtype=float)))

        means_to = np.array([mean_or_nan(bins["to"][m]) for m in minutes], dtype=float)
        means_turn = np.array([mean_or_nan(bins["turn"][m]) for m in minutes], dtype=float)
        means_ret = np.array([mean_or_nan(bins["ret"][m]) for m in minutes], dtype=float)

        # 每分鐘的樣本數（取三者中最大，供 x 軸標示 n）
        counts = []
        for m in minutes:
            count_max = max(len(bins["to"][m]), len(bins["turn"][m]), len(bins["ret"][m]))
            counts.append(count_max)
        counts = np.array(counts, dtype=int)

        # 顏色設定
        color_to = "#F58518"
        color_turn = "#E45756"
        color_ret = "#72B7B2"

        fig_width = max(7.0, float(M) * float(figsize_per_minute))
        fig_height = 4.2
        fig, ax = plt.subplots(figsize=(fig_width, fig_height), dpi=dpi, layout="constrained")

        x = minutes.astype(float)
        offset = bar_width + group_gap / 2.0

        x_to = x - offset
        x_turn = x
        x_ret = x + offset

        bars_to = ax.bar(x_to, means_to, width=bar_width, label="Walk to cone", color=color_to)
        bars_turn = ax.bar(x_turn, means_turn, width=bar_width, label="Turn at cone", color=color_turn)
        bars_ret = ax.bar(x_ret, means_ret, width=bar_width, label="Walk back", color=color_ret)

        ax.grid(True, axis="y", linestyle="--", alpha=0.25)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)

        ax.set_ylabel("Duration (s)")
        ax.set_xlabel("Minute (from first lap start)")
        ax.set_xticks(x)
        ax.set_xticklabels([f"{m + 1}\n(n={int(n)})" for m, n in zip(minutes, counts)])

        self._apply_limits(ax, ylim=ylim)

        def annotate_bars(
            axis: plt.Axes,
            bar_container,
            values: np.ndarray,
            fmt: Callable[[float], str],
        ) -> None:
            """在每根柱子上方標示其數值（若為 NaN 則略過）。"""
            if not np.isfinite(values).any():
                return

            ymax = float(np.nanmax(values))
            ypad = 0.02 * ymax if np.isfinite(ymax) and ymax > 0 else 0.05

            for rect, value in zip(bar_container, values):
                if not np.isfinite(value):
                    continue

                axis.text(
                    rect.get_x() + rect.get_width() / 2.0,
                    float(value) + ypad,
                    fmt(float(value)),
                    ha="center",
                    va="bottom",
                    fontsize=9,
                    color="#222",
                )

        annotate_bars(ax, bars_to, means_to, fmt=lambda v: f"{v:.2f}s")
        annotate_bars(ax, bars_turn, means_turn, fmt=lambda v: f"{v:.2f}s")
        annotate_bars(ax, bars_ret, means_ret, fmt=lambda v: f"{v:.2f}s")

        ax.set_title(f"{self.prefix} - Per-minute stage durations")
        ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5), frameon=False)

        filename = add_prefix_to_filename(save_name or "minutely_stage_duration_bars.png", self.prefix)
        save_path = Path(self.out_dir) / filename
        save_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(save_path))
        plt.close(fig)

        return save_path


# 軌跡影片匯出（Top-down）
class TrajectoryVideoExporterMixin(VisualizerUtilsMixin):
    """
    Top-down 行走軌跡影片輸出：

    - 使用髖點（或自訂關節）在投影平面上的 2D 軌跡
    - 顯示：
      - 全程軌跡
      - 尾巴軌跡（最近 trail_sec 秒）
      - 左右髖點位置
      - 骨盆線段
      - 椅子 / 錐桶位置與半徑
      - 每圈轉身區段的標記
      - 目前時間與滑動平均速度
    """

    def save_trajectory_video(
        self,
        projection: str = DEFAULT_PROJECTION,
        smooth_window_s: float = DEFAULT_SMOOTH_WINDOW_S,
        flat_frac: float = DEFAULT_FLAT_FRAC,
        min_v_abs: float = DEFAULT_MIN_V_ABS,
        save_name: Optional[str] = None,
        *,
        left_joint: Union[int, str] = "L_HIP",
        right_joint: Union[int, str] = "R_HIP",
        fps_out: int = 24,
        speed: float = 1.0,
        dpi: int = 110,
        figsize: Tuple[float, float] = (7.6, 7.2),
        draw_radius: bool = False,
        draw_turn_markers: bool = True,
        bg_color: str = "#ffffff",
        path_color_L: str = "#cfcfcf",
        path_color_R: str = "#cdcdcd",
        trail_color_L: str = "#3b82f6",
        trail_color_R: str = "#22c55e",
        dot_color_L: str = "#1f2937",
        dot_color_R: str = "#111827",
        chair_color: str = "#22c55e",
        cone_color: str = "#f97316",
        turn_cone_start_color: str = "#ef4444",
        turn_cone_end_color: str = "#b91c1c",
        turn_chair_start_color: str = "#0ea5e9",
        turn_chair_end_color: str = "#0369a1",
        pad_scale: float = 0.08,
        rotate_180: bool = True,
        frame_jump: int = 3,
        avg_window_s: float = 1.0,
        ffmpeg_preset: str = "veryfast",
        ffmpeg_crf: int = 28,
    ) -> Path:
        """
        匯出 top-down 軌跡影片，顯示左右髖位置、每圈尾巴、轉身標記與即時速度文字。

        尾巴邏輯：
            - 在某一圈內：顯示「該圈從起點到目前幀」的整圈軌跡。
            - 不屬於任何圈：尾巴為空，不畫軌跡。
            - 進入下一圈時：上一圈尾巴整條消失，只顯示新那一圈。

        rotate_180:
            True -> 以整體畫面中心為軸，將繪圖結果旋轉 180°（椅/錐上下互換）。
        """
        # 取得髖點投影座標與有效 mask
        fps_in = float(self._estimate_fps())
        smooth_window = max(1, int(round(smooth_window_s * fps_in)))
        L2, R2, valid = self._compute_hip_points(
            projection=projection,
            smooth_window=smooth_window,
            left_joint=left_joint,
            right_joint=right_joint,
        )
        C2 = (L2 + R2) / 2.0
        num_frames = C2.shape[0]

        det = self.detect_laps_auto(
            projection=projection,
            smooth_window_s=smooth_window_s,
            flat_frac=flat_frac,
            min_v_abs=min_v_abs,
        )
        chair_pos = np.array(det.chair_pos, dtype=float)
        cone_pos = np.array(det.cone_pos, dtype=float)
        rC = float(det.r_chair_enter)
        rK = float(det.r_cone_enter)

        if not np.any(valid):
            raise ValueError("沒有有效的髖點座標。")

        # 畫面可見範圍：以所有有效點與椅、錐位置決定
        all_points = np.vstack([L2[valid], R2[valid], chair_pos[None, :], cone_pos[None, :]])
        xmin, ymin = np.min(all_points, axis=0)
        xmax, ymax = np.max(all_points, axis=0)
        span = max(xmax - xmin, ymax - ymin, 1e-6)
        pad_abs = pad_scale * span
        xmin -= pad_abs; xmax += pad_abs; ymin -= pad_abs; ymax += pad_abs

        if rotate_180:
            cx = 0.5 * (xmin + xmax)
            cy = 0.5 * (ymin + ymax)

            def _rotate_coords(arr: np.ndarray) -> np.ndarray:
                rotated = np.array(arr, dtype=float, copy=True)
                rotated[..., 0] = 2 * cx - rotated[..., 0]
                rotated[..., 1] = 2 * cy - rotated[..., 1]
                return rotated

            L2 = _rotate_coords(L2)
            R2 = _rotate_coords(R2)
            C2 = _rotate_coords(C2)
            chair_pos = _rotate_coords(chair_pos)
            cone_pos = _rotate_coords(cone_pos)

        # 按 speed 與輸出 fps 決定取樣步距
        stride = max(1, int(round((fps_in * float(speed)) / float(fps_out))))
        idxs_full = np.arange(0, num_frames, stride, dtype=int)
        idxs_full = idxs_full[valid[idxs_full]]

        if idxs_full.size < 2:
            raise ValueError("有效影格太少，無法產生影片。")

        if frame_jump > 1:
            idxs_full = idxs_full[::frame_jump]
        M = idxs_full.size

        L2_sub = L2[idxs_full]
        R2_sub = R2[idxs_full]

        # 時間軸處理（若有缺值則線性內插）
        if self.t is not None and np.isfinite(self.t).any():
            finite_mask = np.isfinite(self.t)
            indices_all = np.arange(num_frames)
            known_indices = np.where(finite_mask)[0]
            known_times = self.t[finite_mask].astype(float)
            interpolated = np.interp(indices_all, known_indices, known_times)
            t_all = np.where(finite_mask, self.t, interpolated).astype(float)
        else:
            t_all = np.arange(num_frames, dtype=float) / max(1.0, fps_in)
        t_sub = t_all[idxs_full]

        # 計算瞬時速度（每幀位移 / dt）
        dt = np.diff(t_all, prepend=t_all[0])
        positive_dt_mask = np.isfinite(dt) & (dt > 0)
        dt_median = float(np.median(dt[positive_dt_mask])) if np.any(positive_dt_mask) else 1.0 / max(1.0, fps_in)
        dt[~np.isfinite(dt) | (dt <= 0)] = dt_median
        dC = np.sqrt(np.sum(np.diff(C2, axis=0, prepend=C2[[0], :]) ** 2, axis=1))
        speed_inst = dC / dt
        speed_sub = speed_inst[idxs_full].astype(float)

        # 渲染用的滑動平均速度（依輸出幀序列）
        window_size = max(1, int(round(avg_window_s * (fps_in / stride))))
        if M >= window_size:
            csum = np.cumsum(np.insert(speed_sub, 0, 0.0))
            counts = np.cumsum(np.insert(np.isfinite(speed_sub).astype(np.int32), 0, 0))
            spd_avg_arr = (csum[window_size:] - csum[:-window_size]) / np.maximum(1, (counts[window_size:] - counts[:-window_size]))
            head = np.full(window_size - 1, 0.0, dtype=float)
            spd_avg_arr = np.concatenate([head, spd_avg_arr])
        else:
            spd_avg_arr = np.full(M, 0.0, dtype=float)

        # 文字時間標籤
        minutes = (t_sub // 60).astype(int)
        seconds = t_sub % 60.0
        time_labels = np.array([f"{m}:{s:05.2f}" for m, s in zip(minutes, seconds)])

        # 建立 figure 與三個 axes
        fig = plt.figure(figsize=figsize, dpi=dpi)
        canvas = FigureCanvas(fig)
        left_margin = 0.02
        ax_legend = fig.add_axes([left_margin, 0.18, 0.10, 0.76], facecolor=bg_color)
        ax_main = fig.add_axes([left_margin + 0.12, 0.18, 1.0 - (left_margin + 0.14), 0.76], facecolor=bg_color)
        ax_info = fig.add_axes([0.00, 0.02, 1.00, 0.12], facecolor=bg_color)
        ax_legend.set_axis_off()

        # 圖例內容
        legend_handles: List[Line2D] = [
            Line2D([], [], color=path_color_L, lw=1.4, label="L hip (full)"),
            Line2D([], [], color=path_color_R, lw=1.4, label="R hip (full)"),
            Line2D([], [], marker="s", markersize=8, color=chair_color, lw=0, label="Chair"),
            Line2D([], [], marker="^", markersize=8, color=cone_color, lw=0, label="Cone"),
            Line2D([], [], color=trail_color_L, lw=2.2, label="L hip (tail)"),
            Line2D([], [], color=trail_color_R, lw=2.2, label="R hip (tail)"),
            Line2D([], [], color="#2b2b2b", lw=2.0, label="Pelvis"),
        ]
        if draw_radius:
            if np.isfinite(rC) and rC > 0:
                legend_handles.append(Line2D([], [], color=chair_color, lw=1.5, ls="--", label=f"Chair radius ({rC:.2f} m)"))
            if np.isfinite(rK) and rK > 0:
                legend_handles.append(Line2D([], [], color=cone_color, lw=1.5, ls="--", label=f"Cone radius ({rK:.2f} m)"))
        if draw_turn_markers:
            legend_handles.extend([
                Line2D([], [], marker="o", markersize=8, color=turn_cone_start_color, lw=0, label="Cone-turn start"),
                Line2D([], [], marker="X", markersize=8, color=turn_cone_end_color, lw=0, label="Cone-turn end"),
                Line2D([], [], marker="D", markersize=8, color=turn_chair_start_color, lw=0, label="Chair-turn start"),
                Line2D([], [], marker="P", markersize=8, color=turn_chair_end_color, lw=0, label="Chair-turn end"),
            ])
        ax_legend.legend(handles=legend_handles, loc="upper left", frameon=False, fontsize=9)

        # 靜態軌跡與椅 / 錐位置（仍用 full，保持原本效果）
        ax_main.plot(L2[valid, 0], L2[valid, 1], lw=1.0, alpha=0.55, color=path_color_L, zorder=1)
        ax_main.plot(R2[valid, 0], R2[valid, 1], lw=1.0, alpha=0.50, color=path_color_R, zorder=1)
        ax_main.scatter([chair_pos[0]], [chair_pos[1]], s=80, color=chair_color, marker="s", zorder=4)
        ax_main.scatter([cone_pos[0]], [cone_pos[1]], s=80, color=cone_color, marker="^", zorder=4)

        # 半徑顯示
        if draw_radius:
            if np.isfinite(rC) and rC > 0:
                ax_main.add_patch(Circle(chair_pos, rC, fill=False, lw=1.5, ls="--", color=chair_color, alpha=0.9, clip_on=False))
            if np.isfinite(rK) and rK > 0:
                ax_main.add_patch(Circle(cone_pos, rK, fill=False, lw=1.5, ls="--", color=cone_color, alpha=0.9, clip_on=False))

        # 轉身標記的 scatter（先建立空的，之後逐幀更新）
        cone_turn_start_sc = ax_main.scatter([], [], s=70, marker="o", color=turn_cone_start_color, alpha=0.95, zorder=6)
        cone_turn_end_sc = ax_main.scatter([], [], s=70, marker="X", color=turn_cone_end_color, alpha=0.95, zorder=6)
        chair_turn_start_sc = ax_main.scatter([], [], s=70, marker="D", color=turn_chair_start_color, alpha=0.95, zorder=6)
        chair_turn_end_sc = ax_main.scatter([], [], s=70, marker="P", color=turn_chair_end_color, alpha=0.95, zorder=6)

        # 全域 frame -> lap 映射
        frame_to_lap = np.full(num_frames, -1, dtype=int)
        for lap_idx, lap in enumerate(det.laps):
            start_idx_lap = max(0, int(lap.idx_start))
            end_idx_lap = min(num_frames - 1, int(lap.idx_end))
            if end_idx_lap >= start_idx_lap:
                frame_to_lap[start_idx_lap : end_idx_lap + 1] = lap_idx

        # 子序列中的圈索引
        lap_idx_sub = frame_to_lap[idxs_full]
        num_laps = len(det.laps)
        lap_first = np.full(num_laps, -1, dtype=int)
        for li in range(num_laps):
            idxs = np.where(lap_idx_sub == li)[0]
            if idxs.size:
                lap_first[li] = int(idxs[0])

        # Main axes 外觀
        ax_main.set_title("Trajectory - chair & cone", fontsize=13, pad=6, color="#111")
        ax_main.set_aspect("equal", adjustable="box")
        ax_main.set_xlim(xmin, xmax)
        ax_main.set_ylim(ymin, ymax)
        ax_main.xaxis.set_label_position("top")

        # 根據投影決定實際使用的資料軸，並套用 axis_convention 轉成 X/Y/Z 標籤：
        # - projection='xz' -> (raw X, raw Z)
        # - projection='xy' -> (raw X, raw Y)
        proj = (projection or "xz").lower()
        if proj == "xz":
            dim_x, dim_y = 0, 2
        elif proj == "xy":
            dim_x, dim_y = 0, 1
        else:
            dim_x, dim_y = 0, 2  # 理論上不會進來，仍給預設

        ax_main.set_xlabel(self._axis_label_for_data_dim(dim_x))
        ax_main.set_ylabel(self._axis_label_for_data_dim(dim_y))
        for side in ("top", "right"):
            ax_main.spines[side].set_visible(False)
        ax_main.grid(True, linestyle="--", alpha=0.18)

        # 底部資訊區（時間 / 速度文字）
        ax_info.set_xticks([]); ax_info.set_yticks([])
        for spine in ax_info.spines.values(): spine.set_visible(False)
        box_kwargs = dict(boxstyle="round,pad=0.33,rounding_size=0.20", fc="#ffffff", ec="#dddddd", lw=1.0, alpha=0.96)
        text_time = ax_info.text(0.5, 0.64, "", transform=ax_info.transAxes, ha="center", va="center", fontsize=12, color="#111", bbox=box_kwargs)
        text_speed = ax_info.text(0.5, 0.30, "", transform=ax_info.transAxes, ha="center", va="center", fontsize=12, color="#111")

        # 動態物件：尾巴 / 點 / 骨盆線
        tail_L, = ax_main.plot([], [], lw=2.4, color=trail_color_L, zorder=3, animated=True)
        tail_R, = ax_main.plot([], [], lw=2.4, color=trail_color_R, zorder=3, animated=True)
        head_L = ax_main.scatter([], [], s=36, color=dot_color_L, zorder=5)
        head_R = ax_main.scatter([], [], s=36, color=dot_color_R, zorder=5)
        pelvis_line, = ax_main.plot([], [], lw=2.0, color="#2b2b2b", zorder=4, alpha=0.9, animated=True)

        # 預先擷取背景（blit 用）
        fig.canvas.draw()
        bg_main = fig.canvas.copy_from_bbox(ax_main.bbox)
        bg_info = fig.canvas.copy_from_bbox(ax_info.bbox)

        # FFmpeg 管線初始化
        save_name_template = save_name or "trajectory_{left_joint}_{right_joint}.mp4"
        save_name_final = save_name_template.format(left_joint=left_joint, right_joint=right_joint)
        filename = add_prefix_to_filename(save_name_final, self.prefix)
        save_path = Path(self.out_dir) / filename
        save_path.parent.mkdir(parents=True, exist_ok=True)
        width = int(round(figsize[0] * dpi)); height = int(round(figsize[1] * dpi))
        pipe = FFmpegPipe(
            out_path=str(save_path),
            width=width,
            height=height,
            fps=fps_out,
            preset=ffmpeg_preset,
            crf=ffmpeg_crf,
            pixel_format="rgb24",
            extra_args=["-pix_fmt", "yuv420p"],
            loglevel="error",
        )

        tmp_offset = np.empty((1, 2), dtype=float)
        empty_points = np.empty((0, 2), dtype=float)

        try:
            for k in range(M):
                frame_idx = idxs_full[k]  # 只給 lap / marker 用
                fig.canvas.restore_region(bg_main)
                fig.canvas.restore_region(bg_info)

                # 尾巴區間：同一圈內顯示整圈軌跡；不在任何圈 -> 不畫尾巴
                lap_id = lap_idx_sub[k]
                if 0 <= lap_id < num_laps and lap_first[lap_id] >= 0:
                    seg_slice = slice(lap_first[lap_id], k + 1)
                    tail_L.set_data(L2_sub[seg_slice, 0], L2_sub[seg_slice, 1])
                    tail_R.set_data(R2_sub[seg_slice, 0], R2_sub[seg_slice, 1])
                else:
                    tail_L.set_data([], []); tail_R.set_data([], [])

                # 更新左右點位置（用 *_sub，避免再次 fancy indexing）
                tmp_offset[0, 0], tmp_offset[0, 1] = L2_sub[k, 0], L2_sub[k, 1]
                head_L.set_offsets(tmp_offset)
                tmp_offset[0, 0], tmp_offset[0, 1] = R2_sub[k, 0], R2_sub[k, 1]
                head_R.set_offsets(tmp_offset)

                # 更新骨盆線段
                pelvis_line.set_data([L2_sub[k, 0], R2_sub[k, 0]], [L2_sub[k, 1], R2_sub[k, 1]])

                # 更新轉身標記（用 full C2，因為 lap idx 是 full frame）
                if draw_turn_markers and det.laps:
                    lap_id_mark = frame_to_lap[frame_idx]
                    if 0 <= lap_id_mark < len(det.laps):
                        lap = det.laps[lap_id_mark]

                        def _get_point(idx: int) -> Optional[np.ndarray]:
                            return C2[idx] if 0 <= idx < num_frames else None

                        pts = {
                            "cone_start": _get_point(int(lap.idx_turn_cone_start)),
                            "cone_end": _get_point(int(lap.idx_turn_cone_end)),
                            "chair_start": _get_point(int(lap.idx_turn_chair_start)),
                            "chair_end": _get_point(int(lap.idx_turn_chair_end)),
                        }
                        cone_turn_start_sc.set_offsets(np.asarray(pts["cone_start"])[None, :] if pts["cone_start"] is not None else empty_points)
                        cone_turn_end_sc.set_offsets(np.asarray(pts["cone_end"])[None, :] if pts["cone_end"] is not None else empty_points)
                        chair_turn_start_sc.set_offsets(np.asarray(pts["chair_start"])[None, :] if pts["chair_start"] is not None else empty_points)
                        chair_turn_end_sc.set_offsets(np.asarray(pts["chair_end"])[None, :] if pts["chair_end"] is not None else empty_points)
                        ax_main.draw_artist(cone_turn_start_sc); ax_main.draw_artist(cone_turn_end_sc)
                        ax_main.draw_artist(chair_turn_start_sc); ax_main.draw_artist(chair_turn_end_sc)
                    else:
                        cone_turn_start_sc.set_offsets(empty_points)
                        cone_turn_end_sc.set_offsets(empty_points)
                        chair_turn_start_sc.set_offsets(empty_points)
                        chair_turn_end_sc.set_offsets(empty_points)

                ax_main.draw_artist(tail_L); ax_main.draw_artist(tail_R)
                ax_main.draw_artist(pelvis_line)
                ax_main.draw_artist(head_L); ax_main.draw_artist(head_R)

                spd_avg = spd_avg_arr[k] if k < spd_avg_arr.size else float("nan")
                text_time.set_text(f"t = {time_labels[k]} (avg over {avg_window_s:g}s)")
                speed_str = f"{spd_avg:.2f}" if np.isfinite(spd_avg) else "--.--"
                text_speed.set_text(f"speed {speed_str} m/s")
                ax_info.draw_artist(text_time); ax_info.draw_artist(text_speed)

                fig.canvas.blit(ax_main.bbox)
                fig.canvas.blit(ax_info.bbox)
                pipe.write_frame_from_canvas(canvas)
        finally:
            pipe.close()
            plt.close(fig)

        return save_path


# 速度時空熱圖（每圈）
class SpeedHeatmapMixin(VisualizerUtilsMixin):
    """
    每圈速度時空熱圖：

    - X 軸：規一化的進度（從離椅 → 回到椅）
    - Y 軸：圈數（Lap 1, Lap 2, ...）
    - 顏色：速度值（m/s）
    """

    def save_spatiotemporal_speed_heatmap(
        self,
        projection: str = DEFAULT_PROJECTION,
        smooth_window_s: float = DEFAULT_SMOOTH_WINDOW_S,
        flat_frac: float = DEFAULT_FLAT_FRAC,
        min_v_abs: float = DEFAULT_MIN_V_ABS,
        *,
        width: int = 300,
        dpi: int = 150,
        save_name: Optional[str] = None,
        vmin: Optional[float] = None,
        vmax: Optional[float] = None,
    ) -> Path:
        """對每圈做索引重採樣後，畫出速度時空熱圖（每列一圈）。"""
        fps = float(self._estimate_fps())
        smooth_window = max(1, int(round(smooth_window_s * fps)))
        L2, R2, _ = self._compute_hip_points(projection=projection, smooth_window=smooth_window)
        C2 = (L2 + R2) / 2.0
        _, speed, _ = self._speed_series(C2)

        det = self.detect_laps_auto(
            projection=projection,
            smooth_window_s=smooth_window_s,
            flat_frac=flat_frac,
            min_v_abs=min_v_abs,
        )
        laps = det.laps
        if not laps:
            raise ValueError("沒有圈數可視覺化。")

        def resample_1d(arr: np.ndarray, i0: int, i1: int, m: int) -> np.ndarray:
            """以索引為自變數，將 arr[i0:i1] 線性插值重採樣成 m 個點（含端點）。"""
            i0 = max(0, int(i0))
            i1 = max(0, int(i1))
            if i1 <= i0:
                raise ValueError("i1 必須大於 i0。")
            idx_src = np.linspace(i0, i1, num=(i1 - i0 + 1))
            idx_dst = np.linspace(i0, i1, num=m)
            return np.interp(idx_dst, idx_src, arr[i0 : i1 + 1])

        num_laps = len(laps)
        width = int(max(50, width))

        # mat[row, col] = 速度值
        mat = np.full((num_laps, width), np.nan, dtype=float)
        marks: List[Tuple[float, float]] = []

        for row, lap in enumerate(laps):
            start_idx = int(lap.idx_onset_end)
            end_idx = int(lap.idx_chair_sit_end)
            if end_idx <= start_idx:
                continue

            mat[row] = resample_1d(speed, start_idx, end_idx, width)
            denom = max(1, end_idx - start_idx)
            a = (lap.idx_turn_cone_start - start_idx) / denom
            b = (lap.idx_turn_cone_end - start_idx) / denom
            marks.append((a, b))

        fig = plt.figure(figsize=(12, max(3.6, 0.36 * num_laps)), dpi=dpi)
        ax = plt.gca()

        # 熱圖
        image = ax.imshow(mat, aspect="auto", interpolation="nearest", origin="upper", vmin=vmin, vmax=vmax)
        colorbar = fig.colorbar(image, ax=ax)
        colorbar.set_label("Speed (m/s)")

        # 在每圈上畫錐桶轉身區間的線
        for row, (a, b) in enumerate(marks):
            x1 = a * (width - 1)
            x2 = b * (width - 1)
            ax.plot([x1, x1], [row - 0.5, row + 0.5], ls="--", lw=1.0, c="w", alpha=0.8)
            ax.plot([x2, x2], [row - 0.5, row + 0.5], ls="--", lw=1.0, c="w", alpha=0.8)

        ax.set_yticks(np.arange(num_laps))
        ax.set_yticklabels([f"Lap {idx + 1}" for idx in range(num_laps)])

        # X 軸顯示 0%, 10%, ..., 100%
        xticks_pos = np.linspace(0, width - 1, 11)
        xticks_lbl = [f"{int(p)}%" for p in np.linspace(0, 100, 11)]
        ax.set_xticks(xticks_pos)
        ax.set_xticklabels(xticks_lbl)

        ax.set_xlabel("Normalized progress (leave → re-enter)")
        ax.set_title(f"{self.prefix} - Spatiotemporal speed heatmap")

        fig.tight_layout(pad=0.3)

        filename = add_prefix_to_filename(save_name or "speed_heatmap.png", self.prefix)
        save_path = Path(self.out_dir) / filename
        save_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(save_path))
        plt.close(fig)

        return save_path


# 每分鐘步頻與步長（上下兩圖）
class StepLengthBarsMixin(VisualizerUtilsMixin):
    """
    每分鐘步頻與步長：

    - 上圖：cadence (spm, steps/min)
    - 下圖：mean step length (m)

    資料來源：compute_gait_summary().per_interval
    """

    def save_minutely_cadence_step_length_bars(
        self,
        projection: str = DEFAULT_PROJECTION,
        smooth_window_s: float = DEFAULT_SMOOTH_WINDOW_S,
        flat_frac: float = DEFAULT_FLAT_FRAC,
        min_v_abs: float = DEFAULT_MIN_V_ABS,
        *,
        max_minutes: Optional[int] = None,
        dpi: int = 170,
        figsize_per_minute: float = 1.0,
        row_height: float = 3.2,
        bar_width: float = 0.28,
        capsize: float = 3.0,
        save_name: Optional[str] = None,
        spm_ylim: Optional[Tuple[float, float]] = None,
        steplen_ylim: Optional[Tuple[float, float]] = None,
    ) -> Path:
        """
        產生單張圖（上：步頻 spm、下：步長 m），每分鐘一根柱。

        使用 compute_gait_summary().per_interval 的彙整結果。
        """
        summary = self.compute_gait_summary(
            smooth_window_s=smooth_window_s,
            projection=projection,
            flat_frac=flat_frac,
            min_v_abs=min_v_abs,
        )
        per_interval = summary.per_interval or []
        if not per_interval:
            raise ValueError("沒有每分鐘區間可視覺化（per_interval 為空）。")

        if max_minutes is not None:
            per_interval = per_interval[: max(1, int(max_minutes))]

        M = len(per_interval)
        minutes = np.arange(1, M + 1, dtype=int)

        # 每分鐘的步頻與步長
        mu_spm = np.array([float(interval.spm) for interval in per_interval], dtype=float)
        mu_len = np.array([float(interval.mean_step_len_m) for interval in per_interval], dtype=float)

        # 每分鐘樣本數 = 左右腳步數總和
        n_spm = np.array([int(interval.left_step_count + interval.right_step_count) for interval in per_interval], dtype=int)

        color_bar = "#2563eb"
        fig_width = max(7.5, float(M) * float(figsize_per_minute))
        fig_height = row_height * 2.0

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(fig_width, fig_height), dpi=dpi, sharex=True)

        x = minutes.astype(float)

        # 上圖：步頻
        bars_spm = ax1.bar(x, mu_spm, width=bar_width, capsize=capsize, color=color_bar)
        ax1.set_title("Cadence (SPM)", pad=8)
        ax1.set_ylabel("Steps/min")
        ax1.grid(True, axis="y", linestyle="--", alpha=0.25)
        for side in ("top", "right"):
            ax1.spines[side].set_visible(False)
        self._apply_limits(ax1, ylim=spm_ylim)

        # 下圖：步長
        bars_len = ax2.bar(x, mu_len, width=bar_width, capsize=capsize, color=color_bar)
        ax2.set_title("Step length (m)", pad=8)
        ax2.set_ylabel("Meters")
        ax2.grid(True, axis="y", linestyle="--", alpha=0.25)
        for side in ("top", "right"):
            ax2.spines[side].set_visible(False)
        self._apply_limits(ax2, ylim=steplen_ylim)

        # X 軸：分鐘與樣本數
        ax2.set_xlabel("Minute (from start)")
        ax2.set_xticks(x)
        ax2.set_xticklabels([f"{m}\n(n={int(n)})" for m, n in zip(minutes, n_spm)])

        def annotate_bars(
            axis: plt.Axes,
            bar_container,
            values: np.ndarray,
            fmt: Callable[[float], str],
        ) -> None:
            """在柱頂標註數值。"""
            if not np.isfinite(values).any():
                return

            ymax = float(np.nanmax(values))
            ypad = 0.02 * ymax if np.isfinite(ymax) and ymax > 0 else 0.05

            for rect, value in zip(bar_container, values):
                if not np.isfinite(value):
                    continue
                top = float(value)
                axis.text(rect.get_x() + rect.get_width() / 2.0, top + ypad, fmt(float(value)), ha="center", va="bottom", fontsize=9, color="#222")

        annotate_bars(ax1, bars_spm, mu_spm, fmt=lambda v: f"{v:.1f}")
        annotate_bars(ax2, bars_len, mu_len, fmt=lambda v: f"{v:.2f} m")

        fig.suptitle(f"{self.prefix} - Per-minute cadence & step length", y=0.995)

        filename = add_prefix_to_filename(save_name or "minutely_cadence_step_length_bars.png", self.prefix)
        save_path = Path(self.out_dir) / filename
        save_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(save_path))
        plt.close(fig)

        return save_path


# 擺動資訊熱力圖與柱狀圖
class SwingInfoHeatmapMixin(VisualizerUtilsMixin):
    """
    擺動百分比與秒數（每分鐘區間）的可視化：

    - 熱力圖：左/右腳 swing% 與秒數文字標註
    - 柱狀圖：左/右腳 stance / swing 時間
    """

    def save_swing_info_heatmap(
        self,
        projection: str = DEFAULT_PROJECTION,
        smooth_window_s: float = DEFAULT_SMOOTH_WINDOW_S,
        flat_frac: float = DEFAULT_FLAT_FRAC,
        min_v_abs: float = DEFAULT_MIN_V_ABS,
        *,
        dpi: int = 150,
        figsize_per_col: float = 0.9,
        save_name: Optional[str] = None,
        vmin_pct: Optional[float] = None,
        vmax_pct: Optional[float] = None,
    ) -> Path:
        """
        使用 compute_gait_summary().per_interval 製作 swing% 熱力圖，
        每格同時顯示 swing% 與 swing 秒數。
        """
        summary = self.compute_gait_summary(
            smooth_window_s=smooth_window_s,
            projection=projection,
            flat_frac=flat_frac,
            min_v_abs=min_v_abs,
        )
        per_interval = summary.per_interval or []
        if not per_interval:
            raise ValueError("沒有每分鐘區間可視覺化（per_interval 為空）。")

        L = len(per_interval)

        # H_pct[0, :] = 左腳 swing%，H_pct[1, :] = 右腳 swing%
        H_pct = np.full((2, L), np.nan, dtype=float)
        H_sec = np.full((2, L), np.nan, dtype=float)

        for j, interval in enumerate(per_interval):
            H_pct[0, j] = interval.l_swing_pct_mean
            H_pct[1, j] = interval.r_swing_pct_mean
            H_sec[0, j] = interval.l_swing_s_mean
            H_sec[1, j] = interval.r_swing_s_mean

        fig_width = max(6.0, L * figsize_per_col + 2.0)
        fig_height = 4.0
        fig, ax = plt.subplots(figsize=(fig_width, fig_height), dpi=dpi, layout="constrained")

        image = ax.imshow(H_pct, aspect="auto", vmin=vmin_pct, vmax=vmax_pct)
        ax.set_yticks([0, 1])
        ax.set_yticklabels(["Left", "Right"])

        xticklabels = [f"Min {k}" for k in range(L)]
        ax.set_xticks(np.arange(L))
        ax.set_xticklabels(xticklabels)

        # 畫細格線
        ax.set_xticks(np.arange(-0.5, L, 1), minor=True)
        ax.set_yticks(np.arange(-0.5, 2, 1), minor=True)
        ax.grid(which="minor", linewidth=0.8, alpha=0.6)
        ax.tick_params(which="minor", bottom=False, left=False)

        # 在格內標註 swing% 與秒數
        for row in range(2):
            for col in range(L):
                pct = H_pct[row, col]
                sec = H_sec[row, col]
                if np.isfinite(pct) and np.isfinite(sec):
                    text = f"{pct:.1f}%\n{sec:.2f}s"
                elif np.isfinite(pct):
                    text = f"{pct:.1f}%"
                else:
                    text = "n/a"
                ax.text(col, row, text, ha="center", va="center", fontsize=10)

        colorbar = fig.colorbar(image, ax=ax, shrink=0.9)
        colorbar.set_label("Swing (% of stride)")

        ax.set_title(f"{self.prefix} - Swing percentage (per minute)")

        filename = add_prefix_to_filename(save_name or "swing_info_heatmap.png", self.prefix)
        save_path = Path(self.out_dir) / filename
        save_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(save_path))
        plt.close(fig)

        return save_path

    def save_minutely_stance_swing_bars(
        self,
        projection: str = DEFAULT_PROJECTION,
        smooth_window_s: float = DEFAULT_SMOOTH_WINDOW_S,
        flat_frac: float = DEFAULT_FLAT_FRAC,
        min_v_abs: float = DEFAULT_MIN_V_ABS,
        *,
        max_minutes: Optional[int] = None,
        dpi: int = 170,
        figsize_per_minute: float = 0.9,
        row_height: float = 3.1,
        bar_width: float = 0.28,
        group_gap: float = 0.18,
        capsize: float = 3.0,
        save_name: Optional[str] = None,
        stance_ylim: Optional[Tuple[float, float]] = None,
        swing_ylim: Optional[Tuple[float, float]] = None,
    ) -> Path:
        """
        使用 compute_gait_summary().per_interval 直接繪製：

        - 站立期 (stance) 時間
        - 擺動期 (swing) 時間

        左 / 右腳並列柱狀圖。
        """
        summary = self.compute_gait_summary(
            smooth_window_s=smooth_window_s,
            projection=projection,
            flat_frac=flat_frac,
            min_v_abs=min_v_abs,
        )
        per_interval = summary.per_interval or []
        if not per_interval:
            raise ValueError("沒有每分鐘區間可視覺化（per_interval 為空）。")

        if max_minutes is not None:
            per_interval = per_interval[: max(1, int(max_minutes))]

        M = len(per_interval)
        minutes = np.arange(M, dtype=int)

        # 每分鐘彙整的左右腳 stance / swing 秒數
        mu_ls = np.array([float(interval.l_stance_s_mean) for interval in per_interval], dtype=float)
        mu_rs = np.array([float(interval.r_stance_s_mean) for interval in per_interval], dtype=float)
        mu_lw = np.array([float(interval.l_swing_s_mean) for interval in per_interval], dtype=float)
        mu_rw = np.array([float(interval.r_swing_s_mean) for interval in per_interval], dtype=float)

        color_left = "#2563eb"
        color_right = "#ef4444"

        fig_width = max(7.0, float(M) * float(figsize_per_minute))
        fig_height = row_height * 2.0

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(fig_width, fig_height), dpi=dpi, sharex=True, layout="constrained")

        x = minutes.astype(float)
        offset = bar_width + group_gap / 2.0

        x_ls = x - offset / 2.0
        x_rs = x + offset / 2.0

        # 站立期時間
        bars_ls = ax1.bar(x_ls, mu_ls, width=bar_width, capsize=capsize, label="Left", color=color_left)
        bars_rs = ax1.bar(x_rs, mu_rs, width=bar_width, capsize=capsize, label="Right", color=color_right)
        ax1.set_title("Stance time")
        ax1.set_ylabel("Duration (s)")
        ax1.grid(True, axis="y", linestyle="--", alpha=0.25)
        for side in ("top", "right"):
            ax1.spines[side].set_visible(False)
        self._apply_limits(ax1, ylim=stance_ylim)

        # 擺動期時間
        bars_lw = ax2.bar(x_ls, mu_lw, width=bar_width, capsize=capsize, label="Left", color=color_left)
        bars_rw = ax2.bar(x_rs, mu_rw, width=bar_width, capsize=capsize, label="Right", color=color_right)
        ax2.set_title("Swing time")
        ax2.set_ylabel("Duration (s)")
        ax2.grid(True, axis="y", linestyle="--", alpha=0.25)
        for side in ("top", "right"):
            ax2.spines[side].set_visible(False)
        self._apply_limits(ax2, ylim=swing_ylim)

        ax2.set_xlabel("Minute (from start)")
        ax2.set_xticks(x)

        # 每分鐘步數總和當作 n
        n_per_minute = np.array([int(interval.left_step_count + interval.right_step_count) for interval in per_interval], dtype=int)
        ax2.set_xticklabels([f"{m}\n(n={int(count)})" for m, count in zip(minutes, n_per_minute)])

        def annotate_bars(
            axis: plt.Axes,
            bar_container,
            values: np.ndarray,
        ) -> None:
            """在柱頂顯示秒數。"""
            if not np.isfinite(values).any():
                return

            ypad = 0.02 * float(np.nanmax(values))

            for rect, value in zip(bar_container, values):
                if not np.isfinite(value):
                    continue
                top = float(value)
                axis.text(rect.get_x() + rect.get_width() / 2.0, top + ypad, f"{value:.2f}s", ha="center", va="bottom", fontsize=9, color="#222")

        annotate_bars(ax1, bars_ls, mu_ls)
        annotate_bars(ax1, bars_rs, mu_rs)
        annotate_bars(ax2, bars_lw, mu_lw)
        annotate_bars(ax2, bars_rw, mu_rw)

        fig.suptitle(f"{self.prefix} - Per-minute stance/swing durations", y=0.995)

        # 調整圖的位置給右側圖例留空間
        for axis in (ax1, ax2):
            box = axis.get_position()
            axis.set_position([box.x0, box.y0, box.width * 0.83, box.height])

        ax1.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), frameon=False, ncol=1, title="Side")
        ax2.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), frameon=False, ncol=1, title="Side")

        filename = save_name or "minutely_stance_swing_bars.png"
        save_path = self.out_dir / add_prefix_to_filename(filename, self.prefix)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(save_path))
        plt.close(fig)

        return save_path


# 時頻分析：空間頻譜（X(Z) 或 Y(Z)）
class TimeFrequencyMixin(VisualizerUtilsMixin):
    """
    時頻分析相關繪圖（目前實作空間頻譜）：

    - 以 Z 為自變數，X 或 Y 為依變數，做空間 periodogram。
    """

    def _save_spatial_spectrum_zind(
        self,
        pair: Literal["xz", "yz"] = "xz",
        *,
        k_smooth: int = 2,
        dpi: int = 150,
        min_peak_distance_ratio: float = 0.01,
        min_db: float = -40.0,
        min_freq: float = 0.5,
        save_name: Optional[str] = None,
        top_k: Optional[int] = None,
        spec_ylim: Optional[Tuple[float, float]] = None,
    ) -> Path:
        """
        實際繪製一個 pair 的空間頻譜圖（以 dB 顯示）。

        pair:
            "xz" 表 X(Z)，"yz" 表 Y(Z)
        spec_ylim:
            y 軸範圍（單位 dB，0 dB 代表此頻譜中的最大值）
        """
        # 計算空間功率譜（線性值）
        f, spec = self.compute_spatial_spectrum_zind(pair=pair, k_smooth=k_smooth)

        # 轉成 numpy array，避免後面型別問題
        f = np.asarray(f, dtype=float)
        spec = np.asarray(spec, dtype=float)

        # 轉成 dB。這裡用「相對最大值」：
        # 0 dB = 該頻譜的最大值
        # 其他皆為負值
        eps = np.finfo(float).tiny
        max_spec = float(spec.max()) if spec.size else 0.0
        if max_spec <= 0.0:
            # 如果全部都是 0，避免 log(0)，乾脆畫一條很低的常數線
            spec_db = np.full_like(spec, -300.0)
        else:
            spec_db = 10.0 * np.log10(np.maximum(spec / max_spec, eps))

        # 依據目前 axis_convention 把 pair ('xz' / 'yz') 映射到概念軸
        dep_label, indep_label = self._axis_labels_for_pair(pair)
        label_axis = f"{dep_label}({indep_label})"

        fig, ax = plt.subplots(figsize=(12, 4.2), dpi=dpi, layout="constrained")
        ax.plot(f, spec_db, lw=1.6, label=f"{label_axis} spectrum (periodogram, dB)")

        if spec_db.size >= 3 and top_k is not None:
            # 找局部極大值：spec_db[i] >= 左右兩邊
            idx_candidates = []
            for i in range(1, spec_db.size - 1):
                if not np.isfinite(spec_db[i]):
                    continue
                if f[i] < min_freq:
                    continue
                if spec_db[i] < min_db:
                    continue
                if spec_db[i] >= spec_db[i - 1] and spec_db[i] >= spec_db[i + 1]:
                    idx_candidates.append(i)

            if idx_candidates:
                idx_candidates = np.asarray(idx_candidates, dtype=int)

                # 依 dB 值由高到低排序
                order = np.argsort(spec_db[idx_candidates])[::-1]
                idx_sorted = idx_candidates[order]

                # 要求 peak 之間在頻率軸有最小間距，避免文字重疊
                f_span = float(f.max() - f.min()) if f.size else 0.0
                min_df = min_peak_distance_ratio * f_span if f_span > 0.0 else 0.0

                chosen: list[int] = []
                for idx in idx_sorted:
                    if len(chosen) >= top_k:
                        break
                    if not chosen:
                        chosen.append(idx)
                    else:
                        if all(abs(f[idx] - f[j]) >= min_df for j in chosen):
                            chosen.append(idx)

                # 估個 y 方向偏移量，讓文字不要壓到點上
                if spec_ylim is not None:
                    y_span = float(spec_ylim[1] - spec_ylim[0])
                    dy = 0.04 * y_span
                else:
                    dy = 2.0

                for idx in chosen:
                    x = float(f[idx])
                    y = float(spec_db[idx])

                    ax.scatter([x], [y], s=35, zorder=5, color="#f97316")

                    # 箭頭 + 小框框標註頻率與 dB，分兩行比較清楚
                    ax.annotate(
                        f"{x:.3g}\n{y:.1f} dB",
                        xy=(x, y),
                        xytext=(0, 10 + dy),
                        textcoords="offset points",
                        ha="center",
                        va="bottom",
                        fontsize=9,
                        bbox=dict(boxstyle="round,pad=0.2", fc="white", alpha=0.8),
                        arrowprops=dict(arrowstyle="->", lw=0.8),
                        clip_on=True,
                    )

        pair_str = f"{dep_label}{indep_label}"
        ax.set_xlabel(f"Spatial frequency (cycles / unit-{pair_str})")
        ax.set_ylabel("Power (dB, re max = 0 dB)")
        ax.set_title(f"{self.prefix} - Spatial spectrum with {pair_str} as independent")
        ax.grid(True, alpha=0.3)
        self._apply_limits(ax, ylim=spec_ylim)

        default_name = (save_name or "{pair}_spatial_spectrum_db.png").format(
            pair=pair_str
        )
        filename = add_prefix_to_filename(default_name, self.prefix)
        save_path = self.out_dir / filename
        save_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(save_path))
        plt.close(fig)
        return save_path

    def save_spatial_spectrum(
        self,
        *,
        pair: List[Literal["xz", "yz"]] = ["xz", "yz"],
        k_smooth: int = 2,
        top_k: Optional[int] = None,
        dpi: int = 150,
        spec_ylim: Optional[List[Tuple[float, float]]] = None,
        save_name: Optional[Union[str, List[str]]] = None,
    ) -> List[Path]:
        """
        一次產生多個空間頻譜圖。

        pair:
            例如 ["xz", "yz"]
        spec_ylim:
            每個 pair 對應一組縱軸範圍
        save_name:
            可傳字串或字串列表（與 pair 對應）
        """
        save_paths: List[Path] = []

        for idx, p in enumerate(pair):
            if p not in ("xz", "yz"):
                raise ValueError(f"pair 必須是 'xz' 或 'yz'，但得到 {p}")

            if isinstance(save_name, list):
                this_save_name: Optional[str] = save_name[idx]
            else:
                this_save_name = save_name

            this_ylim = spec_ylim[idx] if spec_ylim is not None else None

            save_path = self._save_spatial_spectrum_zind(
                pair=p,
                k_smooth=k_smooth,
                top_k=top_k,
                dpi=dpi,
                save_name=this_save_name,
                spec_ylim=this_ylim,
            )
            save_paths.append(save_path)

        return save_paths

    def save_multi_fft_from_series(
        self,
        joints: Sequence[Union[int, str, Sequence[Union[int, str]]]],
        labels: Sequence[str],
        *,
        component: Literal["x", "y", "z"] = "z",
        max_peaks: int = 3,
        dpi: int = 150,
        figsize: Tuple[float, float] = (11.0, 4.0),
        min_peak_distance_ratio: float = 0.01,
        min_db: float = -40.0,
        min_freq: float = 0.05,
        save_name: Optional[str] = None,
        xlim: Optional[Tuple[float, float]] = None,
        ylim: Optional[Tuple[float, float]] = None,
        fft_params: Optional[Mapping[str, Any]] = None,
    ) -> Path:
        """
        對多條時間序列做 FFT/PSD，畫在同一張圖上。

        joints:
            - 可以是單一關節編號/名稱，例如 27, "L_HEEL"
            - 也可以是關節群，例如 [27, 28]，代表先在指定 component 上做平均再 FFT
            - 輸入例子: [[27, 28], 27, 28]

        labels:
            - 每條線的標籤，長度需與 joints 一致

        component:
            - "x", "y", "z" -> self.arr[:, joint_idx, component_idx]

        max_peaks:
            - 每條線要標註前幾個最高峰 (0 表示不標註)
        """
        if not joints:
            raise ValueError("joints 不能是空的。")
        if len(joints) != len(labels):
            raise ValueError("joints 與 labels 長度必須一致。")

        # component: "x", "y", "z" -> index 0/1/2
        match component:
            case "x":
                component_idx = 0
            case "y":
                component_idx = 1
            case "z":
                component_idx = 2
            case _:
                raise ValueError(f"component 必須是 'x', 'y', 'z'，但得到 {component}")

        def _series_from_joint_spec(
            spec: Union[int, str, Sequence[Union[int, str]]]
        ) -> np.ndarray:
            """
            spec 可以是：
                - 單一關節 (int / str)
                - 關節群 (Sequence[int|str])，會先平均

            回傳 shape = (N,) 的 1D 序列。
            """
            if isinstance(spec, (list, tuple, np.ndarray)):  # 關節群
                if not spec:
                    raise ValueError("joint group 不能是空的。")
                idxs = [self.resolve_joint(j) for j in spec]
                arr_group = self.arr[:, idxs, component_idx]  # (N, K)
                return np.mean(arr_group, axis=1)            # (N,)

            # 單一關節
            idx = self.resolve_joint(spec)
            return self.arr[:, idx, component_idx]

        def _select_peak_indices(
            f: np.ndarray,
            psd_db: np.ndarray,
            *,
            max_peaks: int,
            xlim: Optional[Tuple[float, float]],
            min_peak_distance_ratio: float,
            min_db: float,
            min_freq: float,
        ) -> list[int]:
            """
            從單一 PSD 曲線中挑出要標註的 peak index。
            回傳依 dB 由大到小排序後、且彼此間至少相隔一定頻率的 index 列表。
            """
            if max_peaks <= 0 or psd_db.size <= 2:
                return []

            # 頻率範圍與最小間距
            if xlim is not None:
                f_min, f_max = xlim
            else:
                f_min, f_max = float(f.min()), float(f.max())
            f_span = max(f_max - f_min, 1e-9)
            min_df = min_peak_distance_ratio * f_span

            # 基本候選條件：頻率在範圍內、> min_freq、dB 過門檻
            base_mask = np.isfinite(psd_db)
            base_mask &= psd_db >= min_db
            base_mask &= f >= max(min_freq, f_min)
            base_mask &= f <= f_max

            idx_all = np.nonzero(base_mask)[0]
            if idx_all.size == 0:
                return []

            # 先記住整體最高點（確保一定會被納入）
            best_idx_global = int(idx_all[np.nanargmax(psd_db[idx_all])])

            # 只保留「局部極大值」
            idx_candidates: list[int] = []
            for idx in idx_all:
                if idx == 0 or idx == psd_db.size - 1:
                    continue
                if psd_db[idx] >= psd_db[idx - 1] and psd_db[idx] >= psd_db[idx + 1]:
                    idx_candidates.append(idx)

            if best_idx_global not in idx_candidates:
                idx_candidates.append(best_idx_global)

            idx_candidates_arr = np.asarray(idx_candidates, dtype=int)

            # 依 dB 值由高到低排序
            order = np.argsort(psd_db[idx_candidates_arr])[::-1]
            idx_sorted = idx_candidates_arr[order]

            # 要求 peak 之間在頻率軸有最小間距，避免文字重疊
            chosen: list[int] = []
            for idx in idx_sorted:
                if len(chosen) >= max_peaks:
                    break
                if not chosen or all(abs(f[idx] - f[j]) >= min_df for j in chosen):
                    chosen.append(idx)

            return chosen

        # 計算每條線的 FFT / PSD，順便找出全域最大 PSD 方便轉成 dB
        fft_kwargs = dict(fft_params or {})
        results = []
        max_power = 0.0
        for joint_spec in joints:
            series = _series_from_joint_spec(joint_spec)
            res = self.compute_lateral_offset_fft(
                lat=np.asarray(series, dtype=float),
                t=self.t,
                **fft_kwargs,
            )
            results.append(res)
            if res.Pxx.size:
                pmax = float(np.nanmax(res.Pxx))
                if np.isfinite(pmax):
                    max_power = max(max_power, pmax)

        # 避免全部都是 0 或 NaN
        eps = np.finfo(float).tiny
        if not np.isfinite(max_power) or max_power <= 0.0:
            max_power = 1.0

        fig, ax = plt.subplots(figsize=figsize, dpi=dpi, layout="constrained")

        # 畫每一條 PSD 曲線 +（可選）標註最高幾個點（避免重疊）
        for res, label in zip(results, labels):
            f = np.asarray(res.f, dtype=float)
            Pxx = np.asarray(res.Pxx, dtype=float)
            if f.size == 0 or Pxx.size == 0:
                continue

            psd_db = 10.0 * np.log10(np.maximum(Pxx / max_power, eps))
            (line,) = ax.plot(f, psd_db, lw=1.6, label=str(label))
            color = line.get_color()

            peak_indices = _select_peak_indices(
                f,
                psd_db,
                max_peaks=max_peaks,
                xlim=xlim,
                min_peak_distance_ratio=min_peak_distance_ratio,
                min_db=min_db,
                min_freq=min_freq,
            )
            if not peak_indices:
                continue

            # 估一個 y 偏移量，讓文字不要壓在點上
            if ylim is not None:
                y_span = float(ylim[1] - ylim[0])
            else:
                y_span = float(np.nanmax(psd_db) - np.nanmin(psd_db) + 1e-6)
            dy = 0.04 * y_span

            # 用頻帶範圍決定標籤左右對齊
            if xlim is not None:
                f_min, f_max = xlim
            else:
                f_min, f_max = float(f.min()), float(f.max())
            f_span = max(f_max - f_min, 1e-9)
            left_zone = f_min + 0.2 * f_span
            right_zone = f_min + 0.8 * f_span

            for idx in peak_indices:
                x = float(f[idx])
                y = float(psd_db[idx])

                ax.scatter([x], [y], s=18, color=color)

                if x < left_zone:
                    ha, dx = "left", 4
                elif x > right_zone:
                    ha, dx = "right", -4
                else:
                    ha, dx = "center", 0

                ax.annotate(
                    f"{x:.3g} Hz, {y:.1f} dB",
                    xy=(x, y),
                    xytext=(dx, dy),
                    textcoords="offset points",
                    fontsize=8,
                    ha=ha,
                    va="bottom",
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", alpha=0.8),
                    arrowprops=dict(arrowstyle="->", lw=0.8),
                    clip_on=True,
                )

        def _format_joint_spec_for_filename(spec: Union[int, str, Sequence[Union[int, str]]]) -> str:
            """把單一 joints 規格轉成適合檔名的字串（不含中括號、逗號）。"""
            if isinstance(spec, (list, tuple, np.ndarray)):
                return "_".join(str(x) for x in spec)
            return str(spec)
        
        joints_str = "_".join(_format_joint_spec_for_filename(j) for j in joints)
        ax.set_xlabel("Frequency (Hz)")
        ax.set_ylabel("Power (dB, re max = 0 dB)")
        ax.set_title(f"{self.prefix}-{joints_str} - Multi-series FFT")
        ax.grid(True, alpha=0.3)
        ax.legend(loc="upper right", frameon=False)
        self._apply_limits(ax, xlim=xlim, ylim=ylim)
        
        default_name = (save_name or "{joints}_multi_fft.png").format(joints=joints_str)
        filename = add_prefix_to_filename(default_name, self.prefix)
        save_path = self.out_dir / filename
        save_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(save_path))
        plt.close(fig)
        return save_path


# 左右偏移診斷圖（每圈）
class LateralOffsetPlotterMixin(VisualizerUtilsMixin):
    """
    每圈 lateral offset 診斷圖：

    - 子圖 A：lateral offset vs time（含原始 / 平滑）
    - 子圖 B： lateral offset 的 FFT / PSD
    - 子圖 C：骨盆朝向 θ(t)（以圈起點為 0°）
    """
    def _resolve_theta_ylim_for_lap(
        self,
        theta_ylim: Optional[List[Tuple[float, float]]],
        theta_values: np.ndarray,
    ) -> Optional[Tuple[float, float]]:
        """
        根據這一圈的 theta(t) 和使用者傳進來的 theta_ylim，
        自動決定本圈要用哪一組 y 軸範圍。

        支援：
            - 單一 (lo, hi)
            - 多組 [(lo1, hi1), (lo2, hi2), ...]
        """
        if theta_ylim is None:
            return None

        # 整理出候選區間列表 candidates
        # 如果是單一 (lo, hi)，就包成一個 list
        # 如果是多組 [(lo1, hi1), ...]，就逐一檢查
        candidates: List[Tuple[float, float]] = []

        if isinstance(theta_ylim, (list, tuple)) and len(theta_ylim) == 2 \
        and all(np.isscalar(v) for v in theta_ylim):
            # 單一區間
            lo, hi = float(theta_ylim[0]), float(theta_ylim[1])
            if np.isfinite(lo) and np.isfinite(hi) and hi > lo:
                candidates.append((lo, hi))
        else:
            # 多組區間
            for item in theta_ylim:
                if not isinstance(item, (list, tuple)) or len(item) != 2:
                    continue
                lo, hi = float(item[0]), float(item[1])
                if np.isfinite(lo) and np.isfinite(hi) and hi > lo:
                    candidates.append((lo, hi))

        if not candidates:
            return None

        # 找出「涵蓋點數最多」的那個區間；
        # 若打平，選較窄的區間。
        theta_arr = np.asarray(theta_values, dtype=float)
        valid = np.isfinite(theta_arr)
        if not valid.any():
            # 全 NaN 的話，只能隨便選一個
            return candidates[0]

        best_range: Tuple[float, float] = candidates[0]
        best_score = -1
        best_span = float("inf")

        for lo, hi in candidates:
            inside = valid & (theta_arr >= lo) & (theta_arr <= hi)
            score = int(inside.sum())
            span = hi - lo

            if score > best_score or (score == best_score and span < best_span):
                best_score = score
                best_span = span
                best_range = (lo, hi)

        # 如果所有候選都沒涵蓋到任何資料點，就用資料本身範圍
        if best_score == 0:
            y_min = float(np.nanmin(theta_arr[valid]))
            y_max = float(np.nanmax(theta_arr[valid]))
            if np.isfinite(y_min) and np.isfinite(y_max):
                margin = 0.05 * (y_max - y_min + 1e-6)
                return (y_min - margin, y_max + margin)

        return best_range

    def save_per_lap_offset(
        self,
        projection: str = DEFAULT_PROJECTION,
        smooth_window_s: float = DEFAULT_SMOOTH_WINDOW_S,
        flat_frac: float = DEFAULT_FLAT_FRAC,
        min_v_abs: float = DEFAULT_MIN_V_ABS,
        *,
        k_smooth: int = 1,
        fft_band: Tuple[float, float] = (0.00, 2.0),
        dpi: int = 130,
        num_indices: Optional[List[int]] = None,
        max_points_plot: Optional[int] = 150,
        show_samples: bool = True,
        save_name: Optional[str] = None,
        lat_ylim: Optional[Tuple[float, float]] = None,
        psd_ylim: Optional[Tuple[float, float]] = None,
        theta_ylim: Optional[List[Tuple[float, float]]] = None,
        fft_params: Optional[Mapping[str, Any]] = None,
    ) -> List[Path]:
        """
        針對每圈產生三子圖：

        - lat(t) 原始與平滑後曲線
        - lat(t) 的頻譜 / PSD（只取走路時間，並以 dB 顯示）
        - θ(t)（以圈起始為 0°）

        會輸出多個檔案，每圈一張。
        """
        det = self.detect_laps_auto(
            projection=projection,
            smooth_window_s=smooth_window_s,
            flat_frac=flat_frac,
            min_v_abs=min_v_abs,
        )
        laps = det.laps
        if not laps:
            raise ValueError("沒有圈數可視覺化（laps 為空）。")

        save_paths: List[Path] = []
        save_name_template = save_name or "lap_{lap_idx}_diagnostics.png"
        save_name_template = add_prefix_to_filename(save_name_template, self.prefix)

        def compute_sample_idx(length: int, max_points: Optional[int]) -> np.ndarray:
            """決定要取樣的索引，用於畫 sample 點，避免點太密。"""
            if max_points is None or max_points <= 0 or length <= max_points:
                return np.arange(length, dtype=int)
            indices = np.linspace(0, length - 1, num=int(max_points), dtype=int)
            indices = np.unique(
                np.concatenate(([0], indices, [length - 1]))
            ).astype(int)
            return indices

        def draw_turn_region(
            axis: plt.Axes,
            t: np.ndarray,
            start_idx: int,
            end_idx: int,
            *,
            alpha: float = 0.15,
            label: Optional[str] = None,
        ) -> None:
            """在時間區間 [start_idx, end_idx] 上畫出轉身區域底色。"""
            if (
                0 <= start_idx < len(t)
                and 0 <= end_idx < len(t)
                and end_idx >= start_idx
            ):
                axis.axvspan(t[start_idx], t[end_idx], alpha=alpha, label=label)

        # 整段 lateral offset / heading
        fps = float(self._estimate_fps())
        smooth_window = max(1, int(round(smooth_window_s * fps)))
        L2, R2, _ = self._compute_hip_points(
            projection=projection, smooth_window=smooth_window
        )
        C2 = (L2 + R2) / 2.0

        lat_raw_all, lat_smooth_all = self._lateral_offset_series(
            C2,
            np.array(det.chair_pos),
            np.array(det.cone_pos),
            k_smooth=k_smooth,
        )
        theta_all = self.compute_pelvis_heading_unwrapped(L2=L2, R2=R2)

        fft_kwargs = dict(fft_params or {})

        for lap_idx, lap in enumerate(laps):
            if num_indices is not None and (lap_idx+1) not in num_indices:
                continue
            
            start_idx = int(lap.idx_start)
            end_idx = int(lap.idx_end)

            def rel(i: int) -> int:
                """轉換為相對於圈起點的索引。"""
                return int(i - start_idx)

            # 這一圈的時間與訊號（相對圈起點）
            t_rel = self.t[start_idx : end_idx + 1]
            lat_rel = lat_smooth_all[start_idx : end_idx + 1]
            lat_raw_rel = lat_raw_all[start_idx : end_idx + 1]
            theta_rel = theta_all[start_idx : end_idx + 1] - theta_all[start_idx]

            n_rel = len(t_rel)

            # 轉身區域（相對索引）
            tc_start_rel = rel(lap.idx_turn_cone_start)
            tc_end_rel = rel(lap.idx_turn_cone_end)
            th_start_rel = rel(lap.idx_turn_chair_start)
            th_end_rel = rel(lap.idx_turn_chair_end)

            # 走路區段：離開椅子 -> 再次進入椅區
            walk_start_rel = rel(lap.idx_leave_chair)
            walk_end_rel = rel(lap.idx_reenter_chair)

            # 夾在合法範圍內
            walk_start_rel = max(0, min(walk_start_rel, n_rel - 1))
            walk_end_rel = max(0, min(walk_end_rel, n_rel - 1))
            if walk_end_rel < walk_start_rel:
                walk_start_rel, walk_end_rel = walk_end_rel, walk_start_rel

            # 只用走路區段做 FFT
            lat_fft = lat_rel[walk_start_rel : walk_end_rel + 1]
            t_fft = t_rel[walk_start_rel : walk_end_rel + 1]

            fft_res = self.compute_lateral_offset_fft(
                lat=lat_fft,
                t=t_fft,
                band=fft_band,
                **fft_kwargs,
            )
            sample_idx = compute_sample_idx(len(t_rel), max_points_plot)

            fig = plt.figure(figsize=(11, 11), constrained_layout=True)
            gridspec = fig.add_gridspec(3, 1, height_ratios=[1, 1, 1])

            # 子圖 A：lateral offset vs time
            ax1 = fig.add_subplot(gridspec[0, 0])
            ax1.plot(t_rel, lat_raw_rel, label="lat_raw")
            ax1.plot(t_rel, lat_rel, label=f"lat_smooth (k={k_smooth})")

            draw_turn_region(
                ax1,
                t_rel,
                tc_start_rel,
                tc_end_rel,
                label="cone turn (existing)",
            )
            draw_turn_region(
                ax1,
                t_rel,
                th_start_rel,
                th_end_rel,
                label="chair turn (existing)",
            )

            if show_samples:
                ax1.plot(
                    t_rel[sample_idx],
                    lat_rel[sample_idx],
                    linestyle="none",
                    marker="o",
                    label=f"samples (≤{max_points_plot or 'all'})",
                )

            ax1.set_title(
                f"{self.prefix or 'session'} - Lap #{lap_idx + 1} — lateral offset"
            )
            ax1.set_xlabel("time (s)")
            ax1.set_ylabel("lat(t)")
            ax1.grid(True, alpha=0.35)
            ax1.margins(x=0.02)
            ax1.legend(fontsize=9)
            self._apply_limits(ax1, ylim=lat_ylim)

            # 子圖 B：FFT / PSD（走路區段，dB）
            ax2 = fig.add_subplot(gridspec[1, 0])
            if fft_res and fft_res.f.size:
                # 轉成 dB：10*log10(PSD)
                Pxx = np.asarray(fft_res.Pxx, dtype=float)
                eps = float(np.finfo(float).tiny)
                Pxx_clipped = np.clip(Pxx, eps, None)
                Pxx_db = 10.0 * np.log10(Pxx_clipped)

                ax2.plot(
                    fft_res.f,
                    Pxx_db,
                    label="PSD of lat(t) — walking segment (dB)",
                )

                # 標註主峰頻率與其 dB 值
                if (
                    np.isfinite(fft_res.f_peak)
                    and fft_res.f_peak > 0
                    and np.isfinite(getattr(fft_res, "p_peak", np.nan))
                    and fft_res.p_peak > 0
                ):
                    p_peak_db = 10.0 * np.log10(max(fft_res.p_peak, eps))

                    # 垂直線 + 樣本點
                    ax2.axvline(
                        fft_res.f_peak,
                        linestyle="--",
                        linewidth=1,
                        label=f"peak ≈ {fft_res.f_peak:.2f} Hz",
                    )
                    if show_samples:
                        ax2.plot(
                            fft_res.f_peak,
                            p_peak_db,
                            linestyle="none",
                            marker="o",
                            label="peak sample",
                        )

                    # 在 peak 點上方標註頻率與 dB
                    xmin, xmax = fft_band
                    xspan = xmax - xmin
                    left_zone = xmin + 0.2 * xspan
                    right_zone = xmax - 0.2 * xspan

                    # 預設：文字在點的右上方
                    dx = 10
                    ha = "left"

                    # 如果 peak 在中間，就置中
                    if left_zone < fft_res.f_peak < right_zone:
                        dx = 0
                        ha = "center"
                    # 如果 peak 很靠右，就把文字放左邊
                    elif fft_res.f_peak >= right_zone:
                        dx = -10
                        ha = "right"

                    ax2.annotate(
                        f"{fft_res.f_peak:.2f} Hz\n{p_peak_db:.1f} dB",
                        xy=(fft_res.f_peak, p_peak_db),
                        xytext=(dx, 10),
                        textcoords="offset points",
                        ha=ha,
                        va="bottom",
                        fontsize=9,
                        bbox=dict(boxstyle="round,pad=0.2", fc="white", alpha=0.8),
                        arrowprops=dict(arrowstyle="->", lw=0.8),
                        clip_on=True,
                    )

                # 自動給一個合理的 y 範圍，避免整條線被裁掉
                if psd_ylim is None:
                    y_min = float(np.nanmin(Pxx_db))
                    y_max = float(np.nanmax(Pxx_db))
                    if np.isfinite(y_min) and np.isfinite(y_max):
                        margin = max(3.0, 0.1 * (y_max - y_min + 1e-6))
                        ax2.set_ylim(y_min - margin, y_max + margin)
                else:
                    self._apply_limits(ax2, ylim=psd_ylim)

            ax2.set_title("FFT / PSD of lateral offset (walking segment, dB)")
            ax2.set_xlabel("frequency (Hz)")
            ax2.set_ylabel("power spectral density (dB)")
            ax2.grid(True, alpha=0.35)
            ax2.set_xlim(fft_band[0], fft_band[1])
            ax2.legend(fontsize=9)

            # 子圖 C：θ(t)
            ax3 = fig.add_subplot(gridspec[2, 0])
            ax3.plot(
                t_rel,
                theta_rel,
                label=r"θ(t) (deg) — per-lap relative",
            )
            if show_samples:
                ax3.plot(
                    t_rel[sample_idx],
                    theta_rel[sample_idx],
                    linestyle="none",
                    marker="o",
                    label=f"θ samples (≤{max_points_plot or 'all'})",
                )

            # 畫出錐區與椅區的轉彎區塊底色
            draw_turn_region(
                ax3,
                t_rel,
                tc_start_rel,
                tc_end_rel,
                label="cone turn (existing)",
            )
            draw_turn_region(
                ax3,
                t_rel,
                th_start_rel,
                th_end_rel,
                label="chair turn (existing)",
            )

            # 以圈起點為 0° 的參考線
            ax3.axhline(0.0, linestyle="--", linewidth=1, label="0° at lap start")

            # 標出「轉彎方向」和「Δθ」資訊
            cone_dir = lap.turn_cone_dir
            chair_dir = lap.turn_chair_dir
            dtheta_cone = lap.delta_theta_cone_deg
            dtheta_chair = lap.delta_theta_chair_deg

            def dir_str(d: int) -> str:
                if d > 0:
                    return "+1 (Direction: θ increasing)"
                if d < 0:
                    return "-1 (Direction: θ decreasing)"
                return "0 (No significant turning)"

            info_lines = [
                f"cone turn: dir={dir_str(cone_dir)}, Δθ≈{dtheta_cone:.1f}°",
                f"chair turn: dir={dir_str(chair_dir)}, Δθ≈{dtheta_chair:.1f}°",
            ]

            ax3.text(
                0.02,
                0.98,
                "\n".join(info_lines),
                transform=ax3.transAxes,
                va="top",
                ha="left",
                fontsize=9,
                bbox=dict(
                    boxstyle="round,pad=0.3",
                    facecolor="white",
                    alpha=0.6,
                ),
            )

            ax3.set_title(
                "θ vs. t (pelvis heading, stable-unwrapped, relative to lap start)"
            )
            ax3.set_xlabel("time (s)")
            ax3.set_ylabel(r"Δθ (deg)")
            ax3.grid(True, alpha=0.35)
            ax3.margins(x=0.02)
            ax3.legend(fontsize=9)

            # 這一圈用自己的 theta_ylim（可能從多個候選中挑出來）
            theta_ylim_this_lap = self._resolve_theta_ylim_for_lap(theta_ylim, theta_rel)
            self._apply_limits(ax3, ylim=theta_ylim_this_lap)

            out_path = Path(self.out_dir) / save_name_template.format(
                lap_idx=lap_idx + 1
            )
            out_path.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(str(out_path), dpi=dpi)
            plt.close(fig)
            save_paths.append(out_path)

        return save_paths

# 高度多系列曲線繪製
class HeightMultiSeriesPlotterMixin(VisualizerUtilsMixin):
    """
    高度多系列曲線：

    - joints: 例如 ["L_HEEL", "R_HEEL"] 或 [29, 30]
    - labels: 每條線的標籤，長度需與 joints 一致

    只畫 Y 軸高度（第 2 維）隨時間變化。
    """
    def save_y_height_diff(
        self,
        left_joint: Union[int, str],
        right_joint: Union[int, str],
        labels: Optional[List[str]] = None,
        *,
        smooth_window_s: float = DEFAULT_SMOOTH_WINDOW_S,
        draw_original: bool = True,
        dpi: int = 150,
        figsize: Tuple[float, float] = (11.0, 4.0),
        save_name: Optional[str] = None,
        ylim: Optional[Tuple[float, float]] = None,
    ) -> Path:
        """
        畫出單一曲線：「左腳高度 - 右腳高度」隨時間變化。

        - 正值：左腳比右腳高
        - 負值：右腳比左腳高
        """
        t, series = self.compute_y_heigh(
            joints=[left_joint, right_joint],
            smooth_window=smooth_window_s,
        )
        if len(series) != 2:
            raise ValueError("save_y_height_diff 需要剛好兩個關節（左、右）。")

        left, right = series
        diff = left - right

        # labels 允許為 None；也允許只給 1 個或含空字串
        if labels is None:
            labels = [str(left_joint), str(right_joint)]
        else:
            labels = list(labels) + [None, None]
            labels = labels[:2]
            labels[0] = labels[0] or str(left_joint)
            labels[1] = labels[1] or str(right_joint)

        # 直接用公分顯示（更直覺），ylim 也請用公分
        scale = 100.0
        left_plot = left * scale
        right_plot = right * scale
        diff_plot = diff * scale

        fig, ax = plt.subplots(figsize=figsize, dpi=dpi, layout="constrained")
        if draw_original:
            ax.plot(t, left_plot, lw=1.4, label=labels[0])
            ax.plot(t, right_plot, lw=1.4, label=labels[1])
        ax.plot(
            t,
            diff_plot,
            lw=1.8,
            label=f"{left_joint}-{right_joint} (L-R)",
        )
        ax.axhline(0.0, color="k", lw=1.0, alpha=0.7)

        # 更細的刻度：10 cm 一大格、1 cm 一小格
        # 但若 y 範圍很大（例如 heel 深度誤當高度、或 outlier 導致平移），
        # 固定 10cm 會讓刻度標籤爆炸而看起來像一條黑線；因此依 range 自動調整。
        if ylim is not None:
            y0, y1 = float(ylim[0]), float(ylim[1])
        else:
            y0 = float(np.nanmin([np.nanmin(left_plot), np.nanmin(right_plot), np.nanmin(diff_plot)]))
            y1 = float(np.nanmax([np.nanmax(left_plot), np.nanmax(right_plot), np.nanmax(diff_plot)]))
        yr = max(1e-6, y1 - y0)

        if yr <= 150.0:
            major_step, minor_step = 10.0, 1.0
        elif yr <= 350.0:
            major_step, minor_step = 20.0, 5.0
        elif yr <= 900.0:
            major_step, minor_step = 50.0, 10.0
        else:
            major_step, minor_step = 100.0, 20.0

        ax.yaxis.set_major_locator(MultipleLocator(major_step))
        ax.yaxis.set_minor_locator(MultipleLocator(minor_step))
        ax.grid(True, which="major", alpha=0.28, linestyle="--")
        ax.grid(True, which="minor", axis="y", alpha=0.14, linestyle=":")
        ax.set_xlabel("time (s)")
        axis_label = self._axis_label_for_data_dim(1)
        ax.set_ylabel(f"{axis_label} height / diff (L-R) [cm]")

        ax.legend(loc="upper right", frameon=False)
        joints_str = f"{left_joint},{right_joint}"
        ax.set_title(
            f"{self.prefix or 'session'} - {axis_label} height & diff (L-R, {joints_str}) [cm]"
        )
        self._apply_limits(ax, ylim=ylim)

        save_name_template = save_name or "y_height_diff_{left}_{right}.png"
        save_name_final = save_name_template.format(
            left=str(left_joint), right=str(right_joint)
        )
        filename = add_prefix_to_filename(save_name_final, self.prefix)
        out_path = Path(self.out_dir) / filename
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(out_path))
        plt.close(fig)

        return out_path


# 對外整合類：統一入口
class RehabSummaryVisualizer(
    StageDurationsPlotterMixin,
    MinutelyStageDurationBarsMixin,
    TrajectoryVideoExporterMixin,
    SpeedHeatmapMixin,
    StepLengthBarsMixin,
    SwingInfoHeatmapMixin,
    LateralOffsetPlotterMixin,
    TimeFrequencyMixin,
    HeightMultiSeriesPlotterMixin,
):
    """
    對外使用的入口類別：

    - 繼承所有 Mixin，可呼叫所有繪圖 / 影片輸出方法
    - 建構子與 VisualizerCore 相同
    """

    def __init__(
        self,
        npy_path: str,
        out_dir: str,
        prefix: Optional[str] = None,
        axis_convention: str = "standard",
    ) -> None:
        super().__init__(npy_path, out_dir, prefix, axis_convention=axis_convention)


if __name__ == "__main__":
    from utils.timing import time_it

    # 範例
    # 1_1_1031, 4_1_1208, 1_1_607, 4_1_1208_30, 1_1_1031_30
    tag = "4_1_1208"
    npy = f"./data/npy/{tag}.npy"
    # npy = f"./outputs/{tag}/{tag}_pose.npy"
    out_dir = "./outputs"

    # X=前後(深度)、Y=左右、Z=上下
    viz = RehabSummaryVisualizer(npy, out_dir=out_dir, axis_convention="anatomical")
    
    # 左腳跟與右腳跟 Y 高度差圖
    time_it(
        viz.save_y_height_diff,
        left_joint=27,
        right_joint=28,
        labels=["Left ankle", "Right ankle"],
        save_name="ankle_diff.png",
        smooth_window_s=3,
        ylim=[-20, 80],
    )
    
    # 左右臀部 Y 高度差圖
    time_it(
        viz.save_y_height_diff,
        left_joint=23,
        right_joint=24,
        labels=["Left hip", "Right hip"],
        smooth_window_s=3,
        save_name="hip_diff.png",
        ylim=[-20, 80],
    )

    # 左右腳後跟 Y 高度差圖
    time_it(
        viz.save_y_height_diff,
        left_joint=29,
        right_joint=30,
        smooth_window_s=3,
        labels=["Left heel", "Right heel"],
        save_name="heel_diff.png",
        # ylim=[-20, 80],
    )
    
    # X(Z) 或 Y(Z) 的空間頻譜（只改圖上標示，不改計算）
    time_it(
        viz.save_spatial_spectrum, 
        spec_ylim=[[-80, 20], [-80, 20]],
        top_k=5,
    )
    
    # 多系列 FFT
    time_it(
        viz.save_multi_fft_from_series,
        joints=[[27, 28]],
        min_peak_distance_ratio=0.01,
        min_db=-40.0,
        min_freq=0.05,
        ylim=[-80, 10],
        # labels=["(L+R ankle)/2", "Left ankle", "Right ankle"],
        labels=["(L+R ankle)/2"],
        max_peaks=3,
    )

    # 三圖左右偏移診斷圖 (速度較慢)
    time_it(
        viz.save_per_lap_offset, 
        lat_ylim=[-1.0, 1.0], 
        psd_ylim=[-70, 20], 
        theta_ylim=[[-450, 100], [-100, 450]],
        max_points_plot=None,
        # num_indices=[1, 2, 3, 25],
    )

    # 每分鐘每圈左右步頻/步長圖
    time_it(
        viz.save_minutely_cadence_step_length_bars,
        spm_ylim=[30, 140],
        steplen_ylim=[0.0, 1.6],
    )

    # 每分鐘每圈左右步態時間圖
    time_it(
        viz.save_minutely_stance_swing_bars,
        stance_ylim=[0.2, 1.0],
        swing_ylim=[0.2, 1.0],
    )

    # 每圈左右擺動趨勢圖（百分比/秒數）
    time_it(
        viz.save_swing_info_heatmap,
        vmin_pct=30,
        vmax_pct=45,
    )

    # 每圈三段(去程/迴轉/回程)每分鐘耗時圖
    time_it(
        viz.save_minutely_stage_duration_bars,
    )

    # 速度熱圖
    time_it(
        viz.save_spatiotemporal_speed_heatmap,
        vmin=0.0,
        vmax=2.5,
    )

    # 每圈各階段耗時圖 (六段)
    time_it(
        viz.save_stage_durations_image,
    )

    # 軌跡影片使用左右臀部當髖點 (速度較慢)
    time_it(
        viz.save_trajectory_video,
        left_joint=23,
        right_joint=24,
    )
    
    # 軌跡影片使用左右腳踝當髖點 (速度較慢)
    time_it(
        viz.save_trajectory_video,
        left_joint=27,
        right_joint=28,
    )