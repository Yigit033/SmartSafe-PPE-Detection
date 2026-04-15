-- Active detections state table
-- Used by Core to persist "currently running detections" across processes.
-- Keep schema minimal + indexed; Core performs upserts by camera_key.

CREATE TABLE IF NOT EXISTS active_detections (
    camera_key VARCHAR(255) PRIMARY KEY,
    company_id VARCHAR(255) NOT NULL,
    camera_id VARCHAR(255) NOT NULL,
    detection_mode VARCHAR(50) DEFAULT 'ppe',
    confidence_threshold DECIMAL(5,3) DEFAULT 0.500,
    status BOOLEAN DEFAULT TRUE,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (company_id) REFERENCES companies (company_id) ON DELETE CASCADE
);

-- Fast lookups for dashboard polling.
CREATE INDEX IF NOT EXISTS idx_active_detections_company_status
    ON active_detections(company_id, status);

CREATE INDEX IF NOT EXISTS idx_active_detections_camera_id
    ON active_detections(camera_id);

