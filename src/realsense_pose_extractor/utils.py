"""檔案與目錄工具函式。"""

from pathlib import Path
from typing import Optional


def ensure_dir(path: str) -> Path:
    """確保目錄存在，不存在則遞迴建立。"""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p

def ensure_file(
    path: str,
    content: Optional[str] = None,
    overwrite: bool = False,
    encoding: str = "utf-8",
) -> Path:
    """確保檔案存在，不存在則建立。
    
    Args:
        path: 檔案路徑
        content: 寫入內容，None 則建立空檔
        overwrite: True 則覆蓋既有檔案
        encoding: 編碼，預設 utf-8
        
    Returns:
        檔案 Path 物件
        
    Raises:
        IsADirectoryError: path 是目錄
        PermissionError: 無權限建立或寫入
    """
    p = Path(path)

    if p.exists() and p.is_dir():
        raise IsADirectoryError(f"Path '{p}' is a directory, not a file.")

    if p.parent:
        p.parent.mkdir(parents=True, exist_ok=True)

    try:
        if p.exists():
            if overwrite:
                with p.open("w", encoding=encoding) as f:
                    if content is not None:
                        f.write(content)
        else:
            with p.open("w", encoding=encoding) as f:
                if content is not None:
                    f.write(content)
        return p
    except PermissionError as e:
        raise PermissionError(f"Permission denied creating/writing file '{p}': {e}") from e