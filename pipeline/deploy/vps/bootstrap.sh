#!/usr/bin/env bash
# HERO — pemasangan di VPS Ubuntu 24.04 (dijalankan DI VPS, sebagai sudo).
#
# Prasyarat: kode sudah di-rsync ke /opt/hero (pipeline/) dan /opt/hero/backend
# (backend/). Lihat langkah rsync di deploy/vps/README.md.
#
# Idempoten: rahasia dibuat SEKALI dan tidak pernah ditimpa; aman dijalankan ulang.
#   sudo bash /opt/hero/deploy/vps/bootstrap.sh
set -euo pipefail

HERO_HOME=/opt/hero
HERO_USER=hero
ML_BIND=172.17.0.1          # gateway docker0: hanya dapat dicapai container, bukan internet
ML_PORT=8100
CORS_ORIGIN="https://hero-ojk.vercel.app,https://hero-ojk-its.github.io"

[[ $EUID -eq 0 ]] || { echo "Jalankan dengan sudo." >&2; exit 1; }
command -v docker >/dev/null || { echo "Docker belum terpasang." >&2; exit 1; }

log() { echo; echo "==> $*"; }

log "1/8 Paket sistem"
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip openssl \
  tesseract-ocr tesseract-ocr-ind tesseract-ocr-eng poppler-utils rsync ca-certificates >/dev/null

log "2/8 User sistem dan direktori"
id -u "$HERO_USER" >/dev/null 2>&1 || useradd --system --home-dir "$HERO_HOME" --shell /usr/sbin/nologin "$HERO_USER"
mkdir -p "$HERO_HOME"/data/{staging,logs,export,knowledge_base,vectors,models} "$HERO_HOME/config"
# Seluruh /opt/hero: user hero perlu menulis .venv dan data. Dijalankan ulang = aman.
chown -R "$HERO_USER:$HERO_USER" "$HERO_HOME"

log "3/8 Rahasia (dibuat sekali)"
if [[ ! -f "$HERO_HOME/.env" ]]; then
  PG_PASS=$(openssl rand -hex 24)
  IKEY=$(openssl rand -hex 32)
  SKEY=$(openssl rand -hex 32)
  umask 077
  cat > "$HERO_HOME/.env" <<ENV
# Dibaca docker compose (interpolasi) DAN worker lapisan data. Mode 600.
POSTGRES_USER=hero_user
POSTGRES_PASSWORD=$PG_PASS
POSTGRES_DB=hero_db
HERO_BACKEND_URL=http://127.0.0.1:8000
HERO_BACKEND_INTERNAL_KEY=$IKEY
HERO_PG_DSN=postgresql://hero_user:$PG_PASS@127.0.0.1:5432/hero_db
HERO_ML_CORS=$CORS_ORIGIN
ENV
  mkdir -p "$HERO_HOME/backend"
  cat > "$HERO_HOME/backend/.env.prod" <<ENV
APP_ENV=production
APP_PORT=8000
SECRET_KEY=$SKEY
INTERNAL_API_KEY=$IKEY
AUTH_ENABLED=false
EXPOSE_API_DOCS=false
CORS_ORIGINS=$CORS_ORIGIN
CRAWLER_BACKEND=simple_http
CRAWL_ALLOW_PRIVATE_NETWORKS=false
MAX_UPLOAD_MB=100
UVICORN_WORKERS=1
FORWARDED_ALLOW_IPS=172.16.0.0/12
ENV
  chown "$HERO_USER:$HERO_USER" "$HERO_HOME/.env"
  chmod 600 "$HERO_HOME/.env" "$HERO_HOME/backend/.env.prod"
  echo "    dibuat: $HERO_HOME/.env dan $HERO_HOME/backend/.env.prod (mode 600)"
else
  echo "    sudah ada, dilewati"
fi

log "4/8 Konfigurasi lapisan data untuk VPS (RAM 2 GB: tanpa e5-large)"
CFG="$HERO_HOME/config/sources.yaml"
if [[ -f "$CFG" ]]; then
  sed -i 's/^  semantic_model: e5-large/  semantic_model: minilm/' "$CFG"
fi

log "5/8 Jaringan docker bersama (dipakai Caddy Nextcloud untuk meneruskan API)"
docker network inspect hero_edge >/dev/null 2>&1 || docker network create hero_edge >/dev/null
echo "    hero_edge siap"

log "6/8 Virtual environment + paket HERO"
if [[ ! -x "$HERO_HOME/.venv/bin/python" ]]; then
  sudo -u "$HERO_USER" python3 -m venv "$HERO_HOME/.venv"
fi
sudo -u "$HERO_USER" "$HERO_HOME/.venv/bin/python" -m pip install -q --upgrade pip
sudo -u "$HERO_USER" "$HERO_HOME/.venv/bin/python" -m pip install -q -e "$HERO_HOME[api,vector,pg]"
(cd "$HERO_HOME" && sudo -u "$HERO_USER" "$HERO_HOME/.venv/bin/hero" version)

log "7/8 Backend + Postgres (docker compose)"
install -m 0644 "$HERO_HOME/deploy/vps/docker-compose.yml" "$HERO_HOME/docker-compose.yml"
cd "$HERO_HOME"
docker compose up -d --build
echo "    menunggu backend sehat…"
for i in $(seq 1 60); do
  if curl -fsS -m 3 http://127.0.0.1:8000/health >/dev/null 2>&1; then
    echo "    backend hidup setelah $((i*3)) detik"; break
  fi
  sleep 3
  if [[ $i -eq 60 ]]; then echo "    backend belum sehat — cek: docker compose logs backend" >&2; exit 1; fi
done
curl -fsS http://127.0.0.1:8000/health | python3 -c "import json,sys; d=json.load(sys.stdin); print('    status:', d['status'], '| migrasi:', d['migrations_up_to_date'], '| crawler:', d['crawler_backend'])"

log "8/8 Layanan systemd: worker ekstraksi, layanan analisa, sinkron berkala"
S="$HERO_HOME/deploy/systemd"
# Layanan analisa hanya dibuka ke jembatan docker0 — Caddy (container) yang memanggilnya.
sed -i "s|ExecStart=.*hero bridge serve.*|ExecStart=$HERO_HOME/.venv/bin/hero bridge serve --host $ML_BIND --port $ML_PORT --cors $CORS_ORIGIN|" "$S/hero-ml.service"
for u in hero-bridge-ekstraksi.service hero-ml.service hero-bridge-sinkron.service hero-bridge-sinkron.timer; do
  install -m 0644 "$S/$u" "/etc/systemd/system/$u"
done
systemctl daemon-reload
systemctl enable --now hero-bridge-ekstraksi.service hero-ml.service hero-bridge-sinkron.timer

# Firewall: SSH, HTTP, HTTPS. Port lain tertutup. Docker menerbitkan port lewat
# iptables sendiri, jadi aturan ini melindungi layanan OS, bukan kontainer
# yang dipublikasikan ke 0.0.0.0 (tidak ada yang seperti itu di sini).
if ufw status | grep -q inactive; then
  ufw allow OpenSSH >/dev/null
  ufw allow 80/tcp >/dev/null
  ufw allow 443/tcp >/dev/null
  ufw --force enable >/dev/null
  echo "    ufw diaktifkan: OpenSSH, 80, 443"
fi

cat <<EOF

Pemasangan dasar selesai.
  Backend (loopback) : http://127.0.0.1:8000/health
  Analisa (docker0)  : http://$ML_BIND:$ML_PORT/health   (diakses Caddy, bukan publik)
  Rahasia            : $HERO_HOME/.env · $HERO_HOME/backend/.env.prod  (jangan disalin ke chat/repo)

Langkah berikutnya:
  sudo bash $HERO_HOME/deploy/vps/nextcloud-edge.sh   # sambungkan api.<domain> ke Caddy
  sudo -u $HERO_USER $HERO_HOME/.venv/bin/hero bridge status
EOF
