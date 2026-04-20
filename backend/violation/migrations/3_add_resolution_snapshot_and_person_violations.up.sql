-- Add optional schema pieces used by AI Core runtime:
-- 1) violation_events.resolution_snapshot_path (stored when a violation is resolved)
-- 2) person_violations table (monthly per-person violation stats)
--
-- Safe to run multiple times.

DO $$
BEGIN
  IF to_regclass('public.violation_events') IS NULL THEN
    RETURN;
  END IF;

  ALTER TABLE violation_events
    ADD COLUMN IF NOT EXISTS resolution_snapshot_path TEXT;
END $$;

CREATE TABLE IF NOT EXISTS person_violations (
  id SERIAL PRIMARY KEY,
  person_id TEXT NOT NULL,
  company_id TEXT NOT NULL,
  month TEXT NOT NULL,
  violation_type TEXT NOT NULL,
  violation_count INTEGER NOT NULL DEFAULT 0,
  total_duration_seconds INTEGER NOT NULL DEFAULT 0,
  penalty_amount NUMERIC DEFAULT 0,
  last_violation_date TIMESTAMP,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (person_id, company_id, month, violation_type)
);

