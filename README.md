# 🚚 AsyaFatigueGuard — Endüstriyel Sürücü İzleme Sistemi (DMS)

![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Hazır-2496ED?logo=docker&logoColor=white)
![MediaPipe](https://img.shields.io/badge/MediaPipe-0.10.14-orange)
![YOLO](https://img.shields.io/badge/YOLOv8%20%2B%20YOLOv11-Ultralytics-purple)
![Lisans](https://img.shields.io/badge/Lisans-MIT-green)

Tır/kamyon filoları için **mevcut kamera donanımına müdahale gerektirmeyen**,
gerçek zamanlı sürücü izleme yazılımı. Kabin kamerasının RTSP / HTTP / USB
görüntüsünü alır; yorgunluk, mikro uyku, telefon, sigara, içecek ve dikkat
dağınıklığını anlık tespit eder; **canlı web paneli + WebSocket + Telegram /
webhook** üzerinden bildirim gönderir ve sürücü başına **0-100 canlı risk
puanı** üretir.

---

## İçindekiler

- [Özellikler](#özellikler)
- [Risk Puanı](#risk-puanı)
- [Mimari](#mimari)
- [Hızlı Başlangıç](#hızlı-başlangıç)
- [Sigara Modelini İndirme](#sigara-modelini-indirme)
- [Yapılandırma](#yapılandırma)
- [Canlı Panel](#canlı-panel)
- [API Referansı](#api-referansı)
- [Özel Model Eğitimi](#özel-model-eğitimi)
- [Saha Kurulum Önerileri](#saha-kurulum-önerileri)
- [Sık Sorulanlar](#sık-sorulanlar)
- [Yasal / KVKK](#yasal--kvkk)

---

## Özellikler

| # | Tespit | Yöntem | Seviye |
|---|--------|--------|--------|
| 1 | 😴 **Mikro Uyku** | MediaPipe Face Mesh → EAR (göz açıklık oranı) eşik + süre | 🔴 Kritik |
| 2 | 🥱 **Yorgunluk (PERCLOS)** | 60 sn pencerede gözlerin kapalı kalma oranı | 🔴 Kritik |
| 3 | 😮 **Esneme** | MAR (ağız açıklık oranı) eşik + süre | 🟡 Uyarı |
| 4 | 😩 **Aşırı Yorgunluk** | 5 dk içinde 3+ esneme | 🔴 Kritik |
| 5 | 🙇 **Baş Öne Düşmesi** | Head Pose (solvePnP, pitch açısı) | 🔴 Kritik |
| 6 | 👀 **Yola Bakmama** | Head Pose (yaw açısı) + süre | 🟡 Uyarı |
| 7 | 📱 **Telefon Kullanımı** | YOLOv8 (COCO `cell phone`) + kalıcılık süzgeci | 🔴 Kritik |
| 8 | 🚬 **Sigara** | Özel YOLOv11 modeli (Hugging Face, mAP50 %82.9) | 🟡 Uyarı |
| 9 | ☕ **İçecek İçme** | YOLOv8 (`cup`/`bottle`/`wine glass`) + **ağız hizası** kontrolü | 🟡 Uyarı |
| 10 | 🚫 **Sürücü Görünmüyor** | Yüz kaybı (kamera engelleme dahil) | 🟡 Uyarı |
| 11 | ⚠️ **Bozulmuş Sürüş Şüphesi** | Kısa sürede yoğun uyku belirtisi kombinasyonu | 🔴 Kritik |

Akıllı süzgeçler:

- **Kalıcılık**: Telefon/sigara/bardak anlık değil, 1.5-2 sn görünürse alarm olur.
- **Kesinti toleransı**: YOLO tespiti kareler arası titrese de (şeffaf çay
  bardağı gibi) 0.8 sn'ye kadar boşluk sayacı sıfırlamaz.
- **Çakışma çözümü**: Bardak ağız hizasındayken sigara tespiti bastırılır
  (sigara modeli çay bardağını sigara sanabiliyor).
- **Ağız hizası şartı**: Torpidodaki şişe/bardak alarm üretmez; kap ancak
  yüz landmark'ına yakınsa "içiyor" sayılır.
- **Cooldown**: Aynı kameradan aynı tip alarm 30 sn'de en fazla bir kez bildirilir.

> **Alkol hakkında dürüst not:** Kamera alkol seviyesini **ölçemez** — bu
> fizik sınırıdır, hiçbir kamera-DMS promil ölçemez. Sistem bunun yerine
> alkol/ilaç etkisine işaret edebilecek davranış örüntüsünü (sık mikro uyku +
> baş düşmesi + yüksek PERCLOS) birleştirip **"Bozulmuş Sürüş Şüphesi"**
> bildirimi üretir. Kesin tespit için ateşleme kilidi (alcohol interlock)
> gibi donanım gerekir.

## Risk Puanı

Her sürücü (kamera) için **0-100 arası canlı risk puanı** hesaplanır ve
panelin üst menüsünde renkli rozet olarak gösterilir:

- Her alarm, türüne göre ağırlıklı puan ekler
  (Bozulma Şüphesi 35, Mikro Uyku 25, PERCLOS 22, Telefon 20, ... İçecek 6).
- Puanlar **üstel olarak söner**: varsayılan ayarda 5 dakikada yarıya iner —
  uyarı gelmedikçe risk kendiliğinden düşer, sık uyarıda birikir.
- `risk_gain` çarpanı artış hızını ölçekler (varsayılan 0.25).
- Rozet renkleri: 🟢 %0-29 · 🟡 %30-59 · 🔴 %60+ (yanıp söner).
- Her alarm kaydına o anki risk yazılır → "sürücüyü kritik eşiğe hangi alarm
  taşıdı" raporlanabilir.

## Mimari

```
RTSP/USB Kamera ──> OpenCV Capture ──> Ön işleme (640px yeniden boyutlandırma)
                                          │
                        ┌─────────────────┴─────────────────┐
                        │ Kanal 1: MediaPipe Face Mesh      │ Kanal 2: YOLO (her N karede)
                        │  EAR · MAR · Head Pose (solvePnP) │  COCO: telefon, bardak, şişe
                        │  468 yüz noktası                  │  Özel: sigara (YOLOv11m)
                        └─────────────────┬─────────────────┘
                                          ▼
                          Karar Motoru (süre + eşik + çakışma kuralları)
                                          ▼
                 AlertManager (cooldown · risk puanı · kanıt JPEG · geçmiş)
                     │             │              │              │
                Web Paneli    WebSocket      Telegram        Webhook
                (MJPEG canlı) (anlık uyarı)  (opsiyonel)     (opsiyonel)
```

- Her kamera **kendi thread'inde** işlenir → tek sunucu, çoklu araç.
- YOLO her N karede bir çalışır (`yolo_every_n_frames`) → CPU tasarrufu.
- Kamera koptuğunda otomatik yeniden bağlanır; dosya kaynakları döngüye alınır (demo).

### Proje yapısı

```
AsyaFatigueGuard/
├── app/
│   ├── main.py               # giriş noktası (AFG_PORT/AFG_HOST destekler)
│   ├── server.py             # FastAPI: panel, MJPEG, WS, REST, debug
│   ├── config.py             # config.yaml yükleyici + doğrulama
│   ├── core/
│   │   ├── video_source.py   # RTSP/USB/dosya okuyucu, otomatik yeniden bağlanma
│   │   ├── face_analyzer.py  # MediaPipe: EAR, MAR, head pose
│   │   ├── object_detector.py# YOLO: telefon, sigara, içecek + debug_all
│   │   ├── decision_engine.py# alarm kuralları, zamanlayıcılar, risk ağırlıkları
│   │   └── pipeline.py       # kamera başına işleme thread'i + görselleştirme
│   ├── alerts/
│   │   ├── manager.py        # cooldown, risk puanı, geçmiş, WS yayını, kanıt JPEG
│   │   └── notifiers.py      # Telegram + genel webhook
│   └── static/index.html     # canlı izleme paneli (tek dosya, bağımlılıksız)
├── config/config.yaml        # TÜM eşikler ve kamera tanımları
├── training/                 # özel YOLO eğitim rehberi + betiği
├── models/                   # özel model ağırlıkları (git'e girmez)
├── media/alerts/             # alarm kanıt görüntüleri (git'e girmez)
├── Dockerfile · docker-compose.yml
└── baslat.bat                # Windows tek tık başlatıcı
```

## Hızlı Başlangıç

### Docker ile (üretim için önerilen)

```bash
git clone https://github.com/berkegazioglu/AsyaFatigueGuard.git
cd AsyaFatigueGuard

# 1) Kameralarınızı tanımlayın: config/config.yaml -> cameras -> source
# 2) (Opsiyonel) Sigara modelini indirin — aşağıdaki bölüme bakın
# 3) Başlatın:
docker compose up -d --build

# Panel: http://localhost:8000
```

İlk çalıştırmada YOLOv8n (~6 MB) otomatik iner. `restart: unless-stopped`
sayesinde makine yeniden başlasa da servis kendiliğinden kalkar.

> Docker Desktop (Windows) USB web kamerasına erişemez; Docker yolu RTSP/IP
> kameralar içindir. Yerel web kamerası testi için aşağıdaki yerel kurulumu kullanın.

### Yerel kurulum (geliştirme / webcam testi)

MediaPipe için **Python 3.10-3.12** gerekir (3.13+ desteklenmez):

```bash
python3.11 -m venv .venv
.venv\Scripts\activate            # Linux/Mac: source .venv/bin/activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
python -m app.main                # Panel: http://localhost:8000
```

- Port meşgulse: `AFG_PORT=8010` ortam değişkeniyle değiştirin.
- Windows'ta `baslat.bat` çift tıklamayla sunucuyu + paneli açar.
- ⚠️ Windows'ta proje yolu **Türkçe karakter içeriyorsa** (ör. "Masaüstü")
  MediaPipe model dosyasını yükleyemez — sanal ortamı ASCII bir yola kurun
  (ör. `C:\venvs\afg`).

## Sigara Modelini İndirme

Sigara sınıfı COCO'da yoktur; hazır eğitilmiş model Hugging Face'ten indirilir
(`models/` klasörü git'e girmez, bu adım klonlamadan sonra bir kez yapılır):

```bash
curl -L -o models/cigarette.pt \
  "https://huggingface.co/HEIher/smoking-detection/resolve/main/best.pt"
```

Model: YOLOv11-Medium, tek sınıf `cigarette`, mAP@0.5 = %82.9
([model kartı](https://huggingface.co/HEIher/smoking-detection)).
`config.yaml → detection.custom_model: "models/cigarette.pt"` zaten ayarlıdır;
dosya yoksa sistem sigara tespiti olmadan sorunsuz çalışır.

## Yapılandırma

Tüm eşikler [config/config.yaml](config/config.yaml) dosyasındadır — kod
değişikliği gerektirmez. Önemli anahtarlar:

| Anahtar | Varsayılan | Açıklama |
|---|---|---|
| `cameras[].source` | `0` | RTSP URL, USB indeksi veya video dosyası |
| `ear_threshold` | `0.21` | Göz kapalı eşiği (gözlüklüde 0.18 deneyin) |
| `microsleep_sec` | `1.5` | Mikro uyku alarm süresi |
| `perclos_threshold` | `0.30` | Pencere içi göz kapalılık oranı eşiği |
| `mar_threshold` | `0.65` | Esneme eşiği |
| `distraction_yaw_deg` | `32` | Yola bakmama açısı (derece) |
| `phone_conf` | `0.45` | Telefon tespit güveni |
| `cigarette_conf` | `0.55` | Sigara güveni (düşükse el/bardak yanlış alarm verir) |
| `drink_conf` | `0.22` | Bardak/şişe güveni (şeffaf bardak için düşük) |
| `yolo_every_n_frames` | `3` | YOLO çalışma sıklığı (CPU tasarrufu) |
| `cooldown_sec` | `30` | Aynı alarmın tekrar bildirim aralığı |
| `risk_half_life_sec` | `300` | Risk puanı yarılanma süresi |
| `risk_gain` | `0.25` | Risk artış hızı çarpanı |
| `telegram_bot_token/chat_id` | boş | Doldurulursa Telegram'a anlık bildirim |
| `webhook_url` | boş | Alarm JSON'unun POST edileceği adres |

## Canlı Panel

`http://localhost:8000` (Docker) / `http://localhost:8010` (yerel):

- **Kamera kartları**: İşlenmiş MJPEG canlı yayın — yüz landmark'ları,
  tespit kutuları (TELEFON/SIGARA/ICECEK), alarm anında kırmızı çerçeve.
- **Anlık metrikler**: EAR, MAR, PERCLOS, yüz/telefon/sigara/içecek durumu (1 sn).
- **Üst menü**: kamera başına **RİSK %XX** rozeti (yeşil/sarı/kırmızı),
  canlı saat, bağlantı durumu.
- **Uyarı akışı**: Sesli bip + ekran bildirimi + kanıt görüntüsü bağlantısı;
  WebSocket koptuğunda otomatik yeniden bağlanır.

## API Referansı

| Uç | Açıklama |
|---|---|
| `GET /` | Canlı izleme paneli |
| `GET /stream/{camera_id}` | MJPEG canlı yayın (işlenmiş görüntü) |
| `GET /api/status` | Kameraların anlık metrikleri + risk puanı |
| `GET /api/alerts?limit=100` | Alarm geçmişi |
| `GET /api/debug/{camera_id}?conf=0.15` | Modellerin o karede gördüğü TÜM sınıflar (eşik ayarı için) |
| `WS /ws/alerts` | Anlık alarm yayını (bağlanınca son 50 kayıt gelir) |
| `GET /media/alerts/...` | Alarm anı kanıt görüntüleri |

Alarm JSON örneği (WS / webhook / Telegram aynı içerik):

```json
{
  "type": "MICROSLEEP",
  "camera_id": "cam1",
  "camera_name": "TTC 59 Berko",
  "title": "Mikro Uyku",
  "severity": "critical",
  "message": "Sürücünün gözleri uzun süre kapalı!",
  "value": 0.14,
  "risk": 57,
  "time_str": "08.07.2026 00:04:15",
  "snapshot": "/media/alerts/cam1_MICROSLEEP_20260708_000415.jpg"
}
```

## Özel Model Eğitimi

Kendi kabin görüntülerinizle sigara/telefon modeli eğitmek doğruluğu en çok
artıran adımdır. Kaggle/Roboflow veri seti bulma, YOLO formatı ve eğitim
komutları için: **[training/README.md](training/README.md)**

```bash
python training/train.py --data training/data/dataset.yaml --epochs 100 --model yolov8s.pt
```

## Saha Kurulum Önerileri

- Kamerayı sürücü yüzünü **önden ~30° içinde** görecek şekilde konumlandırın
  (MediaPipe profil yüzlerde çalışmaz).
- Gece sürüşü için **IR (kızılötesi) kamera** şarttır; MediaPipe IR görüntüde çalışır.
- İlk hafta eşikleri sahada kalibre edin: yanlış alarm çoksa `microsleep_sec`,
  `cooldown_sec`, `cigarette_conf` değerlerini artırın.
- `/api/debug/{camera_id}` ucu, "neden algılamıyor/yanlış algılıyor"
  sorularının cevabını verir: modelin gördüğü ham sınıf+güven listesi.
- CPU'da kamera başına ~30-70 FPS işlenir (yolov8n + yolov11m, Intel i5+);
  çok kamerada `yolo_every_n_frames` değerini artırın.

## Sık Sorulanlar

**Alkolü gerçekten tespit edemiyor mu?**
Kameradan promil ölçümü fiziksel olarak imkânsızdır. "Bozulmuş Sürüş Şüphesi"
alarmı davranışsal bir göstergedir; hukuki işlem için nefes analizörü gerekir.

**Mevcut kameramı değiştirmem gerekir mi?**
Hayır. RTSP/HTTP yayını olan her IP kamera ve her USB kamera doğrudan çalışır.

**İnternet bağlantısı gerekir mi?**
Hayır — tüm işleme yereldir (edge). Yalnızca Telegram/webhook bildirimleri
için internet gerekir. Görüntüler buluta gönderilmez.

**Kaç kamera bağlayabilirim?**
Donanıma bağlı; her kamera bir thread'dir. `config.yaml`'a `id/name/source`
üçlüsü ekleyerek çoğaltın, panel otomatik yeni kart açar.

## Yasal / KVKK

Sürücü izleme, biyometrik kişisel veri işler. Türkiye'de KVKK kapsamında:

- Sürücülere **aydınlatma metni** sunulmalı ve açık rıza alınmalıdır.
- Kanıt görüntüleri (`media/alerts/`) yereldedir; saklama süresi ve erişim
  yetkisi politikası tanımlanmalıdır.
- Sistem bir **güvenlik destek aracıdır**; işe alım/işten çıkarma gibi
  kararların tek dayanağı olmamalıdır.

## Lisans

[MIT](LICENSE) — Asyaport için geliştirilmiştir.
