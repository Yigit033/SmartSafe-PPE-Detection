-- Convert violation_events.start_time / end_time from TIMESTAMP to DOUBLE PRECISION (unix epoch seconds).
--
-- Why: Both the Python AI core (core/database/database_adapter.py::add_violation_event) and
-- the Encore backend (backend/violation/violation.ts → ViolationEvent.start_time: number)
-- treat these columns as numeric unix epochs. The original init schema used TIMESTAMP
-- without time zone, which caused every INSERT from Core to fail with:
--
--   ERROR: column "start_time" is of type timestamp without time zone
--          but expression is of type numeric
--
-- Result: snapshot files were written to disk but violation_events stayed empty,
-- so the /violations page stayed empty too.
--
-- Idempotent: only runs ALTER when the columns are still TIMESTAMP.
-- Existing timestamp rows are preserved via EXTRACT(EPOCH FROM ...).

DO $$
BEGIN
  IF to_regclass('public.violation_events') IS NULL THEN
    RETURN;
  END IF;

  -- start_time → DOUBLE PRECISION
  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name  = 'violation_events'
      AND column_name = 'start_time'
      AND data_type   IN ('timestamp without time zone', 'timestamp with time zone')
  ) THEN
    ALTER TABLE violation_events
      ALTER COLUMN start_time DROP DEFAULT;

    ALTER TABLE violation_events
      ALTER COLUMN start_time TYPE DOUBLE PRECISION
      USING EXTRACT(EPOCH FROM start_time);
  END IF;

  -- end_time → DOUBLE PRECISION
  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name  = 'violation_events'
      AND column_name = 'end_time'
      AND data_type   IN ('timestamp without time zone', 'timestamp with time zone')
  ) THEN
    ALTER TABLE violation_events
      ALTER COLUMN end_time DROP DEFAULT;

    ALTER TABLE violation_events
      ALTER COLUMN end_time TYPE DOUBLE PRECISION
      USING EXTRACT(EPOCH FROM end_time);
  END IF;
END $$;

-- Reassert the ordered index on (company_id, start_time DESC) — it survives the type
-- change but listing it here documents the expected shape for operators.
CREATE INDEX IF NOT EXISTS idx_violation_events_company_time
  ON violation_events(company_id, start_time DESC);
