"""RealSense 姿態提取模組。

使用延遲載入避免在不需要時載入重型依賴。
"""

from typing import TYPE_CHECKING

# 輕量級模組可以直接導入
from .anchor_detector import (
    AnchorConfig,
    AnchorDetectorMixin,
    load_anchor_config,
    save_anchor_config,
)

if TYPE_CHECKING:
    from .processor import PoseProcessor
    from .cli import main as processor_cli

__all__ = [
    "PoseProcessor",
    "processor_cli",
    "AnchorConfig",
    "AnchorDetectorMixin",
    "load_anchor_config",
    "save_anchor_config",
]


def __getattr__(name: str):
    """延遲載入重型模組。"""
    if name == "PoseProcessor":
        from .processor import PoseProcessor
        return PoseProcessor
    if name == "processor_cli":
        from .cli import main
        return main
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
