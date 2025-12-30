"""Bag file preparation and output persistence helpers."""

import pickle
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np
import zstandard as zstd

from utils import add_prefix_to_filename

class BagIOMixin:
    def _prepare_bag_file(self, bag_path: Path) -> str:
        """
        如果輸入是 zstd 壓縮的 bag（例如 .bag.zst / .zst / .zstd），
        先解壓成暫存 .bag 檔，回傳給 RealSense 使用的檔案路徑字串。
        如果本來就是 .bag，就直接回傳原路徑。
        """
        suffixes = {s.lower() for s in bag_path.suffixes}
        is_zstd_ext = (".zst" in suffixes) or (".zstd" in suffixes)

        def _looks_like_zstd(p: Path) -> bool:
            try:
                with p.open("rb") as f:
                    magic = f.read(4)
                # ZSTD magic header = 0x28 B5 2F FD
                return magic == b"\x28\xB5\x2F\xFD"
            except Exception:
                return False

        if is_zstd_ext or _looks_like_zstd(bag_path):
            self.logger.info(f"Detected zstd-compressed bag file: {bag_path}")

            # Decompressor 本身已經很快，這裡主要調整 I/O buffer 大小
            dctx = zstd.ZstdDecompressor()

            tmp = tempfile.NamedTemporaryFile(
                suffix=".bag", delete=False
            )
            tmp_path = Path(tmp.name)

            try:
                # 根據磁碟速度調整，這裡示範 8MB
                read_size = 8 * 1024 * 1024
                write_size = 8 * 1024 * 1024

                with bag_path.open("rb") as src, tmp:
                    dctx.copy_stream(src, tmp, read_size=read_size, write_size=write_size)

                self.logger.info(f"Decompressed bag to temporary file: {tmp_path}")
                self._temp_bag_path = tmp_path
                return str(tmp_path)
            except Exception as e:
                self.logger.error(f"Failed to decompress zstd bag file {bag_path}: {e}")
                try:
                    if tmp_path.exists():
                        tmp_path.unlink()
                except Exception:
                    pass
                raise
        else:
            return str(bag_path)

class OutputMixin:
    def _resolve_output_path(
        self, filename: Optional[str], default_name: str
    ) -> Path:
        """
        統一處理輸出檔案路徑：
        - 若未提供檔名則套用預設
        - 自動加上 prefix
        - 若未指定資料夾則寫入 output_dir
        """
        name = filename or default_name
        name = add_prefix_to_filename(name, self.prefix)

        path = Path(name)
        if not path.is_absolute() and str(path.parent) in ("", "."):
            path = self.output_dir / path
        return path
    
    def _save_results(
        self,
        camera_coordinate_list: np.ndarray,
        save_npy: bool = True,
        save_pickle: bool = True,
        output_npy_filename: Optional[str] = None,
        output_pickle_filename: Optional[str] = None,
    ) -> tuple[Path, Path]:
        """
        保存結果
        """
        default_npy = f"{Path(self.bag_file_path).stem}_pose.npy"
        default_pickle = f"{Path(self.bag_file_path).stem}_pose.pkl"

        npy_path = self._resolve_output_path(output_npy_filename, default_npy)
        pickle_path = self._resolve_output_path(
            output_pickle_filename, default_pickle
        )

        if len(camera_coordinate_list) > 0:
            first_frame = camera_coordinate_list[0]
            self.logger.info(f"Save data shape:")
            self.logger.info(f"  - Total frames: {len(camera_coordinate_list)}")
            self.logger.info(f"  - Shape: {camera_coordinate_list.shape}")
            self.logger.info(f"  - Each frame shape: {first_frame.shape}")
            self.logger.info(f"  - Data type: {first_frame.dtype}")

        if save_npy:
            np.save(npy_path, camera_coordinate_list)
            self.logger.info(f"Results saved to: {npy_path}")

        if save_pickle:
            with open(pickle_path, "wb") as f:
                pickle.dump(camera_coordinate_list, f)
            self.logger.info(f"Results saved to: {pickle_path}")

        return npy_path, pickle_path

