"""
在有一個 pose 的 .npy：裡面每一幀都有 33 個關節的 3D 座標（單位：公尺）。
但是因為人有時候離相機近、有時候離相機遠，3D 量出來會出現「忽大忽小」的問題：
同一個人、同一個骨架，數值會被放大/縮小，導致高度曲線看起來很飄。

這支程式做兩種校正（可單獨或一起用）：

1) scale 校正（主要）：
   - 想法：人的骨頭長度（例如左右髖距、髖到膝、膝到踝…）不會一秒變長一秒變短。
   - 做法：每一幀都用骨頭長度估一個「這一幀看起來有多大」的尺度 s(t)，
           再把它縮放回一個固定參考大小 ref。

2) pitch 校正（可選）：
   - 有些情況不是忽大忽小，而是「越遠高度越怪」，常見原因是相機俯仰角或地面不水平。
   - 做法：用腳部接近地面的點估一條地面斜率，推估 pitch 角度，再把 y/z 旋轉回來。

重要保證（避免破壞你其他程式）：
- 本專案 pose npy 的第 34 個點（index 33）是「時間戳列」[0,0,t]，這裡完全不會改它。
- 無效的關節點通常是 (0,0,0)，校正時也會保持無效點不亂動。
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


# MediaPipe Pose（33 個關鍵點）：`https://developers.google.com/mediapipe/solutions/vision/pose_landmarker`
#
# 本專案的 pose npy 格式約定：
# - arr shape = (N, 34, 3)
# - arr[:, :33, :]：33 個關節點的「相機座標系 3D（公尺）」(x,y,z)
#   * RealSense rs2_deproject_pixel_to_point 回傳座標通常為：x 向右、y 向下、z 向前（遠離相機）
# - arr[:, 33, :]：時間戳列（timestamp row），格式為 [0, 0, t_seconds]


# DEFAULT_BONES：用來「估算每幀尺度」的骨頭清單。
# 我們選一些相對穩定、比較不會因為小動作就變形的長度（骨頭長度理論上固定）。
DEFAULT_BONES: Tuple[Tuple[int, int], ...] = (
    # 上半身 / 骨盆 / 肩膀（通常比較穩）
    (23, 24),  # 23=左髖, 24=右髖 -> 左右髖距
    (11, 12),  # 11=左肩, 12=右肩 -> 左右肩距
    (11, 23),  # 左肩到左髖 -> 軀幹左側長度
    (12, 24),  # 右肩到右髖 -> 軀幹右側長度
    # 下半身 / 腿（也很適合估尺度）
    (23, 25),  # 左髖到左膝
    (24, 26),  # 右髖到右膝
    (25, 27),  # 左膝到左踝
    (26, 28),  # 右膝到右踝
)


# DEFAULT_GROUND_JOINTS：用來推估「地面」與「相機 pitch（俯仰）」的腳部關節。
# 理由：腳的點最容易接近地面，用它們來看地面是否是斜的。
DEFAULT_GROUND_JOINTS: Tuple[int, ...] = (
    27,  # 左踝
    28,  # 右踝
    29,  # 左腳跟
    30,  # 右腳跟
    31,  # 左腳尖（foot index）
    32,  # 右腳尖（foot index）
)


@dataclass(frozen=True)
class CalibrationConfig:
    """
    Pose npy 的「校正」設定。

    mode(校正模式):
      - "scale"        :用「骨頭長度」推估每一幀的縮放因子，修正忽遠忽近造成的尺度漂移
      - "pitch"        :用「腳部接地點」推估相機俯仰(pitch)，修正「高度隨距離漂移」(optional)
      - "scale+pitch"  :兩者都做
      - "auto"         "一定做 scale;pitch 只有在估到的角度夠大時才做（避免過度校正）
    """

    # mode：選擇要做哪種校正（預設 auto）
    mode: Literal["auto", "scale", "pitch", "scale+pitch"] = "auto"

    # scale normalization（尺度校正：修正忽遠忽近造成的整體縮放漂移)
    bones: Tuple[Tuple[int, int], ...] = DEFAULT_BONES  # 用哪些「骨頭(兩關節索引)」來估每幀的身體尺度
    scale_clip: Tuple[float, float] = (0.5, 2.0)  # 縮放倍率的上下限，避免壞幀讓倍率爆掉
    smooth_scale_s: float = 0.75  # 縮放倍率平滑時間窗(秒)；設 0 代表不平滑

    # pitch correction（俯仰校正：修正「高度隨距離漂移」，本質是 y/z 平面旋轉）
    ground_joints: Tuple[int, ...] = DEFAULT_GROUND_JOINTS  # 用哪些「腳部關節」來推估地面/俯仰角（腳踝、腳跟、腳尖等）
    ground_quantile: float = 0.90  # 只取 y 最大的前 q 分位當「最接近地面」的點來估斜率（相機座標常見 y 向下）
    min_ground_points: int = 200  # 用來估俯仰角的最少點數，不足就不做 pitch 校正
    auto_pitch_min_deg: float = 2.0  # auto 模式門檻：估到的 |pitch| 小於此角度(度) 就不做（避免過度校正）


class PoseNpyCalibrator:
    """
    Pose npy 校正器（把校正流程集中在同一個 class，避免函數分散）。

    支援兩種校正：
    - scale：修正忽遠忽近造成的整體尺度漂移
    - pitch：修正「高度隨距離漂移」（相機俯仰/地面不水平）
    """

    def __init__(self, cfg: CalibrationConfig = CalibrationConfig()):
        self.cfg = cfg

    def calibrate_array(self, arr: np.ndarray) -> np.ndarray:
        """
        校正本專案 pose npy 載入後的陣列，輸出一份「更穩定」的新座標。

        - 只校正前 33 個關節（index 0~32）
        - index 33 的「時間戳列」會被完整保留（不改動）
        """
        # 把設定拿出來（只是讓後面寫起來短一點）
        cfg = self.cfg

        # 保險：就算你傳進來的是 list，也先轉成 numpy array 方便後續計算
        arr = np.asarray(arr)

        # 我們只支援 (N, J, 3) 這種格式：最後一維一定要是 3（x,y,z）
        # 記住：如果 shape 不符合，後面所有運算都沒有意義，所以直接報錯。
        if arr.ndim != 3 or arr.shape[-1] != 3:
            raise ValueError(f"Expected arr shape (N,J,3); got {arr.shape}")

        # 拆出維度：N=幀數、J=關節數、3=xyz
        _n, j, _ = arr.shape

        # 為了容忍有人只存 33 而沒有 timestamp row（34），所以 pose_j 用 min(33, j)
        pose_j = min(33, j)

        # 判斷有沒有第 34 列（index 33）的 timestamp row
        # 有 timestamp 的好處：我們可以用時間戳估 fps，進而把 scale factor 做更合理的平滑
        has_timestamp_row = j >= 34

        out = arr.copy()

        # pose：只取前 33 個關節做校正；型別轉 float 是為了避免整數運算造成截斷
        pose = out[:, :pose_j, :].astype(float, copy=False)

        # valid：每個關節是否有效（不是 (0,0,0)）
        valid = self._valid_mask(pose)

        # mode：看使用者指定要做哪一種校正（scale / pitch / 兩者 / auto）
        mode = cfg.mode

        # 尺度（scale）校正：修正忽遠忽近造成的整體縮放漂移
        if mode in ("auto", "scale", "scale+pitch"):
            # s(t)：每一幀的「身體尺度」代理值（用骨頭長度的中位數當作這幀有多大）
            # 直覺：人離相機近 -> 3D 看起來會變大 -> 骨頭長度也變大 -> s(t) 變大
            s = self._compute_frame_scales(pose, valid, cfg.bones)

            # ref：整段影片的「標準尺度」（用中位數比較不怕離群值）
            # 如果 s 全都是 NaN（例如都沒有有效關節），就退回 ref=1.0
            ref = float(np.nanmedian(s)) if np.any(np.isfinite(s)) else 1.0

            # ref 不能是 NaN/inf，也不能太小（避免除以 0）
            if not np.isfinite(ref) or ref <= 1e-6:
                ref = 1.0

            # f(t) = ref / s(t)：每一幀的縮放倍率
            # - s(t) 太大（近） -> f(t) < 1 -> 把這幀縮小
            # - s(t) 太小（遠） -> f(t) > 1 -> 把這幀放大
            f = ref / s

            # 如果 s(t) 是 NaN/0 造成 f(t) 變成 inf/NaN，先統一標成 NaN，等一下用補值處理
            f[~np.isfinite(f)] = np.nan

            # 取出縮放倍率的限制範圍（避免壞幀讓倍率爆掉）
            lo, hi = cfg.scale_clip

            # 把倍率夾在 [lo, hi] 之間 
            f = np.clip(f, lo, hi)

            # 把 NaN 的倍率用「上一幀」補起來（開頭如果 NaN 就用 1.0）
            f = self._fill_forward(f, 1.0)

            # 若有時間戳，就用時間窗把縮放因子 f(t) 做平滑（避免單幀跳動）
            if cfg.smooth_scale_s and cfg.smooth_scale_s > 0 and has_timestamp_row:
                # t：每一幀的時間（秒），存在 timestamp row 的 z 位置（[0,0,t]）
                t = arr[:, 33, 2].astype(float)

                # 估計 fps（為了把「秒」換算成「幀」的平滑窗大小）
                fps = self._estimate_fps_from_t(t)
                if fps is not None:
                    # k：平滑窗大小（幀）= smooth_scale_s（秒）* fps（幀/秒）
                    k = int(round(float(cfg.smooth_scale_s) * fps))
                    # 移動平均：把 f(t) 平滑一下（避免一幀一幀跳）
                    if k > 1:
                        f = self._moving_average(f, k=k)

            # anchor：縮放中心點（每一幀一個 3D 點）
            # 直覺：像「以髖部為中心縮放」，這樣人不會被縮放動作拉走位置
            anchor = self._compute_anchor(pose, valid)

            # 真正做縮放：把每個關節相對 anchor 的向量乘上倍率，再加回 anchor
            # 公式：scaled = (pose - anchor) * f + anchor
            scaled = (pose - anchor[:, None, :]) * f[:, None, None] + anchor[:, None, :]

            # 只對有效點套用縮放；無效點（0,0,0）保持原樣
            pose = np.where(valid[:, :, None], scaled, pose)

            # 把縮放結果寫回 out（維持原本 dtype，例如 float32）
            out[:, :pose_j, :] = pose.astype(out.dtype, copy=False)

        # pitch 校正：修正「高度隨距離漂移」（常見於相機俯仰/地面不水平）
        if mode in ("auto", "pitch", "scale+pitch"):
            # scale 校正後重新取一次 pose（若 scale 沒做就會是原始 pose）
            pose = out[:, :pose_j, :].astype(float, copy=False)
            # 重新算一次 valid（因為 pose 可能已經被 scale 更新過）
            valid = self._valid_mask(pose)

            # theta：估計出來的 pitch 角度（rad）
            # - 如果資料不足/不可靠，會回傳 None（代表不做 pitch）
            theta = self._estimate_pitch_angle_rad_from_ground(
                pose,
                valid,
                cfg.ground_joints,
                quantile=cfg.ground_quantile,
                min_points=cfg.min_ground_points,
            )

            if theta is not None:
                # auto 模式：角度太小就不做（避免過度校正）
                if mode == "auto":
                    # 把「度」換成「弧度」做比較
                    min_rad = float(np.deg2rad(cfg.auto_pitch_min_deg))
                    if abs(theta) < min_rad:
                        # 角度太小 -> 視為不需要修
                        theta = None

            if theta is not None:
                # cos/sin：旋轉矩陣需要的參數
                c = float(np.cos(theta))
                s_ = float(np.sin(theta))

                # 把 y/z 拿出來（因為 pitch 是繞 x 軸旋轉，只會動到 y 和 z）
                y = pose[:, :, 1]
                z = pose[:, :, 2]

                # 旋轉公式（繞 x 軸）：
                # y' = y*cos(theta) - z*sin(theta)
                # z' = y*sin(theta) + z*cos(theta)
                y_rot = y * c - z * s_
                z_rot = y * s_ + z * c

                # pose2：避免直接改原 pose（更安全，也方便理解）
                pose2 = pose.copy()

                # 只對有效點寫入旋轉後的 y/z；無效點保留
                pose2[:, :, 1] = np.where(valid, y_rot, y)
                pose2[:, :, 2] = np.where(valid, z_rot, z)

                # 寫回 out（保持 dtype）
                out[:, :pose_j, :] = pose2.astype(out.dtype, copy=False)

        # 注意：index 33 的時間戳列不會被動到（out = arr.copy() 已保留）
        return out

    def calibrate_npy(
        self,
        *,
        npy_path: Optional[str | Path] = None,
        arr: Optional[np.ndarray] = None,
        out_path: Optional[str | Path] = None,
    ) -> Path:
        """
        讀取 pose npy、做校正、並存成新的 npy。

        若 out_path 為 None，會存到同資料夾並加上尾碼：`_calib.npy`。
        """
        if npy_path is not None:
            # 把輸入路徑轉成 Path（不管你傳字串還是 Path 都統一處理）
            in_path = Path(npy_path)

            # 讀取 npy：這會得到 (N, 34, 3) 的 numpy array（本專案的 pose 格式）
            arr = np.load(in_path)
        
        if arr is None:
            raise ValueError("npy_path or arr is required")

        # 直接呼叫 calibrate_array 做校正，拿到校正後的陣列
        out_arr = self.calibrate_array(arr)

        # 如果使用者沒有指定輸出檔名，就用「原檔名 + _calib」當作新檔名
        if out_path is None:
            out_path = in_path.with_name(f"{in_path.stem}_calib.npy")

        # 再把 out_path 轉成 Path（確保一致）
        out_path = Path(out_path)

        # 確保輸出資料夾存在（例如 outputs/xxx/）
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # 存檔：把校正後的陣列寫到新的 npy
        np.save(out_path, out_arr)

        # 回傳輸出路徑，方便外面顯示/串接
        return out_path

    def _estimate_fps_from_t(self, t: np.ndarray) -> Optional[float]:
        """從時間戳序列（秒）估計 FPS。若資訊不足則回傳 None。"""
        # 雖然型別提示寫 np.ndarray，但我們仍容忍有人傳 None（更穩健）
        if t is None:
            return None
        # 把 t 轉成 1D float array（避免 t 是 list / shape 不是 (N,)）
        t = np.asarray(t, dtype=float).ravel()
        # 幀數太少，沒辦法估 fps（至少要 3 個點才像樣）
        if t.size < 3:
            return None
        # dt：相鄰幀時間差
        dt = np.diff(t)
        # 只保留合理的 dt（必須是有限且 > 0），避免時間戳重複/倒退影響估計
        dt = dt[np.isfinite(dt) & (dt > 0)]
        if dt.size == 0:
            return None
        # fps ≈ 1 / median(dt)：用中位數比較不怕離群值
        fps = 1.0 / float(np.median(dt))
        # fps 不合理就回 None（例如變成 inf 或 <=0）
        if not np.isfinite(fps) or fps <= 0:
            return None
        # 把 fps 夾在合理範圍，避免極端值（1~240 fps）
        return float(np.clip(fps, 1.0, 240.0))

    def _fill_forward(self, x: np.ndarray, fill_value: float) -> np.ndarray:
        """把 NaN 做 forward-fill；開頭的 NaN 會用 fill_value 補上。"""
        # out：複製一份（避免改到原始 x）
        out = x.astype(float).copy()
        # n：序列長度（幀數）
        n = out.size
        # last：記住上一個有效值；一開始先用 fill_value
        last = fill_value
        for i in range(n):
            # 如果這格是有效數值（不是 NaN/inf），就更新 last
            if np.isfinite(out[i]):
                last = float(out[i])
            else:
                # 如果這格是 NaN，就用上一個有效值 last 補上
                out[i] = last
        # 回傳補好洞的序列
        return out

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

    def _valid_mask(self, pose: np.ndarray) -> np.ndarray:
        """pose: (N,J,3) -> valid: (N,J)。只要該關節任一座標非 0，就視為有效。"""
        # axis=2 表示沿著 (x,y,z) 這個維度去看
        # 只要 x/y/z 任一個不是 0，就代表這個關節有被偵測到（有效）
        return np.any(pose != 0.0, axis=2)

    def _compute_anchor(
        self,
        pose: np.ndarray,
        valid: np.ndarray,
        *,
        left_hip: int = 23,
        right_hip: int = 24,
    ) -> np.ndarray:
        """
        計算每一幀的 anchor（縮放中心點）座標。
        """
        # n=幀數、j=關節數
        n, j, _ = pose.shape

        # out：每一幀的 anchor（中心點）座標，shape=(n,3)
        # 預設先填 0，後面再依 anchor 規則補上
        out = np.zeros((n, 3), dtype=float)
        
        if left_hip >= j or right_hip >= j:
            raise ValueError(f"left_hip or right_hip is out of range: {left_hip} or {right_hip}")

        # 使用「左右髖中點」當作縮放中心
        # m_both：左右髖都存在的幀
        m_both = valid[:, left_hip] & valid[:, right_hip]
        # 左右髖都存在 -> anchor = (左髖 + 右髖) / 2
        out[m_both] = (pose[m_both, left_hip] + pose[m_both, right_hip]) / 2.0

        # m_l：只有左髖存在
        m_l = valid[:, left_hip] & ~valid[:, right_hip]
        # 只有左髖 -> 用左髖當 anchor
        out[m_l] = pose[m_l, left_hip]

        # m_r：只有右髖存在
        m_r = valid[:, right_hip] & ~valid[:, left_hip]
        # 只有右髖 -> 用右髖當 anchor
        out[m_r] = pose[m_r, right_hip]

        # m_missing：左右髖都不存在（例如偵測失敗）
        m_missing = ~(valid[:, left_hip] | valid[:, right_hip])
        if np.any(m_missing):
            # frames：缺左右髖的幀索引列表
            frames = np.where(m_missing)[0]
            # sub_valid：這些幀在每個關節的有效性
            sub_valid = valid[frames]
            # any_valid：這些幀是否「至少有一個關節有效」
            any_valid = sub_valid.any(axis=1)
            # 如果這些幀中至少有一個關節有效，則用「第一個有效關節」的座標當作 anchor
            if np.any(any_valid):
                # idx：每一幀「第一個有效關節」的索引（argmax 會回傳第一個 True 的位置）
                idx = np.argmax(sub_valid[any_valid], axis=1)
                # frames2：那些真的有有效關節的幀
                frames2 = frames[any_valid]
                # 把這些幀的 anchor 設成「第一個有效關節」的座標（總比全 0 好）
                out[frames2] = pose[frames2, idx]
                
        # mid_hips 情況完成，直接回傳
        return out

    def _compute_frame_scales(
        self,
        pose: np.ndarray,
        valid: np.ndarray,
        bones: Sequence[Tuple[int, int]],
        *,
        eps: float = 1e-6,
    ) -> np.ndarray:
        """
        以「多條骨頭長度的中位數」當作每一幀的尺度代理 s(t)。

        回傳 shape = (N,)；若某幀沒有任何可用骨頭，該幀為 NaN。
        """
        # n=幀數、j=關節數
        n, j, _ = pose.shape

        # 如果 bones 清單是空的，就沒辦法估尺度，全部回 NaN
        if not bones:
            return np.full((n,), np.nan, dtype=float)

        # lengths：每條骨頭在每一幀的長度序列（之後會堆成矩陣）
        lengths = []
        for a, b in bones:
            # 如果骨頭索引超出關節數，就跳過
            if a >= j or b >= j:
                continue
            # m：這條骨頭在某幀是否可用（兩端關節都有效）
            m = valid[:, a] & valid[:, b]
            # d：先建立一條長度序列（每幀一個值），預設 NaN
            d = np.full((n,), np.nan, dtype=float)
            if np.any(m):
                # diff：骨頭向量 = 關節 a - 關節 b（每幀一個 3D 向量）
                diff = pose[m, a] - pose[m, b]
                # 長度 = 向量的 L2 norm
                d[m] = np.linalg.norm(diff, axis=1)
            # 把這條骨頭的長度序列加入列表
            lengths.append(d)

        # 如果完全沒有任何骨頭能用，一樣回 NaN
        if not lengths:
            return np.full((n,), np.nan, dtype=float)

        # L：把多條骨頭堆起來，shape=(N, nbones)
        # - 每一列是某一幀
        # - 每一行是某一條骨頭的長度
        L = np.vstack(lengths).T  # (N, nbones)

        # s：每一幀取「骨頭長度的中位數」當作尺度代理（比較穩，不怕某條骨頭爆掉）
        s: np.ndarray = np.nanmedian(L, axis=1)

        # 如果 s 是 NaN/inf 或 <= eps，就視為不可用，設成 NaN
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
        """
        用腳部「接地」點估計相機 pitch（繞 x 軸旋轉的角度，單位：rad）。

        作法：
        - 在相機座標中通常 y 向下，因此「越接近地面」會有越大的 y
        - 對這些「地面附近」的足部點，擬合直線：y ≈ a*z + b
        - 角度 theta = arctan(a)
        """
        # j=關節數
        _n, j, _ = pose.shape

        # joints：把 ground_joints 過濾成「合法索引」
        joints = [idx for idx in ground_joints if 0 <= idx < j]
        if not joints:
            return None

        # ys/zs：收集地面附近點的 y 與 z（最後會 concatenate）
        ys: list[np.ndarray] = []
        zs: list[np.ndarray] = []

        # quantile 夾在合理範圍（太小就不叫「接地」，太大可能點數不夠）
        q = float(np.clip(quantile, 0.50, 0.999))

        for idx in joints:
            # m：哪些幀這個腳部關節是有效的
            m = valid[:, idx]
            if not np.any(m):
                continue
            # 取出有效幀的 y/z
            y = pose[m, idx, 1].astype(float)
            z = pose[m, idx, 2].astype(float)

            # sel_thr：y 的分位數門檻；我們只取「y 最大」的那些點當作最接近地面
            sel_thr = np.quantile(y, q)
            # sel：y >= sel_thr 的點（比較接近地面）
            sel = y >= sel_thr
            if np.any(sel):
                # 把選到的點加入列表（之後一起做線性擬合）
                ys.append(y[sel])
                zs.append(z[sel])

        if not ys:
            return None

        # 把不同關節收集到的點合併成一大包
        y_all = np.concatenate(ys, axis=0)
        z_all = np.concatenate(zs, axis=0)

        # 過濾掉 NaN/inf
        ok = np.isfinite(y_all) & np.isfinite(z_all)
        y_all = y_all[ok]
        z_all = z_all[ok]

        # 點數太少就不要硬估 pitch（會不準）
        if y_all.size < int(min_points):
            return None

        # 用最小平方法估斜率：y ≈ a*z + b
        # 為了數值穩定先做「去中心化」：減掉中位數
        z0 = z_all - float(np.median(z_all))
        y0 = y_all - float(np.median(y_all))

        # denom = sum(z0^2) = var(z) 的比例；如果太小代表 z 幾乎不變，就沒法估斜率
        denom = float(np.dot(z0, z0))
        if denom <= 1e-9:
            return None

        # a = sum(z0*y0) / sum(z0^2) （等價 cov/var）
        a = float(np.dot(z0, y0) / denom)

        # guard：避免斜率太誇張（角度會接近 90 度，不合理也不穩）
        a = float(np.clip(a, -2.0, 2.0))  # about +/-63 deg

        # theta：pitch 角度（rad）= arctan(斜率)
        theta = float(np.arctan(a))
        return theta

if __name__ == "__main__":
    # 範例
    # 1_1_1031, 4_1_1208, 1_1_607, 4_1_1208_pose_30, 1_1_1031_pose_30
    tag = "1_1_1031"
    npy = f"./data/npy/{tag}.npy"
    # npy = f"./outputs/{tag}/{tag}_pose.npy"
    out_dir = "./outputs"
    out_path = Path(out_dir) / f"{Path(npy).stem}_calib.npy"

    calibrator = PoseNpyCalibrator(
        cfg=CalibrationConfig(
            mode="auto",
        )
    )
    saved = calibrator.calibrate_npy(npy_path=npy, out_path=out_path)
    print(f"Saved calibrated npy: {saved}")