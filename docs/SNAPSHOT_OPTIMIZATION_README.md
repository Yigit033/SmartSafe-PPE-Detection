# 📸 Snapshot Optimization - Akıllı Fotoğraf Çekme Sistemi

## 🎯 PROBLEM

**Önceki Durum:**
- Her frame'de ihlal varsa snapshot çekiliyordu
- Aynı ihlal için 100+ fotoğraf
- Gereksiz disk kullanımı
- Veri kirliliği

**Örnek:**
```
Kişi 5 dakika boyunca baretsiz → 300+ snapshot (her 1 saniyede 1)
```

---

## ✅ ÇÖZÜM: AKILLI SNAPSHOT SİSTEMİ

### 📋 Yeni Mantık:

```
1. İhlal Başladı (İLK KEZ)
   ├─ Kişi görünür mü? → Kontrol et
   ├─ Frame'de yeterince büyük mü? → Kontrol et
   └─ ✅ SNAPSHOT ÇEK (Eksik ekipmanlarla)

2. İhlal Devam Ediyor
   └─ ❌ SNAPSHOT ÇEKME (Gereksiz)

3. İhlal Bitti (Ekipmanlar takıldı)
   └─ ✅ SNAPSHOT ÇEK (Tam ekipmanlarla)
```

### 🎯 Sonuç:
```
Kişi 5 dakika boyunca baretsiz → 2 snapshot
  1. İhlal başlangıcı (baretsiz)
  2. İhlal bitişi (baretli)
```

**Veri Azaltma: 150x daha az snapshot! 🎉**

---

## 📸 SNAPSHOT TÜRLERİ

### 1. **İhlal Snapshot'ı** (Violation Snapshot)
- **Ne zaman:** İhlal ilk başladığında
- **İçerik:** Kişi eksik ekipmanlarla
- **Amaç:** İhlali kanıtlamak
- **Dosya adı:** `PERSON_XXX_no_helmet_timestamp.jpg`
- **Database kolonu:** `snapshot_path`

### 2. **Çözüm Snapshot'ı** (Resolution Snapshot)
- **Ne zaman:** İhlal bittiğinde (ekipmanlar takıldı)
- **İçerik:** Kişi tam ekipmanlarla
- **Amaç:** İhlalin ne kadar sürdüğünü göstermek
- **Dosya adı:** `PERSON_XXX_no_helmet_resolved_timestamp.jpg`
- **Database kolonu:** `resolution_snapshot_path`

---

## 🔍 GÖRÜNÜRLİK KONTROLLERI

### Snapshot çekilmeden önce:

1. **Frame İçinde Mi?**
   ```python
   if px1 < 0 or py1 < 0 or px2 > frame_width or py2 > frame_height:
       # Kişi frame dışında, snapshot atla
   ```

2. **Yeterince Büyük Mü?**
   ```python
   person_area = (px2 - px1) * (py2 - py1)
   frame_area = frame_height * frame_width
   
   if person_area < (frame_area * 0.05):  # %5'ten küçükse
       # Kişi çok küçük, snapshot atla
   ```

3. **Bounding Box Geçerli Mi?**
   ```python
   if not person_bbox or len(person_bbox) != 4:
       # Geçersiz bbox, snapshot atla
   ```

---

## 📊 ÖRNEK SENARYO

### Senaryo: İşçi 10 dakika baretsiz çalışıyor

**Önceki Sistem:**
```
Frame 1  → Snapshot (baretsiz)
Frame 2  → Snapshot (baretsiz)
Frame 3  → Snapshot (baretsiz)
...
Frame 600 → Snapshot (baretsiz)
Toplam: 600 snapshot
```

**Yeni Sistem:**
```
Frame 1   → ✅ Snapshot (baretsiz) - İhlal başladı
Frame 2   → ❌ Snapshot yok - İhlal devam ediyor
Frame 3   → ❌ Snapshot yok - İhlal devam ediyor
...
Frame 600 → ✅ Snapshot (baretli) - İhlal bitti
Toplam: 2 snapshot
```

**Kazanç:**
- Disk: 600 MB → 2 MB (%99.7 azalma)
- İşlem süresi: 600x daha hızlı
- Veri kalitesi: Daha anlamlı

---

## 🗄️ DATABASE YAPISI

### violation_events Tablosu:

```sql
CREATE TABLE violation_events (
    event_id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL,
    camera_id TEXT NOT NULL,
    person_id TEXT NOT NULL,
    violation_type TEXT NOT NULL,
    start_time REAL NOT NULL,
    end_time REAL,
    duration_seconds INTEGER,
    snapshot_path TEXT,                    -- İhlal snapshot'ı
    resolution_snapshot_path TEXT,         -- Çözüm snapshot'ı (YENİ!)
    severity TEXT DEFAULT 'warning',
    status TEXT DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Örnek Kayıt:

```json
{
  "event_id": "VIO_CAM_XXX_1234567890",
  "person_id": "PERSON_ABC123",
  "violation_type": "no_helmet",
  "start_time": 1730419200,
  "end_time": 1730419800,
  "duration_seconds": 600,
  "snapshot_path": "violations/COMP_XXX/CAM_XXX/2025-11-01/PERSON_ABC123_no_helmet_1730419200.jpg",
  "resolution_snapshot_path": "violations/COMP_XXX/CAM_XXX/2025-11-01/PERSON_ABC123_no_helmet_resolved_1730419800.jpg",
  "status": "resolved"
}
```

---

## 📁 KLASÖR YAPISI

```
violations/
├── COMP_BE043ECA/
│   ├── CAM_5798AEEC/
│   │   ├── 2025-11-01/
│   │   │   ├── PERSON_ABC123_no_helmet_1730419200.jpg        # İhlal başlangıcı
│   │   │   ├── PERSON_ABC123_no_helmet_resolved_1730419800.jpg  # İhlal bitişi
│   │   │   ├── PERSON_DEF456_no_vest_1730419300.jpg
│   │   │   └── PERSON_DEF456_no_vest_resolved_1730419900.jpg
│   │   └── 2025-11-02/
│   └── CAM_0CE61521/
└── COMP_XXXXXXXX/
```

---

## 🔍 KONTROL VE TEST

### 1. Snapshot'ları Kontrol Et:
```bash
python check_violations.py
```

**Çıktı:**
```
📸 İhlal Snapshot: ✅ VAR
    violations/COMP_XXX/CAM_XXX/2025-11-01/PERSON_ABC123_no_helmet_1730419200.jpg
✅ Çözüm Snapshot: ✅ VAR
    violations/COMP_XXX/CAM_XXX/2025-11-01/PERSON_ABC123_no_helmet_resolved_1730419800.jpg
```

### 2. Canlı İzleme:
```bash
python monitor_violations.py
```

### 3. Snapshot Görüntüleyici:
```bash
python view_snapshots.py
```

---

## 📊 PERFORMANS KARŞILAŞTIRMASI

| Metrik | Önceki Sistem | Yeni Sistem | İyileştirme |
|--------|---------------|-------------|-------------|
| **Snapshot/İhlal** | 300+ | 2 | **150x azalma** |
| **Disk Kullanımı** | 30 MB/ihlal | 200 KB/ihlal | **99.3% azalma** |
| **İşlem Süresi** | 300x çekim | 2x çekim | **150x hızlı** |
| **Veri Kalitesi** | Düşük (tekrar) | Yüksek (anlamlı) | **Çok daha iyi** |
| **Database Boyutu** | Şişkin | Minimal | **Optimize** |

---

## 🎯 KULLANIM ÖRNEKLERİ

### Örnek 1: İhlal ve Çözüm Snapshot'larını Getir

```python
from database_adapter import get_db_adapter

db = get_db_adapter()

# Event'i getir
cursor = db.conn.cursor()
cursor.execute("""
    SELECT 
        event_id,
        violation_type,
        duration_seconds,
        snapshot_path,
        resolution_snapshot_path
    FROM violation_events
    WHERE event_id = ?
""", (event_id,))

event = cursor.fetchone()

print(f"İhlal: {event[1]}")
print(f"Süre: {event[2]} saniye")
print(f"İhlal Snapshot: {event[3]}")
print(f"Çözüm Snapshot: {event[4]}")
```

### Örnek 2: Çözülmüş İhlalleri Listele

```python
cursor.execute("""
    SELECT 
        event_id,
        violation_type,
        duration_seconds,
        snapshot_path,
        resolution_snapshot_path
    FROM violation_events
    WHERE status = 'resolved'
      AND resolution_snapshot_path IS NOT NULL
    ORDER BY end_time DESC
    LIMIT 10
""")

for event in cursor.fetchall():
    print(f"İhlal: {event[1]}, Süre: {event[2]}s")
    print(f"  Başlangıç: {event[3]}")
    print(f"  Bitiş: {event[4]}")
```

---

## 🐛 SORUN GİDERME

### Snapshot çekilmiyor?

**1. Kişi görünür mü kontrol edin:**
```python
# Log'larda şunu arayın:
"⚠️ Kişi frame'de yeterince görünür değil, snapshot atlandı"
```

**2. Bounding box geçerli mi?**
```python
# person_bbox kontrolü:
if not person_bbox or len(person_bbox) != 4:
    print("Geçersiz bbox!")
```

**3. Disk alanı var mı?**
```bash
df -h
```

### Resolution snapshot çekilmiyor?

**1. İhlal bitti mi?**
```sql
SELECT status FROM violation_events WHERE event_id = 'XXX';
-- status = 'resolved' olmalı
```

**2. Log'ları kontrol edin:**
```bash
tail -f logs/smartsafe.log | grep "RESOLUTION SNAPSHOT"
```

---

## 📝 ÖNEMLİ NOTLAR

1. **Cooldown:** Aynı kişi için aynı ihlal 60 saniye içinde tekrar sayılmaz
2. **Görünürlük:** Kişi frame'in en az %5'ini kaplamalı
3. **Resolution Snapshot:** Sadece ihlal bittiğinde çekilir
4. **Disk Temizleme:** 30 günden eski snapshot'lar otomatik silinir
5. **Database:** Her snapshot path database'de saklanır

---

## ✅ AVANTAJLAR

1. **Veri Tasarrufu:** %99+ daha az snapshot
2. **Anlamlı Veri:** Sadece önemli anlar kaydedilir
3. **Hızlı İşlem:** Snapshot çekme overhead'i minimal
4. **Kolay Analiz:** Başlangıç ve bitiş net görülür
5. **Süre Hesaplama:** İki snapshot arasındaki fark = ihlal süresi

---

## 🚀 SONUÇ

**Yeni sistem:**
- ✅ Akıllı snapshot çekimi
- ✅ Kişi görünürlük kontrolü
- ✅ İhlal başlangıcı + bitişi
- ✅ 150x daha az veri
- ✅ Daha anlamlı kayıtlar

**Artık sadece önemli anları kaydediyoruz! 🎉**
