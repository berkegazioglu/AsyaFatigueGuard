"""Giriş noktası: python -m app.main"""
from __future__ import annotations

import logging
import os

import uvicorn

from app.config import Config
from app.server import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)


def main() -> None:
    cfg = Config.load()
    app = create_app(cfg)
    server_cfg = cfg.server
    # AFG_HOST / AFG_PORT ortam değişkenleri config dosyasını ezebilir
    uvicorn.run(
        app,
        host=os.environ.get("AFG_HOST", server_cfg.get("host", "0.0.0.0")),
        port=int(os.environ.get("AFG_PORT", server_cfg.get("port", 8000))),
        log_level="info",
    )


if __name__ == "__main__":
    main()
