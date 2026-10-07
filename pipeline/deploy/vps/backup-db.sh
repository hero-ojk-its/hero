#!/usr/bin/env bash
# Cadangan harian database PostgreSQL HERO (+ arsip storage backend) ke Nextcloud.
#
# - Langkah 1: backend/deploy/backup.sh membuat dump di /var/backups/hero
#   (menyimpan 7 terakhir, gagal keras bila dump kosong).
# - Langkah 2: `rclone copy`, BUKAN sync, ke nc:HERO-Backup/db — berkas lama di
#   Nextcloud tidak pernah dihapus.
# - Kredensial: /opt/hero/rclone-nextcloud.conf (mode 600, root). Remote bernama `nc`.
#
# Dijalankan oleh hero-backup-db.timer (03:00). Bisa juga manual:
#   sudo /opt/hero/deploy/vps/backup-db.sh
set -uo pipefail

CONF=/opt/hero/rclone-nextcloud.conf
DEST="nc:HERO-Backup/db"
BACKUP_DIR=/var/backups/hero
LOG=/opt/hero/data/logs/backup-db.log

mkdir -p "$(dirname "$LOG")"
exec >>"$LOG" 2>&1
echo "===== backup-db $(date -Is) ====="

if [[ ! -f "$CONF" ]]; then
  echo "GAGAL: $CONF belum ada. Buat dengan: sudo rclone config --config $CONF"
  exit 2
fi

BACKUP_DIR="$BACKUP_DIR" /opt/hero/backend/deploy/backup.sh
rc=$?
if [[ $rc -ne 0 ]]; then
  echo "GAGAL: backup.sh exit $rc — tidak ada yang diunggah"
  echo "===== selesai $(date -Is) · exit $rc ====="
  exit $rc
fi

nice -n 19 ionice -c3 rclone --config "$CONF" copy --transfers 1 --bwlimit 5M \
  --retries 3 --low-level-retries 10 --stats 0 --log-level NOTICE \
  --include "hero_db_*.sql.gz" --include "hero_storage_*.tar.gz" \
  "$BACKUP_DIR" "$DEST"
rc=$?
echo "    unggah ke Nextcloud selesai (exit $rc)"
echo "===== selesai $(date -Is) · exit $rc ====="
exit $rc
