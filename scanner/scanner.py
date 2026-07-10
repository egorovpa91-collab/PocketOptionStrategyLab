from .websocket import CDPClient
from .parser import Parser


class Scanner:

    def __init__(self, websocket_url):
        self.client = CDPClient(websocket_url)
        self.parser = Parser()

    async def start(self):

        await self.client.connect()

        async for message in self.client.receive():

            method = message.get("method")

            if method != "Network.webSocketFrameReceived":
                continue

            payload = (
                message.get("params", {})
                .get("response", {})
                .get("payloadData", "")
            )

            if not payload:
                continue

            decoded = self.parser.parse(payload)

            if decoded:
                print("=" * 80)
                print(decoded[:300])
                print("=" * 80)