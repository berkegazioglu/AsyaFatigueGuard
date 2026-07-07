"""YOLOv8 özel model eğitimi (sigara / telefon).

Kullanım:
    python training/train.py --data training/data/dataset.yaml --epochs 100
"""
from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="AsyaFatigueGuard özel YOLO eğitimi")
    parser.add_argument("--data", required=True, help="dataset.yaml yolu")
    parser.add_argument("--model", default="yolov8s.pt", help="başlangıç ağırlığı")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16)
    args = parser.parse_args()

    from ultralytics import YOLO

    model = YOLO(args.model)
    results = model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        patience=20,
        project="runs/detect",
    )
    print("Eğitim tamamlandı. En iyi ağırlık:", results.save_dir, "/weights/best.pt")
    print("models/ klasörüne kopyalayıp config.yaml -> detection.custom_model alanına yazın.")


if __name__ == "__main__":
    main()
