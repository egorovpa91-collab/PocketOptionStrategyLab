import base64
import json


class Parser:

    def __init__(self):
        pass

    def parse(self, payload):

        if not payload:
            return None

        if payload.startswith("0"):
            return None

        if payload.startswith("40"):
            return None

        if payload.startswith("42"):
            return None

        try:
            decoded = base64.b64decode(payload).decode("utf-8")
        except Exception:
            return None

        return decoded