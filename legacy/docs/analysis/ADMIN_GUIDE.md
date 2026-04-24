# SmartSafe Admin Kılavuzu

## Admin Paneline Erişim

**URL:** `http://localhost:10000/admin`  
**Şifre:** `.env` dosyasındaki `FOUNDER_PASSWORD` değeri (default: `smartsafe2024admin`)

---

## Admin Olarak Neler Yapabilirsin?

### 🏢 Şirket Yönetimi
| İşlem | Nerede |
|---|---|
| Yeni şirket oluştur | Admin → Şirketler → Yeni Ekle |
| Şirket planını değiştir | Şirket Detay → subscription_type |
| Kamera limitini ayarla | Şirket Detay → max_cameras |
| Şirketi aktif/pasif yap | Şirket Detay → status |
| Demo hesap oluştur | account_type = 'demo', demo_expires_at doldur |

### 📷 Kamera Yönetimi
| İşlem | Nerede |
|---|---|
| Şirket kameralarını gör | Admin → Şirket → Kameralar |
| Kamera ekle/sil | Kamera sayfasından |
| DVR/NVR bağlantısı | Admin → DVR Sistemleri |

### 📊 Raporlar & İzleme
- Tüm şirketlerin ihlal loglarını görüntüle
- Detection geçmişi ve compliance raporları
- `/metrics` endpoint → Prometheus metrikleri

---

## Plan Yapısı (DB'de max_cameras ile kontrol)

| Plan | `subscription_type` | `max_cameras` |
|---|---|---|
| Starter | `starter` | 5 |
| Professional | `professional` | 25 |
| Enterprise | `enterprise` | 100+ |
| Demo | (account_type=`demo`) | 2 |

**Limiti değiştirmek için** (SQLite):
```sql
UPDATE companies SET max_cameras = 50, subscription_type = 'professional'
WHERE company_id = 'XXXX';
```

---

## Hızlı DB Erişimi (geliştirme)
```bash
# SQLite doğrudan aç
sqlite3 smartsafe_saas.db

# Tüm şirketleri listele
SELECT company_id, company_name, subscription_type, max_cameras, status FROM companies;
```

---

## Detection Worker Konfigürasyonu (.env)

| Değişken | Açıklama | Default |
|---|---|---|
| `MAX_CONCURRENT_CAMERAS` | Sistem geneli hard cap | 32 |
| `MAX_INFERENCE_WORKERS` | Eşzamanlı YOLO inference | CPU/2 veya 4 (GPU) |
| `DETECTION_CONFIDENCE_THRESHOLD` | Tespit hassasiyeti | 0.5 |
| `FRAME_SKIP` | Kaç frame'de bir tespit | 3 |
