-- =============================================================================
-- violation_events — PR3 sonrası doğrulama (PostgreSQL, salt okunur)
-- =============================================================================
-- Çalıştır: psql "$DATABASE_URL" -f verify_violation_events_post_pr3.sql
-- Beklenti: aşağıdaki sayaçlar 0; CHECK / index varlığı doğrulanır.
-- =============================================================================

-- Constraint var mı?
SELECT conname
FROM pg_constraint
WHERE conrelid = 'public.violation_events'::regclass
  AND conname IN (
    'violation_events_source_shape_chk',
    'violation_events_dvr_channel_id_fkey'
  )
ORDER BY conname;

-- Eski cameras FK kalmamalı (PR1 güncel migration ile kaldırılır)
SELECT COUNT(*) AS legacy_violation_events_camera_id_fkey_present
FROM pg_constraint
WHERE conrelid = 'public.violation_events'::regclass
  AND conname = 'violation_events_camera_id_fkey';

-- source_type NULL (olmamalı)
SELECT COUNT(*) AS source_type_null_count
FROM violation_events
WHERE source_type IS NULL;

-- DVR satırında camera_id dolu (olmamalı)
SELECT COUNT(*) AS dvr_rows_with_camera_id
FROM violation_events
WHERE source_type = 'dvr_channel' AND camera_id IS NOT NULL;

-- Kamera satırında dvr_channel_id dolu (olmamalı)
SELECT COUNT(*) AS camera_rows_with_dvr_fk
FROM violation_events
WHERE source_type = 'camera' AND dvr_channel_id IS NOT NULL;

-- Kamera satırında camera_id boş (olmamalı)
SELECT COUNT(*) AS camera_rows_missing_camera_id
FROM violation_events
WHERE source_type = 'camera' AND (camera_id IS NULL OR camera_id = '');

-- DVR satırında dvr_channel_id boş (olmamalı)
SELECT COUNT(*) AS dvr_rows_missing_channel_fk
FROM violation_events
WHERE source_type = 'dvr_channel'
  AND (dvr_channel_id IS NULL OR dvr_channel_id = '');

-- Orphan dvr_channel_id
SELECT COUNT(*) AS dvr_orphan_fk
FROM violation_events ve
WHERE ve.source_type = 'dvr_channel'
  AND ve.dvr_channel_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM dvr_channels dc
    WHERE dc.company_id = ve.company_id
      AND dc.channel_id = ve.dvr_channel_id
  );

-- Partial index (isim bazlı)
SELECT indexname
FROM pg_indexes
WHERE tablename = 'violation_events'
  AND indexname IN (
    'idx_violation_events_active_camera',
    'idx_violation_events_active_dvr' 
  )
ORDER BY indexname;
