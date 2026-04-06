# violation_events — PR1 → PR2 → PR3 rollout checklist

Aynı adımları **local Docker** (`smartsafe_saas`, PgWeb :5051) ve **prod** (`DATABASE_URL`, örn. Render) için ayrı ayrı uygulayın. Veritabanları farklıdır.

---

## Tamamlanan (senin durumun)

- [x] `backend/company/migrations/2_violation_events_expand_pr1.up.sql` — kolonlar + `dvr_channel_id` FK + `cameras` FK kaldırıldı  
- [x] Orphan kontrolü (LEFT JOIN `cameras` → 0)  
- [x] `pg_constraint`: `violation_events_camera_id_fkey` **yok**

---

## Adım PR2 — Backfill (PgWeb veya psql)

**Dosya:** `core/scripts/database/violation_events_pr2_backfill.sql`

1. İsteğe bağlı: satır 27–28’deki ön kontrolleri yorumdan çıkarıp çalıştır.
2. Sırayla çalıştır:
   - **Bölüm 1** — `UPDATE` (DVR eşleşmesi, `camera_id = channel_id`)
   - **Bölüm 2** — `UPDATE` (`dvr_` + SUBSTRING kuralı)
   - **Bölüm 3** — `UPDATE` (geri kalanlar → `camera`, `_ch` olmayanlar)
3. **Bölüm 4** doğrulama `SELECT`’leri:
   - **4a** `violation_events_source_type_still_null` → **0** (0 değilse önce 4f listesini incele)
   - **4b**, **4c** → **0**
   - **4d** `dvr_fk_fill_pct` → **100** veya kabul ettiğin eşik
   - **4e** `rows_needing_legacy_substring_join` → mümkünse **0** (PR3 read path sade)
   - **4f** boş sonuç (veya bilerek bırakılan satır yok)

**Prod:** Aynı dosyayı prod `DATABASE_URL` ile bağlandığın istemcide tekrarla.

---

## Adım uygulama — PR3 öncesi kod

**Repo:** `core/database/database_adapter.py`, `core/app.py`, DVR/camera entegrasyonları, `backend/violation/violation.ts` (zaten PR3 read path için güncel).

- Çalışan süreç **DVR ihlalinde DB’ye `camera_id = NULL`, `source_type` + `dvr_channel_id` dolu** yazmalı (PR3 CHECK ile uyumlu).  
- Bu sürüm **PR3 SQL’den önce** deploy edilmeli (migration dosyasındaki uyarı).

---

## Adım PR3 — Contract migration

**Dosya:** `backend/company/migrations/3_violation_events_contract_pr3.up.sql`

1. PR2 gate’leri tamamlandıktan ve uygulama yukarıdaki gibi deploy edildikten sonra PgWeb’de (veya prod’da) **tüm dosyayı** çalıştır.  
2. Hata: `PR2 backfill required: source_type IS NULL` → PR2’yi bitir, tekrar dene.

---

## Adım verify — PR3 sonrası

**Dosya:** `core/scripts/database/verify_violation_events_post_pr3.sql`

- Tüm sorguları çalıştır; sayımlar **0**, `legacy_violation_events_camera_id_fkey_present` **0**, CHECK + index isimleri listede olmalı.

---

## Smoke (manuel)

- `GET /company/:company_id/violation-events` — `camera_name` / `camera_id` mantıklı mı  
- DVR kanalında test ihlali → kayıt ve liste

---

## Encore / local backend

`backend/db.ts` her pool açılışında `*/migrations/*.sql` dosyalarını sırayla çalıştırır; **local’de sadece PgWeb kullanıyorsan** migration’ları elle koşturman yeterli. **Prod’da** deploy sonrası aynı SQL’lerin o ortamda da işlendiğinden emin ol.




Sorunumuz neydi?
Kök problem: violation_events.camera_id tek kimlik gibi kullanılıyordu ve bazı DVR kanal kimlikleri cameras tablosunda yoktu. Bu da FK/okuma-yazma uyumsuzluğu, “shadow row” gibi hack’lere ve prod’da hata riskine yol açıyordu.
Hedef: violation_events’i iki kaynağı destekleyecek şekilde normalize etmek:
IP kamera → source_type='camera', camera_id dolu
DVR kanal → source_type='dvr_channel', dvr_channel_id dolu
Son durumda CHECK ile “tam olarak biri dolu” kuralı.
Ne yaptık? (mimariyi prod’a taşımak için)
1) Expand → Migrate → Contract planını “operasyonel” hale getirdik
Planı 3 parça PR/migration seti gibi netleştirdik:
PR1 Expand: Şema genişletme + uyumlu yazma/okuma
PR2 Migrate: Idempotent backfill + doğrulama
PR3 Contract: CHECK + NOT NULL + temizlik + index
2) PR1’i güvenli hale getirdik (shadow yok + fail-fast)
Shadow yaklaşımını tamamen devre dışı bıraktık (veri modelini kirletmemek için).
DVR eşleşmesi bulunamazsa:
Sessiz NULL yazma yok (silent corruption riski kaldırıldı)
Fail-fast: event yazılmıyor + loglanıyor (prod güvenliği)
3) Read path geriye uyumlu kalsın diye geçiş katmanı ekledik
getEvents tarafında DVR camera_name boş dönmesin diye geçici join mantığı ekledik.
Bu mantığı “geçici geçiş katmanı” olarak açıkça işaretledik ve PR3’te sadeleşmesini planladık.
4) PR2 için idempotent backfill + gate sorgularını hazırladık
core/scripts/database/violation_events_pr2_backfill.sql:
Aynı script tekrar çalıştırılabilir (idempotent)
Doğrulama sorguları: NULL source_type, orphan FK, doluluk yüzdesi, SUBSTRING dalı gerekliliği vb.
5) PR3 için contract + verify
Contract’ta:
DVR satırlarında camera_id = NULL
source_type NOT NULL
CHECK constraint (shape kuralı)
Partial index’ler (kamera vs DVR path)
Post-PR3 doğrulama:
core/scripts/database/verify_violation_events_post_pr3.sql ile tüm sayaçlar 0 ve constraint/index varlığı kontrolü.
Checklist dosyası (core/scripts/database/VIOLATION_EVENTS_ROLLOUT_CHECKLIST.md) ne diyor?
Bu dosya, yaptıklarımızı “prod’da uygulanabilir” bir runbook’a çeviriyor:

Tamamlanan (senin durumda):

PR1 migration çalıştı, source_type + dvr_channel_id geldi
Orphan kontrolü yapıldı (0)
violation_events_camera_id_fkey kaldırıldı
PR2 Backfill:

violation_events_pr2_backfill.sql içinde bölüm 1–2–3 UPDATE
bölüm 4’teki gate SELECT’ler (0/100% hedefleri)
PR3 öncesi uygulama:

DVR yazımı DB’ye camera_id=NULL, source_type+dvr_channel_id dolu olmalı
PR3 migration:

3_violation_events_contract_pr3.up.sql çalıştır
PR3 sonrası verify:

verify_violation_events_post_pr3.sql tüm sayımlar 0 + index/constraint kontrol
Smoke:

GET /company/:company_id/violation-events
DVR’dan test ihlali üret → DB’ye yazıldı mı + listede görünüyor mu
Local vs prod ayrımı:

PgWeb (local docker) ile prod DATABASE_URL birbirinden farklı olabilir; aynı adımlar iki ortamda ayrı uygulanır.
Sonuç (profesyonel seviyede “neden iyi oldu?”)
Shadow hack kaldırıldı → veri modeli temiz.
Fail-fast → sessiz veri bozulması yok.
Backfill + gate sorguları → PR3’e geçiş “ölçülebilir” hale geldi.
Contract (CHECK/NOT NULL) + verify → prod’da kalıcı doğruluk garantisi.
Runbook/checklist → operasyon adımları tek dosyada, tekrarlanabilir.