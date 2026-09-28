#!/usr/bin/env bash
# ==============================================================================
# HERO Backend - Skrip Restore Database & Storage
# ==============================================================================
# Penggunaan:
#   ./deploy/restore.sh <berkas_db.sql.gz> <berkas_storage.tar.gz> [--yes]
# Contoh:
#   ./deploy/restore.sh /var/backups/hero/hero_db_20260928_120000.sql.gz /var/backups/hero/hero_storage_20260928_120000.tar.gz
# ==============================================================================
set -euo pipefail

# 1. Parsing argumen
if [ "$#" -lt 2 ]; then
    echo "Penggunaan: $0 <berkas_db.sql.gz> <berkas_storage.tar.gz> [--yes]"
    exit 1
fi

DB_FILE="$1"
STORAGE_FILE="$2"
AUTO_CONFIRM=false

for arg in "$@"; do
    if [ "$arg" = "--yes" ] || [ "$arg" = "-y" ]; then
        AUTO_CONFIRM=true
    fi
done

if [ ! -f "${DB_FILE}" ]; then
    echo "ERROR: Berkas database '${DB_FILE}' tidak ditemukan!"
    exit 1
fi

if [ ! -f "${STORAGE_FILE}" ]; then
    echo "ERROR: Berkas storage '${STORAGE_FILE}' tidak ditemukan!"
    exit 1
fi

STORAGE_DIR="${STORAGE_DIR:-./storage}"
POSTGRES_USER="${POSTGRES_USER:-hero_user}"
POSTGRES_DB="${POSTGRES_DB:-hero_db}"

echo "================================================================="
echo "PERINGATAN RESTORE SISTEM HERO BACKEND"
echo "================================================================="
echo "Database yang akan ditimpa : ${POSTGRES_DB}"
echo "Berkas DB Sumber           : ${DB_FILE}"
echo "Direktori Storage Target   : ${STORAGE_DIR}"
echo "Berkas Storage Sumber      : ${STORAGE_FILE}"
echo "================================================================="

if [ "${AUTO_CONFIRM}" != "true" ]; then
    read -r -p "Apakah Anda yakin ingin memulihkan data ini? Semua data saat ini akan DITIMPA! (ketik 'ya' untuk melanjutkan): " CONFIRM
    if [ "${CONFIRM}" != "ya" ] && [ "${CONFIRM}" != "y" ] && [ "${CONFIRM}" != "yes" ]; then
        echo "Operasi restore dibatalkan oleh pengguna."
        exit 0
    fi
fi

# 2. Hentikan container backend sementara untuk konsistensi data
echo "--> 1/5 Menghentikan container backend..."
docker compose stop backend 2>/dev/null || docker compose -f docker-compose.yml -f docker-compose.prod.yml stop backend 2>/dev/null || true

# 3. Restore Database
echo "--> 2/5 Memulihkan database '${POSTGRES_DB}' dari ${DB_FILE}..."
db_status=$(docker compose ps db 2>/dev/null || true)
db_prod_status=$(docker compose -f docker-compose.yml -f docker-compose.prod.yml ps db 2>/dev/null || true)

if echo "${db_status}" | grep -E "Up|running" >/dev/null 2>&1; then
    gunzip -c "${DB_FILE}" | docker compose exec -T db psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}"
elif echo "${db_prod_status}" | grep -E "Up|running" >/dev/null 2>&1; then
    gunzip -c "${DB_FILE}" | docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T db psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}"
else
    gunzip -c "${DB_FILE}" | psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}"
fi
echo "    Database berhasil dipulihkan."

# 4. Restore Storage
echo "--> 3/5 Memulihkan berkas storage ke '${STORAGE_DIR}'..."
mkdir -p "${STORAGE_DIR}"
tar -xzf "${STORAGE_FILE}" -C "${STORAGE_DIR}"
echo "    Storage berhasil diekstrak."

# 5. Jalankan migrasi Alembic (bila ada migrasi skema yang tertinggal)
echo "--> 4/5 Memeriksa dan menjalankan migrasi skema database..."
if docker compose run --rm backend alembic upgrade head 2>/dev/null; then
    echo "    Alembic upgrade head berhasil."
else
    alembic upgrade head || echo "    (Alembic dijalankan di container saat backend start)"
fi

# 6. Menjalankan kembali backend
echo "--> 5/5 Menjalankan kembali container backend..."
docker compose start backend 2>/dev/null || docker compose -f docker-compose.yml -f docker-compose.prod.yml start backend 2>/dev/null || true

echo "================================================================="
echo "Restore selesai dengan sukses! Silakan periksa status kesehatan via /health."
echo "================================================================="
