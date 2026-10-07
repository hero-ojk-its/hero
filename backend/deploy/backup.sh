#!/usr/bin/env bash
# ==============================================================================
# HERO Backend - Skrip Backup Database & Storage
# ==============================================================================
# Penggunaan:
#   ./deploy/backup.sh
# Di VPS dijadwalkan oleh hero-backup-db.timer (lihat pipeline/deploy/vps/backup-db.sh).
#
# Container dipanggil langsung dengan `docker exec` (bukan `docker compose`), jadi
# skrip bisa dijalankan dari folder mana pun. Nama user dan database dibaca dari
# environment DI DALAM container db, tidak perlu diketahui di sini.
#
# Variabel (opsional):
#   BACKUP_DIR (default /var/backups/hero), DB_CONTAINER (default hero_db),
#   BACKEND_CONTAINER (default hero_backend), STORAGE_PATH (default /app/storage),
#   STORAGE_DIR (jika diisi: arsipkan folder lokal ini, bukan dari container),
#   KEEP (jumlah backup disimpan, default 7)
# ==============================================================================
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/hero}"
DB_CONTAINER="${DB_CONTAINER:-hero_db}"
BACKEND_CONTAINER="${BACKEND_CONTAINER:-hero_backend}"
STORAGE_PATH="${STORAGE_PATH:-/app/storage}"
STORAGE_DIR="${STORAGE_DIR:-}"
KEEP="${KEEP:-7}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

mkdir -p "${BACKUP_DIR}"

DB_BACKUP_FILE="${BACKUP_DIR}/hero_db_${TIMESTAMP}.sql.gz"
STORAGE_BACKUP_FILE="${BACKUP_DIR}/hero_storage_${TIMESTAMP}.tar.gz"

# Berkas sementara dibuang bila skrip gagal, supaya tidak ada backup setengah jadi
# (atau kosong) yang tampak seperti backup sah.
cleanup() { rm -f -- "${DB_BACKUP_FILE}.tmp" "${STORAGE_BACKUP_FILE}.tmp"; }
trap cleanup EXIT

echo "================================================================="
echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Memulai proses backup HERO..."
echo "Direktori tujuan: ${BACKUP_DIR}"
echo "================================================================="

if ! docker ps --format '{{.Names}}' | grep -qx "${DB_CONTAINER}"; then
    echo "ERROR: container '${DB_CONTAINER}' tidak berjalan." >&2
    exit 1
fi

# 1. Backup Database PostgreSQL
echo "--> 1/3 Dump database (di dalam container ${DB_CONTAINER})..."
docker exec "${DB_CONTAINER}" sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
    | gzip > "${DB_BACKUP_FILE}.tmp"
# Dump sungguhan selalu jauh lebih besar dari gzip kosong (20 byte) dan memuat DDL.
if ! gunzip -c "${DB_BACKUP_FILE}.tmp" | head -c 1048576 | grep -q "PostgreSQL database dump"; then
    echo "ERROR: dump database kosong atau tidak valid." >&2
    exit 1
fi
mv -- "${DB_BACKUP_FILE}.tmp" "${DB_BACKUP_FILE}"
echo "    Database berhasil dibackup: ${DB_BACKUP_FILE} ($(du -h "${DB_BACKUP_FILE}" | cut -f1))"

# 2. Backup Berkas Storage
echo "--> 2/3 Mengarsipkan storage..."
if [ -n "${STORAGE_DIR}" ]; then
    tar -czf "${STORAGE_BACKUP_FILE}.tmp" -C "${STORAGE_DIR}" .
else
    docker exec "${BACKEND_CONTAINER}" tar -czf - -C "${STORAGE_PATH}" . > "${STORAGE_BACKUP_FILE}.tmp"
fi
tar -tzf "${STORAGE_BACKUP_FILE}.tmp" >/dev/null   # arsip harus bisa dibaca utuh
mv -- "${STORAGE_BACKUP_FILE}.tmp" "${STORAGE_BACKUP_FILE}"
echo "    Storage berhasil dibackup: ${STORAGE_BACKUP_FILE} ($(du -h "${STORAGE_BACKUP_FILE}" | cut -f1))"

# 3. Rotasi Backup (simpan ${KEEP} terakhir untuk tiap jenis)
echo "--> 3/3 Rotasi backup (menyimpan ${KEEP} arsip terakhir)..."
for pattern in "hero_db_*.sql.gz" "hero_storage_*.tar.gz"; do
    find "${BACKUP_DIR}" -maxdepth 1 -name "${pattern}" -type f -printf "%T@ %p\n" 2>/dev/null \
        | sort -nr | tail -n +"$((KEEP + 1))" | cut -d' ' -f2- \
        | while IFS= read -r old_file; do rm -f -- "${old_file}"; done
done

echo "================================================================="
echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Backup selesai dengan sukses!"
echo "Berkas tersimpan:"
echo "  - DB:      ${DB_BACKUP_FILE}"
echo "  - Storage: ${STORAGE_BACKUP_FILE}"
echo "================================================================="
