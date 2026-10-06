#!/usr/bin/env bash
# HERO — backfill folder OneDrive mitra langsung KE VPS, bertahap dan dapat
# dilanjutkan. Dijalankan DI DALAM VPS (deploy/README.md, bagian "Backfill
# OneDrive ke VPS"):
#
#   sudo -u hero -H nohup /opt/hero/deploy/fetch-onedrive.sh &
#   tail -f /opt/hero/data/logs/onedrive-*.log
#
# Kenapa dijalankan di VPS, bukan diunduh di laptop lalu dikirim ulang:
# berkas mengalir SharePoint -> VPS satu kali, tanpa singgah di laptop.
#
# Aman dihentikan (Ctrl-C, reboot, koneksi putus) dan dijalankan ulang: berkas
# yang sudah tersimpan dilewati SEBELUM diunduh (kb/catalog.py has_source_file),
# jadi setiap putaran mengambil berkas BARU berikutnya, bukan mengulang.
#
# Variabel (semua opsional):
#   HERO_HOME        lokasi proyek                         [/opt/hero]
#   HERO_CONFIG      berkas sources.yaml                   [$HERO_HOME/config/sources.yaml]
#   BATCH            berkas baru per putaran               [100]
#   MAX_ROUNDS       batas putaran per eksekusi            [30]  (30 x 100 = 3000 > 2299)
#   PAUSE            jeda antar putaran, detik             [30]
#   MIN_FREE_GB      berhenti bila ruang disk kurang dari  [3]
set -uo pipefail

HERO_HOME="${HERO_HOME:-/opt/hero}"
HERO_CONFIG="${HERO_CONFIG:-${HERO_HOME}/config/sources.yaml}"
BATCH="${BATCH:-100}"
MAX_ROUNDS="${MAX_ROUNDS:-30}"
PAUSE="${PAUSE:-30}"
MIN_FREE_GB="${MIN_FREE_GB:-3}"

# Lewat `python -m hero.cli`, bukan skrip .venv/bin/hero: shebang skrip itu
# menyimpan path absolut venv dan rusak bila proyek dipindah folder.
PY="${HERO_HOME}/.venv/bin/python"
LOG_DIR="${HERO_HOME}/data/logs"
LOCK="${HERO_HOME}/data/.onedrive-fetch.lock"
STAMP="$(date +%Y%m%d-%H%M%S)"
LOG="${LOG_DIR}/onedrive-${STAMP}.log"

mkdir -p "${LOG_DIR}"

# Satu eksekusi pada satu waktu: dua proses yang menulis katalog SQLite
# bersamaan saling mengunci dan salah satunya gagal dengan "database is locked".
exec 9>"${LOCK}"
if ! flock -n 9; then
  echo "Backfill OneDrive sudah berjalan (lock: ${LOCK}). Keluar." >&2
  exit 1
fi

exec > >(tee -a "${LOG}") 2>&1
echo "===== backfill OneDrive mulai: $(date -Is) | batch=${BATCH} maks=${MAX_ROUNDS} ====="

free_gb() { df -P --output=avail -BG "${HERO_HOME}/data" | tail -1 | tr -dc '0-9'; }

# Cek tautan dulu, tanpa mengunduh apa pun. Tautan kedaluwarsa atau berubah
# jadi "butuh login" akan terlihat di sini, bukan sebagai ratusan galat samar.
if ! "${PY}" -m hero.cli onedrive --config "${HERO_CONFIG}" --check; then
  echo "Tautan OneDrive tidak dapat dibaca tanpa login — berhenti. Minta tautan baru ke pemilik folder."
  exit 2
fi

total_new=0
for ((round = 1; round <= MAX_ROUNDS; round++)); do
  if (( $(free_gb) < MIN_FREE_GB )); then
    echo "Ruang disk < ${MIN_FREE_GB} GB — berhenti agar VPS tidak penuh."
    break
  fi

  echo "--- putaran ${round}/${MAX_ROUNDS} ($(date +%T)), sisa disk $(free_gb) GB"
  out="$("${PY}" -m hero.cli onedrive --config "${HERO_CONFIG}" --limit "${BATCH}" 2>&1)"
  echo "${out}" | grep -E "Ringkasan|Catatan|•" || true

  new="$(echo "${out}" | grep -oE '[0-9]+ masuk' | head -1 | grep -oE '[0-9]+' || echo 0)"
  new="${new:-0}"
  total_new=$(( total_new + new ))

  if ! echo "${out}" | grep -q "more new PDFs remain"; then
    echo "Tidak ada berkas baru tersisa — selesai."
    break
  fi
  if (( new == 0 )); then
    # Ada sisa tetapi tak satu pun berhasil disimpan: mengulang hanya akan
    # mengunduh berkas bermasalah yang sama lagi. Berhenti dan minta dilihat.
    echo "Putaran tanpa satu pun dokumen tersimpan padahal masih ada sisa — berhenti (lihat log)."
    exit 3
  fi
  sleep "${PAUSE}"
done

echo "===== selesai: ${total_new} dokumen baru pada eksekusi ini | $(date -Is) ====="
"${PY}" -m hero.cli stats --config "${HERO_CONFIG}" 2>&1 | head -12
