#!/usr/bin/env bash
set -euo pipefail

echo "==> Menjalankan migrasi database Alembic..."
alembic upgrade head

APP_PORT="${APP_PORT:-8000}"
UVICORN_WORKERS="${UVICORN_WORKERS:-1}"
FORWARDED_ALLOW_IPS="${FORWARDED_ALLOW_IPS:-127.0.0.1}"

echo "==> Menjalankan server HERO Backend Uvicorn pada port ${APP_PORT} dengan ${UVICORN_WORKERS} worker..."
exec python -m uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${APP_PORT}" \
    --workers "${UVICORN_WORKERS}" \
    --proxy-headers \
    --forwarded-allow-ips="${FORWARDED_ALLOW_IPS}"
