# AsyaFatigueGuard - Endüstriyel Sürücü İzleme Sistemi (DMS)

# --- 1. aşama: React arayüzünü derle ---
FROM node:22-slim AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- 2. aşama: Python çalışma ortamı ---
# MediaPipe henüz Python 3.13+ desteklemediği için 3.11 kullanılır.
FROM python:3.11-slim

# OpenCV / MediaPipe / ffmpeg (RTSP) sistem bağımlılıkları
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/afg

# Torch'un CPU sürümü ayrı katmanda: requirements değişince yeniden inmez
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY config ./config
COPY --from=frontend /build/dist ./frontend/dist

# YOLO ağırlığı ilk çalıştırmada indirilir; imaja gömmek için:
# RUN python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"

ENV AFG_CONFIG=/opt/afg/config/config.yaml \
    PYTHONUNBUFFERED=1

EXPOSE 8000
CMD ["python", "-m", "app.main"]
