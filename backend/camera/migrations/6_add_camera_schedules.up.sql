-- Kameralar için otomatik çalışma çizelgesi tablosu
CREATE TABLE IF NOT EXISTS camera_schedules (
    id SERIAL PRIMARY KEY,
    company_id VARCHAR(255) NOT NULL,
    camera_id VARCHAR(255) NOT NULL,
    camera_type VARCHAR(50) DEFAULT 'ip_camera', -- 'ip_camera' veya 'dvr_channel'
    day_of_week INTEGER NOT NULL, -- 0: Pazar, 1: Pzt, ..., 6: Cmt, 7: Her Gün
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    is_enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (company_id) REFERENCES companies (company_id) ON DELETE CASCADE
);

-- Hızlı sorgulama için indeksler
CREATE INDEX IF NOT EXISTS idx_camera_schedules_company ON camera_schedules(company_id);
CREATE INDEX IF NOT EXISTS idx_camera_schedules_lookup ON camera_schedules(camera_id, is_enabled);
