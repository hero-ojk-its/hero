#!/usr/bin/env bash
# Pintu masuk tunggal untuk kunci SSH milik GitHub Actions (forced command).
#
# Kunci deploy di authorized_keys dibatasi ke skrip ini:
#
#   command="/opt/hero/deploy/ci-entry.sh",no-pty,no-port-forwarding,no-agent-forwarding,no-X11-forwarding ssh-ed25519 AAAA… hero-deploy-gha
#
# Artinya kunci yang bocor sekalipun TIDAK bisa membuka shell: ia hanya bisa meminta
# dua hal di bawah, dengan argumen yang divalidasi ketat. Perintah yang diminta
# klien ada di $SSH_ORIGINAL_COMMAND; stdin diteruskan apa adanya (token registri
# atau arsip kode).
set -Eeuo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PERINTAH="${SSH_ORIGINAL_COMMAND:-}"

tolak() {
  echo "ditolak: perintah tidak dikenal atau argumen tidak valid" >&2
  logger -t hero-deploy "DITOLAK: ${PERINTAH:0:120}" 2>/dev/null || true
  exit 126
}

# Hanya image backend milik repo ini, dengan tag aman (sha / nama versi).
REGEX_IMAGE='^ghcr\.io/hero-ojk-its/hero-backend:[A-Za-z0-9._-]{1,128}$'

case "$PERINTAH" in
  "deploy-backend "*)
    IMAGE="${PERINTAH#deploy-backend }"
    [[ "$IMAGE" =~ $REGEX_IMAGE ]] || tolak
    logger -t hero-deploy "deploy-backend $IMAGE" 2>/dev/null || true
    exec sudo -n "$DIR/deploy-backend.sh" "$IMAGE"
    ;;
  "deploy-backend-gladi "*)
    # Tarik image, cadangkan, dan lathan migrasi pada SALINAN data — produksi tidak diubah.
    IMAGE="${PERINTAH#deploy-backend-gladi }"
    [[ "$IMAGE" =~ $REGEX_IMAGE ]] || tolak
    logger -t hero-deploy "deploy-backend-gladi $IMAGE" 2>/dev/null || true
    exec sudo -n env DRY_RUN=1 "$DIR/deploy-backend.sh" "$IMAGE"
    ;;
  "deploy-pipeline")
    logger -t hero-deploy "deploy-pipeline" 2>/dev/null || true
    exec sudo -n "$DIR/deploy-pipeline.sh"
    ;;
  *)
    tolak
    ;;
esac
