"""Uyarı yöneticisi: tekrar süzme (cooldown), geçmiş, kanıt görüntüsü,
WebSocket yayını ve harici bildirim kanalları (webhook / Telegram).
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from collections import deque
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from app.core.decision_engine import Event, RISK_POINTS
from app.alerts.notifiers import Notifier

log = logging.getLogger(__name__)


class AlertManager:
    def __init__(self, cfg: dict):
        self.cooldown = cfg.get("cooldown_sec", 30)
        self.save_snapshots = cfg.get("save_snapshots", True)
        self.snapshot_dir = Path(cfg.get("snapshot_dir", "media/alerts"))
        self.history: deque[dict] = deque(maxlen=cfg.get("history_size", 500))
        self._last_fired: dict[tuple[str, str], float] = {}
        # risk skoru: kamera -> [(zaman, puan), ...]; üstel sönümlü toplam
        self.risk_half_life = cfg.get("risk_half_life_sec", 600)
        self.risk_gain = cfg.get("risk_gain", 1.0)  # puan çarpanı (artış hızı)
        self._risk_events: dict[str, deque] = {}
        self._lock = threading.Lock()
        self._ws_clients: set = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._notifier = Notifier(
            webhook_url=cfg.get("webhook_url", ""),
            telegram_bot_token=cfg.get("telegram_bot_token", ""),
            telegram_chat_id=cfg.get("telegram_chat_id", ""),
        )
        if self.save_snapshots:
            self.snapshot_dir.mkdir(parents=True, exist_ok=True)

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """FastAPI event loop'u; işçi thread'lerden WS yayını için gerekir."""
        self._loop = loop

    # --- WebSocket istemcileri (server.py yönetir) -------------------------
    def register_ws(self, ws) -> None:
        self._ws_clients.add(ws)

    def unregister_ws(self, ws) -> None:
        self._ws_clients.discard(ws)

    # --- ana giriş: işçi thread'lerden çağrılır ------------------------------
    def handle(self, events: list[Event], frame: Optional[np.ndarray] = None) -> None:
        for ev in events:
            key = (ev.camera_id, ev.type)
            now = ev.timestamp
            with self._lock:
                last = self._last_fired.get(key, 0.0)
                if now - last < self.cooldown:
                    continue
                self._last_fired[key] = now

            with self._lock:
                self._risk_events.setdefault(ev.camera_id, deque()).append(
                    (now, RISK_POINTS.get(ev.type, 10) * self.risk_gain)
                )

            record = asdict(ev)
            record["risk"] = self.risk(ev.camera_id, now)
            record["time_str"] = datetime.fromtimestamp(now).strftime("%d.%m.%Y %H:%M:%S")
            record["snapshot"] = self._save_snapshot(ev, frame) if frame is not None else None
            with self._lock:
                self.history.appendleft(record)

            log.warning("ALARM [%s] %s - %s", ev.camera_name, ev.title, ev.message)
            self._broadcast(record)
            self._notifier.send(record)

    def _save_snapshot(self, ev: Event, frame: np.ndarray) -> Optional[str]:
        if not self.save_snapshots:
            return None
        try:
            ts = datetime.fromtimestamp(ev.timestamp).strftime("%Y%m%d_%H%M%S")
            name = f"{ev.camera_id}_{ev.type}_{ts}.jpg"
            cv2.imwrite(str(self.snapshot_dir / name), frame)
            return f"/media/alerts/{name}"
        except Exception:
            log.exception("Kanıt görüntüsü kaydedilemedi")
            return None

    def _broadcast(self, record: dict) -> None:
        if self._loop is None or not self._ws_clients:
            return
        payload = json.dumps({"kind": "alert", "data": record}, ensure_ascii=False)

        async def _send() -> None:
            dead = []
            for ws in list(self._ws_clients):
                try:
                    await ws.send_text(payload)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self._ws_clients.discard(ws)

        asyncio.run_coroutine_threadsafe(_send(), self._loop)

    def risk(self, camera_id: str, now: Optional[float] = None) -> int:
        """0-100 arası sürücü risk puanı.

        Her alarm türü ağırlığı kadar puan ekler; puanlar 'risk_half_life_sec'
        yarılanma süresiyle üstel söner. Uyarı gelmedikçe skor kendiliğinden düşer.
        """
        now = now if now is not None else time.time()
        with self._lock:
            dq = self._risk_events.get(camera_id)
            if not dq:
                return 0
            # ~6 yarılanma süresinden eski kayıtların katkısı %2'nin altı: temizle
            cutoff = now - 6 * self.risk_half_life
            while dq and dq[0][0] < cutoff:
                dq.popleft()
            total = sum(
                p * 0.5 ** ((now - t) / self.risk_half_life) for t, p in dq
            )
        return min(100, round(total))

    def get_history(self, limit: int = 100) -> list[dict]:
        with self._lock:
            return list(self.history)[:limit]
