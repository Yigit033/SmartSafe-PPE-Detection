# SmartSafe AI - Gerçek Kamera Sistemi Kurulum Rehberi

## 🚀 Sistem Kurulumu ve Çalıştırma

### 1. Sistem Gereksinimleri
```bash
- Python 3.8+
- OpenCV
- PostgreSQL (production) veya SQLite (test)
- Ağ bağlantısı (kameralar için)
- Port 5000 (web arayüzü için)
```

### 2. Kurulum Adımları

#### A. Bağımlılıkları Yükleyin
```bash
pip install -r requirements.txt
```

#### B. Veritabanını Başlatın
```bash
python database_adapter.py
```

#### C. Sistemi Başlatın
```bash
python smartsafe_saas_api.py
```

## 🏢 Şirket Kurulumu

### 1. Yeni Şirket Oluşturma
```bash
# Admin paneli üzerinden veya doğrudan veritabanı ile
python -c "
from smartsafe_multitenant_system import MultiTenantDatabase
db = MultiTenantDatabase()
db.create_company('ACME_CONSTRUCTION', 'ACME İnşaat', 'Türkiye', 'construction', 10)
"
```

### 2. Şirket Kullanıcısı Oluşturma
```bash
python -c "
from smartsafe_multitenant_system import MultiTenantDatabase
db = MultiTenantDatabase()
db.create_user('ACME_CONSTRUCTION', 'admin', 'admin@acme.com', 'password123', 'admin')
"
```

## 📹 Kamera Ekleme ve Test Etme

### 1. Web Arayüzü Üzerinden

#### A. Sisteme Giriş
1. Tarayıcıda `http://localhost:5000` adresine gidin
2. Şirket bilgileri ile giriş yapın
3. Dashboard'a erişin

#### B. Kamera Ekleme
1. Dashboard'da **"Kamera Ekle"** butonuna tıklayın
2. Kamera bilgilerini girin:
   - **Kamera Adı**: "Üretim Alanı Kamera 1"
   - **IP Adresi**: 192.168.1.190
   - **Port**: 8080
   - **Kullanıcı Adı**: admin (varsa)
   - **Parola**: password (varsa)
   - **Protokol**: HTTP veya RTSP
   - **Stream Yolu**: /video

#### C. Kamera Testi
1. **"Kamera Testi"** butonuna tıklayın
2. Bağlantı durumunu kontrol edin
3. Başarılı ise **"Kamera Ekle"** butonuna tıklayın

### 2. Programatik Kamera Ekleme

```python
from camera_integration_manager import RealCameraManager, RealCameraConfig
from smartsafe_multitenant_system import MultiTenantDatabase

# Kamera yapılandırması
camera_config = RealCameraConfig(
    camera_id="CAM_001",
    name="Üretim Alanı Kamera 1",
    ip_address="192.168.1.190",
    port=8080,
    username="admin",
    password="admin123",
    protocol="http",
    stream_path="/video",
    resolution=(1920, 1080),
    fps=25
)

# Kamera yöneticisi
camera_manager = RealCameraManager()

# Kamera testi
test_result = camera_manager.test_real_camera_connection(camera_config)
if test_result['success']:
    print("✅ Kamera bağlantısı başarılı!")
    
    # Veritabanına ekle
    db = MultiTenantDatabase()
    camera_data = {
        'name': camera_config.name,
        'ip_address': camera_config.ip_address,
        'port': camera_config.port,
        'username': camera_config.username,
        'password': camera_config.password,
        'protocol': camera_config.protocol,
        'stream_path': camera_config.stream_path,
        'resolution': f"{camera_config.resolution[0]}x{camera_config.resolution[1]}",
        'fps': camera_config.fps,
        'location': 'Üretim Alanı'
    }
    
    success, camera_id = db.add_camera('ACME_CONSTRUCTION', camera_data)
    if success:
        print(f"✅ Kamera veritabanına eklendi: {camera_id}")
else:
    print(f"❌ Kamera bağlantısı başarısız: {test_result['error']}")
```

## 🔧 Kamera Konfigürasyonları

### 1. Yaygın Kamera Türleri

#### A. IP Webcam (Android)
```python
camera_config = RealCameraConfig(
    name="Android IP Webcam",
    ip_address="192.168.1.100",
    port=8080,
    protocol="http",
    stream_path="/video",
    auth_type="none"
)
```

#### B. RTSP Güvenlik Kamerası
```python
camera_config = RealCameraConfig(
    name="RTSP Güvenlik Kamerası",
    ip_address="192.168.1.200",
    port=554,
    username="admin",
    password="12345",
    protocol="rtsp",
    stream_path="/stream1",
    auth_type="basic"
)
```

#### C. HTTP Kamerası
```python
camera_config = RealCameraConfig(
    name="HTTP Kamerası",
    ip_address="192.168.1.150",
    port=8080,
    username="user",
    password="pass",
    protocol="http",
    stream_path="/mjpeg",
    auth_type="basic"
)
```

### 2. Kamera Keşif Sistemi

#### A. Otomatik Kamera Keşfi
```python
# Web arayüzünde "Kamera Keşfet" butonuna tıklayın
# Veya programatik olarak:

from camera_integration_manager import ProfessionalCameraManager

camera_manager = ProfessionalCameraManager()
discovery_result = camera_manager.discover_and_sync_cameras(
    company_id='ACME_CONSTRUCTION',
    network_range='192.168.1.0/24'
)

print(f"Keşfedilen kamera sayısı: {discovery_result['total_discovered']}")
```

## 🧪 Test Senaryoları

### 1. Kamera Bağlantı Testi
```bash
python test_real_camera_system.py
```

### 2. Manuel Test Adımları

#### A. Kamera Erişilebilirlik Testi
```bash
# Ping testi
ping 192.168.1.190

# Port testi
telnet 192.168.1.190 8080
```

#### B. Stream URL Testi
```bash
# Tarayıcıda test edin:
http://192.168.1.190:8080/video
http://192.168.1.190:8080/shot.jpg
```

#### C. RTSP Stream Testi
```bash
# VLC ile test edin:
rtsp://admin:password@192.168.1.190:554/stream1
```

## 🏭 Saha Kurulumu

### 1. Ağ Konfigürasyonu
```bash
# Kameraların aynı ağda olduğundan emin olun
# Örnek ağ yapısı:
Router: 192.168.1.1
Server: 192.168.1.10
Camera 1: 192.168.1.190
Camera 2: 192.168.1.191
Camera 3: 192.168.1.192
```

### 2. Kamera Yerleştirme
- **Yükseklik**: 2.5-3 metre
- **Açı**: 15-30 derece aşağı
- **Kapsama**: 10-15 metre alan
- **Aydınlatma**: Yeterli ışık seviyesi

### 3. Sistem Başlatma Sırası
```bash
# 1. Kameraları açın ve IP adreslerini ayarlayın
# 2. Ağ bağlantısını test edin
# 3. SmartSafe AI sistemini başlatın
python smartsafe_saas_api.py

# 4. Web arayüzüne erişin
http://localhost:5000

# 5. Kameraları ekleyin ve test edin
```

## 🔍 Sorun Giderme

### 1. Yaygın Sorunlar

#### A. Kamera Bağlantısı Yok
```bash
# Çözüm adımları:
1. IP adresini kontrol edin
2. Port numarasını doğrulayın
3. Güvenlik duvarını kontrol edin
4. Kamera güç durumunu kontrol edin
```

#### B. Kimlik Doğrulama Hatası
```bash
# Çözüm adımları:
1. Kullanıcı adı/parola doğruluğunu kontrol edin
2. Auth type'ı değiştirin (basic/digest/none)
3. Kamera web arayüzüne erişim test edin
```

#### C. Stream Kalitesi Düşük
```bash
# Çözüm adımları:
1. Çözünürlük ayarlarını kontrol edin
2. FPS değerini ayarlayın
3. Ağ bant genişliğini kontrol edin
4. Kamera lens temizliğini kontrol edin
```

### 2. Debug Modları

#### A. Detaylı Log
```bash
# Sistem loglarını izleyin
tail -f logs/smartsafe.log
```

#### B. Kamera Test Modu
```python
# Test scriptini çalıştırın
python test_real_camera_system.py
```

## 📊 Performans İzleme

### 1. Sistem Durumu
- Dashboard'da kamera durumları
- Bağlantı süreleri
- FPS değerleri
- Hata oranları

### 2. Kamera Metrikleri
- Çözünürlük
- Kalite skoru
- Bağlantı süresi
- Desteklenen özellikler

## 🎯 Üretim Ortamı

### 1. PostgreSQL Konfigürasyonu
```bash
# .env dosyasında:
DATABASE_URL=postgresql://user:password@localhost/smartsafe_db
```

### 2. Güvenlik Ayarları
```bash
# Güvenlik duvarı kuralları
# SSL sertifikaları
# Kamera şifreleri
```

### 3. Yedekleme
```bash
# Veritabanı yedekleme
# Kamera konfigürasyonu yedekleme
# Log dosyası rotasyonu
```

## 📞 Teknik Destek

### Sistem Gereksinimleri
- Python 3.8+
- OpenCV 4.5+
- PostgreSQL 12+ (production)
- Minimum 4GB RAM
- 100GB disk alanı

### İletişim
- Teknik destek için sistem loglarını hazırlayın
- Kamera modellerini ve IP adreslerini not edin
- Hata mesajlarını kaydedin

---

**Not**: Bu rehber gerçek kamera entegrasyonu için hazırlanmıştır. Test ortamında önce yerel kameralar ile deneme yapmanız önerilir. 