from collections import defaultdict, deque

from database.repository import save_candle

from .normalizer import Normalizer
from .parser import Parser
from .websocket import CDPClient


class Scanner:
    """Получает сообщения CDP, извлекает свечи и сохраняет их в SQLite."""

    def __init__(self, websocket_url: str):
        self.client = CDPClient(websocket_url)
        self.parser = Parser()
        self.normalizer = Normalizer()

        self.candle_cache = defaultdict(
            lambda: deque(maxlen=500)
        )

        self.saved_count = 0
        self.duplicate_count = 0

    async def start(self) -> None:
        await self.client.connect()

        print("✓ Scanner запущен")
        print("Ожидаем свечи Pocket Option...")

        async for message in self.client.receive():
            if message.get("method") != "Network.webSocketFrameReceived":
                continue

            payload = (
                message.get("params", {})
                .get("response", {})
                .get("payloadData", "")
            )

            decoded = self.parser.parse(payload)
            if not decoded:
                continue

            candles = self.normalizer.normalize(decoded)
            if not candles:
                continue

            for candle in candles:
                saved = save_candle(
                    asset=candle["asset"],
                    timeframe=candle["timeframe"],
                    timestamp=candle["timestamp"],
                    open_price=candle["open"],
                    high=candle["high"],
                    low=candle["low"],
                    close=candle["close"],
                    volume=candle["volume"],
                )

                cache_key = (
                    candle["asset"],
                    candle["timeframe"],
                )

                self.candle_cache[cache_key].append(candle)

                if saved:
                    self.saved_count += 1
                else:
                    self.duplicate_count += 1

            last = candles[-1]

            print(
                f'✓ {last["asset"]:15} | '
                f'{len(candles):4} свечей | '
                f'всего сохранено: {self.saved_count} | '
                f'дублей: {self.duplicate_count}'
            )