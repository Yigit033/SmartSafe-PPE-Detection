-- Soft Delete: companies tablosuna deleted_at kolonu ekle
-- Bu sayede silme işlemi geri alınabilir hale gelir
ALTER TABLE companies ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP DEFAULT NULL;

-- Performans: Soft delete sorguları için partial index
-- Sadece aktif (silinmemiş) kayıtlarda arama yapar, tam tablo taraması önlenir
CREATE INDEX IF NOT EXISTS idx_companies_active ON companies (company_id) WHERE deleted_at IS NULL;
