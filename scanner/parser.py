import base64
import json

from .models import Candle, MarketData


class Parser:
    """
    Парсер данных Pocket Option.

    Поддерживает:
    - готовые OHLC свечи
    - историю тиков
    """

    def parse(self, raw: str) -> MarketData | None:

        try:
            decoded = base64.b64decode(raw).decode()
            data = json.loads(decoded)

        except Exception:
            return None


        # =========================
        # ГОТОВЫЕ СВЕЧИ
        # =========================

        if (
            isinstance(data, dict)
            and "asset" in data
            and "data" in data
        ):

            candles = []

            for item in data["data"]:

                if "open" not in item:
                    continue

                candles.append(
                    Candle(
                        asset=data["asset"],
                        time=item["time"],
                        open=item["open"],
                        high=item["high"],
                        low=item["low"],
                        close=item["close"],
                    )
                )


            if candles:
                return MarketData(
                    asset=data["asset"],
                    source="ohlc",
                    candles=candles,
                )


        # =========================
        # ТИКИ → СВЕЧИ
        # =========================

        if (
            isinstance(data, dict)
            and "history" in data
            and "asset" in data
        ):

            candles = self.build_from_ticks(
                data["asset"],
                data["history"]
            )

            if candles:
                return MarketData(
                    asset=data["asset"],
                    source="ticks",
                    candles=candles,
                )

        return None


    def build_from_ticks(
        self,
        asset,
        ticks,
        period=60,
    ):

        result = []
        current = None


        for tick in ticks:

            if (
                not isinstance(tick, list)
                or len(tick) < 2
            ):
                continue


            ts = tick[0]
            price = tick[1]

            bucket = int(ts // period) * period


            if (
                current is None
                or current.time != bucket
            ):

                if current:
                    result.append(current)


                current = Candle(
                    asset=asset,
                    time=bucket,
                    open=price,
                    high=price,
                    low=price,
                    close=price,
                )


            else:

                current.close = price
                current.high = max(
                    current.high,
                    price
                )
                current.low = min(
                    current.low,
                    price
                )


        if current:
            result.append(current)


        return result