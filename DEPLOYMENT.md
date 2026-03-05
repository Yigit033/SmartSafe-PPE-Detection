# SmartSafe — Tam Saha Deployment Kılavuzu
*(Windows · Linux · macOS · Tüm Kamera Sistemleri)*

---

## A. Müşteri Kodu Görecek mi?

Bu SaaS projesi **on-premise kurulum** ile çalışıyor — yani sunucu müşterinin tesisinde.  
Kod görünürlüğü seçtiğin yönteme göre değişiyor:

| Yöntem | Müşteri kodu görür mü? | Kurulum |
|---|---|---|
| **Kaynak kodu kopyala** | ✅ Evet (açık) | Basit, geliştirme için |
| **Docker container** | ❌ Hayır | Orta, önerilen |
| **PyInstaller .exe** | ❌ Hayır | Zor, Windows için |
| **Cloud/SaaS (Render/VPS)** | ❌ Hayır | En profesyonel |

**Pratik öneri:** Kısa vadede kaynak kodu ver ama lisans dosyası ekle.  
Uzun vadede Docker imajı hazırla — müşteri sadece `docker-compose up` çalıştırır, kodu görmez.

---

## B. Kendi Laptop'ınla Müşteri Sahaya Git — Adım Adım

### 1️⃣ Önce Laptop'ında Sistemi Hazırla

```bash
# Projeyi aç
cd smartsafe

# .env düzenle — üretim modu
FLASK_DEBUG=False
SECRET_KEY=<güçlü-key>

# Çalıştır
python core/run.py
# → http://localhost:5000/admin açılmalı
```

### 2️⃣ Müşteri Ağına Bağlan

Kameralar her zaman **yerel ağda (LAN/intranet)** çalışır — internete açık değil.

```
Laptop → [Ethernet veya WiFi] → Müşteri Switch/Router → DVR/NVR → Kameralar
```

**Bağlanma yöntemleri:**
- **En basit:** Laptop'ı müşterinin ethernet ağına tak
- **Kablosuz:** Müşterinin iç WiFi'sine bağlan (kameralar aynı ağda olmalı)
- **Uzak test:** VPN + port yönlendirme (gelecekte SaaS kurulum için)

### 3️⃣ Kameranın IP'sini Bul

```bash
# Windows — ağdaki cihazları tara
for /L %i in (1,1,254) do ping -n 1 -w 50 192.168.1.%i | findstr "TTL"

# Linux / macOS
nmap -sn 192.168.1.0/24

# Ya da DVR/NVR web arayüzünden kamera listesi bak (her DVR'ın web UI'si var)
# Tipik DVR web adresi: http://192.168.1.1 veya http://192.168.1.100
```

### 4️⃣ RTSP URL'ini Test Et

```bash
# VLC ile test (en hızlı yöntem):
# Medya > Ağ Akışı Aç > URL yapıştır

# FFmpeg ile test:
ffplay "rtsp://admin:admin123@192.168.1.100:554/stream1"

# Python ile test:
python -c "import cv2; cap=cv2.VideoCapture('rtsp://admin:admin123@192.168.1.100:554/stream1'); print('Bağlı!' if cap.isOpened() else 'Bağlanamadı')"
```

### 5️⃣ SmartSafe'e Kamera Ekle

Admin panel → Şirket oluştur → Kamera Ekle:
```
İsim: Ana Giriş Kamerası
RTSP URL: rtsp://admin:admin123@192.168.1.100:554/stream1
Tip: ip_camera / dvr / nvr
Sektör: (şirketin sektörü otomatik gelir)
```

Detection → Başlat → PPE analizi başlar.

---

## C. Kurulum (İşletim Sistemine Göre)

### 🪟 Windows

```powershell
# 1. Python 3.11 kur: https://python.org (PATH'e ekle kutusunu işaretle!)
# 2. Proje klasörüne git
cd C:\SmartSafe

# 3. Sanal ortam
python -m venv venv
venv\Scripts\activate

# 4. Paketler
pip install -r core\requirements.txt

# 5. .env oluştur (Notepad ile)
copy .env.example .env
notepad .env

# 6. Çalıştır
python core\run.py
# → http://localhost:5000

# Production için (Windows Service gibi çalıştır):
pip install waitress
python -c "from waitress import serve; from core.app import create_app; serve(create_app(), host='0.0.0.0', port=5000)"
```

**Windows'ta arka planda otomatik başlat (NSSM ile):**
```powershell
# NSSM indir: https://nssm.cc
nssm install SmartSafe "C:\SmartSafe\venv\Scripts\python.exe" "C:\SmartSafe\core\run.py"
nssm start SmartSafe
# Artık Windows başlayınca otomatik çalışır
```

### 🐧 Linux (Ubuntu/Debian)

```bash
# 1. Python 3.11
sudo apt update && sudo apt install python3.11 python3.11-venv python3-pip -y

# 2. Proje
cd /opt/smartsafe
python3.11 -m venv venv
source venv/bin/activate
pip install -r core/requirements.txt

# 3. .env
cp .env.example .env && nano .env

# 4. Test
python core/run.py

# 5. Production (systemd servisi)
sudo nano /etc/systemd/system/smartsafe.service
```

```ini
[Unit]
Description=SmartSafe PPE Detection
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/opt/smartsafe
ExecStart=/opt/smartsafe/venv/bin/gunicorn -w 2 -b 0.0.0.0:5000 "core.app:create_app()"
Restart=always
EnvironmentFile=/opt/smartsafe/.env

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now smartsafe
# Nginx reverse proxy eklemek istersen:
sudo apt install nginx -y
```

### 🍎 macOS

```bash
# 1. Homebrew yoksa kur
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 2. Python
brew install python@3.11

# 3. Proje
cd ~/smartsafe
python3.11 -m venv venv
source venv/bin/activate
pip install -r core/requirements.txt

# 4. .env
cp .env.example .env && open -e .env

# 5. Çalıştır
python core/run.py
# → http://localhost:5000
```

### 🐳 Docker (Kod Gizli, Tüm OS Çalışır — Önerilen)

```dockerfile
# Dockerfile (proje köküne ekle)
FROM python:3.11-slim
WORKDIR /app
COPY core/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5000
CMD ["python", "core/run.py"]
```

```yaml
# docker-compose.yml
services:
  smartsafe:
    build: .
    ports:
      - "5000:5000"
    volumes:
      - ./models:/app/models        # Modeller ayrı mount
      - smartsafe_db:/app/data      # DB kalıcı
    env_file: .env
    restart: unless-stopped
volumes:
  smartsafe_db:
```

```bash
# Müşteride çalıştırma (Docker Desktop gerekli):
docker-compose up -d
# → http://localhost:5000 hazır. Kod içinde gizli.
```

---

## D. Kamera Sistemi Entegrasyon Analizi

### Gerçekten Hazır mıyız?

| Özellik | Durum | Açıklama |
|---|---|---|
| **RTSP (IP Kamera)** | ✅ Hazır | Tüm IP kameralar desteklenir |
| **DVR/NVR (RTSP üzerinden)** | ✅ Hazır | Her kanal ayrı RTSP stream |
| **Çoklu kamera** | ✅ Hazır | Plan bazlı limit, thread-safe |
| **ONVIF (otomatik keşif)** | ⚠️ Eksik | Büyük kurumsal sistemler için önemli |
| **MJPEG stream** | ✅ Hazır | Eski kameralar için |
| **HLS (web oynatıcı)** | ⚠️ Kısmi | RTSP→HLS dönüşümü eksik |
| **HTTP snapshot** | ✅ Çalışır | Bazı kameralar JPEG endpoint sunar |

**Kritik eksik: ONVIF** — büyük kurumsal tesislerde (fabrika, havalimanı, AVM) kamera keşfi ve kontrol için standart protokol. Kameralar ağda otomatik bulunur.

### Kamera Markası → RTSP URL Formatları

```
# Hikvision
rtsp://admin:PASSWORD@IP:554/Streaming/Channels/101   # Kanal 1 Ana Stream
rtsp://admin:PASSWORD@IP:554/Streaming/Channels/102   # Kanal 1 Sub Stream

# Dahua
rtsp://admin:PASSWORD@IP:554/cam/realmonitor?channel=1&subtype=0  # Main
rtsp://admin:PASSWORD@IP:554/cam/realmonitor?channel=1&subtype=1  # Sub

# Reolink
rtsp://admin:PASSWORD@IP:554/h264Preview_01_main

# TP-Link Tapo
rtsp://admin:PASSWORD@IP:554/stream1

# Axis
rtsp://admin:PASSWORD@IP/axis-media/media.amp

# Hanwha (Samsung)
rtsp://admin:PASSWORD@IP:554/profile1/media.sst

# Generic (çoğu Çin markası)
rtsp://admin:PASSWORD@IP:554/live/ch0

# DVR/NVR üzerinden kanal bazlı (Hikvision NVR)
rtsp://admin:PASSWORD@NVR_IP:554/Streaming/Channels/201  # 2. kamera
rtsp://admin:PASSWORD@NVR_IP:554/Streaming/Channels/301  # 3. kamera
```

### DVR/NVR Bağlantı Mimarisi

```
┌─────────────────────────────────────────┐
│           MÜŞTERI TESİSİ                │
│                                          │
│  [Kamera 1] ─┐                          │
│  [Kamera 2] ─┤                          │
│  [Kamera N] ─┤──► [DVR/NVR] ──────────►│── (RTSP üzerinden)
│               │      │                   │
│               │   [Switch]               │
└───────────────┼──────┼───────────────────┘
                │      │
                └──────┼──► [SmartSafe Sunucu]
                              (Aynı LAN'da)
```

SmartSafe **doğrudan NVR'a** RTSP ile bağlanır — kameralar NVR'a bağlı olsa bile her kanal kendi RTSP URL'si ile erişilebilir.

### Şu An Olmayan: Genel (Public) IP ile Kamera

Kameralar ve DVR'lar genellikle özel IP (192.168.x.x / 10.x.x.x) ile çalışır.  
Uzaktan erişim için müşteri tarafında şunlar gerekir:

```
Seçenek 1: Port yönlendirme (basit ama güvensiz)
Router → Port 554 → DVR/NVR IP'sine yönlendir
→ Dışarıdan: rtsp://MÜŞTERİ_GENEL_IP:554/stream1

Seçenek 2: VPN (önerilen, güvenli)
SmartSafe sunucu + DVR aynı VPN ağında
→ Özel IP ile doğrudan bağlanılır

Seçenek 3: SmartSafe sunucu onsitede çalışır (en yaygın)
→ Sunucu müşterinin LAN'ında, kameralar doğrudan görünür
```

---

## E. .gitignore & GitHub Push Kontrolü

```bash
# Push öncesi kontrol — büyük dosyalar git'te olmamalı:
git ls-files --others --ignored --exclude-standard | head -20

# .pt dosyaları tracked mı?
git ls-files models/ | grep ".pt"  # Sonuç BOŞ olmalı

# .env tracked mı?
git ls-files .env  # Sonuç BOŞ olmalı

# İlk push
git init  # Eğer henüz yapılmadıysa
git add .
git commit -m "Initial commit - SmartSafe PPE Detection v1.0"
git remote add origin <repo-url>
git push -u origin main
```

---

## F. Model Dosyaları — Sunucuya Taşıma

Modeller Git'te yok. Her kurulumda ayrıca kopyalanmalı:

```
Gerekli dosyalar:
  models/yolo9e.pt                                         → Ana SH17 modeli (~140MB)  
  models/sh17_food_beverage/.../weights/best.pt            → Gıda sektörü modeli (~112MB)
                                                              (SH17'den AYRI, Roboflow kaynaklı)

Taşıma yöntemleri:
  USB bellek        → Sahaya git, elle kopyala
  scp/rsync         → ssh erişimliyse uzaktan kopyala
  Özel dosya sunucu → İç ağda HTTP sunucu (python -m http.server)
  Google Drive      → İndir, kopyala
```

---

## G. Saha Test Kontrol Listesi

```
KURULUM
[ ] Python 3.11 kurulu, PATH'de
[ ] pip install -r requirements.txt — hata yok
[ ] .env dolduruldu (SECRET_KEY, FOUNDER_PASSWORD)
[ ] models/ klasöründe yolo9e.pt VE best.pt mevcut
[ ] python core/run.py — hata yok

ADMIN PANELİ
[ ] http://localhost:5000/admin açılıyor
[ ] FOUNDER_PASSWORD ile giriş yapıldı
[ ] Yeni şirket oluşturuldu (sektör seçildi)
[ ] Şirket hesabıyla login çalışıyor

KAMERA
[ ] Laptop müşteri ağına bağlandı (ping 192.168.x.x OK)
[ ] DVR/NVR web arayüzüne ulaşıldı
[ ] RTSP URL VLC ile test edildi — görüntü geliyor
[ ] SmartSafe'e kamera eklendi
[ ] Detection "Başlat" → video akıyor

DETECTION
[ ] PPE tespiti görsel olarak doğrulandı
[ ] İhlal kaydedildi → log/uyarı oluştu
[ ] Çoklu kamera → aynı anda çalışıyor
```
