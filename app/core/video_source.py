"""Kamera / RTSP / video dosyası okuyucu.

Mevcut kamera donanımına müdahale etmez: OpenCV ile RTSP, HTTP, USB veya
dosya kaynağından kare çeker. Bağlantı koptuğunda otomatik yeniden bağlanır.

Kaynak türleri (config: cameras[].source):
- 0, 1, ...                  : kamera indeksi (Windows'ta DirectShow sırası)
- "Insta360 Ace Pro"         : kamera ADI (Windows; sıralama değişse de doğru
                               donanım açılır, sanal kameralara karışmaz)
- "rtsp://..." / "http://..." : IP kamera akışı
- "video.mp4"                : dosya (demo; bitince başa sarar)
"""
from __future__ import annotations

import logging
import platform
import time
from pathlib import Path
from typing import Optional, Union

import cv2
import numpy as np

log = logging.getLogger(__name__)


def find_device_index(name: str) -> Optional[int]:
    """Kamera adını DirectShow indeksine çevirir (yalnız Windows).

    Ad, cihaz adının içinde geçiyorsa eşleşir (büyük/küçük harf duyarsız).
    """
    if platform.system() != "Windows":
        return None
    try:
        from pygrabber.dshow_graph import FilterGraph

        devices = FilterGraph().get_input_devices()
    except Exception:
        log.exception("Kamera listesi alınamadı (pygrabber)")
        return None
    low = name.lower()
    for i, dev in enumerate(devices):
        if low in dev.lower():
            log.info("Kamera adı eşleşti: '%s' -> [%d] %s", name, i, dev)
            return i
    log.warning("'%s' adında kamera bulunamadı. Mevcutlar: %s", name, devices)
    return None


class VideoSource:
    def __init__(self, source: Union[int, str], reconnect_delay: float = 5.0):
        self.source = source
        self.reconnect_delay = reconnect_delay
        self._cap: Optional[cv2.VideoCapture] = None
        self._is_url = isinstance(source, str) and source.lower().startswith(
            ("rtsp://", "http://", "https://")
        )
        self._is_file = (
            isinstance(source, str) and not self._is_url and Path(source).exists()
        )
        self._is_index = isinstance(source, int) or (
            isinstance(source, str) and source.isdigit()
        )
        # indeks/URL/dosya değilse: kamera ADI (Windows DirectShow)
        self._is_name = (
            isinstance(source, str)
            and not (self._is_url or self._is_file or self._is_index)
        )

    def _open(self) -> bool:
        if self._cap is not None:
            self._cap.release()
        src = self.source
        if self._is_url and str(src).lower().startswith("rtsp://"):
            # TCP, RTSP'de kare kaybını azaltır
            self._cap = cv2.VideoCapture(str(src), cv2.CAP_FFMPEG)
            self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)
        elif self._is_name:
            idx = find_device_index(str(src))
            if idx is None:
                return False
            self._cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
        elif self._is_index:
            idx = int(src)
            # Windows'ta DirectShow: pygrabber listesindeki sırayla aynı
            if platform.system() == "Windows":
                self._cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
            else:
                self._cap = cv2.VideoCapture(idx)
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
