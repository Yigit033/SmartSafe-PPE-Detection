-- =============================================================================
-- violation_events — PR2 backfill (PostgreSQL)
-- =============================================================================
-- Amaç: PR1 öncesi / eksik kolonlu satırlarda source_type ve dvr_channel_id doldurmak.
-- Önkoşul: PR1 migration uygulanmış olmalı (source_type, dvr_channel_id kolonları).
--           Güncel `2_violation_events_expand_pr1.up.sql` violation_events_camera_id_fkey
--           kaldırır (orphan kontrolü: LEFT JOIN cameras → 0 satır). PgWeb’de dosyayı
--           yeniden çalıştırın veya backend auto-migration çalışsın.
--
-- Idempotent: Aynı UPDATE’ler tekrar çalıştırılabilir; zaten doğru atanmış satırlar
--             genelde değişmez (WHERE source_type IS NULL veya açık koşullar).
--
-- Çalıştırma: Yedek alın; maintenance penceresinde veya düşük yükte batch ile çalıştırın.
--             Büyük tabloda her UPDATE’i LIMIT ile batch’lemek için ayrı script önerilir.
--
-- PR2 sonrası doğrulama (PR3 migration öncesi):
--   1) DVR satırlarında dvr_channel_id doluluk oranı ~%100 mü?
--   2) “PR3 readiness” sorgusu: SUBSTRING ile eşleşen satır kaldı mı? (≈0 olmalı)
--
-- Sonraki adım: backend/company/migrations/3_violation_events_contract_pr3.up.sql
-- (CHECK, NOT NULL, DVR camera_id temizliği, partial index) + uygulama deploy.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 0) Ön kontrol (salt okunur)
-- -----------------------------------------------------------------------------
-- SELECT COUNT(*) AS total FROM violation_events;
-- SELECT COUNT(*) AS missing_source_type FROM violation_events WHERE source_type IS NULL;

-- -----------------------------------------------------------------------------
-- 1) DVR eşleşmesi: camera_id = dvr_channels.channel_id (ham channel_id formatı)
-- -----------------------------------------------------------------------------
UPDATE violation_events ve
SET
  source_type = 'dvr_channel',
  dvr_channel_id = dc.channel_id
FROM dvr_channels dc
WHERE ve.company_id = dc.company_id
  AND ve.source_type IS NULL
  AND ve.dvr_channel_id IS NULL
  AND ve.camera_id = dc.channel_id;

-- -----------------------------------------------------------------------------
-- 2) DVR eşleşmesi: işlemci stream_id dvr_{dvr_id}_chNN → channel_id = substring
--    (add_violation_event / getEvents ile aynı kural)
-- -----------------------------------------------------------------------------
UPDATE violation_events ve
SET
  source_type = 'dvr_channel',
  dvr_channel_id = dc.channel_id
FROM dvr_channels dc
WHERE ve.company_id = dc.company_id
  AND ve.source_type IS NULL
  AND ve.dvr_channel_id IS NULL
  AND SUBSTRING(ve.camera_id FROM 1 FOR 4) = 'dvr_'
  AND dc.channel_id = SUBSTRING(ve.camera_id FROM 5);

-- -----------------------------------------------------------------------------
-- 3) Kalan açıkça IP kamera sayılanlar: '_ch' içermeyenler → camera
--    (_ch içeren ama eşleşmeyenler bilinçli olarak NULL bırakılır → doğrulamada yakalanır)
-- -----------------------------------------------------------------------------
UPDATE violation_events
SET
  source_type = 'camera',
  dvr_channel_id = NULL
WHERE source_type IS NULL
  AND dvr_channel_id IS NULL
  AND camera_id IS NOT NULL
  AND camera_id NOT LIKE '%_ch%';

-- -----------------------------------------------------------------------------
-- 4) Doğrulama — gate: prod’a PR3 öncesi sıfır veya kabul edilebilir eşik
-- -----------------------------------------------------------------------------

-- 4a) Hâlâ source_type atanmamış (inceleme / orphan adayı)
--     Beklenti: 0 (veya bilinen veri borcu listesi)
SELECT COUNT(*) AS violation_events_source_type_still_null
FROM violation_events
WHERE source_type IS NULL;

-- 4b) DVR etiketli ama FK kolonu boş (olmamalı)
SELECT COUNT(*) AS dvr_channel_rows_missing_fk
FROM violation_events
WHERE source_type = 'dvr_channel'
  AND (dvr_channel_id IS NULL OR dvr_channel_id = '');

-- 4c) dvr_channels’da karşılığı olmayan dvr_channel_id (orphan)
SELECT COUNT(*) AS dvr_orphan_fk
FROM violation_events ve
WHERE ve.source_type = 'dvr_channel'
  AND ve.dvr_channel_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1
    FROM dvr_channels dc
    WHERE dc.company_id = ve.company_id
      AND dc.channel_id = ve.dvr_channel_id
  );

-- 4d) DVR satırlarında dvr_channel_id doluluk oranı (payda: source_type = dvr_channel)
SELECT
  COUNT(*) FILTER (
    WHERE source_type = 'dvr_channel' AND dvr_channel_id IS NOT NULL
  ) AS dvr_rows_with_fk,
  COUNT(*) FILTER (WHERE source_type = 'dvr_channel') AS dvr_rows_total,
  ROUND(
    100.0 * COUNT(*) FILTER (
      WHERE source_type = 'dvr_channel' AND dvr_channel_id IS NOT NULL
    ) / NULLIF(COUNT(*) FILTER (WHERE source_type = 'dvr_channel'), 0),
    2
  ) AS dvr_fk_fill_pct
FROM violation_events;

-- 4e) PR3 readiness: getEvents SUBSTRING dalı hâlâ gerekli mi?
--     Aşağıdaki > 0 ise bazı satırlar hâlâ sadece camera_id + substring ile join oluyor demektir
--     (dvr_channel_id NULL veya eşleşmeyen eski veri).
SELECT COUNT(*) AS rows_needing_legacy_substring_join
FROM violation_events ve
WHERE ve.dvr_channel_id IS NULL
  AND SUBSTRING(ve.camera_id FROM 1 FOR 4) = 'dvr_'
  AND EXISTS (
    SELECT 1
    FROM dvr_channels dc
    WHERE dc.company_id = ve.company_id
      AND dc.channel_id = SUBSTRING(ve.camera_id FROM 5)
  );

-- 4f) '_ch' içeriyor, hâlâ NULL source_type (mutlaka inceleme)
SELECT event_id, company_id, camera_id, source_type, dvr_channel_id
FROM violation_events
WHERE source_type IS NULL
  AND camera_id LIKE '%_ch%';
