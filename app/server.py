"""FastAPI sunucusu: canlı izleme paneli, MJPEG yayın, WebSocket anlık uyarı,
REST durum/geçmiş uçları ve kanıt görüntüleri.
"""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.config import Config
from app.core.object_detector import ObjectDetector
from app.core.pipeline import CameraPipeline
from app.alerts.manager import AlertManager

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


def create_app(cfg: Config) -> FastAPI:
    alert_manager = AlertManager(cfg.alerts)
    detector = ObjectDetector(
        base_model=cfg.det("yolo_model", "yolov8n.pt"),
        custom_model=cfg.det("custom_model", ""),
        phone_conf=cfg.det("phone_conf", 0.45),
        cigarette_conf=cfg.det("cigarette_conf", 0.40),
        drink_conf=cfg.det("drink_conf", 0.35),
    )
    pipelines: dict[str, CameraPipeline] = {}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        alert_manager.set_loop(asyncio.get_running_loop())
        for cam in cfg.cameras:
            p = CameraPipeline(cam, cfg.video, cfg.detection, detector, alert_manager)
            pipelines[p.camera_id] = p
            p.start()
        log.info("%d kamera hattı başlatıldı", len(pipelines))
        yield
        for p in pipelines.values():
            p.stop()

    app = FastAPI(title="AsyaFatigueGuard DMS", lifespan=lifespan)

    snapshot_dir = Path(cfg.alerts.get("snapshot_dir", "media/alerts"))
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/media/alerts", StaticFiles(directory=snapshot_dir), name="snapshots")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    async def index():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/status")
    async def status():
        return {"cameras": [p.status() for p in pipelines.values()]}

    @app.get("/api/alerts")
    async def alerts(limit: int = 100):
        return {"alerts": alert_manager.get_history(limit)}

    @app.get("/api/debug/{camera_id}")
    async def debug_detections(camera_id: str, conf: float = 0.15):
        """Modellerin o anki karede gördüğü TÜM sınıflar (eşik ayarı için)."""
        pipeline = pipelines.get(camera_id)
        if pipeline is None:
            return {"error": "kamera bulunamadı"}
        frame = pipeline.latest_raw()
        if frame is None:
            return {"error": "henüz kare yok"}
        detections = await asyncio.to_thread(detector.debug_all, frame, conf)
        return {"detections": detections}

    @app.get("/stream/{camera_id}")
    async def stream(camera_id: str):
        pipeline = pipelines.get(camera_id)
        if pipeline is None:
            return {"error": "kamera bulunamadı"}

        async def gen():
            boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
            while True:
                jpeg = pipeline.latest_jpeg()
                if jpeg is not None:
                    yield boundary + jpeg + b"\r\n"
                await asyncio.sleep(0.066)  # ~15 FPS yayın

        return StreamingResponse(
            gen(), media_type="multipart/x-mixed-replace; boundary=frame"
        )

    @app.websocket("/ws/alerts")
    async def ws_alerts(ws: WebSocket):
        await ws.accept()
        alert_manager.register_ws(ws)
        try:
            # bağlanınca son alarmları gönder
            await ws.send_text(json.dumps(
                {"kind": "history", "data": alert_manager.get_history(50)},
                ensure_ascii=False,
            ))
            while True:
                # istemciden gelen ping vb. mesajları tüket
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            alert_manager.unregister_ws(ws)

    return app
