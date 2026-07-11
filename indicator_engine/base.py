from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from scanner.models import Candle


class Indicator(ABC):
    """Базовый контракт одного независимого индикатора."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Возвращает уникальное имя индикатора."""

    @property
    @abstractmethod
    def required_candles(self) -> int:
        """Возвращает минимальное число закрытых свечей для расчёта."""

    @abstractmethod
    def calculate(
        self,
        candles: Sequence[Candle],
    ) -> float:
        """
        Рассчитывает значение по закрытым свечам.

        Последний элемент последовательности является текущей
        подтверждённой закрытой свечой.
        """

    def validate(self) -> None:
        """Проверяет корректность метаданных индикатора."""

        if not self.name.strip():
            raise ValueError("Имя индикатора не может быть пустым")

        if self.required_candles <= 0:
            raise ValueError(
                f"{self.name}: required_candles должен быть больше нуля"
            )
