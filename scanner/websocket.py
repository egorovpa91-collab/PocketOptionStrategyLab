from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

import websockets
from websockets.asyncio.client import ClientConnection


class CDPClient:
    """
    Асинхронный клиент Chrome DevTools Protocol.

    Клиент использует единственный цикл чтения WebSocket:
    - ответы CDP направляются ожидающим командам по полю id;
    - события CDP складываются в отдельную очередь;
    - входящие свечи не теряются во время выполнения команд.
    """

    def __init__(
        self,
        websocket_url: str,
        command_timeout: float = 10.0,
    ) -> None:
        """
        Создаёт CDP-клиент.

        Args:
            websocket_url: WebSocket URL вкладки Brave.
            command_timeout: Максимальное ожидание ответа CDP в секундах.
        """
        self.url = websocket_url
        self.command_timeout = command_timeout

        self.ws: ClientConnection | None = None

        self._message_id = 0
        self._reader_task: asyncio.Task[None] | None = None

        self._pending_commands: dict[
            int,
            asyncio.Future[dict[str, Any]],
        ] = {}

        self._event_queue: asyncio.Queue[
            dict[str, Any] | None
        ] = asyncio.Queue()

        self._send_lock = asyncio.Lock()
        self._closed = True

    async def connect(self) -> None:
        """Подключается к CDP вкладки Brave."""
        if self.ws is not None:
            return

        self.ws = await websockets.connect(
            self.url,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=5,
            max_size=None,
        )

        self._closed = False

        self._reader_task = asyncio.create_task(
            self._reader_loop(),
            name="cdp-reader",
        )

        await self.send("Network.enable")
        await self.send("Page.enable")
        await self.send("Runtime.enable")

        print("✓ CDP подключен")

    async def send(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Отправляет CDP-команду и ожидает соответствующий ответ.

        Args:
            method: Название CDP-метода.
            params: Параметры CDP-команды.

        Returns:
            Полный ответ CDP.

        Raises:
            RuntimeError: Если соединение не установлено или CDP вернул ошибку.
            TimeoutError: Если CDP не ответил вовремя.
        """
        if self.ws is None or self._closed:
            raise RuntimeError("CDP-соединение не установлено")

        loop = asyncio.get_running_loop()

        async with self._send_lock:
            self._message_id += 1
            command_id = self._message_id

            future: asyncio.Future[dict[str, Any]] = (
                loop.create_future()
            )

            self._pending_commands[command_id] = future

            command = {
                "id": command_id,
                "method": method,
                "params": params or {},
            }

            try:
                await self.ws.send(
                    json.dumps(
                        command,
                        ensure_ascii=False,
                    )
                )
            except Exception:
                self._pending_commands.pop(
                    command_id,
                    None,
                )
                raise

        try:
            response = await asyncio.wait_for(
                future,
                timeout=self.command_timeout,
            )
        except asyncio.TimeoutError as error:
            self._pending_commands.pop(
                command_id,
                None,
            )

            raise TimeoutError(
                f"CDP не ответил на команду {method} "
                f"за {self.command_timeout} сек."
            ) from error

        if "error" in response:
            error_data = response["error"]

            raise RuntimeError(
                f"Ошибка CDP при выполнении {method}: "
                f"{error_data}"
            )

        return response

    async def events(self) -> AsyncIterator[dict[str, Any]]:
        """
        Асинхронно возвращает события CDP.

        Ответы на команды сюда не попадают.
        """
        while True:
            event = await self._event_queue.get()

            if event is None:
                break

            yield event

    async def _reader_loop(self) -> None:
        """
        Постоянно читает единственное CDP WebSocket-соединение.

        Ответы с полем id передаются соответствующим Future.
        События с полем method помещаются в очередь событий.
        """
        if self.ws is None:
            return

        try:
            async for raw_message in self.ws:
                try:
                    message = json.loads(raw_message)
                except json.JSONDecodeError:
                    continue

                command_id = message.get("id")

                if isinstance(command_id, int):
                    future = self._pending_commands.pop(
                        command_id,
                        None,
                    )

                    if (
                        future is not None
                        and not future.done()
                    ):
                        future.set_result(message)

                    continue

                if "method" in message:
                    await self._event_queue.put(message)

        except asyncio.CancelledError:
            raise

        except Exception as error:
            if not self._closed:
                await self._event_queue.put(
                    {
                        "method": "CDP.connectionError",
                        "params": {
                            "message": str(error),
                        },
                    }
                )

        finally:
            self._fail_pending_commands(
                RuntimeError(
                    "CDP-соединение было закрыто"
                )
            )

            await self._event_queue.put(None)

    def _fail_pending_commands(
        self,
        error: Exception,
    ) -> None:
        """Завершает ожидающие команды указанной ошибкой."""
        pending = list(
            self._pending_commands.values()
        )

        self._pending_commands.clear()

        for future in pending:
            if not future.done():
                future.set_exception(error)

    async def close(self) -> None:
        """Корректно закрывает CDP-соединение."""
        if self._closed:
            return

        self._closed = True

        reader_task = self._reader_task
        self._reader_task = None

        websocket = self.ws
        self.ws = None

        if websocket is not None:
            try:
                await websocket.close()
            except Exception:
                pass

        if reader_task is not None:
            reader_task.cancel()

            try:
                await reader_task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

        self._fail_pending_commands(
            RuntimeError(
                "CDP-клиент остановлен"
            )
        )

        print("✓ CDP отключен")