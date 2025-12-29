"""Frequency / spatial spectrum analysis helpers."""

import math
from functools import partial
from operator import attrgetter
from typing import Literal, Optional, Tuple, Union

import numpy as np
from cachetools import cachedmethod
from scipy.signal import periodogram

from .entities import OffsetFFTResult

from .cache_keys import method_key
from .lap_detector import LapDetector

class FftAnalyzer(LapDetector):
    """與頻率 / 空間頻譜相關的方法。"""

    def compute_lateral_offset_fft(
        self,
        lat: np.ndarray,
        t: np.ndarray,
        *,
        band: Optional[Tuple[float, float]] = None,
        window: str = "hann",
        detrend: Literal["none", "constant", "linear"] = "none",
        scaling: Literal["spectrum", "density"] = "spectrum",
        min_nfft: int = 512,
        pad_to_pow2: bool = True,
        zero_pad_factor: float = 1.0,
        remove_dc: bool = False,
    ) -> OffsetFFTResult:
        """對 lateral offset 計算單邊頻譜並找主峰，可自訂 FFT 參數。"""
        lat = np.asarray(lat, float)
        t = np.asarray(t, float)

        if lat.size < 4:
            return OffsetFFTResult(
                f=np.array([]),
                Pxx=np.array([]),
                f_peak=np.nan,
                p_peak=np.nan,
            )

        t0, t1 = float(t[0]), float(t[-1])
        if lat.size >= 3:
            dt_est = float(np.median(np.diff(t)))
        else:
            dt_est = (t1 - t0) / max(lat.size - 1, 1)
        fs = 1.0 / max(dt_est, 1e-6)

        if remove_dc:
            finite = np.isfinite(lat)
            if np.any(finite):
                lat = lat.copy()
                lat[finite] = lat[finite] - float(np.mean(lat[finite]))

        n = len(lat)
        target_nfft = max(int(min_nfft), n)
        zero_pad_factor = max(float(zero_pad_factor), 1.0)
        target_nfft = max(target_nfft, int(math.ceil(n * zero_pad_factor)))
        if pad_to_pow2:
            target_nfft = int(2 ** math.ceil(math.log2(max(target_nfft, 1))))
        nfft = target_nfft

        detrend_option: Union[str, bool]
        if detrend == "none":
            detrend_option = False
        else:
            detrend_option = detrend

        f, Pxx = periodogram(
            x=lat,
            fs=fs,
            window=window,
            nfft=nfft,
            detrend=detrend_option,
            return_onesided=True,
            scaling=scaling,
        )

        if band is not None:
            lo, hi = band
            m = (f >= lo) & (f <= hi)
            f_band = f[m]
            Pxx_band = Pxx[m]
        else:
            f_band, Pxx_band = f, Pxx

        if f_band.size:
            i_peak = int(np.nanargmax(Pxx_band))
            f_peak = float(f_band[i_peak])
            p_peak = float(Pxx_band[i_peak])
        else:
            f_peak = np.nan
            p_peak = np.nan

        return OffsetFFTResult(
            f=f_band,
            Pxx=Pxx_band,
            f_peak=f_peak,
            p_peak=p_peak,
        )

    @cachedmethod(attrgetter("cache"), key=partial(method_key, "compute_spatial_spectrum_zind"))
    def compute_spatial_spectrum_zind(
        self,
        pair: Literal["xz", "yz"] = "xz",
        *,
        k_smooth: int = 2,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """以 Z 為自變量，計算 X(Z) 或 Y(Z) 的空間頻譜。"""
        p = (pair or "xz").lower()
        if p not in ("xz", "yz"):
            raise ValueError("pair 只能是 'xz' 或 'yz'。")

        xyz = self.arr[:, :33, :]
        L = xyz[:, self.L_HIP, :]
        R = xyz[:, self.R_HIP, :]
        C = (L + R) / 2.0

        X = C[:, 0].astype(float)
        Y = C[:, 1].astype(float)
        Z = C[:, 2].astype(float)

        dep = X if p == "xz" else Y
        indep = Z

        order = np.argsort(indep)
        z_sorted = indep[order]
        s_sorted = dep[order]

        z_unique, keep_idx = np.unique(z_sorted, return_index=True)
        s_unique = s_sorted[keep_idx]

        n0 = int(z_unique.size)
        if n0 < 16:
            raise ValueError("以 Z 重採樣後有效點太少，無法計算 FFT。")

        z_min, z_max = float(z_unique[0]), float(z_unique[-1])
        span = z_max - z_min
        if span <= 0:
            raise ValueError("Z 範圍太小或不遞增，無法計算 FFT。")

        z_grid = np.linspace(z_min, z_max, n0, dtype=float)
        s_grid = np.interp(z_grid, z_unique, s_unique)

        if k_smooth and k_smooth > 1:
            s_grid = self._moving_average(s_grid, k=int(k_smooth))

        s_grid = s_grid - float(np.median(s_grid))
        dz = span / (n0 - 1)
        fs_spatial = 1.0 / dz

        f, psd = periodogram(
            s_grid,
            fs=fs_spatial,
            window="hann",
            return_onesided=True,
            detrend="constant",
            scaling="spectrum",
        )

        return f, psd

# 對外使用的 facade

