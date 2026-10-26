# HERO di server lokal — dari `adduser` sampai deploy otomatis

Panduan memindahkan backend dan lapisan data HERO dari VPS Tencent ke **server Ubuntu/Debian
milik Anda sendiri**, lengkap dengan akses dari internet dan deploy otomatis.

```
         internet                          rumah/kantor Anda
                                    ┌─────────────────────────────────┐
Vercel ──HTTPS──▶ Cloudflare ◀──────┤ cloudflared  (koneksi KELUAR)   │
(frontend)         (tunnel)         │      │                          │
                                    │      ▼ 127.0.0.1:8000           │
                                    │  hero_backend ──▶ hero_db       │
                                    │      ▲                          │
                                    │      │ /api/v1/ml/*             │
                                    │  hero-ml  (layanan analisa)     │
                                    │  hero-bridge-ekstraksi (worker) │
                                    └─────────────────────────────────┘
                                       tidak ada port router dibuka

GitHub ──(image + kode)──▶ GHCR / git ◀──tarik tiap 5 menit── hero-watch-deploy.timer
```

**Dua gagasan penting.**

1. **Akses tanpa membuka port.** Server lokal hampir pasti tanpa IP publik. `cloudflared`
   membuat koneksi **keluar** ke Cloudflare, lalu Cloudflare meneruskan permintaan lewat
   koneksi itu. Tidak ada port router yang dibuka, IP rumah Anda tidak terekspos, HTTPS
   otomatis, dan jalan juga di CGNAT.
2. **Deploy ditarik, bukan didorong.** GitHub tidak bisa menghubungi server di balik NAT.
   Jadi `hero-watch-deploy.timer` di server memeriksa GitHub tiap 5 menit: ada image/commit
   baru → deploy sendiri. Ini juga **lebih aman daripada self-hosted runner**: repo HERO
   publik, dan runner akan menjalankan kode dari pull request siapa pun di mesin Anda.

| | VPS Tencent | Server lokal |
|---|---|---|
| RAM | 1,9 GB (swap terpakai ±1,6 GB) | milik Anda — biasanya jauh lebih lega |
| Build image | di GitHub, VPS menarik | sama |
| Akses | IP publik + Caddy | Cloudflare Tunnel |
| Deploy | GitHub SSH masuk (dorong) | server memeriksa sendiri (tarik) |
| Pencarian makna e5-large | tidak muat | muat bila RAM ≥ 4 GB |

> **Sebelum memindahkan data: ini pertanyaan kepatuhan, bukan teknis.** Katalog HERO memuat
> dokumen internal DPEA yang tunduk NDA (NFR-08, NFR-09: penyimpanan dengan akses terkendali,
> tidak ada distribusi ke luar lingkungan yang disepakati). Memindahkannya ke server pribadi
> **perlu persetujuan Pak Faris**, dan sebaiknya tertulis. Untuk sementara Anda bisa
> memakai dokumen publik saja (`jdih-ojk`, `ojk-regulasi`) di server lokal.

---

## 0. Yang Anda butuhkan

- Server Ubuntu/Debian yang **menyala terus**, akses `sudo`, RAM ≥ 4 GB (≥ 8 GB bila ingin
  pencarian makna), disk ≥ 40 GB.
- Akun Cloudflare (gratis) dan domain `mirzafathir.com` — nameserver-nya akan dipindah dari
  Hostinger ke Cloudflare.
- Catatan: VPS Tencent **tetap jalan** sampai langkah 9. Tidak ada yang dimatikan lebih dulu.

Anda sudah menjalankan `sudo adduser hero`. Itu membuat user **login biasa** (home `/home/hero`,
punya kata sandi dan shell). HERO memerlukan akun **layanan**. Langkah 2 menanganinya: skrip
memakai user `hero` yang sudah ada, **mengunci kata sandinya**, dan memberinya `/opt/hero`.
Tidak perlu Anda hapus.

---

## 1. Salin skrip pemasangan ke server

**Syarat:** PR yang memuat folder `deploy/lokal/` sudah di-merge ke `main` (PR #149). Sampai itu
terjadi, folder ini hanya ada di branch `feat/deploy-server-lokal`, dan `main` tidak
memilikinya — `git clone` biasa tidak akan menemukan `install-server.sh`.

Di server (repo publik, tanpa kredensial):

```bash
sudo apt-get update && sudo apt-get install -y git

# Setelah PR di-merge (disarankan):
git clone --depth 1 https://github.com/hero-ojk-its/hero.git /tmp/hero-src

# SEBELUM di-merge (sementara): ambil branch-nya
git clone --depth 1 --branch feat/deploy-server-lokal https://github.com/hero-ojk-its/hero.git /tmp/hero-src
```

## 2. Jalankan pemasang

```bash
# Setelah PR di-merge:
sudo bash /tmp/hero-src/deploy/lokal/install-server.sh

# Sebelum di-merge, beri tahu pemasang branch mana yang dipakai (ia juga mengklon repo ke /opt/hero/src):
sudo REPO_BRANCH=feat/deploy-server-lokal bash /tmp/hero-src/deploy/lokal/install-server.sh
```

Yang dipasang: paket sistem + Tesseract, Docker Engine resmi, user `hero` (kata sandi dikunci),
tata letak `/opt/hero`, klon repo di `/opt/hero/src`, venv lapisan data, skrip deploy di
`/opt/hero/ci` (**milik root**, supaya layanan tidak bisa mengubah kode deploy-nya sendiri),
dan unit systemd. Idempoten — aman diulang.

Verifikasi:

```bash
docker --version && docker compose version
sudo -u hero /opt/hero/.venv/bin/hero version     # harus menyebut tesseract siap
ls -la /opt/hero
```

## 3. Isi dua berkas rahasia

Keduanya diperlukan dan **perannya berbeda**. `docker compose` hanya membaca `/opt/hero/.env`
untuk mengisi `${…}`; ia tidak membaca `.env.prod` untuk itu.

| Berkas | Untuk |
|---|---|
| `/opt/hero/.env` | kata sandi Postgres (dipakai compose) + variabel `HERO_*` lapisan data |
| `/opt/hero/backend/.env.prod` | lingkungan di dalam kontainer backend |

```bash
openssl rand -hex 32     # jalankan 3×: POSTGRES_PASSWORD, SECRET_KEY, INTERNAL_API_KEY
sudo nano /opt/hero/.env
sudo nano /opt/hero/backend/.env.prod
```

Tiga nilai **harus konsisten**, kalau tidak backend gagal tersambung atau worker ditolak 401:

- `POSTGRES_PASSWORD` (`.env`) = kata sandi di `DATABASE_URL` (`.env.prod`) = di `HERO_PG_DSN` (`.env`)
- `INTERNAL_API_KEY` (`.env.prod`) = `HERO_BACKEND_INTERNAL_KEY` (`.env`)
- `CORS_ORIGINS` (`.env.prod`) memuat asal frontend Anda

Jaga modenya 600: `sudo chmod 600 /opt/hero/.env /opt/hero/backend/.env.prod`

## 4. Nyalakan database

```bash
cd /opt/hero
sudo docker compose up -d db
sudo docker compose ps
sudo docker exec hero_db psql -U hero_user -d hero_db -c 'select extname from pg_extension'
```

`vector` harus muncul (dipasang otomatis oleh `init_db/01_enable_pgvector.sql`).

## 5. Deploy backend pertama kali

```bash
sudo /opt/hero/ci/watch-deploy.sh backend
```

Skrip ini: menarik image dari GHCR → `pg_dump` → **melatih migrasi pada salinan database**
(gagal di sini berarti berhenti, produksi tak tersentuh) → menjalankan backend → memeriksa
`/health` → mengembalikan versi lama bila tidak sehat.

```bash
curl -s http://127.0.0.1:8000/health | python3 -m json.tool
```

Harus `"status": "ok"` dan `"migrations_up_to_date": true`.

> **Bila gagal "digest tidak terbaca":** paket GHCR masih privat. Buka
> `github.com/orgs/hero-ojk-its/packages` → `hero-backend` → *Package settings* → ubah
> visibilitas menjadi **public** (image tidak memuat rahasia; rahasia ada di `.env.prod`).
> Alternatif: simpan PAT `read:packages` di `/opt/hero/ci/ghcr-token` (mode 600).
>
> **Bila paketnya belum ada sama sekali** (kasus pertama kali): image `ghcr.io/hero-ojk-its/hero-backend:main`
> hanya dibangun oleh workflow *Deploy VPS*, dan itu baru ada di `main` setelah PR di-merge. Dari komputer
> yang sudah login `gh` (bukan server):
>
> ```bash
> gh variable set DEPLOY_VPS_ENABLED --body true      # hanya membangun image; JANGAN set DEPLOY_VPS_SSH
> gh workflow run "Deploy VPS" -f komponen=backend    # membangun sekarang, tanpa menunggu merge berikutnya
> gh run watch                                        # tunggu selesai (±3–6 menit)
> ```
>
> Setelah itu ubah paketnya menjadi publik (lihat di atas). Selanjutnya setiap merge ke `main` yang
> lolos Backend CI membangun image baru otomatis. `DEPLOY_VPS_SSH` sengaja dibiarkan mati: itu
> jalur dorong SSH ke VPS, yang tidak ada gunanya (dan akan gagal) untuk server di balik NAT.

## 6. Akses dari internet (Cloudflare Tunnel)

### 6a. Pindahkan DNS ke Cloudflare (sekali)

1. Daftar/masuk Cloudflare → **Add a site** → `mirzafathir.com` → paket **Free**.
2. Cloudflare memindai DNS yang ada. **Periksa daftarnya** dan pastikan record Nextcloud serta
   record lain ikut terbawa, supaya tidak ada layanan yang mati saat nameserver berpindah.
3. Cloudflare memberi dua nameserver. Di **Hostinger** (pengelola `mirzafathir.com` saat ini,
   nameserver `ns1/ns2.dns-parking.com`), ganti nameserver domain ke dua nilai itu.
4. Tunggu propagasi (biasanya < 1 jam). Cek: `dig +short NS mirzafathir.com`.

### 6b. Pasang cloudflared di server

```bash
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg \
  | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main" \
  | sudo tee /etc/apt/sources.list.d/cloudflared.list
sudo apt-get update && sudo apt-get install -y cloudflared

cloudflared tunnel login                 # buka URL yang muncul, pilih mirzafathir.com
cloudflared tunnel create hero
sudo mkdir -p /etc/cloudflared
```

`sudo nano /etc/cloudflared/config.yml`:

```yaml
tunnel: hero
credentials-file: /root/.cloudflared/<ID-TUNNEL>.json   # ID dari perintah create
ingress:
  - hostname: api.mirzafathir.com
    service: http://127.0.0.1:8000
  - service: http_status:404
```

```bash
cloudflared tunnel route dns hero api.mirzafathir.com   # membuat CNAME di Cloudflare
sudo cloudflared service install
sudo systemctl enable --now cloudflared
sudo systemctl status cloudflared --no-pager | head -5
```

Uji **dari luar** (mis. dari Mac Anda):

```bash
curl -s https://api.mirzafathir.com/health | python3 -m json.tool
```

Begitu ini menjawab dari server lokal, `VITE_API_BASE_URL` di Vercel **tidak perlu diubah** —
URL-nya sama, isinya yang berpindah.

> **Catatan:** selama langkah 6a–6b, `api.mirzafathir.com` masih menunjuk VPS. Setelah
> `tunnel route dns` dibuat, Cloudflare mengarahkannya ke tunnel. Lakukan saat lalu lintas sepi,
> dan siapkan rencana kembali: hapus CNAME tunnel lalu buat A record ke `43.128.102.71`.

## 7. Lapisan data (layanan analisa + worker)

```bash
sudo systemctl enable --now hero-ml hero-bridge-ekstraksi
cd /opt/hero && sudo -u hero -H /opt/hero/.venv/bin/hero bridge status
```

Yang harus terlihat: `/health` ok, kunci API internal **diterima**, kontrak pasal **Langkah 13**.

Indeks pencarian (sekali, agak berat):

```bash
cd /opt/hero && sudo -u hero -H /opt/hero/.venv/bin/hero vector build --lsa-only
sudo systemctl restart hero-ml
curl -s http://172.17.0.1:8100/health | python3 -m json.tool
```

Dengan RAM ≥ 8 GB, pencarian makna juga mungkin: pasang ekstra `semantic`, lalu `hero vector build`
tanpa `--lsa-only`. Di VPS lama ini tidak muat.

## 8. Nyalakan deploy otomatis

Setelah langkah 5 dan 7 berhasil sekali secara manual:

```bash
sudo systemctl enable --now hero-watch-deploy.timer
systemctl list-timers hero-watch-deploy.timer --no-pager
```

Sejak ini, setiap merge ke `main` yang lolos CI akan tiba sendiri di server dalam ±5 menit.

```bash
sudo LAPOR_SAJA=1 /opt/hero/ci/watch-deploy.sh    # periksa tanpa deploy
sudo journalctl -u hero-watch-deploy -n 40        # riwayat
sudo systemctl disable --now hero-watch-deploy.timer   # tombol berhenti
```

## 9. Pindahkan data dari VPS (setelah izin di langkah 0)

Di VPS: `docker exec hero_db sh -c 'pg_dump -U $POSTGRES_USER $POSTGRES_DB' | gzip > ~/pindah.sql.gz`

Lalu salin ke server lokal dan pulihkan:

```bash
scp ubuntu@43.128.102.71:~/pindah.sql.gz /tmp/
sudo docker compose stop backend
gunzip -c /tmp/pindah.sql.gz | sudo docker exec -i hero_db psql -U hero_user -d hero_db
sudo docker compose start backend
```

Ikut dipindah: `storage_data` (PDF backend), `/opt/hero/data/` (katalog SQLite, knowledge base),
dan `hero_bridge.db`. Jalankan `hero bridge sinkron` sesudahnya. **Matikan VPS hanya setelah
server lokal terbukti jalan beberapa hari.**

---

## Pemeliharaan

| Kebutuhan | Perintah |
|---|---|
| Status semua | `sudo docker compose ps && systemctl status hero-ml hero-bridge-ekstraksi cloudflared --no-pager \| head -20` |
| Log backend | `sudo docker logs hero_backend -n 50` |
| Log deploy | `sudo journalctl -u hero-watch-deploy -n 50` |
| Cadangan | otomatis sebelum tiap deploy di `/opt/hero/data/cadangan-deploy/` (14 DB, 5 kode terakhir) |
| Kembali ke versi lama | `sudo /opt/hero/ci/deploy-backend.sh ghcr.io/hero-ojk-its/hero-backend:<sha12-lama>` |
| Gladi tanpa menyentuh produksi | `sudo DRY_RUN=1 /opt/hero/ci/deploy-backend.sh <image>` |

Cadangan ke luar server (penting: cadangan di mesin yang sama tidak menolong bila diskmu mati)
belum diotomatiskan di sini. `backend/deploy/backup.sh` dan `pipeline/deploy/` memuat skrip
rclone ke Nextcloud yang bisa dipakai ulang.

## Batas dan risiko — baca

1. **Belum pernah dijalankan di server lokal sungguhan.** Logika skrip diuji dengan
   `docker`/`curl`/`git`/`systemctl` palsu (99 tes di dua berkas uji, plus *mutation test*), dan
   `docker compose config` divalidasi di CI. Tetapi jalannya di mesin Anda baru terbukti saat
   langkah 2–5 dijalankan. Lakukan berurutan dan berhenti di langkah yang hasilnya tidak sesuai.
2. **Server rumah = tanggung jawab Anda.** Tidak ada SLA, UPS, atau pengganti bila listrik/
   internet mati. Untuk demo ke mitra, pastikan ada rencana cadangan (VPS tetap menyala, atau
   jadwalkan demo saat Anda bisa memantau).
3. **`main` tanpa proteksi.** Siapa pun dengan akses tulis bisa push langsung, dan dalam ±5 menit
   itu berjalan di server Anda. Aktifkan *Branch protection* (wajib PR + status check).
4. **Timer menjalankan skrip sebagai root.** Skrip ada di `/opt/hero/ci` milik root dan tidak
   dapat ditulis user layanan. Jangan menaruh skrip deploy di direktori yang bisa ditulis `hero`.
5. **Image GHCR publik** (bila Anda memilih itu) berarti siapa pun bisa menariknya. Kodenya
   memang sudah publik, dan rahasia tidak ada di dalam image — tetapi putuskan secara sadar.
6. **Yang belum diotomatiskan:** unit systemd, `config/*.yaml`, `.env*`, dan konfigurasi
   cloudflared. Perubahan di sana tetap manual (dan memang sebaiknya begitu).
