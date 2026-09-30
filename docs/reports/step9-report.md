# Laporan Langkah 9: Kontrak API Fase 1 (#91) dan Format Penamaan Berkas Dinamis (#90)

**Penulis:** Senior Backend Engineer  
**Tanggal:** 30 September 2026  
**Branch:** `feat/step9-api-contract-rename`  
**Status:** SELESAI (Definition of Done 100% terpenuhi)

---

## 1. Ringkasan Eksekutif

Langkah 9 menyelesaikan dua isu prioritas kritis menjelang rilis MVP Fase 1 (11 Oktober 2026):
1. **#90 (US-20c) Penamaan Berkas Dinamis:** Pengguna dapat menentukan urutan komponen penamaan berkas (`nama`, `tahun`, `jenis`, `bidang`, `nomor`) dan karakter pemisah (`" "`, `"_"`, `"-"`) secara interaktif dari UI. Ditambahkan kolom `bidang`, `naming_format`, dan `naming_separator` di database serta endpoint pendukung `GET /api/v1/naming/components` dan `POST /api/v1/naming/preview`.
2. **#91 (AI-T12) Kontrak API Fase 1:** Menyusun dokumen kontrak API yang komprehensif, terstruktur per alur UI frontend (`docs/api/KONTRAK-API-FASE1.md`), snapshot OpenAPI (`docs/api/openapi-fase1.json`), koleksi permintaan REST Client (`docs/api/hero-fase1.http`), serta panduan perubahan frontend (`docs/api/frontend-changes-step9.md`). Seluruh contoh JSON dan tabel enum dibangkitkan secara deterministik dan idempoten via `scripts/build_api_contract.py`.

---

## 2. Desain Penamaan Berkas Dinamis

### 2.1 Komponen dan Resolusi Nilai
Komponen penamaan yang didukung (`nama`, `tahun`, `jenis`, `bidang`, `nomor`) diproses dengan aturan:
- **`nama`**: Mengambil `doc.title`; jika belum ada, mengambil nama stem dari `original_filename`. Jika panjang nama berkas melebihi batas (default 150 karakter), pemotongan dilakukan khusus pada komponen nama di batas kata.
- **`nomor`**: Mengambil `regulation_number` dengan karakter garis miring (`/` dan `\`) diganti strip (`-`).
- **`tahun`**: Diekstrak dari `release_date.year` atau 4 digit tahun dalam `regulation_number`.
- **`jenis`**: Dinormalisasi via alias standar (`normalize_regulation_type`, misal `Peraturan Otoritas Jasa Keuangan` -> `POJK`).
- **`bidang`**: Nilai kolom `bidang` (misal `Perbankan`, `Pasar Modal`, `IKNB`, `BMKS`).
- Komponen yang kosong / belum terisi otomatis digantikan dengan wildcard `NAMING_WILDCARD` (default `NA`) tanpa menggagalkan proses rename.

### 2.2 Hirarki Precedence
Format penamaan dievaluasi berdasarkan urutan prioritas:
1. **Request Payload**: Format yang dikirim saat pull scan (`naming_format` array), unggah manual (`naming_format` string dipisah koma), atau trigger folder run.
2. **Default Sumber**: `scraping_sources.default_naming_format` dan `default_naming_separator`.
3. **Konfigurasi Lingkungan**: `NAMING_TEMPLATE` di `.env` (diparsing otomatis ke format komponen).

### 2.3 Keputusan Akhiran Hash di `_inbox/` vs `kb/`
- **Saat Ingest (`pdf/_inbox/`)**: Berkas disimpan dengan format baku pilihan ditambah akhiran pembeda `__<8 hex SHA-256>` sebelum ekstensi `.pdf` (misal: `pdf/_inbox/POJK 10 Tahun 2026 Bank Umum_NA_NA_Perbankan__0f357835.pdf`). Keputusan ini menjamin setiap unggahan di staging inbox tidak saling menimpa meskipun metadata awalnya sama (misal beberapa berkas belum memiliki judul).
- **Saat Penempatan (`kb/{jenis}/{tahun}/`)**: Berkas dipindahkan tanpa akhiran hash (misal: `kb/POJK/2026/POJK 10 Tahun 2026 Bank Umum.pdf`). Bentrok nama ditangani secara atomik oleh `storage_service` non-overwrite (menambahkan suffix `-1`, `-2`, dst.).
- **Tujuan `unduh_folder` (ZIP)**: Berkas di dalam arsip ZIP diformat langsung sesuai `naming_format` sesi scan, memudahkan pengurutan berkas lokal oleh tim kurator/hukum.

---

## 3. Daftar File yang Diubah / Ditambahkan

| File | Status | Keterangan |
|---|---|---|
| `alembic/versions/2ba03d5c9aa4_step9_api_contract_rename.py` | Baru | Migrasi penambahan kolom `bidang`, `naming_format`, `naming_separator` |
| `app/models/document.py` | Modifikasi | Menambahkan field `bidang`, `naming_format`, `naming_separator` |
| `app/models/scraping_source.py` | Modifikasi | Menambahkan `default_naming_format`, `default_naming_separator` |
| `app/models/scan_session.py` | Modifikasi | Menambahkan `naming_format`, `naming_separator` |
| `app/schemas/naming.py` | Baru | Skema Pydantic untuk komponen dan pratinjau penamaan |
| `app/schemas/document.py` | Modifikasi | Field `bidang` pada respon dokumen, daftar, dan pembaruan metadata |
| `app/schemas/scraping_source.py` | Modifikasi | Field `default_naming_format` & `default_naming_separator` |
| `app/schemas/scan.py` | Modifikasi | Field `naming_format` & `naming_separator` pada pull scan |
| `app/services/naming_service.py` | Modifikasi | Core refactor `build_standard_filename`, validasi komponen & separator |
| `app/services/placement_service.py` | Modifikasi | Menggunakan `doc.naming_format` & `doc.naming_separator` saat placement |
| `app/services/ingest_service.py` | Modifikasi | Simpan format ke dokumen, simpan inbox dengan hash suffix `__<hash8>` |
| `app/services/scan_service.py` | Modifikasi | Dukungan naming dinamis saat pull KB dan export ZIP |
| `app/services/search_service.py` | Modifikasi | Filter `bidang` pada pencarian dan filter KB |
| `app/routers/naming.py` | Baru | Endpoint `GET /api/v1/naming/components` & `POST /api/v1/naming/preview` |
| `app/routers/documents.py` | Modifikasi | Dukungan filter `bidang` & update `bidang` pada PATCH metadata |
| `app/routers/ingest.py` | Modifikasi | Form data `naming_format`, `naming_separator`, `bidang` |
| `app/routers/internal.py` | Modifikasi | Dukungan alias `sektor`/`sector` -> `bidang` pada hasil ekstraksi ML |
| `app/routers/scans.py` | Modifikasi | Parameter `naming_format` & `naming_separator` pada pull |
| `app/routers/scraping_sources.py` | Modifikasi | CRUD default naming format & override di endpoint `run` |
| `app/main.py` | Modifikasi | Pendaftaran `naming_router` ke aplikasi FastAPI |
| `scripts/build_api_contract.py` | Baru | Generator otomatis kontrak API Fase 1, snapshot OpenAPI, dan REST client |
| `scripts/smoke_test.py` | Modifikasi | Penambahan Step 11 pengujian penamaan dinamis dan verifikasi `standardized_filename` |
| `docs/api/KONTRAK-API-FASE1.md` | Baru | Dokumen lengkap kontrak API Fase 1 per alur UI frontend |
| `docs/api/openapi-fase1.json` | Baru | Snapshot skema OpenAPI Fase 1 |
| `docs/api/hero-fase1.http` | Baru | Koleksi request REST Client siap eksekusi |
| `docs/api/frontend-changes-step9.md` | Baru | Ringkasan perubahan API untuk tim frontend |
| `README.md` | Modifikasi | Menambahkan tautan dokumen API untuk Tim Frontend |
| `tests/test_naming_step9.py` | Baru | Suite pengujian otomatis N01–N14 dan C01–C04 |
| `tests/test_docs_enums.py` | Modifikasi | Memindai validitas enum di `KONTRAK-API-FASE1.md` |

---

## 4. Output Mentah Terminal

### 4.1 Alembic Upgrade Head
```text
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
```

### 4.2 Alembic Check
```text
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.ddl.postgresql] Detected sequence named 'scan_candidates_id_seq' as owned by integer column 'scan_candidates(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'audit_logs_id_seq' as owned by integer column 'audit_logs(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'articles_id_seq' as owned by integer column 'articles(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'legal_references_id_seq' as owned by integer column 'legal_references(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'source_files_id_seq' as owned by integer column 'source_files(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'article_references_id_seq' as owned by integer column 'article_references(id)', assuming SERIAL and omitting
C:\Users\IBUCOMP\Downloads\hero-backend\venv\Lib\site-packages\alembic\autogenerate\compare.py:1034: UserWarning: Computed default on documents.search_vector cannot be modified
  util.warn("Computed default on %s.%s cannot be modified" % (tname, cname))
No new upgrade operations detected.
```

### 4.3 Pytest Suite Lengkap (188 Tests)
```text
============================= test session starts =============================
platform win32 -- Python 3.13.7, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\IBUCOMP\Downloads\hero-backend
plugins: anyio-4.15.1
collected 188 items

tests\test_api.py .....................                                  [ 11%]
tests\test_category_service.py ....                                      [ 13%]
tests\test_crawler_simple.py .....                                       [ 15%]
tests\test_dashboard.py ....                                             [ 18%]
tests\test_deploy_readiness.py .....                                     [ 20%]
tests\test_docs_enums.py ..                                              [ 21%]
tests\test_document_detail.py .....                                      [ 24%]
tests\test_extraction_internal.py .............                          [ 31%]
tests\test_failures.py ............                                      [ 37%]
tests\test_file_validation.py ........                                   [ 42%]
tests\test_ingest_service.py ....                                        [ 44%]
tests\test_local_folder.py ........s.......                              [ 52%]
tests\test_metadata_correction.py .......                                [ 56%]
tests\test_naming_service.py .......                                     [ 60%]
tests\test_naming_step9.py ..................                            [ 69%]
tests\test_placement.py ...........                                      [ 75%]
tests\test_scan_flow.py .......                                          [ 79%]
tests\test_scan_push.py .                                                [ 79%]
tests\test_search.py .................                                   [ 88%]
tests\test_source_validation.py ........                                 [ 93%]
tests\test_step8_fixes.py .....                                          [ 95%]
tests\test_storage_service.py ...                                        [ 97%]
tests\test_url_guard.py .....                                            [100%]

============================== warnings summary ===============================
venv\Lib\site-packages\fastapi\testclient.py:1
  C:\Users\IBUCOMP\Downloads\hero-backend\venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

venv\Lib\site-packages\starlette\testclient.py:53
  C:\Users\IBUCOMP\Downloads\hero-backend\venv\Lib\site-packages\starlette\testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
=========== 187 passed, 1 skipped, 2 warnings in 182.60s (0:03:02) ============
```

### 4.4 Eksekusi Uji Idempotensi `scripts/build_api_contract.py` dan `git diff --stat`
```text
C:\Users\IBUCOMP\Downloads\hero-backend> .\venv\Scripts\python scripts/build_api_contract.py
Memulai build API Contract HERO Backend...
Kontrak API berhasil ditulis ke: C:\Users\IBUCOMP\Downloads\hero-backend\docs\api\KONTRAK-API-FASE1.md
Snapshot OpenAPI berhasil ditulis ke: C:\Users\IBUCOMP\Downloads\hero-backend\docs\api\openapi-fase1.json
REST Client collection berhasil ditulis ke: C:\Users\IBUCOMP\Downloads\hero-backend\docs\api\hero-fase1.http
Pembuatan kontrak API selesai!

C:\Users\IBUCOMP\Downloads\hero-backend> .\venv\Scripts\python scripts/build_api_contract.py
Memulai build API Contract HERO Backend...
Kontrak API berhasil ditulis ke: C:\Users\IBUCOMP\Downloads\hero-backend\docs\api\KONTRAK-API-FASE1.md
Snapshot OpenAPI berhasil ditulis ke: C:\Users\IBUCOMP\Downloads\hero-backend\docs\api\openapi-fase1.json
REST Client collection berhasil ditulis ke: C:\Users\IBUCOMP\Downloads\hero-backend\docs\api\hero-fase1.http
Pembuatan kontrak API selesai!

C:\Users\IBUCOMP\Downloads\hero-backend> git diff --stat docs/api/
```
*(Output `git diff --stat docs/api/` kosong, membuktikan 100% idempoten).*

### 4.5 Smoke Test Server Lokal
```text
================================================================================
               HERO BACKEND SMOKE TEST - http://127.0.0.1:8000
================================================================================
METHOD   | ENDPOINT / PATH                                    | STATUS  | HASIL
--------------------------------------------------------------------------------
GET      | /health                                            | 200     | OK
GET      | /                                                  | 200     | OK
GET      | /api/v1/categories/                                | 200     | OK
GET      | /api/v1/categories/tree                            | 200     | OK
GET      | /api/v1/documents/                                 | 200     | OK
GET      | /api/v1/documents/needs-review                     | 200     | OK
GET      | /api/v1/dashboard/summary                          | 200     | OK
GET      | /api/v1/ingest/jobs                                | 200     | OK
GET      | /api/v1/ingest/failures                            | 200     | OK
GET      | /api/v1/ingest/status                              | 200     | OK
GET      | /api/v1/audit-logs/                                | 200     | OK
GET      | /api/v1/scraping-sources/                          | 200     | OK
GET      | /docs                                              | 200     | OK
GET      | /openapi.json                                      | 200     | OK
POST     | 1. /ingest/upload-pdf (Unggah PDF Awal)            | 200     | OK (doc_id=56)
POST     | 2. /internal/extraction/claim (Claim Antrean)      | 200     | OK (claimed & requeued non-target docs)
PATCH    | 3. /internal/documents/{id}/extraction             | 200     | OK (status=terindeks)
GET      | 4. /documents/?q=modal minimum perbankan 1... (Pencarian) | 200     | OK (total=1)
GET      | 5. /documents/56/pdf (Buka PDF)                    | 200     | OK (483 bytes)
PATCH    | 6. /documents/56/metadata (Koreksi)                | 200     | OK (title updated)
GET      | 7. /dashboard/summary (Dashboard)                  | 200     | OK (sections valid)
POST     | 8a. /ingest/upload-pdf (Duplicate Check)           | 200     | OK (duplicate_count=1)
POST     | 8b. /ingest/upload-pdf (Non-PDF Check)             | 200     | OK (failed_count=1)
POST     | 9a. /scraping-sources/ (Daftar Folder Lokal)       | 201     | OK (source_id=12)
POST     | 9b. /scraping-sources/12/run (Run 1)               | 200     | OK (2 success)
POST     | 9c. /scraping-sources/12/run (Run 2 Idempoten)     | 200     | OK (2 skipped)
DELETE   | 9d. /scraping-sources/12 (Hapus Sumber)            | 200     | OK
GET      | 10. /api/v1/scans/ (Pindai Situs)                  | 200     | DILEWATI (SMOKE_SCAN_URL tidak diset)
GET      | 11a. /naming/components                            | 200     | OK
POST     | 11b. /naming/preview                               | 200     | OK
POST     | 11c. /ingest/upload-pdf (Format Dinamis)           | 200     | OK (std_name=Regulasi Bursa Karbon 1790785582822_BMKS_NA.pdf)
================================================================================
[OK] HASIL: SMOKE TEST SUKSES - Seluruh pemeriksaan (Langkah 0-7) lulus 100%.
```

---

## 5. Perubahan Kontrak API (Penambahan Saja)

Sesuai Aturan Main 0.3, tidak ada path atau kunci respon lama yang diubah/dihapus:
1. **Endpoint Baru**:
   - `GET /api/v1/naming/components`: Mengembalikan daftar komponen penamaan yang didukung (`nama`, `tahun`, `jenis`, `bidang`, `nomor`), daftar pemisah yang diperbolehkan (`" "`, `"_"`, `"-"`), default wildcard (`"NA"`), default format, dan batas komponen maksimum (8).
   - `POST /api/v1/naming/preview`: Menghasilkan pratinjau nama berkas PDF dan mendeteksi komponen yang belum lengkap (`missing_components`).
2. **Kunci dan Parameter Tambahan**:
   - `bidang` (opsional): Ditambahkan pada `GET /api/v1/documents/` (filter query), `GET /api/v1/documents/{id}` (respon), `PATCH /api/v1/documents/{id}/metadata` (body), dan `POST /api/v1/ingest/upload-pdf` (form field).
   - `naming_format` & `naming_separator`: Ditambahkan pada `POST /api/v1/ingest/upload-pdf` (form field), `POST /api/v1/scans/{id}/pull` (request body), `POST /api/v1/scraping-sources/` & `PATCH /api/v1/scraping-sources/{id}` (default naming format sumber), dan `POST /api/v1/scraping-sources/{id}/run` (override body).

---

## 6. Inkonsistensi yang Ditemukan dan Perbaikannya (§2.4)

| Temuan Inkonsistensi | Dampak pada Frontend | Perbaikan yang Dilakukan |
|---|---|---|
| Ekstraksi ML mengirim alias `sektor` atau `sector`, sedangkan database menyimpan kolom `bidang`. | Jika kurator mengecek metadata, sektor OJK bisa hilang. | Ditambahkan `AliasChoices("bidang", "sektor", "sector")` pada skema `ExtractionResultIn` dan pemetaan di router internal. |
| Perbedaan urutan set / dictionary pada daftar `changed_fields`. | Respon snapshot API test berpotensi flappy pada run berulang. | Dinormalisasi via pengurutan daftar string alfabetis di fungsi `normalize_val`. |
| Pydantic / multipart form data `naming_format` pada unggah berkas. | Frontend mengirim form data multipart string (`"nama,jenis,tahun"`), bukan array JSON. | Router `upload_pdf` mem-parsing string dipisah koma menjadi `List[str]` secara transparan. |

---

## 7. Deviasi dan Risiko

- **Deviasi:** Tidak ada dependensi Python baru yang ditambahkan. Tidak ada perubahan breaking pada skema database atau respons API yang sudah ada.
- **Risiko & Mitigasi:**
  - *Risiko:* Pengguna memasukkan karakter tidak lazim di judul dokumen.
  - *Mitigasi:* Pembersihan karakter dilakukan otomatis oleh `_clean_field` dan `sanitize_filename`, menghapus karakter terlarang filesystem OS.

---

## 8. Status Git

### 8.1 `git log --oneline -6`
```text
095b003 test: unit and integration tests N01-N14, C01-C04 dan pembaruan smoke test
8c22424 docs(api): normalisasi kontrak API Fase 1 dan pembaruan builder
2e3d9eb docs(api): kontrak API Fase 1, snapshot openapi, REST collection, dan script builder
1c4bb4b feat(naming): format penamaan berkas dinamis, kolom bidang, dan endpoint pratinjau
0a7883c feat: kesiapan deploy produksi, hardening konfigurasi, demo seed/reset, dan runbook VPS
0bd893b fix(api): perbaiki konsistensi kontrak, enum docs, penamaan berkas failure, agregat dashboard, dan sanitasi smoke test
```

### 8.2 `git status --short`
```text
```
*(Working tree bersih, tanpa uncommitted files).*

### 8.3 `git remote -v`
```text
```
*(Kosong sesuai aturan main).*

---

## 9. Panduan Pengujian Manual untuk Personil_E (Swagger UI)

Buka Swagger UI di browser: `http://localhost:8000/docs`.

### Langkah 1: Melihat Komponen Penamaan yang Tersedia
1. Buka tag **Naming** -> `GET /api/v1/naming/components`.
2. Klik **Try it out** lalu **Execute**.
3. Pastikan respon 200 menampilkan daftar komponen dengan urutan UI: `nama`, `tahun`, `jenis`, `bidang`, `nomor`.

### Langkah 2: Mencoba Pratinjau Penamaan Berkas
1. Buka tag **Naming** -> `POST /api/v1/naming/preview`.
2. Klik **Try it out** dan kirim body:
   ```json
   {
     "naming_format": ["nama", "bidang", "tahun"],
     "naming_separator": "_",
     "sample": {
       "title": "Penyelenggaraan Bursa Karbon",
       "bidang": "BMKS",
       "release_date": "2026-08-20"
     }
   }
   ```
3. Klik **Execute**.
4. Periksa respon 200: `filename` bernilai `"Penyelenggaraan Bursa Karbon_BMKS_2026.pdf"` dan `missing_components` kosong `[]`.

### Langkah 3: Unggah Dokumen dengan Format Kustom
1. Buka tag **Ingest** -> `POST /api/v1/ingest/upload-pdf`.
2. Klik **Try it out**:
   - `files`: Pilih satu berkas PDF sampel.
   - `access_classification`: `publik`
   - `document_role`: `corpus_eksisting`
   - `title`: `Regulasi Fintech OJK`
   - `naming_format`: `nama,tahun`
   - `naming_separator`: `_`
3. Klik **Execute**.
4. Ambil `document_id` dari respon `details[0].document_id`.

### Langkah 4: Koreksi Metadata dan Periksa Perpindahan Berkas
1. Buka tag **Documents** -> `PATCH /api/v1/documents/{document_id}/metadata`.
2. Masukkan `document_id` dari Langkah 3 dan body:
   ```json
   {
     "regulation_type": "POJK",
     "regulation_number": "POJK 15/2026",
     "release_date": "2026-06-01",
     "bidang": "Fintech"
   }
   ```
3. Klik **Execute**.
4. Periksa objek `placement` pada respon: `placed: true`, `new_path: "kb/POJK/2026/Regulasi Fintech OJK_2026.pdf"`. Nama berkas baku mengikuti format `nama,tahun` yang dipilih saat unggah.

### Langkah 5: Tarik Sesi Pindai ke Unduh Folder (ZIP)
1. Buka tag **Scans** -> `POST /api/v1/scans/{scan_id}/pull`.
2. Kirim body:
   ```json
   {
     "destination": "unduh_folder",
     "naming_format": ["nama", "tahun"],
     "naming_separator": " "
   }
   ```
3. Setelah selesai, buka `GET /api/v1/scans/{scan_id}/download` untuk mengunduh arsip ZIP.
4. Buka ZIP di komputer lokal; berkas di dalam ZIP bernama `<nama> <tahun>.pdf` (misal: `peraturan_modal NA.pdf`).
