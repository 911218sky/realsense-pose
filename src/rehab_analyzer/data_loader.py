"""姿態 npy 檔案載入器，提供 rehab_analyzer 模組的基礎資料存取。"""

from pathlib import Path

import numpy as np
from cachetools import TTLCache


class DataLoader:
    """載入姿態 npy 檔並建立共用屬性的基底類別。
    
    這是整個分析流程的起點，負責把 npy 檔讀進來，
    並把時間戳記、關節索引等常用資訊準備好。
    """

    # MediaPipe Pose 的關節索引（33 個關節點）
    L_HIP = 23
    R_HIP = 24
    L_HEEL = 29
    R_HEEL = 30

    def __init__(self, npy_path: str):
        # 快取分析結果，避免重複計算（最多 200 筆，30 秒後過期）
        self.cache: TTLCache = TTLCache(maxsize=200, ttl=30)

        self.npy_path: Path = Path(npy_path)

        # 姿態資料：shape = (幀數, 關節數, 3)，最後一維是 xyz 座標
        self.arr: np.ndarray = np.load(self.npy_path)

        # 時間戳記放在第 34 個 slot 的 z 欄位
        self.t: np.ndarray = (
            self.arr[:, 33, 2].astype(float) if self.arr.shape[1] >= 34 else None
        )
        assert self.t is not None, "npy 缺少時間戳記"

    def __repr__(self) -> str:
        return f"<DataLoader npy={self.npy_path!s} n_frames={self.arr.shape[0]}>"


