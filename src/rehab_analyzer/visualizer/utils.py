"""
可視化共用工具函數和 Mixin 類別。

包含影像讀取、格式轉換、圖形處理等工具。
"""
from typing import TYPE_CHECKING, Any

import numpy as np

from .core import VisualizerCore

if TYPE_CHECKING:
    from matplotlib.figure import Figure


def fmt_timestamp(t: float) -> str:
    """秒數格式化為 mm:ss.ss 文字。"""
    minutes = int(t // 60)
    seconds = t % 60.0
    return f"{minutes}:{seconds:05.2f}"


def imread_rgb(path: str) -> np.ndarray[Any, Any]:
    """使用 PIL 讀取影像並轉成 RGB uint8 numpy 陣列。"""
    from PIL import Image

    img = Image.open(path).convert("RGB")
    return np.asarray(img, dtype=np.uint8)


def canvas_to_numpy_rgba(fig: "Figure") -> np.ndarray[Any, Any]:
    """
    將 Matplotlib Figure 轉成 RGBA uint8 numpy 陣列 (H, W, 4)。

    會優先使用 tostring_argb，如沒有則退而求其次使用 tostring_rgb。
    """
    fig.canvas.draw()

    # 優先使用 ARGB
    if hasattr(fig.canvas, "tostring_argb"):
        width, height = fig.canvas.get_width_height()
        argb = np.frombuffer(fig.canvas.tostring_argb(), dtype=np.uint8).reshape(
            height, width, 4
        )
        rgba = argb[:, :, [1, 2, 3, 0]]  # ARGB -> RGBA
        return rgba

    # 次選使用 RGB，再補一個 alpha 通道
    if hasattr(fig.canvas, "tostring_rgb"):
        width, height = fig.canvas.get_width_height()
        rgb = np.frombuffer(fig.canvas.tostring_rgb(), dtype=np.uint8).reshape(
            height, width, 3
        )
        alpha = np.full((height, width, 1), 255, dtype=np.uint8)
        rgba = np.concatenate([rgb, alpha], axis=2)
        return rgba

    raise RuntimeError("無法擷取 Matplotlib 畫布內容。")


class VisualizerUtilsMixin(VisualizerCore):
    """
    共用工具類別：

    - 時間字串格式
    - 影像讀取、補白/裁切
    - Matplotlib Figure 轉 numpy 陣列
    """

    def _fmt_ts(self, t: float) -> str:
        """秒數格式化為 mm:ss.ss 文字。"""
        return fmt_timestamp(t)

    def _imread_rgb(self, path: str) -> np.ndarray[Any, Any]:
        """使用 PIL 讀取影像並轉成 RGB uint8 numpy 陣列。"""
        return imread_rgb(path)

    def _pad_or_crop_even(self, img: np.ndarray[Any, Any], H: int, W: int) -> np.ndarray[Any, Any]:
        """
        將影像補白或裁切到指定大小 (H, W)。

        通常搭配 ffmpeg 使用：
        - 一些編碼格式要求影格尺寸需為偶數。
        """
        import cv2

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

        # 過大時裁切
        if h > H or w > W:
            img = img[:H, :W]

        return img

    def _canvas_to_numpy_rgba(self, fig: "Figure") -> np.ndarray[Any, Any]:
        """將 Matplotlib Figure 轉成 RGBA uint8 numpy 陣列 (H, W, 4)。"""
        return canvas_to_numpy_rgba(fig)
