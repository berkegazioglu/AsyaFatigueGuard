# Özel Model Eğitimi: Sigara / E-Sigara / Telefon Tespiti

> 📌 **Adım adım tam plan için: [YOL-HARITASI.md](YOL-HARITASI.md)**
> (bardak/çay bardağı dahil tek model eğitimi, veri toplama betiği,
> Kaggle GPU eğitimi ve saha iyileştirme döngüsü)

Varsayılan `yolov8n.pt` (COCO) modeli **cep telefonunu** hazır tanır.
**Sigara** COCO'da yoktur; yüksek doğruluk için özel veri setiyle eğitim gerekir.

## 1. Veri seti bulma (Kaggle / Roboflow)

Kaggle'da aranabilecek hazır setler (YOLO formatında olanları tercih edin):

| Veri Seti (Kaggle'da arayın) | İçerik |
|---|---|
| "Cigarette Smoker Detection" | sigara içen / içmeyen kişiler |
| "Smoking Detection Dataset" | sigara + el + yüz kutuları |
| "Driver Distraction / State Farm Distracted Driver Detection" | telefon, içecek, yolcuyla konuşma vb. 10 sınıf |
| "Drowsiness Detection (yawn/eye)" | EAR/MAR eşiklerini doğrulamak için test verisi |

Roboflow Universe'te "cigarette detection" araması YOLO formatında
indirilebilir, etiketli çok sayıda set verir (ücretsiz hesap yeterli).

### Kaggle CLI ile indirme

```bash
pip install kaggle
# kaggle.com/settings -> "Create New API Token" -> kaggle.json dosyasını
# ~/.kaggle/ (Windows: C:\Users\<kullanıcı>\.kaggle\) klasörüne koyun
kaggle datasets download -d <kullanici/veri-seti-adi> -p training/data --unzip
```

## 2. Veri setini YOLO formatına hazırlama

Beklenen klasör yapısı:

```
training/data/
├── images/train  ├── images/val
├── labels/train  ├── labels/val
└── dataset.yaml
```

`dataset.yaml` örneği:

```yaml
path: ./training/data
train: images/train
val: images/val
names:
  0: cigarette
  1: phone
```

## 3. Eğitim

```bash
pip install ultralytics
python training/train.py --data training/data/dataset.yaml --epochs 100 --model yolov8s.pt
```

Eğitim bitince en iyi ağırlık `runs/detect/train/weights/best.pt` olur.
Bunu `models/cigarette.pt` olarak kopyalayıp `config/config.yaml` içinde:

```yaml
detection:
  custom_model: "models/cigarette.pt"
```

## 4. Doğruluk ipuçları

- Kabin içi gerçek görüntülerinizden 200-500 kare etiketleyip eğitim setine
  eklemek doğruluğu en çok artıran adımdır (kendi kamera açınız, gece/IR
  görüntüleri, güneş yansımaları).
- Gece sürüşü için IR kameradan alınmış örnekler mutlaka ekleyin.
- `yolov8s.pt` (small) doğruluk/hız dengesi için iyi bir başlangıçtır;
  yalnızca CPU varsa `yolov8n.pt` ile eğitin.
- mAP50 > 0.85 hedefleyin; altındaysa veri artırma (augmentation) ve daha
  fazla etiketli örnekle tekrar eğitin.
