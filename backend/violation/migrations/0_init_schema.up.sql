CREATE TABLE IF NOT EXISTS violations (
    violation_id SERIAL PRIMARY KEY,
    company_id VARCHAR(255) NOT NULL,
    camera_id VARCHAR(255) NOT NULL,
    worker_id VARCHAR(255),
    missing_ppe VARCHAR(255) NOT NULL,
    violation_type VARCHAR(255) NOT NULL,
    confidence DECIMAL(5,2) DEFAULT 0,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (company_id) REFERENCES companies (company_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reports (
    report_id SERIAL PRIMARY KEY,
    company_id VARCHAR(255) NOT NULL,
    report_type VARCHAR(255) NOT NULL,
    report_data JSON NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (company_id) REFERENCES companies (company_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS alerts (
    alert_id SERIAL PRIMARY KEY,
    company_id VARCHAR(255) NOT NULL,
    camera_id VARCHAR(255),
    alert_type VARCHAR(255) NOT NULL,
    severity VARCHAR(50) NOT NULL,
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    status VARCHAR(50) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP,
    FOREIGN KEY (company_id) REFERENCES companies (company_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS detections (
    detection_id SERIAL PRIMARY KEY,
    company_id VARCHAR(255) NOT NULL,
    camera_id VARCHAR(255) NOT NULL,
    detection_type VARCHAR(255) NOT NULL,
    confidence DECIMAL(5,2) DEFAULT 0,
    people_detected INTEGER DEFAULT 0,
    ppe_compliant INTEGER DEFAULT 0,
    total_people INTEGER DEFAULT 0,
    violations_count INTEGER DEFAULT 0,
    compliance_rate DECIMAL(5,2),
    processing_time_ms DECIMAL(12,3),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (company_id) REFERENCES companies (company_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS dvr_detection_results (
    id SERIAL PRIMARY KEY,
    stream_id VARCHAR(255) NOT NULL,
    company_id VARCHAR(255) NOT NULL,
    total_people INTEGER DEFAULT 0,
    compliant_people INTEGER DEFAULT 0,
    violations_count INTEGER DEFAULT 0,
    missing_ppe TEXT,
    detection_confidence DECIMAL(5,2) DEFAULT 0.0,
    detection_time DECIMAL(10,4) DEFAULT 0.0,
    frame_timestamp TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dvr_detection_sessions (
    session_id VARCHAR(255) PRIMARY KEY,
    dvr_id VARCHAR(255) NOT NULL,
    company_id VARCHAR(255) NOT NULL,
    channels JSON NOT NULL,
    detection_mode VARCHAR(50) DEFAULT 'scheduled',
    status VARCHAR(50) DEFAULT 'active',
    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    end_time TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
