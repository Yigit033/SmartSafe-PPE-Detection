# SmartSafe AI - Agent Rules & Workflow

Bu dosya, SmartSafe AI projesinde çalışan AI agent'ları için operasyonel kuralları ve rol bazlı yetkilendirmeyi tanımlar.

## 👥 Rol Bazlı Geliştirme Sistemi (RBAC)

Agent, çalışmaya başladığında kullanıcının hangi rolde olduğunu kontrol etmeli ve ilgili sınırları aşmamalıdır.

### 🎭 Rol A: FullStack Developer (Senin Modun)

- **Ana Görev:** Kullanıcı arayüzü, iş mantığı ve veritabanı şeması.
- **İzin Verilen Dizinler:** `/frontend`, `/backend`, `core/database/database_adapter.py`.
- **YASAKLI ALAN:** `/core` altındaki AI/Detection modelleri ve algoritmaları (`pose_aware_ppe_detector.py`, `smartsafe_sector_manager.py` vb.).
- **Davranış:** AI değişikliği gerekiyorsa altyapıyı hazırla ve teknik bir devir notu oluştur.

### 🎭 Rol B: Core Developer (Arkadaşının Modu)

- **Ana Görev:** AI tespiti, görüntü işleme ve Core API optimizasyonu.
- **İzin Verilen Dizinler:** `/core` (Tamamı), `core/database/database_adapter.py`.
- **YASAKLI ALAN:** `/frontend` ve `/backend` dizinleri.
- **Davranış:** UI veya Backend değişikliği gerekiyorsa hazırlığı bitirip teknik bir devir notu oluştur.

## 🛠 Genel Operasyonel Kurallar

1. **Backend Restart:** `/backend` altındaki `.ts` kodları değiştiğinde Encore'u şu komutla yeniden başlatmak zorunludur:
   `docker restart smartsafe-backend-encore`
2. **Hata Yakalama:** Core ve Backend arasındaki veri uyumsuzluklarında her zaman `database_adapter.py` üzerindeki şemaya güvenilmelidir.
3. **Senkronizasyon:** Bir rol işini bitirdiğinde, diğer rolün agent'ına hitaben teknik detayları içeren bir özet hazırlar.

## 📋 İş Akışı (Workflow)

1. **Rol Tespiti:** Agent kullanıcıya "Hangi rolde çalışıyoruz?" diye sormalıdır.
2. **Analiz:** İlgili dosyaları bul, rol sınırlarını kontrol et.
3. **Uygulama:** Sadece yetki dahilindeki dosyalarda değişiklik yap.
4. **Devir:** Gerekliyse diğer geliştirici için teknik not hazırla.
