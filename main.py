import asyncio

from config import BRAVE_PATH, CDP_PORT
from database.repository import create_database
from scanner import Scanner
from scanner.connection import PocketConnection


async def run_application() -> None:
    connection = PocketConnection(
        browser_path=BRAVE_PATH,
        port=CDP_PORT,
    )

    scanner: Scanner | None = None

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
        await scanner.start()

    except asyncio.CancelledError:
        print("\nПолучена команда остановки.")

    finally:
     print("\nЗавершение работы...")

    if scanner is not None:
        await scanner.stop()
        await scanner.client.close()

    print("✓ Программа завершена корректно")


def main() -> None:
    try:
        asyncio.run(run_application())
    except KeyboardInterrupt:
        print("\nОстановлено пользователем.")


if __name__ == "__main__":
    main()