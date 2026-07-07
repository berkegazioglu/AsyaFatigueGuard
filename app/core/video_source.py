"""Kamera / RTSP / video dosyası okuyucu.

Mevcut kamera donanımına müdahale etmez: OpenCV ile RTSP, HTTP, USB veya
dosya kaynağından kare çeker. Bağlantı koptuğunda otomatik yeniden bağlanır.
"""
from __future__ import annotations

import logging
import time
from typing import Optional, Union

import cv2
import numpy as np

log = logging.getLogger(__name__)


class VideoSource:
    def __init__(self, source: Union[int, str], reconnect_delay: float = 5.0):
        self.source = source
        self.reconnect_delay = reconnect_delay
        self._cap: Optional[cv2.VideoCapture] = None
        self._is_file = isinstance(source, str) and not source.lower().startswith(
            ("rtsp://", "http://", "https://")
        )

    def _open(self) -> bool:
        if self._cap is not None:
            self._cap.release()
        src = self.source
        if isinstance(src, str) and src.lower().startswith("rtsp://"):
            # TCP, RTSP'de kare kaybını azaltır
            self._cap = cv2.VideoCapture(src, cv2.CAP_FFMPEG)
            self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)
        else:
            self._cap = cv2.VideoCapture(src)
        ok = self._cap.isOpened()
        if ok:
            log.info("Kamera kaynağı açıldı: %s", src)
        else:
            log.warning("Kamera kaynağı açılamadı: %s", src)
        return ok

    def read(self) -> Optional[np.ndarray]:
        """Bir kare döndürür; kaynak kapalıysa/koptuysa yeniden bağlanmayı dener.

        Kare alınamazsa None döner (çağıran döngü beklemeli).
        """
        if self._cap is None or not self._cap.isOpened():
            if not self._open():
                time.sleep(self.reconnect_delay)
                return None
        ok, frame = self._cap.read()
        if not ok or frame is None:
            if self._is_file:
                # video dosyası bitti -> başa sar (demo modu)
                self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, frame = self._cap.read()
                if ok:
                    return frame
            log.warning("Kare alınamadı, yeniden bağlanılacak: %s", self.source)
            self._cap.release()
            self._cap = None
            time.sleep(self.reconnect_delay)
            return None
        return frame

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
