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
Suite pengujian mencakup 70 test otomatis (T01–T25, F01–F12, N01–N07, C01–C04, P01–P11) menggunakan database uji terpisah `hero_test`:
```bash
python -m pytest -q
```

### 2. Menjalankan Smoke Test
Smoke test memvalidasi end-to-end server yang sedang berjalan (termasuk kegagalan, retry, pohon kategori, dan penempatan KB):
```bash
# Terhadap server lokal / docker
python scripts/smoke_test.py http://127.0.0.1:8000
```

---

## ⚠️ Antrian Kegagalan & Retry (Langkah 2)

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

### 2. Alur Penanganan & Contoh Request
- **Melihat Antrian Kegagalan:** `GET /api/v1/ingest/failures?follow_up_status=belum_ditangani`
- **Mengubah Status (Abaikan / Aktifkan Kembali):**
  ```http
  PATCH /api/v1/ingest/failures/{failure_id}
  Content-Type: application/json

  {
    "follow_up_status": "diabaikan",
    "handling_note": "Abaikan berkas uji coba"
  }
  ```
- **Memproses Ulang (Retry Tunggal dengan Override):**
  ```http
  POST /api/v1/ingest/failures/{failure_id}/retry
  Content-Type: application/json

  {
    "category_id": 1,
    "access_classification": "publik",
    "document_role": "corpus_eksisting"
  }
  ```
- **Batch Retry:** `POST /api/v1/ingest/failures/retry` dengan body `{"failure_ids": [1, 2, 3]}`.

---

## 📂 Penamaan Baku & Struktur Folder KB (Langkah 3)

### 1. Alur Dua Tahap Staging & Penempatan
1. **Saat Ingest Awal:** Berkas fisik disimpan sementara di area staging `pdf/_inbox/` dengan nama sementara `<hash12>_<nama_asli>.pdf`.
2. **Saat Penempatan (Placement):** Jika metadata dokumen telah mencukupi (`regulation_number` atau `regulation_type` + `release_date`), berkas otomatis distandarisasi dan dipindahkan ke:
   `kb/<jalur kategori>/<nama baku>.pdf`.

### 2. Format Penamaan Baku
Format penamaan baku: `{nomor} {judul} {tahun}` (contoh: `11-POJK.03-2022 Penyelenggaraan Teknologi Informasi oleh Bank Umum 2022.pdf`).
- Karakter ilegal sistem berkas (`/ \ : * ? " < > |`) dibersihkan secara otomatis.
- Unsur yang belum diketahui diganti dengan wildcard `NA`.
- Jika panjang melebihi batas (default 150 karakter), bagian judul dipotong secara aman di batas kata tanpa memotong nomor maupun tahun.

### 3. Konfigurasi via Environment Variables
```env
NAMING_TEMPLATE="{nomor} {judul} {tahun}"
NAMING_WILDCARD=NA
NAMING_MAX_LENGTH=150
CATEGORY_PATH_TEMPLATE="{jenis}/{tahun}"
CATEGORY_UNKNOWN_TYPE=Lainnya
CATEGORY_UNKNOWN_YEAR=Tanpa Tahun
DRAFT_CATEGORY_ROOT="Draft Kajian"
```

---

## 📡 Daftar Endpoint API (v0.3.0)

### 1. Health & Sistem
| Method | Endpoint | Deskripsi |
|---|---|---|
| `GET` | `/` | Status ringkas service |
| `GET` | `/health` | Health check database (`SELECT 1`) & flag auth |
| `GET` | `/debug-routes` | Daftar semua rute (khusus `APP_ENV=development`) |

### 2. Ingest Pipeline & Log Kegagalan (`/api/v1/ingest`)
| Method | Endpoint | Deskripsi |
|---|---|---|
| `POST` | `/upload-pdf` | Upload PDF regulasi / draft kajian (tunggal/jamak). Mengembalikan `failure_id` pada kegagalan dan objek `placement` pada keberhasilan. |
| `GET` | `/check-duplicate` | Screening deduplikasi sebelum upload |
| `GET` | `/jobs` | Riwayat job ingest (dilengkapi `open_failures_count` dan `source_id`) |
| `GET` | `/jobs/{job_id}` | Detail lengkap job ingest beserta daftar dokumen, durasi, dan kegagalan/duplikat |
| `GET` | `/status` | Statistik ringkasan dokumen, job, dan `open_failures` |
| `GET` | `/failures` | Daftar log kegagalan & antrian retry (filter: `job_id`, `failure_type`, `follow_up_status`, `include_duplicates`) |
| `GET` | `/failures/{failure_id}` | Detail satu baris kegagalan |
| `PATCH` | `/failures/{failure_id}` | Update status tindak lanjut (`belum_ditangani` <-> `diabaikan`) |
| `POST` | `/failures/{failure_id}/retry` | Memproses ulang (retry) dokumen dari karantina |
| `POST` | `/failures/retry` | Batch retry beberapa item kegagalan sekaligus |

### 3. Dokumen Regulasi & Penempatan KB (`/api/v1/documents`)
| Method | Endpoint | Deskripsi |
|---|---|---|
| `GET` | `/` | Daftar dokumen regulasi (filter: klasifikasi akses, peran, kategori, status keberlakuan) |
| `GET` | `/{document_id}` | Detail dokumen regulasi beserta pasal, rujukan hukum, `category_path`, dan status `is_placed` |
| `PUT` | `/{document_id}/status` | Update status keberlakuan (membuat `legal_references` jika dicabut/diubah) |
| `POST` | `/{document_id}/place` | Pemicu penamaan baku dan pemindahan dokumen ke folder KB (`kb/...`) |
| `POST` | `/place-pending` | Batch penempatan dokumen yang masih berada di staging ke folder KB |

### 4. Kategori Knowledge Base (`/api/v1/categories`)
| Method | Endpoint | Deskripsi |
|---|---|---|
| `GET` | `/` | Daftar datar seluruh kategori |
| `GET` | `/tree` | Pohon hierarki folder KB lengkap dengan `document_count` langsung dan `total_document_count` turunan |
| `GET` | `/{category_id}` | Detail satu kategori beserta jalur root->leaf dan jumlah dokumen |
| `POST` | `/` | Buat kategori baru (menolak duplikat nama di bawah induk yang sama dengan HTTP 409) |

### 5. Situs Sumber Scraping (`/api/v1/scraping-sources`)
| Method | Endpoint | Deskripsi |
|---|---|---|
| `POST` | `/` | Tambah situs sumber scraping baru (Audit: `CREATE_SOURCE`) |
| `GET` | `/` | Daftar semua situs sumber scraping |
| `GET` | `/{source_id}` | Detail situs sumber scraping |
| `PUT` / `PATCH` | `/{source_id}` | Update nama/URL/status aktif (Audit: `UPDATE_SOURCE`) |
| `DELETE` | `/{source_id}` | Hapus situs sumber scraping (Audit: `DELETE_SOURCE`) |

### 6. Otentikasi & Jejak Audit
| Method | Endpoint | Deskripsi |
|---|---|---|
| `POST` | `/api/v1/auth/login` | Login form OAuth2 untuk memperoleh token JWT Bearer |
| `GET` | `/api/v1/audit-logs/` | Daftar jejak audit aktivitas sistem (filter: `action`, `user_id`) |

### 7. Internal Pipeline (`/api/v1/internal`)
| Method | Endpoint | Deskripsi |
|---|---|---|
| `POST` | `/articles` | Bulk insert chunk pasal & embedding 1536-dim (proteksi `X-Internal-API-Key`) |

---

## 📁 Struktur Folder Proyek

```
hero-backend/
├── alembic/                 # Skrip migrasi database Alembic
│   ├── versions/            # Riwayat revisi migrasi skema
│   └── env.py               # Konfigurasi environment migrasi
├── app/
│   ├── models/              # ORM SQLAlchemy & Enums (Document, JobIngest, IngestFailure, Category, ...)
│   ├── routers/             # Endpoint FastAPI per modul (ingest, documents, categories, ...)
│   ├── schemas/             # Pydantic validation & response models
│   ├── services/            # Logika bisnis (File validation, Storage, Ingest, Failure, Naming, Category, Placement, Audit)
│   ├── config.py            # Pydantic Settings & environment loader
│   ├── database.py          # SQLAlchemy Session & Base & Category Seeder
│   ├── main.py              # Inisialisasi FastAPI & Middleware
│   └── create_admin.py      # Utilitas CLI pembuatan admin
├── docs/
│   └── reports/             # Laporan berkala implementasi langkah
├── scripts/                 # Skrip smoke test & Docker entrypoint
│   ├── entrypoint.sh        # Entrypoint Docker (Alembic upgrade + Uvicorn)
│   └── smoke_test.py        # Skrip otomatis smoke test
├── tests/                   # Suite pengujian otomatis Pytest (70 test)
│   ├── conftest.py          # Fixture database test & storage terisolasi
│   ├── test_api.py          # Pengujian API umum & auth
│   ├── test_failures.py     # Pengujian log kegagalan & antrian retry (F01-F12)
│   ├── test_naming_service.py # Pengujian standardisasi nama (N01-N07)
│   ├── test_category_service.py # Pengujian hierarki & constraint kategori (C01-C04)
│   └── test_placement.py    # Pengujian penempatan folder KB (P01-P11)
├── .env.example             # Template variabel lingkungan
├── docker-compose.yml       # Definisi service PostgreSQL + Backend
├── Dockerfile               # Image build backend Python 3.11-slim
├── requirements.txt         # Dependensi produksi
└── requirements-dev.txt     # Dependensi pengembangan & pengujian
```
