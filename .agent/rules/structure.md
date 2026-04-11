# SmartSafe Smart Structure Rules

Bu doküman, projenin Frontend, Backend ve Core servisleri arasındaki görev dağılımını ve çalışma prensiplerini belirler.

## 🏗️ Servis Mimarisi

### 1. Frontend (Next.js/React)
- **Port:** `3000`
- **Sorumluluk:** Kullanıcı arayüzü, state yönetimi, kullanıcı etkileşimi.
- **Clientlar:**
  - `api` (`@/lib/api`): Backend (Encore) ile konuşur.
  - `core` (`@/lib/core`): Core (Flask) ile konuşur.

### 2. Backend (Encore/Go)
- **Port:** `4477`
- **Sorumluluk:**
  - Ana iş mantığı (Business Logic).
  - Veritabanı yönetimi ve **Migration** işlemleri.
  - Şirket, kullanıcı ve üyelik yönetimi.
- **Dosya Yolu:** `/backend`
- **NOT:** Verilerde kalıcı bir değişiklik (DB Update) yapılacağı zaman bu servis kullanılır.

### 3. Core (Flask/Python)
- **Port:** `5577`
- **Sorumluluk:**
  - **AI & Computer Vision:** PPE tespiti ve görüntü işleme.
  - **Kamera Entegrasyonları:** ONVIF, DVR Streaming, Kamera Tarama (Discovery).
  - **Bildirimler:** Telegram bot işlemleri ve anlık uyarılar.
- **Dosya Yolu:** `/core`
- **NOT:** Donanım (Kamera) ve yapay zeka ile ilgili tüm asıl işlerin mutfağıdır.

## 🚦 İletişim Kuralları

- **Discovery & Stream:** Kamera arama veya canlı yayın işlemleri doğrudan `core` üzerinden (5577) yapılır.
- **Ayarlar & Profil:** Şirket bilgileri veya bildirim tercihleri güncellenirken `backend` (4477) üzerinden gidilir.
- **Migration:** Yeni bir sütun veya tablo eklendiğinde `backend` klasöründe migration dosyası oluşturulmalıdır. Core servisi veritabanına erişir ama şema değişikliği yapmaz.

## 🛠️ Geliştirme İpuçları
- Bir özellik eklerken kendine sor: "Bu bir veri kaydı mı (Backend), yoksa bir donanım/AI işlemi mi (Core)?"
- Portları karıştırma: `4477` (Kayıt), `5577` (İşlem).
