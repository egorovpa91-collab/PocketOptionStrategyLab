from __future__ import annotations

import asyncio
import json
import time

from .websocket import CDPClient


class SubscriptionManager:
    """Управление переключением активов Pocket Option."""

    def __init__(
        self,
        client: CDPClient,
        period: int = 60,
        history_seconds: int = 9000,
    ) -> None:

        self.client = client
        self.period = period
        self.history_seconds = history_seconds

        self.current_asset: str | None = None


    async def install_websocket_interceptor(self) -> None:
        """
        Устанавливает перехватчик WebSocket.
        """

        script = """
        (() => {

            if (window.__po_interceptor_installed)
                return "already-installed";


            window.__po_interceptor_installed = true;


            const OriginalWebSocket = window.WebSocket;


            window.WebSocket = function(url, protocols) {

                const ws = protocols
                    ? new OriginalWebSocket(url, protocols)
                    : new OriginalWebSocket(url);


                if (
                    typeof url === "string"
                    &&
                    url.includes("po.market")
                    &&
                    url.includes("api")
                ) {

                    window.__po_ws = ws;

                    console.log(
                        "PO market websocket captured"
                    );
                }


                return ws;
            };


            window.WebSocket.prototype =
                OriginalWebSocket.prototype;


            return "installed";

        })();
        """


        await self.client.send(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": script
            }
        )


    async def reload_page(self) -> None:
        """
        Перезагрузка Pocket Option.
        """

        await self.client.send(
            "Page.reload"
        )



    async def wait_for_socket(
        self,
        timeout: int = 30,
    ) -> bool:
        """
        Ожидание открытого управляющего WebSocket.
        """


        script = """

        (() => {

            if (
                window.__po_ws
                &&
                window.__po_ws.readyState
                ===
                WebSocket.OPEN
            ) {

                return true;

            }


            return false;


        })();

        """


        start = time.time()


        while time.time() - start < timeout:


            result = await self.client.send(
                "Runtime.evaluate",
                {
                    "expression": script,
                    "returnByValue": True,
                }
            )


            value = (
                result
                .get("result", {})
                .get("result", {})
                .get("value")
            )


            if value:

                print(
                    "✓ Управляющий WebSocket готов"
                )

                return True


            await asyncio.sleep(1)



        print(
            "⚠ Управляющий WebSocket не найден"
        )


        return False



    async def subscribe(
        self,
        asset: str,
    ) -> None:
        """
        Переключение актива.
        """


        ready = await self.wait_for_socket()


        if not ready:

            print(
                "⚠ Нет рабочего WebSocket"
            )

            return



        normalized_asset = asset.strip()



        timestamp = int(
            time.time()
        )


        history_start = (
            timestamp -
            self.history_seconds
        )



        messages = [

            (
                '42["changeSymbol",'
                f'{{"asset":"{normalized_asset}",'
                f'"period":{self.period}}}]'
            ),


            (
                f'42["subfor","{normalized_asset}"]'
            ),


            (
                '42["loadHistoryPeriod",'
                f'{{'
                f'"asset":"{normalized_asset}",'
                f'"index":{self._history_index(timestamp)},'
                f'"time":{history_start},'
                f'"offset":{self.history_seconds},'
                f'"period":{self.period}'
                f'}}]'
            )

        ]



        expression = (
            self._build_js_send(
                messages
            )
        )



        result = await self.client.send(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
            }
        )


        print(
            "Ответ JS переключения:",
            result
        )



        self.current_asset = normalized_asset


        print(
            f"→ Подписка: {normalized_asset}"
        )



        await asyncio.sleep(2)



        current = await self.get_current_asset()



        print(
            "Текущий актив на странице:",
            current
        )



    async def get_current_asset(self):
        """
        Получает текущий актив из интерфейса.
        """


        script = """

        (() => {

            let result = [];


            document
            .querySelectorAll("span")
            .forEach(
                e => {

                    const text =
                        e.innerText;


                    if (
                        text
                        &&
                        text.includes("/")
                    ) {

                        result.push(
                            text.trim()
                        );

                    }

                }
            );


            return result.slice(0,20);


        })();

        """



        response = await self.client.send(
            "Runtime.evaluate",
            {
                "expression": script,
                "returnByValue": True,
            }
        )



        return (
            response
            .get("result", {})
            .get("result", {})
            .get("value")
        )



    @staticmethod
    def _history_index(
        timestamp: int,
    ) -> int:

        return int(
            f"{timestamp}53"
        )



    @staticmethod
    def _build_js_send(
        messages: list[str],
    ) -> str:
        """
        JavaScript отправки команд.
        """


        data = json.dumps(
            messages,
            ensure_ascii=False,
        )



        return f"""

        (() => {{

            try {{

                const ws =
                    window.__po_ws;


                if (!ws) {{

                    return {{

                        ok:false,

                        error:
                        "websocket-not-found"

                    }};

                }}



                if (
                    ws.readyState
                    !==
                    WebSocket.OPEN
                ) {{

                    return {{

                        ok:false,

                        error:
                        "websocket-not-open",

                        state:
                        ws.readyState

                    }};

                }}



                const messages =
                    {data};



                messages.forEach(
                    m => ws.send(m)
                );



                return {{

                    ok:true,

                    sent:
                    messages.length

                }};



            }}
            catch(e) {{

                return {{

                    ok:false,

                    error:
                    String(e)

                }};

            }}

        }})();

        """