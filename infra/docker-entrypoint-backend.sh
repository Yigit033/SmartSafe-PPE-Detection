#!/usr/bin/env bash
# Encore Entrypoint — LF satır sonu ile kaydedilmeli (Dockerfile'da sed ile temizleniyor)
set -eu
export PATH="/root/.encore/bin:$PATH"
cd /app
node ./scripts/encore-sync-if-needed.cjs || true

# Encore'u 4477 portunda tüm arayüzlerde dinleyecek şekilde başlat
exec encore run --listen 0.0.0.0:4477
