#!/bin/sh
set -e

echo "==> Menjalankan migrasi database Alembic..."
alembic upgrade head

echo "==> Menjalankan server HERO Backend Uvicorn..."
exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
