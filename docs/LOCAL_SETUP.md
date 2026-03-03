# SmartSafe PPE – Lokal Kurulum (Eksiksiz)

Başka bir PC’de projeyi senin lokaldeki gibi çalıştırmak için **tüm** adımlar. Hiçbir adım atlanmamalı.

---

## 1. Gereksinimler

- **Python 3.10+** (tercihen 3.12)
- **Git**
- **Node.js ve npm** (proje `npm run backend` / `npm run frontend` ile çalıştığı için gerekli)
- **NVIDIA GPU sürücüsü** (NVIDIA kart varsa; yoksa PyTorch CPU ile kurulacak)

---

## 2. Repo ve sanal ortam

```bash
git clone <repo-url>
cd Personal_Protective_Equipment_(PPE)_Detection

python -m venv venv
```

Sanal ortamı aktif et:

- **Windows (PowerShell):**  
  `.\venv\Scripts\activate`
- **Linux/macOS:**  
  `source venv/bin/activate`

---

## 3. Python bağımlılıkları

### 3.1 Temel bağımlılıklar

```bash
pip install -r requirements.txt
```

**Not:** `requirements.txt` içinde **torch / torchvision / torchaudio** ve **supervision** yoktur. Bunlar detection pipeline (GPU, ByteTrack, temporal tracking) için ayrı kurulur.

---

### 3.2 PyTorch (GPU veya CPU)

Pose modeli (YOLOv8n-Pose) ve SH17 (yolo9e) GPU’da çalışsın diye **PyTorch’u CUDA’lı kurmak** gerekir. `pip install -r requirements.txt` sırasında ultralytics bazen CPU sürümü torch indirebilir; GPU kullanacaksan önce requirements’ı kur, sonra PyTorch’u aşağıdaki gibi ayarla.

- **NVIDIA GPU varsa (CUDA 12.1 önerilir):**
  ```bash
  pip uninstall torch torchvision torchaudio -y
  pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
  ```
  Başarılı olursa log’da "Pose model set to CUDA inference" / "SH17 ... Device: cuda" görünür.

- **GPU yoksa (sadece CPU):**
  ```bash
  pip install torch torchvision torchaudio
  ```

---

### 3.3 ByteTrack ve temporal tracking (supervision)

Kişi takibi (ByteTrack) ve frame pencereli uyum (temporal voting) için **supervision** kütüphanesi zorunludur. Kurulmazsa uygulama çalışır ama "ByteTrack tracking will be disabled" uyarısı çıkar ve takip/uyum davranışı senin lokalinle aynı olmaz.

```bash
pip install supervision
```

---

### 3.4 Özet: Detection pipeline bağımlılıkları

| Paket | Nerede kullanılır | Kurulum |
|-------|--------------------|---------|
| **torch, torchvision, torchaudio** | Pose model + SH17 (GPU/CPU) | Adım 3.2 |
| **supervision** | ByteTrack, `sv.Detections.from_ultralytics` | Adım 3.3 |
| **ultralytics** | YOLOv8n-Pose, YOLO modelleri | requirements.txt |
| **opencv** | Görüntü okuma, çizim | requirements.txt |

Bu dörtlü (requirements + PyTorch + supervision) tamam olmadan detection senin lokaldeki gibi çalışmaz.

---

## 4. Ortam değişkenleri (.env)

Proje **kök dizininde** `.env` dosyası oluştur. Repo’da yoktur; her geliştirici kendi `.env` dosyasını ekler.

Aşağıdaki içeriği kopyala, kendi değerlerinle düzenle (SECRET_KEY, JWT_SECRET_KEY, mail bilgileri vb.):

```env
ENV=local
DATABASE_URL=

FLASK_ENV=development
FLASK_DEBUG=True
SECRET_KEY=your-secret-key-here
JWT_SECRET_KEY=your-jwt-secret-key-here
BCRYPT_LOG_ROUNDS=12
FOUNDER_PASSWORD=smartsafe2024admin

MAX_CONTENT_LENGTH=16777216
UPLOAD_FOLDER=static/uploads

DETECTION_CONFIDENCE_THRESHOLD=0.5
DETECTION_MODEL_PATH=data/models/yolov8n.pt

LOG_LEVEL=INFO
LOG_FILE=logs/smartsafe.log

SENDGRID_API_KEY=
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USERNAME=
MAIL_PASSWORD=
MAIL_USE_TLS=True

RATE_LIMIT_REQUESTS=100
RATE_LIMIT_WINDOW=3600
```

- `DATABASE_URL` boş bırakılırsa lokal **SQLite** kullanılır (`smartsafe_saas.db` otomatik oluşur).
- `SECRET_KEY` ve `JWT_SECRET_KEY` mutlaka gerçek, rastgele ve güvenli değerler olmalı.
- Mail kullanmayacaksan `MAIL_USERNAME` / `MAIL_PASSWORD` boş bırakılabilir; uygulama açılır.

---

## 5. SH17 model ağırlıkları

PPE detection’ın doğru çalışması için **zorunlu**.

1. **yolo9e.pt** indir:  
   https://github.com/ahmadmughees/SH17dataset/releases/download/v1/yolo9e.pt

2. İndirilen dosyayı proje kökündeki `models` klasörüne koy:
   - Hedef yol: `models/yolo9e.pt`  
   - `models` yoksa oluştur.

3. Kurulum script’ini çalıştır (sanal ortam aktifken, proje kökünden):

   - **Windows:**  
     `.\venv\Scripts\python scripts/install_sh17_yolo9e.py`
   - **Linux/macOS:**  
     `./venv/bin/python scripts/install_sh17_yolo9e.py`

Bu işlem `yolo9e.pt` dosyasını tüm sektörlerin `.../weights/best.pt` path’lerine kopyalar. Atlanırsa PPE detection gerçek SH17 modeli yerine fallback kullanır; davranış senin lokalinle aynı olmaz.

---

## 6. Uygulamayı çalıştırma

Tüm komutlar **proje kök dizininden** ve **sanal ortam aktifken** çalıştırılmalı.

**Backend:**

- **Windows:**  
  `npm run backend`  
  (Arka planda: `PYTHONPATH=src` + `venv` içindeki `python -m src.smartsafe.api.smartsafe_saas_api`)

- **Linux/macOS (npm kullanmadan):**  
  ```bash
  export PYTHONPATH=src
  ./venv/bin/python -m src.smartsafe.api.smartsafe_saas_api
  ```

Backend varsayılan: **http://127.0.0.1:5000**

**Frontend (ayrı bir terminalde):**

- **Windows:**  
  `npm run frontend`  
  veya:  
  `.\venv\Scripts\python -m http.server 8000 --directory vercel-frontend`

- **Linux/macOS:**  
  `./venv/bin/python -m http.server 8000 --directory vercel-frontend`

Tarayıcıda: **http://127.0.0.1:8000**

**Backend + frontend birlikte (tek komut):**

- **Windows:**  
  `npm run dev`

---

## 7. Kamera ile PPE detection (siyah ekran olmaması için)

- Kamera eklerken **IP**, **port** ve **Stream path** doğru olmalı.
- Telefon kamera uygulaması (IP Webcam vb.) için stream path çoğunlukla **`/video`** veya **`/mjpeg`**.
- **Stream path** alanına sadece snapshot path’i (`/shot.jpg`, `/photo.jpg` vb.) yazılırsa ve bu URL’ler çalışmıyorsa detection ekranı siyah kalır. Bu alan mutlaka **canlı yayın path’i** (örn. `/video`) olmalı.

---

## 8. Kontrol listesi

| # | Adım |
|---|------|
| 1 | Repo clone, `cd` ile proje köküne gir |
| 2 | `python -m venv venv` + sanal ortamı aktif et |
| 3 | `pip install -r requirements.txt` |
| 4 | PyTorch kur: GPU için `pip uninstall torch torchvision torchaudio -y` sonra `pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121`; CPU için `pip install torch torchvision torchaudio` |
| 5 | `pip install supervision` (ByteTrack + temporal tracking) |
| 6 | Kökte `.env` oluştur, tüm gerekli değişkenleri doldur |
| 7 | `models/yolo9e.pt` indir, `models/` altına koy |
| 8 | `.\venv\Scripts\python scripts/install_sh17_yolo9e.py` (Windows) veya `./venv/bin/python scripts/install_sh17_yolo9e.py` (Linux/macOS) |
| 9 | `npm run backend` (Windows) veya `export PYTHONPATH=src` + `./venv/bin/python -m src.smartsafe.api.smartsafe_saas_api` (Linux/macOS) |
| 10 | Ayrı terminalde `npm run frontend` veya `python -m http.server 8000 --directory vercel-frontend` |
| 11 | Kamera kullanılacaksa stream path = `/video` (veya kullanılan uygulamanın canlı yayın path’i) |

Bu adımların hepsi uygulandığında proje, senin lokaldekiyle aynı seviyede çalışır.
