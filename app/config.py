"""Yapılandırma yükleyici: config/config.yaml dosyasını okur ve doğrular."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = Path(os.environ.get("AFG_CONFIG", "config/config.yaml"))


class Config:
    def __init__(self, data: dict[str, Any]):
        self._data = data

    @classmethod
    def load(cls, path: Path | str = DEFAULT_CONFIG_PATH) -> "Config":
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(
                f"Yapılandırma dosyası bulunamadı: {path}. "
                "AFG_CONFIG ortam değişkeni ile farklı bir yol verebilirsiniz."
            )
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        cfg = cls(data)
        cfg._validate()
        return cfg

    def _validate(self) -> None:
        cams = self.cameras
        if not cams:
            raise ValueError("config.yaml: en az bir kamera tanımlanmalı (cameras).")
        seen: set[str] = set()
        for cam in cams:
            cid = cam.get("id")
            if not cid or cid in seen:
                raise ValueError(f"config.yaml: kamera 'id' alanı benzersiz olmalı: {cam}")
            seen.add(cid)

    # --- kısayollar -------------------------------------------------------
    @property
    def cameras(self) -> list[dict[str, Any]]:
        return [c for c in self._data.get("cameras", []) if c.get("enabled", True)]

    @property
    def video(self) -> dict[str, Any]:
        return self._data.get("video", {})

    @property
    def detection(self) -> dict[str, Any]:
        return self._data.get("detection", {})

    @property
    def alerts(self) -> dict[str, Any]:
        return self._data.get("alerts", {})

    @property
    def server(self) -> dict[str, Any]:
        return self._data.get("server", {})

    def det(self, key: str, default: Any = None) -> Any:
        return self.detection.get(key, default)
