# SmartSafe PPE Detection - Degisiklik Raporu

**Tarih:** 24 Nisan 2026
**Kapsam:** 6 dosya (4 M, 2 YENI), Core detection pipeline + overlay + DB schema duzeltmeleri
**Oturum odagi:** violation_events kaydedememe sorunu, ekranda sadece "person" bbox gorunmesi, phantom bone tespitleri, insan boyunda negatif bbox'lar, Turkce karakter bozuklugu

---

## 1. Database Migration — violation_events Epoch Kolon Tipi

### 1.1 start_time / end_time TIMESTAMP -> DOUBLE PRECISION
**Dosya:** `backend/violation/migrations/4_violation_events_epoch_time_columns.up.sql` (YENI)

**Tespit edilen sorun:**
- Python Core (`core/database/database_adapter.py::add_violation_event`) Unix epoch float gonderiyordu
- Encore backend (`backend/violation/violation.ts → ViolationEvent.start_time: number`) numeric bekliyor
- Init schema TIMESTAMP kullanmis -> PostgreSQL'den su hata:
  ```
  ERROR: column "start_time" is of type timestamp without time zone
         but expression is of type numeric
  ```
- Sonuc: snapshot'lar diske yaziliyor ama `violation_events` tablosu bos kaliyordu -> frontend `/violations` sayfasi bos

**Cozum:**
- Idempotent migration: yalnizca kolonlar hala TIMESTAMP ise ALTER yapar
- Mevcut TIMESTAMP verilerini `EXTRACT(EPOCH FROM ...)` ile koruyarak DOUBLE PRECISION'a cevirir
- `(company_id, start_time DESC)` index reassert edilir

```sql
ALTER TABLE violation_events
  ALTER COLUMN start_time TYPE DOUBLE PRECISION
  USING EXTRACT(EPOCH FROM start_time);
```

### 1.2 Schema Dogrulama Scripti
**Dosya:** `backend/scripts/verify-violation-schema.cjs` (YENI)

- `information_schema.columns`'tan start_time/end_time tipi dogrulanir
- `violation_events` row count ve son kayit tarihi raporlanir
- Migration sonrasi CLI ile hizli smoke-test icin

---

## 2. Overlay Filter — Pose-aware PPE Bypass

### 2.1 pose_based=True Detection'lari Muaf Tutma
**Dosya:** `core/utils/overlay_requirements_filter.py` -> `filter_detections_for_company_required_overlay()`

**Tespit edilen sorun:**
- Pose-aware detector PPE'leri Turkce etiketle ekliyor: `'Bone'`, `'Maske YOK'`, `'Onluk YOK'`, `'Eldiven'`
- Filter `map_sh17_class_to_config_requirement_id(class_name, sector)` ile sh17 canonical id'ye cevirmeye calisiyordu
- Turkce etiketler canonical isimlerle eslesmiyordu -> hepsi None donuyordu -> **overlay'den dusuruluyordu**
- Sonuc: ekrana yalnizca `class_name='person'` kutulari geliyordu; Bone / Maske YOK / Onluk YOK cizilmiyordu

**Cozum:**
- `d.get("pose_based", False) is True` olan detection'lar filtreden **muaf**
- Pose-aware detector zaten iceride `is_required_for_violation(ppe_type)` suzgecini uyguluyor; ikinci bir filtre gerekmez

```python
for d in detections:
    if bool(d.get("pose_based", False)):
        out.append(d)
        continue
    # ... sh17 class_name -> id mapping yolu (eski davranis)
```

---

## 3. SH17 Haircap Filter — Bes Yeni Guard / Rescue

### 3.1 Upper-body Head Proxy (heads=0 persons>0)
**Dosya:** `core/models/sh17_model_manager.py` -> `_filter_food_haircap_candidates()`

- SH17 head bulamadiginda (ama person varken) haircap atilmamasi icin:
- Person bbox'in ust %35'lik bolgesi (kafa/omuz proxy'si) olarak kullanilir
- IoU hesaplamasi hem tum person hem upper-body proxy ile yapilir
- Center-in-box pad: 0.15 -> 0.25 (person bbox kenarlarini daha genis yakalar)

### 3.2 High-confidence Rescue — no-head
**Dosya:** `core/models/sh17_model_manager.py`

Mevcut (onceki oturumlardan): `heads=0 persons>0` + `conf >= 0.50` -> drop yerine pose_aware_ppe_detector'a birakilir.

### 3.3 High-confidence Rescue — partial-head (YENI)
**Dosya:** `core/models/sh17_model_manager.py`

**Tespit:** Terminal loglarinda `heads=2 persons=4 | conf=0.87 iou=0.0000 drop` gibi kayitlar vardi. Head sayisi person sayisindan az olan durumlarda (bazi kisilerin kafasi SH17'de kacirilmis), food model'in dogru bulmus olabilecegi haircap'ler dusuyordu.

**Cozum:**
- `head_boxes` < `person_boxes` VE haircap merkezi bir person'in ust %45'indeyse VE `conf >= 0.55` -> rescue
- Log: `Food haircap kept (partial-head rescue, conf=0.87): bbox=[...]`

```python
elif (
    head_boxes
    and person_boxes
    and len(head_boxes) < len(person_boxes)
    and _cf >= 0.55
):
    # Haircap center person'un ust %45'inde mi?
    for pb in person_boxes:
        if px1 <= hcx <= px2 and py1 <= hcy <= py1 + p_h * 0.45:
            _rescued = True
            break
```

### 3.4 Anatomik Guard — "on-face" (YENI)
**Dosya:** `core/models/sh17_model_manager.py`

**Tespit:** Cafe sahnelerinde food model, yuz bolgesindeki dokulari (saç, beyaz arka plan, ciltl/golge) `haircap 0.91` olarak isaretliyordu. SH17 face kutulari ile overlap yuksek, head ile IoU da pozitif olunca eski filter bunu kabul ediyordu -> ekrana "Bone 0.91" FP olarak duşuyordu.

**Cozum:** Haircap center'i bir face bbox ICINDEYSE -> drop (bone yuzun USTUNDE durur, yuzde degil)

```python
face_boxes = [d['bbox'] for d in sh17_detections if d['class_name'] == 'face']
for fb in face_boxes:
    if fx1 <= hb_cx <= fx2 and fy1 <= hb_cy <= fy2:
        haircap_on_face = True
        break
if haircap_on_face:
    dropped += 1
    continue  # FP
```

### 3.5 Anatomik Guard — "not-head-top" (YENI)
**Dosya:** `core/models/sh17_model_manager.py`

**Cozum:** Head varsa, haircap center'inin head bbox'in ust %60'inda olmasi zorunlu. Degilse drop:
- y araligi: `head.y1 - 0.30*h .. head.y1 + 0.60*h`
- x toleransi: `head.x1 - 0.25*w .. head.x2 + 0.25*w`

```python
y_top_limit = hy1 + head_h * 0.60
y_above_limit = hy1 - head_h * 0.30
x_left_limit = hx1 - head_w * 0.25
x_right_limit = hx2 + head_w * 0.25
if (y_above_limit <= hb_cy <= y_top_limit
        and x_left_limit <= hb_cx <= x_right_limit):
    head_top_ok = True
# ...
if head_boxes and not head_top_ok:
    continue  # gercek bone kafanin alt yarisinda durmaz
```

### 3.6 Log Mesajlari
Yeni DEBUG satirlari:
```
Food haircap dropped (on-face): conf=0.91 bbox=[...]
Food haircap dropped (not-head-top): conf=0.87 bbox=[...]
Food haircap kept (partial-head rescue, conf=0.87): bbox=[...]
```

INFO ozet satirinda `no_overlap` listesine `face_overlap` ve `not_head_top` sebepleri eklendi.

---

## 4. Pose-aware Detector — Bbox Boyutlandirma Duzeltmeleri

### 4.1 Pozitif PPE Icin Anatomik Clamp
**Dosya:** `core/detection/pose_aware_ppe_detector.py` -> `_calculate_pose_aware_compliance()`

**Tespit:** Food model bazen `haircap / face_mask / apron` bbox'larini person boyunda donduruyor. Sonuc: ekranda "Bone 0.95" etiketi tum insan boyunda ciziliyordu.

**Cozum:** Negatif (NO-*) tarafta zaten kullanilan anatomik kirpmayi pozitifte de uygula. Uc kosuldan biri dogruysa `anatomical` bbox'a snap:

```python
too_big = (bw_f * bh_f) > (aw_f * ah_f) * 2.5           # item 2.5x buyuk
center_out = not (ax1 <= bcx <= ax2 and ay1 <= bcy <= ay2)  # center anatomik disinda
too_tall_haircap = (ppe_type == 'haircap'
                    and bh_f > p_h * 0.30)               # haircap person'un %30'u+
if too_big or center_out or too_tall_haircap:
    bbox_to_use = anatomical
```

Anatomik bolgeler (negatif ile tutarli):
- `haircap`: head'in ust %45'i
- `face_mask`: head'in alt %55'i
- `safety_suit`: torso omuzdan bele, dikey +%20 pay
- `gloves`: hands +%10 dikey band

### 4.2 full_body Fallback Kaldirildi, Anatomik Proxy Eklendi
**Dosya:** `core/detection/pose_aware_ppe_detector.py`

**Tespit:** Pose estimator head keypoint'ini kacirinca
```python
region_bbox = regions.get(region_name) or regions.get('full_body')
```
devreye giriyor, haircap icin `y1 + 0.45 * h` full_body'nin %45'i = insanin UST YARISI kadar cikiyordu. "Bone YOK" bbox'i anlik devasa cizilip sonraki frame'de duzeliyordu.

**Cozum:** full_body fallback'i kaldir, region yoksa person bbox'tan anatomik proxy hesapla:

| Region | Proxy |
|--------|-------|
| head | person'un ust %20'si |
| torso | person'un %20-60'i |
| hands | person'un %35-70'i |
| feet | person'un alt %20'si |

```python
region_bbox = regions.get(region_name)
if region_bbox is None and p_bbox and len(p_bbox) == 4:
    _px1, _py1, _px2, _py2 = map(float, p_bbox)
    _ph = _py2 - _py1
    if region_name == 'head':
        region_bbox = [_px1, _py1, _px2, _py1 + _ph * 0.20]
    elif region_name == 'torso':
        region_bbox = [_px1, _py1 + _ph * 0.20, _px2, _py1 + _ph * 0.60]
    # ...
```

En kotu durumda bbox person'in ust %20'sinde kalir, insan boyunda cizilmez.

### 4.3 EMA Reset — Area Ratio > 3x
**Dosya:** `core/detection/pose_aware_ppe_detector.py` -> `_ema_bbox()`

**Tespit:** Eski EMA reset kurali yalnizca `IoU < 0.10` idi. Bir frame'de kazara full_body boyunda bbox kaydedildiyse, sonraki frame'de gercek head gelince IoU hala > 0.10 oldugu icin EMA eski buyuk bbox'i birkac frame boyunca "surukluyordu" -> "anlik buyuk bbox sonra duzeliyor" pattern'i.

**Cozum:** Alan orani 3x'ten fazla degistiyse de reset et:

```python
prev_area = (prev_bbox[2]-prev_bbox[0]) * (prev_bbox[3]-prev_bbox[1])
cur_area = (cur[2]-cur[0]) * (cur[3]-cur[1])
area_ratio = max(prev_area, cur_area) / max(min(prev_area, cur_area), 1.0)
if self._bbox_iou(prev_bbox, cur) < 0.10 or area_ratio > 3.0:
    self._bbox_ema[key] = (cur, now)
    return cur  # reset, smoothing yapma
```

Etki: Hatali frame sonrasi EMA anında dogru boyuta snap eder, kullanici "anlik buyuk bbox" gormeyi birakir.

---

## 5. Visual Overlay — Turkce Karakter Destegi

### 5.1 PIL/Pillow ROI-bazli Unicode Render
**Dosya:** `core/detection/utils/visual_overlay.py`

**Tespit:** `cv2.putText` Hershey fontlari yalnizca Latin1 destekler. Turkce `O / o / U / u / C / c / S / s / I / i / G / g` karakterleri `?` olarak render ediliyor, ekranda `??nl??k YOK` gibi goruntuler olusuyordu.

**Cozum:** Pillow TrueType fontu ile ROI-bazli render:
- Frame'in tamami dondurulmez, yalnizca label pill alani PIL -> cv2 konvertisyonu gorur (performans)
- Font cache (her frame'de yeniden yukleme yok)
- Font candidates:
  - Windows: `Calibri`, `Arial`, `Segoe UI`
  - Linux: `DejaVuSans`, `LiberationSans`
  - macOS: `Helvetica`
- Pillow yoksa veya font bulunamazsa **ASCII fallback**: `O -> O`, `o -> o`, `U -> U`, `C -> C`, `S -> S`, `I -> I`, `G -> G`

### 5.2 Yeni Public API — `_draw_text_unicode()`
**Dosya:** `core/detection/utils/visual_overlay.py`

```python
def _draw_text_unicode(
    img, text, x, y_top, color_bgr, px_size
) -> None:
    """UTF-8 metni (x, y_top) top-left koseden cizer.
    PIL varsa TrueType ile, yoksa ASCII fallback + cv2.putText."""
```

### 5.3 _draw_label_pill ve draw_hud_bar Guncellendi
**Dosya:** `core/detection/utils/visual_overlay.py`

- `_draw_label_pill`: pill boyutlandirmasi icin cv2 metrikleri ASCII-normalize uzerinden hesaplanir (hiz), gercek cizim PIL ile
- `draw_hud_bar`: `cv2.putText` -> `_draw_text_unicode` (ileride Turkce sector adlari icin)
- `_TR_ASCII_MAP` translate tablosu `str.maketrans` ile (performant)

### 5.4 Font Cache
**Dosya:** `core/detection/utils/visual_overlay.py`

```python
_FONT_CACHE: dict = {}
def _get_pil_font(px_size: int):
    key = int(max(8, px_size))
    if key in _FONT_CACHE:
        return _FONT_CACHE[key]
    # candidates uzerinde ara, cache'le, don
```

Her farkli `px_size` icin bir kere yuklenir, sonraki cagrilarda bellekten gelir.

---

## 6. Degisiklik Ozeti (Dosya Bazinda)

| Dosya | Tip | Ozet |
|-------|-----|------|
| `backend/violation/migrations/4_violation_events_epoch_time_columns.up.sql` | YENI | TIMESTAMP -> DOUBLE PRECISION |
| `backend/violation/migrations/5_violation_events_add_debug_meta.up.sql` | YENI | violation_events.debug_meta (JSONB) |
| `backend/scripts/verify-violation-schema.cjs` | YENI | Schema smoke-test scripti |
| `core/utils/overlay_requirements_filter.py` | M | pose_based=True bypass |
| `core/models/sh17_model_manager.py` | M | Upper-body proxy, partial-head rescue, on-face guard, not-head-top guard, face_boxes toplama |
| `core/detection/pose_aware_ppe_detector.py` | M | Pozitif anatomik clamp, full_body fallback kaldirma, anatomik proxy (head/torso/hands/feet), EMA area-ratio reset, pose-based PPE'ye parent_track_id + parent_bbox |
| `core/detection/pose_aware_ppe_detector.py` | M | Missing (NO-*) EMA clamp: parent person bbox'a kırp + oversize guard (devasa "YOK" kutularını azaltır) |
| `core/detection/utils/visual_overlay.py` | M | Pillow TrueType ROI render, font cache, ASCII fallback, _TR_ASCII_MAP, _draw_text_unicode, label_pill + hud_bar entegrasyonu |
| `core/utils/detection_roi.py` | M | Pose-based PPE'ler icin parent-ROI mirasi (parent_track_id / parent_bbox uzerinden) |
| `core/configs/constants.py` | M | `PROXY_STREAM_CONNECT_TIMEOUT_S=20` eklendi |
| `core/utils/temporal_ppe_gating.py` | YENI | PPE bazli temporal gating (N-of-M + histerezis) |
| `core/app.py` | M | Overlay toggle: default sadece person bbox + warning label, `OVERLAY_SHOW_PPE_BOXES=1` ile detay PPE kutuları |
| `core/app.py` | M | violation_events'e debug_meta (temporal gating/ROI/decision gate) yaz |
| `core/app.py` | M | debug_meta derinlestirildi: event person track_id esleme + anatomical_regions + pose-based PPE listesi (mask VAR/YOK sayimi) |
| `core/utils/violation_debug_meta.py` | YENI | debug_meta builder helper (app.py'yi sisirmez) |
| `core/utils/temporal_ppe_gating.py` | M | temporal gating stats: window/miss_count/%missing/confirmed debug_meta'ya |
| `core/app.py` | M | ViolationTracker'a kisi-bazli ihlal gonder: temporal_gating confirmed_missing olmayan track'lerde event uretme |
| `core/database/database_adapter.py` | M | violation_events insert: debug_meta JSONB yaz |
| `backend/violation/violation.ts` | M | ViolationEvent response: debug_meta alanı |

---

## 8. ROI-Disi Bbox Gizleme (Parent-ROI Mirasi)

### 8.1 Sorun

ROI polygonu ile calisan `filter_detections_by_roi`, her tespite kendi `bbox`'inin alt-orta noktasinin ROI
icinde olup olmadigini kontrol ediyordu. Ancak pose-aware PPE kutulari (ornegin "Maske YOK" = yuz bolgesi
bbox'i) icin alt-orta nokta gogusun ortasina yakindir ve kisi ROI icinde durmasina ragmen bu PPE bbox'i
ROI cizgisinin disina dusup elenebiliyor ya da tam tersine ROI disinda duran bir kisinin PPE bbox'i
("Bone 0.90") ROI icine denk dustugu icin cizilebiliyordu.

Gorsel etki: turnike/mutfak kamerasinda ROI disinda kalan kapi onundeki insanlar icin de "Bone YOK",
"Onluk YOK", "Maske YOK" kutulari ciziliyordu.

### 8.2 Cozum

Pose-aware detector urettigi her pose-based PPE tespitine artik parent person bilgisini ekliyor:

```python
all_detections.append({
    'bbox': bbox_to_use,
    'class_name': cfg['pos_label'],
    ...
    'pose_based': True,
    'parent_track_id': tid,
    'parent_bbox': list(p_bbox) if p_bbox and len(p_bbox) == 4 else None,
})
```

`filter_detections_by_roi` once tum person tespitlerini ROI'ye gore degerlendirip
`person_inside_by_tid` / `person_inside_by_bbox` haritalarini olusturuyor; ardindan pose-based PPE
tespitleri icin parent'in ROI durumunu miras aliyor:

```python
if is_pose_based and not _is_person_detection(item):
    inside = _parent_inside(item)
    if inside is None:
        inside = _eval_inside(bbox)
else:
    inside = _eval_inside(bbox)
```

Boylece:
- ROI icindeki kisiye ait `Maske YOK` / `Bone YOK` / `Onluk YOK` kutulari her zaman cizilir.
- ROI disindaki kisinin PPE kutulari (pose-based) bosluk birakmadan elenir.
- SH17'den gelen ham sinif tespitleri (pose_based=False) eski bbox alt-orta kurali ile calisir.

### 8.3 Dosyalar

- `core/detection/pose_aware_ppe_detector.py` — pozitif + negatif pose-based PPE append'lerine
  `parent_track_id` ve `parent_bbox` eklendi.
- `core/utils/detection_roi.py` — `filter_detections_by_roi` person haritasi + `_parent_inside()`
  helper'i ile yeniden yazildi; ROI poligonunun aktif oldugu durumda pose-based PPE'ler parent'in
  ROI durumunu miras aliyor.

---

## 7. Kullanici Tarafinda Gozlemlenecek Etki

1. **`/violations` sayfasi artik bos degil** — migration sonrasi yeni ihlaller DB'ye yaziliyor, frontend'de goruluyor
2. **Ekranda sadece "person" kutulari yok artik** — pose-aware PPE kutulari (Bone, Maske YOK, Onluk YOK, Eldiven YOK...) ciziliyor
3. **Cafe ortaminda "Bone 0.91" FP'leri azaldi** — on-face / not-head-top guard'lari phantom bone'lari eliyor
4. **"Bone" etiketi artik kafada ciziliyor** — insan boyunda degil, anatomik clamp ile ust %45 head bolgesinde
5. **"Bone YOK" / "Onluk YOK" devasa bbox'lari kalkti** — full_body fallback yok, en kotu durumda anatomik proxy + EMA hizli reset
6. **Turkce karakterler dogru goruluyor** — `Onluk YOK`, `Maske YOK`, `Bone YOK`, `Sac filesi eksik` vb. PIL ile render ediliyor
7. **Yuksek conf haircap drop'lari azaldi** — partial-head rescue, SH17'nin kafayi kacirdigi kisiler icin haircap'i koruyor
