"""Harici bildirim kanalları: genel webhook (JSON POST) ve Telegram.

Bildirimler ayrı bir thread'de gönderilir; video işleme hattını yavaşlatmaz.
"""
from __future__ import annotations

import logging
import threading

import requests

log = logging.getLogger(__name__)


class Notifier:
    def __init__(self, webhook_url: str = "", telegram_bot_token: str = "", telegram_chat_id: str = ""):
        self.webhook_url = webhook_url.strip()
        self.tg_token = telegram_bot_token.strip()
        self.tg_chat = str(telegram_chat_id).strip()

    @property
    def enabled(self) -> bool:
        return bool(self.webhook_url or (self.tg_token and self.tg_chat))

    def send(self, record: dict) -> None:
        if not self.enabled:
            return
        threading.Thread(target=self._send_sync, args=(record,), daemon=True).start()

    def _send_sync(self, record: dict) -> None:
        if self.webhook_url:
            try:
                requests.post(self.webhook_url, json=record, timeout=10)
            except Exception:
                log.exception("Webhook bildirimi gönderilemedi")
        if self.tg_token and self.tg_chat:
            try:
                text = (
                    f"🚨 <b>{record['title']}</b>\n"
                    f"🚚 {record['camera_name']}\n"
                    f"🕐 {record['time_str']}\n"
                    f"ℹ️ {record['message']}"
                )
                requests.post(
                    f"https://api.telegram.org/bot{self.tg_token}/sendMessage",
                    json={"chat_id": self.tg_chat, "text": text, "parse_mode": "HTML"},
                    timeout=10,
                )
            except Exception:
                log.exception("Telegram bildirimi gönderilemedi")
