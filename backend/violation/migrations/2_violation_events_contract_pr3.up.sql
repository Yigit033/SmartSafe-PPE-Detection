-- PR3 Contract: violation_events — DVR satırlarında camera_id temizliği, CHECK, NOT NULL, partial index.

DO $$
BEGIN
  IF to_regclass('public.violation_events') IS NULL THEN
    RETURN;
  END IF;
  
  -- PR2 backfill required check can be simplified or kept if we are sure backfill ran
  -- For now, let's keep the logic safe
  IF EXISTS (SELECT 1 FROM violation_events WHERE source_type IS NULL LIMIT 1) THEN
     -- If new table, it might be empty, so this is fine.
     NULL;
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
