from __future__ import annotations

import json
import time

from .websocket import CDPClient


class SubscriptionManager:
    """Управляет подписками Pocket Option на рыночные активы."""

    def __init__(
        self,
        client: CDPClient,
        period: int = 60,
        history_seconds: int = 9_000,
    ) -> None:
        """
        Инициализирует менеджер подписок.

        Args:
            client: Активное CDP-соединение с вкладкой Pocket Option.
            period: Период свечи в секундах.
            history_seconds: Глубина запрашиваемой истории в секундах.
        """
        self.client = client
        self.period = period
        self.history_seconds = history_seconds
        self.current_asset: str | None = None

    async def install_websocket_interceptor(self) -> None:
        """
        Устанавливает перехватчик WebSocket в страницу Pocket Option.

        Перехватчик сохраняет рыночное WebSocket-соединение
        в переменной window.__po_ws.
        """
        script = """
        (() => {
            if (window.__po_interceptor_installed) {
                return "already-installed";
            }

            window.__po_interceptor_installed = true;

            const OriginalWebSocket = window.WebSocket;

            window.WebSocket = function(url, protocols) {
                const socket = protocols === undefined
                    ? new OriginalWebSocket(url)
                    : new OriginalWebSocket(url, protocols);

                if (
                    typeof url === "string"
                    && url.includes("po.market")
                    && url.includes("api")
                ) {
                    window.__po_ws = socket;
                }

                return socket;
            };

            window.WebSocket.prototype = OriginalWebSocket.prototype;

            Object.defineProperties(
                window.WebSocket,
                {
                    CONNECTING: { value: OriginalWebSocket.CONNECTING },
                    OPEN: { value: OriginalWebSocket.OPEN },
                    CLOSING: { value: OriginalWebSocket.CLOSING },
                    CLOSED: { value: OriginalWebSocket.CLOSED },
                },
            );

            return "installed";
        })();
        """

        await self.client.send(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": script},
        )

    async def reload_page(self) -> None:
        """Перезагружает страницу для активации WebSocket-перехватчика."""
        await self.client.send("Page.reload")

    async def subscribe(self, asset: str) -> None:
        """
        Переключает Pocket Option на указанный актив и запрашивает историю.

        Args:
            asset: Идентификатор актива, например EURUSD_otc.
        """
        normalized_asset = asset.strip()

        if not normalized_asset:
            raise ValueError("Название актива не может быть пустым")

        timestamp = int(time.time())
        history_start = timestamp - self.history_seconds

        messages = [
            (
                '42["changeSymbol",'
                f'{{"asset":"{normalized_asset}",'
                f'"period":{self.period}}}]'
            ),
            f'42["subfor","{normalized_asset}"]',
            (
                '42["loadHistoryPeriod",'
                f'{{"asset":"{normalized_asset}",'
                f'"index":{self._build_history_index(timestamp)},'
                f'"time":{history_start},'
                f'"offset":{self.history_seconds},'
                f'"period":{self.period}}}]'
            ),
        ]

        expression = self._build_send_expression(messages)

        await self.client.send(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
            },
        )

        self.current_asset = normalized_asset

        print(
            f"→ Подписка: {normalized_asset} | "
            f"период: {self.period} сек."
        )

    @staticmethod
    def _build_history_index(timestamp: int) -> int:
        """
        Создаёт индекс запроса истории в формате рабочего прототипа.

        В тестовом сборщике к Unix-времени добавлялась строка «53».
        Сохраняем это поведение до проверки точного назначения поля index.
        """
        return int(f"{timestamp}53")

    @staticmethod
    def _build_send_expression(messages: list[str]) -> str:
        """Создаёт JavaScript для отправки команд через WebSocket страницы."""
        serialized_messages = json.dumps(
            messages,
            ensure_ascii=False,
        )

        return f"""
        (() => {{
            try {{
                const socket = window.__po_ws;

                if (!socket) {{
                    return {{
                        ok: false,
                        reason: "websocket-not-found"
                    }};
                }}

                if (socket.readyState !== WebSocket.OPEN) {{
                    return {{
                        ok: false,
                        reason: "websocket-not-open",
                        readyState: socket.readyState
                    }};
                }}

                const messages = {serialized_messages};

                for (const message of messages) {{
                    socket.send(message);
                }}

                return {{
                    ok: true,
                    sent: messages.length
                }};
            }} catch (error) {{
                return {{
                    ok: false,
                    reason: String(error)
                }};
            }}
        }})();
        """