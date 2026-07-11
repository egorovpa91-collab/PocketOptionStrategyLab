from __future__ import annotations

from collections.abc import Sequence

from scanner.models import Candle

from ..base import Indicator


class EMAIndicator(Indicator):
    """
    Экспоненциальная скользящая средняя по цене закрытия.

    Первая EMA инициализируется как SMA первых ``period`` закрытых свечей.
    Далее используется стандартная рекурсивная формула EMA.
    """

    def __init__(self, period: int) -> None:
        """
        Создаёт EMA с указанным периодом.

        Args:
            period: Число закрытых свечей в периоде EMA.
        """

        if period <= 1:
            raise ValueError("Период EMA должен быть больше единицы")

        self._period = period
        self._multiplier = 2.0 / (period + 1.0)

    @property
    def name(self) -> str:
        """Возвращает уникальное имя индикатора."""

        return f"ema_{self._period}"

    @property
    def required_candles(self) -> int:
        """Возвращает минимальную историю для первой EMA."""

        return self._period

    @property
    def period(self) -> int:
        """Возвращает период EMA."""

        return self._period

    def calculate(
        self,
        candles: Sequence[Candle],
    ) -> float:
        """
        Рассчитывает последнее значение EMA по доступной истории.

        Args:
            candles: Закрытые свечи в хронологическом порядке.

        Returns:
            Последнее значение EMA.
        """

        if len(candles) < self._period:
            raise ValueError(
                f"{self.name}: требуется минимум "
                f"{self._period} свечей, получено {len(candles)}"
            )

        closes = [
            float(candle.close)
            for candle in candles
        ]

        ema = sum(closes[:self._period]) / self._period

        for close_price in closes[self._period:]:
            ema = (
                close_price * self._multiplier
                + ema * (1.0 - self._multiplier)
            )

        return ema
