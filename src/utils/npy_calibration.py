"""
Pose npy 校正模組：修正因距離變化造成的尺度漂移與相機俯仰偏差。

支援兩種校正：
- scale：用骨頭長度估算每幀尺度，縮放回固定參考值
- pitch：用腳部接地點估算地面斜率，旋轉修正 y/z

注意：index 33 的時間戳列 [0,0,t] 不會被修改，無效點 (0,0,0) 也會保持原樣。
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional, Sequence, Tuple

import numpy as np
from scipy.ndimage import uniform_filter1d

__all__ = [
    "CalibrationConfig",
    "PoseNpyCalibrator",
    "DEFAULT_BONES",
    "DEFAULT_GROUND_JOINTS",
]

# 用來估算每幀尺度的骨頭清單（選相對穩定、不易因動作變形的長度）
DEFAULT_BONES: Tuple[Tuple[int, int], ...] = (
    (23, 24),  # 左右髖距
    (11, 12),  # 左右肩距
    (11, 23),  # 軀幹左側
    (12, 24),  # 軀幹右側
    (23, 25),  # 左髖到左膝
    (24, 26),  # 右髖到右膝
    (25, 27),  # 左膝到左踝
    (26, 28),  # 右膝到右踝
)

# 用來推估地面與相機 pitch 的腳部關節
DEFAULT_GROUND_JOINTS: Tuple[int, ...] = (27, 28, 29, 30, 31, 32)


@dataclass(frozen=True)
class CalibrationConfig:
    """Pose npy 校正設定。"""

    mode: Literal["auto", "scale", "pitch", "scale+pitch"] = "auto"

    # scale 校正參數
    bones: Tuple[Tuple[int, int], ...] = DEFAULT_BONES
    scale_clip: Tuple[float, float] = (0.5, 2.0)
    smooth_scale_s: float = 0.75

    # pitch 校正參數
    ground_joints: Tuple[int, ...] = DEFAULT_GROUND_JOINTS
    ground_quantile: float = 0.90
    min_ground_points: int = 200
    auto_pitch_min_deg: float = 2.0


class PoseNpyCalibrator:
    """Pose npy 校正器，支援 scale 與 pitch 兩種校正。"""

    def __init__(self, cfg: CalibrationConfig = CalibrationConfig()):
        self.cfg = cfg

    def calibrate_array(self, arr: np.ndarray) -> np.ndarray:
        """校正 pose array，只處理前 33 個關節，保留 index 33 的時間戳列。"""
        cfg = self.cfg
        arr = np.asarray(arr)

        if arr.ndim != 3 or arr.shape[-1] != 3:
            raise ValueError(f"Expected arr shape (N,J,3); got {arr.shape}")

        _n, j, _ = arr.shape
        pose_j = min(33, j)
        has_timestamp_row = j >= 34

        out = arr.copy()
        pose = out[:, :pose_j, :].astype(float, copy=False)
        valid = self._valid_mask(pose)
        mode = cfg.mode

        # Scale 校正
        if mode in ("auto", "scale", "scale+pitch"):
            s = self._compute_frame_scales(pose, valid, cfg.bones)
            ref = float(np.nanmedian(s)) if np.any(np.isfinite(s)) else 1.0
            if not np.isfinite(ref) or ref <= 1e-6:
                ref = 1.0

            f = ref / s
            f[~np.isfinite(f)] = np.nan
            f = np.clip(f, *cfg.scale_clip)
            f = self._fill_forward(f, 1.0)

            if cfg.smooth_scale_s > 0 and has_timestamp_row:
                t = arr[:, 33, 2].astype(float)
                fps = self._estimate_fps_from_t(t)
                if fps is not None:
                    k = int(round(cfg.smooth_scale_s * fps))
                    if k > 1:
                        f = self._moving_average(f, k=k)

            anchor = self._compute_anchor(pose, valid)
            scaled = (pose - anchor[:, None, :]) * f[:, None, None] + anchor[:, None, :]
            pose = np.where(valid[:, :, None], scaled, pose)
            out[:, :pose_j, :] = pose.astype(out.dtype, copy=False)

        # Pitch 校正
        if mode in ("auto", "pitch", "scale+pitch"):
            pose = out[:, :pose_j, :].astype(float, copy=False)
            valid = self._valid_mask(pose)

            theta = self._estimate_pitch_angle_rad_from_ground(
                pose, valid, cfg.ground_joints,
                quantile=cfg.ground_quantile,
                min_points=cfg.min_ground_points,
            )

            if theta is not None and mode == "auto":
                if abs(theta) < np.deg2rad(cfg.auto_pitch_min_deg):
                    theta = None

            if theta is not None:
                c, s_ = np.cos(theta), np.sin(theta)
                y, z = pose[:, :, 1], pose[:, :, 2]
                y_rot = y * c - z * s_
                z_rot = y * s_ + z * c

                pose2 = pose.copy()
                pose2[:, :, 1] = np.where(valid, y_rot, y)
                pose2[:, :, 2] = np.where(valid, z_rot, z)
                out[:, :pose_j, :] = pose2.astype(out.dtype, copy=False)

        return out

    def calibrate_npy(
        self,
        *,
        npy_path: Optional[str | Path] = None,
        arr: Optional[np.ndarray] = None,
        out_path: Optional[str | Path] = None,
    ) -> Path:
        """讀取 pose npy、校正、存檔。若 out_path 為 None，會加上 `_calib.npy` 尾碼。"""
        if npy_path is not None:
            in_path = Path(npy_path)
            arr = np.load(in_path)

        if arr is None:
            raise ValueError("npy_path or arr is required")

        out_arr = self.calibrate_array(arr)

        if out_path is None:
            out_path = in_path.with_name(f"{in_path.stem}_calib.npy")

        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        np.save(out_path, out_arr)
        return out_path

    def _estimate_fps_from_t(self, t: np.ndarray) -> Optional[float]:
        """從時間戳序列估計 FPS。"""
        if t is None:
            return None
        t = np.asarray(t, dtype=float).ravel()
        if t.size < 3:
            return None
        dt = np.diff(t)
        dt = dt[np.isfinite(dt) & (dt > 0)]
        if dt.size == 0:
            return None
        fps = 1.0 / float(np.median(dt))
        if not np.isfinite(fps) or fps <= 0:
            return None
        return float(np.clip(fps, 1.0, 240.0))

    def _fill_forward(self, x: np.ndarray, fill_value: float) -> np.ndarray:
        """Forward-fill NaN 值。"""
        out = x.astype(float).copy()
        last = fill_value
        for i in range(out.size):
            if np.isfinite(out[i]):
                last = float(out[i])
            else:
                out[i] = last
        return out

    def _moving_average(self, data: np.ndarray, k: int) -> np.ndarray:
        """移動平均，自動補洞。"""
        if k is None or int(k) <= 1:
            return data

        arr = np.asarray(data, dtype=float)
        was_1d = arr.ndim == 1

        if was_1d:
            d = arr.reshape(-1, 1)
        elif arr.ndim == 2:
            d = arr.copy()
        else:
            raise ValueError(f"僅支援 1D 或 2D 陣列，取得 ndim={arr.ndim}")

        n = d.shape[0]
        x = np.arange(n)

        for j in range(d.shape[1]):
            col = d[:, j]
            invalid = (col == 0) | (~np.isfinite(col))
            valid_idx = np.where(~invalid)[0]

            if valid_idx.size == 0:
                continue
            if valid_idx.size == n:
                filled = col
            else:
                fp = col[valid_idx]
                filled = np.interp(x, valid_idx, fp, left=fp[0], right=fp[-1])

            d[:, j] = uniform_filter1d(filled, size=int(k), mode="nearest")

        return d[:, 0] if was_1d else d

    def _valid_mask(self, pose: np.ndarray) -> np.ndarray:
        """回傳 (N,J) 的 mask，標記有效關節（非全零）。"""
        return np.any(pose != 0.0, axis=2)

    def _compute_anchor(
        self,
        pose: np.ndarray,
        valid: np.ndarray,
        *,
        left_hip: int = 23,
        right_hip: int = 24,
    ) -> np.ndarray:
        """計算每幀的縮放中心點（優先用左右髖中點）。"""
        n, j, _ = pose.shape
        out = np.zeros((n, 3), dtype=float)

        if left_hip >= j or right_hip >= j:
            raise ValueError(f"hip index out of range: {left_hip}, {right_hip}")

        m_both = valid[:, left_hip] & valid[:, right_hip]
        out[m_both] = (pose[m_both, left_hip] + pose[m_both, right_hip]) / 2.0

        m_l = valid[:, left_hip] & ~valid[:, right_hip]
        out[m_l] = pose[m_l, left_hip]

        m_r = valid[:, right_hip] & ~valid[:, left_hip]
        out[m_r] = pose[m_r, right_hip]

        # 左右髖都沒有時，用第一個有效關節
        m_missing = ~(valid[:, left_hip] | valid[:, right_hip])
        if np.any(m_missing):
            frames = np.where(m_missing)[0]
            sub_valid = valid[frames]
            any_valid = sub_valid.any(axis=1)
            if np.any(any_valid):
                idx = np.argmax(sub_valid[any_valid], axis=1)
                frames2 = frames[any_valid]
                out[frames2] = pose[frames2, idx]

        return out

    def _compute_frame_scales(
        self,
        pose: np.ndarray,
        valid: np.ndarray,
        bones: Sequence[Tuple[int, int]],
        *,
        eps: float = 1e-6,
    ) -> np.ndarray:
        """用骨頭長度中位數估算每幀尺度。"""
        n, j, _ = pose.shape

        if not bones:
            return np.full((n,), np.nan, dtype=float)

        lengths = []
        for a, b in bones:
            if a >= j or b >= j:
                continue
            m = valid[:, a] & valid[:, b]
            d = np.full((n,), np.nan, dtype=float)
            if np.any(m):
                diff = pose[m, a] - pose[m, b]
                d[m] = np.linalg.norm(diff, axis=1)
            lengths.append(d)

        if not lengths:
            return np.full((n,), np.nan, dtype=float)

        L = np.vstack(lengths).T
        s: np.ndarray = np.nanmedian(L, axis=1)
        s[(~np.isfinite(s)) | (s <= eps)] = np.nan
        return s

    def _estimate_pitch_angle_rad_from_ground(
        self,
        pose: np.ndarray,
        valid: np.ndarray,
        ground_joints: Sequence[int],
        *,
        quantile: float,
        min_points: int,
    ) -> Optional[float]:
        """用腳部接地點估計相機 pitch 角度（rad）。"""
        _n, j, _ = pose.shape
        joints = [idx for idx in ground_joints if 0 <= idx < j]
        if not joints:
            return None

        ys, zs = [], []
        q = float(np.clip(quantile, 0.50, 0.999))

        for idx in joints:
            m = valid[:, idx]
            if not np.any(m):
                continue
            y = pose[m, idx, 1].astype(float)
            z = pose[m, idx, 2].astype(float)
            sel_thr = np.quantile(y, q)
            sel = y >= sel_thr
            if np.any(sel):
                ys.append(y[sel])
                zs.append(z[sel])

        if not ys:
            return None

        y_all = np.concatenate(ys)
        z_all = np.concatenate(zs)
        ok = np.isfinite(y_all) & np.isfinite(z_all)
        y_all, z_all = y_all[ok], z_all[ok]

        if y_all.size < int(min_points):
            return None

        z0 = z_all - float(np.median(z_all))
        y0 = y_all - float(np.median(y_all))
        denom = float(np.dot(z0, z0))
        if denom <= 1e-9:
            return None

        a = float(np.clip(np.dot(z0, y0) / denom, -2.0, 2.0))
        return float(np.arctan(a))


if __name__ == "__main__":
    tag = "1_1_1031"
    npy = f"./data/npy/{tag}.npy"
    out_dir = "./outputs"
    out_path = Path(out_dir) / f"{Path(npy).stem}_calib.npy"

    calibrator = PoseNpyCalibrator(cfg=CalibrationConfig(mode="auto"))
    saved = calibrator.calibrate_npy(npy_path=npy, out_path=out_path)
    print(f"Saved calibrated npy: {saved}")
