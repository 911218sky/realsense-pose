"""cachedmethod 的 cache key 工具。"""

from typing import Any

import numpy as np
from cachetools.keys import hashkey


def method_key(prefix: str, *args: Any, **kwargs: Any) -> tuple:
    """產生 cachedmethod 用的 key。

    為了避免 list / ndarray 這種不可雜湊物件，這裡會把它們濾掉，
    只用純量與可雜湊型別組成 key。
    """
    filtered_args = []
    for arg in args:
        if not isinstance(arg, (list, np.ndarray)):
            filtered_args.append(arg)

    filtered_kwargs = {}
    for key, value in kwargs.items():
        if not isinstance(value, (list, np.ndarray)):
            filtered_kwargs[key] = value

    return (prefix,) + hashkey(*filtered_args, **filtered_kwargs)
