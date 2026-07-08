"""Basit admin kimlik doğrulama.

Tek admin hesabı (config veya ortam değişkeni), bellekte oturum token'ları.
Token'lar sunucu yeniden başlayınca geçersizleşir. Üretimde AFG_ADMIN_PASSWORD
ortam değişkeniyle parolayı mutlaka değiştirin.
"""
from __future__ import annotations

import hmac
import os
import secrets
import threading
import time
from typing import Optional

from fastapi import HTTPException, Request

TOKEN_TTL_SEC = 12 * 3600  # oturum süresi: 12 saat


class AuthManager:
    def __init__(self, server_cfg: dict):
        self.username = os.environ.get(
            "AFG_ADMIN_USER", server_cfg.get("admin_user", "admin")
        )
        self.password = os.environ.get(
            "AFG_ADMIN_PASSWORD", server_cfg.get("admin_password", "admin123")
        )
        self._tokens: dict[str, float] = {}  # token -> son kullanma zamanı
        self._lock = threading.Lock()

    def login(self, username: str, password: str) -> Optional[str]:
        if not (
            hmac.compare_digest(username, self.username)
            and hmac.compare_digest(password, self.password)
        ):
            return None
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._tokens[token] = time.time() + TOKEN_TTL_SEC
        return token

    def logout(self, token: str) -> None:
        with self._lock:
            self._tokens.pop(token, None)

    def is_valid(self, token: Optional[str]) -> bool:
        if not token:
            return False
        now = time.time()
        with self._lock:
            exp = self._tokens.get(token)
            if exp is None:
                return False
            if exp < now:
                del self._tokens[token]
                return False
            return True

    def require(self, request: Request) -> str:
        """FastAPI dependency: Authorization: Bearer <token> veya ?t=<token>."""
        token = None
        header = request.headers.get("authorization", "")
        if header.lower().startswith("bearer "):
            token = header[7:].strip()
        if not token:
            token = request.query_params.get("t")
        if not self.is_valid(token):
            raise HTTPException(status_code=401, detail="Oturum gerekli")
        return token
