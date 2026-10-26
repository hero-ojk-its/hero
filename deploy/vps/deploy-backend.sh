#!/usr/bin/env bash
# Deploy backend HERO ke VPS dari image GHCR yang dibangun di GitHub Actions.
# Dijalankan sebagai root oleh ci-entry.sh (atau manual: sudo ./deploy-backend.sh IMAGE).
#
# Urutan — setiap langkah bisa menghentikan deploy SEBELUM produksi tersentuh:
#   1. prasyarat (disk, daemon Docker)
#   2. tarik image (token registri opsional lewat stdin, baris pertama)
#   3. cadangan: pg_dump database produksi
#   4. GLADI BERSIH migrasi: pulihkan cadangan ke database sementara dan jalankan
#      `alembic upgrade head` dengan image BARU di sana. Gagal → berhenti; produksi utuh.
#   5. ganti image backend (migrasi produksi berjalan otomatis saat kontainer start)
#   6. tunggu /health (status ok + migrations_up_to_date); gagal → kembali ke image lama
#
# DRY_RUN=1 menjalankan langkah 1–4 saja: aman dipakai untuk menguji di VPS sungguhan.
#
# Batas yang jujur: bila migrasi produksi SUDAH berjalan lalu health gagal, pengembalian
# image memulihkan KODE, bukan skema. Migrasi proyek ini aditif (kolom/tabel baru),
# sehingga kode lama tetap berjalan di skema baru; pemulihan skema penuh dari cadangan
# (jalur tercantum di akhir pesan galat) adalah langkah manual yang disengaja.
set -Eeuo pipefail

IMAGE="${1:?pemakaian: deploy-backend.sh ghcr.io/hero-ojk-its/hero-backend:TAG}"

HERO_HOME="${HERO_HOME:-/opt/hero}"
DB_CONTAINER="${DB_CONTAINER:-hero_db}"
APP_CONTAINER="${APP_CONTAINER:-hero_backend}"
NETWORK="${HERO_NETWORK:-hero_internal}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8000/health}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-150}"
HEALTH_INTERVAL="${HEALTH_INTERVAL:-3}"
MIN_FREE_KB="${MIN_FREE_KB:-2621440}"      # 2,5 GB
DRY_RUN="${DRY_RUN:-0}"
KEEP_DUMPS="${KEEP_DUMPS:-14}"
KEEP_IMAGES="${KEEP_IMAGES:-3}"

DEPLOY_DIR="$HERO_HOME/.deploy"
BACKUP_DIR="${BACKUP_DIR:-$HERO_HOME/data/cadangan-deploy}"
COMPOSE_BASE="$HERO_HOME/docker-compose.yml"
COMPOSE_OVERRIDE="$DEPLOY_DIR/docker-compose.image.yml"
STATE_FILE="$DEPLOY_DIR/backend-image"
REHEARSAL_DB="hero_rehearsal"

log() { printf '%s [deploy-backend] %s\n' "$(date '+%H:%M:%S')" "$*" >&2; }
die() { log "GAGAL: $*"; exit 1; }

REGISTRY_LOGGED_IN=0
ENV_TMP=""
# shellcheck disable=SC2329  # dipanggil tak langsung lewat trap
cleanup() {
  if [ "$REGISTRY_LOGGED_IN" = 1 ]; then docker logout ghcr.io >/dev/null 2>&1 || true; fi
  if [ -n "$ENV_TMP" ]; then rm -f "$ENV_TMP"; fi
}
trap cleanup EXIT

compose() { docker compose -f "$COMPOSE_BASE" -f "$COMPOSE_OVERRIDE" "$@"; }

pakai_image() {                      # tulis override compose untuk image tertentu
  mkdir -p "$DEPLOY_DIR"
  cat >"$COMPOSE_OVERRIDE" <<EOF
# Dihasilkan deploy-backend.sh — jangan disunting. Image dari GHCR, bukan build lokal.
services:
  backend:
    image: $1
    pull_policy: never
EOF
}

health_ok() {                        # 0 bila /health menjawab ok dan migrasi mutakhir
  local body
  body="$(curl -fsS -m 8 "$HEALTH_URL" 2>/dev/null)" || return 1
  printf '%s' "$body" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except ValueError:
    sys.exit(1)
sys.exit(0 if d.get("status") == "ok" and d.get("migrations_up_to_date") is True else 1)'
}

tunggu_sehat() {
  local mulai="$SECONDS"
  while [ $((SECONDS - mulai)) -lt "$HEALTH_TIMEOUT" ]; do
    health_ok && return 0
    sleep "$HEALTH_INTERVAL"
  done
  return 1
}

# ---------------------------------------------------------------- 1. prasyarat
log "image: $IMAGE (DRY_RUN=$DRY_RUN)"
docker info >/dev/null 2>&1 || die "daemon Docker tidak menjawab"
mkdir -p "$DEPLOY_DIR" "$BACKUP_DIR"
bebas_kb="$(df -Pk "$HERO_HOME" | awk 'NR==2{print $4}')"
[ "${bebas_kb:-0}" -ge "$MIN_FREE_KB" ] || die "disk bebas ${bebas_kb:-0} KB < batas $MIN_FREE_KB KB"

# ------------------------------------------------------------- 2. tarik image
# Baris pertama stdin (bila ada) adalah token registri berumur pendek. Tanpa stdin
# (jalan manual) dan image publik, tarik anonim.
TOKEN=""
if [ ! -t 0 ]; then IFS= read -r -t 5 TOKEN || true; fi
if [ -n "$TOKEN" ]; then
  printf '%s' "$TOKEN" | docker login ghcr.io -u github-actions --password-stdin >/dev/null \
    || die "login ke ghcr.io ditolak"
  REGISTRY_LOGGED_IN=1
fi
docker pull "$IMAGE" >/dev/null || die "gagal menarik $IMAGE"
log "image ditarik"

# -------------------------------------------------------------- 3. cadangan
STAMP="$(date +%Y%m%d-%H%M%S)"
DUMP="$BACKUP_DIR/hero_db-$STAMP.sql.gz"
docker exec "$DB_CONTAINER" sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip >"$DUMP" \
  || die "pg_dump gagal"
[ -s "$DUMP" ] || die "cadangan kosong: $DUMP"
log "cadangan: $DUMP ($(du -h "$DUMP" | cut -f1))"

# ---------------------------------------------------- 4. gladi bersih migrasi
PROD_URL="$(docker exec "$APP_CONTAINER" printenv DATABASE_URL)" \
  || die "tidak bisa membaca DATABASE_URL dari $APP_CONTAINER"
REHEARSAL_URL="${PROD_URL%/*}/$REHEARSAL_DB"

drop_rehearsal() {
  docker exec "$DB_CONTAINER" sh -c \
    "psql -q -U \"\$POSTGRES_USER\" -d postgres -c 'DROP DATABASE IF EXISTS $REHEARSAL_DB'" \
    >/dev/null 2>&1 || true
}

drop_rehearsal
docker exec "$DB_CONTAINER" sh -c \
  "psql -q -U \"\$POSTGRES_USER\" -d postgres -c 'CREATE DATABASE $REHEARSAL_DB'" >/dev/null \
  || die "tidak bisa membuat database gladi"
if ! gunzip -c "$DUMP" | docker exec -i "$DB_CONTAINER" sh -c \
    "psql -q -v ON_ERROR_STOP=1 -U \"\$POSTGRES_USER\" -d $REHEARSAL_DB" >/dev/null; then
  drop_rehearsal
  die "cadangan tidak bisa dipulihkan ke database gladi (produksi TIDAK disentuh)"
fi
# `docker run --env-file` memakai nilai apa adanya, sedangkan `docker compose` membuang kutip
# di sekitar nilai. Gladi harus melihat lingkungan yang SAMA dengan produksi, jadi kutipnya
# dibuang di salinan sementara (mode 600, dihapus saat keluar).
ENV_TMP="$(mktemp)"
chmod 600 "$ENV_TMP"
sed -E "s/^([A-Za-z_][A-Za-z0-9_]*)=[\"'](.*)[\"']\$/\1=\2/" "$HERO_HOME/backend/.env.prod" >"$ENV_TMP"
if ! docker run --rm --network "$NETWORK" --env-file "$ENV_TMP" \
    -e "DATABASE_URL=$REHEARSAL_URL" "$IMAGE" alembic upgrade head >&2; then
  drop_rehearsal
  die "migrasi GAGAL pada salinan data produksi — produksi TIDAK disentuh. Perbaiki migrasi lalu ulangi."
fi
drop_rehearsal
log "gladi migrasi pada salinan data: lulus"

if [ "$DRY_RUN" = 1 ]; then
  log "DRY_RUN: berhenti di sini; produksi tidak diubah"
  exit 0
fi

# ------------------------------------------------------- 5. ganti image
IMAGE_LAMA_ID="$(docker inspect -f '{{.Image}}' "$APP_CONTAINER" 2>/dev/null || true)"
TAG_KEMBALI="hero-backend:rollback"
if [ -n "$IMAGE_LAMA_ID" ]; then
  docker tag "$IMAGE_LAMA_ID" "$TAG_KEMBALI" || log "peringatan: tidak bisa menandai image lama untuk pemulihan"
fi

pakai_image "$IMAGE"
log "mengganti backend → $IMAGE"
compose up -d --no-build --no-deps backend >&2 || die "docker compose up gagal"

# ---------------------------------------------------------------- 6. verifikasi
if tunggu_sehat; then
  printf '%s\n' "$IMAGE" >"$STATE_FILE"
  log "SEHAT — revisi migrasi mutakhir"
  docker image prune -f >/dev/null 2>&1 || true
  # simpan beberapa image terbaru saja; yang lain dibuang agar disk tidak penuh
  docker images ghcr.io/hero-ojk-its/hero-backend --format '{{.ID}}' 2>/dev/null \
    | awk '!seen[$0]++' | tail -n +"$((KEEP_IMAGES + 1))" | xargs -r docker rmi >/dev/null 2>&1 || true
  find "$BACKUP_DIR" -maxdepth 1 -name 'hero_db-*.sql.gz' -printf '%T@ %p\n' 2>/dev/null \
    | sort -rn | tail -n +"$((KEEP_DUMPS + 1))" | cut -d' ' -f2- | xargs -r rm -f
  log "selesai"
  exit 0
fi

log "TIDAK SEHAT dalam ${HEALTH_TIMEOUT}s — mengembalikan image lama"
if [ -n "$IMAGE_LAMA_ID" ]; then
  pakai_image "$TAG_KEMBALI"
  compose up -d --no-build --no-deps backend >&2 || true
  if tunggu_sehat; then
    log "image lama pulih dan sehat (kode dikembalikan; skema TIDAK diubah balik)"
  else
    log "image lama pun tidak sehat — periksa manual: docker logs $APP_CONTAINER"
  fi
else
  log "tidak ada image lama untuk dikembalikan"
fi
die "deploy dibatalkan. Cadangan sebelum deploy: $DUMP"
