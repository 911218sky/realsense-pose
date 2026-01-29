"""
bag_path 解析工具（給 Docker 容器內的後端使用）

需求背景：
- 前端可能傳 Windows 路徑（例如 `C:/aa/bb/cc/1.bag` / `D:\\aa\\bb\\cc\\1.bag`）
- 但後端在 Linux Docker 容器內看不到 `C:`/`D:` 這種磁碟機路徑
- 解法是：把 host 的資料夾（例如 `./bb`）mount 到容器 `/app/dataset`，
  然後用 `HOST_DATASET_DIR` 的最後一層資料夾名（basename）作為「錨點」去推導相對路徑：

  例：
  - bag_path:         C:/aa/bb/cc/1.bag
  - HOST_DATASET_DIR: ./bb              (basename = "bb")
  - 容器內 mount:     /app/dataset  <-- (docker-compose.yml)
  -> 推導：           /app/dataset/cc/1.bag
"""
import re
from pathlib import Path
from typing import Iterable, Optional

from utils.file import is_bag_file

def resolve_bag_path(
    bag_path: str,
    *,
    host_dataset_dir: Optional[str],
    dataset_mount_dir: Path = Path("/app/dataset"),
    search_dirs: Optional[Iterable[Path]] = None,
) -> Path:
    """
    把「前端傳入的 bag_path」解析成「容器內實際存在的檔案路徑」。
    """
    bag_path = (bag_path or "").strip()
    if not bag_path:
        raise ValueError("bag_path is empty")

    if not is_bag_file(bag_path):
        raise ValueError("only .bag files are supported")

    # 最直覺：先看使用者傳入的路徑在「容器內」是否真的存在
    raw = Path(bag_path)
    if raw.is_file():
        return raw

    # 若輸入是相對路徑（例如 API list 回傳的 bag_id: "subdir/1.bag"），
    # 嘗試在允許的 base dirs 下拼接尋找（避免任意讀取檔案）
    if search_dirs and not raw.is_absolute() and not re.match(r"^[a-zA-Z]:[\\/]", bag_path):
        for base in search_dirs:
            try:
                candidate = (Path(base) / bag_path).resolve()
                base_resolved = Path(base).resolve()
            except Exception:
                continue

            # 路徑穿越保護：candidate 必須位於 base 之下
            if base_resolved not in candidate.parents and candidate != base_resolved:
                continue

            if candidate.is_file():
                return candidate

    # 若有設定 HOST_DATASET_DIR 且輸入是 Windows 路徑，嘗試映射到 /app/dataset/...
    if host_dataset_dir and re.match(r"^[a-zA-Z]:[\\/]", bag_path):
        mapped = _map_windows_path_to_dataset_mount(
            bag_path,
            host_dataset_dir=host_dataset_dir,
            dataset_mount_dir=dataset_mount_dir,
        )
        if mapped and mapped.is_file():
            return mapped
    raise FileNotFoundError(
        f"bag file not found: {bag_path}. "
        f"Tried: {raw}"
    )

def _map_windows_path_to_dataset_mount(
    bag_path: str,
    *,
    host_dataset_dir: str,
    dataset_mount_dir: Path,
) -> Optional[Path]:
    """
    Windows 路徑 -> 容器 dataset mount 的簡單映射。

    範例：
    - bag_path:         C:/aa/bb/cc/1.bag
    - HOST_DATASET_DIR: ./bb   (marker = "bb")
    -> /app/dataset/cc/1.bag

    注意：
    - 這個映射「只」靠 marker（basename）找切點，所以如果整條路徑裡有重複資料夾名，
      會以第一次出現的位置為準。
    """
    marker = Path(host_dataset_dir).name
    if not marker:
        return None

    # 正規化：把反斜線轉成 /，並移除磁碟機前綴
    s = bag_path.strip().replace("\\", "/")
    s = re.sub(r"^[a-zA-Z]:", "", s)  # "C:/aa/bb/cc/1.bag" -> "/aa/bb/cc/1.bag"
    parts = [p for p in s.split("/") if p]
    if not parts:
        return None

    try:
        idx = parts.index(marker)
    except ValueError:
        # 找不到 marker（例如 HOST_DATASET_DIR=./bb 但路徑中沒有 bb）
        return None

    rel_parts = parts[idx + 1 :]
    if not rel_parts:
        return None

    return Path(dataset_mount_dir, *rel_parts)


