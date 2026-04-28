-- Add debug metadata payload for violation event explainability.
--
-- Goal: Store "why this event was created" details inside the DB row so UI can
-- show it (instead of relying on ephemeral logs).
--
-- Column: debug_meta JSONB (nullable; can be empty).
-- Idempotent: safe to run multiple times.

DO $$
BEGIN
  IF to_regclass('public.violation_events') IS NULL THEN
    RETURN;
  END IF;

  ALTER TABLE violation_events
    ADD COLUMN IF NOT EXISTS debug_meta JSONB;
END $$;

