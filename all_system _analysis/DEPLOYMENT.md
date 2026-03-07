# SmartSafe AI — Saha Deployment Kılavuzu v2.0

*Windows · Linux · macOS · Docker · Tüm Kamera / DVR / NVR Sistemleri*

> **Bu doküman**, SmartSafe AI sistemini bir şirketin sahası veya kendi sunucunuzda kurarak kurumsal kamera altyapısına bağlamak ve PPE detection çalıştırmak için bilmeniz gereken **her şeyi** kapsar.

---

## İçindekiler

1. [Genel Bakış](#1-genel-bakış)
2. [Ön Hazırlık — Sahaya Gitmeden Önce](#2-ön-hazırlık--sahaya-gitmeden-önce)
3. [Kurulum (OS Bazlı)](#3-kurulum-os-bazlı)
4. [GPU / CUDA Yapılandırması](#4-gpu--cuda-yapılandırması)
5. [Docker ile Deployment (Önerilen)](#5-docker-ile-deployment-önerilen)
6. [Kamera Altyapısı — Tüm Senaryolar](#6-kamera-altyapısı--tüm-senaryolar)
7. [DVR/NVR Bağlantısı — Adım Adım](#7-dvrnvr-bağlantısı--adım-adım)
8. [IP Kamera (Bağımsız) Bağlantısı](#8-ip-kamera-bağımsız-bağlantısı)
9. [ONVIF Keşfi](#9-onvif-keşfi)
10. [Toplu IP ile Kamera Ekleme (Batch Provisioning)](#10-toplu-ip-ile-kamera-ekleme)
11. [PPE Detection Başlatma](#11-ppe-detection-başlatma)
12. [Kamera Sağlık İzleme (Health Dashboard)](#12-kamera-sağlık-izleme)
13. [Stream Watchdog & Otomatik Kurtarma](#13-stream-watchdog--otomatik-kurtarma)
14. [Ağ Yapılandırması & Firewall](#14-ağ-yapılandırması--firewall)
15. [Güvenlik & Kod Koruma](#15-güvenlik--kod-koruma)
16. [Saha Test Kontrol Listesi](#16-saha-test-kontrol-listesi)
17. [Sorun Giderme](#17-sorun-giderme)
18. [Model Dosyaları](#18-model-dosyaları)
19. [Performans & Ölçeklendirme](#19-performans--ölçeklendirme)

---

## 1. Genel Bakış

SmartSafe AI, kurumsal tesislerde kamera altyapısına bağlanarak **gerçek zamanlı PPE (Kişisel Koruyucu Donanım) tespiti** yapar. Sistem **on-premise** çalışır — sunucu müşterinin tesisinde veya sizin taşıdığınız bir donanımda çalışır.

### Desteklenen Kamera Senaryoları

| Senaryo | Açıklama | Durum |
|---------|----------|-------|
| **DVR/NVR üzerinden** | Tek IP → N kanal RTSP | ✅ Tam destek |
| **Bağımsız IP kamera** | Her kamera ayrı IP | ✅ Tam destek |
| **ONVIF otomatik keşif** | Ağda kamera bulma | ✅ Tam destek |
| **Toplu IP ekleme** | IT'den alınan IP listesi | ✅ Tam destek |
| **MJPEG stream** | Eski kameralar | ✅ Tam destek |
| **Android IP Webcam** | Mobil test cihazı | ✅ Tam destek |

### Mimari

```
┌─────────────── MÜŞTERI TESİSİ ───────────────┐
│                                                │
│  [Kamera 1] ──┐                                │
│  [Kamera 2] ──┤──► [DVR/NVR] ◄── IP: X.X.X.X  │
│  [Kamera N] ──┘      │                        │
│                       │ RTSP                   │
│                    [Switch]                    │
│                       │                        │
│              [SmartSafe Sunucu]                 │
│              (Aynı LAN'da)                     │
└────────────────────────────────────────────────┘
```

---

## 2. Ön Hazırlık — Sahaya Gitmeden Önce

### Bilmeniz Gerekenler

Sahaya gitmeden önce **müşteriden/IT ekibinden** aşağıdaki bilgileri alın:

| Bilgi | Neden Gerekli | Örnek |
|-------|---------------|-------|
| DVR/NVR IP adresi(leri) | Bağlanmak için | `192.168.1.100` |
| DVR/NVR port (RTSP) | RTSP stream portu | Genellikle `554` |
| DVR/NVR port (HTTP/Web) | Web arayüz | Genellikle `80` veya `8080` |
| Kullanıcı adı | Kimlik doğrulama | `admin` |
| Şifre | Kimlik doğrulama | `Admin123` |
| DVR/NVR markası | RTSP URL formatı | Hikvision, Dahua, XMEye... |
| Kaç kamera bağlı | Kapasite planlaması | 16, 32, 64... |
| Hangi kameralar PPE için | Seçim yapabilmek için | "Sadece üretim hattı" |
| Ağ bilgisi (VLAN var mı?) | Bağlantı sorunu önleme | `192.168.1.0/24` |

### Yanınızda Bulunması Gerekenler

```
✅ Laptop (GPU'lu önerilir — NVIDIA GTX 1060+)
✅ Ethernet kablosu (mutlaka!)
✅ USB bellek (yedek — modeller + kurulum dosyaları)
✅ Projenin çalışır hali (önceden test edilmiş)
✅ VLC Media Player (RTSP test için)
✅ Bu doküman (çıktı veya dijital)
```

---

## 3. Kurulum (OS Bazlı)

### 🪟 Windows

```powershell
# 1. Python 3.11 kur: https://python.org
#    ⚠️ "Add Python to PATH" kutusunu işaretle!

# 2. Proje klasörüne git
cd C:\SmartSafe

# 3. Sanal ortam oluştur
python -m venv venv
venv\Scripts\activate

# 4. Bağımlılıkları kur
pip install -r core\requirements.txt

# 5. .env dosyası oluştur
copy .env.example .env
notepad .env    # SECRET_KEY ve diğer ayarları düzenle

# 6. Çalıştır (Geliştirme)
python core\run.py
# → http://localhost:5000

# 7. Production (Waitress WSGI Server)
pip install waitress
python -c "from waitress import serve; from core.app import create_app; serve(create_app(), host='0.0.0.0', port=5000, threads=8)"

# 8. Windows Servisi (Otomatik başlatma — NSSM)
# NSSM indir: https://nssm.cc
nssm install SmartSafe "C:\SmartSafe\venv\Scripts\python.exe" "C:\SmartSafe\core\run.py"
nssm set SmartSafe AppDirectory "C:\SmartSafe"
nssm start SmartSafe
# Artık Windows açıldığında otomatik çalışır
```

### 🐧 Linux (Ubuntu/Debian)

```bash
# 1. Python 3.11
sudo apt update && sudo apt install python3.11 python3.11-venv python3-pip -y

# 2. Projeyi kopyala
cd /opt/smartsafe
python3.11 -m venv venv
source venv/bin/activate
pip install -r core/requirements.txt

# 3. .env
cp .env.example .env && nano .env

# 4. Test
python core/run.py

# 5. Production (systemd servisi)
sudo tee /etc/systemd/system/smartsafe.service << 'EOF'
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
EOF

sudo systemctl enable --now smartsafe

# 6. Nginx reverse proxy (opsiyonel ama önerilen)
sudo apt install nginx -y
sudo tee /etc/nginx/sites-available/smartsafe << 'EOF'
server {
    listen 80;
    server_name _;
    client_max_body_size 100M;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 300;
    }
}
EOF
sudo ln -sf /etc/nginx/sites-available/smartsafe /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo systemctl reload nginx
```

### 🍎 macOS

```bash
brew install python@3.11
cd ~/smartsafe
python3.11 -m venv venv
source venv/bin/activate
pip install -r core/requirements.txt
cp .env.example .env
python core/run.py
```

---

## 4. GPU / CUDA Yapılandırması

> **Neden GPU?** YOLO modelimiz GPU olmadan çalışabilir (CPU mode) ama performans büyük fark eder:
> - **GPU (RTX 3060)**: ~25 FPS
> - **CPU (i7-12700)**: ~3-5 FPS

### NVIDIA GPU Kurulumu

```bash
# 1. NVIDIA sürücü kontrolü
nvidia-smi   # Eğer çıktı yoksa sürücü kurulu değil

# 2. CUDA Toolkit kur (11.8 veya 12.x)
# https://developer.nvidia.com/cuda-downloads

# 3. PyTorch CUDA sürümünü kur
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# 4. CUDA çalışıyor mu kontrol
python -c "import torch; print('CUDA:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'N/A')"
```

### CPU-Only Mode

GPU yoksa sistem otomatik olarak CPU moduna düşer. Ek bir yapılandırma gerekmez. Ancak aynı anda çalıştırabileceğiniz kamera sayısı sınırlı olur (~2-4 kamera).

---

## 5. Docker ile Deployment (Önerilen)

Docker kullanıldığında müşteri kaynak kodunu **görmez** ve kurulum çok basitleşir.

### Dockerfile

```dockerfile
FROM python:3.11-slim

# Sistem bağımlılıkları (OpenCV için)
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx libglib2.0-0 libsm6 libxext6 libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY core/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/')" || exit 1

CMD ["python", "core/run.py"]
```

### docker-compose.yml

```yaml
version: '3.8'
services:
  smartsafe:
    build: .
    ports:
      - "5000:5000"
    volumes:
      - ./models:/app/models              # Model dosyaları
      - smartsafe_data:/app/data          # Veritabanı (kalıcı)
      - smartsafe_logs:/app/logs          # Loglar
    env_file: .env
    restart: unless-stopped
    # GPU desteği (NVIDIA Container Toolkit gerekli)
    # deploy:
    #   resources:
    #     reservations:
    #       devices:
    #         - driver: nvidia
    #           capabilities: [gpu]
    networks:
      - smartsafe_net

  # Opsiyonel: Nginx reverse proxy
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
    depends_on:
      - smartsafe
    restart: unless-stopped
    networks:
      - smartsafe_net

networks:
  smartsafe_net:
    driver: bridge

volumes:
  smartsafe_data:
  smartsafe_logs:
```

### Docker GPU Desteği

```bash
# NVIDIA Container Toolkit kur (bir kez)
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list
sudo apt update && sudo apt install -y nvidia-container-toolkit
sudo systemctl restart docker

# docker-compose.yml'deki GPU bölümünü aktifleştir (yorum satırlarını kaldır)
docker-compose up -d
```

### Müşteri Lokasyonunda Çalıştırma

```bash
# Tek komut — tüm sistem ayağa kalkar
docker-compose up -d

# Durum kontrolü
docker-compose ps
docker-compose logs -f smartsafe

# Güncelleme
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

---

## 6. Kamera Altyapısı — Tüm Senaryolar

### Senaryo 1: Şirkette DVR/NVR var (EN YAYGIN)

```
Durum: 100 kamerası var, hepsi 1 veya birkaç DVR/NVR'a bağlı.
       Sadece belirli alanlardaki 8 kamerada PPE detection istiyor.

Çözüm:
1. IT'den DVR/NVR'ın IP adresini ve giriş bilgilerini al
2. SmartSafe'de DVR/NVR'ı ekle
3. Sistem otomatik olarak tüm kanalları keşfeder
4. Sadece istenen 8 kanalı seç ve detection başlat

⚡ TEK IP ile TÜM KANALLARA ERİŞİRSİN
   Örnek: DVR IP = 192.168.1.100
   → Kanal 1: rtsp://admin:pass@192.168.1.100:554/...channel=1
   → Kanal 2: rtsp://admin:pass@192.168.1.100:554/...channel=2
   → Kanal 64: rtsp://admin:pass@192.168.1.100:554/...channel=64
```

### Senaryo 2: Her kameranın ayrı IP'si var

```
Durum: IP kameralar doğrudan switch'e bağlı, DVR/NVR yok.

Çözüm:
1. Her kameranın IP adresini IT'den al
2. "Toplu IP Ekleme" bölümünü kullan → IP listesini yapıştır
3. Sistem her IP için ONVIF + RTSP testi yapar
4. İstenen kameraları seç ve detection başlat
```

### Senaryo 3: Birden fazla DVR/NVR var (büyük tesisler)

```
Durum: Fabrikada 3 ayrı bina, her birinde ayrı DVR.
       Bina-1 DVR: 192.168.1.100 (32 kamera)
       Bina-2 DVR: 192.168.2.100 (16 kamera)
       Bina-3 DVR: 10.0.5.100   (48 kamera)

Çözüm:
1. Her DVR'ı ayrı ayrı SmartSafe'e ekle
2. Her DVR'ın kanallarını bağımsız olarak yönet
3. İstenen kanalları seçip detection başlat
⚠️ SmartSafe sunucu TÜM DVR ağlarına erişebilmeli (VLAN routing!)
```

### Senaryo 4: Kamera ağı VLAN ile izole (kurumsal ağlar)

```
Durum: Kameralar ayrı VLAN'da (ör: 10.x.x.x), ofis ağı 192.168.x.x

Çözüm:
1. IT'den SmartSafe sunucuya kamera VLAN'ına erişim iste
   → Router/L3 Switch'te VLAN arası routing açılmalı
   → Veya SmartSafe sunucu kamera VLAN'ına direkt bağlanmalı
2. Alternatif: SmartSafe sunucuya iki NIC (ağ kartı) tak
   → eth0: 192.168.1.x (yönetim / web erişimi)
   → eth1: 10.0.0.x (kamera ağına erişim)
```

### Senaryo 5: Uzaktan erişim (remote/VPN)

```
Durum: SmartSafe sunucu müşteri binasında değil, merkezi bir konumda.

Çözüm:
1. Site-to-Site VPN kur (önerilen: WireGuard veya IPsec)
2. SmartSafe sunucu → VPN → Müşteri LAN → DVR/NVR
3. RTSP streaming VPN üzerinden akar
⚠️ VPN bant genişliği yeterli olmalı (kamera başına ~2-5 Mbps)
⚠️ Gecikme (latency) < 100ms olmalı
```

---

## 7. DVR/NVR Bağlantısı — Adım Adım

### Adım 1: Ağa Bağlan & Erişimi Test Et

```bash
# DVR/NVR'a ping at
ping 192.168.1.100

# DVR web arayüzünü aç (tarayıcıdan)
# http://192.168.1.100  veya  http://192.168.1.100:80

# RTSP portunu kontrol et
# Windows:
Test-NetConnection -ComputerName 192.168.1.100 -Port 554
# Linux:
nc -zv 192.168.1.100 554
```

### Adım 2: RTSP URL'ini Test Et (VLC ile)

Her DVR markasının RTSP URL formatı farklıdır:

```
# ═══ Hikvision ═══
rtsp://admin:PASS@IP:554/Streaming/Channels/101   # Kanal 1, Ana stream
rtsp://admin:PASS@IP:554/Streaming/Channels/201   # Kanal 2, Ana stream
rtsp://admin:PASS@IP:554/Streaming/Channels/N01   # Kanal N, Ana stream
# Alt stream (düşük kalite, daha az bant genişliği):
rtsp://admin:PASS@IP:554/Streaming/Channels/102   # Kanal 1, Sub stream

# ═══ Dahua / XMEye ═══
rtsp://admin:PASS@IP:554/cam/realmonitor?channel=1&subtype=0   # Main
rtsp://admin:PASS@IP:554/cam/realmonitor?channel=1&subtype=1   # Sub
# Veya (XMEye/Genel Çin DVR):
rtsp://IP:554/user=admin&password=PASS&channel=1&stream=0.sdp

# ═══ Reolink ═══
rtsp://admin:PASS@IP:554/h264Preview_01_main

# ═══ TP-Link (Tapo) ═══
rtsp://admin:PASS@IP:554/stream1

# ═══ Axis ═══
rtsp://admin:PASS@IP/axis-media/media.amp

# ═══ Hanwha (Samsung) ═══
rtsp://admin:PASS@IP:554/profile1/media.sst

# ═══ Uniview ═══
rtsp://admin:PASS@IP:554/unicast/c1/s0/live
```

**VLC ile test:**
```
Medya → Ağ Akışı Aç → RTSP URL'i yapıştır → Oynat
```

**Python ile test (command line):**
```bash
python -c "import cv2; cap=cv2.VideoCapture('rtsp://admin:pass@192.168.1.100:554/Streaming/Channels/101'); print('✅ Bağlantı başarılı!' if cap.isOpened() else '❌ Bağlanamadı'); cap.release()"
```

### Adım 3: SmartSafe'e DVR Ekle

1. `http://sunucu:5000` adresine gidin
2. Admin panelinden şirket oluşturun (veya mevcut olana girin)
3. **Kamera Yönetimi** sayfasına gidin
4. **"DVR/NVR Sistem Yönetimi"** bölümünde:

| Alan | Açıklama | Örnek |
|------|----------|-------|
| DVR Adı | İstediğiniz isim | `Merkez DVR` |
| IP Adresi | DVR'ın ağ adresi | `192.168.1.100` |
| Port | Web/HTTP portu | `80` |
| Kullanıcı Adı | DVR giriş | `admin` |
| Şifre | DVR şifresi | `Admin123` |
| DVR Tipi | Marka seçimi | `Genel DVR` |
| Maksimum Kanal | Toplam kanal sayısı | `16` |

5. **"+ DVR Ekle"** butonuna tıklayın

### Adım 4: Kanalları Keşfet & Detection Başlat

1. DVR eklendikten sonra sağ taraftaki **"DVR PPE Detection"** panelinde:
   - **Kanal Seçimi** bölümünde kanallar otomatik listelenir
   - İstediğiniz kanalları seçin (checkbox ile)
   - **"✓ Tümü"** ile hepsini seçin veya **"Filtrele"** ile arama yapın
2. **Detection Modu** seçin (İnşaat, Gıda, vs.)
3. **"▶ Detection Başlat"** butonuna tıklayın
4. Seçili kanallarda gerçek zamanlı PPE tespiti başlar

---

## 8. IP Kamera (Bağımsız) Bağlantısı

DVR/NVR olmadan doğrudan IP kameraları bağlamak için:

### Tek Kamera Ekleme (Manuel)

1. Kamera Yönetimi → **"Kamera Ekleme"** formunda:
   - Kamera Adı: `Üretim Hattı K1`
   - IP Adresi: `192.168.1.50`
   - Port: `554` (RTSP) veya `8080` (HTTP)
   - Kullanıcı / Şifre: kamera giriş bilgileri
2. **"⚡ Hızlı Test"** ile bağlantıyı doğrulayın
3. **"Kaydet"** ile ekleyin

### Akıllı Tespit (Smart Detect)

IP girip **"⚡ Akıllı Tespit"** butonuna basarsanız sistem otomatik olarak:
- Bilinen portları tarar (554, 80, 8080, 443...)
- Kamera markasını ve RTSP URL formatını tespit eder
- Uygun bağlantı bilgilerini doldurur

---

## 9. ONVIF Keşfi

ONVIF, IP kameraları ağda otomatik olarak bulan bir endüstri standardıdır.

### Nasıl Kullanılır

1. Kamera Yönetimi → **"ONVIF Keşif"** bölümü
2. Ağ aralığı girin (ör: `192.168.1.1` → `192.168.1.254`)
3. **"🔍 ONVIF Tarama"** butonuna tıklayın
4. Bulunan cihazlar listelenir → seçip ekleyin

### ⚠️ ONVIF Çalışmadığında

Kurumsal ağlarda ONVIF çoğu zaman **çalışmaz** çünkü:
- **UDP multicast (239.255.255.250:3702)** kapalıdır
- Kamera ağı **VLAN ile izole** edilmiştir
- Bazı markalar ONVIF'i varsayılan olarak kapatır

**Çözüm:** IT ekibinden IP listesini alın → **"Toplu IP Ekleme"** bölümünü kullanın.

---

## 10. Toplu IP ile Kamera Ekleme

IT ekibinden aldığınız kamera IP listesini toplu olarak eklemek için:

1. Kamera Yönetimi → **"📦 Toplu IP ile Kamera Ekleme"** bölümü
2. Textarea'ya IP listesini girin:

```
Format: IP, port, kullanıcı, şifre, isim
Sadece IP girmek de yeterlidir.

192.168.1.100, 554, admin, pass123, Üretim Sahası K1
192.168.1.101, 554, admin, pass123, Üretim Sahası K2
192.168.1.102, 554, admin, pass123, Depo Giriş
10.0.5.50, 80, , , Ofis Girişi
10.0.5.51
```

3. **"ONVIF ile dene"** toggle'ı: Her IP için önce ONVIF, başarısız olursa RTSP probe
4. **"Kanalları otomatik bul"** toggle'ı: DVR/NVR ise alt kanalları keşfet
5. **"Toplu Ekle"** butonuna tıklayın
6. Sonuç tablosunda her IP için başarılı/başarısız durumunu görün

---

## 11. PPE Detection Başlatma

### Tek Kamerada Detection

Kamera tablosunda ilgili kameranın **"PPE Detection"** sütunundaki toggle butonuna tıklayın.
- 🟢 **Aktif**: Detection çalışıyor
- ⚪ **Durdu**: Detection pasif

### Birden Fazla Kamerada Toplu Detection

1. Kamera tablosunda sol taraftaki **checkbox'ları** işaretleyin
2. Üstte beliren **"Seçililerde Detection Başlat"** butonuna tıklayın
3. Tüm seçili kameralarda aynı anda detection başlar

### DVR Kanallarında Detection

DVR panelinde:
1. İstediğiniz kanalları seçin
2. Detection modunu belirleyin
3. **"▶ Detection Başlat"** → Seçili tüm kanallarda PPE tespiti başlar

### Canlı Detection İzleme

Kamera tablosunda **🧠** (beyin) ikonuna tıklayarak o kameranın canlı detection akışını izleyebilirsiniz. Detection sonuçları (bounding box + label) gerçek zamanlı olarak video üzerine çizilir.

---

## 12. Kamera Sağlık İzleme

Kamera tablosunun üzerindeki **"💓 Kamera Sağlık Durumu"** paneli gerçek zamanlı bilgi gösterir:

| Badge | Açıklama |
|-------|----------|
| 🟢 **Online** | Aktif bağlantısı olan kameralar |
| 🔴 **Offline** | Bağlantısı kopmuş kameralar |
| 🔵 **Detection Aktif** | PPE detection çalışan kameralar |
| 🛡️ **Watchdog** | Otomatik kurtarma sistemi durumu |

Panel **30 saniyede bir otomatik yenilenir**.

---

## 13. Stream Watchdog & Otomatik Kurtarma

SmartSafe, kamera stream'lerini otomatik olarak izler ve müdahale eder:

| Özellik | Değer | Açıklama |
|---------|-------|----------|
| Stale threshold | 30 sn | Frame gelmezse "stale" olarak işaretlenir |
| Max restart attempt | 10 | Maksimum yeniden başlatma denemesi |
| Backoff | 5s → 120s | Her başarısız denemede bekleme süresi artar |
| Check interval | 15 sn | Stream durumu kontrol periyodu |

**Reconnect Logic:**
- Bağlantı koparsa 5 deneme × üstel backoff (1s → 16s)
- Alternatif URL'leri sırayla dener
- Tüm denemeler tükenirse kamerayı "dead" olarak işaretler

---

## 14. Ağ Yapılandırması & Firewall

### SmartSafe Sunucu Gereksinimleri

| Port | Protokol | Yön | Açıklama |
|------|----------|-----|----------|
| `5000` | TCP | Gelen | Web arayüzü (HTTP) |
| `554` | TCP | Giden | RTSP (kameralara bağlanma) |
| `80/443` | TCP | Giden | ONVIF / kamera web arayüzü |
| `3702` | UDP | Gelen+Giden | ONVIF WS-Discovery (multicast) |

### Firewall Kuralları (Windows)

```powershell
# SmartSafe web erişimi
netsh advfirewall firewall add rule name="SmartSafe Web" dir=in action=allow protocol=TCP localport=5000

# ONVIF Discovery (opsiyonel)
netsh advfirewall firewall add rule name="ONVIF Discovery" dir=in action=allow protocol=UDP localport=3702
```

### Firewall Kuralları (Linux)

```bash
sudo ufw allow 5000/tcp comment "SmartSafe Web"
sudo ufw allow 3702/udp comment "ONVIF Discovery"
```

### Bant Genişliği Hesaplaması

```
Kamera başına ortalama RTSP bant genişliği:
  Ana stream (1080p, 25fps): ~4-8 Mbps
  Alt stream (D1, 15fps):    ~1-2 Mbps

Örnek: 8 kamera × 4 Mbps = 32 Mbps (switch bağlantısı yeterli)
Örnek: 64 kamera × 2 Mbps (sub) = 128 Mbps (gigabit gerekli)

⚠️ Detection için sub stream genellikle yeterlidir ve sistemi yormaz
```

---

## 15. Güvenlik & Kod Koruma

| Yöntem | Müşteri Kodu Görür mü? | Kurulum |
|--------|------------------------|---------|
| Kaynak kodu (geliştirme) | ✅ Evet | Basit |
| Docker container | ❌ Hayır | Önerilen |
| PyInstaller .exe | ❌ Hayır | Zor, Windows |

### .env Dosyası (Asla Git'e Eklemeyin!)

```env
# Zorunlu
SECRET_KEY=çok-güçlü-rastgele-key
FLASK_DEBUG=False

# Opsiyonel
MAX_CONCURRENT_CAMERAS=25
MAX_INFERENCE_WORKERS=4
FRAME_SKIP=2
```

---

## 16. Saha Test Kontrol Listesi

```
═══ KURULUM ═══
[ ] Python 3.11 kurulu, PATH'de
[ ] pip install -r requirements.txt — hatasız
[ ] .env dosyası oluşturuldu ve düzenlendi
[ ] models/ klasöründe yolo9e.pt ve food_beverage best.pt mevcut
[ ] python core/run.py — hatasız çalışıyor
[ ] GPU kontrol: nvidia-smi (varsa CUDA aktif)

═══ AĞ ═══
[ ] SmartSafe sunucu ağa bağlandı (ethernet önerilir)
[ ] DVR/NVR'a ping atılıyor (ping 192.168.X.X)
[ ] DVR web arayüzü açılıyor (http://192.168.X.X)
[ ] RTSP portu (554) erişilebilir
[ ] VLC ile RTSP stream test edildi — görüntü geliyor
[ ] Firewall kuralları eklendi (port 5000 açık)

═══ ADMİN PANELİ ═══
[ ] http://sunucu:5000 açılıyor
[ ] Admin girişi yapıldı
[ ] Şirket oluşturuldu (sektör seçildi)
[ ] Şirket kullanıcısı ile giriş çalışıyor

═══ DVR/NVR ═══
[ ] DVR/NVR bilgileri girildi (IP, port, kullanıcı, şifre)
[ ] DVR başarıyla eklendi
[ ] Kanallar keşfedildi / listelendi
[ ] En az 1 kanalda stream görüntüsü geldi
[ ] Detection modunda bounding box görünüyor

═══ IP KAMERA (DVR olmadan) ═══
[ ] Kamera IP girildi ve test edildi
[ ] Kamera başarıyla eklendi
[ ] Detection başlatıldı ve çalışıyor

═══ TOPLU EKLEME ═══
[ ] Birden fazla IP girildi
[ ] Toplu ekleme başarılı
[ ] Sağlık panelinde online/offline doğru gösteriyor

═══ DETECTION ═══
[ ] PPE tespiti görsel olarak doğrulandı (bbox + label)
[ ] Tekli detection toggle çalışıyor
[ ] Toplu detection (checkbox + başlat) çalışıyor
[ ] DVR kanallarında detection çalışıyor
[ ] Canlı detection modalı açılıyor
[ ] İhlal kaydedildi → dashboard'da görünüyor

═══ DAYANIKLILIK ═══
[ ] Kamera bağlantısı kasıtlı olarak kesildi → watchdog yeniden bağlandı
[ ] Çoklu kamera aynı anda çalışıyor (en az 4)
[ ] Sistem 1+ saat kararlı çalıştı
```

---

## 17. Sorun Giderme

### RTSP Bağlantı Sorunları

| Sorun | Olası Neden | Çözüm |
|-------|-------------|-------|
| Bağlanamadı | Yanlış IP/port | `ping` ve `nc -zv IP 554` ile kontrol |
| 401 Unauthorized | Yanlış kullanıcı/şifre | DVR web arayüzünden doğrulayın |
| Timeout | Firewall engelliyor | IT'den port 554 açtırın |
| Siyah ekran | Yanlış kanal/URL formatı | VLC ile doğru RTSP URL'i bulun |
| Kekeme görüntü | Bant genişliği yetersiz | Sub stream kullanın |
| "Stream failed" | DVR meşgul/dolu | Bazı DVR'lar eşzamanlı bağlantı sınırlar (genellikle 4-6) → sub stream kullanın |

### ONVIF Sorunları

| Sorun | Çözüm |
|-------|-------|
| Cihaz bulunamadı | Multicast kapalı olabilir → Toplu IP Ekleme kullanın |
| VLAN izolasyonu | IT'den routing açtırın veya sunucuya ikinci NIC takın |
| Marka desteklemiyor | DVR'ın ONVIF ayarlarını kontrol edin, veya manuel RTSP kullanın |

### Performans Sorunları

| Sorun | Çözüm |
|-------|-------|
| Düşük FPS | GPU kontrolü yapın, CPU mode ise kamera sayısını azaltın |
| Yüksek bellek kullanımı | `FRAME_SKIP=3` yapın, sub stream kullanın |
| Sunucu çökmesi | `MAX_CONCURRENT_CAMERAS` değerini düşürün |

### Genel

| Sorun | Çözüm |
|-------|-------|
| Sayfa açılmıyor | Python çalışıyor mu? `python core/run.py` |
| 500 hatası | Logları kontrol edin: `logs/` klasörü |
| Session timeout | Tarayıcı cookie'lerini temizleyin |

---

## 18. Model Dosyaları

Model dosyaları Git'te saklanmaz. Her kurulumda ayrıca kopyalanmalıdır.

```
Gerekli dosyalar:
  models/yolo9e.pt                                         (~140 MB)
  models/sh17_food_beverage/.../weights/best.pt            (~112 MB)

Taşıma yöntemleri:
  USB bellek        → Sahaya git, elle kopyala
  scp/rsync         → SSH erişimliyse uzaktan kopyala
  HTTP sunucu       → python -m http.server 8888 (iç ağda)
  Google Drive      → indirip kopyala
```

---

## 19. Performans & Ölçeklendirme

### Donanım Önerileri

| Kapasite | CPU | RAM | GPU | Disk |
|----------|-----|-----|-----|------|
| 1-4 kamera | i5/Ryzen 5 | 8 GB | Opsiyonel | 100 GB SSD |
| 5-16 kamera | i7/Ryzen 7 | 16 GB | GTX 1060+ | 256 GB SSD |
| 17-64 kamera | i9/Ryzen 9 | 32 GB | RTX 3060+ | 512 GB SSD |
| 64+ kamera | Xeon/Threadripper | 64 GB | RTX 3090/A100 | 1 TB NVMe |

### Yapılandırma Parametreleri

```env
# Eşzamanlı kamera limiti (RAM ve GPU'ya göre ayarlayın)
MAX_CONCURRENT_CAMERAS=25

# Inference thread sayısı
MAX_INFERENCE_WORKERS=4

# Frame atlama (her N frame'de bir detection — sistemik yükü azaltır)
FRAME_SKIP=2

# Stream Watchdog
STALE_THRESHOLD_SEC=30
CHECK_INTERVAL_SEC=15
MAX_RESTART_ATTEMPTS=10
```

### Alt Stream Kullanımı (Kaynak Tasarrufu)

Detection için yüksek çözünürlüklü ana stream gerekmez. Alt stream (D1 / CIF / 480p) yeterlidir ve:
- Bant genişliğini **%70** azaltır
- GPU/CPU yükünü **%50** azaltır
- DVR eşzamanlı bağlantı limitine takılmaz

Hikvision alt stream: `...Channels/102` (son rakam `2`)
Dahua alt stream: `...subtype=1`

---

© 2026 SmartSafe AI. Tüm hakları saklıdır.
