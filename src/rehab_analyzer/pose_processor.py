"""姿態/訊號前處理工具。"""

from functools import partial
from operator import attrgetter
from typing import Optional, Sequence, Tuple, Union, Literal

import numpy as np
from cachetools import cachedmethod
from scipy.signal import savgol_filter
from scipy.ndimage import uniform_filter1d

from .cache_keys import method_key
from .data_loader import DataLoader

class PoseProcessor(DataLoader):
    """提供投影、平滑、微分等基礎處理工具。"""

    def _moving_average(self, data: np.ndarray, k: int) -> np.ndarray:
        """對 1D 或 2D 陣列做移動平均並簡單補洞。

        若輸入為 1D（形狀為 (N,)），會自動視為單一欄位的 (N,1) 來處理，
        回傳時再還原成 1D；2D (N, D) 則維持原有行為。

        規則：
        * 把 0 視為缺值
        * 缺值用線性內插補齊（含首尾，首尾用最近有效值延伸）
        * 最後用移動平均平滑（使用 `scipy.ndimage.uniform_filter1d`，速度較快）
        """
        if k is None or int(k) <= 1:
            return data

        arr = np.asarray(data, dtype=float)
        was_1d = arr.ndim == 1

        if was_1d:
            d = arr.reshape(-1, 1)
        elif arr.ndim == 2:
            d = arr.copy()
        else:
            raise ValueError(f"_moving_average 僅支援 1D 或 2D 陣列，取得 ndim={arr.ndim}")

        n = d.shape[0]
        x = np.arange(n)

        # 逐欄處理缺值與內插
        for j in range(d.shape[1]):
            col = d[:, j]
            invalid = (col == 0) | (~np.isfinite(col))
            valid_idx = np.where(~invalid)[0]

            # 整欄都沒有有效值就跳過
            if valid_idx.size == 0:
                continue
            if valid_idx.size == n:
                filled = col
            else:
                fp = col[valid_idx]
                # np.interp 會在首尾用 left/right 延伸最近的有效值
                filled = np.interp(x, valid_idx, fp, left=fp[0], right=fp[-1])

            d[:, j] = uniform_filter1d(filled, size=int(k), mode="nearest")

        smoothed = d

        if was_1d:
            return smoothed[:, 0]
        return smoothed

    @staticmethod
    def auto_spike_squash_1d(
        y: np.ndarray,
        *,
        window: int = 11,
        z_thresh: float = 4.0,
    ) -> np.ndarray:
        """
        自動偵測並壓平明顯「尖峰」的 1D 序列。

        做法：
        - 先用 Savitzky–Golay（平滑多項式）估計平滑曲線 y_smooth
        - 看殘差 r = y - y_smooth 的 robust z-score
        - |z| 過大（預設 > z_thresh）就視為尖峰，改用 y_smooth 的值取代
        """
        y = y.astype(float)
        n = y.size
        if n < 5:
            return y

        # window 需為奇數且不大於資料長度
        w = int(window)
        if w % 2 == 0:
            w += 1
        if w > n:
            w = n if n % 2 == 1 else n - 1
        if w < 5:
            return y

        y_smooth = savgol_filter(y, window_length=w, polyorder=2, mode="interp")
        resid = y - y_smooth

        # robust scale：使用 MAD 避免被尖峰影響
        valid = np.isfinite(resid)
        if not np.any(valid):
            return y
        r = resid[valid]
        med = np.median(r)
        mad = np.median(np.abs(r - med))
        if not np.isfinite(mad) or mad <= 1e-6:
            return y

        z = (resid - med) / (1.4826 * mad)  # 1.4826 ~ 把 MAD 轉成類似標準差
        mask = np.abs(z) > float(z_thresh)
        if not np.any(mask):
            return y

        y_out = y.copy()
        y_out[mask] = y_smooth[mask]
        return y_out

    @cachedmethod(attrgetter("cache"), key=partial(method_key, "_estimate_fps"))
    def _estimate_fps(self) -> int:
        """根據時間戳估計 fps，並忽略異常 dt。"""
        dt = np.diff(self.t)
        dt = dt[dt > 0]
        if dt.size == 0:
            return 30
        fps = round(np.clip(1.0 / np.median(dt), 1.0, 120.0))
        return int(fps)

    @cachedmethod(attrgetter("cache"), key=partial(method_key, "_infer_input_y_axis"))
    def _infer_input_y_axis(self) -> Literal["up", "down"]:
        """
        推估輸入 npy 的 y 軸方向（up/down）。

        背景：
        - RealSense deproject 常見為 y 向下為正（down）
        - 本專案 PoseProcessor 可選擇輸出 y_axis_up=True（向上為正，up）

        這裡用「髖部 y 的中位數符號」做簡單推估：
        - 多數情境下受試者在相機下方；若 y 中位數 > 0，通常表示 down；
          若 y 中位數 < 0，通常表示 up。
        """
        cand = []
        for idx in (self.L_HIP, self.R_HIP):
            if idx >= self.arr.shape[1]:
                continue
            valid = np.any(self.arr[:, idx, :] != 0.0, axis=1)
            if not np.any(valid):
                continue
            y = self.arr[valid, idx, 1].astype(float)
            y = y[np.isfinite(y) & (y != 0.0)]
            if y.size:
                cand.append(y)

        if not cand:
            # 沒資料時，偏向新版本預設（y_axis_up=True）
            return "up"

        y_all = np.concatenate(cand, axis=0)
        med = float(np.nanmedian(y_all)) if y_all.size else 0.0
        return "down" if med > 0 else "up"

    def _savgol_residual(
        self,
        x: np.ndarray,
        win: int = 41,
        poly: int = 5,
        auto_fix: bool = True,
    ) -> np.ndarray:
        """對序列做 Savitzky–Golay 去趨勢並回傳殘差。

        - 會自動調整窗長為合理的奇數，避免超出序列長度
        - 適合用來保留高頻成分（例如步態事件）
        """
        x = np.asarray(x, dtype=float)
        n = x.size
        if n < 7:
            return x - np.nanmean(x)

        if auto_fix:
            w = win if win % 2 == 1 else win + 1
            if (n - 1) % 2:
                max_w = n - 2
            else:
                max_w = n - 1
            w = max(7, min(w, max_w))
            p = min(poly, 5)
        else:
            w = win
            p = poly

        trend = savgol_filter(x, window_length=w, polyorder=p, mode="interp")
        return x - trend

    @cachedmethod(attrgetter("cache"), key=partial(method_key, "resolve_joint"))
    def resolve_joint(self, sel: Union[int, str]) -> int:
        """解析關節索引。

        sel 可以是：
        - int：直接視為索引
        - str：若是類別屬性名（例如 "L_HIP"），則取其數值；
               否則嘗試轉成 int。
        """
        if isinstance(sel, int):
            return int(sel)

        if isinstance(sel, str):
            if hasattr(self, sel):
                return int(getattr(self, sel))
            try:
                return int(sel)
            except (ValueError, TypeError):
                raise ValueError(
                    f"未知的關節選擇 '{sel}'（不是整數，也不是類別常數名）"
                )

        raise TypeError("joint 必須為 int 或 str")

    @cachedmethod(attrgetter("cache"), key=partial(method_key, "_compute_hip_points"))
    def _compute_hip_points(
        self,
        projection: str = "xz",
        smooth_window: int = 3,
        left_joint: Union[int, str] = "L_HIP",
        right_joint: Union[int, str] = "R_HIP",
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """取得左右髖在 2D 投影平面的座標並平滑。

        回傳：
        - L2, R2: (N, 2) 的 2D 軌跡
        - valid : (N,) bool，表示該幀兩側髖是否都有有效值
        """
        li = self.resolve_joint(left_joint)
        ri = self.resolve_joint(right_joint)

        xyz = self.arr[:, :33, :]
        Lh = xyz[:, li, :]
        Rh = xyz[:, ri, :]

        valid_L = np.any(Lh != 0.0, axis=1)
        valid_R = np.any(Rh != 0.0, axis=1)
        valid = valid_L & valid_R

        proj = projection.lower()
        if proj == "xz":
            L2 = Lh[:, [0, 2]]
            R2 = Rh[:, [0, 2]]
        elif proj == "xy":
            L2 = Lh[:, [0, 1]]
            R2 = Rh[:, [0, 1]]
        else:
            raise ValueError("projection 僅支援 'xz' 或 'xy'")

        L2[~valid] = 0.0
        R2[~valid] = 0.0

        L2 = self._moving_average(L2, smooth_window)
        R2 = self._moving_average(R2, smooth_window)
        return L2, R2, valid

    @cachedmethod(attrgetter("cache"), key=partial(method_key, "_hip_separation_series"))
    def _hip_separation_series(
        self,
        projection: str = "xy",
        smooth_window: int = 5,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """計算左右髖在投影平面上的距離序列 d(t)。"""
        xyz = self.arr[:, :33, :]
        Lh = xyz[:, self.L_HIP, :]
        Rh = xyz[:, self.R_HIP, :]

        valid_L = np.any(Lh != 0.0, axis=1)
        valid_R = np.any(Rh != 0.0, axis=1)
        valid = valid_L & valid_R

        proj = projection.lower()
        if proj == "xy":
            L2 = Lh[:, [0, 1]]
            R2 = Rh[:, [0, 1]]
        elif proj == "xz":
            L2 = Lh[:, [0, 2]]
            R2 = Rh[:, [0, 2]]
        else:
            raise ValueError("projection 僅支援 'xy' 或 'xz'")

        L2[~valid] = 0.0
        R2[~valid] = 0.0

        L2 = self._moving_average(L2, smooth_window)
        R2 = self._moving_average(R2, smooth_window)

        d = np.linalg.norm(L2 - R2, axis=1)
        return d, valid

    def _compute_yprime(self, y: np.ndarray) -> np.ndarray:
        """計算 y 的近似時間導數 y' = Δy / Δt（長度與 y 相同）。"""
        dt = np.diff(self.t, prepend=self.t[0])

        pos = np.isfinite(dt) & (dt > 0)
        median_dt = np.median(dt[pos]) if np.any(pos) else 1.0
        dt[~np.isfinite(dt) | (dt <= 0)] = median_dt

        dy = np.diff(y, prepend=y[0])
        return dy / dt

    def compute_y_heigh(
        self,
        joints: Sequence[Union[int, str]],
        *,
        smooth_window: int = 3,
        shift_to_zero: bool = True,
    ) -> tuple[np.ndarray, list[np.ndarray]]:
        """
        取得指定關節在 y 軸的高度序列，並自動偵測/壓平明顯的尖峰異常值。

        參數
        - joints: 關節 index 或名稱
        - smooth_window:（目前保留，不在此函式內做平滑）
        - shift_to_zero:（目前保留，不在此函式內平移）
        - outlier_low_pct / outlier_high_pct:
            目前在此函式中已不再使用，僅為相容舊呼叫保留。
        """
        joints = [self.resolve_joint(j) for j in joints]

        def series_y(joint: int) -> np.ndarray:
            y = self.arr[:, joint, 1].astype(float)
            
            # 平滑
            y = self._moving_average(y, smooth_window)
                
            # 自動尖峰偵測 + 壓平，不再依賴手動設定百分位
            y = self.auto_spike_squash_1d(y)
            return y

        series = [series_y(i) for i in joints]
        
        # 平移到 0 基準
        if shift_to_zero:
            series = np.array(series)
            series -= np.min(series)
        
        return self.t, series

    @cachedmethod(
        attrgetter("cache"),
        key=partial(method_key, "compute_pelvis_heading_unwrapped"),
    )
    def compute_pelvis_heading_unwrapped(
        self,
        L2: Optional[np.ndarray] = None,
        R2: Optional[np.ndarray] = None,
        *,
        max_deg_per_s: float = 180.0,
        min_vec_norm: Optional[float] = None,
        max_vec_norm: Optional[float] = None,
    ) -> np.ndarray:
        """
        由投影在 2D（XZ 或 XY）的左右髖點序列，計算穩定解包後的骨盆朝向角 θ（度）。
        回傳：theta_unwrap_all（連續角，度）
        參數
        hysteresis_deg : float
            穩定解包的遲滯帶寬。
        max_deg_per_s : floatx
            最大允許的角速度，度/秒。
        min_vec_norm : Optional[float]
            若提供，當 |R-L| 小於此值時沿用上一幀角度（避免噪聲導致亂跳）。
        """
        if L2 is None or R2 is None:
            L2, R2, _ = self._compute_hip_points(projection="xz")
        else:
            assert L2.shape == R2.shape and L2.shape[1] == 2, "L2/R2 需為 (N,2)"
        
        def wrap_to_180(deg: np.ndarray) -> np.ndarray:
            """包到 [-180, 180)（度）。"""
            return (deg + 180.0) % 360.0 - 180.0
        
        def unwrap_rate_limited(
            theta_wrapped_deg: np.ndarray,
            *,
            valid_mask: Optional[np.ndarray] = None,
        ) -> np.ndarray:
            """
            使用相鄰有效幀的 wrapped 差值做 unwrap，避免累積誤差導致的分支判斷錯誤。
            """
            x = theta_wrapped_deg
            out = np.empty_like(x)
            out[0] = x[0]

            for i in range(1, len(x)):
                # 跳過無效幀或無窮大值
                prev = out[i-1]
                if not valid_mask[i]:
                    out[i] = prev
                    continue

                # 相對上一幀
                d = wrap_to_180(x[i] - prev)
                cand = prev + d

                # 角速度上限
                dt = max(1e-6, float(t[i] - t[i-1]))
                step_limit = abs(max_deg_per_s) * dt
                step = cand - prev

                if step > step_limit:
                    cand = prev + step_limit
                if step < -step_limit:
                    cand = prev - step_limit
                    
                out[i] = cand
                
            return out

        t = self.t
        dx = (R2[:, 0] - L2[:, 0]).astype(float)
        dz = (R2[:, 1] - L2[:, 1]).astype(float)
        # 包到 [-180, 180)
        theta_wrapped = wrap_to_180(np.degrees(np.arctan2(dz, dx)))

        # 向量幅值門檻
        vnorm = np.hypot(dx, dz)
        valid = np.isfinite(theta_wrapped)
        if max_vec_norm is not None:
            valid &= (vnorm <= float(max_vec_norm))
        if min_vec_norm is not None:
            valid &= (vnorm >= float(min_vec_norm))

        theta_unwrap = unwrap_rate_limited(
            theta_wrapped,
            valid_mask=valid,
        )
        return theta_unwrap

# 圈數偵測與路徑 / 速度序列

