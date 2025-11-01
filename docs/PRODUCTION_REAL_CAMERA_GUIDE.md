# SmartSafe AI - Production Real Camera Deployment Guide

## 🚀 Akıllı Kamera Tespiti Sistemi

### Yeni Özellikler
- **Otomatik Model Tespiti**: Kamera markasını ve modelini otomatik algılar
- **Akıllı Konfigürasyon**: Bağlantı parametrelerini otomatik önerir
- **Genişletilmiş Destek**: Hikvision, Dahua, Axis, Foscam ve Generic kamera desteği

### Kurulum Adımları

1. **Gerekli Paketler**
```bash
pip install opencv-python requests ipaddress
```

2. **Akıllı Tespit Kullanımı**
```python
from camera_integration_manager import SmartCameraDetector

detector = SmartCameraDetector()
result = detector.smart_detect_camera("192.168.1.100")

if result['success']:
    print(f"Kamera tespit edildi: {result['model']}")
    print(f"Konfigürasyon: {result['config']}")
```

3. **API Endpoint**
```bash
POST /api/company/{company_id}/cameras/smart-test
{
    "ip_address": "192.168.1.100",
    "camera_name": "Test Kamera"
}
```

## 🔧 Production Konfigürasyonu

### 1. Güvenlik Ayarları
```yaml
# config.yaml
security:
  camera_network:
    allowed_ips: ["192.168.1.0/24", "10.0.0.0/8"]
    firewall_rules: true
    ssl_required: true
  
  authentication:
    timeout: 30
    max_retries: 3
    rate_limit: "100/minute"
```

### 2. Kamera Modeli Veritabanı
```yaml
camera_models:
  hikvision:
    ports: [80, 554, 8000, 8080, 443]
    paths: ["/ISAPI/Streaming/channels/101", "/Streaming/Channels/101"]
    default_credentials:
      username: "admin"
      password: "admin"
  
  dahua:
    ports: [80, 554, 37777, 443]
    paths: ["/cam/realmonitor", "/cgi-bin/magicBox.cgi"]
    default_credentials:
      username: "admin"
      password: "admin"
```

## 📊 Monitoring ve Alerting

### 1. Kamera Durumu İzleme
```python
# monitoring/camera_health.py
def check_camera_health():
    for camera in get_all_cameras():
        if not camera.is_accessible():
            send_alert(f"Kamera {camera.name} erişilemez")
```

### 2. Performans Metrikleri
- Bağlantı süresi
- Tespit doğruluğu
- Hata oranı
- Kullanıcı memnuniyeti

## 🛠️ Sorun Giderme

### Yaygın Sorunlar

1. **Kamera Tespit Edilemiyor**
   - Firewall ayarlarını kontrol edin
   - Port taraması yapın: `nmap -p 80,554,8080 192.168.1.100`
   - Kamera web arayüzüne erişimi test edin

2. **Bağlantı Zaman Aşımı**
   - Network latency kontrol edin
   - Timeout değerlerini artırın
   - Kamera firmware'ini güncelleyin

3. **Kimlik Doğrulama Hatası**
   - Varsayılan şifreleri deneyin
   - Kamera ayarlarından şifre sıfırlayın
   - Manufacturer'ın dokümantasyonunu kontrol edin

### Debug Modu
```bash
export DEBUG_CAMERA=1
python smartsafe_saas_api.py
```

## 📋 Deployment Checklist

### Pre-Installation
- [ ] Network güvenlik ayarları
- [ ] Firewall kuralları
- [ ] SSL sertifikaları
- [ ] Database backup

### Post-Installation
- [ ] Kamera tespit testleri
- [ ] API endpoint testleri
- [ ] Monitoring kurulumu
- [ ] Alert sistemi testleri

### Pre-Production
- [ ] Load testing
- [ ] Security audit
- [ ] Performance optimization
- [ ] Documentation review

## 🔗 Destek ve İletişim

### Log Dosyaları
- `/logs/camera_detection.log`
- `/logs/api_requests.log`
- `/logs/error.log`

### Debug Komutları
```bash
# Kamera tespit logları
tail -f logs/camera_detection.log

# API istekleri
tail -f logs/api_requests.log

# Hata logları
tail -f logs/error.log
```

### İletişim
- Teknik Destek: support@smartsafe.ai
- Dokümantasyon: docs.smartsafe.ai
- GitHub Issues: github.com/smartsafe/ppe-detection

---

**Not**: Bu guide sürekli güncellenmektedir. En son versiyon için dokümantasyon sayfasını ziyaret edin. 