from __future__ import annotations

from collections.abc import Iterator

from .base import Indicator


class IndicatorRegistry:
    """Хранит зарегистрированные индикаторы в стабильном порядке."""

    def __init__(self) -> None:
        """Создаёт пустой реестр."""

        self._indicators: dict[str, Indicator] = {}

    def register(self, indicator: Indicator) -> None:
        """
        Регистрирует индикатор.

        Повторное имя запрещено независимо от регистра символов.
        """

        indicator.validate()
        key = self._normalize_name(indicator.name)

        if key in self._indicators:
            raise ValueError(
                f"Индикатор уже зарегистрирован: {indicator.name}"
            )

        self._indicators[key] = indicator

    def unregister(self, name: str) -> None:
        """Удаляет индикатор по имени."""

        self._indicators.pop(
            self._normalize_name(name),
            None,
        )

    def get(self, name: str) -> Indicator | None:
        """Возвращает индикатор по имени."""

        return self._indicators.get(
            self._normalize_name(name)
        )

    def __iter__(self) -> Iterator[Indicator]:
        """Перебирает индикаторы в порядке регистрации."""

        return iter(self._indicators.values())

    def __len__(self) -> int:
        """Возвращает число зарегистрированных индикаторов."""

        return len(self._indicators)

    @staticmethod
    def _normalize_name(name: str) -> str:
        """Нормализует имя для поиска в реестре."""

        return name.strip().lower()
