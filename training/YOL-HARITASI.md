# 🎯 Özel Model Eğitimi Yol Haritası — Bardak / Sigara / Telefon

Hedef: COCO'nun tanımadığı **ince belli çay bardağı**, termos, kupa gibi
nesneleri ve kendi kabin açınızdaki sigara/telefonu yüksek doğrulukla tanıyan
**tek bir YOLO modeli** eğitmek. Tek model = iki model yerine bir kez çıkarım
→ hem daha isabetli hem daha hızlı.

## Neden tek model?

Şu an sistem 2 model çalıştırıyor: COCO (telefon+bardak) + hazır sigara
modeli. Sorunlar: COCO çay bardağını tanımıyor, sigara modeli çay bardağını
sigara sanıyor (0.60 güvenle gördük), her kare iki model maliyeti. Kendi
verinizle eğitilmiş tek model üçünü de çözer.

**Sınıf listesi** (adları AYNEN böyle kullanın — sisteme kod değişikliği
gerekmeden takılır):

| id | sınıf adı | kapsam |
|----|-----------|--------|
| 0 | `cigarette` | sigara, e-sigara (elde veya ağızda) |
| 1 | `cell phone` | telefon (elde, kulakta, bakarken) |
| 2 | `cup` | çay bardağı, kupa, termos, pet şişe, karton bardak |

---

## Aşama 1 — Veri Toplama (1. hafta) 🎥

**Altın kural: modeli nerede kullanacaksanız veriyi oradan toplayın.**
Kendi kabin kameranızdan gelen 500 kare, internetten inen 5000 kareden
değerlidir.

### 1a. Otomatik kare toplama (hazır betik)

```bash
# canlı kameradan her 2 saniyede bir kare kaydeder (Ctrl+C ile durdurun)
python training/collect_frames.py --source "Insta360 Ace Pro" --interval 2 --out training/data/raw
```

Toplama planı (hedef: **1000-1500 kare**):

- ☕ Çay bardağı: ağızda, elde, torpidoda, yarı dolu/boş — **300+ kare**
- 🚬 Sigara: yakma anı, ağızda, elde, camdan kül silkme — **250+ kare**
- 📱 Telefon: kulakta, elde bakarken, kucakta — **250+ kare**
- ❌ **Negatif kareler** (nesnesiz): normal sürüş, el ağızda (sigarasız!),
  esneme, mikrofon/telsiz kullanımı — **300+ kare**
  → Yanlış alarmların ilacı budur: sigara modeli el hareketini sigara
  sanıyordu; "el ağızda ama sigara yok" kareleri bunu söndürür.

Çeşitlilik kontrol listesi:
- [ ] En az 3-5 farklı sürücü (eldiven, gözlük, şapka dahil)
- [ ] Gündüz / alacakaranlık / gece (IR) ışığı
- [ ] Güneş yansıması ve karşı ışık
- [ ] Farklı bardak türleri: cam çay bardağı, kupa, termos, pet şişe

### 1b. Hazır veri setiyle takviye (opsiyonel ama önerilir)

Kendi kareleriniz azsa şunlarla harmanlayın (toplamın %50'sini geçmesin):

- **Roboflow Universe**: "cigarette detection", "cup detection", "tea glass"
  aramaları — YOLO formatında hazır indirilir (ücretsiz hesap).
- **Kaggle**: "Cigarette Smoker Detection", "State Farm Distracted Driver".
- **COCO'dan süzme**: `fiftyone` ile yalnız cup/cell phone içeren kareleri çekin.

## Aşama 2 — Etiketleme (2. hafta) 🏷️

Önerilen araç: **Roboflow** (tarayıcıda çalışır, ekiple paylaşılır, YOLO
formatında dışa aktarır). Alternatif: CVAT, Label Studio, LabelImg.

Etiketleme kuralları (kalite = doğruluk):

1. Kutu nesneyi **sıkı** sarsın; el/parmak kutuya girmesin.
2. Kısmen görünen nesneyi de etiketleyin (elin sardığı bardak, ağızdaki
   sigara ucu) — gerçek kullanım hep böyledir.
3. Negatif karelere hiç kutu koymayın ama veri setine **dahil edin**.
4. Kararsız kaldığınız kareyi atın; yanlış etiket, eksik etiketten kötüdür.
5. Sınıf başına **minimum 300 örnek** hedefleyin (bardak için 500 ideal).

Roboflow'da otomatik augmentation AÇMAYIN (flip/rotate yeter, mosaic'i
eğitim zaten yapıyor); "Auto-Orient" ve "Resize 640" yeterli.

## Aşama 3 — Veri Seti Düzeni 📁

```
training/data/
├── images/train  (kareler %85)
├── images/val    (kareler %15)
├── labels/train
├── labels/val
└── dataset.yaml
```

`dataset.yaml`:

```yaml
path: ./training/data
train: images/train
val: images/val
names:
  0: cigarette
  1: cell phone
  2: cup
```

⚠️ **Bölme tuzağı**: train/val ayrımını rastgele kareyle değil **çekim
oturumuyla** yapın (aynı videonun ardışık kareleri iki tarafa düşerse doğruluk
sahte yüksek çıkar). Örn. pazartesi-perşembe çekimleri train, cuma val.

## Aşama 4 — Eğitim (3. hafta) 🏋️

Bilgisayarınızda NVIDIA GPU yoksa **Kaggle Notebook** kullanın (haftada 30
saat ücretsiz T4 GPU — CPU'da bu eğitim günler sürer, T4'te 1-2 saat):

1. kaggle.com → New Notebook → sağ panelden **Accelerator: GPU T4 x2**
2. Veri setini zip'leyip "Add Data" ile yükleyin
3. Not defterinde:

```python
!pip install -q ultralytics
from ultralytics import YOLO

model = YOLO("yolo11s.pt")          # s = hız/doğruluk dengesi
model.train(
    data="/kaggle/input/afg-dataset/dataset.yaml",
    epochs=150, imgsz=640, batch=32, patience=30,
    degrees=5, translate=0.1, scale=0.3, fliplr=0.5,  # kabin içi augmentasyon
)
```

4. Çıktı: `runs/detect/train/weights/best.pt` → indirin.

Yerelde GPU'nuz varsa: `python training/train.py --data training/data/dataset.yaml --model yolo11s.pt --epochs 150`

## Aşama 5 — Değerlendirme 📊

Kabul eşikleri (val kümesinde):

| Metrik | Hedef |
|---|---|
| mAP@50 (genel) | > 0.85 |
| `cup` recall | > 0.80 (kaçan bardak = kaçan alarm) |
| `cigarette` precision | > 0.85 (yanlış sigara alarmı can sıkar) |

Kontrol edilecekler:
- `confusion_matrix.png` → bardak-sigara karışması bitti mi?
- Gerçek video ile saha testi: `yolo predict model=best.pt source=test_video.mp4`
- Özellikle **çay bardağı ağızda** klipleriyle test edin (eski zayıf nokta).

## Aşama 6 — Sisteme Takma 🔌

```bash
cp best.pt models/afg_custom.pt
```

`config/config.yaml`:

```yaml
detection:
  custom_model: "models/afg_custom.pt"
  # özel model üç sınıfı da tanıdığı için eşikleri buna göre ayarlayın:
  cigarette_conf: 0.50
  phone_conf: 0.45
  drink_conf: 0.40        # artık 0.22 gibi düşük eşiğe gerek kalmaz
```

Sınıf adları COCO ile aynı olduğundan (`cell phone`, `cup`) sistem otomatik
tanır; kod değişikliği gerekmez.

## Aşama 7 — Sürekli İyileştirme Döngüsü 🔁

Endüstriyel doğruluğun sırrı tek eğitim değil, döngüdür:

1. Sahada 1-2 hafta çalıştırın; `media/alerts/` kanıt görüntüleri birikir.
2. **Yanlış alarmları** ve **kaçırılan olayları** ayıklayın
   (`/api/debug/cam1` ucu modelin ne gördüğünü anlık gösterir).
3. Bu "zor kareleri" etiketleyip veri setine ekleyin (hard-example mining).
4. Yeniden eğitin → mAP her turda yükselir. 2-3 tur sonra saha doğruluğu
   %95+ seviyesine oturur.

## Zaman Çizelgesi Özeti

| Hafta | İş | Çıktı |
|---|---|---|
| 1 | Kare toplama (betik sahada çalışır) | 1000-1500 ham kare |
| 2 | Etiketleme (Roboflow) | YOLO formatlı veri seti |
| 3 | Kaggle'da eğitim + değerlendirme | best.pt (mAP50 > 0.85) |
| 4 | Sahaya alma + zor örnek toplama | v2 veri seti → yeniden eğitim |
