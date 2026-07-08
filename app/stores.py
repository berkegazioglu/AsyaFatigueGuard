"""JSON tabanlı kalıcı veri: ekipman eşleştirmeleri ve sürücü kayıtları.

data/equipment.json : { identifier(MAC/USB-N): {equipment, camera_id, paired_at} }
data/drivers.json   : [ {id, camera_id, equipment, name, status, photos, created_at} ]
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

DATA_DIR = Path("data")


class _JsonFile:
    def __init__(self, path: Path, default: Any):
        self.path = path
        self.default = default
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> Any:
        with self._lock:
            if not self.path.exists():
                return json.loads(json.dumps(self.default))
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                return json.loads(json.dumps(self.default))

    def save(self, data: Any) -> None:
        with self._lock:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            tmp.replace(self.path)


class EquipmentStore:
    """Kamera kimliği (MAC / USB-N) -> ekipman adı (ör. TTC59) eşleştirmesi."""

    def __init__(self, data_dir: Path = DATA_DIR):
        self._file = _JsonFile(data_dir / "equipment.json", {})

    def all(self) -> dict:
        return self._file.load()

    def get(self, identifier: str) -> Optional[dict]:
        return self._file.load().get(identifier)

    def pair(self, identifier: str, equipment: str, camera_id: str) -> dict:
        data = self._file.load()
        data[identifier] = {
            "equipment": equipment.strip(),
            "camera_id": camera_id,
            "paired_at": time.time(),
        }
        self._file.save(data)
        return data[identifier]

    def unpair(self, identifier: str) -> bool:
        data = self._file.load()
        if identifier in data:
            del data[identifier]
            self._file.save(data)
            return True
        return False


class DriverStore:
    """Sürücü kayıtları: yakalanan fotoğraflar + admin'in verdiği isim.

    status: 'capturing' (fotoğraflar toplanıyor) | 'pending' (isim bekliyor)
            | 'named' (tamamlandı) | 'failed' (yüz yakalanamadı)
    """

    def __init__(self, data_dir: Path = DATA_DIR):
        self._file = _JsonFile(data_dir / "drivers.json", [])

    def all(self) -> list[dict]:
        return self._file.load()

    def get(self, driver_id: str) -> Optional[dict]:
        return next((d for d in self._file.load() if d["id"] == driver_id), None)

    def create(self, camera_id: str, equipment: Optional[str]) -> dict:
        record = {
            "id": uuid.uuid4().hex[:12],
            "camera_id": camera_id,
            "equipment": equipment,
            "name": None,
            "status": "capturing",
            "photos": [],
            "created_at": time.time(),
        }
        data = self._file.load()
        data.append(record)
        self._file.save(data)
        return record

    def update(self, driver_id: str, **fields) -> Optional[dict]:
        data = self._file.load()
        for d in data:
            if d["id"] == driver_id:
                d.update(fields)
                self._file.save(data)
                return d
        return None

    def pending(self) -> list[dict]:
        """İsimlendirme bekleyen kayıtlar (admin'i zorlamak için)."""
        return [d for d in self._file.load() if d["status"] == "pending"]
