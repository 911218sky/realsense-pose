"""Utility functions for the project."""

import sys
from pathlib import Path

from .file import ensure_dir, ensure_file, add_prefix_to_filename

# Optional: FFmpegPipe pulls in heavier deps (e.g., matplotlib). Make import best-effort
# so light-weight utilities (like npy calibration) can still be used standalone.
try:
  from .FFmpegPipe import FFmpegPipe
except Exception:  # pragma: no cover
  FFmpegPipe = None


def ensure_src_in_path() -> Path:
    """確保 src 目錄在 sys.path 中，方便測試和範例腳本使用。
    
    這個函數會自動找到專案的 src 目錄並將其添加到 sys.path 中，
    使得可以使用絕對 import（如 `from rehab_analyzer import ...`）。
    
    Returns:
        Path: src 目錄的絕對路徑
    
    Example:
        >>> from utils import ensure_src_in_path
        >>> ensure_src_in_path()
        >>> from rehab_analyzer import RehabilitationSessionAnalyzer
    
    Note:
        - 這個函數是冪等的（idempotent），多次調用不會重複添加路徑
        - 主要用於測試腳本、範例腳本和子進程中
        - API 服務器通常不需要調用此函數（uvicorn 會自動處理）
    """
    # 從當前文件位置向上找到 src 目錄
    # __file__ 是 src/utils/__init__.py
    # parent 是 src/utils
    # parent.parent 是 src
    src_dir = Path(__file__).resolve().parent.parent
    
    # 只在不存在時才添加，避免重複
    src_dir_str = str(src_dir)
    if src_dir_str not in sys.path:
        sys.path.insert(0, src_dir_str)
    
    return src_dir


__all__ = [
  # path setup
  "ensure_src_in_path",
  
  # ffmpeg
  "FFmpegPipe",

  # file
  "ensure_dir",
  "ensure_file",
  "add_prefix_to_filename",
]