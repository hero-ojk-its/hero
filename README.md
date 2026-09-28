# HERO Backend

Backend API untuk sistem **HERO (Harmonisasi & Analisa Regulasi Otomatis)** — platform analisa kepatuhan regulasi OJK (DPEA), pencarian semantik, klasifikasi akses kepatuhan NDA, dan pipeline ingest dokumen terpadu.

**Stack**: FastAPI 0.115+ (Python 3.11 Docker / Python 3.13 Lokal) · SQLAlchemy 2.0+ · Alembic 1.13+ · PostgreSQL 15 + pgvector · psycopg 3.

---

## 🚀 Cara Menjalankan

### Opsi A — Menjalankan Lewat Docker (Rekomendasi)

1. **Salin environment template:**
   ```bash
   cp .env.example .env
   ```

2. **Build dan jalankan container:**
   ```bash
   docker compose up -d --build
   ```
   *Container backend akan otomatis mengeksekusi `alembic upgrade head` saat startup sebelum uvicorn berjalan.*

3. **Cek status & log:**
   ```bash
   docker compose ps
   docker compose logs -f backend
   ```

4. **Akses Swagger UI API:**
   Buka browser pada: **http://localhost:8000/docs**

---

### Opsi B — Menjalankan Secara Lokal (Python Venv)

1. **Aktifkan Virtual Environment:**
   ```powershell
   # Windows PowerShell
   .\venv\Scripts\Activate.ps1
   ```

2. **Install Dependensi:**
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-dev.txt
   ```

3. **Konfigurasi `.env`:**
   Pastikan variabel `DATABASE_URL` dan `STORAGE_PATH=./storage` sudah sesuai.

4. **Jalankan Migrasi Database:**
   ```bash
   alembic upgrade head
   ```

5. **Jalankan Server Uvicorn:**
   ```bash
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

---

## 🔒 Konfigurasi Otentikasi (`AUTH_ENABLED`)

Berdasarkan keputusan **MoM 22 Sep 2026**, otentikasi login ditunda untuk mempermudah pengujian awal frontend dan mitra:
- **`AUTH_ENABLED=false` (Default):** Seluruh endpoint terbuka tanpa memerlukan JWT bearer token. `get_current_user` mengembalikan `None` (pengguna anonim / sistem).
- **`AUTH_ENABLED=true`:** Proteksi JWT aktif. Endpoint yang memerlukan otentikasi akan menolak request tanpa token dengan status HTTP 401.

Untuk membuat/mereset akun admin:
```bash
python -m app.create_admin
```

---

## 🧪 Pengujian Otomatis

### 1. Menjalankan Pytest
Suite pengujian mencakup 170 test otomatis tanpa kegagalan (Langkah 0–8) menggunakan database uji terpisah `hero_test`:
```bash
python -m pytest -q
```

### 2. Uji Performa Pencarian (Benchmark 2.000 Dokumen)
Menguji performa full-text search PostgreSQL TSVector dan indeks GIN trigram terhadap 2.000 dokumen regulasi sintetis (syarat p95 < 1.000 ms):
```bash
python scripts/perf_search.py
```

### 3. Menjalankan Smoke Test
Smoke test memvalidasi end-to-end server yang sedang berjalan (Langkah 0–8: Upload -> Claim -> Extraction -> Search -> PDF -> Metadata -> Dashboard -> Scan & Pull):
```bash
# Terhadap server lokal / docker
python scripts/smoke_test.py http://127.0.0.1:8000
```

---

## 🚢 Panduan Deployment Produksi (VPS)

Deployment ke target server produksi (Ubuntu/Debian VPS) menggunakan **Docker Compose** dengan reverse proxy **Caddy 2** (HTTPS Let's Encrypt otomatis, Basic Auth Swagger, proteksi ukuran payload 110MB).

Panduan lengkap instalasi, backup rutin, pembaruan, dan mitigasi kendala tersedia di:
- 👉 **[Runbook Deployment VPS](docs/deploy/RUNBOOK-VPS.md)**
- 👉 **[Checklist Persiapan Demo 8 Oktober](docs/deploy/DEMO-CHECKLIST-8-OKT.md)**

### Perintah Cepat Deploy Produksi:
```bash
# 1. Konfigurasi env produksi
cp .env.prod.example .env.prod
nano .env.prod

# 2. Jalankan stack produksi
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# 3. Cek status kesehatan sistem
curl https://<API_DOMAIN>/health
```

---

## ⚙️ Variabel Lingkungan (Environment Variables)

| Kategori | Variabel | Tipe / Default | Deskripsi |
|---|---|---|---|
| **Aplikasi** | `APP_ENV` | `development` / `production` | Mode lingkungan aplikasi |
| | `APP_PORT` | `8000` | Port aplikasi di dalam container |
| | `API_DOMAIN` | `localhost` | Domain publik untuk reverse proxy Caddy & CORS |
| | `UVICORN_WORKERS` | `1` | Jumlah worker Uvicorn (1 disarankan untuk in-process task) |
| | `FORWARDED_ALLOW_IPS` | `127.0.0.1` | IP reverse proxy yang dipercaya untuk X-Forwarded-For |
| | `EXPOSE_API_DOCS` | `true` | Menampilkan/menyembunyikan endpoint `/docs` & `/redoc` |
| **Keamanan** | `AUTH_ENABLED` | `false` | Status proteksi JWT Bearer login pengguna |
| | `PROTECT_NON_PUBLIC_WHEN_AUTH_DISABLED` | `true` | Proteksi NDA (403 PDF/teks & restricted search) bila auth nonaktif |
| | `SECRET_KEY` | *(wajib)* | Kunci signing token JWT (min 32 karakter pada produksi) |
| | `INTERNAL_API_KEY` | *(wajib)* | Kunci API untuk worker internal ML & crawler |
| | `CORS_ORIGINS` | `http://localhost:3000` | Daftar origin frontend yang diizinkan (dipisah koma) |
| | `DOCS_BASIC_AUTH_USER` | `hero-team` | Username HTTP Basic Auth dokumentasi Swagger di Caddy |
| | `DOCS_BASIC_AUTH_HASH` | *(string bcrypt)* | Hash password Basic Auth dokumentasi Swagger di Caddy |
| **Database** | `DATABASE_URL` | `postgresql+psycopg://...` | URI koneksi PostgreSQL |
| | `TEST_DATABASE_URL` | `postgresql+psycopg://...` | URI database pengujian `hero_test` |
| | `POSTGRES_USER` | `hero_user` | User database PostgreSQL |
| | `POSTGRES_PASSWORD` | `hero_pass` | Password database PostgreSQL |
| | `POSTGRES_DB` | `hero_db` | Nama database utama |
| **Storage** | `STORAGE_PATH` | `./storage` | Root path direktori penyimpanan dokumen lokal |
| | `MAX_UPLOAD_SIZE_MB` | `100` | Batas maksimum ukuran unggahan PDF (MB) |
| **Sumber Dokumen** | `LOCAL_SOURCE_ROOTS` | `./sources` | Direktori sumber berkas lokal/OneDrive yang diizinkan |
| **Crawler Web** | `CRAWLER_BACKEND` | `simple_http` | Backend crawling (`simple_http`, `push`, `external_module`) |
| | `CRAWLER_MODULE` | `null` | Modul kustom crawler jika backend `external_module` |
| | `CRAWLER_USER_AGENT` | `HERO-Bot/1.0` | User agent HTTP crawler |
| | `CRAWLER_RATE_LIMIT_DELAY` | `1.0` | Jeda waktu minimum antar request crawler (detik) |
| | `CRAWLER_REQUEST_TIMEOUT` | `15.0` | Timeout per HTTP request crawler (detik) |
| | `CRAWLER_MAX_FILE_SIZE_MB` | `50` | Batas ukuran berkas PDF yang dipindai crawler |
| | `CRAWL_ALLOW_PRIVATE_NETWORKS` | `false` | Izin crawling jaringan privat (wajib `false` di produksi) |
| **Ekstraksi ML** | `EXTRACTION_CONFIDENCE_THRESHOLD` | `0.7` | Ambang batas confidence untuk status `terindeks` |
| **Penamaan/Kategori** | `NAMING_AUTO_RENAME` | `true` | Otomatis menstandardisasi nama berkas PDF saat ingest |
| | `NAMING_MAX_LENGTH` | `120` | Panjang maksimum nama berkas hasil standardisasi |

---

## 🔍 Pencarian Knowledge Base (Langkah 4)

Pencarian dokumen regulasi didukung oleh kolom komputasi `search_vector` (`TSVECTOR`) dengan konfigurasi `'simple'` dan pembobotan:
- **Bobot A**: `regulation_number`, `title`
- **Bobot B**: `regulation_type`
- **Bobot C**: `left(full_text, 300000)` (dibatasi 300.000 karakter agar tidak melebihi batas 1 MB tsvector PostgreSQL)

### 1. Mode Pencarian (`mode`)
- **`phrase` (Default):** Pencocokan frasa berurutan menggunakan `phraseto_tsquery`. Contoh: `q=sepatu roda` hanya mencocokkan dokumen dengan kata "sepatu" yang langsung diikuti "roda".
- **`all`:** Semua kata harus ada dalam urutan bebas menggunakan `plainto_tsquery`.
- **`web`:** Sintaks pencarian tingkat lanjut menggunakan `websearch_to_tsquery` (mendukung tanda kutip `"sepatu roda"`, operator `OR`, dan tanda minus `-kecuali`).

### 2. Filter & Parameter Pencarian
- `q`: Kata kunci / nomor regulasi (otomatis mendeteksi pola nomor regulasi untuk pencocokan trigram toleran tanda baca).
- `regulation_number`: Pencocokan nomor regulasi (`ILIKE %...%` berbasis trigram).
- `regulation_type`: Jenis regulasi dinormalisasi (`POJK`, `SEOJK`, dll.).
- `category_id` + `include_subcategories=true`: Filter kategori rekursif (CTE).
- `status_keberlakuan`: Multi-value filter (`?status_keberlakuan=berlaku&status_keberlakuan=diubah`). Tanpa filter, dokumen dicabut tetap ikut tampil.
- `date_from`, `date_to`, `year`: Rentang tanggal dan tahun terbit.
- `sort`: `relevance` (default bila `q` terisi), `release_date_desc`, `release_date_asc`, `created_desc`, `title_asc`.

---

## 🤖 Integrasi Ekstraksi Data/ML (Langkah 5)

Backend menyediakan API terpadu untuk worker Data/ML (Fathir) di `/api/v1/internal`:
1. **`POST /api/v1/internal/extraction/claim`**: Mengambil task antrean ekstraksi (`SELECT ... FOR UPDATE SKIP LOCKED`).
2. **`GET /api/v1/internal/documents/{id}/pdf`**: Mengunduh berkas PDF asli untuk proses OCR / ekstraksi teks.
3. **`PATCH /api/v1/internal/documents/{id}/extraction`**: Mengirimkan hasil ekstraksi (`title`, `regulation_number`, `release_date`, `full_text`, `confidence`) atau laporan kegagalan (`error`). Mendukung field bahasa Inggris dan alias Bahasa Indonesia (`judul`, `nomor_peraturan`, dsb.).
4. **`POST /api/v1/internal/extraction/requeue/{id}`**: Mengembalikan dokumen ke antrean jika worker dibatalkan.

### Aturan Bisnis Ekstraksi & Koreksi
- **Penentuan Status:** Dokumen dengan metadata lengkap dan confidence ≥ threshold (`0.7`) otomatis berstatus `terindeks` dan ditempatkan ke `kb/{jenis}/{tahun}/`. Dokumen dengan confidence < 0.7 atau metadata tidak lengkap masuk status `perlu_koreksi`.
- **Preservasi Koreksi Manual:** Jika reviewer telah mengoreksi metadata secara manual (`metadata_corrected_at` terisi), hasil ekstraksi ML tidak akan menimpa metadata manual tersebut.
- **Keamanan Kunci Internal:** Kunci API internal (`INTERNAL_API_KEY`) dibagikan ke tim Data/ML melalui kanal privat yang aman, bukan melalui repositori dokumen terbuka.

---

## 📊 Dashboard Ringkasan (Langkah 5)

Endpoint `GET /api/v1/dashboard/summary` menyajikan statistik agregat database:
- **`kb`**: Total corpus, draft kajian, status pencapaian target Fase 1 (≥ 20 dokumen corpus), sebaran status keberlakuan, sebaran status pemrosesan, sebaran jenis regulasi, dan sebaran tahun terbit.
- **`ingest`**: Jumlah open failures, dokumen dalam antrean koreksi (`needs_review`), serta 5 job ingest terakhir.
- **`sources`**: Total dan jumlah situs sumber scraping yang aktif.

---

## ⚠️ Antrian Kegagalan & Retry (Langkah 2 & 5)

Sistem mencatat seluruh kegagalan dan duplikat pada tabel `ingest_failures`.

### 1. Kategori Kegagalan & Sifat Retry
| `reason_code` | `failure_type` | Karantina Berkas Fisik | `is_retryable` | Status Awal |
|---|---|---|---|---|
| `format_tidak_didukung` | `format_tidak_didukung` | Tidak | False | `belum_ditangani` |
| `berkas_kosong` | `format_tidak_didukung` | Tidak | False | `belum_ditangani` |
| `ukuran_melebihi_batas` | `format_tidak_didukung` | Tidak | False | `belum_ditangani` |
| `duplikat` | `duplikat` | Tidak | False | `diabaikan` |
| `kategori_tidak_ditemukan` | `metadata_tidak_lengkap` | Ya (`quarantine/`) | True | `belum_ditangani` |
| `kesalahan_internal` | `kesalahan_internal` | Ya (`quarantine/`) | True | `belum_ditangani` |
| `ekstraksi_gagal` | `ekstraksi_gagal` | Tidak (di inbox/kb) | True | `belum_ditangani` |
| `ocr_gagal` | `ocr_gagal` | Tidak (di inbox/kb) | True | `belum_ditangani` |

---

## 📂 Penamaan Baku & Struktur Folder KB (Langkah 3)

### 1. Alur Dua Tahap Staging & Penempatan
1. **Saat Ingest Awal:** Berkas fisik disimpan sementara di area staging `pdf/_inbox/` dengan nama sementara `<hash12>_<nama_asli>.pdf`.
2. **Saat Penempatan (Placement):** Jika metadata dokumen telah mencukupi (`regulation_number` atau `regulation_type` + `release_date`), berkas otomatis distandarisasi dan dipindahkan ke:
   `kb/<jalur kategori>/<nama baku>.pdf`.

### 2. Format Penamaan Baku
Format penamaan baku: `{nomor} {judul} {tahun}` (contoh: `11-POJK.03-2022 Penyelenggaraan Teknologi Informasi oleh Bank Umum 2022.pdf`).

---

## 📂 Sumber Dokumen & Sinkronisasi Folder Lokal (Langkah 6)

### 1. Jenis Sumber Dokumen
Sistem mendukung 3 jenis sumber dokumen (`JenisSumber`):
1. `situs_web`: Perayap web regulasi publik (dieksekusi melalui alur pemindaian Langkah 7).
2. `folder_lokal`: Sinkronisasi direktori berkas PDF lokal pada server.
3. `onedrive_public`: Tautan folder OneDrive/SharePoint publik (Fase 1: disinkronkan ke folder lokal terlebih dahulu).

### 2. Konfigurasi Akar Folder Lokal (`LOCAL_SOURCE_ROOTS`)
Demi keamanan, backend dibatasi hanya membaca direktori di bawah akar yang diizinkan:
- **Environment:** `LOCAL_SOURCE_ROOTS` (daftar jalur dipisahkan titik koma `;`, default: `./sources`).
- **Di Lingkungan Docker:** `./sources` di-mount ke `/app/sources:ro`. Folder yang didaftarkan ke API adalah `/app/sources/<subfolder>`.
- **Di Lingkungan Lokal:** Folder ditaruh di `./sources/<subfolder>` dan didaftarkan menggunakan jalur absolut atau relatif yang berada di bawah `./sources`.

### 3. Idempotensi & `skipped_unchanged`
Tabel `source_files` mengindeks berkas per sumber dengan mencatat `size_bytes`, `mtime`, dan `file_hash`:
- Jika ukuran berkas (`size_bytes`) dan waktu modifikasi (`mtime`) tidak berubah dari hasil sukses sebelumnya, isi berkas **tidak dibaca ulang dari disk**, dan ditandai sebagai `skipped_unchanged`.
- Fitur ini menghemat I/O dan menjaga proses sinkronisasi tetap cepat walau terdapat ribuan dokumen.

### 4. Klasifikasi Akses Default `non_publik`
Dokumen dari `folder_lokal` dan `onedrive_public` secara default diberi klasifikasi `non_publik`. Hal ini dikarenakan folder lokal pada institusi perbankan/regulator umumnya memuat draft kajian, peraturan internal yang tunduk pada NDA, atau dokumen rahasia sebelum dipublikasikan secara resmi ke publik. Dokumen dari `situs_web` tetap default `publik`.

### 5. Panduan OneDrive pada Fase 1
Pada Fase 1, konektor langsung OneDrive API belum diimplementasikan. Untuk menggunakan OneDrive:
1. Sinkronkan folder OneDrive ke subfolder `./sources/onedrive/` pada host.
2. Daftarkan folder tersebut sebagai `folder_lokal` melalui API dengan jalur `/app/sources/onedrive` (di Docker) atau `./sources/onedrive` (di lokal).

---

## 🔐 Keamanan Kunci API Internal
Kunci API internal (`INTERNAL_API_KEY`) digunakan untuk autentikasi worker Data/ML pada endpoint `/api/v1/internal/*`.
> **PENTING:** Kunci API internal wajib diganti dengan nilai rahasia yang kuat sebelum dideploy ke environment staging/production. Kunci ini dibagikan ke tim Data/ML melalui kanal privat yang aman, bukan dicantumkan dalam dokumentasi publik atau repository.

---

## 📡 Daftar Endpoint API (v0.6.0)

### 1. Health & Dashboard
| Method | Endpoint | Deskripsi |
|---|---|---|
| `GET` | `/` | Status ringkas service |
| `GET` | `/health` | Health check database (`SELECT 1`) & flag auth |
| `GET` | `/api/v1/dashboard/summary` | Statistik ringkasan Knowledge Base, Ingest, dan Scraping Sources (termasuk `sources.by_type`) |
| `GET` | `/debug-routes` | Daftar semua rute (khusus `APP_ENV=development`) |

### 2. Ingest Pipeline & Log Kegagalan (`/api/v1/ingest`)
| Method | Endpoint | Deskripsi |
|---|---|---|
| `POST` | `/upload-pdf` | Upload PDF regulasi / draft kajian (tunggal/jamak). |
| `GET` | `/check-duplicate` | Screening deduplikasi sebelum upload |
| `GET` | `/jobs` | Riwayat job ingest (filter `source_id`, `status`, `job_type`) |
| `GET` | `/jobs/{job_id}` | Detail lengkap job ingest beserta progres, dokumen, dan kegagalan |
| `GET` | `/status` | Statistik ringkasan dokumen, job, dan `open_failures` |
| `GET` | `/failures` | Daftar log kegagalan & antrian retry |
| `GET` | `/failures/{failure_id}` | Detail satu baris kegagalan |
| `PATCH` | `/failures/{failure_id}` | Update status tindak lanjut (`belum_ditangani` <-> `diabaikan`) |
| `POST` | `/failures/{failure_id}/retry` | Memproses ulang (retry) kegagalan ingest atau ekstraksi |
| `POST` | `/failures/retry` | Batch retry beberapa item kegagalan |

### 3. Dokumen Regulasi & Knowledge Base (`/api/v1/documents`)
| Method | Endpoint | Deskripsi |
|---|---|---|
| `GET` | `/` | Pencarian regulasi full-text & filter terpadu (Langkah 4) |
| `GET` | `/needs-review` | Antrian dokumen yang membutuhkan koreksi metadata / review keyakinan rendah |
| `GET` | `/{document_id}` | Detail dokumen regulasi beserta pasal, rujukan, dan confidence |
| `GET` | `/{document_id}/pdf` | Buka PDF asli (`inline` atau `?download=true` untuk unduh) |
| `GET` | `/{document_id}/text` | Baca potongan teks regulasi terpaginasi |
| `PATCH`| `/{document_id}/metadata` | Koreksi metadata dokumen manual (auto-reorganize KB) |
| `PUT` | `/{document_id}/status` | Update status keberlakuan (membuat `legal_references` jika dicabut/diubah) |
| `POST` | `/{document_id}/place` | Pemicu penamaan baku dan pemindahan dokumen ke folder KB (`kb/...`) |
| `POST` | `/place-pending` | Batch penempatan dokumen staging ke folder KB |

### 4. Kategori Knowledge Base (`/api/v1/categories`)
| Method | Endpoint | Deskripsi |
|---|---|---|
| `GET` | `/` | Daftar datar seluruh kategori |
| `GET` | `/tree` | Pohon hierarki folder KB lengkap dengan agregasi dokumen |
| `GET` | `/{category_id}` | Detail satu kategori beserta jalur root->leaf |
| `POST` | `/` | Buat kategori baru (menolak duplikat nama di bawah induk yang sama) |

### 5. Internal Data/ML Pipeline (`/api/v1/internal`)
| Method | Endpoint | Deskripsi |
|---|---|---|
| `POST` | `/extraction/claim` | Klaim antrean dokumen untuk diekstraksi/OCR |
| `GET` | `/documents/{id}/pdf` | Unduh berkas PDF untuk worker tanpa audit log |
| `PATCH`| `/documents/{id}/extraction` | Kirim hasil ekstraksi teks, metadata & confidence atau error |
| `POST` | `/extraction/requeue/{id}` | Kembalikan dokumen ke antrean `diterima` |
| `POST` | `/articles` | Bulk insert chunk pasal & embedding 1536-dim |

### 6. Sumber Scraping & Sinkronisasi Folder (`/api/v1/scraping-sources`)
| Method | Endpoint | Deskripsi |
|---|---|---|
| `GET` / `POST` | `/api/v1/scraping-sources/` | Kelola sumber dokumen (situs web, folder lokal, OneDrive) |
| `GET` | `/api/v1/scraping-sources/{id}` | Detail satu sumber dokumen (termasuk `address`, status run terakhir) |
| `PUT` / `PATCH` | `/api/v1/scraping-sources/{id}` | Ubah properti sumber dokumen |
| `DELETE` | `/api/v1/scraping-sources/{id}` | Hapus sumber dokumen (cascade ke `source_files`) |
| `POST` | `/api/v1/scraping-sources/{id}/run` | Jalankan sinkronisasi sumber folder (202 async / 200 via `?wait=true`) |
| `GET` | `/api/v1/scraping-sources/{id}/files` | Daftar berkas terindeks per sumber (pagination & filter status) |

### 7. Alur Pindai Situs Web (`/api/v1/scans`)
| Method | Endpoint | Deskripsi |
|---|---|---|
| `POST` | `/api/v1/scans/` | Mulai sesi pindai situs web (202 Accepted / 200 via `?wait=true`) |
| `GET` | `/api/v1/scans/` | Riwayat sesi pindai (filter `source_id`, `status`) |
| `GET` | `/api/v1/scans/{id}` | Detail status sesi, progres halaman & ringkasan kandidat |
| `GET` | `/api/v1/scans/{id}/candidates` | Daftar kandidat PDF (filter status, centang, outcome, search nama berkas) |
| `PATCH`| `/api/v1/scans/{id}/selection` | Perbarui centang pilihan (`set`, `select_all_new`, `select_none`) |
| `POST` | `/api/v1/scans/{id}/pull` | Tarik kandidat terpilih (`knowledge_base` atau `unduh_folder`) |
| `POST` | `/api/v1/scans/{id}/cancel` | Batalkan sesi pemindaian atau penarikan yang sedang berjalan |
| `GET` | `/api/v1/scans/{id}/download` | Unduh arsip ZIP hasil penarikan tujuan `unduh_folder` |

### 8. Jejak Audit & Autentikasi
| Method | Endpoint | Deskripsi |
|---|---|---|
| `GET` | `/api/v1/audit-logs/` | Daftar jejak audit aktivitas (filter `action`, `user_id`, `target_resource`) |
| `POST` | `/api/v1/auth/login` | Login form OAuth2 untuk memperoleh token JWT Bearer |

---

## 🌐 Pindai Situs Web (Langkah 7)

Alur pemindaian situs web dirancang sesuai keputusan rapat mitra (*MoM 15 & 22 Sep 2026*): **Scan → Compare → Select → Pull**.

### 1. Mode & Backend Crawler
- **`simple_http` (Bawaan):** Crawler HTTP berbasis `httpx` murni untuk situs HTML statis standar. Menghormati `robots.txt`, jeda rate-limit, BFS kedalaman slash, deteksi paging tanpa menghabiskan depth, dan HEAD request untuk ukuran/Content-Disposition.
  *Batasan:* Tidak mengeksekusi JavaScript sisi klien (SPA) dan tidak menangani proteksi anti-bot tingkat lanjut.
- **`external_module`:** Memuat kelas crawler kustom yang memenuhi `Crawler` Protocol secara dinamis via `CRAWLER_MODULE=pkg.module:Class`.
- **`push`:** Mode antrean untuk worker crawler independen Data/ML via endpoint internal (`/internal/scans/claim` dan `/internal/scans/{id}/candidates`).

### 2. Perlindungan Keamanan SSRF
Semua URL divalidasi ketat oleh `guard_url`:
- Hanya skema `http` dan `https` yang diizinkan.
- Host di-resolve ke IP dan seluruh alamat private (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), loopback (`127.0.0.1`, `::1`), link-local (`169.254.169.254`), multicast, dan reserved ditolak keras dengan status HTTP 422 (kecuali `CRAWL_ALLOW_PRIVATE_NETWORKS=true` untuk testing lokal).
- Setiap pengalihan (*redirect hop*) diperiksa ulang secara independen.

---

## 📁 Struktur Folder Proyek

```
hero-backend/
├── alembic/                 # Skrip migrasi database Alembic
│   ├── versions/            # Riwayat revisi migrasi skema (Langkah 0–7)
│   └── env.py               # Konfigurasi environment migrasi
├── app/
│   ├── crawlers/            # Modul crawler terisolasi (Base, URL utils, SimpleHttp, Registry)
│   ├── models/              # ORM SQLAlchemy & Enums (Document, JobIngest, ScanSession, ScanCandidate, ...)
│   ├── routers/             # Endpoint FastAPI (documents, ingest, categories, internal, dashboard, scans, ...)
│   ├── schemas/             # Pydantic validation & response models
│   ├── services/            # Logika bisnis (Search, Storage, Ingest, Failure, Naming, Category, Scan, Placement, Audit)
│   ├── config.py            # Pydantic Settings, environment loader & validasi produksi
│   ├── database.py          # SQLAlchemy Session & Base & Category Seeder
│   ├── main.py              # Inisialisasi FastAPI, OpenAPI patch & Middleware
│   └── create_admin.py      # Utilitas CLI pembuatan admin
├── deploy/                  # Konfigurasi deployment produksi & skrip backup
│   ├── Caddyfile            # Reverse proxy Caddy 2, SSL & Basic Auth
│   ├── backup.sh            # Skrip backup otomatis DB + storage (retensi 7 hari)
│   ├── restore.sh           # Skrip restore interaktif DB + storage
│   └── demo_sources.example.json # Template konfigurasi sumber demo
├── docs/
│   ├── api/                 # Panduan & kontrak integrasi API (Frontend & Data/ML)
│   │   ├── frontend-changes-step7.md
│   │   ├── frontend-changes-step8.md
│   │   └── crawler-adapter-contract.md
│   ├── deploy/              # Runbook operasional VPS & checklist demo
│   │   ├── RUNBOOK-VPS.md
│   │   └── DEMO-CHECKLIST-8-OKT.md
│   └── reports/             # Laporan berkala implementasi langkah (step0-1, step2-3, step4-5, step6, step7, step8)
├── scripts/                 # Skrip benchmark, smoke test, demo & Docker entrypoint
│   ├── entrypoint.sh        # Entrypoint Docker produksi (Alembic upgrade + Uvicorn)
│   ├── demo_reset.py        # Reset bersih data operasional pra-demo
│   ├── demo_seed.py         # Ingest otomatis sumber demo lewat API
│   ├── perf_search.py       # Benchmark performa full-text search (2.000 dokumen)
│   ├── smoke_test.py        # Skrip otomatis smoke test end-to-end (clean teardown)
│   └── demo_real_site_scan.py # Skrip demonstrasi alur pemindaian situs web nyata
├── tests/                   # Suite pengujian otomatis Pytest (170 test)
│   ├── conftest.py          # Fixture database test & storage terisolasi
│   ├── test_api.py          # Pengujian API umum & auth
│   ├── test_failures.py     # Pengujian log kegagalan & antrian retry
│   ├── test_naming_service.py # Pengujian standardisasi nama
│   ├── test_category_service.py # Pengujian hierarki & constraint kategori
│   ├── test_placement.py    # Pengujian penempatan folder KB
│   ├── test_search.py       # Pengujian pencarian KB full-text & filter
│   ├── test_document_detail.py # Pengujian buka PDF asli & teks
│   ├── test_metadata_correction.py # Pengujian koreksi metadata & audit diff
│   ├── test_extraction_internal.py # Pengujian integrasi worker ML
│   ├── test_dashboard.py    # Pengujian dashboard ringkasan
│   ├── test_local_folder_sync.py # Pengujian sinkronisasi folder lokal
│   ├── test_url_guard.py    # Pengujian keamanan SSRF & URL normalizer
│   ├── test_crawler_simple.py # Pengujian BFS crawler, robots.txt & paging
│   ├── test_scan_flow.py    # Pengujian alur scan, deduplikasi KB, selection & pull
│   ├── test_scan_push.py    # Pengujian mode crawler push internal
│   ├── test_docs_enums.py   # Pengujian validitas enum pada dokumentasi API
│   ├── test_step8_fixes.py  # Pengujian bugfixes §1.2 & §1.3
│   └── test_deploy_readiness.py # Pengujian kesiapan deploy produksi §2.2–§2.7
├── .env.example             # Template variabel lingkungan lokal
├── .env.prod.example        # Template variabel lingkungan produksi VPS
├── docker-compose.yml       # Definisi service lokal PostgreSQL + Backend
├── docker-compose.prod.yml  # Override produksi (Caddy, named volume, no host DB port)
├── Dockerfile               # Image build backend Python 3.11-slim + Healthcheck
├── requirements.txt         # Dependensi produksi
└── requirements-dev.txt     # Dependensi pengembangan & pengujian
```

