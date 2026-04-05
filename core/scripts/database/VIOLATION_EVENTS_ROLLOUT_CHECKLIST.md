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
