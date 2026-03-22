from __future__ import annotations

import os
from threading import Lock

import requests


class TelegramNotifier:
    def __init__(self) -> None:
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        self.enabled = bool(self.bot_token and self.chat_id)
        self.timeout = float(os.getenv("TELEGRAM_TIMEOUT_SEC", "10"))
        self.prefix = os.getenv("TELEGRAM_PREFIX", "Unhedged Bot").strip()
        self._session = requests.Session()
        self._lock = Lock()

    def send(self, message: str) -> None:
        if not self.enabled or not message:
            return

        payload = {
            "chat_id": self.chat_id,
            "text": f"{self.prefix}\n{message}",
            "disable_web_page_preview": True,
        }
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"

        try:
            with self._lock:
                response = self._session.post(url, json=payload, timeout=self.timeout)
                response.raise_for_status()
        except Exception:
            # Notification failure must never break trading or UI flow.
            return


telegram_notifier = TelegramNotifier()
