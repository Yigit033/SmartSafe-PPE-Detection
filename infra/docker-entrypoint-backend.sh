#!/usr/bin/env bash
# Encore Entrypoint — LF satır sonu ile kaydedilmeli (Dockerfile'da sed ile temizleniyor)
set -eu
export PATH="/root/.encore/bin:$PATH"
cd /app
node ./scripts/encore-sync-if-needed.cjs || true

# Bağımlılıkları kontrol et ve yükle
echo "📦 Checking for backend dependencies..."
npm install --no-audit --no-fund

# Veritabanı migrasyonlarını otomatik olarak çalıştır
echo "🗄️ Running database migrations..."
node ./scripts/migrate.cjs || true

# Encore'u 4477 portunda tüm arayüzlerde dinleyecek şekilde başlat
echo "🚀 Starting Backend (Encore)..."
exec encore run --listen 0.0.0.0:4477
