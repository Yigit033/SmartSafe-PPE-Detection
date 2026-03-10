-- Create camera_groups table
CREATE TABLE IF NOT EXISTS camera_groups (
    group_id VARCHAR(255) PRIMARY KEY,
    company_id VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    location VARCHAR(255),
    group_type VARCHAR(50) DEFAULT 'general',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Add group_id to cameras table
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS group_id VARCHAR(255);

-- Create index for group lookup
CREATE INDEX IF NOT EXISTS idx_cameras_group_id ON cameras(group_id);
CREATE INDEX IF NOT EXISTS idx_camera_groups_company_id ON camera_groups(company_id);
