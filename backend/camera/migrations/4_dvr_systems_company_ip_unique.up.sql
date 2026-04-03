-- One physical NVR IP per tenant: prevents duplicate dvr_systems rows that break RTSP cache resolution.
-- If this fails, remove duplicate (company_id, ip_address) pairs first, then re-run migrations.
CREATE UNIQUE INDEX IF NOT EXISTS dvr_systems_company_id_ip_address_key
  ON dvr_systems (company_id, ip_address);
