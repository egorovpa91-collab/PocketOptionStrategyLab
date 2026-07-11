from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from .models import Candle


@dataclass(frozen=True, slots=True)
class ClosedCandleEvent:
    """Событие закрытия одной свечи."""

    name: str
    asset: str
    timeframe: int
    candle: Candle


ClosedCandleHandler = Callable[
    [ClosedCandleEvent],
    Awaitable[None] | None,
]


class CandleEventDispatcher:
    """Публикует события закрытия свечей подписанным обработчикам."""

    def __init__(self) -> None:
        """Создаёт пустой список подписчиков."""

        self._closed_candle_handlers: list[ClosedCandleHandler] = []

    def subscribe_new_closed_candle(
        self,
        handler: ClosedCandleHandler,
    ) -> None:
        """Подписывает обработчик на событие new_closed_candle."""

        if handler not in self._closed_candle_handlers:
            self._closed_candle_handlers.append(handler)

    def unsubscribe_new_closed_candle(
        self,
        handler: ClosedCandleHandler,
    ) -> None:
        """Удаляет обработчик из подписчиков new_closed_candle."""

        if handler in self._closed_candle_handlers:
            self._closed_candle_handlers.remove(handler)

    async def publish_new_closed_candle(
        self,
        event: ClosedCandleEvent,
    ) -> None:
        """Последовательно уведомляет всех подписчиков."""

        for handler in tuple(self._closed_candle_handlers):
            result = handler(event)

            if inspect.isawaitable(result):
                await result
