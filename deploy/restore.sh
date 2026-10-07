#!/usr/bin/env bash
# ==============================================================================
# HERO Backend - Skrip Restore Database & Storage (PRODUKSI, DESTRUKTIF)
# ==============================================================================
# Menimpa database dan storage produksi. Jalankan HANYA setelah deploy/restore-test.sh
# lulus untuk berkas yang sama.
#
# Penggunaan:
#   ./deploy/restore.sh <berkas_db.sql.gz> <berkas_storage.tar.gz> [--yes]
# Contoh:
#   ./deploy/restore.sh /var/backups/hero/hero_db_20260928_120000.sql.gz /var/backups/hero/hero_storage_20260928_120000.tar.gz
# Variabel (opsional, sama dengan backup.sh):
#   DB_CONTAINER (default hero_db), BACKEND_CONTAINER (default hero_backend),
#   STORAGE_PATH (default /app/storage)
# ==============================================================================
set -euo pipefail

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

DB_CONTAINER="${DB_CONTAINER:-hero_db}"
BACKEND_CONTAINER="${BACKEND_CONTAINER:-hero_backend}"
STORAGE_PATH="${STORAGE_PATH:-/app/storage}"

for f in "${DB_FILE}" "${STORAGE_FILE}"; do
    if [ ! -f "${f}" ]; then
        echo "ERROR: berkas '${f}' tidak ditemukan!"
        exit 1
    fi
done

if ! docker ps --format '{{.Names}}' | grep -qx "${DB_CONTAINER}"; then
    echo "ERROR: container '${DB_CONTAINER}' tidak berjalan."
    exit 1
fi
# User dan database dibaca dari environment container db (tidak perlu diketahui di sini)
POSTGRES_USER="$(docker exec "${DB_CONTAINER}" printenv POSTGRES_USER)"
POSTGRES_DB="$(docker exec "${DB_CONTAINER}" printenv POSTGRES_DB)"

echo "================================================================="
echo "PERINGATAN RESTORE SISTEM HERO BACKEND"
echo "================================================================="
echo "Database yang akan ditimpa : ${POSTGRES_DB} (schema public dikosongkan dulu)"
echo "Berkas DB Sumber           : ${DB_FILE}"
echo "Berkas Storage Sumber      : ${STORAGE_FILE}"
echo "Target storage             : ${BACKEND_CONTAINER}:${STORAGE_PATH}"
echo "================================================================="

if [ "${AUTO_CONFIRM}" != "true" ]; then
    read -r -p "Apakah Anda yakin ingin memulihkan data ini? Semua data saat ini akan DITIMPA! (ketik 'ya' untuk melanjutkan): " CONFIRM
    if [ "${CONFIRM}" != "ya" ] && [ "${CONFIRM}" != "y" ] && [ "${CONFIRM}" != "yes" ]; then
        echo "Operasi restore dibatalkan oleh pengguna."
        exit 0
    fi
fi

# 1. Hentikan backend agar tidak ada penulisan saat restore
echo "--> 1/4 Menghentikan container backend..."
docker stop "${BACKEND_CONTAINER}" >/dev/null 2>&1 || true

# 2. Restore database. Schema public dikosongkan dulu supaya dump tidak bertabrakan
#    dengan tabel yang sudah ada.
echo "--> 2/4 Memulihkan database '${POSTGRES_DB}'..."
docker exec -i "${DB_CONTAINER}" psql -v ON_ERROR_STOP=1 -q -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
    -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;" >/dev/null
gunzip -c "${DB_FILE}" | docker exec -i "${DB_CONTAINER}" psql -v ON_ERROR_STOP=1 -q -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" >/dev/null
echo "    Database berhasil dipulihkan."

# 3. Restore storage. Container backend dalam keadaan berhenti, jadi volume-nya
#    diakses lewat --volumes-from memakai image yang sama.
echo "--> 3/4 Memulihkan berkas storage ke ${STORAGE_PATH}..."
BACKEND_IMAGE="$(docker inspect -f '{{.Config.Image}}' "${BACKEND_CONTAINER}")"
docker run --rm -i --volumes-from "${BACKEND_CONTAINER}" --entrypoint tar "${BACKEND_IMAGE}" \
    -xzf - -C "${STORAGE_PATH}" < "${STORAGE_FILE}"
echo "    Storage berhasil diekstrak."

# 4. Jalankan kembali backend. Migrasi Alembic dijalankan saat backend start.
echo "--> 4/4 Menjalankan kembali container backend..."
docker start "${BACKEND_CONTAINER}" >/dev/null

echo "================================================================="
echo "Restore selesai. Periksa status kesehatan via /health."
echo "================================================================="
