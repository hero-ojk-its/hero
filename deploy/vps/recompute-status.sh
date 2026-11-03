#!/usr/bin/env bash
# Perhitungan ulang status keberlakuan dokumen (Langkah 19, FR terkait status).
#
# Kenapa perlu terjadwal: status `berlaku` bergantung pada `effective_date` yang
# terlewati oleh kalender, BUKAN oleh aksi pengguna. Backend hanya menghitung
# ulang saat ada event (PATCH ekstraksi / koreksi metadata), jadi dokumen yang
# tanggal berlakunya lewat tanpa disentuh siapa pun akan nyangkut di status lama.
#
# Zona waktu: `date.today()` di dalam kontainer memakai TZ kontainer. Tanpa
# TZ eksplisit kontainer berjalan UTC, sehingga dokumen yang mulai berlaku
# 00:00 WIB baru terbaca 7 jam kemudian. Karena itu TZ dipaksa ke WIB di sini
# dan timer dijadwalkan pada zona yang sama.
#
# Dijalankan oleh hero-recompute-status.timer (00:10 WIB). Bisa juga manual:
#   sudo /opt/hero/ci/recompute-status.sh
#   sudo DRY_RUN=1 /opt/hero/ci/recompute-status.sh   # tinjau tanpa menulis
set -uo pipefail

APP_CONTAINER="${APP_CONTAINER:-hero_backend}"
TZ_BISNIS="${TZ_BISNIS:-Asia/Jakarta}"
DRY_RUN="${DRY_RUN:-0}"
LOG="${LOG:-/opt/hero/data/logs/recompute-status.log}"

mkdir -p "$(dirname "$LOG")"
exec >>"$LOG" 2>&1
echo "===== recompute-status $(date -Is) ====="

if ! docker inspect -f '{{.State.Running}}' "$APP_CONTAINER" 2>/dev/null | grep -q true; then
  echo "DILEWATI: kontainer $APP_CONTAINER tidak berjalan — tidak ada yang dihitung"
  echo "===== selesai $(date -Is) · exit 0 (dilewati) ====="
  exit 0
fi

if [[ "$DRY_RUN" = "1" ]]; then
  MODE_FLAG="--dry-run"
  echo "    mode: DRY-RUN (tidak menulis ke database)"
else
  MODE_FLAG="--apply"
  echo "    mode: APPLY · TZ=$TZ_BISNIS"
fi

nice -n 19 docker exec -e "TZ=$TZ_BISNIS" "$APP_CONTAINER" \
  python scripts/recompute_status.py "$MODE_FLAG"
rc=$?

if [[ $rc -ne 0 ]]; then
  echo "GAGAL: recompute_status.py exit $rc"
fi
echo "===== selesai $(date -Is) · exit $rc ====="
exit $rc
