import json

import websockets


class CDPClient:
    """Асинхронный клиент Chrome DevTools Protocol."""

    def __init__(self, websocket_url: str):
        self.url = websocket_url
        self.ws = None
        self.message_id = 0

    async def connect(self) -> None:
        self.ws = await websockets.connect(self.url)

        await self.send(
            "Network.enable",
            {},
        )

        print("✓ CDP подключен")

    async def send(self, method: str, params: dict | None = None) -> None:
        if self.ws is None:
            raise RuntimeError("CDP-соединение не установлено")

        self.message_id += 1

        await self.ws.send(
            json.dumps(
                {
                    "id": self.message_id,
                    "method": method,
                    "params": params or {},
                }
            )
        )

    async def receive(self):
        if self.ws is None:
            raise RuntimeError("CDP-соединение не установлено")

        async for message in self.ws:
            yield json.loads(message)

    async def close(self) -> None:
        if self.ws is None:
            return

        try:
            await self.ws.close()
        except Exception:
            pass
        finally:
            self.ws = None

        print("✓ CDP отключен")