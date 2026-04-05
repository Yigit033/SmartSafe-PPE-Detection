-- PR1 Expand: violation_events — source_type, dvr_channel_id (FK), camera_id nullable.
-- Strategy A (PR1–PR2): DVR satırlarında geçici olarak camera_id doldurulabilir; PR3’te NULL olur.
--
-- cameras(camera_id) FK: DVR kanal id’leri cameras’ta olmayabilir (shadow yok). Orphan kontrolü
-- (violation_events.camera_id LEFT JOIN cameras → 0 satır) sonrası güvenle kaldırılır.

DO $$
BEGIN
  IF to_regclass('public.violation_events') IS NULL THEN
    RETURN;
  END IF;
  ALTER TABLE violation_events DROP CONSTRAINT IF EXISTS violation_events_camera_id_fkey;
  ALTER TABLE violation_events ADD COLUMN IF NOT EXISTS source_type VARCHAR(20);
  ALTER TABLE violation_events ADD COLUMN IF NOT EXISTS dvr_channel_id VARCHAR(255);
  ALTER TABLE violation_events ALTER COLUMN camera_id DROP NOT NULL;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'violation_events_dvr_channel_id_fkey'
  ) THEN
    ALTER TABLE violation_events
      ADD CONSTRAINT violation_events_dvr_channel_id_fkey
      FOREIGN KEY (dvr_channel_id) REFERENCES dvr_channels (channel_id);
  END IF;
END $$;
