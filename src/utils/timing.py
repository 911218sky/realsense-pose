import time
from collections.abc import Callable
from typing import Any

from logger import setup_logger

__all__ = ["time_it"]

logger = setup_logger("utils.timing")

def format(ns: int) -> str:
    """
    將整數奈秒格式化到毫秒（3 位小數）顯示，行為類似你原本的 format_time：
    - < 60s: "SS.mmm s"  (e.g. "02.345s")
    - >= 60s and <3600s: "M m SS.mmm s" (e.g. "1m 05.123s")
    - >= 3600s: "Hh Mm SS.mmm s" (e.g. "1h 02m 03.456s")
    輸入: ns (int) 奈秒
    """
    ms = ns / 1_000_000.0
    return f"{ms:0.3f} ms"

def time_it(func: Callable[..., Any], time_it_label: str | None = None, *args: Any, **kwargs: Any) -> Any:
    """
    使用 time.perf_counter_ns() 做高解析度（整數奈秒）計時。
    - func: 可呼叫物件
    - label: 顯示任務名稱（預設 func.__name__）
    - 回傳 func 的結果（如果有）
    """
    name = time_it_label or getattr(func, "__name__", str(func))
    start_ns = time.perf_counter_ns()
    try:
        result = func(*args, **kwargs)
    except Exception as e:
        logger.error(f"{name:<48s}  ❌  {e}")
        return None
    elapsed_ns = time.perf_counter_ns() - start_ns
    logger.info(f"{name:<48s}  ✅  {format(elapsed_ns)}")
    return result