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
Suite pengujian mencakup 114 test otomatis tanpa kegagalan/skip (Langkah 0–5) menggunakan database uji terpisah `hero_test`:
```bash
python -m pytest -q
```

### 2. Uji Performa Pencarian (Benchmark 2.000 Dokumen)
Menguji performa full-text search PostgreSQL TSVector dan indeks GIN trigram terhadap 2.000 dokumen regulasi sintetis (syarat p95 < 1.000 ms):
```bash
python scripts/perf_search.py
```

### 3. Menjalankan Smoke Test
Smoke test memvalidasi end-to-end server yang sedang berjalan (Langkah 0–5: Upload -> Claim -> Extraction -> Search -> PDF -> Metadata -> Dashboard):
```bash
# Terhadap server lokal / docker
python scripts/smoke_test.py http://127.0.0.1:8000
```

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

## 📡 Daftar Endpoint API (v0.5.0)

### 1. Health & Dashboard
| Method | Endpoint | Deskripsi |
|---|---|---|
| `GET` | `/` | Status ringkas service |
| `GET` | `/health` | Health check database (`SELECT 1`) & flag auth |
| `GET` | `/api/v1/dashboard/summary` | Statistik ringkasan Knowledge Base, Ingest, dan Scraping Sources |
| `GET` | `/debug-routes` | Daftar semua rute (khusus `APP_ENV=development`) |

### 2. Ingest Pipeline & Log Kegagalan (`/api/v1/ingest`)
| Method | Endpoint | Deskripsi |
|---|---|---|
| `POST` | `/upload-pdf` | Upload PDF regulasi / draft kajian (tunggal/jamak). |
| `GET` | `/check-duplicate` | Screening deduplikasi sebelum upload |
| `GET` | `/jobs` | Riwayat job ingest |
| `GET` | `/jobs/{job_id}` | Detail lengkap job ingest beserta dokumen dan kegagalan |
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

### 6. Situs Sumber Scraping & Jejak Audit
| Method | Endpoint | Deskripsi |
|---|---|---|
| `GET` / `POST` | `/api/v1/scraping-sources/` | Kelola situs sumber scraping |
| `GET` | `/api/v1/audit-logs/` | Daftar jejak audit aktivitas (filter `action`, `user_id`, `target_resource`) |
| `POST` | `/api/v1/auth/login` | Login form OAuth2 untuk memperoleh token JWT Bearer |

---

## 📁 Struktur Folder Proyek

```
hero-backend/
├── alembic/                 # Skrip migrasi database Alembic
│   ├── versions/            # Riwayat revisi migrasi skema (Langkah 0–5)
│   └── env.py               # Konfigurasi environment migrasi
├── app/
│   ├── models/              # ORM SQLAlchemy & Enums (Document, JobIngest, IngestFailure, Category, ...)
│   ├── routers/             # Endpoint FastAPI (documents, ingest, categories, internal, dashboard, auth, ...)
│   ├── schemas/             # Pydantic validation & response models
│   ├── services/            # Logika bisnis (Search, Storage, Ingest, Failure, Naming, Category, Placement, Audit)
│   ├── config.py            # Pydantic Settings & environment loader
│   ├── database.py          # SQLAlchemy Session & Base & Category Seeder
│   ├── main.py              # Inisialisasi FastAPI & Middleware
│   └── create_admin.py      # Utilitas CLI pembuatan admin
├── docs/
│   ├── api/                 # Panduan & kontrak integrasi API (Frontend & Data/ML)
│   └── reports/             # Laporan berkala implementasi langkah (step0-1, step2-3, step4-5)
├── scripts/                 # Skrip benchmark, smoke test & Docker entrypoint
│   ├── entrypoint.sh        # Entrypoint Docker (Alembic upgrade + Uvicorn)
│   ├── perf_search.py       # Benchmark performa full-text search (2.000 dokumen)
│   └── smoke_test.py        # Skrip otomatis smoke test end-to-end
├── tests/                   # Suite pengujian otomatis Pytest (114 test)
│   ├── conftest.py          # Fixture database test & storage terisolasi
│   ├── test_api.py          # Pengujian API umum & auth
│   ├── test_failures.py     # Pengujian log kegagalan & antrian retry (F01-F12)
│   ├── test_naming_service.py # Pengujian standardisasi nama (N01-N07)
│   ├── test_category_service.py # Pengujian hierarki & constraint kategori (C01-C04)
│   ├── test_placement.py    # Pengujian penempatan folder KB (P01-P11)
│   ├── test_search.py       # Pengujian pencarian KB full-text & filter (S01-S16)
│   ├── test_document_detail.py # Pengujian buka PDF asli & teks (D01-D05)
│   ├── test_metadata_correction.py # Pengujian koreksi metadata & audit diff (M01-M07)
│   ├── test_extraction_internal.py # Pengujian integrasi worker ML (E01-E12)
│   └── test_dashboard.py    # Pengujian dashboard ringkasan & audit target_resource (B01-B03, A01)
├── .env.example             # Template variabel lingkungan
├── docker-compose.yml       # Definisi service PostgreSQL + Backend
├── Dockerfile               # Image build backend Python 3.11-slim
├── requirements.txt         # Dependensi produksi
└── requirements-dev.txt     # Dependensi pengembangan & pengujian
```

