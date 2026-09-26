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

### 1. Menjalankan Pytest (Unit & Integrasi T01–T25)
Suite pengujian menggunakan database uji terpisah `hero_test`:
```bash
python -m pytest -q
```

### 2. Menjalankan Smoke Test
Smoke test memvalidasi end-to-end server yang sedang berjalan:
```bash
# Terhadap server lokal / docker
python scripts/smoke_test.py http://127.0.0.1:8000
```

---

## 🗄️ Skema Database & Keputusan Arsitektur

### Perubahan Skema Fase 1 (Langkah 0):
1. **Deduplikasi (ADR-05 / KEP-06):**
   - Kolom `regulation_number` **tidak unik** (tetap berindeks) agar tidak memicu kegagalan saat versi berbeda menggunakan nomor yang sama.
   - Kolom `file_hash` (SHA-256) dan `file_size_bytes` (BIGINT, `nullable=False`) diikat dengan constraint unik komposit:
     `UniqueConstraint("file_hash", "file_size_bytes", name="uq_documents_hash_size")`.
2. **Peran Dokumen (ADR-03 / FR-SCR-04a):**
   - Kolom `document_role` bernilai `corpus_eksisting` atau `draft_kajian`, **wajib dinyatakan** saat unggah (`nullable=False`, tanpa default Python).
3. **Penyimpanan Berkas (ADR-01):**
   - `file_path_pdf` menyimpan **path relatif terhadap `STORAGE_PATH`** (contoh: `pdf/3fa1c2d4e5f6_nama.pdf`) untuk portabilitas antara lokal, Docker, dan VPS.
   - Penyimpanan fisik bersifat atomik dan **tidak pernah menimpa** berkas yang sudah ada (menambahkan sufiks `-1`, `-2`, dst.).
4. **Indeks Performa:**
   - Ditambahkan indeks pada `status_keberlakuan`, `document_role`, dan `processing_status`.

---

## 📡 Daftar Endpoint API (v0.2.0)

### 1. Health & Sistem
| Method | Endpoint | Deskripsi |
|---|---|---|
| `GET` | `/` | Status ringkas service |
| `GET` | `/health` | Health check database (`SELECT 1`) & flag auth |
| `GET` | `/debug-routes` | Daftar semua rute (khusus `APP_ENV=development`) |

### 2. Ingest Pipeline (`/api/v1/ingest`)
| Method | Endpoint | Deskripsi |
|---|---|---|
| `POST` | `/upload-pdf` | Upload PDF regulasi / draft kajian (tunggal/jamak). `document_role` & `access_classification` WAJIB. |
| `GET` | `/check-duplicate` | Screening deduplikasi sebelum upload |
| `GET` | `/jobs` | Riwayat job ingest dengan pagination & filter |
| `GET` | `/status` | Statistik ringkasan dokumen & job pipeline |
| *~~POST~~* | *~~`/scrape-url`~~* | *[DIHAPUS] Digantikan pipeline terpadu pada Langkah 7* |

### 3. Dokumen Regulasi (`/api/v1/documents`)
| Method | Endpoint | Deskripsi |
|---|---|---|
| `GET` | `/` | Daftar dokumen regulasi (filter: klasifikasi akses, peran, kategori, status keberlakuan) |
| `GET` | `/{document_id}` | Detail dokumen regulasi beserta pasal & rujukan hukum |
| `PUT` | `/{document_id}/status` | Update status keberlakuan (membuat `legal_references` jika dicabut/diubah) |

### 4. Situs Sumber Scraping (`/api/v1/scraping-sources`)
| Method | Endpoint | Deskripsi |
|---|---|---|
| `POST` | `/` | Tambah situs sumber scraping baru (Audit: `CREATE_SOURCE`) |
| `GET` | `/` | Daftar semua situs sumber scraping |
| `GET` | `/{source_id}` | Detail situs sumber scraping |
| `PUT` / `PATCH` | `/{source_id}` | Update nama/URL/status aktif (Audit: `UPDATE_SOURCE`) |
| `DELETE` | `/{source_id}` | Hapus situs sumber scraping (Audit: `DELETE_SOURCE`) |

### 5. Kategori Knowledge Base (`/api/v1/categories`)
| Method | Endpoint | Deskripsi |
|---|---|---|
| `GET` | `/` | Daftar 5 kategori default KB (`POJK`, `SEOJK`, `UU`, `PP`, `Peraturan Internal DPEA`) |

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
│   ├── models/              # ORM SQLAlchemy & Enums
│   ├── routers/             # Endpoint FastAPI per modul
│   ├── schemas/             # Pydantic validation & response models
│   ├── services/            # Logika bisnis (File validation, Storage, Ingest, Audit)
│   ├── config.py            # Pydantic Settings & environment loader
│   ├── database.py          # SQLAlchemy Session & Base
│   ├── main.py              # Inisialisasi FastAPI & Middleware
│   └── create_admin.py      # Utilitas CLI pembuatan admin
├── backups/                 # Direktori backup SQL & storage pra-reset
├── init_db/                 # Skrip inisialisasi awal container PostgreSQL
├── scripts/                 # Skrip smoke test & Docker entrypoint
│   ├── entrypoint.sh        # Entrypoint Docker (Alembic upgrade + Uvicorn)
│   └── smoke_test.py        # Skrip otomatis smoke test
├── tests/                   # Suite pengujian otomatis Pytest (T01–T25)
├── .env.example             # Template variabel lingkungan
├── docker-compose.yml       # Definisi service PostgreSQL + Backend
├── Dockerfile               # Image build backend Python 3.11-slim
├── requirements.txt         # Dependensi produksi
└── requirements-dev.txt     # Dependensi pengembangan & pengujian
```
