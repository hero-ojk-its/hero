#!/usr/bin/env bash
# Menyambungkan API HERO ke Caddy milik Nextcloud (tanpa mengubah layanan cloud).
#
#  - Caddy Nextcloud ikut ke jaringan `hero_edge` dan mendapat alias host.docker.internal
#  - Blok baru di Caddyfile: api.<domain> → backend (/) dan layanan analisa (/api/v1/ml/*)
#  - Sebelum menimpa apa pun: berkas dicadangkan, lalu divalidasi
#
# Prasyarat: DNS A record  api.<domain>  →  IP VPS  sudah ada, agar sertifikat terbit.
#   sudo bash /opt/hero/deploy/vps/nextcloud-edge.sh [api.domain.anda]
set -euo pipefail

NC="${NC_DIR:-/home/ubuntu/nextcloud}"
API_HOST="${1:-api.mirzafathir.com}"
ML_BIND=172.17.0.1
ML_PORT=8100
TS=$(date +%Y%m%d-%H%M%S)

[[ $EUID -eq 0 ]] || { echo "Jalankan dengan sudo." >&2; exit 1; }
[[ -f "$NC/docker-compose.yml" && -f "$NC/Caddyfile" ]] || { echo "Nextcloud tidak ditemukan di $NC" >&2; exit 1; }
docker network inspect hero_edge >/dev/null 2>&1 || { echo "Jalankan bootstrap.sh dulu (hero_edge belum ada)." >&2; exit 1; }

cp "$NC/docker-compose.yml" "$NC/docker-compose.yml.bak-$TS"
cp "$NC/Caddyfile" "$NC/Caddyfile.bak-$TS"
echo "cadangan: $NC/*.bak-$TS"

if grep -q "hero_edge" "$NC/docker-compose.yml"; then
  echo "compose Nextcloud sudah memuat hero_edge — dilewati"
else
  python3 - "$NC/docker-compose.yml" <<'PY'
import sys
p = sys.argv[1]
s = open(p).read()
old_svc = "    networks:\n      - internal\n    env_file:\n      - .env"
old_top = "networks:\n  internal:\n"
assert s.count(old_svc) == 1, "blok networks caddy tidak cocok persis — periksa manual"
assert s.count(old_top) == 1, "blok networks top-level tidak cocok persis — periksa manual"
s = s.replace(old_svc,
    "    extra_hosts:\n      - \"host.docker.internal:host-gateway\"\n"
    "    networks:\n      - internal\n      - edge\n    env_file:\n      - .env", 1)
s = s.replace(old_top,
    "networks:\n  internal:\n  edge:\n    name: hero_edge\n    external: true\n", 1)
open(p, "w").write(s)
print("compose Nextcloud diperbarui")
PY
fi

if grep -q "^$API_HOST {" "$NC/Caddyfile"; then
  echo "Caddyfile sudah memuat $API_HOST — dilewati"
else
  cat >> "$NC/Caddyfile" <<CADDY

# --- HERO API (ditambahkan oleh deploy/vps/nextcloud-edge.sh) ---
$API_HOST {
    request_body {
        max_size 110MB
    }
    header {
        Strict-Transport-Security "max-age=15552000; includeSubDomains"
        -Server
    }
    encode gzip

    # Layanan analisa & harmonisasi: /api/v1/ml/* → /* di layanan ML
    handle_path /api/v1/ml/* {
        reverse_proxy host.docker.internal:$ML_PORT
    }

    # Backend FastAPI: semua yang lain
    handle {
        reverse_proxy hero_backend:8000
    }
}
CADDY
  echo "blok $API_HOST ditambahkan"
fi

echo "validasi compose dan Caddyfile…"
(cd "$NC" && docker compose config -q)
docker run --rm -e DOMAIN=cloud.mirzafathir.com -v "$NC/Caddyfile:/etc/caddy/Caddyfile:ro" \
  caddy:2-alpine caddy validate --config /etc/caddy/Caddyfile >/dev/null
echo "    valid"

echo "memuat ulang Caddy Nextcloud (sebentar; data Nextcloud tidak tersentuh)…"
(cd "$NC" && docker compose up -d caddy)
sleep 5
echo "cek Nextcloud:"
curl -sk -o /dev/null -w "    https://cloud  → HTTP %{http_code}\n" --resolve cloud.mirzafathir.com:443:127.0.0.1 https://cloud.mirzafathir.com/ || true
echo "cek API (sertifikat menyusul setelah DNS aktif):"
curl -sk -o /dev/null -w "    https://$API_HOST/health → HTTP %{http_code}\n" --resolve "$API_HOST:443:127.0.0.1" "https://$API_HOST/health" || true
