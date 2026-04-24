## PPE + BBox Sistem Raporu (2026-04-15)

Bu raporun tarihi: **2026-04-15** (repo koduna göre çıkarılmış snapshot).

---

## Amaç ve kapsam

Bu doküman, PPE tespit sistemimizin **bbox (bounding box) kalitesini**, **algoritmik/mimari yapısını**, ve **production güvenilirliğini** kodun “tek kaynak gerçekliği” (source of truth) olan dosyalar üzerinden raporlar. Amaç; ileride yeni model ekleme, mevcut modeli iyileştirme veya bbox/association sistemini refactor etme kararlarında “neredeyiz, neden böyleyiz, riskler neler” sorularını net cevaplamaktır.

Kapsam:
- **Core inference pipeline**: `core/app.py`
- **Pose-aware association**: `core/detection/pose_aware_ppe_detector.py`
- **Model orchestration (SH17 + Food PPE)**: `core/models/sh17_model_manager.py`
- **ROI sistemi**: `core/utils/detection_roi.py`
- **BBox observability**: `core/utils/bbox_observability.py`
- **Runtime decision engine (DECISION_GATE)**: `core/utils/detection_decision.py`

Bu rapor “docs/*.md” vb. eski dokümanlara dayanmaz; doğrudan çalışan koda dayanır.

---

## Sistem özeti (yüksek seviye mimari)

### Core çalışma döngüsü (SaaS worker)
Sistem, kamera başına bir worker döngüsü ile çalışır. Döngü içinde:
- Frame alınır (buffer üzerinden),
- Belirli aralıklarla inference yapılır (`frame_skip`),
- Pose-aware varsa öncelik onda; yoksa SH17 ile PPE çıkarılır,
- Kişi bbox’ları için opsiyonel tracking id atanır,
- ROI filtresi uygulanır,
- BBox observability metrikleri periyodik loglanır,
- Decision engine “güvenilirlik” state’i üretir (ACCEPT/UNCERTAIN/REJECT),
- Sadece **ACCEPT** ise violation event üretilir; aksi halde suppress edilir.

Kaynak: `core/app.py` (özellikle `saas_detection_worker` içi akış).

### Model katmanı
Food sektöründe iki kaynak birleşir:
- **SH17** (genel PPE + person/head vb.),
- **Food PPE local model** (özellikle haircap/glasses/mask vb. fine-grained).

Food model ile ilgili özel durumlar:
- Haircap için rescue pass (daha düşük conf) var.
- Haircap bulunamazsa SH17 head bbox’larından crop yapıp “head-crop inference” denenir.
- Head-crop da yoksa renk analizi fallback var.

Kaynak: `core/models/sh17_model_manager.py`

### Pose-aware association (bbox → PPE eşleştirme)
Pose-aware katman:
- YOLOv8 pose ile person + keypoints çıkarır,
- Keypoints’ten “anatomical regions” (head/torso/hands/feet…) üretir,
- PPE bbox’larını bu region’lara IoU + fallbacks ile bağlar,
- Compliance hesaplar.

Kaynak: `core/detection/pose_aware_ppe_detector.py`

---

## BBox coordinate pipeline: “tek koordinat uzayı” durumu

Mevcut hedef uzay: **frame pixel space** (orijinal frame’in px koordinatları).

Bug’a açık yerler:
- Food model’in bazı durumlarda “devasa / alakasız haircap bbox” üretebilmesi (model kaynaklı veya postprocess kaynaklı). Bu bbox’lar frame px uzayında olsa bile semantik olarak yanlış olur ve association’ı bozar.

Bu bug için uyguladığımız kalıcı guard/fix:
- `FoodPPE-Local` haircap bbox’ları; SH17 head/person bbox’ları ile geometrik ilişki göstermiyorsa **drop** edilir.
- Ayrıca “imkânsız haircap” için coverage/aspect guards uygulanır.
- Drop olduysa head-crop rescue gating’i yine çalışır (rescue kilitlenmez).

Kaynak: `core/models/sh17_model_manager.py` (`_filter_food_haircap_candidates` ve `detect_ppe` gating).

---

## ROI (Analiz bölgesi) kalitesi

### ROI temsil ve dönüşüm
- ROI DB’den 0–1 normalize poligon şeklinde gelir.
- Frame shape’e göre px’e çevrilir.
- Varsayılan kural: **bbox alt-orta noktası polygon içinde mi** (hard filter).

Ek olarak skor bazlı yardımcılar var:
- `intersection_ratio_bbox_roi`: bbox ∩ ROI oranı
- `roi_score_for_bbox`: (bottom-center inside) + (intersection_ratio) hibrit skor

Kaynak: `core/utils/detection_roi.py`

### Production değerlendirmesi
- **Artı**: ROI filtre “cheap & robust” (alt-orta heuristiği) + debug meta var.
- **Eksi/Risk**: Filtre kuralı tek başına kenar durumlarda flip üretebilir (küçük jitter → inside/outside flip). Bu, decision engine ve observability metrikleriyle yönetiliyor (roi_flip_rate vb.).

---

## Tracking ve bbox stabilitesi

### Track id ataması
Core worker loop’ta person bbox’larına track_id atanması opsiyonel olarak çalışıyor:
- `assign_track_ids_to_person_detections(camera_key, persons_now)`

Kaynak: `core/app.py` (person-centric tracking bölümü).

### Stabilite metrikleri (ölçülebilirlik)
`bbox_observability` modülü, env ile açıldığında periyodik özet basar:
- trackless_frame_ratio
- avg_track_lifetime_s
- bbox_jitter_px_avg/p95
- invalid_bbox_ratio
- clipped_bbox_ratio
- (opsiyonel) roi_flip_rate

Kaynak: `core/utils/bbox_observability.py`

### Production değerlendirmesi
- **Artı**: Bbox kalitesi artık “hissiyat” değil, metrikle ölçülebilir.
- **Eksi/Risk**: Tracking coverage trackless_frame_ratio yüksekse overlay ve decision güveni düşer; bu durumda decision engine violation suppress edebilir (tasarım doğru).

---

## Decision Engine (DECISION_GATE): güvenilirlik mimarisi

### Amaç
Decision engine, frame/person bazında bbox güvenilirliğini ölçüp runtime davranışı belirler:
- **ACCEPT**: violation event üretilebilir
- **UNCERTAIN/REJECT**: violation event **suppress** edilir (false alert önleme)

Kaynak: `core/utils/detection_decision.py` ve worker entegrasyonu `core/app.py`.

### Girdi sinyalleri ve füzyon
`decide_frame()` her person için şu sinyalleri birleştirir:
- **ROI score** (varsa): `roi_score_for_bbox` ile \(0..1\)
- **track_conf**: track ömrü + jitter’dan üretilir; yeni track’ler için warmup floor uygulanır
- **stability_score**: IoU sürekliliği (son bbox ile)
- **model_conf**: person detection confidence (yoksa 0.9 varsayılıyor)

Final confidence:
\[
final\_conf = model\_conf \times track\_conf \times roi\_score \times stability\_score
\]

Eşikler env ile ayarlanır:
- `ROI_REJECT_T`, `ROI_UNCERTAIN_T`
- `FINAL_CONF_REJECT_T`, `FINAL_CONF_UNCERTAIN_T`
- track kalite: `TRACK_CONF_*`

### Production değerlendirmesi
- **Çok güçlü artı**: Sistem artık “güvenemediği” durumda ihlal spam’lemiyor.
- **Risk**: Yanlış threshold seçimi “aşırı suppress” veya “aşırı accept” yaratır; bu yüzden `bbox_observability` metrikleriyle birlikte ayarlanmalı.

---

## PPE association kalitesi (pose-aware)

### Anatomical region üretimi
Pose modelden keypoint’ler çıkarılır ve `anatomical_regions` üretilir. PPE türü baş/torso/hands/shoes gibi region’lara map edilir.

Kaynak: `core/detection/pose_aware_ppe_detector.py`

### `_find_best_ppe_match` kural seti
Eşleştirme, region IoU + person IoU gating ile çalışır:
- Her PPE türü için `iou_threshold` (region IoU) ve `person_iou_threshold` (person overlap) var.
- “Region IoU yoksa” person IoU ile en iyi aday promot edilir.
- Birkaç fallback: helmet/haircap için üst gövde fraksiyonu, center containment, person bbox containment.

Kaynak: `core/detection/pose_aware_ppe_detector.py` (`_find_best_ppe_match`)

### Haircap özel durumu ve bug sınıfı
Saha gözlemi ile kapanan teşhis:
- `FoodPPE-Local` bazen haircap için **frame’in büyük kısmını kaplayan** alakasız bbox üretiyordu.
- Bu bbox head/person ile IoU=0 olduğundan eşleşme bozuluyor, compliance 0 görünüyor ve decision gate bazen suppress ediyordu.

Kalıcı önlem:
- Food haircap filter + guard + rescue gating (model manager tarafında).

---

## Head region tightness: haircap IoU hassasiyeti

Haircap eşleştirmesi `head` region’u çok dar çıktığında IoU_head sıfıra düşebilir. Bu nedenle:
- Haircap için head region, association öncesi **az miktar genişletilir** (frame’e clip).

Kaynak: `core/detection/pose_aware_ppe_detector.py` (haircap için region_bbox expansion).

Production değerlendirmesi:
- **Artı**: Region IoU “mikro kaymalar” yüzünden 0 olmaktan çıkar; daha stabil eşleşme.
- **Risk**: Aşırı expansion yanlış pozitif eşleşme üretir; bu yüzden sadece haircap ve kontrollü pad ile uygulanır.

---

## Mevcut sistemin seviye değerlendirmesi (2026-04 snapshot)

### Mimari kalite (8/10)
- **Güçlü**: Çok katmanlı güvenilirlik: tracking/ROI/observability/decision gate.
- **Güçlü**: Food sektörüne özel haircap rescue stratejisi (crop + renk analizi).
- **Güçlü**: Event-based violation tracker + snapshot kayıt mekanizması (spam’i azaltır).
- **Zayıf**: Model çıktılarında (özellikle FoodPPE haircap) zaman zaman “garbage bbox” üretimi; fakat artık filtreleniyor.

### BBox stabilitesi (6.5/10 → izlenebilir)
- Tracking coverage varsa iyi; yoksa decision engine false alert’i suppress ediyor.
- Stabilite artık ölçülebiliyor (jitter/trackless/clipped/invalid metrikleri).

### PPE doğruluk/kalite (sektöre bağlı)
- Food: haircap için “full-frame local model” zayıf; head-crop rescue ile toparlıyor.
- Mask/Glasses: model + pose region tanımı ile iyi; fakat head/face region kalitesine duyarlı.

---

## Bilinen riskler ve “ne zaman model eklemeliyiz?”

### Ne zaman yeni model / retrain gerekli?
- FoodPPE-Local haircap “garbage bbox” oranı yüksek kalıyorsa (guard çok drop ediyorsa) → model dataset/label kalitesi veya sınıf ayrımı zayıf.
- Head-crop rescue sürekli devrede ve hala haircap recall düşükse → haircap sınıfı için daha güçlü model veya haircap/helmet ayrımı daha net bir checkpoint.

### Ne zaman bbox sistemi iyileştirmesi gerekli?
- `trackless_frame_ratio` sürekli yüksek (örn >0.2) ise → tracking pipeline güçlendirilmeli / stabil track_id zorunlu hale getirilmeli.
- ROI flip rate yüksekse → ROI skorlamada intersection ağırlığı artırılabilir veya bbox smoothing/EMA reset logic güçlendirilebilir.

---

## Operasyonel “health checklist” (canlı sistemde)

Bu metrikler ve loglar canlıda kaliteyi hızlı gösterir:
- `📦 BBOX_SUMMARY [...] health=... reasons=...`
- `🛡️ DECISION_GATE [...] state=...`
- Food haircap için:
  - `🍽️ Food haircap dropped (guard|no overlap)` (çok sık ise model kalitesi kötü)
  - `🍽️ Head-crop/color haircap rescue: ...` (rescue’nun işe yarayıp yaramadığı)
- Pose-aware haircap için:
  - `haircap candidate: IoU_head=..., IoU_person=..., matched=...`

---

## Ek not: “eski dokümanlar” temizliği

Bu repo içinde eski mimariyi anlatan `.md` dosyaları olabilir. Bu rapor, yalnızca koda dayanır.

Silme işlemi için kural:
- Bir `.md` dosyası **yanlış yönlendirici** ve **kodla çelişkili** ise ve güncel kullanımda referans edilmiyorsa silinebilir.
- Silmeden önce, dosyanın referans edilmediğini (CI/README/automation) doğrulamak gerekir.

