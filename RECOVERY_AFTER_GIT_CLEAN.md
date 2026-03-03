# 🔧 Kurtarma Rehberi: git clean -fdx Sonrası

## Ne Oldu?

`git clean -fdx` komutu **sadece __pycache__ değil**, şunları da sildi:

- **-f** = force  
- **-d** = untracked klasörleri de sil  
- **-x** = **.gitignore’daki dosya/klasörleri de sil** (normalde clean onlara dokunmaz)

Yani hem takip edilmeyen hem de .gitignore’da olan **her şey** silindi.

---

## Silinen Öğeler (.gitignore + çıktıya göre)

| Ne | Durum | Açıklama |
|----|--------|----------|
| **.env** | ❌ Silindi | Ortam değişkenleri, DB URL, secret'lar. `.env.example` var. |
| **venv/** (veya core/venv/) | ❌ Silindi | Sanal ortam. Yeniden oluşturulmalı. |
| **__pycache__/** | ❌ Silindi | Zararsız; Python tekrar üretir. |
| **models/sh17_*/.../weights/** | ❌ Silindi | `.gitignore`: `models/*/weights/`, `models/*/*.pt`. Tüm SH17 ağırlıkları (best.pt) gitti. |
| **data/** (içerik) | ❌ Silindi | data/raw, data/processed, data/models/yolov8n.pt vb. .gitignore’da. |
| **datasets/SH17/images/, labels/** | ❌ Silindi | .gitignore’da; eğitim verisi. |
| **yolov8n.pt, yolov8n-pose.pt** | ❌ Silindi | .gitignore’da `*.pt`. Fallback modeller. |
| **runs/, violations/, smartsafe_saas.db** | ❌ Silindi | .gitignore’da. |
| **assets/, static/** (kısmen) | ❌ Silindi | Çıktıda vardı. |
| **src/** | ⚠️ Çıktıda “Removing src/” vardı | Şu an projede `src/` var; ya geri yüklendi ya da farklı bir çalışma kopyası. |
| **models/** (sadece .py) | ✅ Duruyor | `models/sh17_model_manager.py` mevcut; alt klasörler (weights) gitti. |

---

## Model Kullanımı – Sıkıntı Var mı?

### Nerede tanımlı / kullanılıyor?

- **Tanım:** `models/sh17_model_manager.py` → `SH17ModelManager` (singleton).
- **Kullanım:**  
  `src/smartsafe/api/smartsafe_saas_api.py`,  
  `src/smartsafe/integrations/dvr/dvr_ppe_integration.py`,  
  `src/smartsafe/integrations/cameras/camera_integration_manager.py`,  
  `src/smartsafe/api/blueprints/detection.py`  
  → Hepsi `from models.sh17_model_manager import SH17ModelManager` ve `SH17ModelManager()` ile kullanıyor.
- **Çalışma dizini:** Uygulama **proje kökünden** (örn. `python -m` veya `gunicorn` ile) çalıştığı için `models` paketi bulunuyor; ekstra `sys.path` sadece `scripts/`, `tests/` için var.

### Şu anki sorun

- **Kod tarafı:** `src/` ve `models/sh17_model_manager.py` duruyorsa **entegrasyon ve import’larda sıkıntı yok**.
- **Eksik olan:**  
  - SH17 ağırlık dosyaları:  
    `models/sh17_base/sh17_base_model/weights/best.pt`,  
    `models/sh17_construction/sh17_construction_model/weights/best.pt`,  
    vb.  
  - Bunlar .gitignore’da olduğu için `git clean -fdx` ile silindi.  
  - Ağırlıklar olmadan SH17 yüklenemez; uygulama fallback (yolov8n.pt) kullanır veya hata verir.
- **Ayrıca:** `.env` ve `venv` silindiği için ortam ve bağımlılıklar da yok.

---

## Adım Adım Kurtarma

1. **.env**
   - `.env.example` dosyasını kopyala:  
     `copy .env.example .env` (Windows)  
   - `.env` içinde `DATABASE_URL`, `SECRET_KEY`, vb. değerleri doldur.

2. **Sanal ortam**
   ```bash
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **YOLO fallback**
   - `yolov8n.pt` / `yolov8n-pose.pt` genelde ilk inference’da otomatik indirilir (ultralytics).  
   - İstersen proje köküne veya `data/models/` içine yerleştir; kod `data/models/yolov8n.pt` ve `yolov8n.pt` fallback’lerine bakıyor.

4. **SH17 ağırlıkları**
   - **Yedekten geri yükle:**  
     `models/sh17_<sector>/sh17_<sector>_model/weights/best.pt` yapısını yedekten projeye kopyala.  
   - **Yedek yoksa:** Eğitim pipeline’ını (datasets + training) tekrar çalıştırman veya ağırlıkları başka kaynaktan (internal drive, paylaşım) alman gerekir.  
   - Bu dosyalar Git’te olmadığı için `git checkout` ile geri gelmez.

5. **Veritabanı**
   - `smartsafe_saas.db` silindi.  
   - Ya sıfırdan başlarsın (uygulama yeni DB oluşturur) ya da DB yedeğin varsa onu kopyalarsın.

6. **data/ ve datasets/**
   - Eğitim / test verisi ve `data/models/` içeriği yedekten veya orijinal kaynaktan geri yüklenmeli.  
   - Sadece uygulama çalıştırmak için: SH17 ağırlıkları + .env + venv yeterli; data/datasets zorunlu değil ama eğitim/benchmark için gerekir.

---

## Bir Daha Sadece __pycache__ Temizlemek İçin

- **Sadece __pycache__ silmek (güvenli):**
  ```bash
  Get-ChildItem -Path . -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force
  ```
  veya (Git Bash):
  ```bash
  find . -type d -name __pycache__ -exec rm -rf {} +
  ```
- **.env’i koruyarak clean (eğer ileride yine clean kullanırsan):**
  ```bash
  git clean -fdx -e .env
  ```
  Böylece .env silinmez; yine de `venv`, `models/*/weights/`, `data/` gibi ignore’daki her şey silinir, bu yüzden **sadece __pycache__ için yukarıdaki find/Get-ChildItem yöntemini kullanmak daha güvenli.**

---

## Özet

- **Model tanımı ve entegrasyon:** Projede doğru yerde ve kullanım doğru; **kod tarafında model kullanımıyla ilgili ek bir hata yok**.
- **Eksik olan:** `git clean -fdx` ile **.env, venv, SH17 weights, data/datasets içeriği, DB** silindi. Bunların yedekten veya yeniden kurulumla geri gelmesi gerekiyor.
- **Sonraki sefer:** Sadece önbellek temizlemek için `__pycache__` klasörlerini hedefleyen komutları kullan; `git clean -fdx` özellikle `-x` yüzünden ignore’daki tüm dosyaları sildiği için proje klasörü düzenlerken riskli.

Bu dosyayı proje kökünde `RECOVERY_AFTER_GIT_CLEAN.md` olarak kaydettim; adımları takip ederek ortamı ve (mümkünse) ağırlıkları geri yükleyebilirsin.
