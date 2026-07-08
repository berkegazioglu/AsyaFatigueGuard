"""FastAPI sunucusu.

- React yönetim paneli (frontend/dist varsa onu, yoksa eski tek-dosya paneli servis eder)
- Admin girişi (Bearer token; MJPEG/WS için ?t= sorgu parametresi)
- MJPEG canlı yayın, WebSocket anlık uyarı, REST durum/geçmiş
- Kamera kimliği (MAC) tespiti + ekipman eşleştirme (ör. TTC59)
- Sürücü tanıtımı: canlıdan 10 fotoğraf yakalama + zorunlu isimlendirme
"""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import time

from app.auth import AuthManager
from app.config import Config
from app.core.enrollment import DRIVERS_MEDIA_DIR, AutoEnroller, EnrollmentService
from app.core.mac_detect import source_identity
from app.core.object_detector import ObjectDetector
from app.core.pipeline import CameraPipeline
from app.stores import DriverStore, EquipmentStore
from app.alerts.manager import AlertManager

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"


class LoginBody(BaseModel):
    username: str
    password: str


class PairBody(BaseModel):
    identifier: str
    equipment: str
    camera_id: str


class NameBody(BaseModel):
    name: str


def create_app(cfg: Config) -> FastAPI:
    auth = AuthManager(cfg.server)
    alert_manager = AlertManager(cfg.alerts)
    equipment_store = EquipmentStore()
    driver_store = DriverStore()
    enrollment = EnrollmentService(driver_store)
    detector = ObjectDetector(
        base_model=cfg.det("yolo_model", "yolov8n.pt"),
        custom_model=cfg.det("custom_model", ""),
        phone_conf=cfg.det("phone_conf", 0.45),
        cigarette_conf=cfg.det("cigarette_conf", 0.40),
        drink_conf=cfg.det("drink_conf", 0.35),
    )
    pipelines: dict[str, CameraPipeline] = {}
    identity_cache: dict[str, dict] = {}
    session_start = time.time()

    def _equipment_of(camera_id: str) -> str | None:
        for info in equipment_store.all().values():
            if info.get("camera_id") == camera_id:
                return info.get("equipment")
        return None

    def _driver_of(camera_id: str) -> str | None:
        record = driver_store.latest_named(camera_id, since=session_start)
        return record["name"] if record else None

    # uyarılar aktif sürücünün adıyla gitsin
    alert_manager.driver_resolver = _driver_of
    auto_enroller = AutoEnroller(pipelines, enrollment, _equipment_of, session_start)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        alert_manager.set_loop(asyncio.get_running_loop())
        for cam in cfg.cameras:
            p = CameraPipeline(cam, cfg.video, cfg.detection, detector, alert_manager)
            pipelines[p.camera_id] = p
            p.start()
        auto_enroller.start()
        log.info("%d kamera hattı başlatıldı", len(pipelines))
        yield
        auto_enroller.stop()
        for p in pipelines.values():
            p.stop()

    app = FastAPI(title="AsyaFatigueGuard DMS", lifespan=lifespan)
    require_auth = Depends(auth.require)

    # --- kimlik doğrulama -----------------------------------------------------
    @app.post("/api/login")
    async def login(body: LoginBody):
        token = auth.login(body.username, body.password)
        if token is None:
            raise HTTPException(status_code=401, detail="Kullanıcı adı veya parola hatalı")
        return {"token": token, "username": body.username}

    @app.post("/api/logout")
    async def logout(request: Request, _=require_auth):
        header = request.headers.get("authorization", "")
        auth.logout(header[7:].strip() if header.lower().startswith("bearer ") else "")
        return {"ok": True}

    @app.get("/api/me")
    async def me(_=require_auth):
        return {"ok": True, "username": auth.username}

    # --- durum / uyarılar -------------------------------------------------------
    @app.get("/api/status")
    async def status(_=require_auth):
        return {
            "cameras": [
                {
                    **p.status(),
                    "equipment": _equipment_of(p.camera_id),
                    "driver": _driver_of(p.camera_id),
                }
                for p in pipelines.values()
            ]
        }

    @app.get("/api/alerts")
    async def alerts(limit: int = 100, _=require_auth):
        return {"alerts": alert_manager.get_history(limit)}

    @app.get("/api/debug/{camera_id}")
    async def debug_detections(camera_id: str, conf: float = 0.15, _=require_auth):
        pipeline = pipelines.get(camera_id)
        if pipeline is None:
            raise HTTPException(status_code=404, detail="kamera bulunamadı")
        frame = pipeline.latest_raw()
        if frame is None:
            return {"detections": [], "error": "henüz kare yok"}
        detections = await asyncio.to_thread(detector.debug_all, frame, conf)
        return {"detections": detections}

    # --- kamera kimliği (MAC) + ekipman eşleştirme -------------------------------
    @app.get("/api/cameras/{camera_id}/identity")
    async def camera_identity(camera_id: str, refresh: bool = False, _=require_auth):
        pipeline = pipelines.get(camera_id)
        if pipeline is None:
            raise HTTPException(status_code=404, detail="kamera bulunamadı")
        if refresh or camera_id not in identity_cache:
            # ping + arp birkaç saniye sürebilir; event loop'u bloklamayalım
            identity_cache[camera_id] = await asyncio.to_thread(
                source_identity, pipeline.source.source
            )
        identity = dict(identity_cache[camera_id])
        identity["pairing"] = equipment_store.get(identity["identifier"])
        return identity

    @app.get("/api/equipment")
    async def equipment_all(_=require_auth):
        return {"equipment": equipment_store.all()}

    @app.post("/api/equipment")
    async def equipment_pair(body: PairBody, _=require_auth):
        if not body.equipment.strip():
            raise HTTPException(status_code=422, detail="Ekipman adı boş olamaz")
        if body.camera_id not in pipelines:
            raise HTTPException(status_code=404, detail="kamera bulunamadı")
        pairing = equipment_store.pair(body.identifier, body.equipment, body.camera_id)
        return {"ok": True, "pairing": pairing}

    @app.delete("/api/equipment/{identifier}")
    async def equipment_unpair(identifier: str, _=require_auth):
        return {"ok": equipment_store.unpair(identifier)}

    # --- sürücü tanıtımı (10 fotoğraf + zorunlu isimlendirme) ---------------------
    @app.post("/api/cameras/{camera_id}/enroll")
    async def enroll_driver(camera_id: str, _=require_auth):
        pipeline = pipelines.get(camera_id)
        if pipeline is None:
            raise HTTPException(status_code=404, detail="kamera bulunamadı")
        record = enrollment.start(pipeline, _equipment_of(camera_id))
        if record is None:
            raise HTTPException(
                status_code=409, detail="Bu kamerada yakalama zaten sürüyor"
            )
        return {"ok": True, "driver": record}

    @app.get("/api/drivers")
    async def drivers_all(_=require_auth):
        return {"drivers": driver_store.all()}

    @app.get("/api/drivers/pending")
    async def drivers_pending(_=require_auth):
        return {"pending": driver_store.pending()}

    @app.post("/api/drivers/{driver_id}/name")
    async def driver_name(driver_id: str, body: NameBody, _=require_auth):
        if not body.name.strip():
            raise HTTPException(status_code=422, detail="Sürücü adı boş olamaz")
        record = driver_store.get(driver_id)
        if record is None:
            raise HTTPException(status_code=404, detail="kayıt bulunamadı")
        updated = driver_store.update(
            driver_id, name=body.name.strip(), status="named"
        )
        return {"ok": True, "driver": updated}

    @app.get("/media/drivers/{driver_id}/{filename}")
    async def driver_photo(driver_id: str, filename: str, _=require_auth):
        # yol kaçışlarını engelle
        if "/" in filename or "\\" in filename or ".." in driver_id + filename:
            raise HTTPException(status_code=400)
        path = DRIVERS_MEDIA_DIR / driver_id / filename
        if not path.exists():
            raise HTTPException(status_code=404)
        return FileResponse(path)

    # --- canlı yayın -------------------------------------------------------------
    @app.get("/stream/{camera_id}")
    async def stream(camera_id: str, _=require_auth):
        pipeline = pipelines.get(camera_id)
        if pipeline is None:
            raise HTTPException(status_code=404, detail="kamera bulunamadı")

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
        if not auth.is_valid(ws.query_params.get("t")):
            await ws.close(code=4401)
            return
        await ws.accept()
        alert_manager.register_ws(ws)
        try:
            await ws.send_text(json.dumps(
                {"kind": "history", "data": alert_manager.get_history(50)},
                ensure_ascii=False,
            ))
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            alert_manager.unregister_ws(ws)

    # --- statik dosyalar / arayüz --------------------------------------------------
    snapshot_dir = Path(cfg.alerts.get("snapshot_dir", "media/alerts"))
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/media/alerts", StaticFiles(directory=snapshot_dir), name="snapshots")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    if FRONTEND_DIST.exists():
        app.mount(
            "/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets"
        )

        @app.get("/")
        async def index():
            return FileResponse(FRONTEND_DIST / "index.html")
    else:
        @app.get("/")
        async def index_legacy():
            return FileResponse(STATIC_DIR / "index.html")

    return app
