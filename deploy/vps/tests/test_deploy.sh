#!/usr/bin/env bash
# Uji logika skrip deploy dengan docker/curl/sudo/systemctl PALSU — tanpa menyentuh server.
# Yang diuji: urutan langkah, kapan deploy berhenti SEBELUM produksi tersentuh, pemulihan,
# dan penolakan perintah/arsip berbahaya. Yang TIDAK diuji: Docker/Postgres/systemd sungguhan
# (itu tugas `DRY_RUN` pada VPS nyata: lihat README).
#
# Jalankan di Linux (butuh GNU find/tar): bash deploy/vps/tests/test_deploy.sh
#   Di Mac:  docker run --rm -v "$PWD:/repo:ro" ubuntu:24.04 bash /repo/deploy/vps/tests/test_deploy.sh
# Kondisi uji ditulis sebagai string berkutip tunggal lalu dievaluasi oleh `cek` (eval) supaya
# ekspresinya dibaca SETELAH perintah yang diuji berjalan. Karena itu shellcheck mengira
# variabel tak dipakai (SC2034) dan ekspresi tak berkembang (SC2016) — itu disengaja.
# shellcheck disable=SC2016,SC2034,SC2155
set -uo pipefail

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VPS_DIR="${VPS_DIR:-$(cd "$AQUI/.." && pwd)}"
LULUS=0
GAGAL=0

ok()    { LULUS=$((LULUS + 1)); printf '  \033[32mlulus\033[0m  %s\n' "$1"; }
salah() { GAGAL=$((GAGAL + 1)); printf '  \033[31mGAGAL\033[0m  %s\n' "$1"; [ -n "${2:-}" ] && printf '         %s\n' "$2"; }
cek()   { if eval "$2"; then ok "$1"; else salah "$1" "kondisi: $2"; fi; }

# ------------------------------------------------------------------ lingkungan palsu
buat_lingkungan() {
  T="$(mktemp -d)"
  export HERO_HOME="$T/opt-hero" BACKUP_DIR="$T/opt-hero/data/cadangan-deploy"
  export CALLS="$T/panggilan.log" FAKE_STATE="$T/state"
  mkdir -p "$HERO_HOME/backend" "$HERO_HOME/data" "$FAKE_STATE" "$T/bin"
  : >"$CALLS"
  : >"$HERO_HOME/docker-compose.yml"
  printf 'DATABASE_URL=x\nAPP_ENV="production"\nSECRET=\x27rahasia\x27\nBIASA=tanpa-kutip\n' >"$HERO_HOME/backend/.env.prod"

  # docker palsu: mencatat setiap panggilan; perilaku diatur lewat variabel FAKE_*.
  cat >"$T/bin/docker" <<'EOF'
#!/usr/bin/env bash
echo "docker $*" >>"$CALLS"
case "$1" in
  info) exit 0 ;;
  pull) exit "${FAKE_PULL_FAIL:-0}" ;;
  login|logout|tag|image|rmi|images) exit 0 ;;
  inspect) echo "sha256:imagelama000"; exit 0 ;;
  exec)
    shift
    [ "$1" = "-i" ] && { shift; cat >/dev/null; }
    kontainer="$1"; shift
    all="$*"
    case "$all" in
      *pg_dump*) echo "-- dump palsu"; echo "SELECT 1;"; exit "${FAKE_DUMP_FAIL:-0}" ;;
      printenv*) echo "postgresql+psycopg://u:p@db:5432/hero_db"; exit 0 ;;
      *) exit 0 ;;
    esac ;;
  run)
    prev=""; for a in "$@"; do [ "$prev" = "--env-file" ] && { cp "$a" "$FAKE_STATE/envfile_gladi"; echo "$a" >"$FAKE_STATE/envfile_jalur"; }; prev="$a"; done
    [ "${FAKE_REHEARSAL_FAIL:-0}" = 1 ] && { echo "alembic: migrasi meledak" >&2; exit 1; }; exit 0 ;;
  compose)
    # catat image yang dipakai dari berkas override (argumen -f kedua)
    prev=""; override=""
    for a in "$@"; do [ "$prev" = "-f" ] && override="$a"; prev="$a"; done
    [ -f "$override" ] && grep -E '^\s+image:' "$override" | awk '{print $2}' >"$FAKE_STATE/image_sekarang"
    echo "compose-image $(cat "$FAKE_STATE/image_sekarang" 2>/dev/null)" >>"$CALLS"
    exit 0 ;;
esac
exit 0
EOF
  # curl palsu: /health bergantung pada skenario dan image yang sedang terpasang.
  cat >"$T/bin/curl" <<'EOF'
#!/usr/bin/env bash
img="$(cat "$FAKE_STATE/image_sekarang" 2>/dev/null)"
case "${FAKE_HEALTH:-ok}" in
  ok)               echo '{"status":"ok","migrations_up_to_date":true}' ;;
  bad)              echo '{"status":"degraded","migrations_up_to_date":false}'; exit 0 ;;
  bad_until_rollback)
    if [[ "$img" == *rollback* ]]; then echo '{"status":"ok","migrations_up_to_date":true}'
    else echo '{"status":"degraded"}'; fi ;;
  down)             exit 7 ;;
esac
EOF
  cat >"$T/bin/sudo" <<'EOF'
#!/usr/bin/env bash
echo "sudo $*" >>"$CALLS"
# lewati opsi sudo; jalankan perintahnya
while [ $# -gt 0 ]; do
  case "$1" in -n|-H) shift ;; -u) shift 2 ;; *) break ;; esac
done
exec "$@"
EOF
  cat >"$T/bin/systemctl" <<'EOF'
#!/usr/bin/env bash
echo "systemctl $*" >>"$CALLS"
exit "${FAKE_SYSTEMCTL_FAIL:-0}"
EOF
  printf '#!/usr/bin/env bash\nexit 0\n' >"$T/bin/logger"
  chmod +x "$T/bin/"*
  export PATH="$T/bin:$PATH"
  export HEALTH_TIMEOUT=2 HEALTH_INTERVAL=1
  unset FAKE_PIP_FAIL FAKE_PULL_FAIL FAKE_DUMP_FAIL FAKE_REHEARSAL_FAIL FAKE_HEALTH FAKE_SYSTEMCTL_FAIL DRY_RUN
}

bersihkan() { rm -rf "$T"; }
urutan() { grep -n "$1" "$CALLS" | head -1 | cut -d: -f1; }
IMAGE="ghcr.io/hero-ojk-its/hero-backend:abc123def456"

# ============================================================= deploy-backend.sh
echo "deploy-backend.sh"

buat_lingkungan
OUT="$("$VPS_DIR/deploy-backend.sh" "$IMAGE" </dev/null 2>&1)"; KODE=$?
cek "jalur sukses: keluar 0"                       '[ $KODE -eq 0 ]'
cek "cadangan database dibuat dan tidak kosong"     'ls "$BACKUP_DIR"/hero_db-*.sql.gz >/dev/null 2>&1 && [ -s "$(ls "$BACKUP_DIR"/hero_db-*.sql.gz | head -1)" ]'
cek "urutan: cadangan → gladi migrasi → ganti image" '[ "$(urutan pg_dump)" -lt "$(urutan "docker run")" ] && [ "$(urutan "docker run")" -lt "$(urutan compose-image)" ]'
cek "image baru yang dipasang"                      'grep -q "compose-image $IMAGE" "$CALLS"'
cek "status image tersimpan untuk deploy berikutnya" '[ "$(cat "$HERO_HOME/.deploy/backend-image")" = "$IMAGE" ]'
cek "image lama ditandai untuk pemulihan"           'grep -q "docker tag sha256:imagelama000 hero-backend:rollback" "$CALLS"'
cek "gladi memakai env produksi TANPA kutip (seperti compose)" 'grep -qx "APP_ENV=production" "$FAKE_STATE/envfile_gladi" && grep -qx "SECRET=rahasia" "$FAKE_STATE/envfile_gladi" && grep -qx "BIASA=tanpa-kutip" "$FAKE_STATE/envfile_gladi"'
cek "salinan env sementara (berisi rahasia) dihapus setelah selesai" '[ -s "$FAKE_STATE/envfile_jalur" ] && [ ! -e "$(cat "$FAKE_STATE/envfile_jalur")" ]'
cek "database gladi dibuang di akhir"               'grep -q "DROP DATABASE IF EXISTS hero_rehearsal" "$CALLS"'
bersihkan

buat_lingkungan
OUT="$(DRY_RUN=1 "$VPS_DIR/deploy-backend.sh" "$IMAGE" </dev/null 2>&1)"; KODE=$?
cek "DRY_RUN: keluar 0 dan gladi dijalankan"         '[ $KODE -eq 0 ] && grep -q "alembic upgrade head" "$CALLS"'
cek "DRY_RUN: produksi TIDAK diganti"                '! grep -q "compose-image" "$CALLS" && [ ! -f "$HERO_HOME/.deploy/backend-image" ]'
bersihkan

buat_lingkungan
OUT="$(FAKE_REHEARSAL_FAIL=1 "$VPS_DIR/deploy-backend.sh" "$IMAGE" </dev/null 2>&1)"; KODE=$?
cek "migrasi gagal pada salinan: deploy berhenti (≠0)" '[ $KODE -ne 0 ]'
cek "migrasi gagal: produksi TIDAK disentuh"          '! grep -q "compose-image" "$CALLS"'
cek "migrasi gagal: pesan menyebut produksi utuh"     'echo "$OUT" | grep -q "TIDAK disentuh"'
cek "migrasi gagal: database gladi tetap dibuang"     'grep -q "DROP DATABASE IF EXISTS hero_rehearsal" "$CALLS"'
bersihkan

buat_lingkungan
OUT="$(FAKE_HEALTH=bad_until_rollback "$VPS_DIR/deploy-backend.sh" "$IMAGE" </dev/null 2>&1)"; KODE=$?
cek "tidak sehat: deploy dinyatakan gagal (≠0)"       '[ $KODE -ne 0 ]'
cek "tidak sehat: image lama dipasang kembali"        '[ "$(grep -c compose-image "$CALLS")" -eq 2 ] && grep "compose-image" "$CALLS" | tail -1 | grep -q rollback'
cek "tidak sehat: pesan menyebut jalur cadangan"      'echo "$OUT" | grep -q "hero_db-"'
cek "tidak sehat: status image TIDAK diperbarui"      '[ ! -f "$HERO_HOME/.deploy/backend-image" ]'
bersihkan

buat_lingkungan
OUT="$(FAKE_HEALTH=bad "$VPS_DIR/deploy-backend.sh" "$IMAGE" </dev/null 2>&1)"; KODE=$?
cek "pemulihan pun gagal: tetap ≠0 dan memberi tahu"  '[ $KODE -ne 0 ] && echo "$OUT" | grep -q "periksa manual"'
bersihkan

buat_lingkungan
OUT="$(FAKE_PULL_FAIL=1 "$VPS_DIR/deploy-backend.sh" "$IMAGE" </dev/null 2>&1)"; KODE=$?
cek "gagal menarik image: berhenti sebelum cadangan"   '[ $KODE -ne 0 ] && ! grep -q pg_dump "$CALLS"'
bersihkan

buat_lingkungan
OUT="$(MIN_FREE_KB=999999999999 "$VPS_DIR/deploy-backend.sh" "$IMAGE" </dev/null 2>&1)"; KODE=$?
cek "disk kurang: berhenti sebelum menarik image"      '[ $KODE -ne 0 ] && ! grep -q "docker pull" "$CALLS"'
bersihkan

buat_lingkungan
OUT="$(printf 'tokenrahasia123\n' | "$VPS_DIR/deploy-backend.sh" "$IMAGE" 2>&1)"; KODE=$?
cek "token registri dari stdin dipakai login lalu logout" 'grep -q "docker login ghcr.io" "$CALLS" && grep -q "docker logout ghcr.io" "$CALLS"'
cek "token TIDAK pernah muncul di log/panggilan"        '! grep -q tokenrahasia123 "$CALLS" && ! echo "$OUT" | grep -q tokenrahasia123'
bersihkan

buat_lingkungan
for i in 1 2 3 4 5; do touch -d "2020-01-0$i" "$BACKUP_DIR/hero_db-2020010$i.sql.gz" 2>/dev/null || { mkdir -p "$BACKUP_DIR"; touch -d "2020-01-0$i" "$BACKUP_DIR/hero_db-2020010$i.sql.gz"; }; done
KEEP_DUMPS=3 "$VPS_DIR/deploy-backend.sh" "$IMAGE" </dev/null >/dev/null 2>&1
cek "cadangan lama dirotasi (hanya KEEP_DUMPS terakhir)" '[ "$(ls "$BACKUP_DIR"/hero_db-*.sql.gz | wc -l)" -eq 3 ]'
bersihkan

# ================================================================== ci-entry.sh
echo "ci-entry.sh (pintu masuk kunci deploy)"

buat_lingkungan
for jahat in \
  "bash" \
  "bash -i" \
  "cat /etc/shadow" \
  "deploy-backend ghcr.io/penyerang/hero-backend:1" \
  "deploy-backend ghcr.io/hero-ojk-its/hero-backend:ok; rm -rf /" \
  "deploy-backend ghcr.io/hero-ojk-its/hero-backend:\$(id)" \
  "deploy-backend ghcr.io/hero-ojk-its/hero-backend:a b" \
  "deploy-backend ghcr.io/hero-ojk-its/other-image:1" \
  "deploy-backend " \
  "deploy-pipeline; id" \
  "" ; do
  SSH_ORIGINAL_COMMAND="$jahat" "$VPS_DIR/ci-entry.sh" </dev/null >/dev/null 2>&1; k=$?
  cek "ditolak (126): '${jahat:-<kosong>}'" '[ $k -eq 126 ]'
done
cek "tak satu pun perintah jahat sampai ke sudo"        '! grep -q "^sudo" "$CALLS"'
SSH_ORIGINAL_COMMAND="deploy-backend $IMAGE" "$VPS_DIR/ci-entry.sh" </dev/null >/dev/null 2>&1 || true
cek "perintah sah diteruskan ke deploy-backend.sh"      'grep -q "^sudo -n .*deploy-backend.sh $IMAGE" "$CALLS"'
: >"$CALLS"
SSH_ORIGINAL_COMMAND="deploy-backend-gladi $IMAGE" "$VPS_DIR/ci-entry.sh" </dev/null >/dev/null 2>&1 || true
cek "gladi diteruskan dengan DRY_RUN=1"                 'grep -q "^sudo -n env DRY_RUN=1 .*deploy-backend.sh $IMAGE" "$CALLS"'
bersihkan

# ============================================================== deploy-pipeline.sh
echo "deploy-pipeline.sh"

buat_kode_lama() {
  mkdir -p "$HERO_HOME/hero" "$HERO_HOME/.venv/bin"
  echo "VERSI_LAMA" >"$HERO_HOME/hero/penanda.txt"
  echo "[project]" >"$HERO_HOME/pyproject.toml"
  ln -sf "$(command -v python3)" "$HERO_HOME/.venv/bin/python"
  printf '#!/usr/bin/env bash\necho "pip $*" >>"$CALLS"\nexit "${FAKE_PIP_FAIL:-0}"\n' >"$HERO_HOME/.venv/bin/pip"; chmod +x "$HERO_HOME/.venv/bin/pip"
  export HERO_USER="$(id -un)" SERVICES="hero-ml" SKIP_PIP=0 ML_HEALTH_URL="http://x/health"
}

buat_arsip() {                 # $1 = penanda versi
  rm -rf "$T/src" && mkdir -p "$T/src/pipeline/hero/bridge" "$T/src/pipeline/hero/analysis"
  : >"$T/src/pipeline/hero/__init__.py"
  echo "" >"$T/src/pipeline/hero/cli.py"
  : >"$T/src/pipeline/hero/bridge/__init__.py"; : >"$T/src/pipeline/hero/bridge/client.py"
  : >"$T/src/pipeline/hero/analysis/__init__.py"
  echo 'VERSION = "v-uji"' >"$T/src/pipeline/hero/analysis/structured.py"
  echo "$1" >"$T/src/pipeline/hero/penanda.txt"
  echo "[project]
versi = \"$1\"" >"$T/src/pipeline/pyproject.toml"
  tar czf "$T/kode.tgz" -C "$T/src" pipeline/hero pipeline/pyproject.toml
}

buat_lingkungan; buat_kode_lama; buat_arsip "VERSI_BARU"
OUT="$("$VPS_DIR/deploy-pipeline.sh" <"$T/kode.tgz" 2>&1)"; KODE=$?
cek "jalur sukses: keluar 0"                             '[ $KODE -eq 0 ]'
cek "kode baru terpasang"                                '[ "$(cat "$HERO_HOME/hero/penanda.txt")" = "VERSI_BARU" ]'
cek "kode lama dicadangkan"                              'ls "$BACKUP_DIR"/hero-kode-*.tar.gz >/dev/null 2>&1'
cek "layanan direstart"                                  'grep -q "systemctl restart hero-ml" "$CALLS"'
cek "pyproject berubah → dependensi dipasang ulang"      'grep -q "^pip install" "$CALLS"'
bersihkan

buat_lingkungan; buat_kode_lama; buat_arsip "X"
SKIP_PIP=0 "$VPS_DIR/deploy-pipeline.sh" <"$T/kode.tgz" >/dev/null 2>&1
buat_arsip "X"                 # pyproject identik dengan yang terpasang
cp "$T/src/pipeline/pyproject.toml" "$HERO_HOME/pyproject.toml"
: >"$CALLS"
"$VPS_DIR/deploy-pipeline.sh" <"$T/kode.tgz" >/dev/null 2>&1
cek "pyproject tidak berubah → TIDAK memasang ulang"     '! grep -q "^pip install" "$CALLS"'
bersihkan

# arsip berbahaya: tidak boleh mengubah apa pun
for kasus in jalan_keluar absolut tautan luar_daftar campuran; do
  buat_lingkungan; buat_kode_lama; buat_arsip "BERBAHAYA"
  rm -rf "$T/jahat" && mkdir -p "$T/jahat"
  case "$kasus" in
    jalan_keluar) mkdir -p "$T/jahat/pipeline"; echo x >"$T/jahat/x"; tar czf "$T/kode.tgz" -C "$T/jahat" --transform='s,^x$,pipeline/hero/../../../etc-palsu,' x 2>/dev/null ;;
    absolut)      echo x >"$T/jahat/x"; tar czf "$T/kode.tgz" -P --transform="s,^$T/jahat/x$,/tmp/hero-absolut-palsu," "$T/jahat/x" 2>/dev/null ;;
    tautan)       mkdir -p "$T/jahat/pipeline/hero"; : >"$T/jahat/pipeline/hero/__init__.py"; ln -s /etc/passwd "$T/jahat/pipeline/hero/pwd"; tar czf "$T/kode.tgz" -C "$T/jahat" pipeline ;;
    luar_daftar)  mkdir -p "$T/jahat/etc"; echo x >"$T/jahat/etc/cron"; tar czf "$T/kode.tgz" -C "$T/jahat" etc ;;
    # Paket sah + berkas ekstra: HANYA daftar putih yang menolaknya (pemeriksaan lain tak terpicu).
    campuran)     echo "ekstra" >"$T/src/pipeline/rahasia.txt"; tar czf "$T/kode.tgz" -C "$T/src" pipeline ;;
  esac
  OUT="$("$VPS_DIR/deploy-pipeline.sh" <"$T/kode.tgz" 2>&1)"; KODE=$?
  cek "arsip berbahaya ($kasus): ditolak"               '[ $KODE -ne 0 ]'
  cek "arsip berbahaya ($kasus): alasannya validasi arsip" 'echo "$OUT" | grep -qE "di luar pipeline|path berbahaya|tautan simbolik|tidak memuat pipeline/hero"'
  cek "arsip berbahaya ($kasus): tidak ada berkas bocor keluar" '[ ! -e /tmp/hero-absolut-palsu ] && [ ! -e "$T/etc-palsu" ]'
  cek "arsip berbahaya ($kasus): kode berjalan tak berubah" '[ "$(cat "$HERO_HOME/hero/penanda.txt")" = "VERSI_LAMA" ] && ! grep -q "systemctl restart" "$CALLS"'
  bersihkan
done


buat_lingkungan; buat_kode_lama; buat_arsip "VERSI_BARU"
OUT="$(FAKE_PIP_FAIL=1 "$VPS_DIR/deploy-pipeline.sh" <"$T/kode.tgz" 2>&1)"; KODE=$?
cek "pip install gagal: deploy gagal dan kode lama dipulihkan" '[ $KODE -ne 0 ] && [ "$(cat "$HERO_HOME/hero/penanda.txt")" = "VERSI_LAMA" ]'
bersihkan

buat_lingkungan; buat_kode_lama; buat_arsip "VERSI_BARU"
OUT="$(FAKE_SYSTEMCTL_FAIL=1 "$VPS_DIR/deploy-pipeline.sh" <"$T/kode.tgz" 2>&1)"; KODE=$?
cek "restart gagal: deploy gagal dan kode lama dipulihkan" '[ $KODE -ne 0 ] && [ "$(cat "$HERO_HOME/hero/penanda.txt")" = "VERSI_LAMA" ]'
bersihkan

buat_lingkungan; buat_kode_lama; buat_arsip "VERSI_BARU"
OUT="$(FAKE_HEALTH=down HEALTH_TIMEOUT=2 "$VPS_DIR/deploy-pipeline.sh" <"$T/kode.tgz" 2>&1)"; KODE=$?
cek "layanan analisa tak menjawab: kode lama dipulihkan"  '[ $KODE -ne 0 ] && [ "$(cat "$HERO_HOME/hero/penanda.txt")" = "VERSI_LAMA" ]'
bersihkan

buat_lingkungan; buat_kode_lama
OUT="$("$VPS_DIR/deploy-pipeline.sh" </dev/null 2>&1)"; KODE=$?
cek "arsip kosong ditolak, kode lama utuh"                '[ $KODE -ne 0 ] && [ "$(cat "$HERO_HOME/hero/penanda.txt")" = "VERSI_LAMA" ]'
bersihkan

echo
printf 'Hasil: %d lulus, %d gagal\n' "$LULUS" "$GAGAL"
[ "$GAGAL" -eq 0 ]
