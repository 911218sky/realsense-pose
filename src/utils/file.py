import logging
from pathlib import Path
from typing import Optional, Union

def ensure_dir(path: str):
    """
    確保指定的目錄存在，若不存在則遞迴建立。

    參數:
        path (str): 要確保存在的目錄路徑（可以是相對或絕對路徑）。

    回傳:
        pathlib.Path: 對應於該目錄的 Path 物件（方便後續操作）。
    """
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p

def ensure_file(path: str,
                content: Optional[str] = None,
                overwrite: bool = False,
                encoding: str = "utf-8") -> Path:
    """
    確保指定檔案存在（若不存在就建立）。選項：
      - content: 若提供，會把這個字串寫入檔案（建立或覆蓋時使用）。
      - overwrite: 若 True，且檔案已存在，會以 content 覆蓋（若 content is None，會清空檔案）。
                   若 False，且檔案已存在，則保留原檔不做變動。
      - encoding: 檔案編碼（預設 utf-8）。

    回傳:
      pathlib.Path: 指向該檔案的 Path 物件。

    例外:
      - 若 path 指向一個已存在的目錄，會丟出 IsADirectoryError。
      - 若沒有權限建立或寫入檔案，會丟出 PermissionError（包含底層錯誤訊息）。
    """
    p = Path(path)

    if p.exists() and p.is_dir():
        raise IsADirectoryError(f"Path '{p}' is a directory, not a file.")

    # 確保 parent 目錄存在（若 parent 為空則不做）
    if p.parent:
        p.parent.mkdir(parents=True, exist_ok=True)

    try:
        if p.exists():
            if overwrite:
                # 覆蓋（若 content 為 None，就清空檔案）
                with p.open("w", encoding=encoding) as f:
                    if content is not None:
                        f.write(content)
            # 若不覆蓋，直接返回現有檔案
        else:
            # 檔案不存在，建立並根據 content 寫入（若 content 為 None 則建立空檔）
            with p.open("w", encoding=encoding) as f:
                if content is not None:
                    f.write(content)
        return p
    except PermissionError as e:
        # 把更清楚的錯誤訊息往上傳
        raise PermissionError(f"Permission denied creating/writing file '{p}': {e}") from e

def add_prefix_to_filename(
    path_str: Optional[Union[str, Path]] = None,
    prefix: Optional[str] = None,
    mode: str = "preserve_full",
) -> str:
    """
    加 prefix 到檔名（不改變 extension）。
    If prefix is None or empty -> return original path as Path.

    mode:
      - "preserve_full": 保留完整 parent 路徑 (data/a/b/file -> data/a/b/tag_file)
      - "no_dir"       : 不保留任何資料夾，僅回傳檔名 (data/a/b/file -> tag_file)
    """

    if path_str is None:
        return None

    p = Path(path_str)

    if prefix is None or prefix == "":
        return str(p)

    name = p.name

    # 避免重複加上相同 prefix
    if name.startswith(prefix):
        prefixed_name = name
    else:
        prefixed_name = f"{prefix}_{name}"

    if mode == "preserve_full":
        return str(p.parent / prefixed_name)
    elif mode == "no_dir":
        return str(Path(prefixed_name))
    else:
        raise ValueError("mode must be one of: preserve_full, no_dir")

def setup_logger(name: str, log_file: Optional[str] = None, level: int = logging.INFO) -> logging.Logger:
    """建立 logger，輸出到終端機，若有指定 log_file 則同時寫檔。"""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(level)
    fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s", "%Y-%m-%d %H:%M:%S")

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    if log_file:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    logger.propagate = False
    return logger