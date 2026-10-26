#!/usr/bin/env bash
# Pemasangan HERO di server LOKAL Ubuntu/Debian — dijalankan DI SERVER, sekali.
#
#   sudo bash install-server.sh
#
# Idempoten: aman diulang bila ada langkah yang gagal di tengah.
# Yang dilakukan: paket sistem, Docker Engine, user `hero`, tata letak /opt/hero,
# klon repo, venv lapisan data, skrip deploy, unit systemd, timer pengawas.
#
# TIDAK dilakukan di sini (sengaja, perlu keputusan/rahasia Anda):
#   - mengisi /opt/hero/backend/.env.prod  (kata sandi, kunci)
#   - Cloudflare Tunnel                     (login ke akun Anda)
#   - menyalakan timer pengawas             (nyalakan setelah deploy pertama berhasil)
# Lihat deploy/lokal/README.md.
set -Eeuo pipefail

HERO_HOME="${HERO_HOME:-/opt/hero}"
HERO_USER="${HERO_USER:-hero}"
REPO_URL="${REPO_URL:-https://github.com/hero-ojk-its/hero.git}"
REPO_BRANCH="${REPO_BRANCH:-main}"

[ "$EUID" -eq 0 ] || { echo "Jalankan dengan sudo: sudo bash install-server.sh" >&2; exit 1; }
# shellcheck source=/dev/null
. /etc/os-release 2>/dev/null || true
case "${ID:-}:${ID_LIKE:-}" in
  *debian*|ubuntu:*) ;;
  *) echo "Skrip ini untuk Ubuntu/Debian (terdeteksi: ${PRETTY_NAME:-tidak diketahui}). Hentikan." >&2; exit 1 ;;
esac

log() { printf '\n==> %s\n' "$*"; }

log "[1/9] Paket sistem"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends \
  ca-certificates curl git rsync jq \
  python3 python3-venv python3-pip \
  poppler-utils tesseract-ocr tesseract-ocr-ind tesseract-ocr-eng \
  postgresql-client

log "[2/9] Docker Engine (repositori resmi Docker, bukan Docker Desktop)"
if ! command -v docker >/dev/null 2>&1; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL "https://download.docker.com/linux/${ID}/gpg" -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/${ID} ${VERSION_CODENAME} stable" >/etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
else
  echo "    sudah ada: $(docker --version)"
fi
docker compose version >/dev/null 2>&1 || { echo "plugin docker compose tidak ada" >&2; exit 1; }

log "[3/9] User '${HERO_USER}'"
if id -u "$HERO_USER" >/dev/null 2>&1; then
  echo "    sudah ada (dipakai apa adanya)"
else
  useradd --system --create-home --home-dir "$HERO_HOME" --shell /usr/sbin/nologin "$HERO_USER"
  echo "    dibuat sebagai user sistem"
fi
# Bila dibuat dengan `adduser` (user login biasa), kunci kata sandinya: akun ini
# hanya untuk menjalankan layanan, bukan untuk login interaktif.
if passwd -S "$HERO_USER" 2>/dev/null | awk '{exit ($2=="P")?0:1}'; then
  passwd -l "$HERO_USER" >/dev/null && echo "    kata sandi dikunci (akun layanan, bukan akun login)"
fi

log "[4/9] Tata letak ${HERO_HOME}"
mkdir -p "$HERO_HOME"/{ci,src,.deploy} \
         "$HERO_HOME"/data/{staging,logs,export,knowledge_base,cadangan-deploy,vectors,models} \
         "$HERO_HOME"/config "$HERO_HOME"/backend "$HERO_HOME"/sources
chown -R "$HERO_USER:$HERO_USER" "$HERO_HOME"
chown root:root "$HERO_HOME/ci"; chmod 755 "$HERO_HOME/ci"   # kode deploy: tidak boleh ditulis layanan

log "[5/9] Klon repo (publik, tanpa kredensial) → ${HERO_HOME}/src"
if [ -d "$HERO_HOME/src/.git" ]; then
  sudo -u "$HERO_USER" git -C "$HERO_HOME/src" remote set-url origin "$REPO_URL"
  sudo -u "$HERO_USER" git -C "$HERO_HOME/src" fetch -q --depth 1 origin "$REPO_BRANCH"
  echo "    sudah ada, diperbarui"
else
  sudo -u "$HERO_USER" git clone -q --depth 1 --branch "$REPO_BRANCH" "$REPO_URL" "$HERO_HOME/src"
fi
SRC="$HERO_HOME/src"

log "[6/9] Skrip deploy → ${HERO_HOME}/ci (milik root)"
install -m 755 -o root -g root \
  "$SRC/deploy/vps/deploy-backend.sh" \
  "$SRC/deploy/vps/deploy-pipeline.sh" \
  "$SRC/deploy/lokal/watch-deploy.sh" \
  "$HERO_HOME/ci/"

log "[7/9] Berkas compose & konfigurasi backend"
install -m 644 -o "$HERO_USER" -g "$HERO_USER" "$SRC/deploy/lokal/docker-compose.lokal.yml" \
  "$HERO_HOME/docker-compose.yml"
# DUA berkas rahasia dengan peran berbeda:
#   /opt/hero/.env           → interpolasi ${…} docker compose + variabel HERO_* lapisan data
#   /opt/hero/backend/.env.prod → lingkungan di dalam kontainer backend
# compose TIDAK membaca .env.prod untuk interpolasi, jadi keduanya diperlukan.
for pasangan in ".env:env.contoh" "backend/.env.prod:env.prod.contoh"; do
  tujuan="$HERO_HOME/${pasangan%%:*}"; contoh="$SRC/deploy/lokal/${pasangan##*:}"
  if [ -f "$tujuan" ]; then
    echo "    ${pasangan%%:*} sudah ada, tidak ditimpa"
  else
    install -m 600 -o "$HERO_USER" -g "$HERO_USER" "$contoh" "$tujuan"
    echo "    ${pasangan%%:*} dibuat dari contoh — WAJIB diisi (langkah 5 README)"
  fi
done

log "[8/9] Lapisan data: venv + paket hero"
# Kode lapisan data dipasang terpisah dari src/ supaya deploy-pipeline.sh bisa
# menimpanya tanpa menyentuh klon git.
[ -d "$HERO_HOME/.venv" ] || sudo -u "$HERO_USER" python3 -m venv "$HERO_HOME/.venv"
sudo -u "$HERO_USER" "$HERO_HOME/.venv/bin/pip" install -q --upgrade pip
rm -rf "$HERO_HOME/hero"
cp -r "$SRC/pipeline/hero" "$HERO_HOME/hero"
cp "$SRC/pipeline/pyproject.toml" "$HERO_HOME/pyproject.toml"
chown -R "$HERO_USER:$HERO_USER" "$HERO_HOME/hero" "$HERO_HOME/pyproject.toml"
( cd "$HERO_HOME" && sudo -u "$HERO_USER" -H "$HERO_HOME/.venv/bin/pip" install -q -e "${HERO_HOME}[api,vector]" )
for f in sources.yaml kategori.yaml harmonisasi.yaml ground_truth.yaml eval_queries.yaml; do
  [ -f "$HERO_HOME/config/$f" ] || { [ -f "$SRC/pipeline/config/$f" ] && \
    install -m 644 -o "$HERO_USER" -g "$HERO_USER" "$SRC/pipeline/config/$f" "$HERO_HOME/config/$f"; }
done
( cd "$HERO_HOME" && sudo -u "$HERO_USER" -H "$HERO_HOME/.venv/bin/hero" version ) || true

log "[9/9] Unit systemd"
install -m 644 "$SRC/pipeline/deploy/systemd/hero-ml.service" /etc/systemd/system/
install -m 644 "$SRC/pipeline/deploy/systemd/hero-bridge-ekstraksi.service" /etc/systemd/system/
install -m 644 "$SRC/deploy/lokal/systemd/hero-watch-deploy.service" /etc/systemd/system/
install -m 644 "$SRC/deploy/lokal/systemd/hero-watch-deploy.timer" /etc/systemd/system/
systemctl daemon-reload

cat <<SELESAI

Pemasangan dasar selesai. Yang masih harus Anda lakukan (deploy/lokal/README.md):

  1. Isi DUA berkas rahasia:
       sudo nano $HERO_HOME/.env                 (kata sandi DB + variabel HERO_*)
       sudo nano $HERO_HOME/backend/.env.prod    (lingkungan kontainer backend)
  2. Nyalakan database   : cd $HERO_HOME && sudo docker compose up -d db
  3. Deploy backend 1x   : sudo $HERO_HOME/ci/watch-deploy.sh backend
  4. Cloudflare Tunnel   : akses dari internet (bagian 6 README)
  5. Nyalakan pengawas   : sudo systemctl enable --now hero-watch-deploy.timer

Cek kapan saja:  sudo LAPOR_SAJA=1 $HERO_HOME/ci/watch-deploy.sh
SELESAI
