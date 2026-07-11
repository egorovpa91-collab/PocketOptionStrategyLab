from __future__ import annotations

import asyncio
from collections import defaultdict, deque

from database.repository import (
    CandleWriteStatus,
    save_candle,
)

from .events import CandleEventDispatcher, ClosedCandleEvent
from .models import Candle, MarketData
from .parser import Parser
from .subscription import SubscriptionManager
from .websocket import CDPClient


DEFAULT_ASSETS = [
    "EURUSD_otc",
    "GBPUSD_otc",
    "AUDUSD_otc",
    "USDJPY_otc",
    "EURGBP_otc",
    "GBPJPY_otc",
    "AUDCAD_otc",
    "EURRUB_otc",
    "USDCHF_otc",
]


class Scanner:
    """Получает и сохраняет рыночные данные Pocket Option."""

    TIMEFRAME = 60

    def __init__(
        self,
        websocket_url: str,
        assets: list[str] | None = None,
        switch_interval: float = 10.0,
    ) -> None:
        """
        Создаёт сканер.

        Args:
            websocket_url: CDP WebSocket URL вкладки Pocket Option.
            assets: Список активов для последовательного сканирования.
            switch_interval: Время работы с одной парой в секундах.
        """

        self.client = CDPClient(websocket_url)
        self.parser = Parser()
        self.subscription = SubscriptionManager(
            client=self.client,
            period=self.TIMEFRAME,
            history_seconds=9_000,
        )

        self.assets = (
            assets.copy()
            if assets is not None
            else DEFAULT_ASSETS.copy()
        )
        self.switch_interval = switch_interval

        self.market_ready = asyncio.Event()
        self.running = False

        # Pocket Option может создать несколько рыночных сокетов.
        self.market_websocket_ids: set[str] = set()
        self.subscription_task: asyncio.Task[None] | None = None

        # Актив, данные которого сейчас разрешено сохранять.
        # Во время переключения значение сбрасывается в None.
        self.active_asset: str | None = None

        # Локальный кэш последних свечей каждой пары.
        self.candle_cache: dict[
            tuple[str, int],
            deque[Candle],
        ] = defaultdict(lambda: deque(maxlen=500))

        # Последняя формирующаяся свеча для каждой пары и таймфрейма.
        self.current_candle_timestamps: dict[
            tuple[str, int],
            int,
        ] = {}

        self.events = CandleEventDispatcher()

        self.received_count = 0
        self.inserted_count = 0
        self.updated_count = 0
        self.unchanged_count = 0
        self.filtered_count = 0
        self.closed_count = 0

    async def start(self) -> None:
        """Запускает подключение и основной цикл сканера."""

        await self.client.connect()
        await self.subscription.install_websocket_interceptor()

        print(
            "Перезагружаем Pocket Option "
            "для подключения перехватчика..."
        )
        await self.subscription.reload_page()

        self.running = True
        self.subscription_task = asyncio.create_task(
            self._subscription_loop(),
            name="pocket-option-subscriptions",
        )

        print("✓ Scanner запущен")
        print("Ожидаем WebSocket Pocket Option...")

        try:
            async for event in self.client.events():
                if not self.running:
                    break

                await self._handle_event(event)
        finally:
            await self.stop()

    async def _handle_event(
        self,
        event: dict,
    ) -> None:
        """Обрабатывает одно событие CDP."""

        method = event.get("method", "")

        if method == "Network.webSocketCreated":
            self._handle_websocket_created(event)
            return

        if method == "Network.webSocketClosed":
            self._handle_websocket_closed(event)
            return

        if method == "Network.webSocketFrameReceived":
            await self._handle_websocket_frame(event)
            return

        if method == "CDP.connectionError":
            message = (
                event
                .get("params", {})
                .get(
                    "message",
                    "Неизвестная ошибка CDP",
                )
            )
            print(f"Ошибка CDP: {message}")

    def _handle_websocket_created(
        self,
        event: dict,
    ) -> None:
        """Запоминает рыночный WebSocket Pocket Option."""

        params = event.get("params", {})
        url = str(params.get("url", ""))

        if "po.market" not in url or "api" not in url:
            return

        request_id = str(params.get("requestId", ""))

        if not request_id:
            return

        was_empty = not self.market_websocket_ids
        self.market_websocket_ids.add(request_id)
        self.market_ready.set()

        if was_empty:
            print("✓ Рыночный WebSocket Pocket Option найден")

    def _handle_websocket_closed(
        self,
        event: dict,
    ) -> None:
        """Удаляет закрытый рыночный WebSocket."""

        request_id = str(
            event
            .get("params", {})
            .get("requestId", "")
        )

        if request_id not in self.market_websocket_ids:
            return

        self.market_websocket_ids.discard(request_id)

        if not self.market_websocket_ids:
            self.market_ready.clear()
            self.active_asset = None
            print(
                "⚠ Все рыночные WebSocket "
                "Pocket Option закрыты"
            )

    async def _handle_websocket_frame(
        self,
        event: dict,
    ) -> None:
        """Извлекает рыночные данные из WebSocket-кадра."""

        params = event.get("params", {})
        request_id = str(params.get("requestId", ""))

        if (
            self.market_websocket_ids
            and request_id not in self.market_websocket_ids
        ):
            return

        payload = (
            params
            .get("response", {})
            .get("payloadData", "")
        )

        if not payload:
            return

        # Служебные сообщения Socket.IO.
        if payload.startswith(("0", "40", "42")):
            return

        market_data = self.parser.parse(payload)

        if market_data is None:
            return

        self.received_count += len(market_data.candles)

        if not self._is_market_data_allowed(market_data):
            self.filtered_count += len(market_data.candles)
            return

        await self._save_market_data(market_data)

    def _is_market_data_allowed(
        self,
        market_data: MarketData,
    ) -> bool:
        """
        Проверяет соответствие данных текущему активу.

        Данные разрешены только при одновременном выполнении условий:
        - переключение актива завершено;
        - Scanner разрешил сохранение этого актива;
        - SubscriptionManager подтвердил тот же актив;
        - asset внутри пакета совпадает с ожидаемым;
        - актив входит в установленный список.
        """

        if self.active_asset is None:
            return False

        subscription_asset = self.subscription.current_asset

        if subscription_asset is None:
            return False

        packet_asset = self._normalize_asset(market_data.asset)
        expected_asset = self._normalize_asset(self.active_asset)
        confirmed_asset = self._normalize_asset(subscription_asset)
        allowed_assets = {
            self._normalize_asset(asset)
            for asset in self.assets
        }

        if packet_asset not in allowed_assets:
            return False

        if packet_asset != expected_asset:
            return False

        if packet_asset != confirmed_asset:
            return False

        return True

    async def _save_market_data(
        self,
        market_data: MarketData,
    ) -> None:
        """
        Выполняет UPSERT свечей и определяет закрытие M1-свечи.

        Первый исторический пакет только инициализирует состояние пары.
        Событие new_closed_candle публикуется при последующем появлении
        свечи с более новым timestamp.
        """

        if not market_data.candles:
            return

        candles = sorted(
            market_data.candles,
            key=lambda item: item.time,
        )

        state_key = (
            self._normalize_asset(market_data.asset),
            self.TIMEFRAME,
        )
        is_initial_packet = (
            state_key not in self.current_candle_timestamps
        )

        inserted = 0
        updated = 0
        unchanged = 0

        for candle in candles:
            result = save_candle(
                asset=candle.asset,
                timeframe=self.TIMEFRAME,
                timestamp=candle.time,
                open_price=candle.open,
                high=candle.high,
                low=candle.low,
                close=candle.close,
                volume=0,
            )

            if result.status is CandleWriteStatus.INSERTED:
                self.inserted_count += 1
                inserted += 1
            elif result.status is CandleWriteStatus.UPDATED:
                self.updated_count += 1
                updated += 1
            else:
                self.unchanged_count += 1
                unchanged += 1

            self._upsert_candle_cache(
                candle=candle,
                timeframe=self.TIMEFRAME,
            )

            if not is_initial_packet:
                await self._detect_closed_candle(
                    state_key=state_key,
                    new_candle=candle,
                )

        if is_initial_packet:
            self.current_candle_timestamps[state_key] = max(
                candle.time
                for candle in candles
            )

        if inserted or updated:
            print(
                f"✓ {market_data.asset:15} | "
                f"INSERT: {inserted:3} | "
                f"UPDATE: {updated:3} | "
                f"UNCHANGED: {unchanged:3} | "
                f"закрыто: {self.closed_count} | "
                f"отфильтровано: {self.filtered_count}"
            )

    async def _detect_closed_candle(
        self,
        state_key: tuple[str, int],
        new_candle: Candle,
    ) -> None:
        """Определяет переход к следующей M1-свече."""

        current_timestamp = self.current_candle_timestamps[state_key]

        if new_candle.time <= current_timestamp:
            return

        closed_candle = self._find_cached_candle(
            state_key=state_key,
            timestamp=current_timestamp,
        )

        self.current_candle_timestamps[state_key] = new_candle.time

        if closed_candle is None:
            print(
                "⚠ Не удалось сформировать new_closed_candle: "
                f"{new_candle.asset} | timestamp={current_timestamp}"
            )
            return

        event = ClosedCandleEvent(
            name="new_closed_candle",
            asset=closed_candle.asset,
            timeframe=state_key[1],
            candle=closed_candle,
        )

        self.closed_count += 1

        print(
            "✓ new_closed_candle | "
            f"{event.asset} | "
            f"M{event.timeframe // 60} | "
            f"timestamp={event.candle.time} | "
            f"close={event.candle.close}"
        )

        await self.events.publish_new_closed_candle(event)

    def _upsert_candle_cache(
        self,
        candle: Candle,
        timeframe: int,
    ) -> None:
        """Добавляет свечу в кэш или обновляет её по timestamp."""

        cache_key = (
            self._normalize_asset(candle.asset),
            timeframe,
        )
        cache = self.candle_cache[cache_key]

        for index, cached_candle in enumerate(cache):
            if cached_candle.time == candle.time:
                cache[index] = candle
                return

        cache.append(candle)

    def _find_cached_candle(
        self,
        state_key: tuple[str, int],
        timestamp: int,
    ) -> Candle | None:
        """Ищет свечу в локальном кэше пары."""

        for candle in reversed(self.candle_cache[state_key]):
            if candle.time == timestamp:
                return candle

        return None

    async def _subscription_loop(
        self,
    ) -> None:
        """Переключает девять активов по кругу."""

        try:
            await self.market_ready.wait()
            print("✓ Начинаем перебор активов")

            asset_index = 0

            while self.running:
                if not self.market_ready.is_set():
                    self.active_asset = None
                    await self.market_ready.wait()

                asset = self.assets[
                    asset_index % len(self.assets)
                ]
                asset_index += 1

                # Перед переключением запрещаем сохранение данных.
                self.active_asset = None
                self.subscription.current_asset = None

                try:
                    await self.subscription.subscribe(asset)
                except Exception as error:
                    print(
                        f"Ошибка подписки "
                        f"{asset}: {error}"
                    )
                    await asyncio.sleep(self.switch_interval)
                    continue

                # subscribe() возвращается только после подтверждения
                # фактического переключения интерфейса.
                confirmed_asset = self.subscription.current_asset

                if (
                    confirmed_asset is None
                    or self._normalize_asset(confirmed_asset)
                    != self._normalize_asset(asset)
                ):
                    print(
                        f"⚠ Актив {asset} "
                        "не подтверждён интерфейсом"
                    )
                    self.active_asset = None
                    await asyncio.sleep(self.switch_interval)
                    continue

                self.active_asset = asset
                print(f"✓ Приём данных разрешён: {asset}")
                await asyncio.sleep(self.switch_interval)

        except asyncio.CancelledError:
            raise

    async def stop(self) -> None:
        """Останавливает фоновые задачи сканера."""

        if (
            not self.running
            and self.subscription_task is None
        ):
            return

        self.running = False
        self.active_asset = None

        task = self.subscription_task
        self.subscription_task = None

        if task is not None:
            task.cancel()

            try:
                await task
            except asyncio.CancelledError:
                pass

        print(
            "✓ Scanner остановлен | "
            f"получено: {self.received_count} | "
            f"INSERT: {self.inserted_count} | "
            f"UPDATE: {self.updated_count} | "
            f"UNCHANGED: {self.unchanged_count} | "
            f"закрыто: {self.closed_count} | "
            f"отфильтровано: {self.filtered_count}"
        )

    @staticmethod
    def _normalize_asset(
        asset: str,
    ) -> str:
        """
        Приводит актив к единому виду для сравнения.

        Примеры:
            EURUSD_otc -> eurusd_otc
            EURUSD_OTC -> eurusd_otc
        """

        return (
            asset
            .strip()
            .lower()
            .replace(" ", "")
        )
