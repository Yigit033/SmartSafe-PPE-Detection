-- PR3 Contract: violation_events — DVR satırlarında camera_id temizliği, CHECK, NOT NULL, partial index.
--
-- ÖNKOŞUL: PR2 backfill tamamlanmış olmalı (source_type NULL olmamalı).
--
-- Deploy sırası (kritik): Önce core/backend’i DVR için camera_id = NULL yazacak sürüme yükseltin,
-- ardından bu migration’ı uygulayın. Eski sürüm CHECK eklenmiş DB’ye hem camera_id hem
-- dvr_channel_id yazmaya çalışırsa INSERT başarısız olur.

DO $$
BEGIN
  IF to_regclass('public.violation_events') IS NULL THEN
    RETURN;
  END IF;
  IF EXISTS (SELECT 1 FROM violation_events WHERE source_type IS NULL LIMIT 1) THEN
    RAISE EXCEPTION 'PR2 backfill required: violation_events.source_type IS NULL rows exist';
  END IF;
END $$;

UPDATE violation_events
SET camera_id = NULL
WHERE source_type = 'dvr_channel';

ALTER TABLE violation_events
  ALTER COLUMN source_type SET NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'violation_events_source_shape_chk'
  ) THEN
    ALTER TABLE violation_events
      ADD CONSTRAINT violation_events_source_shape_chk CHECK (
        (source_type = 'camera' AND camera_id IS NOT NULL AND dvr_channel_id IS NULL)
        OR
        (source_type = 'dvr_channel' AND dvr_channel_id IS NOT NULL AND camera_id IS NULL)
      );
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_violation_events_active_camera
  ON violation_events (company_id, start_time DESC)
  WHERE source_type = 'camera' AND status = 'active';

CREATE INDEX IF NOT EXISTS idx_violation_events_active_dvr
  ON violation_events (company_id, dvr_channel_id, start_time DESC)
  WHERE source_type = 'dvr_channel' AND status = 'active';

-- Post-deploy doğrulama: core/scripts/database/verify_violation_events_post_pr3.sql
