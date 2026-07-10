import json
from typing import Any


class Normalizer:
    """Преобразует сообщения Pocket Option в список минутных OHLC-свечей."""

    @staticmethod
    def _build_candles_from_ticks(
        ticks: list,
        period: int = 60,
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None

        for tick in ticks:
            if not isinstance(tick, list) or len(tick) < 2:
                continue

            try:
                timestamp = float(tick[0])
                price = float(tick[1])
            except (TypeError, ValueError):
                continue

            bucket = int(timestamp // period) * period

            if current is None or current["timestamp"] != bucket:
                if current is not None:
                    result.append(current)

                current = {
                    "timestamp": bucket,
                    "open": price,
                    "high": price,
                    "low": price,
                    "close": price,
                    "volume": 0.0,
                }
            else:
                current["close"] = price
                current["high"] = max(current["high"], price)
                current["low"] = min(current["low"], price)

        if current is not None:
            result.append(current)

        return result

    def normalize(self, decoded: str) -> list[dict[str, Any]]:
        """Возвращает список свечей или пустой список."""

        if not decoded:
            return []

        try:
            data = json.loads(decoded)
        except (json.JSONDecodeError, TypeError):
            return []

        # Готовые OHLC-свечи
        if (
            isinstance(data, dict)
            and "asset" in data
            and "data" in data
        ):
            asset = str(data["asset"])
            timeframe = int(data.get("period", 60))
            result: list[dict[str, Any]] = []

            for candle in data["data"]:
                if not isinstance(candle, dict):
                    continue

                required = {"time", "open", "high", "low", "close"}
                if not required.issubset(candle):
                    continue

                try:
                    result.append({
                        "asset": asset,
                        "timeframe": timeframe,
                        "timestamp": int(float(candle["time"])),
                        "open": float(candle["open"]),
                        "high": float(candle["high"]),
                        "low": float(candle["low"]),
                        "close": float(candle["close"]),
                        "volume": float(candle.get("volume", 0) or 0),
                    })
                except (TypeError, ValueError):
                    continue

            return result

        # История в виде тиков
        if (
            isinstance(data, dict)
            and "asset" in data
            and "history" in data
        ):
            asset = str(data["asset"])
            timeframe = int(data.get("period", 60))

            built = self._build_candles_from_ticks(
                data["history"],
                timeframe,
            )

            for candle in built:
                candle["asset"] = asset
                candle["timeframe"] = timeframe

            return built

        return []