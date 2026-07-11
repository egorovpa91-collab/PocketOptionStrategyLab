import asyncio

from candle_manager import CandleManager
from config import BRAVE_PATH, CDP_PORT
from database.repository import create_database
from indicator_engine import IndicatorEngine, IndicatorRegistry
from indicator_engine.indicators import (
    ClosePriceIndicator,
    EMAIndicator,
)
from scanner import Scanner
from scanner.connection import PocketConnection


EMA_PERIODS = (
    5,
    8,
    10,
    13,
    20,
    30,
    50,
    100,
    200,
)


async def run_application() -> None:
    """Запускает основные компоненты Strategy Research Lab."""

    connection = PocketConnection(
        browser_path=BRAVE_PATH,
        port=CDP_PORT,
    )
    scanner: Scanner | None = None

    candle_manager = CandleManager(history_limit=500)

    indicator_registry = IndicatorRegistry()
    indicator_registry.register(ClosePriceIndicator())

    for period in EMA_PERIODS:
        indicator_registry.register(
            EMAIndicator(period=period)
        )

    indicator_engine = IndicatorEngine(
        candle_manager=candle_manager,
        registry=indicator_registry,
    )

    try:
        print("=" * 60)
        print("Pocket Option Strategy Research Lab")
        print("=" * 60)

        create_database()
        connection.start_browser()

        print("\nОткрой Pocket Option и войди в аккаунт.")
        input("После входа нажми ENTER...")

        websocket_url = connection.find_pocket_tab()

        if websocket_url is None:
            print("Pocket Option не найден.")
            return

        scanner = Scanner(websocket_url)

        # Порядок подписки важен:
        # сначала Candle Manager обновляет закрытую историю,
        # затем Indicator Engine рассчитывает снимок.
        scanner.events.subscribe_new_closed_candle(
            candle_manager.handle_new_closed_candle
        )
        scanner.events.subscribe_new_closed_candle(
            indicator_engine.handle_new_closed_candle
        )

        print("✓ Candle Manager подписан на new_closed_candle")
        print(
            "✓ Indicator Engine подписан на new_closed_candle "
            f"| индикаторов: {len(indicator_registry)}"
        )

        await scanner.start()

    except asyncio.CancelledError:
        print("\nПолучена команда остановки.")
    finally:
        print("\nЗавершение работы...")

        if scanner is not None:
            await scanner.stop()
            await scanner.client.close()

        candle_manager.print_summary()
        indicator_engine.print_summary()
        print("✓ Программа завершена корректно")


def main() -> None:
    """Точка входа приложения."""

    try:
        asyncio.run(run_application())
    except KeyboardInterrupt:
        print("\nОстановлено пользователем.")


if __name__ == "__main__":
    main()
