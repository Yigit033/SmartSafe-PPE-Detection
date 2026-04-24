# Food PPE Tespit Sorunu – Analiz Raporu

Bu rapor, ekran görüntüsünde görülen “bone/önlük/eldiven var ama EKSİK gösteriliyor” probleminin kök nedenlerini ve diğer LLM’in teşhis/planının doğruluğunu özetler. **İyileştirme kodu uygulanmamıştır;** sadece analiz yapılmıştır.

---

## 1. Mevcut Akış Özeti

### 1.1 Food model kullanımı (`sh17_model_manager.py`)

- **Sektör `food` veya `food_beverage`** olduğunda `detect_ppe()`:
  1. Önce **SH17** (genel 17 sınıflı model) ile tespit yapar.
  2. Ardından **food PPE local model** (`_load_food_ppe_model()`) çağrılır; bulunursa sonuçlar birleştirilir.

- **Food model yolu:**  
  `core/models/sh17_food_beverage/sh17_food_beverage_model/weights/best.pt`  
  Projede bu dosya **mevcut** (SH17ModelManager.models_dir = core/models ile bulunuyor). Sınıflar: Apron, Googles, Haircap, Mask, gloves — _FOOD_PPE_NAME_MAP ile uyumlu.

- **SH17 sınıfları** (17-class):  
  `person, head, face, glasses, face_mask_medical, ..., gloves, medical_suit, safety_suit, helmet, ...`  
  Yani SH17 **“haircap” / “bone” üretmez**, sadece **“head”** üretir.

- **Sector mapping (food):**  
  `['head', 'face_mask_medical', 'gloves', 'medical_suit']`  
  Gıda için zorunluluk “head” olarak tanımlı; test script’i ise **“haircap”** istiyor.

### 1.2 Test script’in zorunlu PPE listesi (`food_sector_video_test.py`)

```python
FOOD_REQUIRED_PPE = [
    "safety_suit",    # Önlük
    "haircap",        # Bone
    "face_mask",      # Maske
    "safety_glasses", # Gözlük
    "gloves",         # Eldiven
]
```

Bu liste `pose_aware_ppe_detector` içindeki `PPE_CONFIG` anahtarlarıyla uyumlu (safety_suit, haircap, face_mask, safety_glasses, gloves). İsimlendirme tarafında **medical_suit vs safety_suit** uyumsuzluğu yok: `PPE_CONFIG['safety_suit']` zaten `model_classes: ['safety_suit', 'medical_suit', 'apron']` içeriyor; yani model “medical_suit” veya “apron” döndürse bile safety_suit olarak sayılıyor.

---

## 2. Kök Neden Analizi

### 2.1 Neden 1: Food model yok → Bone (haircap) hiç karşılanamıyor

- `pose_aware_ppe_detector.py` içinde **haircap** için `model_classes`:  
  `['haircap', 'bone', 'file', 'kep']`  
  **“head” burada yok.**

- Sadece SH17 çalıştığında gelen **“head”** tespiti, `_associate_ppe_with_pose` içinde hiçbir `ppe_type` ile eşleşmiyor (haircap’in model_classes’ında “head” olmadığı için). Sonuç:
  - Bone/haircap için **her zaman “eksik”** çıkıyor.
- Diğer LLM’in planında bu nokta **yok**. Bu, gıda senaryosunda bone’un sürekli EKSİK görünmesinin önemli bir nedeni.

### 2.2 Neden 2: Küçük nesnelerde IoU reddi (diğer LLM’in teşhisi doğru)

- Kişi kutusu (person bbox) tüm gövdeyi kapsıyor; bone, eldiven, maske, önlük kutuları ise küçük.
- **Person IoU:** PPE kutusu ile kişi kutusunun IoU’su küçük nesnelerde çok düşük kalıyor (ör. 0.02–0.06).
- `_find_best_ppe_match` içinde **person_iou_threshold**:
  - haircap: **0.08**
  - gloves: **0.1**
  - face_mask: **0.1**
  - safety_suit: **0.1**
- Koşul: `person_iou > person_iou_threshold` olmazsa aday hiç “best_match” olmuyor; fallback’ler (merkez içinde mi, vb.) de bu aday için devreye girmiyor.
- Bu yüzden **model bone/eldiven/önlük/maske tespit etse bile**, kişiyle eşleşme aşamasında elenip “EKSİK” gösterilmesi mümkün. Diğer LLM’in “küçük nesnelerin IoU ile reddedilmesi” teşhisi **doğru ve yeterli**.

### 2.3 İsimlendirme (medical_suit / safety_suit)

- **Kod tarafında tutarlı:**  
  Zorunlu liste “safety_suit”, detector çıktısı “medical_suit” veya “apron” olsa bile `PPE_CONFIG` ile safety_suit altında toplanıyor. Ek bir isim düzeltmesine gerek yok.
- Plan’daki “medical_suit vs safety_suit uyumsuzluğu” ifadesi, bu codebase’de **ek bir hata anlamında gerekli değil**; yine de etiket/renk haritalarının aynı canonical isimlerle (safety_suit, haircap, face_mask, vb.) uyumlu olması faydalı (zaten büyük ölçüde öyle).

---

## 3. Diğer LLM’in Önerilerinin Değerlendirmesi

| Öneri | Doğru mu? | Yeterli mi? | Not |
|-------|-----------|-------------|-----|
| **person_iou_threshold’u düşürmek** (haircap, gloves, face_mask için 0.08/0.1 → 0.02) | Evet | Evet | Küçük PPE’lerin kişiyle eşleşmesini artırır; mantıklı ve güvenli. |
| **Class mapping / medical_suit vs safety_suit** | Kısmen | Zaten var | Kodda safety_suit ↔ medical_suit/apron eşlemesi mevcut; ek “fix” gerekmiyor. |
| **FOOD_REQUIRED_PPE ve etiket/renk haritalarını detector çıktısına göre hizalamak** | Evet | Evet | FOOD_REQUIRED_PPE zaten PPE_CONFIG anahtarlarıyla uyumlu; etiket/renk haritalarının bu anahtarlarla (ve neg_label’larla) tutarlı olması iyi olur. |
| **sh17_model_manager’da food için canonical isim tutarlılığı** | Evet | Evet | _FOOD_PPE_NAME_MAP zaten Apron→medical_suit, Haircap→haircap vb. yapıyor; kontrol edilmesi yeterli. |

**Eksik kalan nokta (diğer planda yok):**

- **Food model dosyası yokken bone’un hep EKSİK görünmesi:**  
  SH17 sadece “head” veriyor, “haircap” vermiyor. Pose-aware tarafta **haircap** için `model_classes` içine **“head”** eklenirse, SH17-only modda da “head” tespiti bone yerine sayılabilir (gıda bağlamında “baş bölgesi tespiti” bone için vekil kabul edilebilir).  
  Not: İnşaat sektörü haircap zorunlu tutmadığı için, “head”i haircap’e map etmek sadece gıda/required_ppe=[haircap] kullanan senaryoları etkiler; inşaat davranışını bozmaz.

---

## 4. Sonuç ve Önerilen Aksiyon Sırası

1. **IoU (öncelikli):**  
   `pose_aware_ppe_detector.py` içinde `person_iou_threshold` değerlerini **haircap, gloves, face_mask (ve istenirse safety_suit)** için **0.02** (veya 0.03) seviyesine düşürmek. Diğer LLM’in önerisi **doğru ve en mantıklı ilk adım**.

2. **Bone’un SH17-only modda tanınması:**  
   - Ya **food PPE model** (`sh17_food_beverage/.../best.pt`) projeye eklenir (tercih edilirse),  
   - Ya da **haircap** için `model_classes` listesine **`'head'`** eklenir; böylece sadece SH17 çalışırken “head” tespiti bone yerine kabul edilir.

3. **İsimlendirme:**  
   Mevcut medical_suit/safety_suit/apron ve FOOD_PPE_NAME_MAP yapısı yeterli; ek değişiklik gerekmez. Test script’teki FOOD_LABEL_MAP / FOOD_COLOR_MAP’in PPE_CONFIG’deki `pos_label` / `neg_label` ve canonical isimlerle aynı olduğundan emin olmak yeterli.

4. **Doğrulama:**  
   Diğer LLM’in verification planı (food_sector_video_test ile “Uygun” sayısının artması, kırmızı EKSİK kutularının azalması) uygundur; buna ek olarak:
   - Food model **yoksa**: “head” → haircap eşlemesi sonrası bone’un artık “uygun” sayıldığı manuel kontrol edilmeli.
   - Food model **varsa**: Hem IoU hem (isteğe bağlı) “head” eşlemesi ile sonuçların değişimi izlenmeli.

---

**Özet:** Diğer LLM’in IoU eşiğini düşürme ve etiket/renk haritalarını hizalama önerileri **doğru ve yeterli**. Eksik olan kritik nokta, **food model yokken bone’un hiç karşılanmaması**; bunun için ya food model eklenmeli ya da haircap’in `model_classes`’ına `'head'` eklenmeli. İyileştirme yapmadan önce bu analizi onaylayıp hangi seçenekleri (sadece IoU / IoU + head→haircap / food model kurulumu) uygulayacağınıza karar verebilirsiniz.
