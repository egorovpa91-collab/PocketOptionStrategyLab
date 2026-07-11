from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class IndicatorValue:
    """Одно рассчитанное значение индикатора."""

    name: str
    value: float


@dataclass(frozen=True, slots=True)
class IndicatorSnapshot:
    """
    Неизменяемый набор индикаторов для одной закрытой свечи.

    Один снимок однозначно определяется комбинацией:
    asset + timeframe + timestamp.
    """

    asset: str
    timeframe: int
    timestamp: int
    values: tuple[IndicatorValue, ...]

    def get(self, name: str) -> float | None:
        """Возвращает значение индикатора по имени."""

        normalized_name = name.strip().lower()

        for item in self.values:
            if item.name.lower() == normalized_name:
                return item.value

        return None

    def as_dict(self) -> dict[str, float]:
        """Возвращает копию значений в виде словаря."""

        return {
            item.name: item.value
            for item in self.values
        }


@dataclass(frozen=True, slots=True)
class IndicatorEngineStats:
    """Снимок статистики Indicator Engine."""

    received_events: int
    created_snapshots: int
    duplicate_events: int
    not_ready_calculations: int
    calculation_errors: int
