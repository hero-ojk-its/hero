# RUNBOOK DEPLOYMENT VPS — HERO Backend
> **Panduan Resmi Kesiapan & Operasional Produksi (Fase 1)**  
> **Target Audiens:** Tim DevOps/Infra & Tim Backend Engineer  
> **Stack:** FastAPI · PostgreSQL 15 · Caddy 2 Reverse Proxy · Docker Compose

---

## 1. Prasyarat VPS & Spesifikasi Minimum

Untuk menjalankan HERO Backend dengan lancar pada target demo dan operasional Fase 1:

| Komponen | Spesifikasi Minimum | Rekomendasi Produksi |
|---|---|---|
| **OS** | Ubuntu 22.04 LTS / Debian 12 | Ubuntu 24.04 LTS |
| **CPU** | 2 vCPU | 4 vCPU |
| **RAM** | 4 GB | 8 GB (ekstraksi PDF & full-text search) |
| **Penyimpanan** | 40 GB NVMe / SSD | 100 GB NVMe SSD |
| **Docker Engine** | Docker Engine 24.0+ | Docker Engine 26.0+ |
| **Compose** | Docker Compose v2.20+ (Plugin) | Docker Compose v2.27+ |
| **Firewall (UFW)** | Port 22 (SSH), 80 (HTTP), 443 (HTTPS) | Port 5432 & 8000 **WAJIB DITUTUP** dari publik |

### Pengaturan Firewall (UFW)
```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status verbose
```

---

## 2. Konfigurasi DNS

Arahkan domain/subdomain API ke IP Publik VPS Anda:
- **Tipe Record:** `A` (atau `CNAME` bila menggunakan alias)
- **Nama Host:** `api.hero-regulasi.id` (atau subdomain yang disepakati)
- **Target Value:** `<IP_PUBLIK_VPS>`
- **TTL:** 300 detik (untuk propagasi cepat)

*Pastikan propagasi DNS telah selesai sebelum menyalakan Caddy agar sertifikat HTTPS Let's Encrypt dapat diterbitkan secara otomatis.*

---

## 3. Persiapan Repositori & Kunci Rahasia (.env.prod)

### 3.1 Clone Repositori
```bash
cd /opt
sudo git clone <URL_REPO_HERO_BACKEND> hero-backend
cd hero-backend
sudo chown -R $USER:$USER /opt/hero-backend
```

### 3.2 Pembuatan Token & Kunci Rahasia
Jalankan perintah Python berikut untuk menghasilkan kunci acak dengan entropi tinggi (minimal 32 karakter):
```bash
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(48))"
python3 -c "import secrets; print('INTERNAL_API_KEY=' + secrets.token_urlsafe(48))"
python3 -c "import secrets; print('POSTGRES_PASSWORD=' + secrets.token_urlsafe(32))"
```

### 3.3 Pembuatan Hash Password untuk Basic Auth Dokumentasi API (Swagger/ReDoc)
Caddy melindungi endpoint `/docs`, `/redoc`, dan `/openapi.json` menggunakan Basic Auth:
```bash
docker run --rm caddy:2 caddy hash-password --plaintext "PasswordRahasiaAnda123!"
```
*Catat string hash yang dihasilkan (mis. `$2a$14$...`).*

### 3.4 Menyusun `.env.prod`
Salin template dan edit dengan nilai rahasia di atas:
```bash
cp .env.prod.example .env.prod
chmod 600 .env.prod
nano .env.prod
```

Pastikan variabel-variabel kunci terisi dengan benar:
```ini
APP_ENV=production
API_DOMAIN=api.hero-regulasi.id
CORS_ORIGINS=https://hero-frontend.vercel.app

POSTGRES_USER=hero_user
POSTGRES_PASSWORD=<password_dari_langkah_3.2>
POSTGRES_DB=hero_db
DATABASE_URL=postgresql+psycopg://hero_user:<password_dari_langkah_3.2>@db:5432/hero_db

SECRET_KEY=<secret_key_dari_langkah_3.2>
INTERNAL_API_KEY=<internal_key_dari_langkah_3.2>

DOCS_BASIC_AUTH_USER=hero-team
DOCS_BASIC_AUTH_HASH=<hash_dari_langkah_3.3>

LOCAL_SOURCE_ROOTS=/app/sources
PROTECT_NON_PUBLIC_WHEN_AUTH_DISABLED=true
CRAWL_ALLOW_PRIVATE_NETWORKS=false
```

---

## 4. Menjalankan Layanan Produksi (Docker Compose)

Jalankan perintah Compose dengan berkas override produksi:
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Arsitektur yang berjalan:
1. **`caddy`**: Menerima trafik 80/443, mengelola HTTPS Let's Encrypt otomatis, membatasi request body hingga 110MB, memproteksi Swagger dengan Basic Auth, dan meneruskan trafik ke backend.
2. **`backend`**: FastAPI berjalan di port privat `127.0.0.1:8000`, kode dari container image (tanpa bind mount), volume storage bernama `storage_data`. Otomatis menjalankan `alembic upgrade head` sebelum uvicorn melayani request.
3. **`db`**: PostgreSQL 15 + pgvector, port 5432 **tidak di-expose** ke host.

---

## 5. Verifikasi Kesehatan & Smoke Test

### 5.1 Cek Status Container
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
```
Pastikan seluruh container (`backend`, `db`, `caddy`) berstatus `Up` / `healthy`.

### 5.2 Cek Endpoint `/health`
```bash
curl -i https://api.hero-regulasi.id/health
```
Contoh respons sehat (HTTP 200):
```json
{
  "status": "ok",
  "version": "0.8.0",
  "app_env": "production",
  "database": "connected",
  "alembic_revision": "f1a2b3c4d5e6",
  "alembic_head": "f1a2b3c4d5e6",
  "migrations_up_to_date": true,
  "storage_writable": true,
  "crawler_backend": "simple_http",
  "crawler_loaded": true,
  "auth_enabled": false,
  "protect_non_public": true
}
```

*Keterangan Key Health:*
- `status`: `"ok"` jika normal, `"degraded"` bila migrasi tertinggal namun DB aktif.
- `version`: Versi rilis aplikasi (`0.8.0`).
- `migrations_up_to_date`: `true` menandakan skema DB telah sinkron dengan Alembic head.
- `storage_writable`: `true` memastikan volume storage dapat ditulisi dan dibaca.
- `protect_non_public`: `true` menandakan proteksi NDA aktif untuk dokumen non-publik.

### 5.3 Jalankan Smoke Test Jarak Jauh (Dari Laptop Developer)
Gunakan skrip smoke test Fase 2 untuk memvalidasi seluruh fungsionalitas backend (S01–S22):
```bash
# Pengujian standar (bila AUTH_ENABLED=false):
python scripts/smoke_fase2.py --base-url https://api.hero-regulasi.id

# Menonaktifkan pengujian harmonisasi per pasal (S22):
python scripts/smoke_fase2.py --base-url https://api.hero-regulasi.id --tanpa-harmonisasi

# Menentukan dokumen uji spesifik (doc_id untuk analisa dan draft_id untuk harmonisasi):
python scripts/smoke_fase2.py --base-url https://api.hero-regulasi.id --doc-id 12 --draft-id 15

# Bila AUTH_ENABLED=true (gunakan token JWT pengguna, misal peran Analis atau Admin Sistem):
# PowerShell:
$env:HERO_SMOKE_TOKEN = "<isi_token_jwt_anda>"
python scripts/smoke_fase2.py --base-url https://api.hero-regulasi.id

# Linux / macOS (Bash):
HERO_SMOKE_TOKEN="<isi_token_jwt_anda>" python scripts/smoke_fase2.py --base-url https://api.hero-regulasi.id
```

#### Catatan Efek Samping dan Metode HTTP
- **S22 (`POST /api/v1/ml/harmonisasi/{id}`)** adalah **satu-satunya** permintaan non-GET dalam smoke test. Permintaan ini hanya menghitung temuan harmonisasi per pasal draft terhadap korpus regulasi yang diizinkan, dengan efek samping berupa penyimpanan cache/riwayat eksekusi dan pencatatan audit log (`RUN_HARMONIZATION`) yang serupa dengan S06.
- Pengecualian ini dapat dinonaktifkan sepenuhnya menggunakan flag `--tanpa-harmonisasi` (S22 akan otomatis berstatus `LEWATI "dinonaktifkan"` tanpa melakukan request POST apapun).
- Selain S22, seluruh pengujian (S01–S21) sepenuhnya bersifat **hanya-baca (read-only)** menggunakan metode `HTTP GET`.

#### Daftar Pengujian Smoke Test (S01–S22)
| Kode | Endpoint / Cek | Keterangan & Tujuan |
|---|---|---|
| **S01** | `GET /health` | Memeriksa status service, DB, dan sinkronisasi revisi Alembic target. |
| **S02** | `GET /api/v1/auth/me` | Memeriksa ketersediaan konfigurasi autentikasi pengguna. |
| **S03** | `GET /api/v1/ml/health` | Memeriksa status kesiapan layanan ML gateway. |
| **S04** | Pilih dokumen uji | Auto-detect dokumen publik aktif berstatus `terindeks` atau `perlu_koreksi`. |
| **S05** | `GET /documents/{id}/versi` | Memeriksa struktur relasi versi dokumen (induk, diubah, dicabut). |
| **S06** | `GET /ml/analisa/{id}` (panggilan 1) | Eksekusi analisa pertama (menguji respons ML atau fallback cache/riwayat). |
| **S07** | `GET /ml/analisa/{id}` (panggilan 2) | Memeriksa mekanisme cache hit (`cache.hit=true`). |
| **S08** | `GET /documents/{id}/analisa/banding` | Memeriksa ketersediaan analisa deterministik komparasi regulasi. |
| **S09** | `GET /documents/{id}/analisa/riwayat` | Memeriksa pencatatan riwayat eksekusi analisa append-only. |
| **S10** | `GET .../riwayat/{run_id}` | Memeriksa detail run analisa beserta parameter reproduksibilitas. |
| **S11** | `GET .../ekspor?format=json` | Memvalidasi fungsi ekspor analisa dalam format JSON. |
| **S12** | `GET .../ekspor?format=csv` | Memvalidasi file CSV ekspor analisa (UTF-8 with BOM). |
| **S13** | `GET .../ekspor?format=docx` | Memvalidasi dokumen Word DOCX hasil ekspor analisa. |
| **S14** | `GET /api/v1/audit-logs` | Memverifikasi pencatatan audit trail aksi `RUN_ANALYSIS`. |
| **S15** | Penjaga non-publik | Memastikan dokumen `non_publik` dilindungi HTTP 403 saat auth nonaktif. |
| **S16** | `GET /api/v1/dashboard/summary` | Memastikan enum status keberlakuan memuat `belum_berlaku` (Langkah 26). |
| **S17** | `GET /api/v1/dashboard/corong` | Memvalidasi invarian corong scan dan dokumen per sumber (Langkah 27). |
| **S18** | `GET /dashboard/corong?format=csv` | Memvalidasi ekspor CSV corong ber-BOM, baris `TOTAL`, dan `filename*=`. |
| **S19** | `GET /ingest/failures (filter)` | Memvalidasi filter `reason_code=pdf_rusak&pdf_terenkripsi` (Langkah 26). |
| **S20** | `GET /api/v1/categories/tree` | Memastikan tiap node memuat `jumlah_dokumen` & `classification_rule` (Langkah 28). |
| **S21** | Kategori 'Tanpa Tahun' | Memeriksa akumulasi dokumen salah kamar pada folder "Tanpa Tahun". |
| **S22** | Harmonisasi per pasal | Memvalidasi hasil `POST /ml/harmonisasi/{id}` dan keabsahan hyperlink dokumen pembanding. |

#### Arti Peringatan (`PERINGATAN`) dan Perintah Tindak Lanjut
1. **`PERINGATAN: cek analisa/riwayat/ekspor (S05–S13) tidak dijalankan karena tidak ada dokumen uji...`**
   - **Penyebab**: Belum ada dokumen publik aktif terindeks di database.
   - **Tindak Lanjut**: Unggah minimal satu dokumen melalui dashboard/API, atau jalankan dengan parameter `--doc-id N`.
2. **`PERINGATAN: N dokumen di 'Tanpa Tahun' — jalankan scripts/relokasi_kategori.py (dry-run dulu).`**
   - **Penyebab**: Terdapat dokumen yang terklasifikasi ke kategori "Tanpa Tahun" akibat penempatan historis sebelum perbaikan nomor/tahun.
   - **Tindak Lanjut**:
     ```bash
     docker compose exec backend python scripts/relokasi_kategori.py          # dry-run
     docker compose exec backend python scripts/relokasi_kategori.py --apply  # eksekusi relokasi
     ```
3. **`PERINGATAN: N hasil scan belum ditarik ke KB — Pak Faris meminta semua hasil scan masuk KB (Weekly #7).`**
   - **Penyebab**: Terdapat kandidat regulasi hasil crawling yang masih berstatus `belum_ditarik`.
   - **Tindak Lanjut**: Tarik kandidat dokumen scan ke Knowledge Base via antarmuka Frontend atau API `POST /api/v1/scan/{session_id}/pull`.
4. **`PERINGATAN: N dokumen belum diperiksa proteksi PDF — jalankan scripts/backfill_pdf_info.py --apply.`**
   - **Penyebab**: Dokumen lama belum memiliki atribut `pdf_terproteksi` (Langkah 27).
   - **Tindak Lanjut**:
     ```bash
     docker compose exec backend python scripts/backfill_pdf_info.py --apply
     ```

#### Urutan Pasca-Deploy Fase 2
Setelah kode baru dideploy ke server VPS, jalankan langkah pemeliharaan dan verifikasi berikut secara berurutan:
1. **Cek Kesehatan Backend**:
   Pastikan endpoint `/health` mengembalikan HTTP 200 dengan status `ok`, `migrations_up_to_date: true`, dan `alembic_revision` sama dengan revisi head (`c5d6e7f8a9b0`).
2. **Backfill Proteksi PDF**:
   Jalankan inspeksi proteksi PDF untuk dokumen yang belum diperiksa:
   ```bash
   docker compose exec backend python scripts/backfill_pdf_info.py --apply
   ```
3. **Relokasi Kategori Dokumen**:
   Pindahkan dokumen yang salah kamar (mis. "Tanpa Tahun") ke kategori segmen yang sesuai:
   ```bash
   # Langkah a: periksa kandidat dokumen
   docker compose exec backend python scripts/relokasi_kategori.py
   # Langkah b: terapkan perubahan
   docker compose exec backend python scripts/relokasi_kategori.py --apply
   ```
4. **Eksekusi Smoke Test Fase 2**:
   Jalankan smoke test dari mesin pengembang dengan target **0 GAGAL**:
   ```bash
   python scripts/smoke_fase2.py --base-url https://api.hero-regulasi.id
   ```
5. **Tindak Lanjuti Peringatan**:
   Periksa output setelah baris `RINGKASAN`, lalu jalankan tindak lanjut perbaikan jika ada baris `PERINGATAN` yang muncul.

### 5.4 Uji Fallback ML Mati (#83)
Prosedur verifikasi ketahanan sistem ketika layanan ekstraksi/analisa ML tidak tersedia:
1. Jalankan `smoke_fase2.py` saat layanan ML hidup, supaya hasil analisa tersimpan di database dan cache.
2. Hentikan layanan ML pada worker/bridge:
   ```bash
   hero bridge serve --stop   # atau hentikan proses layanan ML
   ```
3. Jalankan lagi smoke test:
   ```bash
   python scripts/smoke_fase2.py --base-url https://api.hero-regulasi.id
   ```
   Pastikan cek **S06** tetap berstatus **OK** dengan keterangan `"jalur ML mati"` dan `cache.basi=true` (menggunakan cache riwayat sebelumnya).
4. Nyalakan kembali layanan ML:
   ```bash
   hero bridge serve
   ```

### 5.5 Memeriksa Log Layanan
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f --tail=100 backend
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f --tail=100 caddy
```

### 5.6 Penarikan Seluruh Hasil Scan ke KB (`tarik_semua.py`)
Setelah smoke test Fase 2 (S01–S22) lulus dengan **0 GAGAL**, lakukan penarikan dokumen hasil pemindaian (scraping) ke Knowledge Base (KB) menggunakan skrip `scripts/tarik_semua.py`:

```bash
# 1. DRY-RUN (Default): Hanya membaca kandidat dan menampilkan proyeksi tarikan (hanya metode GET)
python scripts/tarik_semua.py --base-url https://api.hero-regulasi.id

# 2. Uji Penarikan Bertahap (Batas 20 kandidat per sumber)
python scripts/tarik_semua.py --base-url https://api.hero-regulasi.id --apply --batas 20

# 3. Penarikan Penuh Seluruh Sumber
python scripts/tarik_semua.py --base-url https://api.hero-regulasi.id --apply

# Opsi autentikasi bila AUTH_ENABLED=true:
# HERO_API_TOKEN="<token_jwt_admin_atau_analis>" python scripts/tarik_semua.py --base-url https://api.hero-regulasi.id --apply
```

#### Pemantauan & Tindak Lanjut Pasca Tarikan:
1. **Pantau Corong Reguler**:
   Periksa pergerakan status corong via API:
   ```bash
   curl -s https://api.hero-regulasi.id/api/v1/dashboard/corong | jq .
   ```
   Pastikan metrik `total.dokumen.di_kb` bertambah dan `total.scan.belum_ditarik` menurun.
2. **Tindak Lanjut Kandidat Gagal**:
   Bila muncul baris `PERINGATAN: N kandidat gagal ditarik`:
   - Telusuri log kegagalan via endpoint antrean kegagalan:
     ```bash
     curl -s "https://api.hero-regulasi.id/api/v1/ingest/failures?source_id=<id>" | jq .
     ```
   - Lakukan penarikan ulang hanya untuk kandidat yang sempat gagal:
     ```bash
     python scripts/tarik_semua.py --base-url https://api.hero-regulasi.id --apply --ulang-gagal
     ```

### 5.7 Menyiapkan KB untuk UAT (Skenario 1.480 + 20)
Sesuai arahan Weekly #7 Pak Faris dan Test Plan PM:
- **Konsep Ground Truth**: Seluruh dokumen regulasi yang terdeteksi saat scraping ditarik, diunduh ke penyimpanan lokal, dipecah (ekstraksi pasal), dan masuk vektor database. Kumpulan regulasi ini menjadi *ground truth* corpus pengetahuan sistem HERO.
- **Skenario UAT 1.480 + 20**:
  1. Dari total ~1.500 dokumen korpus regulasi yang terdeteksi, lakukan penarikan seluruh dokumen ke KB menggunakan `--apply`.
  2. Tunggu worker ekstraksi data / ML menyelesaikan pemrosesan OCR, ekstraksi pasal, dan pembuatan embedding vektor. Angka `terbaca` pada corong akan bertahap meningkat hingga seluruh dokumen selesai diproses.
  3. **Penyisihan 20 Dokumen Uji**:
     > **Catatan untuk Tim QA (Hamdan & Zaky)**:
     > Sisihkan **20 dokumen regulasi uji** yang mewakili berbagai variasi (PDF Word, PDF pindaian/scanned, PDF terproteksi, POJK lama vs POJK baru) sesuai rincian pada Test Plan PM untuk pengujian manual skenario UAT. 1.480 dokumen lainnya dibiarkan aktif sebagai korpus acuan dasar.

---

## 6. Menyambungkan Frontend (Vercel)

1. Pada dashboard Vercel proyek frontend, set Environment Variable:
   - `NEXT_PUBLIC_API_URL=https://api.hero-regulasi.id`
2. Pastikan domain Vercel (mis. `https://hero-frontend.vercel.app` atau domain kustom) tercatat **persis sama** pada `CORS_ORIGINS` di `.env.prod`.
3. Lakukan redeploy pada Vercel untuk menerapkan URL API baru.

---

## 7. Menaruh Sumber Dokumen Offline (OneDrive / File Internal)

Untuk menyinkronkan dokumen dari folder offline (mis. arsip regulasi internal / OneDrive):
1. Salin berkas PDF ke folder `sources/onedrive/` di host:
   ```bash
   mkdir -p /opt/hero-backend/sources/onedrive
   # Salin berkas-berkas PDF ke folder ini
   cp /path/to/my-regulations/*.pdf /opt/hero-backend/sources/onedrive/
   ```
2. Daftarkan sumber folder lokal lewat API atau skrip demo seeder (§8). Folder ini dimount secara read-only (`:ro`) ke dalam container `/app/sources`.

---

## 8. Manajemen Data Demo (Reset & Seeding)

### 8.1 Menyiapkan Konfigurasi Sumber Demo
Buat konfigurasi sumber nyata:
```bash
cp deploy/demo_sources.example.json deploy/demo_sources.json
nano deploy/demo_sources.json
```

### 8.2 Reset Data Demo (Bila Diperlukan)
Untuk membersihkan data uji dan menyisakan skema bersih, kategori standar, dan admin:
```bash
# Menjalankan demo reset (pada mode produksi membutuhkan flag --i-understand-production)
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backend \
  python scripts/demo_reset.py --yes --i-understand-production
```

### 8.3 Seeding Sumber & Scanning Otomatis
Jalankan pengisian data lewat API:
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backend \
  python scripts/demo_seed.py --config deploy/demo_sources.json --base-url http://127.0.0.1:8000
```
Skrip ini akan:
1. Mendaftarkan sumber web JDIH & folder lokal `sources/onedrive`.
2. Menjalankan pemindaian folder lokal dan penarikan berkas.
3. Menjalankan scanning situs web dan menarik kandidat regulasi baru ke Knowledge Base.
4. Menampilkan tabel ringkasan hasil seeding dan dashboard corpus.

---

## 9. Backup & Restore Rutin

### 9.1 Konfigurasi Otomatisasi Backup Harian (systemd timer)
Backup harian dijadwalkan oleh `hero-backup-db.timer` (setiap hari 03:00, dengan jitter 5 menit). Timer ini memanggil `pipeline/deploy/vps/backup-db.sh`, yang menjalankan `backend/deploy/backup.sh` lalu mengunggah hasilnya ke Nextcloud (`nc:HERO-Backup/db`) dengan `rclone copy` (tidak pernah menghapus berkas lama di Nextcloud).

Prasyarat, dikerjakan sekali di VPS:
```bash
sudo mkdir -p /var/backups/hero
sudo rclone config --config /opt/hero/rclone-nextcloud.conf   # remote bernama: nc
sudo install -m 0644 /opt/hero/pipeline/deploy/systemd/hero-backup-db.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now hero-backup-db.timer
```

Cek jadwal dan log terakhir:
```bash
systemctl list-timers hero-backup-db.timer
tail -n 50 /opt/hero/data/logs/backup-db.log
```

### 9.2 Menjalankan Backup Manual
```bash
cd /opt/hero/backend && sudo ./deploy/backup.sh
```
Hasil backup berupa 2 berkas berpasangan:
- `/var/backups/hero/hero_db_YYYYMMDD_HHMMSS.sql.gz` (dump database)
- `/var/backups/hero/hero_storage_YYYYMMDD_HHMMSS.tar.gz` (seluruh berkas PDF & KB)

Skrip hanya menyimpan berkas final bila dump tidak kosong dan arsip storage bisa dibaca utuh; berkas `.tmp` yang gagal dibuang otomatis. Rotasi menyimpan 7 backup terakhir per jenis (ubah dengan `KEEP=<n>`).

### 9.3 Uji Pemulihan (Restore Test) — tanpa menyentuh produksi
Sebelum mengandalkan backup, uji dulu bahwa backup bisa dipulihkan:
```bash
cd /opt/hero/backend && sudo ./deploy/restore-test.sh            # pakai backup terbaru
sudo ./deploy/restore-test.sh <db.sql.gz> <storage.tar.gz>       # pakai berkas tertentu
```
Skrip ini memulihkan ke database sementara `hero_restore_test`, mengekstrak storage ke folder temporer, lalu membandingkan jumlah tabel dan berkas. Database produksi dan container backend tidak disentuh. Waktu pemulihan yang tercetak adalah perkiraan RTO. Database uji dihapus otomatis kecuali memakai `--keep`.

### 9.4 Prosedur Restore Data (produksi)
Bila benar-benar perlu mengembalikan data produksi dari backup tertentu, gunakan `restore.sh` dan jalankan hanya setelah uji pemulihan di atas lulus:
```bash
./deploy/restore.sh /var/backups/hero/hero_db_20261001_030000.sql.gz /var/backups/hero/hero_storage_20261001_030000.tar.gz
```
Skrip restore akan:
1. Meminta konfirmasi interaktif (atau gunakan `--yes` untuk bypass).
2. Menghentikan container `backend` sementara untuk mencegah race condition.
3. Merestore database via `psql`.
4. Mengekstrak kembali seluruh berkas storage ke volume `storage_data`.
5. Menjalankan `alembic upgrade head` untuk memastikan skema up to date.
6. Menyalakan kembali container `backend`.

---

## 10. Prosedur Pembaruan Aplikasi (Update) & Rollback

### 10.1 Prosedur Update Standar (Zero Code Loss)
```bash
cd /opt/hero-backend

# 1. Jalankan backup sebelum update
./deploy/backup.sh

# 2. Ambil perubahan kode terbaru
git pull origin main

# 3. Rebuild dan restart container
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# 4. Verifikasi status
curl -i https://api.hero-regulasi.id/health
```

### 10.2 Prosedur Rollback Cepat
Bila terjadi kendala kritis pada rilis baru:
```bash
# 1. Kembalikan kode ke tag/commit stabil sebelumnya
git checkout v0.8.0-fase1-rc1

# 2. Rebuild container
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# 3. Jika migrasi DB berubah secara destruktif, restore backup sebelum update
./deploy/restore.sh /var/backups/hero/db_hero_sebelum_update.sql.gz /var/backups/hero/storage_hero_sebelum_update.tar.gz --yes
```

---

## 11. Panduan Troubleshooting Masalah Umum

| Gejala | Kemungkinan Penyebab | Langkah Solusi |
|---|---|---|
| **CORS Error di Browser** | `CORS_ORIGINS` di `.env.prod` tidak cocok dengan origin Frontend Vercel (mis. ada trailing slash atau salah protokol `http://` vs `https://`). | Samakan `CORS_ORIGINS` dengan origin frontend persis (mis. `https://hero-frontend.vercel.app`), lalu restart backend: `docker compose -f docker-compose.yml -f docker-compose.prod.yml restart backend`. |
| **HTTP 413 Payload Too Large** | Unggahan PDF > 100MB melampaui batas reverse proxy atau aplikasi. | Caddyfile telah dikonfigurasi `request_body max_size 110MB` dan `MAX_UPLOAD_SIZE_MB=100`. Pastikan berkas PDF di bawah 100MB. |
| **Sertifikat SSL Gagal / Timeout** | Port 80/443 terblokir firewall atau DNS domain belum mengarah ke IP VPS. | Pastikan `sudo ufw allow 80/tcp` dan `443/tcp` aktif. Cek `dig +short api.hero-regulasi.id`. Cek log caddy: `docker compose ... logs caddy`. |
| **Container Backend Restart Loop** | Database belum siap, koneksi DB salah, atau validasi konfigurasi produksi menolak start (§2.2). | Cek `docker compose ... logs backend`. Periksa apakah `SECRET_KEY` < 32 karakter, `CORS_ORIGINS=*`, atau `CRAWL_ALLOW_PRIVATE_NETWORKS=true`. |
| **Port 80/443 Bentrok (Bind Error)** | Ada web server bawaan VPS yang aktif (mis. Apache atau Nginx). | Hentikan server bawaan: `sudo systemctl stop nginx && sudo systemctl disable nginx`, lalu jalankan kembali docker compose. |
| **Migrasi Tertinggal (`status: degraded`)** | File migrasi baru belum dieksekusi atau ada conflict lock. | Jalankan manual: `docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backend alembic upgrade head`. |

---

## 12. Catatan Keamanan Penting (Fase 1)

1. **Status Otentikasi (`AUTH_ENABLED=false`):**
   - Berdasarkan kesepakatan MoM, otentikasi login pengguna ditunda pada Fase 1.
   - Untuk melindungi dokumen berstatus sensitif, fitur **Proteksi Dokumen Non-Publik (§2.3)** aktif secara default (`PROTECT_NON_PUBLIC_WHEN_AUTH_DISABLED=true`).
   - Dokumen berklasifikasi `non_publik` akan menolak akses unduh PDF (`/documents/{id}/pdf`) dan teks penuh (`/documents/{id}/text`) dengan **HTTP 403 Forbidden**.
   - Pada hasil pencarian regulasi, dokumen non-publik tetap dapat ditemukan metadatanya, namun ditandai `restricted: true`, `pdf_url: null`, dan potongan teks (`highlight`) tidak menampilkan isi dokumen sensitif.
2. **Rekomendasi Dokumen di VPS:**
   - Selama Fase 1 (sebelum login pengguna aktif penuh di Fase 2), sangat direkomendasikan untuk **hanya mengunggah regulasi dan dokumen publik** ke VPS produksi.
3. **Kerahasiaan Kunci Internal:**
   - `INTERNAL_API_KEY` digunakan untuk komunikasi service-to-service (Worker Data/ML). Jangan pernah membagikan kunci ini di kanal publik/grup chat tanpa enkripsi. Gunakan password manager tim yang aman.
4. **Rotasi Kunci:**
   - Lakukan rotasi berkala untuk `SECRET_KEY` dan `INTERNAL_API_KEY` menjelang rilis Fase 2.
