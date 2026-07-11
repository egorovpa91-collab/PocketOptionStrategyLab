from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass

from database.repository import get_candles_until
from scanner.events import ClosedCandleEvent
from scanner.models import Candle


@dataclass(frozen=True, slots=True)
class CandleManagerStats:
    """Снимок статистики Candle Manager."""

    initialized_series: int
    received_events: int
    added_candles: int
    updated_candles: int
    ignored_events: int
    detected_gaps: int


class CandleManager:
    """
    Хранит последние закрытые свечи отдельно для каждой пары.

    Candle Manager является потребителем события ``new_closed_candle``.
    При первом событии по серии он восстанавливает историю из SQLite до
    timestamp подтверждённой закрытой свечи. Формирующаяся свеча в память
    менеджера не попадает.
    """

    def __init__(self, history_limit: int = 500) -> None:
        """
        Создаёт менеджер закрытых свечей.

        Args:
            history_limit: Максимальное число закрытых свечей в памяти
                для одной комбинации asset + timeframe.
        """

        if history_limit <= 0:
            raise ValueError("history_limit должен быть больше нуля")

        self.history_limit = history_limit
        self._series: dict[
            tuple[str, int],
            deque[Candle],
        ] = defaultdict(
            lambda: deque(maxlen=self.history_limit)
        )
        self._initialized_series: set[tuple[str, int]] = set()

        self._received_events = 0
        self._added_candles = 0
        self._updated_candles = 0
        self._ignored_events = 0
        self._detected_gaps = 0

    async def handle_new_closed_candle(
        self,
        event: ClosedCandleEvent,
    ) -> None:
        """
        Принимает одну подтверждённую закрытую свечу.

        Метод предназначен для прямой подписки на
        ``Scanner.events.subscribe_new_closed_candle``.
        """

        if event.name != "new_closed_candle":
            self._ignored_events += 1
            return

        self._received_events += 1

        key = (
            self._normalize_asset(event.asset),
            event.timeframe,
        )

        if key not in self._initialized_series:
            self._restore_series(
                asset=event.asset,
                timeframe=event.timeframe,
                closed_timestamp=event.candle.time,
            )

        action = self._upsert_closed_candle(
            key=key,
            candle=event.candle,
        )

        if action == "ADDED":
            self._added_candles += 1
        elif action == "UPDATED":
            self._updated_candles += 1
        else:
            self._ignored_events += 1

    def get_closed_candles(
        self,
        asset: str,
        timeframe: int = 60,
        limit: int | None = None,
    ) -> tuple[Candle, ...]:
        """
        Возвращает неизменяемый снимок закрытых свечей.

        Args:
            asset: Внутреннее имя актива Pocket Option.
            timeframe: Таймфрейм в секундах.
            limit: Число последних свечей. ``None`` возвращает весь кэш.
        """

        if limit is not None and limit <= 0:
            raise ValueError("limit должен быть больше нуля")

        key = (
            self._normalize_asset(asset),
            timeframe,
        )
        candles = tuple(self._series.get(key, ()))

        if limit is None:
            return candles

        return candles[-limit:]

    def get_latest_closed_candle(
        self,
        asset: str,
        timeframe: int = 60,
    ) -> Candle | None:
        """Возвращает последнюю закрытую свечу серии."""

        candles = self.get_closed_candles(
            asset=asset,
            timeframe=timeframe,
            limit=1,
        )

        return candles[0] if candles else None

    def is_ready(
        self,
        asset: str,
        timeframe: int = 60,
        required_candles: int = 1,
    ) -> bool:
        """
        Проверяет достаточность истории для расчёта индикатора.

        Например, EMA200 сможет запросить ``required_candles=200``.
        """

        if required_candles <= 0:
            raise ValueError(
                "required_candles должен быть больше нуля"
            )

        key = (
            self._normalize_asset(asset),
            timeframe,
        )

        return len(self._series.get(key, ())) >= required_candles

    def get_stats(self) -> CandleManagerStats:
        """Возвращает текущую статистику менеджера."""

        return CandleManagerStats(
            initialized_series=len(self._initialized_series),
            received_events=self._received_events,
            added_candles=self._added_candles,
            updated_candles=self._updated_candles,
            ignored_events=self._ignored_events,
            detected_gaps=self._detected_gaps,
        )

    def print_summary(self) -> None:
        """Выводит итоговую статистику Candle Manager."""

        stats = self.get_stats()

        print(
            "✓ Candle Manager | "
            f"серий: {stats.initialized_series} | "
            f"событий: {stats.received_events} | "
            f"добавлено: {stats.added_candles} | "
            f"обновлено: {stats.updated_candles} | "
            f"пропущено: {stats.ignored_events} | "
            f"разрывов: {stats.detected_gaps}"
        )

    def _restore_series(
        self,
        asset: str,
        timeframe: int,
        closed_timestamp: int,
    ) -> None:
        """Восстанавливает закрытую историю серии из SQLite."""

        key = (
            self._normalize_asset(asset),
            timeframe,
        )
        database_candles = get_candles_until(
            asset=asset,
            timeframe=timeframe,
            timestamp=closed_timestamp,
            limit=self.history_limit,
        )

        cache = self._series[key]
        cache.clear()

        for database_candle in database_candles:
            cache.append(
                Candle(
                    asset=database_candle.asset,
                    time=database_candle.timestamp,
                    open=database_candle.open,
                    high=database_candle.high,
                    low=database_candle.low,
                    close=database_candle.close,
                )
            )

        self._initialized_series.add(key)

        print(
            "✓ Candle Manager инициализирован | "
            f"{asset} | "
            f"M{timeframe // 60} | "
            f"закрытых свечей: {len(cache)}"
        )

    def _upsert_closed_candle(
        self,
        key: tuple[str, int],
        candle: Candle,
    ) -> str:
        """
        Добавляет закрытую свечу или заменяет запись того же timestamp.

        Returns:
            ``ADDED``, ``UPDATED`` или ``UNCHANGED``.
        """

        cache = self._series[key]

        for index, existing in enumerate(cache):
            if existing.time != candle.time:
                continue

            if existing == candle:
                return "UNCHANGED"

            cache[index] = candle
            return "UPDATED"

        if cache:
            last_candle = cache[-1]
            timeframe = key[1]
            delta = candle.time - last_candle.time

            if delta > timeframe:
                missing_intervals = (delta // timeframe) - 1
                self._detected_gaps += missing_intervals

                print(
                    "⚠ Разрыв закрытых свечей | "
                    f"{candle.asset} | "
                    f"пропущено интервалов: {missing_intervals} | "
                    f"после timestamp={last_candle.time}"
                )

            if candle.time < last_candle.time:
                self._insert_historical_candle(
                    cache=cache,
                    candle=candle,
                )
                return "ADDED"

        cache.append(candle)
        return "ADDED"

    @staticmethod
    def _insert_historical_candle(
        cache: deque[Candle],
        candle: Candle,
    ) -> None:
        """Вставляет запоздавшую свечу с сохранением хронологии."""

        candles = list(cache)
        candles.append(candle)
        candles.sort(key=lambda item: item.time)

        cache.clear()
        cache.extend(candles)

    @staticmethod
    def _normalize_asset(asset: str) -> str:
        """Приводит имя актива к единому виду."""

        return (
            asset
            .strip()
            .lower()
            .replace(" ", "")
        )
