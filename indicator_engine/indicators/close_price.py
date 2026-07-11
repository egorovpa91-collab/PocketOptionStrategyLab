from __future__ import annotations

from collections.abc import Sequence

from scanner.models import Candle

from ..base import Indicator


class ClosePriceIndicator(Indicator):
    """
    Технический индикатор для проверки всей цепочки Engine.

    Он возвращает цену закрытия последней закрытой свечи и не является
    торговым индикатором.
    """

    @property
    def name(self) -> str:
        """Возвращает имя тестового индикатора."""

        return "close_price"

    @property
    def required_candles(self) -> int:
        """Для Close достаточно одной закрытой свечи."""

        return 1

    def calculate(
        self,
        candles: Sequence[Candle],
    ) -> float:
        """Возвращает Close последней свечи."""

        if not candles:
            raise ValueError(
                "ClosePriceIndicator получил пустую историю"
            )

        return float(candles[-1].close)
