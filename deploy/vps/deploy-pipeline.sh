#!/usr/bin/env bash
# Deploy lapisan data HERO (paket Python `hero`) ke VPS.
# Dijalankan sebagai root oleh ci-entry.sh. Arsip kode dikirim lewat stdin:
#
#   tar czf - pipeline/hero pipeline/pyproject.toml | ssh … deploy-pipeline
#
# Urutan:
#   1. simpan arsip, VALIDASI isinya (hanya pipeline/hero/** dan pipeline/pyproject.toml)
#   2. cadangkan kode yang sedang berjalan
#   3. salin kode baru; pasang ulang dependensi HANYA bila pyproject.toml berubah
#   4. restart layanan lalu uji asap; gagal → pulihkan kode lama
#
# Hanya kode. Konfigurasi (config/, .env) dan data (data/) tidak pernah disentuh.
set -Eeuo pipefail

HERO_HOME="${HERO_HOME:-/opt/hero}"
HERO_USER="${HERO_USER:-hero}"
VENV="${VENV:-$HERO_HOME/.venv}"
ML_HEALTH_URL="${ML_HEALTH_URL:-http://172.17.0.1:8100/health}"
SERVICES="${SERVICES:-hero-ml hero-bridge-ekstraksi}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-90}"
HEALTH_INTERVAL="${HEALTH_INTERVAL:-3}"
KEEP_BACKUPS="${KEEP_BACKUPS:-5}"
SKIP_PIP="${SKIP_PIP:-0}"

DEPLOY_DIR="$HERO_HOME/.deploy"
BACKUP_DIR="${BACKUP_DIR:-$HERO_HOME/data/cadangan-deploy}"

log() { printf '%s [deploy-pipeline] %s\n' "$(date '+%H:%M:%S')" "$*" >&2; }
die() { log "GAGAL: $*"; exit 1; }

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$DEPLOY_DIR" "$BACKUP_DIR"

# ------------------------------------------------------- 1. terima & validasi
[ -t 0 ] && die "arsip kode harus dikirim lewat stdin"
cat >"$STAGE/kode.tgz"
[ -s "$STAGE/kode.tgz" ] || die "arsip kosong"
tar tzf "$STAGE/kode.tgz" >"$STAGE/daftar.txt" 2>/dev/null || die "arsip rusak"
# Daftar putih: apa pun di luar ini ditolak, termasuk path absolut dan '..'.
if grep -vE '^pipeline/(hero(/[^[:cntrl:]]*)?|pyproject\.toml)$' "$STAGE/daftar.txt" | grep -q .; then
  grep -vE '^pipeline/(hero(/[^[:cntrl:]]*)?|pyproject\.toml)$' "$STAGE/daftar.txt" | head -3 >&2
  die "arsip memuat path di luar pipeline/hero dan pipeline/pyproject.toml"
fi
if grep -qE '(^|/)\.\.(/|$)|^/' "$STAGE/daftar.txt"; then die "arsip memuat path berbahaya"; fi
# Tautan simbolik/keras dari arsip bisa menunjuk keluar daftar putih.
if tar tvzf "$STAGE/kode.tgz" | grep -qE '^[lh]'; then die "arsip memuat tautan simbolik/keras"; fi

mkdir "$STAGE/baru"
tar xzf "$STAGE/kode.tgz" -C "$STAGE/baru" --no-same-owner --no-same-permissions
[ -d "$STAGE/baru/pipeline/hero" ] || die "arsip tidak memuat pipeline/hero"
[ -f "$STAGE/baru/pipeline/hero/__init__.py" ] || die "pipeline/hero/__init__.py tidak ada — bukan paket hero"

# -------------------------------------------------------- 2. cadangkan kode lama
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="$BACKUP_DIR/hero-kode-$STAMP.tar.gz"
tar czf "$BACKUP" -C "$HERO_HOME" hero pyproject.toml 2>/dev/null || die "gagal mencadangkan kode lama"
log "kode lama dicadangkan: $BACKUP"

pulihkan() {
  log "memulihkan kode lama dari $BACKUP"
  rm -rf "${HERO_HOME:?}/hero"
  tar xzf "$BACKUP" -C "$HERO_HOME"
  chown -R "$HERO_USER:$HERO_USER" "$HERO_HOME/hero" "$HERO_HOME/pyproject.toml" 2>/dev/null || true
  # shellcheck disable=SC2086
  systemctl restart $SERVICES 2>/dev/null || true
}

# ------------------------------------------------------------- 3. pasang kode
PERLU_PIP=0
if ! cmp -s "$STAGE/baru/pipeline/pyproject.toml" "$HERO_HOME/pyproject.toml" 2>/dev/null; then
  PERLU_PIP=1
fi

rm -rf "${HERO_HOME:?}/hero"
cp -r "$STAGE/baru/pipeline/hero" "$HERO_HOME/hero"
find "$HERO_HOME/hero" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
cp "$STAGE/baru/pipeline/pyproject.toml" "$HERO_HOME/pyproject.toml"
chown -R "$HERO_USER:$HERO_USER" "$HERO_HOME/hero" "$HERO_HOME/pyproject.toml"

if [ "$PERLU_PIP" = 1 ] && [ "$SKIP_PIP" != 1 ]; then
  log "pyproject.toml berubah — memasang ulang dependensi"
  if ! (cd "$HERO_HOME" && sudo -u "$HERO_USER" -H "$VENV/bin/pip" install -q -e "${HERO_HOME}[api,vector]" >&2); then
    pulihkan
    die "pip install gagal; kode lama dipulihkan"
  fi
fi

# ----------------------------------------------- 4. restart & uji asap
# shellcheck disable=SC2086
systemctl restart $SERVICES || { pulihkan; die "systemctl restart gagal"; }

ml_sehat() {
  local body
  body="$(curl -fsS -m 8 "$ML_HEALTH_URL" 2>/dev/null)" || return 1
  printf '%s' "$body" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except ValueError:
    sys.exit(1)
sys.exit(0 if "status" in d else 1)'
}

if ! (cd "$HERO_HOME" && sudo -u "$HERO_USER" -H "$VENV/bin/python" -c "import hero.cli, hero.bridge.client" >&2); then
  pulihkan
  die "paket hero tidak bisa diimpor setelah deploy; kode lama dipulihkan"
fi

mulai="$SECONDS"
until ml_sehat; do
  if [ $((SECONDS - mulai)) -ge "$HEALTH_TIMEOUT" ]; then
    pulihkan
    die "layanan analisa tidak menjawab dalam ${HEALTH_TIMEOUT}s; kode lama dipulihkan"
  fi
  sleep "$HEALTH_INTERVAL"
done

VERSI="$(cd "$HERO_HOME" && sudo -u "$HERO_USER" -H "$VENV/bin/python" -c 'from hero.analysis.structured import VERSION; print(VERSION)' 2>/dev/null || echo '?')"
date '+%F %T' >"$DEPLOY_DIR/pipeline-terakhir"
find "$BACKUP_DIR" -maxdepth 1 -name 'hero-kode-*.tar.gz' -printf '%T@ %p\n' 2>/dev/null \
  | sort -rn | tail -n +"$((KEEP_BACKUPS + 1))" | cut -d' ' -f2- | xargs -r rm -f
log "SEHAT — mesin analisa $VERSI"
