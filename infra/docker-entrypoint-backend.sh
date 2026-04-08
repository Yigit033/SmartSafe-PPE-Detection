#!/usr/bin/env bash
# Encore CLI sürümünü package.json / bind mount ile hizalar; manuel `encore version update` gerekmez.
set -eu
export PATH="/root/.encore/bin:$PATH"
cd /app
if ! encore version update; then
  echo "[smartsafe-backend] encore version update başarısız (ağ kapalı olabilir); mevcut CLI ile devam." >&2
fi
exec /root/.encore/bin/encore run --listen 0.0.0.0:4000
