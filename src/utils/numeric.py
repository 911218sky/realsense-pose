from fractions import Fraction

__all__ = ["to_fraction"]

def to_fraction(x: str | float | int) -> float:
    """
    把 '20%' 或 '0.2' 或 0.2 或 '1/15' 轉成 fraction (0..1) 的 float。
    若無法解析會丟 ValueError。
    """
    if isinstance(x, (float, int)):
        return float(x)
    # x is str
    xs = x.strip()
    if xs == "":
        raise ValueError("空字串無法轉換為 fraction")

    # 百分比: "20%" -> 0.2
    if xs.endswith('%'):
        try:
            return float(Fraction(xs[:-1])) / 100.0
        except Exception as e:
            raise ValueError(f"無法解析百分比字串 {x!r}: {e}")

    # 分數形式: "1/15" 或 " 3 / 4 "
    if '/' in xs:
        try:
            # Fraction 會處理像 "1/15"、" 3/4 "、"0.25" 等
            return float(Fraction(xs))
        except Exception as e:
            raise ValueError(f"無法解析分數字串 {x!r}: {e}")

    # 一般數字字串（整數或浮點）: "0.2", "1", "3.14"
    try:
        return float(xs)
    except Exception as e:
        raise ValueError(f"無法解析數字字串 {x!r}: {e}")