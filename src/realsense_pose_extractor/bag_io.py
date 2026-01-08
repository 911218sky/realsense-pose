"""RealSense bag 檔案 I/O 與結果輸出。"""

import pickle
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np
import zstandard as zstd

from utils import add_prefix_to_filename


class BagIOMixin:
    """Bag 檔案讀取，支援 zstd 壓縮檔自動解壓。"""

    def _prepare_bag_file(self, bag_path: Path) -> str:
        """準備 bag 檔案供 RealSense pipeline 使用。
        
        zstd 壓縮檔（.bag.zst / .zst / .zstd）會先解壓到暫存檔，
        一般 .bag 檔直接回傳原路徑。
        """
        suffixes = {s.lower() for s in bag_path.suffixes}
        is_zstd_ext = (".zst" in suffixes) or (".zstd" in suffixes)

        def _looks_like_zstd(p: Path) -> bool:
            """檢查檔案開頭 4 bytes 是否為 zstd magic number。"""
            try:
                with p.open("rb") as f:
                    magic = f.read(4)
                return magic == b"\x28\xB5\x2F\xFD"
            except Exception:
                return False

        if is_zstd_ext or _looks_like_zstd(bag_path):
            self.logger.info(f"偵測到 zstd 壓縮檔: {bag_path}")

            dctx = zstd.ZstdDecompressor()
            tmp = tempfile.NamedTemporaryFile(suffix=".bag", delete=False)
            tmp_path = Path(tmp.name)

            try:
                # 8MB buffer 在記憶體與 I/O 效率間取得平衡
                read_size = 8 * 1024 * 1024
                write_size = 8 * 1024 * 1024

                with bag_path.open("rb") as src, tmp:
                    dctx.copy_stream(src, tmp, read_size=read_size, write_size=write_size)

                self.logger.info(f"已解壓至暫存檔: {tmp_path}")
                self._temp_bag_path = tmp_path
                return str(tmp_path)
            except Exception as e:
                self.logger.error(f"解壓失敗 {bag_path}: {e}")
                try:
                    if tmp_path.exists():
                        tmp_path.unlink()
                except Exception:
                    pass
                raise
        else:
            return str(bag_path)


class OutputMixin:
    """分析結果輸出儲存。"""

    def _resolve_output_path(self, filename: Optional[str], default_name: str) -> Path:
        """解析輸出路徑，自動加上 prefix 並放到 output_dir。"""
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
        """儲存姿態座標為 npy / pickle 格式。"""
        default_npy = f"{Path(self.bag_file_path).stem}_pose.npy"
        default_pickle = f"{Path(self.bag_file_path).stem}_pose.pkl"

        npy_path = self._resolve_output_path(output_npy_filename, default_npy)
        pickle_path = self._resolve_output_path(output_pickle_filename, default_pickle)

        if len(camera_coordinate_list) > 0:
            first_frame = camera_coordinate_list[0]
            self.logger.info(f"儲存資料:")
            self.logger.info(f"  - 總幀數: {len(camera_coordinate_list)}")
            self.logger.info(f"  - Shape: {camera_coordinate_list.shape}")
            self.logger.info(f"  - 單幀 shape: {first_frame.shape}")
            self.logger.info(f"  - 資料型別: {first_frame.dtype}")

        if save_npy:
            np.save(npy_path, camera_coordinate_list)
            self.logger.info(f"已儲存: {npy_path}")

        if save_pickle:
            with open(pickle_path, "wb") as f:
                pickle.dump(camera_coordinate_list, f)
            self.logger.info(f"已儲存: {pickle_path}")

        return npy_path, pickle_path

