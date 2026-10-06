#!/usr/bin/env bash
# Cadangan harian PDF HERO ke Nextcloud lewat WebDAV.
#
# - Sumber 1: PDF backend (volume docker hero_storage_data) — dokumen yang diunggah
# - Sumber 2: knowledge base lapisan data (/opt/hero/data/knowledge_base)
# - `rclone copy`, BUKAN sync: berkas yang sudah ada di Nextcloud tidak pernah dihapus.
# - Kredensial: /opt/hero/rclone-nextcloud.conf (mode 600, root). Remote bernama `nc`.
#
# Dijalankan oleh hero-backup-pdf.timer (03:30). Bisa juga manual:
#   sudo /opt/hero/deploy/vps/backup-pdf.sh
set -uo pipefail

CONF=/opt/hero/rclone-nextcloud.conf
DEST="nc:HERO-Backup"
LOG=/opt/hero/data/logs/backup-pdf.log
PDF_SRC=/var/lib/docker/volumes/hero_storage_data/_data
KB_SRC=/opt/hero/data/knowledge_base

mkdir -p "$(dirname "$LOG")"
exec >>"$LOG" 2>&1
echo "===== backup $(date -Is) ====="

if [[ ! -f "$CONF" ]]; then
  echo "GAGAL: $CONF belum ada. Buat dengan: sudo rclone config --config $CONF"
  exit 2
fi

RC=(rclone --config "$CONF" copy --transfers 2 --checkers 4 --bwlimit 5M \
   --retries 3 --low-level-retries 10 --stats 0 --log-level NOTICE)

rc_total=0
for pair in "$PDF_SRC|$DEST/pdf-backend" "$KB_SRC|$DEST/knowledge-base"; do
  src="${pair%%|*}"; dst="${pair##*|}"
  if [[ ! -d "$src" ]]; then
    echo "lewati: $src tidak ada"; continue
  fi
  echo "--- $src -> $dst"
  nice -n 19 ionice -c3 "${RC[@]}" "$src" "$dst"
  rc=$?
  echo "    selesai (exit $rc)"
  rc_total=$((rc_total | rc))
done

echo "===== selesai $(date -Is) · exit $rc_total ====="
exit $rc_total
