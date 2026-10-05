#!/usr/bin/env bash
# ==============================================================================
# HERO Backend - Skrip Backup Otomatis Database & Storage
# ==============================================================================
# Penggunaan:
#   ./deploy/backup.sh
# Atau dijadwalkan via cron:
#   0 2 * * * /path/to/hero-backend/deploy/backup.sh >> /var/log/hero-backup.log 2>&1
# ==============================================================================
set -euo pipefail

# 1. Konfigurasi direktori dan variabel
BACKUP_DIR="${BACKUP_DIR:-/var/backups/hero}"
STORAGE_DIR="${STORAGE_DIR:-./storage}"
POSTGRES_USER="${POSTGRES_USER:-hero_user}"
POSTGRES_DB="${POSTGRES_DB:-hero_db}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

mkdir -p "${BACKUP_DIR}"

DB_BACKUP_FILE="${BACKUP_DIR}/hero_db_${TIMESTAMP}.sql.gz"
STORAGE_BACKUP_FILE="${BACKUP_DIR}/hero_storage_${TIMESTAMP}.tar.gz"

echo "================================================================="
echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Memulai proses backup HERO..."
echo "Direktori tujuan: ${BACKUP_DIR}"
echo "================================================================="

# 2. Backup Database PostgreSQL
echo "--> 1/3 Melakukan dump database '${POSTGRES_DB}'..."
db_status=$(docker compose ps db 2>/dev/null || true)
db_prod_status=$(docker compose -f docker-compose.yml -f docker-compose.prod.yml ps db 2>/dev/null || true)

if echo "${db_status}" | grep -E "Up|running" >/dev/null 2>&1; then
    docker compose exec -T db pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" | gzip > "${DB_BACKUP_FILE}"
elif echo "${db_prod_status}" | grep -E "Up|running" >/dev/null 2>&1; then
    docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T db pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" | gzip > "${DB_BACKUP_FILE}"
else
    echo "PERINGATAN: Container database tidak aktif melalui compose default. Mencoba pg_dump langsung..."
    pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" | gzip > "${DB_BACKUP_FILE}"
fi
echo "    Database berhasil dibackup: ${DB_BACKUP_FILE}"

# 3. Backup Berkas Storage
echo "--> 2/3 Mengarsipkan direktori storage '${STORAGE_DIR}'..."
if [ -d "${STORAGE_DIR}" ]; then
    tar -czf "${STORAGE_BACKUP_FILE}" -C "${STORAGE_DIR}" .
    echo "    Storage berhasil dibackup: ${STORAGE_BACKUP_FILE}"
else
    echo "    Direktori ${STORAGE_DIR} belum ada, membuat arsip kosong..."
    tar -czf "${STORAGE_BACKUP_FILE}" --files-from /dev/null
fi

# 4. Rotasi Backup (Simpan 7 backup terakhir)
echo "--> 3/3 Memeriksa rotasi backup (menyimpan 7 arsip terakhir)..."
# Hapus backup DB lama lebih dari 7 file terbaru
while IFS= read -r old_file; do
    if [ -n "${old_file}" ] && [ -f "${old_file}" ]; then
        rm -f -- "${old_file}"
    fi
done < <(find "${BACKUP_DIR}" -maxdepth 1 -name "hero_db_*.sql.gz" -type f -printf "%T@ %p\n" 2>/dev/null | sort -nr | tail -n +8 | awk '{print $2}' || true)

# Hapus backup Storage lama lebih dari 7 file terbaru
while IFS= read -r old_file; do
    if [ -n "${old_file}" ] && [ -f "${old_file}" ]; then
        rm -f -- "${old_file}"
    fi
done < <(find "${BACKUP_DIR}" -maxdepth 1 -name "hero_storage_*.tar.gz" -type f -printf "%T@ %p\n" 2>/dev/null | sort -nr | tail -n +8 | awk '{print $2}' || true)

echo "================================================================="
echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Backup selesai dengan sukses!"
echo "Berkas tersimpan:"
echo "  - DB:      ${DB_BACKUP_FILE}"
echo "  - Storage: ${STORAGE_BACKUP_FILE}"
echo "================================================================="
