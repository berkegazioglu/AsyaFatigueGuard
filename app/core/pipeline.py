"""Kamera başına işleme hattı (görseldeki 'İkili İşleme / Parallel Processing').

Her kamera kendi thread'inde çalışır:
  Kanal 1: MediaPipe -> EAR, MAR, baş pozu
  Kanal 2: YOLO      -> telefon / sigara (her N karede bir, CPU tasarrufu)
Sonuçlar karar motoruna verilir; alarm olayları AlertManager'a iletilir.
Son işlenmiş kare JPEG olarak saklanır (panelde MJPEG canlı yayın için).
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import asdict
from typing import Optional

import cv2
import numpy as np

from app.core.decision_engine import DecisionEngine
from app.core.face_analyzer import FaceAnalyzer
from app.core.object_detector import Detection, ObjectDetector
from app.core.video_source import VideoSource
from app.alerts.manager import AlertManager

log = logging.getLogger(__name__)

GREEN, YELLOW, RED = (80, 200, 120), (0, 200, 255), (60, 60, 230)


class CameraPipeline(threading.Thread):
    def __init__(
        self,
        camera_cfg: dict,
        video_cfg: dict,
        det_cfg: dict,
        detector: ObjectDetector,
        alert_manager: AlertManager,
    ):
        super().__init__(daemon=True, name=f"pipeline-{camera_cfg['id']}")
        self.camera_id = camera_cfg["id"]
        self.camera_name = camera_cfg.get("name", self.camera_id)
        self.source = VideoSource(
            camera_cfg["source"], video_cfg.get("reconnect_delay_sec", 5)
        )
        self.process_width = video_cfg.get("process_width", 640)
        self.yolo_every = max(1, video_cfg.get("yolo_every_n_frames", 3))
        self.face = FaceAnalyzer()
        self.detector = detector
        self.engine = DecisionEngine(self.camera_id, self.camera_name, det_cfg)
        self.alerts = alert_manager

        self._stop = threading.Event()
        self._jpeg_lock = threading.Lock()
        self._latest_jpeg: Optional[bytes] = None
        self._latest_raw: Optional[np.ndarray] = None
        self._last_detections: list[Detection] = []
        self.fps = 0.0
        self.online = False

    # --- dışarıya sunulanlar -------------------------------------------------
    def latest_jpeg(self) -> Optional[bytes]:
        with self._jpeg_lock:
            return self._latest_jpeg

    def latest_raw(self) -> Optional[np.ndarray]:
        with self._jpeg_lock:
            return None if self._latest_raw is None else self._latest_raw.copy()

    def status(self) -> dict:
        return {
            "id": self.camera_id,
            "name": self.camera_name,
            "online": self.online,
            "fps": round(self.fps, 1),
            "risk": self.alerts.risk(self.camera_id),
            "state": asdict(self.engine.state),
        }

    def stop(self) -> None:
        self._stop.set()

    # --- ana döngü ------------------------------------------------------------
    def run(self) -> None:
        log.info("[%s] işleme hattı başladı", self.camera_id)
        frame_no = 0
        t_prev = time.time()
        while not self._stop.is_set():
            frame = self.source.read()
            if frame is None:
                self.online = False
                self._render_offline()
                continue
            self.online = True
            frame_no += 1

            # ön işleme: yeniden boyutlandır
            h, w = frame.shape[:2]
            if w > self.process_width:
                scale = self.process_width / w
                frame = cv2.resize(frame, (self.process_width, int(h * scale)))

            # Kanal 1: yüz analizi (her kare)
            metrics = self.face.analyze(frame)

            # Kanal 2: nesne tespiti (her N karede bir)
            if frame_no % self.yolo_every == 0:
                self._last_detections = self.detector.detect(frame)

            # karar mekanizması
            events = self.engine.update(metrics, self._last_detections)

            # görselleştirme + alarm
            annotated = self._annotate(frame, metrics, self._last_detections)
            if events:
                self.alerts.handle(events, annotated)

            ok, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ok:
                with self._jpeg_lock:
                    self._latest_jpeg = buf.tobytes()
                    self._latest_raw = frame

            now = time.time()
            dt = now - t_prev
            if dt > 0:
                self.fps = 0.9 * self.fps + 0.1 * (1.0 / dt)
            t_prev = now

        self.source.release()
        self.face.close()
        log.info("[%s] işleme hattı durdu", self.camera_id)

    # --- çizim yardımcıları ----------------------------------------------------
    def _annotate(self, frame: np.ndarray, metrics, detections: list[Detection]) -> np.ndarray:
        out = frame.copy()
        s = self.engine.state
        alarm = bool(s.active_events)

        if metrics is not None:
            color = RED if alarm else GREEN
            for i in range(0, len(metrics.landmarks), 8):
                x, y = metrics.landmarks[i]
                cv2.circle(out, (int(x), int(y)), 1, color, -1)
            hud = f"EAR:{s.ear:.2f}  MAR:{s.mar:.2f}  Pitch:{s.pitch:.0f}  Yaw:{s.yaw:.0f}  PERCLOS:{s.perclos:.2f}"
        else:
            hud = "YUZ ALGILANAMADI"
        cv2.putText(out, hud, (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                    YELLOW if metrics is None else (255, 255, 255), 1, cv2.LINE_AA)

        labels = {"phone": ("TELEFON", RED), "cigarette": ("SIGARA", RED),
                  "drink": ("ICECEK", YELLOW)}
        for d in detections:
            x1, y1, x2, y2 = d.box
            label, color = labels.get(d.label, (d.label.upper(), RED))
            cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
            cv2.putText(out, f"{label} {d.confidence:.2f}", (x1, max(14, y1 - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2, cv2.LINE_AA)

        if alarm:
            cv2.rectangle(out, (0, 0), (out.shape[1] - 1, out.shape[0] - 1), RED, 6)
        return out

    def _render_offline(self) -> None:
        img = np.zeros((360, 640, 3), dtype=np.uint8)
        cv2.putText(img, "KAMERA BAGLANTISI YOK", (140, 180),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2, cv2.LINE_AA)
        ok, buf = cv2.imencode(".jpg", img)
        if ok:
            with self._jpeg_lock:
                self._latest_jpeg = buf.tobytes()
