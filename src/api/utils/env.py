"""環境變數工具。"""

import os


def env_bool(name: str, default: bool = False) -> bool:
    """解析布林環境變數。
    
    Python 的 bool("0") 是 True，所以不能直接用 bool(os.getenv(...))。
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    v = raw.strip().lower()
    if v in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if v in {"0", "false", "f", "no", "n", "off", ""}:
        return False
    return default


def env_csv(name: str) -> list[str]:
    """解析逗號分隔的環境變數為 list。"""
    raw = os.getenv(name, "")
    items = [x.strip() for x in raw.split(",")]
    return [x for x in items if x]