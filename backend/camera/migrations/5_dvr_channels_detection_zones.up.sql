-- ROI / analiz bölgesi: DVR kanalları cameras tablosunda değil; dvr_channels üzerinde tutulur.
ALTER TABLE dvr_channels ADD COLUMN IF NOT EXISTS detection_zones JSONB DEFAULT '[]'::jsonb;
