import json
import asyncio
import websockets


class CDPClient:
    def __init__(self, websocket_url: str):
        self.url = websocket_url
        self.ws = None
        self.message_id = 0

    async def connect(self):
        self.ws = await websockets.connect(self.url)

        await self.send(
            "Network.enable",
            {}
        )

        print("✓ CDP подключен")

    async def send(self, method, params=None):
        if params is None:
            params = {}

        self.message_id += 1

        await self.ws.send(
            json.dumps(
                {
                    "id": self.message_id,
                    "method": method,
                    "params": params,
                }
            )
        )

    async def receive(self):
        while True:
            message = await self.ws.recv()
            yield json.loads(message)