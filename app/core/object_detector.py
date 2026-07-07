"""YOLOv8 nesne tespiti: cep telefonu (COCO) + sigara (özel model, opsiyonel).

- Varsayılan `yolov8n.pt` COCO modeli "cell phone" (id 67) sınıfını tanır.
- Sigara/e-sigara için Kaggle/Roboflow veri setiyle eğitilmiş özel bir model
  `detection.custom_model` ile eklenebilir (bkz. training/README.md).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np

log = logging.getLogger(__name__)

COCO_CELL_PHONE = "cell phone"
CIGARETTE_ALIASES = {"cigarette", "cig", "smoke", "smoking", "vape", "e-cigarette"}
# COCO'da hazır bulunan içecek kapları: bardak/kupa, şişe, cam bardak
DRINK_ALIASES = {"cup", "bottle", "wine glass", "mug", "glass", "drink", "tea"}


@dataclass
class Detection:
    label: str          # "phone" | "cigarette" | "drink"
    confidence: float
    box: tuple[int, int, int, int]  # x1, y1, x2, y2


class ObjectDetector:
    def __init__(
        self,
        base_model: str = "yolov8n.pt",
        custom_model: str = "",
        phone_conf: float = 0.45,
        cigarette_conf: float = 0.40,
        drink_conf: float = 0.35,
    ):
        from ultralytics import YOLO  # ağır import; burada tutulur

        self.phone_conf = phone_conf
        self.cigarette_conf = cigarette_conf
        self.drink_conf = drink_conf
        self._base = YOLO(base_model)
        self._custom = None
        if custom_model:
            try:
                self._custom = YOLO(custom_model)
                log.info("Özel model yüklendi: %s", custom_model)
            except Exception:
                log.exception("Özel model yüklenemedi: %s", custom_model)

    def detect(self, frame_bgr: np.ndarray) -> list[Detection]:
        detections: list[Detection] = []
        detections += self._run(self._base, frame_bgr)
        if self._custom is not None:
            detections += self._run(self._custom, frame_bgr)
        return detections

    def debug_all(self, frame_bgr: np.ndarray, conf: float = 0.15) -> list[dict]:
        """Eşik filtrelemeden, modellerin gördüğü TÜM sınıfları döndürür.

        Ayar/teşhis için: bardak neden algılanmıyor sorusuna yanıt verir.
        """
        out: list[dict] = []
        models = [("coco", self._base)] + ([("custom", self._custom)] if self._custom else [])
        for tag, model in models:
            for r in model.predict(frame_bgr, verbose=False, conf=conf):
                if r.boxes is None:
                    continue
                for b in r.boxes:
                    out.append({
                        "model": tag,
                        "class": str(r.names.get(int(b.cls[0]), "?")),
                        "conf": round(float(b.conf[0]), 3),
                        "box": [int(v) for v in b.xyxy[0]],
                    })
        return sorted(out, key=lambda d: -d["conf"])

    def _run(self, model, frame_bgr: np.ndarray) -> list[Detection]:
        out: list[Detection] = []
        results = model.predict(
            frame_bgr, verbose=False,
            conf=min(self.phone_conf, self.cigarette_conf, self.drink_conf),
        )
        for r in results:
            names = r.names
            if r.boxes is None:
                continue
            for b in r.boxes:
                cls_name = str(names.get(int(b.cls[0]), "")).lower()
                conf = float(b.conf[0])
                label: Optional[str] = None
                if cls_name == COCO_CELL_PHONE and conf >= self.phone_conf:
                    label = "phone"
                elif cls_name in CIGARETTE_ALIASES and conf >= self.cigarette_conf:
                    label = "cigarette"
                elif cls_name in DRINK_ALIASES and conf >= self.drink_conf:
                    label = "drink"
                if label is None:
                    continue
                x1, y1, x2, y2 = (int(v) for v in b.xyxy[0])
                out.append(Detection(label=label, confidence=conf, box=(x1, y1, x2, y2)))
        return out
