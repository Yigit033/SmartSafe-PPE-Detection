-- Soft Delete: users tablosuna deleted_at kolonu ekle
-- Bu sayede kullanıcı silme işlemi geri alınabilir hale gelir
ALTER TABLE users ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP DEFAULT NULL;

-- Performans: Soft delete sorguları için partial index
CREATE INDEX IF NOT EXISTS idx_users_active ON users (user_id) WHERE deleted_at IS NULL;

-- Login sorguları için email + aktif kullanıcı indexi
CREATE INDEX IF NOT EXISTS idx_users_email_active ON users (email) WHERE deleted_at IS NULL;
