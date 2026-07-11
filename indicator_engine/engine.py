from __future__ import annotations

from candle_manager import CandleManager
from scanner.events import ClosedCandleEvent

from .models import (
    IndicatorEngineStats,
    IndicatorSnapshot,
    IndicatorValue,
)
from .registry import IndicatorRegistry


class IndicatorEngine:
    """
    Рассчитывает зарегистрированные индикаторы по закрытым свечам.

    Engine не получает тики и формирующиеся свечи. Источник истории —
    только Candle Manager, уже обработавший new_closed_candle.
    """

    def __init__(
        self,
        candle_manager: CandleManager,
        registry: IndicatorRegistry,
    ) -> None:
        """Создаёт Indicator Engine."""

        self._candle_manager = candle_manager
        self._registry = registry

        self._snapshots: dict[
            tuple[str, int, int],
            IndicatorSnapshot,
        ] = {}

        self._received_events = 0
        self._created_snapshots = 0
        self._duplicate_events = 0
        self._not_ready_calculations = 0
        self._calculation_errors = 0

    async def handle_new_closed_candle(
        self,
        event: ClosedCandleEvent,
    ) -> None:
        """Обрабатывает одну подтверждённую закрытую свечу."""

        if event.name != "new_closed_candle":
            return

        self._received_events += 1

        snapshot_key = (
            self._normalize_asset(event.asset),
            event.timeframe,
            event.candle.time,
        )

        if snapshot_key in self._snapshots:
            self._duplicate_events += 1
            return

        candles = self._candle_manager.get_closed_candles(
            asset=event.asset,
            timeframe=event.timeframe,
        )
        values: list[IndicatorValue] = []

        for indicator in self._registry:
            if len(candles) < indicator.required_candles:
                self._not_ready_calculations += 1
                continue

            try:
                value = indicator.calculate(candles)
            except (ArithmeticError, ValueError) as error:
                self._calculation_errors += 1
                print(
                    "⚠ Ошибка индикатора | "
                    f"{indicator.name} | "
                    f"{event.asset} | "
                    f"timestamp={event.candle.time} | "
                    f"{error}"
                )
                continue

            values.append(
                IndicatorValue(
                    name=indicator.name,
                    value=float(value),
                )
            )

        snapshot = IndicatorSnapshot(
            asset=event.asset,
            timeframe=event.timeframe,
            timestamp=event.candle.time,
            values=tuple(values),
        )
        self._snapshots[snapshot_key] = snapshot
        self._created_snapshots += 1

        rendered_values = ", ".join(
            f"{item.name}={item.value:.8f}"
            for item in snapshot.values
        )
        if not rendered_values:
            rendered_values = "нет готовых индикаторов"

        print(
            "✓ Indicator Snapshot | "
            f"{snapshot.asset} | "
            f"M{snapshot.timeframe // 60} | "
            f"timestamp={snapshot.timestamp} | "
            f"{rendered_values}"
        )

    def get_snapshot(
        self,
        asset: str,
        timeframe: int,
        timestamp: int,
    ) -> IndicatorSnapshot | None:
        """Возвращает снимок конкретной закрытой свечи."""

        key = (
            self._normalize_asset(asset),
            timeframe,
            timestamp,
        )
        return self._snapshots.get(key)

    def get_latest_snapshot(
        self,
        asset: str,
        timeframe: int = 60,
    ) -> IndicatorSnapshot | None:
        """Возвращает последний снимок серии."""

        normalized_asset = self._normalize_asset(asset)

        matching = [
            snapshot
            for (stored_asset, stored_timeframe, _), snapshot
            in self._snapshots.items()
            if (
                stored_asset == normalized_asset
                and stored_timeframe == timeframe
            )
        ]

        if not matching:
            return None

        return max(
            matching,
            key=lambda snapshot: snapshot.timestamp,
        )

    def get_stats(self) -> IndicatorEngineStats:
        """Возвращает текущую статистику Engine."""

        return IndicatorEngineStats(
            received_events=self._received_events,
            created_snapshots=self._created_snapshots,
            duplicate_events=self._duplicate_events,
            not_ready_calculations=self._not_ready_calculations,
            calculation_errors=self._calculation_errors,
        )

    def print_summary(self) -> None:
        """Выводит итоговую статистику Indicator Engine."""

        stats = self.get_stats()

        print(
            "✓ Indicator Engine | "
            f"индикаторов: {len(self._registry)} | "
            f"событий: {stats.received_events} | "
            f"снимков: {stats.created_snapshots} | "
            f"дублей: {stats.duplicate_events} | "
            f"не готово: {stats.not_ready_calculations} | "
            f"ошибок: {stats.calculation_errors}"
        )

    @staticmethod
    def _normalize_asset(asset: str) -> str:
        """Приводит имя актива к единому виду."""

        return (
            asset
            .strip()
            .lower()
            .replace(" ", "")
        )
