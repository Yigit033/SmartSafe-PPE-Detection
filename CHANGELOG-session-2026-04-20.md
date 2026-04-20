# SmartSafe PPE Detection - Degisiklik Raporu

**Tarih:** 20 Nisan 2026
**Kapsam:** 12 dosya, +731 / -220 satir

---

## 1. PPE Detection Pipeline Iyilestirmeleri

### 1.1 required_ppe Normalizasyonu
**Dosya:** `core/detection/pose_aware_ppe_detector.py`

- `_normalize_required_ppe()` fonksiyonu eklendi
- Company/DB'den gelen required_ppe artik JSON string, dict, set, tuple, comma-separated string formatlarinin hepsini kabul ediyor
- Alias mapping: `hairnet` → `haircap`, `apron` → `safety_suit`, `vest` → `safety_vest` vb.
- Duplicate temizleme ve None koruma

### 1.2 PPE Etiketi Turkcelestirme
**Dosya:** `core/detection/pose_aware_ppe_detector.py`

PPE_CONFIG icindeki tum `pos_label` ve `neg_label` degerleri Turkce'ye cevrildi:

| PPE Type | Eski | Yeni |
|----------|------|------|
| helmet | Helmet / NO-Helmet | Baret / Baret YOK |
| safety_vest | Safety Vest / NO-Vest | Yelek / Yelek YOK |
| face_mask | Face Mask / NO-Mask | Maske / Maske YOK |
| safety_suit | Safety Suit / NO-Suit | Onluk / Onluk YOK |
| haircap | Haircap / NO-Haircap | Bone / Bone YOK |
| safety_shoes | Safety Shoes / NO-Shoes | Ayakkabi / Ayakkabi YOK |
| gloves | Gloves / NO-Gloves | Eldiven / Eldiven YOK |
| safety_glasses | Safety Glasses / NO-Glasses | Gozluk / Gozluk YOK |

### 1.3 Haircap model_classes Genisletildi
**Dosya:** `core/detection/pose_aware_ppe_detector.py`

- `haircap` icin: `'head'`, `'hairnet'`, `'hair_net'` eklendi
- `safety_suit` icin: `'suit'`, `'tulum'`, `'onluk'` eklendi

---

## 2. False Positive Engelleme (Person Validation Gate)

### 2.1 Pose Detector Tarafinda
**Dosya:** `core/detection/pose_aware_ppe_detector.py` → `_extract_pose_data()`

Yer yazilari ("Bariyer", "Sariyer" vb.), araba tekerlekleri ve rastgele nesnelerin "person" olarak algilanmasini engellemek icin 4 katmanli filtre:

| Filtre | Env Variable | Default | Aciklama |
|--------|-------------|---------|----------|
| Min confidence | `MIN_PERSON_CONF` | 0.40 | %40 altindaki person reddedilir |
| Min yukseklik | `MIN_PERSON_H_RATIO` | 0.08 | Frame yuksekliginin %8'inden kucuk reddedilir |
| Max aspect ratio | `MAX_PERSON_ASPECT` | 2.5 | w/h > 2.5 olan yatik bbox reddedilir |
| Min keypoint sayisi | `MIN_PERSON_KEYPOINTS` | 3 | 3'ten az gecerli keypoint varsa reddedilir |

Keypoint kontrolu en etkili filtre: gercek bir insan en az 3 keypoint'e (bas, omuz, kalca) sahiptir, bir harf veya nesne 0-1 keypoint'e sahiptir.

### 2.2 SH17 Detector Tarafinda
**Dosya:** `core/models/sh17_model_manager.py` → `_detect_with_sh17()`

Person validation gate eklendi:
- `MIN_PERSON_CONF` (0.40), `MAX_PERSON_ASPECT` (2.5) kontrolleri
- `MIN_PERSON_AREA_RATIO` (0.003): Frame alaninin %0.3'unden kucuk person bbox reddedilir

### 2.3 Overlay Cizim Tarafinda (Son Savunma)
**Dosya:** `core/app.py` → `draw_saas_overlay()`

Detection pipeline'dan bir sekilde gecse bile overlay'da gosterilmez:
- `MIN_PERSON_CONF` kontrolu
- Keypoint sayisi kontrolu (`MIN_PERSON_KEYPOINTS`)
- Aspect ratio kontrolu (w/h > 2.5)

---

## 3. Haircap Matching Iyilestirmeleri

### 3.1 IoU Esikleri Sikistirildi
**Dosya:** `core/detection/pose_aware_ppe_detector.py` → `_find_best_ppe_match()`

| Parametre | Eski | Yeni |
|-----------|------|------|
| `iou_threshold['haircap']` | 0.03 | 0.05 |
| `person_iou_threshold['haircap']` | 0.02 | 0.10 |
| Fallback 1 min_person_iou | 0.01 | 0.08 |
| Fallback 3 min_piou (haircap/helmet) | 0.00 | 0.08 |
| Fallback 4 proximity ratio | 0.80 | 0.50 |

### 3.2 Proximity Fallback (Fallback 4) Eklendi
**Dosya:** `core/detection/pose_aware_ppe_detector.py` → `_find_best_ppe_match()`

Tum IoU'lar 0 oldugunda, PPE merkezinin person merkezine uzakligi person diagonal'inin %50'sinden azsa kabul edilir. Ozellikle pose model'in bbox'u yanlis hesapladigi durumlarda devreye girer.

### 3.3 Exclusive PPE Assignment
**Dosya:** `core/detection/pose_aware_ppe_detector.py` → `_enhance_persons_with_ppe()`

- `_assigned_ppe_ids` mekanizmasi: bir PPE nesnesi bir kisiye atandiktan sonra diger kisiler icin artik pool'dan cikarilir
- Ayni bone'nin birden fazla kisiye "match" olmasi engellendi

### 3.4 Haircap Filter (SH17) Duzeltmesi
**Dosya:** `core/models/sh17_model_manager.py` → `_filter_food_haircap_candidates()`

- `heads=0 persons=0` durumunda food model'in buldugu gecerli haircap'ler artik korunuyor (guard'lardan gecmis olanlar drop edilmiyor)
- Nihai association pose_aware_ppe_detector'a birakildi

---

## 5. Violation Snapshot Servisi

### 5.1 Snapshot Kayit Yolu Duzeltmesi
**Dosya:** `core/detection/snapshot_manager.py`

- Eski default: `/app/storage/violations` (sadece Docker'da gecerli)
- Yeni: `SNAPSHOT_BASE_PATH` env var veya proje-relativ `smart-safe/storage/violations/`
- Local development'ta snapshot'lar artik proje icinde kaydediliyor

### 5.2 Filename Sanitization
**Dosya:** `core/detection/snapshot_manager.py`

- `violation_type` icindeki `/`, `\`, `,` karakterleri `_` ile degistiriliyor
- `relative_path` her zaman forward slash kullanir (Windows uyumlulugu)

### 5.3 Flask Route Duzeltmesi
**Dosya:** `core/app.py`

- Eski: `/static/violations/<path>` + `send_from_directory('violations', ...)` (yanlis yol)
- Yeni: `/storage/violations/<path>` + `send_from_directory(snapshot_manager.base_path, ...)`
- Legacy compat route korundu

### 5.4 Frontend Proxy
**Dosya:** `frontend/next.config.ts`

- Next.js `rewrites` eklendi: `/storage/violations/:path*` → Core API'ye proxy
- Frontend'ten gelen snapshot istekleri otomatik olarak backend'e yonlendiriliyor

### 5.5 Frontend URL Normalizasyonu
**Dosya:** `frontend/app/violations/page.tsx`

- `getSnapshotUrl()`: Windows backslash'lari temizleniyor, `storage/violations/` prefix'i strip ediliyor

---

## 6. Log Iyilestirmeleri

### 6.1 Log Throttling & Grouping
**Dosya:** `core/detection/pose_aware_ppe_detector.py`

- `_throttled()` ve `_bump_group()` helper'lari eklendi
- `PPE_LOG_SUMMARY_EVERY_S` (default 2s): Throttled summary log'lar
- `PPE_LOG_GROUP_FLUSH_EVERY_S` (default 10s): Gruplanmis log flush

### 6.2 Haircap Log Konsolidasyonu
**Dosya:** `core/detection/pose_aware_ppe_detector.py`

- Eski: Her kisi icin ayri `Person X haircap candidate` log satiri
- Yeni: Tek satir: `Haircap match: 4 candidates | P0[h=0.07 p=0.08 OK] P1[h=0.24 p=0.57 OK]`

### 6.3 SH17 Haircap Filter Log Konsolidasyonu
**Dosya:** `core/models/sh17_model_manager.py`

- Eski: Her drop icin ayri log satiri
- Yeni: Tek ozet satir: `Haircap filter: dropped=5 kept=13 heads=2 persons=3 | no_overlap(5): [...]`

### 6.4 Violation Isimleri Turkce
**Dosya:** `core/app.py`

- SH17 compliance fallback yolunda `Missing: X` yerine `PPE_CONFIG['violation_tr']` kullaniliyor
- Ornek: `Missing: hairnet` → `Sac filesi/Bone eksik`

---

## 7. ByteTrack Uyumluluk
**Dosya:** `core/detection/pose_aware_ppe_detector.py`

- `sv.ByteTrack()` init try/except ile sarmalandi
- Yeni supervision surumlerinde `track_thresh` desteklenmezse default constructor kullaniliyor
- `bbox_ema_ttl_s`: 8.0 → 1.5 (stale track'ler daha hizli temizleniyor)

---

## 8. Database Migration
**Dosya:** `backend/violation/migrations/3_add_resolution_snapshot_and_person_violations.up.sql` (YENi)

```sql
ALTER TABLE violation_events ADD COLUMN IF NOT EXISTS resolution_snapshot_path TEXT;
CREATE TABLE IF NOT EXISTS person_violations (...);
```

- `resolution_snapshot_path`: Violation cozulme snapshot'i
- `person_violations`: Aylik kisi bazli ihlal istatistikleri

---

## 9. Frontend Iyilestirmeleri

### 9.1 DVR Filter
**Dosya:** `frontend/app/cameras/page.tsx`

- Kamera listesinde DVR bazli filtreleme butonu eklendi
- Birden fazla DVR varsa "TUMU" + her DVR icin ayri buton

### 9.2 Stream Yonetimi
**Dosyalar:** `frontend/components/camera/MjpegCanvas.tsx`, `frontend/components/layout/Sidebar.tsx`, `frontend/app/cameras/page.tsx`

- Sayfa degisikliginde MJPEG stream'leri aninda kapatiliyor
- 150ms gecikme: tarayiciya TCP baglantisini serbest birakma firsati
- `isMountedRef`: Ilk render'da stream'in kesilmesini engelliyor

### 9.3 Kamera Karti Duzeni
**Dosya:** `frontend/app/cameras/page.tsx`

- Location alani `"BELIRTILMEMIS"` fallback'i eklendi
- Kart layout iyilestirildi

---

## Etkilenen Dosyalar Ozeti

| Dosya | Degisiklik |
|-------|-----------|
| `core/detection/pose_aware_ppe_detector.py` | +252 / -131 |
| `core/detection/utils/visual_overlay.py` | +104 / -55 |
| `core/app.py` | +79 / -36 |
| `core/models/sh17_model_manager.py` | +51 / -22 |
| `core/utils/overlay_requirements_filter.py` | +46 / -22 |
| `core/detection/snapshot_manager.py` | +13 / -7 |
| `frontend/app/cameras/page.tsx` | +43 / -12 |
| `frontend/app/violations/page.tsx` | +5 / -3 |
| `frontend/components/camera/MjpegCanvas.tsx` | +14 / -2 |
| `frontend/components/layout/Sidebar.tsx` | +3 / -3 |
| `frontend/next.config.ts` | +10 / -0 |
| `backend/violation/migrations/3_*.up.sql` | +32 (yeni) |

---

## Environment Variables (Tumu Opsiyonel)

| Variable | Default | Aciklama |
|----------|---------|----------|
| `MIN_PERSON_CONF` | 0.40 | Min person confidence |
| `MIN_PERSON_H_RATIO` | 0.08 | Min person height / frame height |
| `MAX_PERSON_ASPECT` | 2.5 | Max person w/h orani |
| `MIN_PERSON_KEYPOINTS` | 3 | Min gecerli keypoint sayisi |
| `MIN_PERSON_AREA_RATIO` | 0.003 | Min person alan / frame alan orani |
| `PPE_LOG_SUMMARY_EVERY_S` | 2.0 | Log throttle suresi (saniye) |
| `PPE_LOG_GROUP_FLUSH_EVERY_S` | 10.0 | Log grup flush suresi (saniye) |
| `SNAPSHOT_BASE_PATH` | (proje/storage/violations) | Snapshot kayit dizini |
| `OSD_PERSON_FILTER` | 1 | OSD false positive filtresi |
