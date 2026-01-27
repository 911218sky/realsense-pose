"""
時頻分析相關繪圖。

包含空間頻譜和多系列 FFT 分析。
"""
from pathlib import Path
from typing import Any, Sequence, Literal, Mapping

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.axes import Axes

from utils import add_prefix_to_filename
from .utils import VisualizerUtilsMixin


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
        save_name: str | None = None,
        top_k: int | None = None,
        spec_ylim: tuple[float, float | None] | None = None,
    ) -> Path:
        """
        實際繪製一個 pair 的空間頻譜圖（以 dB 顯示）。

        pair:
            "xz" 表 X(Z)，"yz" 表 Y(Z)
        spec_ylim:
            y 軸範圍（單位 dB，0 dB 代表此頻譜中的最大值）
        """
        f, spec = self.compute_spatial_spectrum_zind(pair=pair, k_smooth=k_smooth)

        f = np.asarray(f, dtype=float)
        spec = np.asarray(spec, dtype=float)

        eps = np.finfo(float).tiny
        max_spec = float(spec.max()) if spec.size else 0.0
        if max_spec <= 0.0:
            spec_db = np.full_like(spec, -300.0)
        else:
            spec_db = 10.0 * np.log10(np.maximum(spec / max_spec, eps))

        dep_label, indep_label = self._axis_labels_for_pair(pair)
        label_axis = f"{dep_label}({indep_label})"

        fig, ax = plt.subplots(figsize=(12, 4.2), dpi=dpi, layout="constrained")
        ax.plot(f, spec_db, lw=1.6, label=f"{label_axis} spectrum (periodogram, dB)")

        if spec_db.size >= 3 and top_k is not None:
            self._annotate_spectrum_peaks(
                ax, f, spec_db, top_k, min_freq, min_db, min_peak_distance_ratio, spec_ylim
            )

        pair_str = f"{dep_label}{indep_label}"
        ax.set_xlabel(f"Spatial frequency (cycles / unit-{pair_str})")
        ax.set_ylabel("Power (dB, re max = 0 dB)")
        ax.set_title(f"{self.prefix} - Spatial spectrum with {pair_str} as independent")
        ax.grid(True, alpha=0.3)
        if spec_ylim is not None:
            self._apply_limits(ax, ylim=spec_ylim)

        default_name = (save_name or "{pair}_spatial_spectrum_db.png").format(pair=pair_str)
        filename = add_prefix_to_filename(default_name, self.prefix)
        save_path = Path(self.out_dir) / (filename or default_name)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(save_path))
        plt.close(fig)
        return save_path

    def _annotate_spectrum_peaks(
        self,
        ax: Axes,
        f: np.ndarray[Any, Any],
        spec_db: np.ndarray[Any, Any],
        top_k: int,
        min_freq: float,
        min_db: float,
        min_peak_distance_ratio: float,
        spec_ylim: tuple[float, float | None] | None,
    ) -> None:
        """標註頻譜的峰值。"""
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

        if not idx_candidates:
            return

        idx_candidates = np.asarray(idx_candidates, dtype=int)
        order = np.argsort(spec_db[idx_candidates])[::-1]
        idx_sorted = idx_candidates[order]

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

        if spec_ylim is not None and spec_ylim[1] is not None:
            y_span = float(spec_ylim[1] - spec_ylim[0])
            dy = 0.04 * y_span
        else:
            dy = 2.0

        for idx in chosen:
            x = float(f[idx])
            y = float(spec_db[idx])

            ax.scatter([x], [y], s=35, zorder=5, color="#f97316")
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

    def save_spatial_spectrum(
        self,
        *,
        pair: list[Literal["xz", "yz"]] | None = None,
        k_smooth: int = 2,
        top_k: int | None = None,
        dpi: int = 150,
        spec_ylim: list[tuple[float, float | None]] | None = None,
        save_name: str | list[str | None] | None = None,
    ) -> list[Path]:
        """
        一次產生多個空間頻譜圖。

        pair:
            例如 ["xz", "yz"]
        spec_ylim:
            每個 pair 對應一組縱軸範圍
        save_name:
            可傳字串或字串列表（與 pair 對應）
        """
        if pair is None:
            pair = ["xz", "yz"]
        
        save_paths: list[Path] = []

        for idx, p in enumerate(pair):
            if p not in ("xz", "yz"):
                raise ValueError(f"pair 必須是 'xz' 或 'yz'，但得到 {p}")

            if isinstance(save_name, list):
                this_save_name: str | None = save_name[idx]
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
        joints: Sequence[int | str | Sequence[int | str]],
        labels: Sequence[str],
        *,
        component: Literal["x", "y", "z"] = "z",
        max_peaks: int = 3,
        dpi: int = 150,
        figsize: tuple[float, float] = (11.0, 4.0),
        min_peak_distance_ratio: float = 0.01,
        min_db: float = -40.0,
        min_freq: float = 0.05,
        save_name: str | None = None,
        xlim: tuple[float, float | None] | None = None,
        ylim: tuple[float, float | None] | None = None,
        fft_params: Mapping[str, Any] | None = None,
    ) -> Path:
        """
        對多條時間序列做 FFT/PSD，畫在同一張圖上。

        joints:
            - 可以是單一關節編號/名稱，例如 27, "L_HEEL"
            - 也可以是關節群，例如 [27, 28]，代表先在指定 component 上做平均再 FFT

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

        component_idx = {"x": 0, "y": 1, "z": 2}.get(component)
        if component_idx is None:
            raise ValueError(f"component 必須是 'x', 'y', 'z'，但得到 {component}")

        fft_kwargs = dict(fft_params or {})
        results = []
        max_power = 0.0

        for joint_spec in joints:
            series = self._series_from_joint_spec(joint_spec, component_idx)
            t_arr = self.t if self.t is not None else np.arange(len(series), dtype=float)
            res = self.compute_lateral_offset_fft(
                lat=np.asarray(series, dtype=float),
                t=t_arr,
                **fft_kwargs,
            )
            results.append(res)
            if res.Pxx.size:
                pmax = float(np.nanmax(res.Pxx))
                if np.isfinite(pmax):
                    max_power = max(max_power, pmax)

        eps = np.finfo(float).tiny
        if not np.isfinite(max_power) or max_power <= 0.0:
            max_power = 1.0

        fig, ax = plt.subplots(figsize=figsize, dpi=dpi, layout="constrained")

        for res, label in zip(results, labels):
            f = np.asarray(res.f, dtype=float)
            Pxx = np.asarray(res.Pxx, dtype=float)
            if f.size == 0 or Pxx.size == 0:
                continue

            psd_db = 10.0 * np.log10(np.maximum(Pxx / max_power, eps))
            (line,) = ax.plot(f, psd_db, lw=1.6, label=str(label))
            color = line.get_color()

            peak_indices = self._select_peak_indices(
                f, psd_db, max_peaks=max_peaks, xlim=xlim,
                min_peak_distance_ratio=min_peak_distance_ratio,
                min_db=min_db, min_freq=min_freq,
            )
            if peak_indices:
                self._annotate_fft_peaks(ax, f, psd_db, peak_indices, color, xlim, ylim)

        joints_str = "_".join(self._format_joint_spec(j) for j in joints)
        ax.set_xlabel("Frequency (Hz)")
        ax.set_ylabel("Power (dB, re max = 0 dB)")
        ax.set_title(f"{self.prefix}-{joints_str} - Multi-series FFT")
        ax.grid(True, alpha=0.3)
        ax.legend(loc="upper right", frameon=False)
        if xlim is not None:
            self._apply_limits(ax, xlim=xlim)
        if ylim is not None:
            self._apply_limits(ax, ylim=ylim)

        default_name = (save_name or "{joints}_multi_fft.png").format(joints=joints_str)
        filename = add_prefix_to_filename(default_name, self.prefix)
        save_path = Path(self.out_dir) / (filename or default_name)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(save_path))
        plt.close(fig)
        return save_path

    def _series_from_joint_spec(
        self, spec: int | str | Sequence[int | str], component_idx: int
    ) -> np.ndarray[Any, Any]:
        """從關節規格取得時間序列。"""
        if isinstance(spec, (list, tuple, np.ndarray)):
            if not spec:
                raise ValueError("joint group 不能是空的。")
            idxs = [self.resolve_joint(s) for s in spec]
            arr_group = self.arr[:, idxs, component_idx]
            return np.mean(arr_group, axis=1)
        idx = self.resolve_joint(spec)
        return self.arr[:, idx, component_idx]

    @staticmethod
    def _format_joint_spec(spec: int | str | Sequence[int | str]) -> str:
        """把關節規格轉成適合檔名的字串。"""
        if isinstance(spec, (list, tuple, np.ndarray)):
            return "_".join(str(x) for x in spec)
        return str(spec)

    @staticmethod
    def _select_peak_indices(
        f: np.ndarray[Any, Any],
        psd_db: np.ndarray[Any, Any],
        *,
        max_peaks: int,
        xlim: tuple[float, float | None] | None,
        min_peak_distance_ratio: float,
        min_db: float,
        min_freq: float,
    ) -> list[int]:
        """從 PSD 曲線中挑出要標註的 peak index。"""
        if max_peaks <= 0 or psd_db.size <= 2:
            return []

        if xlim is not None and xlim[1] is not None:
            f_min, f_max = xlim[0], xlim[1]
        else:
            f_min, f_max = float(f.min()), float(f.max())
        f_span = max(f_max - f_min, 1e-9)
        min_df = min_peak_distance_ratio * f_span

        base_mask = np.isfinite(psd_db)
        base_mask &= psd_db >= min_db
        base_mask &= f >= max(min_freq, f_min)
        base_mask &= f <= f_max

        idx_all = np.nonzero(base_mask)[0]
        if idx_all.size == 0:
            return []

        best_idx_global = int(idx_all[np.nanargmax(psd_db[idx_all])])

        idx_candidates: list[int] = []
        for idx in idx_all:
            if idx == 0 or idx == psd_db.size - 1:
                continue
            if psd_db[idx] >= psd_db[idx - 1] and psd_db[idx] >= psd_db[idx + 1]:
                idx_candidates.append(idx)

        if best_idx_global not in idx_candidates:
            idx_candidates.append(best_idx_global)

        idx_candidates_arr = np.asarray(idx_candidates, dtype=int)
        order = np.argsort(psd_db[idx_candidates_arr])[::-1]
        idx_sorted = idx_candidates_arr[order]

        chosen: list[int] = []
        for idx in idx_sorted:
            if len(chosen) >= max_peaks:
                break
            if not chosen or all(abs(f[idx] - f[j]) >= min_df for j in chosen):
                chosen.append(idx)

        return chosen

    def _annotate_fft_peaks(
        self,
        ax: Axes,
        f: np.ndarray[Any, Any],
        psd_db: np.ndarray[Any, Any],
        peak_indices: list[int],
        color: Any,
        xlim: tuple[float, float | None] | None,
        ylim: tuple[float, float | None] | None,
    ) -> None:
        """標註 FFT 峰值。"""
        if ylim is not None and ylim[1] is not None:
            y_span = float(ylim[1] - ylim[0])
        else:
            y_span = float(np.nanmax(psd_db) - np.nanmin(psd_db) + 1e-6)
        dy = 0.04 * y_span

        if xlim is not None and xlim[1] is not None:
            f_min, f_max = xlim[0], xlim[1]
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
