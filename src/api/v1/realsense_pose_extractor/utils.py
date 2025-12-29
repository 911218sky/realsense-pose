import asyncio
import hashlib
from pathlib import Path

async def compute_file_hash(file_path: Path) -> str:
    """
    Async wrapper to offload hashing to a thread pool.
    """
    return await asyncio.to_thread(_hash_file_fast, file_path)

def _hash_file_fast(
    file_path: Path,
    *,
    chunk_size: int = 256 * 1024,
    max_chunks: int = 8,
) -> str:
    """
    計算「近似」的檔案雜湊以提高速度，不一定要掃描完整 16G 檔案。

    策略：
    - 小檔案：仍然完整掃描，確保準確。
    - 大檔案：只抽樣幾個固定位置的區塊（頭、中間數點、尾），
      大幅減少 I/O 讀取量。
    """
    hasher = hashlib.blake2b(digest_size=32)
    file_size = file_path.stat().st_size

    # 先把檔案大小編入雜湊，避免不同大小但內容相似的檔案產生同樣結果
    hasher.update(str(file_size).encode("utf-8"))

    # 如果檔案不大，就還是用原本「全檔案掃描」方式
    full_scan_limit = chunk_size * max_chunks
    if file_size <= full_scan_limit:
        with file_path.open("rb") as f:
            for chunk in iter(lambda: f.read(chunk_size), b""):
                if not chunk:
                    break
                hasher.update(chunk)
        return hasher.hexdigest()

    # 大檔案改為抽樣多個位置的區塊
    # 固定的比例位置，確保同一檔案每次得到相同雜湊
    positions = [
        0,  # 開頭
        file_size // 4,
        file_size // 2,
        (file_size * 3) // 4,
        max(file_size - chunk_size, 0),  # 接近結尾
    ]

    with file_path.open("rb") as f:
        for pos in positions:
            if pos >= file_size:
                continue
            f.seek(pos)
            data = f.read(chunk_size)
            if not data:
                continue
            hasher.update(data)

    return hasher.hexdigest()