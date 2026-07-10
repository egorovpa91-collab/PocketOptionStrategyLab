import subprocess
import time
import requests


class PocketConnection:
    """
    Запускает браузер и ищет вкладку Pocket Option
    """

    def __init__(
        self,
        browser_path: str,
        port: int = 9222
    ):
        self.browser_path = browser_path
        self.port = port


    def start_browser(self):

        subprocess.Popen(
            [
                self.browser_path,
                f"--remote-debugging-port={self.port}"
            ]
        )

        print("✓ Браузер запущен")

        time.sleep(5)


    def find_pocket_tab(self):

        url = (
            f"http://127.0.0.1:"
            f"{self.port}/json"
        )

        tabs = requests.get(url).json()

        for tab in tabs:
            if "pocketoption" in tab.get(
                "url",
                ""
            ):
                print("✓ Pocket Option найден")

                return tab[
                    "webSocketDebuggerUrl"
                ]

        return None