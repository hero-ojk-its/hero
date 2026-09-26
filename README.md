# HERO Backend

Backend API untuk sistem **HERO (Harmonisasi & Analisa Regulasi Otomatis)** — pengelolaan dokumen regulasi, pencarian semantik, klasifikasi akses kepatuhan NDA, dan cross-reference pasal.

**Stack**: FastAPI (Python 3.11/3.13) + PostgreSQL + pgvector

---

## 🚀 Cara Menjalankan (Lokal)

### Prasyarat
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) sudah terinstall dan berjalan

### Langkah 1 — Masuk Folder

```bash
cd hero-backend
```

### Langkah 2 — Jalankan Semua Service

```bash
docker-compose up -d --build
```

Perintah ini akan otomatis:
- Download image PostgreSQL + pgvector
- Membuat container `hero_postgres` (database)
- Membuat container `hero_backend` (API FastAPI)
- Mengaktifkan ekstensi pgvector di database
- Menginisialisasi semua tabel database

### Langkah 3 — Cek Status

```bash
docker-compose ps
```

Semua container harus berstatus `Up`.

### Langkah 4 — Akses API

Buka browser dan akses: **http://localhost:8000/docs**

Tersedia Swagger UI interaktif dengan seluruh endpoint dan dokumentasi skema request/response.

---

## 📁 Struktur Folder

```
hero-backend/
├── app/
│   ├── main.py          # Entry point FastAPI & lifespan
│   ├── config.py        # Konfigurasi dari .env
│   ├── database.py      # Engine SQLAlchemy & init_db
│   ├── models/
│   │   ├── __init__.py  # Export semua model & enum
│   │   ├── enums.py     # Definisi enum status, klasifikasi akses, dll.
│   │   ├── category.py  # ORM: tabel categories (hierarki folder KB)
│   │   ├── job_ingest.py# ORM: tabel job_ingest (tracking batch ingest)
│   │   ├── document.py  # ORM: tabel documents
│   │   └── article.py   # ORM: articles, article_references, legal_references
│   └── routers/
│       ├── documents.py # GET /api/v1/documents (list & detail)
│       └── ingest.py    # POST /api/v1/ingest/upload-pdf, /jobs, /status
├── init_db/
│   └── 01_enable_pgvector.sql  # Auto-run saat DB pertama dibuat
├── storage/             # Folder penyimpanan PDF (auto-created)
├── .env                 # Konfigurasi environment
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

---

## 🗄️ Skema Database

Skema diselaraskan 1:1 dengan `docs/08-data-model-dictionary.md`.

### 1. `categories` (KATEGORI)
Menyimpan struktur hierarki folder Knowledge Base.

| Kolom | Tipe | Keterangan |
|-------|------|------------|
| `id` | SERIAL PK | Primary key |
| `name` | VARCHAR(255) | Nama kategori/folder |
| `parent_id` | FK → categories.id (NULL) | Parent kategori (self-referential) |
| `auto_created` | BOOLEAN | Dibuat otomatis oleh aturan klasifikasi |
| `classification_rule` | TEXT | Aturan/regex klasifikasi otomatis |
| `created_at` / `updated_at` | TIMESTAMPTZ | Waktu pembuatan & pembaruan |

### 2. `job_ingest` (JOB_INGEST)
Tracking proses ingest / upload dokumen.

| Kolom | Tipe | Keterangan |
|-------|------|------------|
| `id` | SERIAL PK | Primary key |
| `job_type` | ENUM | `scraping`, `unggah_manual`, `sinkron_folder` |
| `source_ref` | VARCHAR(255) | Nama file atau sumber rujukan |
| `triggered_by` | VARCHAR(100) | Pemicu ingest |
| `started_at` | TIMESTAMPTZ | Waktu mulai |
| `finished_at` | TIMESTAMPTZ (NULL) | Waktu selesai |
| `status` | ENUM | `antrian`, `berjalan`, `selesai`, `gagal` |
| `success_count` | INT | Jumlah dokumen berhasil |
| `duplicate_count` | INT | Jumlah dokumen duplikat |
| `failed_count` | INT | Jumlah dokumen gagal |

### 3. `documents` (DOKUMEN)
Menyimpan metadata regulasi, path PDF asli, klasifikasi akses kepatuhan NDA, dan status pemrosesan.

| Kolom | Tipe | Keterangan |
|-------|------|------------|
| `id` | SERIAL PK | Primary key |
| `title` | VARCHAR(255) | Judul lengkap regulasi/kajian |
| `regulation_number` | VARCHAR(100) (NULL, UNIQUE) | Nomor regulasi unik (mis: PP-24-2005) |
| `regulation_type` | VARCHAR(100) (NULL) | Jenis regulasi (UU, PP, Permen, dll.) |
| `release_date` | DATE (NULL) | Tanggal terbit |
| `source_url` | TEXT (NULL) | URL sumber dokumen |
| `file_path_pdf` | TEXT | Path file PDF fisik |
| `file_hash` | VARCHAR(64) UNIQUE | SHA-256 hash untuk deduplikasi |
| `file_size_bytes` | BIGINT (NULL) | Ukuran file PDF (bytes) |
| `standardized_filename` | VARCHAR(255) (NULL) | Nama file terstandarisasi |
| `access_classification` | ENUM (NOT NULL) | `publik` / `non_publik` (kepatuhan NDA) |
| `document_role` | ENUM (NOT NULL) | `corpus_eksisting` / `draft_kajian` |
| `status_keberlakuan` | ENUM (NOT NULL) | `berlaku`, `diubah`, `dicabut`, `tidak_diketahui` |
| `processing_status` | ENUM (NOT NULL) | `diterima`, `diproses`, `perlu_koreksi`, `terindeks`, `gagal`, `ditolak` |
| `extraction_method` | ENUM (NULL) | `teks_langsung` / `ocr` |
| `full_text` | TEXT (NULL) | Teks lengkap dokumen |
| `category_id` | FK → categories.id (NULL) | Kategori/folder KB |
| `job_id` | FK → job_ingest.id (NULL) | Job ingest terkait |
| `created_at` / `updated_at` | TIMESTAMPTZ | Timestamp |

### 4. `articles` (PASAL)
Struktur hierarkis pasal (Bab → Pasal → Ayat → Huruf) dengan pgvector.

| Kolom | Tipe | Keterangan |
|-------|------|------------|
| `id` | SERIAL PK | Primary key |
| `document_id` | FK → documents.id | Dokumen pemilik pasal |
| `parent_id` | FK → articles.id (NULL) | Hierarki rekursif bab/pasal/ayat |
| `chapter_title` | VARCHAR(255) (NULL) | Judul bab (misal: BAB II) |
| `article_number` | VARCHAR(50) | Nomor pasal/ayat (misal: Pasal 5) |
| `content_text` | TEXT | Isi teks pasal/ayat |
| `level` | VARCHAR(20) | `bab`, `pasal`, `ayat`, `huruf` |
| `order_index` | INT (NULL) | Urutan tampil dalam dokumen |
| `embedding` | vector(1536) (NULL) | Vektor embedding semantic search |

### 5. `article_references` (RUJUKAN_PASAL)
Relasi antar pasal (misal: amandemen pasal spesifik).

| Kolom | Tipe | Keterangan |
|-------|------|------------|
| `id` | SERIAL PK | Primary key |
| `source_article_id` | FK → articles.id | Pasal yang merujuk |
| `target_article_id` | FK → articles.id (NULL) | Pasal yang dirujuk (SET NULL jika target belum di KB) |
| `target_citation_text` | VARCHAR(255) (NULL) | Teks sitiran target fallback |
| `relation_type` | VARCHAR(50) | `MENGUBAH`, `MENCABUT`, `MERUJUK`, `MELENGKAPI` |

### 6. `legal_references` (RUJUKAN_HUKUM)
Rujukan hukum level dokumen (Dasar Hukum, Konsideran, Pencabutan).

| Kolom | Tipe | Keterangan |
|-------|------|------------|
| `id` | SERIAL PK | Primary key |
| `document_id` | FK → documents.id | Dokumen sumber rujukan |
| `cited_text` | TEXT | Teks kutipan rujukan hukum |
| `referenced_document_id` | FK → documents.id (NULL) | Dokumen yang dirujuk jika ada di KB |
| `referenced_document_status` | ENUM (NULL) | Status keberlakuan regulasi yang dirujuk |
| `reference_type` | ENUM | `dasar_hukum`, `rujukan_pasal`, `pencabutan`, `perubahan` |

---

## 📡 API Endpoints

| Method | Endpoint | Deskripsi |
|--------|----------|-----------|
| GET | `/` | Health check & info service |
| GET | `/health` | Health check detail |
| GET | `/api/v1/documents/` | Daftar dokumen regulasi (filter: `access_classification`, `document_role`, `category_id`, `status_keberlakuan`) |
| GET | `/api/v1/documents/{id}` | Detail dokumen lengkap beserta pasal level teratas & rujukan hukum |
| POST | `/api/v1/ingest/upload-pdf` | Upload PDF regulasi/kajian baru (wajib form `access_classification`, tracking otomatis ke `JobIngest`) |
| GET | `/api/v1/ingest/jobs` | Riwayat job ingest dengan pagination & filter status/tipe |
| GET | `/api/v1/ingest/status` | Ringkasan statistik pipeline ingest & penyimpanan |

---

## 🔧 Perintah Berguna

```bash
# Jalankan semua service
docker-compose up -d --build

# Lihat log backend
docker-compose logs -f backend

# Lihat log database
docker-compose logs -f db

# Stop semua service
docker-compose down

# Stop + hapus data DB lama jika ingin rebuild skema dari awal (HATI-HATI: data lokal terhapus!)
docker-compose down -v

# Masuk ke PostgreSQL langsung
docker exec -it hero_postgres psql -U hero_user -d hero_db
```

---

## 👥 Tim

| Role | Nama | Tanggung Jawab |
|------|------|----------------|
| Backend | (kamu) | Database schema, Docker setup, API |
| Data/ML | Fathir | Scraping, preprocessing, embedding |
| Lead | Personil_A | Arsitektur & koordinasi |
