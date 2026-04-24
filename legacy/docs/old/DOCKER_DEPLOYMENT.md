# 🐳 SmartSafe AI - Docker Deployment Guide

## 📋 Ön Gereksinimler

### Sistem Gereksinimleri
- **Docker**: 20.10.0+
- **Docker Compose**: 2.0.0+
- **RAM**: Minimum 4GB, Önerilen 8GB+
- **Disk**: Minimum 20GB boş alan
- **CPU**: 2+ çekirdek

### Kurulum
```bash
# Docker kurulumu (Ubuntu/Debian)
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Docker Compose kurulumu
sudo curl -L "https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

---

## 🚀 Hızlı Başlangıç

### 1. Environment Ayarları
```bash
# Environment dosyasını kopyala
cp docker-compose.env .env

# Güvenlik ayarlarını düzenle
nano .env
```

**⚠️ ÖNEMLİ**: Aşağıdaki değerleri mutlaka değiştirin:
```bash
SECRET_KEY=your-super-secret-key-change-this-in-production
REDIS_PASSWORD=your-redis-password
POSTGRES_PASSWORD=your-postgres-password
GRAFANA_PASSWORD=your-grafana-password
```

### 2. SSL Sertifikası Hazırlama

#### Geliştirme için Self-Signed:
```bash
mkdir -p nginx/ssl
cd nginx/ssl

# Self-signed sertifika oluştur
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout smartsafe.key \
    -out smartsafe.crt \
    -subj "/C=TR/ST=Istanbul/L=Istanbul/O=SmartSafe AI/CN=smartsafe.ai"

cd ../..
```

#### Production için Let's Encrypt:
```bash
# Certbot kurulumu
sudo apt install certbot

# Sertifika alma
sudo certbot certonly --standalone -d smartsafe.ai -d www.smartsafe.ai

# Sertifikaları kopyala
sudo cp /etc/letsencrypt/live/smartsafe.ai/fullchain.pem nginx/ssl/smartsafe.crt
sudo cp /etc/letsencrypt/live/smartsafe.ai/privkey.pem nginx/ssl/smartsafe.key
```

### 3. Deployment

#### Tam Stack Deployment:
```bash
# Tüm servisleri başlat
docker-compose up -d

# Logları izle
docker-compose logs -f
```

#### Minimal Deployment (Sadece Web + Database):
```bash
# Sadece temel servisleri başlat
docker-compose up -d web redis postgres

# Nginx olmadan test
docker-compose up -d web redis postgres
```

---

## 📊 Monitoring ve Health Check

### Health Check
```bash
# Application health
curl http://localhost:5000/health

# Metrics
curl http://localhost:5000/metrics
```

### Monitoring Dashboard'ları
- **Grafana**: http://localhost:3000
- **Prometheus**: http://localhost:9090
- **Application**: https://localhost (SSL) veya http://localhost:5000 (Direct)

### Monitoring Kurulumu
```bash
# Grafana'ya erişim
Username: admin
Password: [docker-compose.env'deki GRAFANA_PASSWORD]

# Prometheus veri kaynağı ekle:
URL: http://prometheus:9090
```

---

## 💾 Backup ve Restore

### Manuel Backup
```bash
# Backup script'ini çalıştır
docker-compose exec backup /backup.sh

# Backup dosyalarını görüntüle
ls -la backups/
```

### Otomatik Backup
Backup servisi günlük olarak otomatik backup alır. Konfigürasyon:
```bash
BACKUP_INTERVAL=daily
BACKUP_RETENTION_DAYS=30
```

### Restore İşlemi
```bash
# PostgreSQL restore
docker-compose exec postgres pg_restore -U smartsafe -d smartsafe_saas /backups/database/smartsafe_db_YYYYMMDD_HHMMSS.sql.gz

# SQLite restore
docker cp backups/database/smartsafe_sqlite_YYYYMMDD_HHMMSS.db.gz smartsafe-web:/app/data/smartsafe_saas.db
```

---

## 🔧 Bakım ve Güncelleme

### Uygulama Güncellemesi
```bash
# Yeni image build et
docker-compose build web

# Servisleri yeniden başlat
docker-compose up -d web

# Eski image'leri temizle
docker image prune -f
```

### Database Migration
```bash
# Migration çalıştır (gerekirse)
docker-compose exec web python -c "from smartsafe_multitenant_system import MultiTenantDatabase; db = MultiTenantDatabase(); db.init_database()"
```

### Log Yönetimi
```bash
# Tüm logları görüntüle
docker-compose logs -f

# Belirli servis logları
docker-compose logs -f web
docker-compose logs -f postgres
docker-compose logs -f nginx

# Log rotasyonu
docker system prune -f
```

---

## 🔍 Sorun Giderme

### Yaygın Sorunlar

#### 1. Container başlamıyor
```bash
# Container durumunu kontrol et
docker-compose ps

# Logları incele
docker-compose logs <service_name>

# Container'ı yeniden başlat
docker-compose restart <service_name>
```

#### 2. Database bağlantı hatası
```bash
# PostgreSQL bağlantısını test et
docker-compose exec postgres psql -U smartsafe -d smartsafe_saas -c "SELECT 1;"

# Database container'ını yeniden başlat
docker-compose restart postgres
```

#### 3. SSL sertifika hatası
```bash
# Sertifika dosyalarını kontrol et
ls -la nginx/ssl/

# Sertifika geçerliliğini test et
openssl x509 -in nginx/ssl/smartsafe.crt -text -noout
```

#### 4. Port çakışması
```bash
# Kullanılan portları kontrol et
netstat -tulpn | grep -E ":(80|443|5000|5432|6379|3000|9090)"

# docker-compose.yml'de port ayarlarını değiştir
```

### Debug Modu
```bash
# Debug modunda başlat
FLASK_ENV=development docker-compose up web

# Container içine gir
docker-compose exec web bash

# Manual komut çalıştır
docker-compose exec web python smartsafe_saas_api.py
```

---

## ⚡ Performance Optimizasyonu

### Production Ayarları
```bash
# .env dosyasında:
FLASK_ENV=production
FLASK_DEBUG=false

# Nginx worker sayısını artır (nginx.conf):
worker_processes auto;
worker_connections 2048;

# PostgreSQL optimize et
# shared_buffers = 256MB
# max_connections = 200
```

### Resource Limits
docker-compose.yml'ye ekle:
```yaml
services:
  web:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 2G
        reservations:
          cpus: '0.5'
          memory: 512M
```

### Scaling
```bash
# Web servisini ölçeklendir
docker-compose up -d --scale web=3

# Load balancer ekle (nginx.conf):
upstream smartsafe_backend {
    server web_1:5000;
    server web_2:5000;
    server web_3:5000;
}
```

---

## 🔐 Güvenlik

### Firewall Ayarları
```bash
# UFW ile port yönetimi
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw deny 5000/tcp  # Direct access'i engelle
sudo ufw deny 5432/tcp  # Database access'i engelle
sudo ufw enable
```

### SSL Güvenlik
nginx.conf'da:
```nginx
# Modern SSL configuration
ssl_protocols TLSv1.2 TLSv1.3;
ssl_ciphers ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384;
ssl_prefer_server_ciphers off;

# Security headers
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
```

### Secret Management
```bash
# Docker secrets kullan (production için)
echo "your-secret-key" | docker secret create smartsafe_secret_key -

# docker-compose.yml'de:
secrets:
  - smartsafe_secret_key
```

---

## 📈 Monitoring Metrikları

### Önemli Metrikler
- **Response Time**: Ortalama yanıt süresi
- **Request Rate**: Saniye başına istek sayısı
- **Error Rate**: Hata oranı
- **Database Connections**: Aktif bağlantı sayısı
- **Memory Usage**: Bellek kullanımı
- **CPU Usage**: İşlemci kullanımı

### Alert Kurulumu
Grafana'da alert kuralları:
```yaml
# High Error Rate Alert
expr: rate(smartsafe_errors_total[5m]) > 0.1
for: 2m
labels:
  severity: warning
```

---

## 🚀 Production Deployment Checklist

### Deployment Öncesi
- [ ] SSL sertifikası hazır
- [ ] Environment variables güvenli
- [ ] Backup sistemi çalışıyor
- [ ] Monitoring kurulu
- [ ] Firewall ayarları tamam
- [ ] Database migration yapıldı
- [ ] Load testing tamamlandı

### Deployment Sonrası
- [ ] Health check'ler geçiyor
- [ ] All services running
- [ ] SSL certificate valid
- [ ] Backup working
- [ ] Monitoring collecting data
- [ ] Performance acceptable
- [ ] Security scan passed

---

## 📞 Destek

### Log Dosyaları
```bash
# Application logs
docker-compose logs web > smartsafe-app.log

# Database logs
docker-compose logs postgres > smartsafe-db.log

# System logs
docker-compose logs > smartsafe-full.log
```

### Sistem Bilgileri
```bash
# Docker info
docker version
docker-compose version

# System resources
docker system df
docker stats

# Container details
docker-compose ps
docker-compose top
```

**🆘 Acil durumda**: 
1. `docker-compose down` ile tüm servisleri durdur
2. Log dosyalarını topla
3. Backup'tan restore yap
4. `docker-compose up -d` ile yeniden başlat 