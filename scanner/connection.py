import subprocess
import time

import requests


class PocketConnection:
    """Запускает Brave и ищет вкладку Pocket Option."""

    def __init__(
        self,
        browser_path: str,
        port: int = 9222,
    ):
        self.browser_path = browser_path
        self.port = port
        self.browser_process: subprocess.Popen | None = None

    def start_browser(self) -> None:
        """Запускает Brave с последней открытой сессией."""

        self.browser_process = subprocess.Popen(
            [
                self.browser_path,
                f"--remote-debugging-port={self.port}",
                "--restore-last-session",
            ]
        )

        print("✓ Brave запущен с последней сессией")
        time.sleep(5)

    def find_pocket_tab(self) -> str | None:
        """Возвращает WebSocket URL вкладки Pocket Option."""

        url = f"http://127.0.0.1:{self.port}/json"

        try:
            tabs = requests.get(
                url,
                timeout=5,
            ).json()
        except requests.RequestException as error:
            print(f"Ошибка подключения к CDP: {error}")
            return None

        for tab in tabs:
            page_url = tab.get("url", "").lower()

            if "pocketoption" in page_url:
                print("✓ Pocket Option найден")
                return tab.get("webSocketDebuggerUrl")

        return None

    def close_browser(self) -> None:
        """Закрывает Brave, запущенный программой."""

        if self.browser_process is None:
            return

        if self.browser_process.poll() is not None:
            return

        print("Закрываем Brave...")

        subprocess.run(
            [
                "taskkill",
                "/PID",
                str(self.browser_process.pid),
                "/T",
                "/F",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.browser_process = None
        print("✓ Brave закрыт")