import asyncio

from config import (
    BRAVE_PATH,
    CDP_PORT,
)

from database.repository import (
    create_database,
)

from scanner.connection import (
    PocketConnection,
)

from scanner import Scanner


async def main():

    print(
        "Pocket Option Strategy Lab"
    )

    create_database()


    connection = PocketConnection(
        BRAVE_PATH,
        CDP_PORT
    )


    connection.start_browser()


    print(
        "Открой Pocket Option и войди"
    )

    input(
        "После входа нажми ENTER..."
    )


    websocket_url = (
        connection.find_pocket_tab()
    )


    if websocket_url is None:
        print(
            "Pocket Option не найден"
        )
        return


    scanner = Scanner(
        websocket_url
    )


    await scanner.start()


if __name__ == "__main__":
    asyncio.run(main())