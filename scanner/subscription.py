from __future__ import annotations

import asyncio
import json
from typing import Any

from .websocket import CDPClient


class SubscriptionManager:
    """
    Управляет переключением активов Pocket Option через интерфейс страницы.
    """

    CURRENT_ASSET_SELECTOR = (
        "span.current-symbol, "
        "span.current-symbol_cropped"
    )

    ASSET_LABEL_SELECTOR = "span.alist__label"

    def __init__(
        self,
        client: CDPClient,
        period: int = 60,
        history_seconds: int = 9000,
    ) -> None:
        """
        Создаёт менеджер переключения активов.

        Args:
            client: Активное CDP-соединение с Pocket Option.
            period: Период свечей в секундах.
            history_seconds: Глубина истории в секундах.
        """
        self.client = client
        self.period = period
        self.history_seconds = history_seconds

        self.current_asset: str | None = None

    async def install_websocket_interceptor(self) -> None:
        """
        Оставлен для совместимости со Scanner.

        Переключение выполняется через интерфейс,
        поэтому отдельный управляющий WebSocket не используется.
        """
        return

    async def reload_page(self) -> None:
        """Перезагружает страницу Pocket Option."""
        await self.client.send(
            "Page.reload",
            {},
        )

    async def subscribe(self, asset: str) -> None:
        """
        Переключает Pocket Option на указанный актив.

        Args:
            asset: Идентификатор актива, например EURUSD_otc.
        """
        normalized_asset = asset.strip()

        if not normalized_asset:
            raise ValueError(
                "Название актива не может быть пустым"
            )

        display_name = self.asset_to_display_name(
            normalized_asset
        )

        ui_ready = await self.wait_for_interface(
            timeout=20.0
        )

        if not ui_ready:
            raise RuntimeError(
                "Интерфейс Pocket Option не загрузился: "
                "элемент текущего актива не найден"
            )

        current_before = await self.get_current_asset()

        if self._asset_names_equal(
            current_before,
            display_name,
        ):
            self.current_asset = normalized_asset

            print(
                f"→ Актив уже открыт: {display_name}"
            )

            return

        print(
            f"→ Переключение: {display_name}"
        )

        opened = await self._open_asset_list()

        if not opened:
            raise RuntimeError(
                "Не удалось открыть список активов"
            )

        list_ready = await self._wait_for_asset_list(
            timeout=5.0
        )

        if not list_ready:
            raise RuntimeError(
                "Список активов не появился"
            )

        click_result = await self._click_asset(
            display_name
        )

        if not click_result.get("ok"):
            raise RuntimeError(
                f"Не удалось выбрать {display_name}: "
                f"{click_result}"
            )

        switched = await self._wait_for_asset(
            expected_display_name=display_name,
            timeout=10.0,
        )

        if not switched:
            actual = await self.get_current_asset()

            raise RuntimeError(
                f"Интерфейс не переключился на "
                f"{display_name}. "
                f"Сейчас отображается: {actual}"
            )

        self.current_asset = normalized_asset

        print(
            f"✓ Актив переключён: {display_name}"
        )

    async def wait_for_interface(
        self,
        timeout: float = 20.0,
    ) -> bool:
        """
        Ждёт загрузки элемента текущего актива.
        """
        deadline = (
            asyncio.get_running_loop().time()
            + timeout
        )

        while (
            asyncio.get_running_loop().time()
            < deadline
        ):
            current = await self.get_current_asset()

            if current:
                return True

            await asyncio.sleep(0.5)

        return False

    async def get_current_asset(self) -> str | None:
        """
        Возвращает текущий актив из интерфейса.
        """
        script = f"""
        (() => {{
            const element = document.querySelector(
                {json.dumps(self.CURRENT_ASSET_SELECTOR)}
            );

            if (!element) {{
                return null;
            }}

            const text =
                element.innerText
                || element.textContent
                || "";

            return text.trim() || null;
        }})();
        """

        response = await self.client.send(
            "Runtime.evaluate",
            {
                "expression": script,
                "returnByValue": True,
            },
        )

        value = self._extract_runtime_value(
            response
        )

        if isinstance(value, str):
            return value.strip() or None

        return None

    async def _open_asset_list(self) -> bool:
        """
        Открывает список активов.
        """
        script = f"""
        (() => {{
            const symbol = document.querySelector(
                {json.dumps(self.CURRENT_ASSET_SELECTOR)}
            );

            if (!symbol) {{
                return {{
                    ok: false,
                    reason: "current-symbol-not-found"
                }};
            }}

            const candidates = [
                symbol,
                symbol.parentElement,
                symbol.parentElement
                    ? symbol.parentElement.parentElement
                    : null,
                symbol.closest("button"),
                symbol.closest("[role='button']"),
                symbol.closest("[class*='asset']"),
                symbol.closest("[class*='symbol']")
            ].filter(Boolean);

            for (const element of candidates) {{
                try {{
                    element.scrollIntoView({{
                        block: "center",
                        inline: "center"
                    }});

                    element.dispatchEvent(
                        new PointerEvent(
                            "pointerdown",
                            {{
                                bubbles: true,
                                cancelable: true,
                                pointerType: "mouse"
                            }}
                        )
                    );

                    element.dispatchEvent(
                        new MouseEvent(
                            "mousedown",
                            {{
                                bubbles: true,
                                cancelable: true,
                                view: window
                            }}
                        )
                    );

                    element.dispatchEvent(
                        new PointerEvent(
                            "pointerup",
                            {{
                                bubbles: true,
                                cancelable: true,
                                pointerType: "mouse"
                            }}
                        )
                    );

                    element.dispatchEvent(
                        new MouseEvent(
                            "mouseup",
                            {{
                                bubbles: true,
                                cancelable: true,
                                view: window
                            }}
                        )
                    );

                    element.click();

                    return {{
                        ok: true,
                        tag: element.tagName,
                        className:
                            String(element.className || "")
                    }};
                }} catch (error) {{
                    continue;
                }}
            }}

            return {{
                ok: false,
                reason: "no-clickable-parent"
            }};
        }})();
        """

        response = await self.client.send(
            "Runtime.evaluate",
            {
                "expression": script,
                "returnByValue": True,
            },
        )

        result = self._extract_runtime_value(
            response
        )

        if not isinstance(result, dict):
            return False

        if not result.get("ok"):
            print(
                "Ошибка открытия списка:",
                result,
            )

        return bool(result.get("ok"))

    async def _wait_for_asset_list(
        self,
        timeout: float,
    ) -> bool:
        """
        Ждёт появления элементов списка активов.
        """
        deadline = (
            asyncio.get_running_loop().time()
            + timeout
        )

        while (
            asyncio.get_running_loop().time()
            < deadline
        ):
            count = await self._get_asset_count()

            if count > 0:
                return True

            await asyncio.sleep(0.25)

        return False

    async def _get_asset_count(self) -> int:
        """
        Возвращает количество элементов списка активов.
        """
        script = f"""
        (() => {{
            return document.querySelectorAll(
                {json.dumps(self.ASSET_LABEL_SELECTOR)}
            ).length;
        }})();
        """

        response = await self.client.send(
            "Runtime.evaluate",
            {
                "expression": script,
                "returnByValue": True,
            },
        )

        value = self._extract_runtime_value(
            response
        )

        if isinstance(value, int):
            return value

        return 0

    async def _click_asset(
        self,
        display_name: str,
    ) -> dict[str, Any]:
        """
        Находит актив в списке и нажимает его строку.
        """
        script = f"""
        (() => {{
            const expected =
                {json.dumps(display_name)};

            const normalize = value =>
                String(value || "")
                    .trim()
                    .replace(/\\s+/g, " ")
                    .toUpperCase();

            const labels = Array.from(
                document.querySelectorAll(
                    {json.dumps(self.ASSET_LABEL_SELECTOR)}
                )
            );

            const target = labels.find(
                element =>
                    normalize(
                        element.innerText
                        || element.textContent
                    )
                    === normalize(expected)
            );

            if (!target) {{
                return {{
                    ok: false,
                    reason: "asset-not-found",
                    available: labels
                        .map(element =>
                            normalize(
                                element.innerText
                                || element.textContent
                            )
                        )
                        .filter(Boolean)
                        .slice(0, 100)
                }};
            }}

            const clickable =
                target.closest(
                    ".alist__item"
                )
                || target.closest("li")
                || target.closest("button")
                || target.closest(
                    "[role='button']"
                )
                || target.parentElement
                || target;

            clickable.scrollIntoView({{
                block: "center",
                inline: "nearest"
            }});

            const events = [
                new PointerEvent(
                    "pointerdown",
                    {{
                        bubbles: true,
                        cancelable: true,
                        pointerType: "mouse"
                    }}
                ),
                new MouseEvent(
                    "mousedown",
                    {{
                        bubbles: true,
                        cancelable: true,
                        view: window
                    }}
                ),
                new PointerEvent(
                    "pointerup",
                    {{
                        bubbles: true,
                        cancelable: true,
                        pointerType: "mouse"
                    }}
                ),
                new MouseEvent(
                    "mouseup",
                    {{
                        bubbles: true,
                        cancelable: true,
                        view: window
                    }}
                ),
                new MouseEvent(
                    "click",
                    {{
                        bubbles: true,
                        cancelable: true,
                        view: window
                    }}
                )
            ];

            for (const event of events) {{
                clickable.dispatchEvent(event);
            }}

            return {{
                ok: true,
                label:
                    target.innerText
                    || target.textContent,
                clickedTag:
                    clickable.tagName,
                clickedClass:
                    String(
                        clickable.className || ""
                    )
            }};
        }})();
        """

        response = await self.client.send(
            "Runtime.evaluate",
            {
                "expression": script,
                "returnByValue": True,
            },
        )

        result = self._extract_runtime_value(
            response
        )

        if isinstance(result, dict):
            return result

        return {
            "ok": False,
            "reason": "invalid-runtime-result",
            "value": result,
        }

    async def _wait_for_asset(
        self,
        expected_display_name: str,
        timeout: float,
    ) -> bool:
        """
        Ждёт подтверждения переключения актива.
        """
        deadline = (
            asyncio.get_running_loop().time()
            + timeout
        )

        while (
            asyncio.get_running_loop().time()
            < deadline
        ):
            current = await self.get_current_asset()

            if self._asset_names_equal(
                current,
                expected_display_name,
            ):
                return True

            await asyncio.sleep(0.25)

        return False

    @staticmethod
    def asset_to_display_name(
        asset: str,
    ) -> str:
        """
        Преобразует EURUSD_otc в EUR/USD OTC.
        """
        value = asset.strip()

        is_otc = value.lower().endswith(
            "_otc"
        )

        if is_otc:
            value = value[:-4]

        clean = (
            value
            .replace("/", "")
            .replace("_", "")
            .replace(" ", "")
            .upper()
        )

        if len(clean) == 6:
            result = (
                f"{clean[:3]}/"
                f"{clean[3:]}"
            )
        else:
            result = clean

        if is_otc:
            result += " OTC"

        return result

    @staticmethod
    def _asset_names_equal(
        first: str | None,
        second: str | None,
    ) -> bool:
        """
        Сравнивает названия активов независимо от формата.
        """
        if not first or not second:
            return False

        def normalize(value: str) -> str:
            return (
                value
                .upper()
                .replace("/", "")
                .replace("_", "")
                .replace(" ", "")
            )

        return normalize(first) == normalize(second)

    @staticmethod
    def _extract_runtime_value(
        response: dict[str, Any],
    ) -> Any:
        """
        Извлекает значение из Runtime.evaluate.
        """
        return (
            response
            .get("result", {})
            .get("result", {})
            .get("value")
        )