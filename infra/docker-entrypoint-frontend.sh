#!/usr/bin/env sh
# SmartSafe Frontend Entrypoint
set -eu

cd /app

# Yeni kütüphaneleri kontrol et ve yükle
echo "📦 Checking for new dependencies..."
npm install --no-audit --no-fund

# Uygulamayı başlat
echo "🚀 Starting Frontend..."
exec npx next dev --webpack --hostname 0.0.0.0 --port 3377
