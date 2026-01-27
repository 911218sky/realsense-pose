import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas

_has_pil = False
_Image: Any = None
_mpimg: Any = None

try:
    from PIL import Image
    _has_pil = True
    _Image = Image
except Exception:
    _has_pil = False
    from matplotlib import image as _mpimg_module
    _mpimg = _mpimg_module

class FFmpegPipe:
    """
    ffmpeg 管線輔助類別，透過 stdin pipe 串流 raw frames 給 ffmpeg 編碼成影片。

    若 pipe 模式失敗（常見於 Windows），會自動切換到 fallback 模式：
    先把每幀存成暫存 PNG，最後再用 ffmpeg 合成影片。
    """

    def __init__(
        self,
        out_path: str | bytes,
        width: int,
        height: int,
        fps: int = 30,
        preset: str | None = "ultrafast",
        crf: int | None = 28,
        bitrate_kbps: int | None = None,
        pixel_format: str = "rgb24",
        ffmpeg_exe: str = "ffmpeg",
        extra_args: Iterable[str] | None = None,
        loglevel: str = "error",
    ) -> None:

        self.out_path: str = str(out_path)
        self.W: int = int(width)
        self.H: int = int(height)
        if self.W <= 0 or self.H <= 0:
            raise ValueError("width/height must be positive integers.")
        self.fps: int = int(fps)
        if self.fps <= 0:
            raise ValueError("fps must be a positive integer.")

        self.preset = preset
        self.crf = crf
        self.bitrate_kbps = bitrate_kbps
        self.pixel_format = pixel_format
        self.ffmpeg_exe = ffmpeg_exe
        self.proc: subprocess.Popen[bytes] | None = None
        self._extra_args = list(extra_args) if extra_args else []
        self._loglevel = loglevel

        # fallback 狀態
        self._fallback_mode: bool = False
        self._temp_dir: Path | None = None
        self._frame_index: int = 0

        # 準備輸出資料夾
        Path(self.out_path).parent.mkdir(parents=True, exist_ok=True)

        # 基本檢查：ffmpeg 是否存在（無論 pipe 或 fallback 都需要）
        if shutil.which(self.ffmpeg_exe) is None:
            raise FileNotFoundError(
                f"Cannot find '{self.ffmpeg_exe}'. "
                "Please install ffmpeg or add the executable to PATH."
            )

        # 嘗試啟動 ffmpeg（pipe 模式）
        self._start_process()

    def _build_cmd(self) -> list[str]:
        # 將 -loglevel / -hide_banner 等 global option 放前面
        cmd = [
            self.ffmpeg_exe,
            "-hide_banner",
            "-loglevel", self._loglevel,
            "-y",
            "-f", "rawvideo",
            "-pix_fmt", self.pixel_format,
            "-s", f"{self.W}x{self.H}",
            "-r", str(self.fps),
            "-i", "-",               # 從 stdin 讀 raw frames
            "-an",
            "-vcodec", "libx264",
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
            "-pix_fmt", "yuv420p",
        ]
        if self.preset:
            cmd += ["-preset", self.preset]
        if self.crf is not None:
            cmd += ["-crf", str(int(self.crf))]
        if (self.crf is None) and (self.bitrate_kbps is not None):
            cmd += ["-b:v", f"{int(self.bitrate_kbps)}k"]
        cmd += list(self._extra_args)
        cmd += [self.out_path]
        return cmd

    def _start_process(self) -> None:
        cmd = self._build_cmd()
        try:
            # Windows：隱藏視窗、避免一些 handle/console 相關問題
            if os.name == "nt":
                creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
                self.proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    bufsize=0,
                    creationflags=creationflags,
                )
            else:
                self.proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    bufsize=0,
                )
            self._fallback_mode = False
        except OSError as e:
            # pipe 模式失敗，啟用 fallback（寫 PNG 再合成速度較慢）
            print("FFmpegPipe: pipe mode failed. Fallback to temp-file mode. Error:", e)
            self.proc = None
            self._enable_fallback()

    def _enable_fallback(self) -> None:
        self._fallback_mode = True
        if self._temp_dir is None:
            self._temp_dir = Path(tempfile.mkdtemp(prefix="ffmpeg_pipe_"))
        self._frame_index = 0

    def _save_frame_to_disk(self, rgb: np.ndarray[Any, Any]) -> None:
        assert self._temp_dir is not None, "temp dir must be initialized in fallback mode"
        fname = self._temp_dir / f"frame_{self._frame_index:08d}.png"
        if _has_pil and _Image is not None:
            _Image.fromarray(rgb, mode="RGB").save(str(fname), format="PNG")
        elif _mpimg is not None:
            _mpimg.imsave(str(fname), rgb)
        self._frame_index += 1

    @staticmethod
    def _to_uint8_rgb(
        arr: np.ndarray[Any, np.dtype[np.generic]], 
        expect_h: int, 
        expect_w: int
    ) -> np.ndarray[Any, Any]:
        if arr.ndim != 3 or arr.shape[2] != 3:
            raise ValueError("rgb array must have shape (H, W, 3).")
        h, w, _ = arr.shape
        if (h != expect_h) or (w != expect_w):
            raise ValueError(f"rgb shape {(h, w)} doesn't match pipe size {(expect_h, expect_w)}.")
        if arr.dtype == np.uint8:
            return np.ascontiguousarray(arr)
        # 寬容地把其它 dtypes 轉為 uint8（float/整數等）
        if np.issubdtype(arr.dtype, np.floating):
            arr_float = arr.astype(np.float64)
            arr_float = np.clip(arr_float, 0.0, 1.0) if arr_float.max() <= 1.0 else np.clip(arr_float, 0.0, 255.0) / 255.0
            arr_uint8 = (arr_float * 255.0 + 0.5).astype(np.uint8)
        else:
            arr_uint8 = np.clip(arr, 0, 255).astype(np.uint8)
        return np.ascontiguousarray(arr_uint8)

    def write_frame_rgb_array(self, rgb: np.ndarray[Any, np.dtype[np.generic]]) -> None:
        rgb = self._to_uint8_rgb(rgb, self.H, self.W)

        if self._fallback_mode:
            if self._temp_dir is None:
                self._enable_fallback()
            self._save_frame_to_disk(rgb)
            return

        # pipe 模式
        if self.proc is None or self.proc.stdin is None:
            # 若意外沒有 proc，直接切換 fallback
            self._enable_fallback()
            self._save_frame_to_disk(rgb)
            return

        try:
            _ = self.proc.stdin.write(rgb.tobytes())
        except (BrokenPipeError, OSError) as e:
            # 中途斷線 → 切換 fallback，後續幀會繼續寫入 PNG
            print("FFmpegPipe: stdin write failed; switching to fallback. Error:", e)
            try:
                if self.proc and self.proc.stdin:
                    try:
                        self.proc.stdin.close()
                    except Exception:
                        pass
                if self.proc:
                    self.proc.kill()
            except Exception:
                pass
            finally:
                self.proc = None
            self._enable_fallback()
            self._save_frame_to_disk(rgb)

    def write_frame_from_canvas(self, canvas: FigureCanvas) -> None:
        arr = np.asarray(canvas.buffer_rgba())  # (H, W, 4)
        rgb = arr[:, :, :3]
        if rgb.dtype != np.uint8:
            if np.issubdtype(rgb.dtype, np.floating):
                rgb = np.clip(rgb, 0.0, 1.0)
                rgb = (rgb * 255.0 + 0.5).astype(np.uint8)
            else:
                rgb = rgb.astype(np.uint8)
        self.write_frame_rgb_array(rgb)

    def _ffmpeg_fallback_cmd(self) -> list[str]:
        if self._temp_dir is None:
            raise ValueError("temp_dir must be set in fallback mode")
        pattern = str(self._temp_dir / "frame_%08d.png")
        cmd = [
            self.ffmpeg_exe,
            "-hide_banner",
            "-loglevel", self._loglevel,
            "-y",
            "-framerate", str(self.fps),
            "-i", pattern,
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
        ]
        if self.preset:
            cmd += ["-preset", self.preset]
        if self.crf is not None:
            cmd += ["-crf", str(int(self.crf))]
        if (self.crf is None) and (self.bitrate_kbps is not None):
            cmd += ["-b:v", f"{int(self.bitrate_kbps)}k"]
        cmd += list(self._extra_args)
        cmd += [self.out_path]
        return cmd

    def close(self, check_returncode: bool = True) -> int | None:
        """
        回傳：
          - pipe 模式：ffmpeg returncode（通常 0）。
          - fallback：合成成功 0；未合成（無幀）或錯誤時 None 或非 0。
        """
        # fallback: 以 ffmpeg 合成 PNG
        if self._fallback_mode:
            rc = None
            try:
                if self._temp_dir is None:
                    return None
                if self._frame_index == 0:
                    # 沒有任何幀 → 清理後返回 None
                    return None
                cmd = self._ffmpeg_fallback_cmd()
                _ = subprocess.run(cmd, check=True)
                rc = 0
            except subprocess.CalledProcessError as e:
                print("FFmpegPipe: fallback ffmpeg failed:", e)
                rc = getattr(e, "returncode", None)
            finally:
                # 確保清理暫存
                try:
                    if self._temp_dir and self._temp_dir.exists():
                        shutil.rmtree(self._temp_dir)
                except Exception:
                    pass
                self._temp_dir = None
                self._frame_index = 0
            return rc

        # pipe 模式：正常收尾
        if self.proc is None:
            return None
        try:
            if self.proc.stdin:
                try:
                    self.proc.stdin.close()
                except Exception:
                    pass
            if check_returncode:
                self.proc.wait()
            return self.proc.returncode
        finally:
            self.proc = None

    def __enter__(self) -> "FFmpegPipe":
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: object) -> None:
        try:
            _ = self.close(check_returncode=(exc_type is None))
        except Exception:
            pass