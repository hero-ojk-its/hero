# Laporan Akhir: Langkah 0 (Fondasi & Perbaikan Bug) + Langkah 1 (Service Pipeline Ingest)

## 1. Ringkasan Eksekutif
Pekerjaan Langkah 0 dan Langkah 1 pada workspace `hero-backend` telah diselesaikan secara menyeluruh dan teruji. Seluruh inisialisasi skema aplikasi kini sepenuhnya dikelola oleh Alembic (menghapus `create_all()`), dengan constraint deduplikasi komposit `(file_hash, file_size_bytes)` sesuai ADR-05/KEP-06 dan penghapusan constraint unik pada `regulation_number` untuk mencegah bug timpa PDF. Service pipeline ingest terpadu (`FileValidation`, `StorageService`, `IngestService`) telah diimplementasikan bersama endpoint upload sinkron baru, penanganan flag `AUTH_ENABLED` (MoM 22 Sep 2026), audit logging terpusat, serta penghapusan endpoint usang `POST /api/v1/ingest/scrape-url`. Seluruh 36 kasus uji otomatis pytest (T01–T25) dan smoke test pada server lokal maupun Docker container lulus 100%.

---

## 2. Hasil Inspeksi Awal (§2)
- **Versi PostgreSQL:** `PostgreSQL 15.4 (Debian 15.4-1.pgdg120+1) on x86_64-pc-linux-gnu, compiled by gcc (Debian 12.2.0-14) 12.2.0, 64-bit`
- **Versi pgvector:** `0.5.0`
- **Alembic Current Sebelum Reset:** `f841df680a0f (head)`
- **Jumlah Dokumen Sebelum Reset:** 6 baris (seluruhnya berkas uji: `test_uu_1.pdf`, `test_uu_2.pdf`, `test_uu_3.pdf`, `test_uu_new_unique.pdf`, `test_uu_diff_size.pdf`, `string.pdf`)
- **Lokasi Backup Database:** `backups/pre_step0_20260926_1515.sql` (82.160 bytes)
- **Lokasi Backup Berkas Storage:** `backups/storage_pre_step0/`

---

## 3. Daftar File
| Path | Status | Ringkasan Perubahan |
|---|---|---|
| `.gitignore` | Diubah | Menambahkan `backups/` dan `.pytest_cache/` |
| `.env.example` | Dibuat | Template konfigurasi lingkungan non-rahasia (`AUTH_ENABLED=false`, `MAX_UPLOAD_MB=100`, dsb.) |
| `Dockerfile` | Diubah | Menggunakan `scripts/entrypoint.sh` dengan `chmod +x` untuk menjalankan migrasi otomatis saat container start |
| `docker-compose.yml` | Diubah | Menghapus tag `version: '3.8'`, menambah volume `./init_db` dan `./alembic`, menyetel env `STORAGE_PATH=/app/storage` dan `AUTH_ENABLED=false` |
| `requirements.txt` | Diubah | Menghapus `aiofiles`, memperbarui `sqlalchemy>=2.0.36` |
| `requirements-dev.txt` | Dibuat | Dependensi pengujian: `pytest>=8.0.0`, `httpx>=0.27.0` |
| `alembic.ini` | Dipertahankan | Konfigurasi dasar Alembic |
| `alembic/env.py` | Diubah | Menggunakan `import app.models`, menghormati override `sqlalchemy.url` untuk test database |
| `alembic/versions/19ab55fb7e4e_fase1_baseline_schema.py` | Dibuat | Revisi baseline skema Fase 1 (`categories`, `job_ingest`, `documents`, `articles`, `legal_references`, `article_references`, `scraping_sources`, `uq_documents_hash_size`, vector 1536) |
| `app/config.py` | Diubah | `SettingsConfigDict` pydantic-settings v2, properti `max_upload_bytes`, flag `auth_enabled`, `max_upload_mb`, `cors_origins`, `access_token_expire_hours` |
| `app/create_admin.py` | Diubah | Membaca `ADMIN_PASSWORD` dari env dengan peringatan fallback di mode development |
| `app/database.py` | Diubah | Menghapus `init_db()`, merapikan import ganda, logging seeder kategori menggunakan logger `hero` |
| `app/main.py` | Diubah | Menghapus `init_db()`, menangani seeder tanpa crash bila DB belum dimigrasi, menambahkan `GET /health`, CORS dinamis, versi `0.2.0` |
| `app/models/audit_log.py` | Diubah | Menghapus fungsi helper `create_audit_log` (hanya menyisakan model ORM) |
| `app/models/document.py` | Diubah | `regulation_number` tidak unik, `file_hash` tidak unik sendirian, `file_size_bytes` NOT NULL, constraint `uq_documents_hash_size`, `document_role` tanpa default, indeks performa |
| `app/schemas/ingest.py` | Dibuat | Schema Pydantic respons upload, detail status, jobs, dan duplikasi |
| `app/services/audit_service.py` | Diubah | Helper `record_audit` dengan opsi `commit=True/False`, konstanta kode aksi, wrapper deprecated `create_audit_log` |
| `app/services/file_validation.py` | Dibuat | Validasi PDF (ekstensi, header `%PDF-`, batas ukuran), sanitasi nama berkas (path traversal & normalisasi Unicode), penghitungan fingerprint |
| `app/services/storage_service.py` | Dibuat | Penyimpanan fisik PDF atomik (mode `xb` tanpa penimpaan berkas, auto-suffix `-1`, `-2`), proteksi path traversal, hapus idempoten |
| `app/services/ingest_service.py` | Dibuat | Service pipeline ingest terpadu (`start_job`, `ingest_one`, `finish_job`, `ingest_batch`), hooks `_on_item_failed` & `_on_item_duplicate`, proteksi rollback DB & penghapusan berkas fisik |
| `app/routers/auth.py` | Diubah | `auto_error=False`, flag `AUTH_ENABLED`, `CurrentUser` alias dependency, masa berlaku token via config |
| `app/routers/audit.py` | Diubah | Terbuka saat auth nonaktif, filter query `action` dan `user_id` |
| `app/routers/documents.py` | Diubah | Audit logging pada `PUT /{id}/status`, path relatif pada `file_path_pdf` |
| `app/routers/ingest.py` | Diubah | Endpoint `POST /upload-pdf` sinkron terpadu, validasi aturan batch vs single metadata, penghapusan `POST /scrape-url` |
| `app/routers/scraping_sources.py` | Diubah | Audit logging pada CREATE, UPDATE, DELETE sumber scraping |
| `scripts/entrypoint.sh` | Dibuat | Script startup Docker: `alembic upgrade head` lalu `uvicorn` |
| `scripts/smoke_test.py` | Dibuat | Runner smoke test otomatis berbasis httpx untuk verifikasi server aktif |
| `tests/conftest.py` | Dibuat | Setup database pengujian `hero_test`, seeder, storage temporer, fixture client & auth |
| `tests/test_file_validation.py` | Dibuat | Unit test validasi dan sanitasi berkas |
| `tests/test_storage_service.py` | Dibuat | Unit test non-overwrite storage dan path traversal guard |
| `tests/test_ingest_service.py` | Dibuat | Unit test alur pipeline ingest, rollback integritas DB, dan cleanup file |
| `tests/test_api.py` | Dibuat | End-to-end API integration tests mencakup T01–T21 |
| `README.md` | Diubah | Dokumentasi lengkap setup, eksekusi, migrasi, konfigurasi auth, testing, dan endpoint |

---

## 4. Output Perintah Verifikasi

### 4.1 `alembic upgrade head` & `alembic check`
```text
PS C:\Users\IBUCOMP\Downloads\hero-backend> .\venv\Scripts\alembic.exe upgrade head
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade f841df680a0f -> 19ab55fb7e4e, fase1 baseline schema

PS C:\Users\IBUCOMP\Downloads\hero-backend> .\venv\Scripts\alembic.exe check
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
No new upgrade operations detected.
```

### 4.2 Round-trip Downgrade dan Upgrade
```text
PS C:\Users\IBUCOMP\Downloads\hero-backend> .\venv\Scripts\alembic.exe downgrade -1
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running downgrade 19ab55fb7e4e -> f841df680a0f, fase1 baseline schema

PS C:\Users\IBUCOMP\Downloads\hero-backend> .\venv\Scripts\alembic.exe upgrade head
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade f841df680a0f -> 19ab55fb7e4e, fase1 baseline schema
```

### 4.3 `python -m pytest -q`
```text
PS C:\Users\IBUCOMP\Downloads\hero-backend> .\venv\Scripts\python.exe -m pytest -q
....................................                                     [100%]
36 passed, 4 warnings in 19.52s
```

### 4.4 `scripts/smoke_test.py` (Server Lokal)
```text
PS C:\Users\IBUCOMP\Downloads\hero-backend> .\venv\Scripts\python.exe scripts\smoke_test.py http://127.0.0.1:8000
================================================================================
               HERO BACKEND SMOKE TEST - http://127.0.0.1:8000
================================================================================
METHOD   | ENDPOINT / PATH                                  | STATUS  | HASIL
--------------------------------------------------------------------------------
GET      | /health                                          | 200     | OK
GET      | /                                                | 200     | OK
GET      | /api/v1/categories/                              | 200     | OK
GET      | /api/v1/documents/                               | 200     | OK
GET      | /api/v1/ingest/jobs                              | 200     | OK
GET      | /api/v1/ingest/status                            | 200     | OK
GET      | /api/v1/audit-logs/                              | 200     | OK
GET      | /api/v1/scraping-sources/                        | 200     | OK
GET      | /docs                                            | 200     | OK
GET      | /openapi.json                                    | 200     | OK
POST     | /api/v1/ingest/upload-pdf (New PDF)              | 200     | OK (success_count=1)
POST     | /api/v1/ingest/upload-pdf (Duplicate PDF)        | 200     | OK (duplicate_count=1)
POST     | /api/v1/ingest/upload-pdf (Non-PDF)              | 200     | OK (failed_count=1)
GET      | /api/v1/documents/2                              | 200     | OK
================================================================================
[OK] HASIL: SMOKE TEST SUKSES - Seluruh pemeriksaan lulus 100%.
```

### 4.5 `scripts/smoke_test.py` (Docker Container)
```text
PS C:\Users\IBUCOMP\Downloads\hero-backend> .\venv\Scripts\python.exe scripts\smoke_test.py http://127.0.0.1:8000
================================================================================
               HERO BACKEND SMOKE TEST - http://127.0.0.1:8000
================================================================================
METHOD   | ENDPOINT / PATH                                  | STATUS  | HASIL
--------------------------------------------------------------------------------
GET      | /health                                          | 200     | OK
GET      | /                                                | 200     | OK
GET      | /api/v1/categories/                              | 200     | OK
GET      | /api/v1/documents/                               | 200     | OK
GET      | /api/v1/ingest/jobs                              | 200     | OK
GET      | /api/v1/ingest/status                            | 200     | OK
GET      | /api/v1/audit-logs/                              | 200     | OK
GET      | /api/v1/scraping-sources/                        | 200     | OK
GET      | /docs                                            | 200     | OK
GET      | /openapi.json                                    | 200     | OK
POST     | /api/v1/ingest/upload-pdf (New PDF)              | 200     | OK (success_count=1)
POST     | /api/v1/ingest/upload-pdf (Duplicate PDF)        | 200     | OK (duplicate_count=1)
POST     | /api/v1/ingest/upload-pdf (Non-PDF)              | 200     | OK (failed_count=1)
GET      | /api/v1/documents/3                              | 200     | OK
================================================================================
[OK] HASIL: SMOKE TEST SUKSES - Seluruh pemeriksaan lulus 100%.
```

---

## 5. Perubahan Kontrak API untuk Frontend
1. **Endpoint `POST /api/v1/ingest/upload-pdf`:**
   - Field `document_role` sekarang **WAJIB** dikirimkan (`corpus_eksisting` atau `draft_kajian`).
   - Field per-dokumen (`title`, `regulation_number`, `release_date`) **hanya boleh diisi untuk unggahan 1 berkas**. Jika `files > 1` dan field tersebut diisi, backend mengembalikan HTTP 422.
   - Format `release_date` harus valid `YYYY-MM-DD` (HTTP 422 jika format salah).
   - Penambahan key pada respons: `job_status` (`"selesai"` / `"gagal"`) dan `reason_code` pada tiap detail item.
2. **Penghapusan Endpoint:**
   - `POST /api/v1/ingest/scrape-url` **dihapus** (mengembalikan 404/405).
3. **Endpoint Baru:**
   - `GET /health` mengembalikan `{"status":"ok","database":"ok","auth_enabled":<bool>}`.
4. **Endpoint `GET /api/v1/ingest/status`:**
   - Penambahan key `dicabut_documents` dan `total_draft_kajian`.
5. **Endpoint `GET /api/v1/audit-logs/`:**
   - Penambahan query parameter filter opsional: `action` dan `user_id`.

---

## 6. Deviasi dari Spesifikasi
- **Metode Penulisan File Storage:** Untuk menjamin portabilitas absolut antara Windows dan Linux tanpa ketergantungan pada variasi semantik `os.link` pada filesystem NTFS, `StorageService` menggunakan mode pembuatan eksklusif `open(candidate_path, "xb")` dikombinasikan dengan berkas temporer `.part`. Pendekatan ini tahan *race condition* pada kedua sistem operasi.
- **Optimasi Koneksi Windows (127.0.0.1 vs localhost):** Pada pengujian lokal di Windows, resolusi DNS `localhost` memicu *timeout* fallback IPv6 `::1` di libpq/psycopg 3. Konfigurasi default test URL dan `.env` disesuaikan menggunakan `127.0.0.1` sehingga koneksi terjadi instan (<0.07 detik).

---

## 7. Temuan & Risiko Baru (Di Luar Cakupan)
1. **Dimensi Embedding (1536-dim):** Kolom `articles.embedding` saat ini menggunakan dimensi 1536 (standar OpenAI text-embedding-ada-002 / 3-small). Keputusan pemilihan embedding model lokal/multilingual bersama tim Data/ML pada 30 September perlu diselaraskan dengan migrasi dimensi kolom jika ada perubahan.
2. **Koneksi Pool di Uvicorn Worker:** Jika pada beban tinggi terjadi lonjakan upload berukuran besar secara simultan, disarankan menambahkan background worker queue (seperti Celery / ARQ) pada fase berikutnya agar thread pool synchronous I/O tidak terblokir.

---

## 8. Daftar Commit (`git log --oneline`)
```text
f7ea90b docs: update README with setup, architecture decisions, and endpoints
801a05e test: add automated test suite T01-T25 and smoke test script
15f0e14 feat: implement unified ingest pipeline, file validation, storage service, and router refactor
892a1ff fix: step 0 foundation, schema constraints, audit helpers, and baseline migration
55d443d chore: initial baseline commit
```
