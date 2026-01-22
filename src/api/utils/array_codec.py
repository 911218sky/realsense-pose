from __future__ import annotations

import base64
import zlib
from typing import Final, Literal, TypedDict

import numpy as np


F32_ZLIB_B64_ENCODING: Final[str] = "f32_le_zlib_b64"
U16_ZLIB_B64_ENCODING: Final[str] = "u16_le_zlib_b64"


class FloatArrayF32ZlibB64Payload(TypedDict):
    """
    對應 `api.v1.rehab_analyzer.models.FloatArrayF32ZlibB64` 的資料結構。

    - `f32_zlib_b64`: zlib(compress(float32 little-endian bytes)) 再 base64
    - `endian`: 固定 little
    - `n`: float32 元素個數
    """

    f32_zlib_b64: str
    endian: Literal["little"]
    n: int

def pack_1d_f32_zlib_b64(arr: np.ndarray) -> FloatArrayF32ZlibB64Payload:
    """
    將一維 float array 壓縮成 float32(little-endian) + zlib + base64。

    用途：回傳超長序列（freq_hz / psd_db）時減少 JSON payload。
    """
    a = np.asarray(arr, dtype=np.float32).reshape(-1)
    raw = a.astype("<f4", copy=False).tobytes(order="C")
    compressed = zlib.compress(raw)
    b64 = base64.b64encode(compressed).decode("ascii")
    return {"f32_zlib_b64": b64, "endian": "little", "n": int(a.size)}

def pack_1d_u16_le_zlib_b64(arr: np.ndarray) -> str:
    """
    將 uint16 array 以 little-endian 轉 bytes 後 zlib 壓縮並 base64 編碼。

    用途：像 `trajectory_payload` 的 frames（u16）可直接共用此工具，避免各 endpoint 重複寫壓縮碼。
    """
    a = np.asarray(arr, dtype=np.uint16)
    raw = a.astype("<u2", copy=False).tobytes(order="C")
    compressed = zlib.compress(raw)
    return base64.b64encode(compressed).decode("ascii")