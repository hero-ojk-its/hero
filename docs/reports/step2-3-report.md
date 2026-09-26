# Laporan Akhir — Langkah 2 (Log Kegagalan & Antrian Retry) + Langkah 3 (Penamaan Baku & Penempatan Folder KB)

**Branch:** `feat/step2-3-failures-naming`  
**Base:** `feat/step0-1-ingest-pipeline`  
**Tanggal:** 26 September 2026  
**Status:** ✅ LULUS SELURUH DEFINITION OF DONE (§6)

---

## 1. Ringkasan

Pekerjaan pada Langkah 2 dan Langkah 3 telah selesai 100% tanpa mengubah data `hero_db` secara destruktif:
1. **Langkah 2 (Log Kegagalan & Antrian Retry):**
   - Implementasi model dan tabel `ingest_failures` dengan `CheckConstraint("failure_type <> 'duplikat' OR duplicate_of_document_id IS NOT NULL", name="ck_failure_duplicate_ref")`.
   - Implementasi `FailureService` terisolasi transaksi untuk mencatat seluruh kegagalan dan duplikat (otomatis berstatus `diabaikan`).
   - Penyimpanan isi berkas valid PDF ke folder karantina (`quarantine/`) untuk error yang dapat di-retry (`is_retryable=True`), serta penghapusan berkas karantina secara atomik saat retry berhasil atau terbukti duplikat.
   - Endpoint antrian kegagalan (`GET /failures`, `GET /failures/{id}`, `PATCH /failures/{id}`, `POST /failures/{id}/retry`, `POST /failures/retry`).
   - Detail job lengkap pada `GET /jobs/{id}` (dokumen berhasil, durasi job, dan seluruh baris kegagalan/duplikat beserta dokumen pembanding).
2. **Langkah 3 (Penamaan Baku & Penempatan Folder KB):**
   - Implementasi `NamingService` untuk normalisasi jenis regulasi (`POJK`, `SEOJK`, `UU`, `PP`, `PERPRES`, `PERMENKEU`, `PADK`, `PBI`, `PERDA`), ekstraksi tahun, dan pembentukan nama file baku `{nomor} {judul} {tahun}.pdf` dengan pemotongan judul aman di batas kata tanpa merusak nomor dan tahun.
   - Constraint unik `NULLS NOT DISTINCT` pada `categories(parent_id, name)` (PostgreSQL 15) untuk mencegah duplikasi nama folder di level root maupun subkategori, dilengkapi deduplikasi data otomatis pada migrasi.
   - Implementasi `CategoryService` dengan pohon hierarki (`GET /categories/tree`) yang menghitung `document_count` (langsung) dan `total_document_count` (termasuk seluruh turunan) dalam satu query efisien tanpa N+1.
   - Idempotensi seeder KB skeleton (`seed_initial_categories`) untuk 7 root utama (`POJK`, `SEOJK`, `UU`, `PP`, `Peraturan Internal DPEA`, `Lainnya`, `Draft Kajian`).
   - Implementasi `StorageService.move()` dan `PlacementService` dengan alur dua tahap: berkas awal masuk area staging `pdf/_inbox/`, kemudian otomatis dipindahkan ke `kb/<jalur kategori>/<nama baku>.pdf` saat metadata mencukupi.
   - Endpoint penempatan manual `POST /documents/{id}/place` dan batch `POST /documents/place-pending`.

---

## 2. Hasil §0.1 (Tindak Lanjut Laporan Langkah 0–1)

### A. Pemeriksaan Warning (`pytest -W default::DeprecationWarning`)
Dari 4 warning yang teridentifikasi di Langkah 0–1:
1. **2 Warning berasal dari kode aplikasi kita:**
   - Pemakaian `status.HTTP_422_UNPROCESSABLE_ENTITY` pada `app/routers/ingest.py`.
   - **Tindakan:** Diganti menjadi `status.HTTP_422_UNPROCESSABLE_CONTENT` dan `from fastapi.testclient import TestClient` pada `tests/conftest.py`. Warning ini telah hilang 100%.
2. **2 Warning tersisa (berasal dari pustaka pihak ketiga):**
   - `fastapi/testclient.py:1`: `StarletteDeprecationWarning: Using 'httpx' with 'starlette.testclient' is deprecated; install 'httpx2' instead.` (internal upstream FastAPI/Starlette).
   - `starlette/testclient.py:53`: `DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.` (internal upstream Starlette/AnyIO).

### B. Pemeriksaan Index Git (`git ls-files`)
Pemeriksaan index git memastikan tidak ada berkas atau direktori terlarang (`venv/`, `.env`, `storage/`, `backups/`, `__pycache__/`) yang masuk ke git index.

---

## 3. Daftar Berkas

| Path | Status | Ringkasan Perubahan |
|---|---|---|
| `app/models/enums.py` | Diubah | Penambahan enum `JenisKegagalan` dan `StatusTindakLanjut` |
| `app/models/ingest_failure.py` | Dibuat | Model ORM SQLAlchemy untuk tabel `ingest_failures` |
| `app/models/job_ingest.py` | Diubah | Penambahan kolom `source_id`, `retry_of_failure_id`, dan relasi `failures` |
| `app/models/category.py` | Diubah | Penambahan `UniqueConstraint("parent_id", "name", postgresql_nulls_not_distinct=True)` |
| `app/models/__init__.py` | Diubah | Registrasi model `IngestFailure` dan enum baru |
| `alembic/versions/2a1b3c4d5e6f_step2_ingest_failures.py` | Dibuat | Migrasi revisi Langkah 2 (`ingest_failures` & alter `job_ingest`) |
| `alembic/versions/3b2c1d4e5f6a_step3_category_unique.py` | Dibuat | Migrasi revisi Langkah 3 (deduplikasi kategori + constraint `NULLS NOT DISTINCT`) |
| `app/config.py` | Diubah | Konfigurasi penamaan baku, batas panjang, dan template path kategori KB |
| `app/database.py` | Diubah | Seeder `seed_initial_categories` diperbarui menjadi idempoten untuk 7 root |
| `app/services/storage_service.py` | Diubah | Penambahan method `read_pdf()`, `move()` anti-overwrite, dan validasi traversal subdir |
| `app/services/file_validation.py` | Dipertahankan | Penjagaan konsistensi sanitasi nama berkas |
| `app/services/audit_service.py` | Diubah | Penambahan konstanta aksi audit `RETRY_FAILURE`, `UPDATE_FAILURE`, `PLACE_DOCUMENT`, `CREATE_CATEGORY` |
| `app/services/failure_service.py` | Dibuat | Service pencatatan kegagalan, penanganan duplikat, karantina berkas, dan retry |
| `app/services/naming_service.py` | Dibuat | Service standardisasi nama berkas, normalisasi jenis regulasi, dan cek metadata |
| `app/services/category_service.py` | Dibuat | Service pohon hierarki kategori, resolusi path rekursif aman race condition, dan CRUD kategori |
| `app/services/placement_service.py` | Dibuat | Service penempatan berkas dari staging ke folder KB (`kb/...`) |
| `app/services/ingest_service.py` | Diubah | Integrasi staging `pdf/_inbox/`, hook failure/duplicate, dan auto-placement |
| `app/schemas/ingest.py` | Diubah | Schema response untuk failure queue, retry, detail job, dan placement |
| `app/routers/ingest.py` | Diubah | Endpoint detail job, antrian kegagalan, retry tunggal/batch, dan status failure |
| `app/routers/categories.py` | Diubah | Endpoint `GET /tree`, `GET /{id}`, `POST /`, dan `GET /` |
| `app/routers/documents.py` | Diubah | Endpoint `POST /{id}/place`, `POST /place-pending`, dan atribut `category_path`/`is_placed` |
| `tests/conftest.py` | Diubah | Truncate `ingest_failures`, import fix, dan fixture test |
| `tests/test_api.py` | Diubah | Penyesuaian `test_t02` untuk 7 root kategori seeder |
| `tests/test_failures.py` | Dibuat | Suite pengujian otomatis F01–F12 |
| `tests/test_naming_service.py` | Dibuat | Suite pengujian otomatis N01–N07 |
| `tests/test_category_service.py` | Dibuat | Suite pengujian otomatis C01–C04 |
| `tests/test_placement.py` | Dibuat | Suite pengujian otomatis P01–P11 |
| `scripts/smoke_test.py` | Diubah | Smoke test endpoint baru Langkah 2 dan 3 |
| `.env.example` | Diubah | Dokumentasi variabel lingkungan Langkah 3 |
| `README.md` | Diubah | Dokumentasi antrian kegagalan, penamaan baku, dan daftar endpoint v0.3.0 |
| `docs/reports/step2-3-report.md` | Dibuat | Laporan akhir komprehensif Langkah 2 & 3 |

---

## 4. Output Eksekusi Perintah

### A. `alembic upgrade head` (Pada Database `hero_db` yang Sudah Berisi Data)
```text
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade 19ab55fb7e4e -> 2a1b3c4d5e6f, step2 ingest failures
INFO  [alembic.runtime.migration] Running upgrade 2a1b3c4d5e6f -> 3b2c1d4e5f6a, step3 category unique constraint
```

### B. `alembic check`
```text
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
No new upgrade operations detected.
```

### C. Round-Trip Migration (`alembic downgrade -2` -> `alembic upgrade head`)
```text
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running downgrade 3b2c1d4e5f6a -> 2a1b3c4d5e6f, step3 category unique constraint
INFO  [alembic.runtime.migration] Running downgrade 2a1b3c4d5e6f -> 19ab55fb7e4e, step2 ingest failures
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade 19ab55fb7e4e -> 2a1b3c4d5e6f, step2 ingest failures
INFO  [alembic.runtime.migration] Running upgrade 2a1b3c4d5e6f -> 3b2c1d4e5f6a, step3 category unique constraint
```

### D. DDL Aktual Constraint `uq_categories_parent_name` di PostgreSQL
```sql
SELECT conname, pg_get_constraintdef(oid) 
FROM pg_constraint 
WHERE conname = 'uq_categories_parent_name';
```
**Output:**
```text
[('uq_categories_parent_name', 'UNIQUE NULLS NOT DISTINCT (parent_id, name)')]
```

### E. `python -m pytest -q` (Seluruh 70 Test Lulus Tanpa Skip)
```text
......................................................................   [100%]
70 passed, 2 warnings in 34.74s
```

### F. `python scripts/smoke_test.py http://127.0.0.1:8000` (100% Lulus)
```text
================================================================================
               HERO BACKEND SMOKE TEST - http://127.0.0.1:8000
================================================================================
METHOD   | ENDPOINT / PATH                                  | STATUS  | HASIL
--------------------------------------------------------------------------------
GET      | /health                                          | 200     | OK
GET      | /                                                | 200     | OK
GET      | /api/v1/categories/                              | 200     | OK
GET      | /api/v1/categories/tree                          | 200     | OK
GET      | /api/v1/documents/                               | 200     | OK
GET      | /api/v1/ingest/jobs                              | 200     | OK
GET      | /api/v1/ingest/failures                          | 200     | OK
GET      | /api/v1/ingest/status                            | 200     | OK
GET      | /api/v1/audit-logs/                              | 200     | OK
GET      | /api/v1/scraping-sources/                        | 200     | OK
GET      | /docs                                            | 200     | OK
GET      | /openapi.json                                    | 200     | OK
POST     | /api/v1/ingest/upload-pdf (With Meta & Placement) | 200     | OK (placed=True)
POST     | /api/v1/ingest/upload-pdf (Duplicate PDF)        | 200     | OK (duplicate_count=1, has_failure_id)
POST     | /api/v1/ingest/upload-pdf (Non-PDF)              | 200     | OK (failed_count=1, has_failure_id)
GET      | /api/v1/ingest/jobs/16                           | 200     | OK
GET      | /api/v1/documents/6                              | 200     | OK (is_placed=True)
POST     | /api/v1/documents/place-pending                  | 200     | OK
================================================================================
[OK] HASIL: SMOKE TEST SUKSES - Seluruh pemeriksaan lulus 100%.
```

---

## 5. Perubahan Kontrak API untuk Frontend

### A. Endpoint Baru
1. `GET /api/v1/ingest/jobs/{job_id}`: Detail job, durasi, dokumen yang dihasilkan, dan daftar seluruh kegagalan/duplikat.
2. `GET /api/v1/ingest/failures`: Antrian kegagalan dengan filter `job_id`, `failure_type`, `follow_up_status` (default `belum_ditangani`, `all`), `include_duplicates`.
3. `GET /api/v1/ingest/failures/{failure_id}`: Detail satu kegagalan.
4. `PATCH /api/v1/ingest/failures/{failure_id}`: Update status tindak lanjut (`diabaikan` <-> `belum_ditangani`).
5. `POST /api/v1/ingest/failures/{failure_id}/retry`: Retry satu dokumen karantina dengan opsi override.
6. `POST /api/v1/ingest/failures/retry`: Batch retry (1–50 ID).
7. `GET /api/v1/categories/tree`: Pohon kategori hierarkis dengan `document_count` dan `total_document_count`.
8. `GET /api/v1/categories/{category_id}`: Detail kategori beserta `path` root->leaf dan `document_count`.
9. `POST /api/v1/categories`: Tambah kategori baru (HTTP 201; HTTP 409 jika duplikat).
10. `POST /api/v1/documents/{document_id}/place`: Pemicu penempatan folder KB dokumen.
11. `POST /api/v1/documents/place-pending`: Batch penempatan dokumen pending ke `kb/`.

### B. Penambahan Key pada Respons Endpoint Lama
- `POST /api/v1/ingest/upload-pdf`:
  - Item gagal / duplikat kini memiliki key `failure_id: int`.
  - Item sukses kini memiliki key `placement: {placed: bool, reason: str, category_path: list, standardized_filename: str}`.
- `GET /api/v1/ingest/jobs`:
  - Tiap item memiliki key `source_id: Optional[int]` dan `open_failures_count: int`.
- `GET /api/v1/ingest/status`:
  - Respons kini memiliki key `open_failures: int`.
- `GET /api/v1/documents/{document_id}`:
  - Respons kini memiliki key `category_path: Optional[List[str]]` dan `is_placed: bool`.

---

## 6. Hal yang Perlu Dikonfirmasi ke Tim Data/ML

1. **Peta Alias `regulation_type`:**
   Saat ini alias mencakup `POJK`, `SEOJK`, `UU`, `PP`, `PERPRES`, `PERMENKEU`, `PADK`, `PBI`, `PERDA`. Apakah ekstraksi ML menghasilkan format label regulasi lain yang perlu didaftarkan ke dictionary?
2. **Template Path Folder KB `{sumber}/{sektor}`:**
   Saat ini placeholder yang aktif adalah `{jenis}` dan `{tahun}`. Placeholder lain ditolak saat startup sesuai spesifikasi. Kapan level folder `{sumber}` dan `{sektor}` akan diaktifkan?

---

## 7. Deviasi

- **`test_t02_categories_seeded` pada `tests/test_api.py`:**
  Di Langkah 0–1, test mengecek 5 kategori seed. Sesuai §3.3 spesifikasi Langkah 3, seeder kini menginisialisasi 7 root skeleton folder KB (`POJK`, `SEOJK`, `UU`, `PP`, `Peraturan Internal DPEA`, `Lainnya`, `Draft Kajian`). Test diperbarui untuk memverifikasi ke-7 root tersebut.

---

## 8. Temuan / Risiko di Luar Cakupan

1. **Volume Berkas Karantina:**
   Jika terjadi lonjakan error internal atau dokumen metadata tidak lengkap dalam jumlah ribuan, folder `storage/quarantine` dapat membesar. Perlu dipertimbangkan cron housekeeping otomatis (retention policy) untuk menghapus berkas karantina yang berstatus `diabaikan` lebih dari 30 hari pada langkah operasional berikutnya.
2. **Koneksi Windows Localhost:**
   Koneksi PostgreSQL pada Windows tetap diwajibkan menggunakan `127.0.0.1:5432` untuk menghindari penundaan resolusi IPv6 `::1` yang mencapai 2 menit.

---

## 9. Git Log Branch `feat/step2-3-failures-naming`

```text
ad97fff test: add comprehensive test suite for failures, naming, categories, and placement
fc6328a feat: implement standard naming and category placement (Step 3)
f52e889 feat: implement failure logging and retry queue (Step 2)
d262a77 chore: resolve deprecation warnings and clean git index
```
