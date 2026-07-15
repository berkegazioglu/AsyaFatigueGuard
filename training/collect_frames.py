"""Eğitim verisi toplama: kameradan aralıklı kare kaydeder.

Kullanım (proje kökünden, sunucu KAPALIYKEN — kamera tek uygulamada açılabilir):
    python training/collect_frames.py --source "Insta360 Ace Pro" --interval 2
    python training/collect_frames.py --source "rtsp://..." --interval 2
    python training/collect_frames.py --source 0 --interval 1 --out training/data/raw

Ctrl+C ile durdurun. Kareler <out>/<tarih>/ altına zaman damgasıyla kaydedilir;
ardışık neredeyse özdeş kareleri atlamak için basit fark filtresi uygular.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

# proje kökünü yola ekle (app.core importu için)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.video_source import VideoSource  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Eğitim karesi toplayıcı")
    parser.add_argument("--source", required=True,
                        help="Kamera adı, indeks, RTSP adresi veya video dosyası")
    parser.add_argument("--interval", type=float, default=2.0,
                        help="İki kayıt arası saniye (varsayılan 2)")
    parser.add_argument("--out", default="training/data/raw",
                        help="Çıktı klasörü")
    parser.add_argument("--min-diff", type=float, default=4.0,
                        help="Önceki kareden minimum ortalama piksel farkı (özdeş kareleri atlar)")
    parser.add_argument("--limit", type=int, default=0,
                        help="En fazla bu kadar kare kaydet (0 = sınırsız)")
    args = parser.parse_args()

    source = int(args.source) if args.source.isdigit() else args.source
    out_dir = Path(args.out) / datetime.now().strftime("%Y%m%d_%H%M")
    out_dir.mkdir(parents=True, exist_ok=True)

    video = VideoSource(source, reconnect_delay=3)
    saved = 0
    last_save = 0.0
    prev_gray: np.ndarray | None = None
    print(f"Kayıt başladı -> {out_dir}  (Ctrl+C ile durdurun)")

    try:
        while True:
            frame = video.read()
            if frame is None:
                continue
            now = time.time()
            if now - last_save < args.interval:
                continue

            gray = cv2.cvtColor(cv2.resize(frame, (160, 90)), cv2.COLOR_BGR2GRAY)
            if prev_gray is not None:
                diff = float(np.mean(cv2.absdiff(gray, prev_gray)))
                if diff < args.min_diff:
                    continue  # sahne değişmemiş, atla
            prev_gray = gray

            name = datetime.now().strftime("%H%M%S_%f")[:-3] + ".jpg"
            cv2.imwrite(str(out_dir / name), frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            saved += 1
            last_save = now
            print(f"\r{saved} kare kaydedildi", end="", flush=True)

            if args.limit and saved >= args.limit:
                break
    except KeyboardInterrupt:
        pass
    finally:
        video.release()
        print(f"\nBitti: {saved} kare -> {out_dir}")


if __name__ == "__main__":
    main()
