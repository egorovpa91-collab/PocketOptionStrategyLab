from dataclasses import dataclass


@dataclass(slots=True)
class Candle:
    """Одна рыночная свеча."""

    asset: str
    time: int

    open: float
    high: float
    low: float
    close: float


@dataclass(slots=True)
class MarketData:
    """Результат разбора данных Pocket Option."""

    asset: str
    source: str

    candles: list[Candle]