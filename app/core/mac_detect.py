"""Kamera kaynağının kimliğini (IP + MAC adresi) tespit eder.

- RTSP/HTTP kameralar: URL'den IP çıkarılır, ping ile ARP tablosu tazelenir,
  'arp -a' çıktısından MAC okunur (Windows ve Linux desteklenir).
- USB kameralar: MAC yoktur; 'USB-<indeks>' takma kimliği kullanılır.
- Video dosyaları: 'FILE-<ad>' takma kimliği.

MAC, kameranın üzerine monteli olduğu ekipmanla (ör. TTC59) eşleştirilerek
kamera hangi araca takılırsa takılsın doğru ekipman adının gelmesini sağlar.
"""
from __future__ import annotations

import platform
import re
import subprocess
from pathlib import Path
from typing import Optional, Union
from urllib.parse import urlparse

MAC_RE = re.compile(r"(?:[0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}")


def _ping(ip: str) -> None:
    """ARP tablosunu doldurmak için tek ping (çıktı önemsiz)."""
    flag = "-n" if platform.system() == "Windows" else "-c"
    try:
        subprocess.run(
            ["ping", flag, "1", "-w" if platform.system() == "Windows" else "-W",
             "1000" if platform.system() == "Windows" else "1", ip],
            capture_output=True, timeout=5,
        )
    except Exception:
        pass


def mac_for_ip(ip: str) -> Optional[str]:
    """ARP tablosundan IP'ye karşılık gelen MAC adresini döndürür."""
    _ping(ip)
    try:
        out = subprocess.run(
            ["arp", "-a", ip], capture_output=True, text=True, timeout=5
        ).stdout
    except Exception:
        return None
    for line in out.splitlines():
        if ip in line:
            m = MAC_RE.search(line)
            if m:
                return m.group(0).replace("-", ":").lower()
    return None


def source_identity(source: Union[int, str]) -> dict:
    """Kamera kaynağı için {kind, ip, mac, identifier} döndürür.

    identifier: ekipman eşleştirmede anahtar olarak kullanılır
    (IP kamerada MAC, USB'de 'USB-N', dosyada 'FILE-ad').
    """
    if isinstance(source, int) or (isinstance(source, str) and source.isdigit()):
        return {
            "kind": "usb",
            "ip": None,
            "mac": None,
            "identifier": f"USB-{source}",
        }
    src = str(source)
    if src.lower().startswith(("rtsp://", "http://", "https://")):
        host = urlparse(src).hostname
        mac = mac_for_ip(host) if host else None
        return {
            "kind": "ip",
            "ip": host,
            "mac": mac,
            # MAC bulunamazsa IP üzerinden geçici kimlik (kamera kapalı olabilir)
            "identifier": mac if mac else (f"IP-{host}" if host else "IP-?"),
        }
    if Path(src).exists():
        return {
            "kind": "file",
            "ip": None,
            "mac": None,
            "identifier": f"FILE-{Path(src).stem}",
        }
    # kamera ADI ile seçim (Windows DirectShow): ad, kalıcı kimliktir
    return {
        "kind": "usb",
        "ip": None,
        "mac": None,
        "identifier": f"DEV-{src}",
    }
