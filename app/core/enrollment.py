"""Sürücü tanıtım (enrollment) servisi.

Canlı görüntüden, yüz görünür olduğu anlarda aralıklı 10 fotoğraf yakalar,
media/drivers/<id>/ altına kaydeder ve kaydı 'pending' (isim bekliyor)
durumuna geçirir. Admin panelde isimlendirmeden bu durum kapanmaz.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

import cv2

from app.stores import DriverStore

log = logging.getLogger(__name__)

PHOTO_COUNT = 10
CAPTURE_INTERVAL_SEC = 0.7   # iki fotoğraf arası minimum süre
CAPTURE_TIMEOUT_SEC = 60     # yüz hiç görünmezse vazgeçme süresi
DRIVERS_MEDIA_DIR = Path("media/drivers")


class EnrollmentService:
    def __init__(self, driver_store: DriverStore):
        self.store = driver_store
        self._active: set[str] = set()   # şu an yakalama yapılan kamera id'leri
        self._lock = threading.Lock()

    def start(self, pipeline, equipment: str | None) -> dict | None:
        """Verilen kamera hattı için yakalamayı başlatır; kaydı döndürür.

        Aynı kamerada eşzamanlı ikinci yakalama başlatılamaz (None döner).
        """
        with self._lock:
            if pipeline.camera_id in self._active:
                return None
            self._active.add(pipeline.camera_id)

        record = self.store.create(pipeline.camera_id, equipment)
        threading.Thread(
            target=self._capture_loop,
            args=(pipeline, record["id"]),
            daemon=True,
            name=f"enroll-{record['id']}",
        ).start()
        return record

    def _capture_loop(self, pipeline, driver_id: str) -> None:
        photo_dir = DRIVERS_MEDIA_DIR / driver_id
        photo_dir.mkdir(parents=True, exist_ok=True)
        photos: list[str] = []
        deadline = time.time() + CAPTURE_TIMEOUT_SEC
        last_shot = 0.0
        try:
            while len(photos) < PHOTO_COUNT and time.time() < deadline:
                now = time.time()
                if now - last_shot < CAPTURE_INTERVAL_SEC:
                    time.sleep(0.1)
                    continue
                frame = pipeline.latest_raw()
                if frame is None or not pipeline.engine.state.face_visible:
                    time.sleep(0.15)
                    continue
                name = f"{len(photos)+1:02d}.jpg"
                if cv2.imwrite(str(photo_dir / name), frame):
                    photos.append(f"/media/drivers/{driver_id}/{name}")
                    last_shot = now
                    self.store.update(driver_id, photos=photos)

            status = "pending" if len(photos) >= PHOTO_COUNT else "failed"
            self.store.update(driver_id, photos=photos, status=status)
            log.info(
                "Sürücü yakalama bitti [%s]: %d fotoğraf, durum=%s",
                driver_id, len(photos), status,
            )
        except Exception:
            log.exception("Sürücü yakalama hatası [%s]", driver_id)
            self.store.update(driver_id, status="failed")
        finally:
            with self._lock:
                self._active.discard(pipeline.camera_id)
