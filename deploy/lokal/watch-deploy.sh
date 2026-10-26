#!/usr/bin/env bash
# Pengawas deploy untuk server LOKAL (di balik NAT, tanpa IP publik).
#
# GitHub tidak bisa menghubungi server di balik router, jadi arahnya dibalik: server
# ini yang memeriksa GitHub secara berkala ("tarik", bukan "dorong"). Tidak ada port
# masuk yang perlu dibuka, dan tidak ada kode dari pull request orang luar yang pernah
# berjalan di sini — berbeda dengan self-hosted runner, yang berbahaya pada repo publik.
#
#   backend  : bandingkan digest ghcr.io/…/hero-backend:main dengan yang terpasang.
#              Berubah → serahkan ke deploy-backend.sh (cadangan → gladi migrasi pada
#              salinan data → ganti → verifikasi /health → pulihkan bila gagal).
#   pipeline : bandingkan commit origin/main dengan yang terpasang. Berubah → kirim
#              arsip kode ke deploy-pipeline.sh (validasi → cadangan → restart → uji asap).
#
# Keduanya memakai skrip deploy yang sudah teruji di deploy/vps/ — tidak ada jalur baru
# yang tidak teruji untuk menyentuh produksi.
#
# Pemakaian:  watch-deploy.sh [backend|pipeline|all]      (bawaan: all)
#             LAPOR_SAJA=1 watch-deploy.sh                 periksa tanpa deploy
set -Eeuo pipefail

HERO_HOME="${HERO_HOME:-/opt/hero}"
SRC_DIR="${SRC_DIR:-$HERO_HOME/src}"
CI_DIR="${CI_DIR:-$HERO_HOME/ci}"
STATE_DIR="${STATE_DIR:-$HERO_HOME/.deploy}"
IMAGE_REPO="${IMAGE_REPO:-ghcr.io/hero-ojk-its/hero-backend}"
IMAGE_TAG="${IMAGE_TAG:-main}"
GIT_REMOTE="${GIT_REMOTE:-origin}"
GIT_BRANCH="${GIT_BRANCH:-main}"
TOKEN_FILE="${TOKEN_FILE:-$CI_DIR/ghcr-token}"
LAPOR_SAJA="${LAPOR_SAJA:-0}"

APA="${1:-all}"
case "$APA" in backend|pipeline|all) ;; *) echo "pemakaian: $0 [backend|pipeline|all]" >&2; exit 2 ;; esac

log() { printf '%s [watch] %s\n' "$(date '+%F %T')" "$*" >&2; }
die() { log "GAGAL: $*"; exit 1; }

mkdir -p "$STATE_DIR"

# --------------------------------------------------------------- backend (GHCR)
# Digest dibaca lewat HTTP API registri, bukan `docker pull`: memeriksa tiap beberapa
# menit tidak boleh berarti mengunduh 750 MB tiap kali. Paket publik → tanpa kredensial;
# bila paketnya privat, taruh PAT read:packages di $TOKEN_FILE (mode 600).
digest_jauh() {
  local path="${IMAGE_REPO#ghcr.io/}" token hdr
  if [ -r "$TOKEN_FILE" ]; then
    token="$(printf '%s' "$(cat "$TOKEN_FILE")" | base64 | tr -d '\n')"
    hdr="Authorization: Basic $token"
  else
    local t
    t="$(curl -fsS -m 20 "https://ghcr.io/token?scope=repository:${path}:pull&service=ghcr.io" \
         | python3 -c 'import json,sys; print(json.load(sys.stdin).get("token",""))' 2>/dev/null)" || t=""
    [ -n "$t" ] || return 1
    hdr="Authorization: Bearer $t"
  fi
  curl -fsS -m 25 -I \
    -H "$hdr" \
    -H 'Accept: application/vnd.oci.image.index.v1+json' \
    -H 'Accept: application/vnd.oci.image.manifest.v1+json' \
    -H 'Accept: application/vnd.docker.distribution.manifest.list.v2+json' \
    -H 'Accept: application/vnd.docker.distribution.manifest.v2+json' \
    "https://ghcr.io/v2/${path}/manifests/${IMAGE_TAG}" \
    | tr -d '\r' | awk -F': ' 'tolower($1)=="docker-content-digest"{print $2}' | tail -1
}

periksa_backend() {
  local state="$STATE_DIR/backend-digest" jauh lokal
  jauh="$(digest_jauh || true)"
  if [ -z "$jauh" ]; then
    log "backend: digest tidak terbaca dari registri — dilewati (jaringan? paket privat tanpa token?)"
    return 0
  fi
  lokal="$(cat "$state" 2>/dev/null || true)"
  if [ "$jauh" = "$lokal" ]; then
    log "backend: mutakhir (${jauh:0:19}…)"
    return 0
  fi
  log "backend: versi baru ${jauh:0:19}… (terpasang: ${lokal:0:19}${lokal:+…})"
  if [ "$LAPOR_SAJA" = 1 ]; then log "LAPOR_SAJA: tidak men-deploy"; return 0; fi
  # Dideploy menurut digest, bukan tag: tag `main` bisa bergeser di tengah deploy,
  # dan digest menjamin yang diuji sama dengan yang dijalankan.
  if "$CI_DIR/deploy-backend.sh" "${IMAGE_REPO}@${jauh}" </dev/null; then
    printf '%s\n' "$jauh" >"$state"
    log "backend: deploy selesai"
  else
    log "backend: deploy GAGAL — digest tidak dicatat, akan dicoba lagi pada pemeriksaan berikutnya"
    return 1
  fi
}

# ------------------------------------------------------------- pipeline (git)
periksa_pipeline() {
  local state="$STATE_DIR/pipeline-sha" jauh lokal
  [ -d "$SRC_DIR/.git" ] || die "klon repo tidak ada di $SRC_DIR (lihat deploy/lokal/README.md)"
  jauh="$(git -C "$SRC_DIR" ls-remote --exit-code "$GIT_REMOTE" "refs/heads/$GIT_BRANCH" 2>/dev/null | awk '{print $1}')" || {
    log "pipeline: tidak bisa menghubungi remote git — dilewati"
    return 0
  }
  [[ "$jauh" =~ ^[0-9a-f]{40}$ ]] || { log "pipeline: sha remote tidak valid — dilewati"; return 0; }
  lokal="$(cat "$state" 2>/dev/null || true)"
  if [ "$jauh" = "$lokal" ]; then
    log "pipeline: mutakhir (${jauh:0:12})"
    return 0
  fi
  log "pipeline: commit baru ${jauh:0:12} (terpasang: ${lokal:0:12}${lokal:+ })"
  if [ "$LAPOR_SAJA" = 1 ]; then log "LAPOR_SAJA: tidak men-deploy"; return 0; fi
  git -C "$SRC_DIR" fetch -q --depth 1 "$GIT_REMOTE" "$GIT_BRANCH" || die "git fetch gagal"
  # Arsip dibuat dari objek git (bukan dari direktori kerja) sehingga isinya persis
  # commit itu, lalu dialirkan ke skrip yang sama dengan jalur VPS.
  if git -C "$SRC_DIR" archive "$jauh" pipeline/hero pipeline/pyproject.toml \
       | gzip | "$CI_DIR/deploy-pipeline.sh"; then
    printf '%s\n' "$jauh" >"$state"
    log "pipeline: deploy selesai"
  else
    log "pipeline: deploy GAGAL — sha tidak dicatat, akan dicoba lagi pada pemeriksaan berikutnya"
    return 1
  fi
}

RC=0
case "$APA" in
  backend)  periksa_backend  || RC=1 ;;
  pipeline) periksa_pipeline || RC=1 ;;
  all)
    # Keduanya dicoba walau salah satu gagal: backend dan lapisan data berdiri sendiri.
    periksa_backend  || RC=1
    periksa_pipeline || RC=1
    ;;
esac
exit "$RC"
