from typing import Optional
import logging

def setup_logger(
    name: str,
    log_file: Optional[str] = None,
    level: int = logging.INFO,
    use_rich: bool = True,
    rich_tracebacks: bool = True,
) -> logging.Logger:
    """
    建立 logger：
      - 優先使用 rich.logging.RichHandler（若安裝且 use_rich=True）
      - 若沒有 rich 或發生錯誤，自動退回到純文字 StreamHandler（原本行為）
      - 若提供 log_file，會同時加上 non-colored FileHandler (UTF-8)
      - 若 logger 已有 handlers，直接回傳（避免重複輸出）
    Args:
        name: logger 名稱，通常傳 __name__
        log_file: 若提供，會額外寫入純文字檔（不含顏色碼）
        level: logging 等級
        use_rich: 是否嘗試使用 rich（預設 True）
        rich_tracebacks: 傳給 RichHandler 的 rich_tracebacks 參數
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(level)

    # file formatter (plain text)
    file_fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s", "%Y-%m-%d %H:%M:%S")

    backend = "plain"
    if use_rich:
        try:
            from rich.logging import RichHandler
            rh = RichHandler(markup=True, rich_tracebacks=rich_tracebacks)
            rh.setLevel(level)
            logger.addHandler(rh)
            backend = "rich"
        except Exception:
            backend = "plain"

    if backend == "plain":
        stream_fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s", "%Y-%m-%d %H:%M:%S")
        sh = logging.StreamHandler()
        sh.setLevel(level)
        sh.setFormatter(stream_fmt)
        logger.addHandler(sh)

    # always add a plain file handler if requested (no color codes)
    if log_file:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(level)
        fh.setFormatter(file_fmt)
        logger.addHandler(fh)

    logger.propagate = False
    logger.debug(f"Logger {name} initialized with backend={backend}")
    return logger

__all__ = ["setup_logger"]