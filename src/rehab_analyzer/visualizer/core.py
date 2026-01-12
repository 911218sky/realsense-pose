"""
可視化核心基礎類別。

提供共用的輸出目錄、前綴名稱和軸顯示設定。
"""
from pathlib import Path
from typing import Dict

from matplotlib.axes import Axes

from ..entities import XYZPair
from ..rehab_analyzer import RehabilitationSessionAnalyzer

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
        prefix: str | None = None,
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
            raise ValueError(
                f"未知的 axis_convention='{axis_convention}'，可用：{list(AXIS_DISPLAY_NAMES)}"
            )
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

    def _axis_labels_for_pair(self, pair: str) -> tuple[str, str]:
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
        ax: Axes,
        *,
        xlim: tuple[float, float | None] | None = None,
        ylim: tuple[float, float | None] | None = None,
    ) -> None:
        """
        設定圖形座標軸範圍。
        傳入 None 時保持原本 Matplotlib 自動範圍。
        """
        if xlim is not None:
            ax.set_xlim(*xlim)
        if ylim is not None:
            ax.set_ylim(*ylim)
