#!/usr/bin/env bash
# Encore CLI < package.json encore.dev ise `encore version update` (scripts/encore-sync-if-needed.cjs)
set -eu
export PATH="/root/.encore/bin:$PATH"
cd /app
node ./scripts/encore-sync-if-needed.cjs || true
exec /root/.encore/bin/encore run --listen 0.0.0.0:4000
