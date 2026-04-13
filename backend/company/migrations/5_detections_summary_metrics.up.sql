-- Core periodic detection summary: public.detections columns used by add_camera_detection_result.
-- No-op if table missing (Core may create it later; database_adapter ensure_schema also adds these).

DO $$
BEGIN
  IF to_regclass('public.detections') IS NULL THEN
    RETURN;
  END IF;
  ALTER TABLE detections ADD COLUMN IF NOT EXISTS compliance_rate DECIMAL(5,2);
  ALTER TABLE detections ADD COLUMN IF NOT EXISTS processing_time_ms DECIMAL(12,3);
END $$;
