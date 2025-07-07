# 🚀 SmartSafe AI - Render.com + Supabase Deployment Guide

## **📋 Kurulum Adımları**

### **1. Supabase Kurulumu**

1. **https://supabase.com** adresine git
2. **GitHub ile giriş yap**
3. **"New Project"** oluştur:
   - **Name:** `SmartSafe PPE Detection`
   - **Database Password:** Güçlü şifre oluştur (kaydet!)
   - **Region:** `West US (Oregon)`
   - **Plan:** `Free Tier`

4. **2-3 dakika bekle** (database kurulumu)

### **2. Database Connection String Al**

1. **Supabase Dashboard** → **Settings** → **Database**
2. **Connection String** bölümüne git
3. **URI** formatını kopyala:
   ```
   postgresql://postgres:[YOUR-PASSWORD]@db.[YOUR-PROJECT-ID].supabase.co:5432/postgres
   ```
4. **[YOUR-PASSWORD]** yerine şifreni yaz

### **3. Render.com Deployment**

1. **https://render.com** adresine git
2. **GitHub ile giriş yap**
3. **"New Web Service"** oluştur
4. **Repository seç:** `SmartSafe-PPE-Detection`

### **4. Render.com Ayarları**

**Build & Deploy:**
- **Name:** `smartsafe-ppe-detection`
- **Region:** `Oregon (US West)`
- **Branch:** `master`
- **Runtime:** `Python 3`
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `python smartsafe_saas_api.py`

### **5. Environment Variables**

**Render.com Dashboard** → **Environment** → **Add Environment Variable**:

```bash
# Database Configuration
DATABASE_URL=postgresql://postgres:[YOUR-PASSWORD]@db.[YOUR-PROJECT-ID].supabase.co:5432/postgres

# Application Configuration
FLASK_ENV=production
FLASK_DEBUG=False
SECRET_KEY=your-super-secret-key-here-change-this

# Security
JWT_SECRET_KEY=your-jwt-secret-key-here
BCRYPT_LOG_ROUNDS=12

# File Upload
MAX_CONTENT_LENGTH=16777216
UPLOAD_FOLDER=static/uploads

# Detection Configuration
DETECTION_CONFIDENCE_THRESHOLD=0.5
DETECTION_MODEL_PATH=data/models/yolov8n.pt

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/smartsafe.log
```

### **6. Deployment Süreci**

1. **"Create Web Service"** tıkla
2. **Build süreci başlayacak** (5-10 dakika)
3. **Deployment tamamlandıktan sonra** URL'yi al
4. **Test et:** `https://your-app-name.onrender.com`

---

## **🔧 Troubleshooting**

### **Build Hataları**

**1. Requirements.txt eksik paketler:**
```bash
# requirements.txt'ye ekle:
psycopg2-binary>=2.9.0
python-dotenv>=1.0.0
```

**2. Database bağlantı hatası:**
- Environment variables'ı kontrol et
- Supabase database'in aktif olduğunu doğrula
- Connection string'i doğru kopyaladığını kontrol et

**3. Model dosyaları eksik:**
- YOLO model dosyalarının yüklü olduğunu kontrol et
- `download_models.py` çalıştır

### **Runtime Hataları**

**1. Database table yok:**
- Uygulama ilk çalıştığında otomatik table oluşturur
- Manuel olarak database adapter'ı çalıştır

**2. Memory limiti:**
- Render.com free tier: 512MB RAM
- Büyük model dosyaları için optimize et

---

## **📊 Monitoring & Logs**

### **Render.com Dashboard**
- **Logs:** Real-time uygulama logları
- **Metrics:** CPU, Memory, Network kullanımı
- **Events:** Deployment geçmişi

### **Supabase Dashboard**
- **Database:** Tablo ve veri görüntüleme
- **SQL Editor:** Query çalıştırma
- **Logs:** Database logları

---

## **🔄 Data Migration**

### **Mevcut SQLite Verisini Taşıma**

```bash
# 1. Environment variables ayarla
export DATABASE_URL="postgresql://postgres:..."

# 2. Migration script çalıştır
python database_migration.py

# 3. Verification
python -c "from database_adapter import get_db_adapter; db = get_db_adapter(); print(f'Database type: {db.db_type}')"
```

---

## **🚀 Production Checklist**

### **Güvenlik**
- [ ] `SECRET_KEY` değiştirildi
- [ ] `JWT_SECRET_KEY` değiştirildi
- [ ] `FLASK_DEBUG=False` ayarlandı
- [ ] Database şifresi güçlü

### **Performance**
- [ ] YOLO model optimizasyonu
- [ ] Image compression ayarları
- [ ] Database indexleri oluşturuldu

### **Monitoring**
- [ ] Error logging aktif
- [ ] Performance metrics takibi
- [ ] Database backup planı

### **Backup**
- [ ] Supabase otomatik backup aktif
- [ ] Critical data export planı
- [ ] Disaster recovery prosedürü

---

## **💡 Best Practices**

### **Environment Variables**
```bash
# .env dosyası (local development)
DATABASE_URL=  # Boş bırak (SQLite kullan)
FLASK_ENV=development
FLASK_DEBUG=True
SECRET_KEY=dev-key-change-in-production
```

### **Database Connections**
- Connection pooling kullan
- Timeout ayarları optimizele
- Error handling ekle

### **File Storage**
- Render.com ephemeral storage
- S3 veya Cloudinary entegrasyonu önerilir
- Uploaded files için external storage

---

## **🎯 Next Steps**

1. **Custom Domain:** Render.com'da custom domain ayarla
2. **SSL Certificate:** Otomatik Let's Encrypt
3. **CDN:** Cloudflare entegrasyonu
4. **Monitoring:** Sentry error tracking
5. **Analytics:** Google Analytics entegrasyonu

---

## **📞 Support**

**Render.com Issues:**
- Dashboard → Support
- Community Forum
- Documentation

**Supabase Issues:**
- Dashboard → Support
- Discord Community
- GitHub Issues

**SmartSafe AI Issues:**
- GitHub Repository
- Technical Documentation
- Contact Developer 