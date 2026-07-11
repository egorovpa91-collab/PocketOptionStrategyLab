from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from .websocket import CDPClient


class SubscriptionManager:
    """
    Переключает активы Pocket Option через интерфейс страницы.

    В строку поиска вводится внутреннее имя актива:

        EURUSD_otc

    Pocket Option может автоматически преобразовать его:

        eurusd_otc

    Сравнение выполняется без учёта регистра.
    """

    CURRENT_ASSET_SELECTOR = "span.current-symbol"
    ACTIVE_MODAL_SELECTOR = ".drop-down-modal-wrap.active"
    SEARCH_FIELD_SELECTOR = "input.search__field"
    ASSET_LABEL_SELECTOR = "span.alist__label"

    def __init__(
        self,
        client: CDPClient,
        period: int = 60,
        history_seconds: int = 9_000,
    ) -> None:
        """Инициализирует менеджер переключения активов."""
        self.client = client
        self.period = period
        self.history_seconds = history_seconds
        self.current_asset: str | None = None

    async def install_websocket_interceptor(self) -> None:
        """
        Оставлен для совместимости со Scanner.

        Переключение активов выполняется через интерфейс страницы.
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
            asset: Внутреннее имя актива, например EURUSD_otc.
        """
        normalized_asset = self.normalize_internal_asset(asset)
        display_name = self.asset_to_display_name(normalized_asset)

        print(
            f"→ Запрошен актив: {normalized_asset} | "
            f"поиск: {normalized_asset} | "
            f"ожидаем: {display_name}"
        )

        interface_ready = await self.wait_for_interface(
            timeout=25.0,
        )

        if not interface_ready:
            raise RuntimeError(
                "Интерфейс Pocket Option не загрузился: "
                "элемент текущего актива не найден"
            )

        current_asset = await self.get_current_asset()

        if self._asset_names_equal(
            current_asset,
            display_name,
        ):
            self.current_asset = normalized_asset

            print(
                f"→ Актив уже открыт: {display_name}"
            )
            return

        await self._open_asset_list()

        await self._fill_search_field(
            normalized_asset
        )

        found = await self._wait_for_filtered_asset(
            display_name=display_name,
            timeout=5.0,
        )

        if not found:
            visible_assets = await self._get_visible_asset_names()

            raise RuntimeError(
                f"Актив {display_name} не найден после "
                f"поиска '{normalized_asset}'. "
                f"Видимые элементы: {visible_assets}"
            )

        print(
            f"→ Нажимаем найденный актив: {display_name}"
        )

        dom_result = await self._click_asset_dom(
            display_name
        )

        print(
            "Результат DOM-нажатия:",
            dom_result,
        )

        switched = await self._wait_for_current_asset(
            expected_display_name=display_name,
            timeout=3.0,
        )

        if not switched:
            print(
                "⚠ DOM-нажатие не переключило актив. "
                "Пробуем CDP-клик."
            )

            # Если DOM-клик закрыл список, открываем его повторно.
            if not await self._is_selector_visible(
                self.ACTIVE_MODAL_SELECTOR
            ):
                await self._open_asset_list()
                await self._fill_search_field(
                    normalized_asset
                )

                found_again = await self._wait_for_filtered_asset(
                    display_name=display_name,
                    timeout=5.0,
                )

                if not found_again:
                    raise RuntimeError(
                        f"Актив {display_name} исчез после "
                        "повторного открытия списка"
                    )

            await self._click_asset_native(
                display_name
            )

            switched = await self._wait_for_current_asset(
                expected_display_name=display_name,
                timeout=10.0,
            )

        if not switched:
            actual = await self.get_current_asset()
            modal_open = await self._is_selector_visible(
                self.ACTIVE_MODAL_SELECTOR
            )

            raise RuntimeError(
                f"Интерфейс не переключился на "
                f"{display_name}. "
                f"Сейчас отображается: {actual}. "
                f"Список открыт: {modal_open}"
            )

        self.current_asset = normalized_asset

        print(
            f"✓ Актив переключён: {display_name}"
        )

    async def wait_for_interface(
        self,
        timeout: float = 25.0,
    ) -> bool:
        """Ждёт появления текущего актива в интерфейсе."""
        deadline = (
            asyncio.get_running_loop().time()
            + timeout
        )

        while asyncio.get_running_loop().time() < deadline:
            current_asset = await self.get_current_asset()

            if current_asset:
                return True

            await asyncio.sleep(0.5)

        return False

    async def get_current_asset(self) -> str | None:
        """Возвращает текущий актив из интерфейса."""
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

        value = self._extract_runtime_value(response)

        if isinstance(value, str):
            return value.strip() or None

        return None

    async def _open_asset_list(self) -> None:
        """Открывает окно выбора активов."""
        if await self._is_selector_visible(
            self.ACTIVE_MODAL_SELECTOR
        ):
            return

        point = await self._get_element_center(
            self.CURRENT_ASSET_SELECTOR
        )

        if point is None:
            raise RuntimeError(
                "Не найден элемент текущего актива"
            )

        await self._native_click(
            x=point["x"],
            y=point["y"],
        )

        opened = await self._wait_for_selector(
            selector=self.ACTIVE_MODAL_SELECTOR,
            timeout=5.0,
        )

        if not opened:
            raise RuntimeError(
                "Окно выбора активов не открылось"
            )

    async def _fill_search_field(
        self,
        search_name: str,
    ) -> None:
        """
        Очищает поле поиска и вводит внутреннее имя актива.

        Pocket Option может автоматически перевести значение
        в нижний регистр.
        """
        point = await self._get_element_center(
            self.SEARCH_FIELD_SELECTOR
        )

        if point is None:
            raise RuntimeError(
                "Поле поиска активов не найдено"
            )

        await self._native_click(
            x=point["x"],
            y=point["y"],
        )

        script = f"""
        (() => {{
            const input = document.querySelector(
                {json.dumps(self.SEARCH_FIELD_SELECTOR)}
            );

            if (!input) {{
                return {{
                    ok: false,
                    reason: "search-field-not-found"
                }};
            }}

            const searchValue =
                {json.dumps(search_name)};

            const descriptor =
                Object.getOwnPropertyDescriptor(
                    HTMLInputElement.prototype,
                    "value"
                );

            if (!descriptor || !descriptor.set) {{
                return {{
                    ok: false,
                    reason: "value-setter-not-found"
                }};
            }}

            input.focus();

            descriptor.set.call(input, "");

            input.dispatchEvent(
                new Event("input", {{
                    bubbles: true
                }})
            );

            descriptor.set.call(
                input,
                searchValue
            );

            input.dispatchEvent(
                new InputEvent("input", {{
                    bubbles: true,
                    inputType: "insertText",
                    data: searchValue
                }})
            );

            input.dispatchEvent(
                new Event("change", {{
                    bubbles: true
                }})
            );

            input.dispatchEvent(
                new KeyboardEvent("keyup", {{
                    bubbles: true,
                    key: "c"
                }})
            );

            return {{
                ok: true,
                requested: searchValue,
                actual: input.value
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

        result = self._extract_runtime_value(response)

        if (
            not isinstance(result, dict)
            or not result.get("ok")
        ):
            raise RuntimeError(
                f"Не удалось заполнить поиск: {result}"
            )

        actual_value = str(
            result.get("actual", "")
        ).strip()

        print(
            f"Поиск активов: '{actual_value}'"
        )

        # Pocket Option переводит значение в нижний регистр.
        if actual_value.lower() != search_name.lower():
            raise RuntimeError(
                f"В поле поиска записалось "
                f"'{actual_value}', ожидалось "
                f"'{search_name}'"
            )

        await asyncio.sleep(0.8)

    async def _wait_for_filtered_asset(
        self,
        display_name: str,
        timeout: float,
    ) -> bool:
        """Ждёт появления нужного актива в результатах поиска."""
        deadline = (
            asyncio.get_running_loop().time()
            + timeout
        )

        while asyncio.get_running_loop().time() < deadline:
            if await self._asset_exists(display_name):
                return True

            await asyncio.sleep(0.25)

        return False

    async def _asset_exists(
        self,
        display_name: str,
    ) -> bool:
        """Проверяет наличие актива в результатах поиска."""
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

            return labels.some(
                element =>
                    normalize(
                        element.innerText
                        || element.textContent
                    )
                    === normalize(expected)
            );
        }})();
        """

        response = await self.client.send(
            "Runtime.evaluate",
            {
                "expression": script,
                "returnByValue": True,
            },
        )

        return bool(
            self._extract_runtime_value(response)
        )

    async def _click_asset_dom(
        self,
        display_name: str,
    ) -> dict[str, Any]:
        """Нажимает на ссылку найденного актива через DOM."""
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

            const label = labels.find(
                element =>
                    normalize(
                        element.innerText
                        || element.textContent
                    )
                    === normalize(expected)
            );

            if (!label) {{
                return {{
                    ok: false,
                    reason: "label-not-found"
                }};
            }}

            const link =
                label.closest("a.alist__link");

            const item =
                label.closest("li.alist__item");

            if (!link) {{
                return {{
                    ok: false,
                    reason: "link-not-found"
                }};
            }}

            link.scrollIntoView({{
                block: "center",
                inline: "nearest"
            }});

            link.focus();

            const options = {{
                bubbles: true,
                cancelable: true,
                composed: true,
                view: window,
                button: 0
            }};

            link.dispatchEvent(
                new PointerEvent(
                    "pointerdown",
                    {{
                        ...options,
                        pointerType: "mouse",
                        buttons: 1
                    }}
                )
            );

            link.dispatchEvent(
                new MouseEvent(
                    "mousedown",
                    {{
                        ...options,
                        buttons: 1
                    }}
                )
            );

            link.dispatchEvent(
                new PointerEvent(
                    "pointerup",
                    {{
                        ...options,
                        pointerType: "mouse",
                        buttons: 0
                    }}
                )
            );

            link.dispatchEvent(
                new MouseEvent(
                    "mouseup",
                    {{
                        ...options,
                        buttons: 0
                    }}
                )
            );

            link.dispatchEvent(
                new MouseEvent(
                    "click",
                    {{
                        ...options,
                        buttons: 0,
                        detail: 1
                    }}
                )
            );

            link.click();

            return {{
                ok: true,
                label:
                    label.innerText
                    || label.textContent,
                linkClass:
                    String(link.className || ""),
                itemClass:
                    item
                        ? String(item.className || "")
                        : null
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

        value = self._extract_runtime_value(response)

        if isinstance(value, dict):
            return value

        return {
            "ok": False,
            "reason": "invalid-runtime-result",
            "value": value,
        }

    async def _click_asset_native(
        self,
        display_name: str,
    ) -> None:
        """Выполняет CDP-клик по названию найденного актива."""
        point = await self._get_asset_label_center(
            display_name
        )

        if point is None:
            raise RuntimeError(
                f"Не удалось получить координаты "
                f"актива {display_name}"
            )

        await self._native_click(
            x=point["x"],
            y=point["y"],
        )

    async def _get_asset_label_center(
        self,
        display_name: str,
    ) -> dict[str, float] | None:
        """Возвращает координаты названия найденного актива."""
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

            const label = labels.find(
                element =>
                    normalize(
                        element.innerText
                        || element.textContent
                    )
                    === normalize(expected)
            );

            if (!label) {{
                return null;
            }}

            label.scrollIntoView({{
                block: "center",
                inline: "nearest"
            }});

            const rect = label.getBoundingClientRect();

            if (
                rect.width <= 0
                || rect.height <= 0
            ) {{
                return null;
            }}

            return {{
                x: rect.left + rect.width / 2,
                y: rect.top + rect.height / 2
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

        value = self._extract_runtime_value(response)

        if not isinstance(value, dict):
            return None

        x = value.get("x")
        y = value.get("y")

        if not isinstance(x, (int, float)):
            return None

        if not isinstance(y, (int, float)):
            return None

        return {
            "x": float(x),
            "y": float(y),
        }

    async def _get_element_center(
        self,
        selector: str,
    ) -> dict[str, float] | None:
        """Возвращает координаты центра элемента."""
        script = f"""
        (() => {{
            const element = document.querySelector(
                {json.dumps(selector)}
            );

            if (!element) {{
                return null;
            }}

            element.scrollIntoView({{
                block: "center",
                inline: "center"
            }});

            const rect = element.getBoundingClientRect();

            if (
                rect.width <= 0
                || rect.height <= 0
            ) {{
                return null;
            }}

            return {{
                x: rect.left + rect.width / 2,
                y: rect.top + rect.height / 2
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

        value = self._extract_runtime_value(response)

        if not isinstance(value, dict):
            return None

        x = value.get("x")
        y = value.get("y")

        if not isinstance(x, (int, float)):
            return None

        if not isinstance(y, (int, float)):
            return None

        return {
            "x": float(x),
            "y": float(y),
        }

    async def _native_click(
        self,
        x: float,
        y: float,
    ) -> None:
        """Выполняет клик мышью через CDP."""
        await self.client.send(
            "Input.dispatchMouseEvent",
            {
                "type": "mouseMoved",
                "x": x,
                "y": y,
                "button": "none",
            },
        )

        await asyncio.sleep(0.08)

        await self.client.send(
            "Input.dispatchMouseEvent",
            {
                "type": "mousePressed",
                "x": x,
                "y": y,
                "button": "left",
                "buttons": 1,
                "clickCount": 1,
            },
        )

        await asyncio.sleep(0.12)

        await self.client.send(
            "Input.dispatchMouseEvent",
            {
                "type": "mouseReleased",
                "x": x,
                "y": y,
                "button": "left",
                "buttons": 0,
                "clickCount": 1,
            },
        )

    async def _wait_for_current_asset(
        self,
        expected_display_name: str,
        timeout: float,
    ) -> bool:
        """Ждёт фактического переключения актива."""
        deadline = (
            asyncio.get_running_loop().time()
            + timeout
        )

        while asyncio.get_running_loop().time() < deadline:
            current_asset = await self.get_current_asset()

            if self._asset_names_equal(
                current_asset,
                expected_display_name,
            ):
                return True

            await asyncio.sleep(0.25)

        return False

    async def _wait_for_selector(
        self,
        selector: str,
        timeout: float,
    ) -> bool:
        """Ждёт появления видимого элемента."""
        deadline = (
            asyncio.get_running_loop().time()
            + timeout
        )

        while asyncio.get_running_loop().time() < deadline:
            if await self._is_selector_visible(selector):
                return True

            await asyncio.sleep(0.2)

        return False

    async def _is_selector_visible(
        self,
        selector: str,
    ) -> bool:
        """Проверяет видимость элемента."""
        script = f"""
        (() => {{
            const element = document.querySelector(
                {json.dumps(selector)}
            );

            if (!element) {{
                return false;
            }}

            const style =
                window.getComputedStyle(element);

            const rect =
                element.getBoundingClientRect();

            return (
                style.display !== "none"
                && style.visibility !== "hidden"
                && Number(style.opacity || 1) > 0
                && rect.width > 0
                && rect.height > 0
            );
        }})();
        """

        response = await self.client.send(
            "Runtime.evaluate",
            {
                "expression": script,
                "returnByValue": True,
            },
        )

        return bool(
            self._extract_runtime_value(response)
        )

    async def _get_visible_asset_names(
        self,
    ) -> list[str]:
        """Возвращает видимые активы для диагностики."""
        script = f"""
        (() => {{
            return Array.from(
                document.querySelectorAll(
                    {json.dumps(self.ASSET_LABEL_SELECTOR)}
                )
            )
            .filter(element => {{
                const rect =
                    element.getBoundingClientRect();

                return (
                    rect.width > 0
                    && rect.height > 0
                );
            }})
            .map(element =>
                (
                    element.innerText
                    || element.textContent
                    || ""
                ).trim()
            )
            .filter(Boolean)
            .slice(0, 20);
        }})();
        """

        response = await self.client.send(
            "Runtime.evaluate",
            {
                "expression": script,
                "returnByValue": True,
            },
        )

        value = self._extract_runtime_value(response)

        if not isinstance(value, list):
            return []

        return [
            str(item)
            for item in value
        ]

    @staticmethod
    def normalize_internal_asset(
        asset: str,
    ) -> str:
        """
        Приводит имя к внутреннему формату Pocket Option.

        Примеры:
            EURUSD_otc -> EURUSD_otc
            EURUSD OTC -> EURUSD_otc
            EUR/USD OTC -> EURUSD_otc
        """
        original = asset.strip()

        if not original:
            raise ValueError(
                "Название актива не может быть пустым"
            )

        upper_value = original.upper()
        is_otc = upper_value.endswith("OTC")

        without_otc = re.sub(
            r"(?:_|\s|-)?OTC$",
            "",
            upper_value,
        )

        clean_code = re.sub(
            r"[^A-Z]",
            "",
            without_otc,
        )

        if len(clean_code) != 6:
            raise ValueError(
                f"Некорректный актив '{asset}'. "
                f"Код после очистки: '{clean_code}'"
            )

        if is_otc:
            return f"{clean_code}_otc"

        return clean_code

    @classmethod
    def asset_to_display_name(
        cls,
        asset: str,
    ) -> str:
        """
        Преобразует внутреннее имя в отображаемое.

        EURUSD_otc -> EUR/USD OTC
        """
        normalized_asset = cls.normalize_internal_asset(
            asset
        )

        is_otc = normalized_asset.endswith("_otc")

        clean_code = (
            normalized_asset[:-4]
            if is_otc
            else normalized_asset
        )

        display_name = (
            f"{clean_code[:3]}/"
            f"{clean_code[3:]}"
        )

        if is_otc:
            display_name += " OTC"

        return display_name

    @staticmethod
    def _asset_names_equal(
        first: str | None,
        second: str | None,
    ) -> bool:
        """Сравнивает названия независимо от оформления."""
        if not first or not second:
            return False

        def normalize(value: str) -> str:
            return re.sub(
                r"[^A-Z]",
                "",
                value.upper(),
            )

        return normalize(first) == normalize(second)

    @staticmethod
    def _extract_runtime_value(
        response: dict[str, Any],
    ) -> Any:
        """Извлекает value из ответа Runtime.evaluate."""
        return (
            response
            .get("result", {})
            .get("result", {})
            .get("value")
        )