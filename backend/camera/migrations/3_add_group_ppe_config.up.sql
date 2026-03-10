-- Add ppe_config column to camera_groups
ALTER TABLE camera_groups ADD COLUMN IF NOT EXISTS ppe_config JSONB DEFAULT '{}';
