# SmartSafe AI - Frontend (Vercel Deployment)

Bu klasör SmartSafe AI projesinin frontend kısmını içerir ve Vercel'de deploy edilmek için optimize edilmiştir.

## 🎯 Neden Ayrı Frontend?

- ⚡ **Cold start sorunu yok**: Statik dosyalar anında yüklenir
- 🌍 **Global CDN**: Dünyanın her yerinden hızlı erişim
- 🚀 **Vercel optimizasyonu**: Otomatik optimizasyon ve caching
- 💰 **Ücretsiz hosting**: Vercel'in cömert free tier'ı

## 📦 İçerik

```
vercel-frontend/
├── index.html              # Ana landing page (SADECE PUBLIC PAGE)
├── static/
│   ├── js/
│   │   ├── translations.js          # Dil çevirileri
│   │   └── smart_camera_detection.js
│   ├── images/                       # Görseller
│   └── videos/                       # Video içerikler
├── vercel.json             # Vercel konfigürasyonu
├── deploy.ps1              # Windows deploy script
├── deploy.sh               # Linux/Mac deploy script
└── README.md              # Bu dosya
```

**Not:** Subscription, billing, ve profile sayfaları backend'de (Render.com) kalıyor çünkü authentication gerektiriyorlar.

## 🚀 Vercel'e Deploy

### 1. Vercel CLI Kurulumu

```bash
npm i -g vercel
```

### 2. Vercel'e Login

```bash
vercel login
```

### 3. Deploy

```bash
cd vercel-frontend
vercel
```

İlk deploy sırasında şu soruları soracak:
- **Set up and deploy**: `Y`
- **Which scope**: Hesabınızı seçin
- **Link to existing project**: `N`
- **Project name**: `smartsafe-frontend` (veya istediğiniz isim)
- **In which directory**: `./`
- **Want to override settings**: `N`

### 4. Production Deploy

Test başarılı olduysa production'a deploy edin:

```bash
vercel --prod
```

## 🔧 Konfigürasyon

### API Backend URL

Backend URL `index.html` içinde tanımlıdır:

```javascript
const API_BASE_URL = 'https://smartsafe-api.onrender.com';
```

Eğer backend URL'iniz farklıysa, bu değeri güncelleyin.

### Environment Variables (Opsiyonel)

Vercel Dashboard'da environment variable olarak da tanımlayabilirsiniz:

```
VITE_API_URL=https://smartsafe-api.onrender.com
```

## 🌐 Domain Ayarları

Vercel ücretsiz olarak size `xxx.vercel.app` domain'i verir. Kendi domain'inizi bağlamak için:

1. Vercel Dashboard → Project → Settings → Domains
2. Domain ekleyin
3. DNS kayıtlarını güncelleyin

## 📊 Performans

- **First Paint**: ~200ms
- **Time to Interactive**: ~500ms
- **Lighthouse Score**: 95+

## 🔒 Güvenlik

- HTTPS otomatik aktif
- Security headers yapılandırılmış
- XSS Protection aktif
- CORS backend'de yapılandırılmış

## 🛠️ Geliştirme

Yerel development için basit bir HTTP server kullanabilirsiniz:

```bash
# Python
python -m http.server 8000

# Node.js
npx serve
```

Sonra `http://localhost:8000` adresini ziyaret edin.

## 📝 Önemli Notlar

1. **Static Site**: Bu tamamen statik bir sitedir, server-side rendering yok
2. **API Calls**: Tüm dinamik işlemler Render.com backend'ine yapılır
3. **CORS**: Backend'de CORS açık olmalı (zaten yapılandırılmış)
4. **Caching**: Static dosyalar 1 yıl cache'lenir

## 🐛 Sorun Giderme

### API çağrıları çalışmıyor

1. Backend'in çalıştığından emin olun
2. CORS ayarlarını kontrol edin
3. Browser console'da hata mesajlarını inceleyin

### Görseller görünmüyor

1. `static/images/` klasöründe dosyaların olduğundan emin olun
2. Path'lerin doğru olduğunu kontrol edin (`/static/images/...`)

### Vercel build hatası

1. `vercel.json` syntax'ının doğru olduğundan emin olun
2. Tüm dosyaların commit edildiğinden emin olun

## 📞 Destek

Sorularınız için: yigittilaver2000@gmail.com

## 📄 Lisans

© 2025 SmartSafe AI. Tüm hakları saklıdır.

