import os

def env_bool(name: str, default: bool = False) -> bool:
    """
    Parse boolean env vars robustly.

    Notes:
    - bool("0") is True in Python, so we must not use `bool(os.getenv(...))`.
    - Accept common truthy/falsy strings.
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
    raw = os.getenv(name, "")
    items = [x.strip() for x in raw.split(",")]
    return [x for x in items if x]