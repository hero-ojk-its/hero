#!/usr/bin/env bash
# Uji logika pengawas deploy server lokal, dengan curl/git/skrip deploy PALSU.
# Yang dijaga: tidak men-deploy saat tidak ada versi baru (timer jalan tiap 5 menit —
# salah di sini berarti produksi diganti terus-menerus), deploy memakai digest yang
# kekal, dan kegagalan tidak dicatat sebagai sukses (supaya dicoba lagi).
#
# Jalankan: bash deploy/lokal/tests/test_watch.sh
# shellcheck disable=SC2016,SC2034
set -uo pipefail

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOKAL_DIR="${LOKAL_DIR:-$(cd "$AQUI/.." && pwd)}"
LULUS=0; GAGAL=0
ok()    { LULUS=$((LULUS + 1)); printf '  \033[32mlulus\033[0m  %s\n' "$1"; }
salah() { GAGAL=$((GAGAL + 1)); printf '  \033[31mGAGAL\033[0m  %s\n' "$1"; [ -n "${2:-}" ] && printf '         %s\n' "$2"; }
cek()   { if eval "$2"; then ok "$1"; else salah "$1" "kondisi: $2"; fi; }

D1="sha256:1111111111111111111111111111111111111111111111111111111111111111"
D2="sha256:2222222222222222222222222222222222222222222222222222222222222222"
S1="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
S2="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

buat() {
  T="$(mktemp -d)"
  export HERO_HOME="$T/hero" CI_DIR="$T/hero/ci" STATE_DIR="$T/hero/.deploy" SRC_DIR="$T/hero/src"
  export CALLS="$T/panggilan.log" TOKEN_FILE="$T/tidak-ada-token"
  mkdir -p "$CI_DIR" "$STATE_DIR" "$SRC_DIR/.git" "$T/bin"
  : >"$CALLS"
  # curl palsu: token lalu header manifest. Digest diatur lewat $FAKE_DIGEST.
  cat >"$T/bin/curl" <<'EOF'
#!/usr/bin/env bash
echo "curl $*" >>"$CALLS"
for a in "$@"; do case "$a" in *"/token?scope="*) echo '{"token":"t-palsu"}'; exit 0 ;; esac; done
[ "${FAKE_REG_FAIL:-0}" = 1 ] && exit 22
printf 'HTTP/1.1 200 OK\r\nDocker-Content-Digest: %s\r\n\r\n' "${FAKE_DIGEST:-}"
EOF
  # git palsu: ls-remote mengembalikan $FAKE_SHA; archive menghasilkan tar kecil.
  cat >"$T/bin/git" <<'EOF'
#!/usr/bin/env bash
echo "git $*" >>"$CALLS"
for a in "$@"; do
  case "$a" in
    ls-remote) [ "${FAKE_GIT_FAIL:-0}" = 1 ] && exit 2; printf '%s\trefs/heads/main\n' "${FAKE_SHA:-}"; exit 0 ;;
    fetch)     exit "${FAKE_FETCH_FAIL:-0}" ;;
    archive)   printf 'arsip-palsu'; exit 0 ;;
  esac
done
exit 0
EOF
  # skrip deploy palsu: mencatat argumen & stdin, sukses/gagal diatur variabel.
  cat >"$CI_DIR/deploy-backend.sh" <<'EOF'
#!/usr/bin/env bash
echo "deploy-backend $*" >>"$CALLS"
if [ ! -t 0 ]; then
  STDIN="$(cat)"
  echo "deploy-backend stdin=$STDIN" >>"$CALLS"
fi
exit "${FAKE_DEPLOY_BE_FAIL:-0}"
EOF
  cat >"$CI_DIR/deploy-pipeline.sh" <<'EOF'
#!/usr/bin/env bash
n=$(wc -c); echo "deploy-pipeline stdin=${n// /}" >>"$CALLS"
exit "${FAKE_DEPLOY_PL_FAIL:-0}"
EOF
  chmod +x "$T/bin/"* "$CI_DIR/"*.sh
  export PATH="$T/bin:$PATH"
  unset FAKE_DIGEST FAKE_SHA FAKE_REG_FAIL FAKE_GIT_FAIL FAKE_FETCH_FAIL \
        FAKE_DEPLOY_BE_FAIL FAKE_DEPLOY_PL_FAIL LAPOR_SAJA
}
bersih() { rm -rf "$T"; }
W() { "$LOKAL_DIR/watch-deploy.sh" "$@" 2>&1; }

echo "backend (GHCR)"
buat; export FAKE_DIGEST="$D1"
OUT="$(W backend)"; K=$?
cek "pertama kali: men-deploy"                  '[ $K -eq 0 ] && grep -q "deploy-backend " "$CALLS"'
cek "dideploy memakai DIGEST, bukan tag :main"  'grep -q "deploy-backend ghcr.io/hero-ojk-its/hero-backend@$D1" "$CALLS" && ! grep -q "hero-backend:main" "$CALLS"'
cek "digest dicatat setelah sukses"             '[ "$(cat "$STATE_DIR/backend-digest")" = "$D1" ]'
: >"$CALLS"
OUT="$(W backend)"; K=$?
cek "digest sama: TIDAK men-deploy lagi"        '[ $K -eq 0 ] && ! grep -q "deploy-backend " "$CALLS"'
cek "digest sama: dilaporkan mutakhir"          'echo "$OUT" | grep -q "mutakhir"'
export FAKE_DIGEST="$D2"; : >"$CALLS"
OUT="$(W backend)"; K=$?
cek "digest berubah: men-deploy lagi"           '[ $K -eq 0 ] && grep -q "@$D2" "$CALLS"'
cek "digest baru dicatat"                       '[ "$(cat "$STATE_DIR/backend-digest")" = "$D2" ]'
bersih

buat; export FAKE_DIGEST="$D1" FAKE_DEPLOY_BE_FAIL=1
OUT="$(W backend)"; K=$?
cek "deploy gagal: keluar bukan 0"              '[ $K -ne 0 ]'
cek "deploy gagal: digest TIDAK dicatat (dicoba lagi)" '[ ! -f "$STATE_DIR/backend-digest" ]'
bersih

buat; export FAKE_DIGEST="$D1" LAPOR_SAJA=1
OUT="$(W backend)"; K=$?
cek "LAPOR_SAJA: melaporkan versi baru tanpa deploy" '[ $K -eq 0 ] && ! grep -q "deploy-backend " "$CALLS" && echo "$OUT" | grep -q "versi baru"'
bersih

buat; export FAKE_REG_FAIL=1
OUT="$(W backend)"; K=$?
cek "registri tak terjangkau: diam-diam dilewati (bukan deploy)" '[ $K -eq 0 ] && ! grep -q "deploy-backend " "$CALLS"'
cek "registri tak terjangkau: dilaporkan di log"  'echo "$OUT" | grep -q "tidak terbaca"'
bersih

buat; export FAKE_DIGEST=""
OUT="$(W backend)"; K=$?
cek "digest kosong: tidak dianggap versi baru"    '[ $K -eq 0 ] && ! grep -q "deploy-backend " "$CALLS"'
bersih

buat; export FAKE_DIGEST="$D1"
printf 'user-github:pat-rahasia\n' >"$TOKEN_FILE"; chmod 600 "$TOKEN_FILE"
OUT="$(W backend)"; K=$?
cek "TOKEN_FILE: tetap men-deploy (paket privat)"      '[ $K -eq 0 ] && grep -q "deploy-backend " "$CALLS"'
cek "TOKEN_FILE: hanya bagian PAT diteruskan lewat stdin, bukan usernya" \
  'grep -q "deploy-backend stdin=pat-rahasia" "$CALLS" && ! grep -q "stdin=user-github" "$CALLS"'
cek "TOKEN_FILE: /token ditukar dengan Basic auth (-u)" 'grep -qE "curl .*-u user-github:pat-rahasia" "$CALLS"'
bersih

echo "pipeline (git)"
buat; export FAKE_SHA="$S1"
OUT="$(W pipeline)"; K=$?
cek "pertama kali: men-deploy"                    '[ $K -eq 0 ] && grep -q "deploy-pipeline stdin=" "$CALLS"'
cek "arsip dikirim lewat stdin (bukan kosong)"    'grep -qE "deploy-pipeline stdin=[1-9]" "$CALLS"'
cek "arsip dibuat dari sha tertentu, bukan HEAD"  'grep -q "archive $S1 pipeline/hero pipeline/pyproject.toml" "$CALLS"'
cek "sha dicatat"                                 '[ "$(cat "$STATE_DIR/pipeline-sha")" = "$S1" ]'
: >"$CALLS"
OUT="$(W pipeline)"; K=$?
cek "sha sama: TIDAK men-deploy lagi"             '[ $K -eq 0 ] && ! grep -q "deploy-pipeline" "$CALLS"'
cek "sha sama: tidak ada git fetch sia-sia"       '! grep -qE "git .*fetch" "$CALLS"'
export FAKE_SHA="$S2"; : >"$CALLS"
OUT="$(W pipeline)"; K=$?
cek "sha berubah: fetch lalu deploy"              '[ $K -eq 0 ] && grep -qE "git .*fetch" "$CALLS" && grep -q "archive $S2" "$CALLS"'
bersih

buat; export FAKE_SHA="$S1" FAKE_DEPLOY_PL_FAIL=1
OUT="$(W pipeline)"; K=$?
cek "deploy gagal: sha TIDAK dicatat"             '[ $K -ne 0 ] && [ ! -f "$STATE_DIR/pipeline-sha" ]'
bersih

buat; export FAKE_GIT_FAIL=1
OUT="$(W pipeline)"; K=$?
cek "remote git tak terjangkau: dilewati, bukan deploy" '[ $K -eq 0 ] && ! grep -q "deploy-pipeline" "$CALLS"'
bersih

buat; export FAKE_SHA="bukan-sha-valid"
OUT="$(W pipeline)"; K=$?
cek "sha tidak valid ditolak (tidak men-deploy)"  '[ $K -eq 0 ] && ! grep -q "deploy-pipeline" "$CALLS"'
bersih

buat; export FAKE_SHA="$S1"; rm -rf "$SRC_DIR/.git"
OUT="$(W pipeline)"; K=$?
cek "tanpa klon repo: gagal dengan pesan jelas"   '[ $K -ne 0 ] && echo "$OUT" | grep -q "klon repo tidak ada"'
bersih

echo "gabungan & argumen"
buat; export FAKE_DIGEST="$D1" FAKE_SHA="$S1"
OUT="$(W all)"; K=$?
cek "all: keduanya dideploy"                      '[ $K -eq 0 ] && grep -q "deploy-backend " "$CALLS" && grep -q "deploy-pipeline" "$CALLS"'
bersih
buat; export FAKE_DIGEST="$D1" FAKE_SHA="$S1" FAKE_DEPLOY_BE_FAIL=1
OUT="$(W all)"; K=$?
cek "all: backend gagal TIDAK menghentikan pipeline" '[ $K -ne 0 ] && grep -q "deploy-pipeline" "$CALLS"'
bersih
buat
W salah-argumen >/dev/null 2>&1; cek "argumen tak dikenal ditolak (kode 2)" '[ $? -eq 2 ]'
bersih

echo
printf 'Hasil: %d lulus, %d gagal\n' "$LULUS" "$GAGAL"
[ "$GAGAL" -eq 0 ]
