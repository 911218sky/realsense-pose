"""Base loader for pose `.npy` files used by rehab analyzer."""

from pathlib import Path
from typing import Optional

import numpy as np
from cachetools import TTLCache

class DataLoader:
    """負責載入 npy 檔與建立共用屬性的基底類別。"""

    # 關節索引常數（方便之後呼叫）
    L_HIP = 23
    R_HIP = 24
    L_HEEL = 29
    R_HEEL = 30

    def __init__(self, npy_path: str):
        # 快取最多 200 筆結果，存活 30 秒
        self.cache = TTLCache(maxsize=200, ttl=30)

        self.npy_path = Path(npy_path)

        # 主姿勢資料：shape (N, J, 3)
        self.arr: np.ndarray = np.load(self.npy_path)

        # 時間戳記：假設 arr[:, 33, 2] 是時間（秒）
        self.t: Optional[np.ndarray] = (
            self.arr[:, 33, 2].astype(float) if self.arr.shape[1] >= 34 else None
        )
        assert self.t is not None, "t 為 None，npy 中沒有時間維度"

    def __repr__(self) -> str:
        return f"<DataLoader npy={self.npy_path!s} n_frames={self.arr.shape[0]}>"


# 姿勢 / 訊號前處理

