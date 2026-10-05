#!/usr/bin/env bash
# HERO — instalasi di VPS Ubuntu 24.04 (dijalankan DI DALAM VPS, bukan di Mac).
#
# Asumsi: kode HERO sudah ada di /opt/hero (lihat deploy/README.md langkah 2).
# Idempoten — aman dijalankan ulang kalau ada langkah yang gagal di tengah.
#
# Pemakaian:
#   sudo bash deploy/install.sh
set -euo pipefail

HERO_HOME="/opt/hero"
HERO_USER="hero"
PYTHON_BIN="python3"

if [[ $EUID -ne 0 ]]; then
  echo "Jalankan dengan sudo: sudo bash deploy/install.sh" >&2
  exit 1
fi

echo "==> [1/6] Paket sistem (apt)"
apt-get update -qq
apt-get install -y --no-install-recommends \
  python3 python3-venv python3-pip \
  poppler-utils \
  tesseract-ocr tesseract-ocr-ind tesseract-ocr-eng \
  ca-certificates curl git rsync rclone

echo "==> [2/6] User sistem '${HERO_USER}' (tanpa login, tanpa home besar)"
if ! id -u "${HERO_USER}" >/dev/null 2>&1; then
  useradd --system --create-home --home-dir "${HERO_HOME}" --shell /usr/sbin/nologin "${HERO_USER}"
  echo "    dibuat: ${HERO_USER}"
else
  echo "    sudah ada, dilewati"
fi

echo "==> [3/6] Kepemilikan direktori proyek"
# Seluruh /opt/hero (bukan cuma data/) — user 'hero' perlu menulis di sini
# untuk membuat .venv, bukan hanya di folder data.
mkdir -p "${HERO_HOME}"/data/{staging,logs,export,knowledge_base}
chown -R "${HERO_USER}:${HERO_USER}" "${HERO_HOME}"

echo "==> [4/6] Virtual environment Python + paket HERO"
if [[ ! -d "${HERO_HOME}/.venv" ]]; then
  sudo -u "${HERO_USER}" "${PYTHON_BIN}" -m venv "${HERO_HOME}/.venv"
fi
sudo -u "${HERO_USER}" "${HERO_HOME}/.venv/bin/pip" install -q --upgrade pip
# api + vector (deterministik, tanpa unduhan model). Mode AI-Assisted (model
# semantik 0,2–2,2 GB) hanya bila diminta: HERO_SEMANTIC=1 sudo bash deploy/install.sh
EXTRAS="api,vector"
if [[ "${HERO_SEMANTIC:-0}" == "1" ]]; then EXTRAS="api,vector,semantic"; fi
sudo -u "${HERO_USER}" "${HERO_HOME}/.venv/bin/pip" install -q -e "${HERO_HOME}[${EXTRAS}]"

echo "==> [5/6] Verifikasi Tesseract & HERO"
sudo -u "${HERO_USER}" "${HERO_HOME}/.venv/bin/hero" version

echo "==> [6/6] Unit systemd"
cp "${HERO_HOME}/deploy/systemd/hero-pipeline.service" /etc/systemd/system/
cp "${HERO_HOME}/deploy/systemd/hero-pipeline.timer" /etc/systemd/system/
cp "${HERO_HOME}/deploy/systemd/hero-api.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now hero-pipeline.timer
# Bangun indeks turunan sekali sebelum API dinyalakan (read model otomatis).
sudo -u "${HERO_USER}" "${HERO_HOME}/.venv/bin/python" -m hero.cli graph build || true
if [[ "${HERO_SEMANTIC:-0}" == "1" ]]; then
  sudo -u "${HERO_USER}" "${HERO_HOME}/.venv/bin/python" -m hero.cli vector build || true
else
  sudo -u "${HERO_USER}" "${HERO_HOME}/.venv/bin/python" -m hero.cli vector build --lsa-only || true
fi
systemctl enable --now hero-api.service

cat <<'EOF'

============================================================
Instalasi dasar selesai. LANGKAH SELANJUTNYA (manual, lihat
deploy/README.md untuk detail tiap langkah):

  1. Buat App Password di Nextcloud, lalu konfigurasi rclone
     SEBAGAI USER 'hero' (bukan root/user login Anda):
       sudo -u hero -H rclone config
     (lihat deploy/README.md bagian 4 untuk nilai-nilai yang diisi)

  2. Uji satu kali secara manual sebelum mengandalkan jadwal otomatis:
       sudo -u hero /opt/hero/.venv/bin/hero discover --sektor 01 --jenis 06
       sudo -u hero /opt/hero/.venv/bin/hero stats
       sudo -u hero /opt/hero/deploy/run-pipeline.sh

  3. Cek jadwal otomatis:
       systemctl status hero-pipeline.timer
       systemctl list-timers hero-pipeline.timer

  4. Lihat log jalannya pipeline:
       journalctl -u hero-pipeline.service -f
============================================================
EOF
