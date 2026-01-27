"""
rehab_analyzer package

IMPORTANT:
Keep this module lightweight and free of heavy optional imports (e.g. matplotlib/cv2),
so that importing `rehab_analyzer.constants` or other submodules will not pull in
visualizer dependencies in minimal Docker images (e.g. Alpine).
"""

from .rehab_analyzer import RehabilitationSessionAnalyzer
from . import constants

# Note: analyzer_cli and RehabSummaryVisualizer are lazy-loaded via __getattr__
__all__ = ["RehabilitationSessionAnalyzer", "constants"]


def __getattr__(name: str):
    # PEP 562: lazy attributes to avoid importing heavy deps unless explicitly requested.
    if name == "analyzer_cli":
        from .cli import main as analyzer_cli

        return analyzer_cli
    if name == "RehabSummaryVisualizer":
        from .visualizer import RehabSummaryVisualizer

        return RehabSummaryVisualizer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")