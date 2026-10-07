#!/usr/bin/env bash
# ==============================================================================
# HERO Backend - Uji Pemulihan (Restore Test) TANPA menyentuh data produksi
# ==============================================================================
# Memulihkan backup terbaru ke database sementara (hero_restore_test) dan folder
# sementara, lalu memverifikasi hasilnya. Database live & storage produksi TIDAK
# diubah, dan container backend tidak dihentikan.
#
# Penggunaan:
#   ./deploy/restore-test.sh                       # pakai backup terbaru
#   ./deploy/restore-test.sh <db.sql.gz> <storage.tar.gz>
#   ./deploy/restore-test.sh --keep                # jangan hapus database uji
# Variabel (opsional):
#   BACKUP_DIR (default /var/backups/hero), DB_CONTAINER (default hero_db)
# User dan database produksi dibaca dari environment di dalam container db.
# ==============================================================================
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/hero}"
DB_CONTAINER="${DB_CONTAINER:-hero_db}"
TEST_DB="hero_restore_test"
KEEP_DB=false
ARGS=()

for arg in "$@"; do
    case "$arg" in
        --keep) KEEP_DB=true ;;
        *) ARGS+=("$arg") ;;
    esac
done

# 1. Tentukan berkas backup
if [ "${#ARGS[@]}" -ge 2 ]; then
    DB_FILE="${ARGS[0]}"
    STORAGE_FILE="${ARGS[1]}"
else
    DB_FILE="$(ls -1t "${BACKUP_DIR}"/hero_db_*.sql.gz 2>/dev/null | head -n 1 || true)"
    STORAGE_FILE="$(ls -1t "${BACKUP_DIR}"/hero_storage_*.tar.gz 2>/dev/null | head -n 1 || true)"
fi

for f in "${DB_FILE:-}" "${STORAGE_FILE:-}"; do
    if [ -z "$f" ] || [ ! -f "$f" ]; then
        echo "ERROR: berkas backup tidak ditemukan: '${f:-<kosong>}'"
        exit 1
    fi
done

# Container database (docker exec langsung, tidak bergantung folder compose)
if ! docker ps --format '{{.Names}}' | grep -qx "${DB_CONTAINER}"; then
    echo "ERROR: container '${DB_CONTAINER}' tidak berjalan."
    exit 1
fi
POSTGRES_USER="$(docker exec "${DB_CONTAINER}" printenv POSTGRES_USER)"
POSTGRES_DB="$(docker exec "${DB_CONTAINER}" printenv POSTGRES_DB)"

db_exec() { docker exec -i "${DB_CONTAINER}" "$@"; }

psql_in_db() {
    db_exec psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER}" -d "$1" -tAc "$2"
}

echo "================================================================="
echo "UJI PEMULIHAN HERO (aman: tidak menyentuh database '${POSTGRES_DB}')"
echo "Berkas DB      : ${DB_FILE}"
echo "Berkas storage : ${STORAGE_FILE}"
echo "Database uji   : ${TEST_DB}"
echo "================================================================="

TMP_STORAGE="$(mktemp -d)"
cleanup() {
    rm -rf "${TMP_STORAGE}"
    if [ "${KEEP_DB}" != "true" ]; then
        db_exec psql -U "${POSTGRES_USER}" -d postgres -c "DROP DATABASE IF EXISTS ${TEST_DB};" >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

# 2. Pulihkan database ke TEST_DB
echo "--> 1/4 Membuat database uji..."
db_exec psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER}" -d postgres -c "DROP DATABASE IF EXISTS ${TEST_DB};" >/dev/null
db_exec psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER}" -d postgres -c "CREATE DATABASE ${TEST_DB};" >/dev/null

echo "--> 2/4 Memulihkan dump database..."
START_TS=$(date +%s)
gunzip -c "${DB_FILE}" | db_exec psql -v ON_ERROR_STOP=1 -q -U "${POSTGRES_USER}" -d "${TEST_DB}" >/dev/null
END_TS=$(date +%s)
echo "    Selesai dalam $((END_TS - START_TS)) detik."

# 3. Verifikasi database
echo "--> 3/4 Verifikasi database..."
TABLE_COUNT=$(psql_in_db "${TEST_DB}" "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE';")
ORIG_TABLE_COUNT=$(psql_in_db "${POSTGRES_DB}" "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE';" 2>/dev/null || echo "?")
ALEMBIC_VER=$(psql_in_db "${TEST_DB}" "SELECT version_num FROM alembic_version;" 2>/dev/null || echo "(tidak ada tabel alembic_version)")
echo "    Jumlah tabel (uji)      : ${TABLE_COUNT}"
echo "    Jumlah tabel (produksi) : ${ORIG_TABLE_COUNT}"
echo "    Versi migrasi Alembic   : ${ALEMBIC_VER}"

# Tampilkan jumlah baris per tabel untuk dibandingkan dengan produksi
echo "    Jumlah baris per tabel:"
psql_in_db "${TEST_DB}" "SELECT relname || ' = ' || n_live_tup FROM pg_stat_user_tables ORDER BY relname;" | sed 's/^/      /'

# 4. Verifikasi storage
echo "--> 4/4 Verifikasi storage..."
tar -xzf "${STORAGE_FILE}" -C "${TMP_STORAGE}"
ARCHIVE_ENTRIES=$(tar -tzf "${STORAGE_FILE}" | grep -v '/$' | wc -l | tr -d ' ')
EXTRACTED_FILES=$(find "${TMP_STORAGE}" -type f | wc -l | tr -d ' ')
STORAGE_SIZE=$(du -sh "${TMP_STORAGE}" | cut -f1)
echo "    Berkas di arsip : ${ARCHIVE_ENTRIES}"
echo "    Berkas terekstrak: ${EXTRACTED_FILES} (ukuran ${STORAGE_SIZE})"

echo "================================================================="
if [ "${ARCHIVE_ENTRIES}" = "${EXTRACTED_FILES}" ] && [ "${TABLE_COUNT}" -gt 0 ]; then
    echo "HASIL: LULUS. Database dan storage dapat dipulihkan."
else
    echo "HASIL: GAGAL. Periksa output di atas."
    exit 1
fi
if [ "${KEEP_DB}" = "true" ]; then
    echo "Database uji '${TEST_DB}' dibiarkan (--keep). Hapus manual bila sudah tidak dipakai."
fi
echo "Catatan: waktu pemulihan database di atas adalah perkiraan RTO."
echo "================================================================="
