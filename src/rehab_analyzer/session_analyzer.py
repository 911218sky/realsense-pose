from .gait_analyzer import GaitAnalyzer
from .fft_analyzer import FftAnalyzer

class RehabilitationSessionAnalyzer(
    GaitAnalyzer,
    FftAnalyzer,
):
    """整合所有分析功能的單一入口類別。"""
    def __init__(self, npy_path: str):
        super().__init__(npy_path)

