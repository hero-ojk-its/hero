# Laporan Pelaksanaan HERO Backend — Langkah 26

**Tanggal:** 30 Oktober 2026  
**Topik:** Temuan QA Ingest (PDF rusak/terenkripsi, teks kosong jadi gagal, status "belum berlaku", placeholder title, mask IP audit saat login mati)  
**Branch:** `fix/step26-qa-ingest`

---

## 1. Ringkasan Eksekutif

Langkah 26 menyelesaikan seluruh temuan pengujian QA Ingest (ING-01 s.d. ING-09) oleh QA Hamdan di lingkungan staging:
1. **Validasi PDF Bisa Dibuka (`app/services/file_validation.py`):**
   - Menambahkan integrasi `pypdf` dan `cryptography`.
   - Urutan validasi: ekstensi `.pdf` → ukuran berkas 0 byte → batas ukuran upload → header `%PDF-` → pembukaan struktur dengan `PdfReader(BytesIO(content), strict=False)`.
   - Mengidentifikasi PDF rusak/corrupt stream (`pdf_rusak`) dan PDF tanpa halaman (`len(pages) == 0`).
   - Penanganan enkripsi PDF: mencoba membuka proteksi pemilik dengan `reader.decrypt("")`. Jika berhasil (hanya owner password/copy-protection), dokumen **diterima** sesuai arahan Pak Faris. Jika memerlukan kata sandi pengguna (user password), ditolak dengan kode `pdf_terenkripsi`.
   - Perbaikan bug laten pemanggilan `validate_pdf` pada baris 148 `failure_service.py` yang sebelumnya tidak menyertakan argumen `max_bytes` (`TypeError`).
   - Kode alasan baru `pdf_rusak` dan `pdf_terenkripsi` dipetakan ke `failure_type=format_tidak_didukung`, tidak dikarantina, `is_retryable=False`, dan masuk antrean kegagalan dengan status `belum_ditangani`.
2. **Teks Ekstraksi Kosong Jadi Gagal (`app/routers/internal.py`):**
   - Pada `PATCH /internal/documents/{id}/extraction` (jalur sukses), bila teks dokumen (`full_text`) kosong atau hanya spasi: status dokumen diubah menjadi `gagal`, dicatat ke `IngestFailure` (`teks_kosong_ocr` untuk metode OCR, `teks_kosong` untuk metode teks langsung), `is_retryable=True`, audit `EXTRACTION_FAILED` dicatat, dokumen tidak dipindahkan ke `kb/`, serta metadata payload tetap disimpan.
3. **Status Keberlakuan "Belum Berlaku":**
   - Menambahkan enum `StatusKeberlakuan.belum_berlaku = "belum_berlaku"`.
   - Evaluasi di `recompute_status()`: bila dokumen (baik regulasi utama maupun lampiran) memiliki `effective_date > hari ini` tanpa aturan relasi pencabutan/pengubahan, sistem menetapkan status `belum_berlaku` dengan `status_source="tanggal_berlaku"`. Status manual tetap menang.
   - Endpoint internal baru `POST /api/v1/internal/documents/status/recompute` dilindungi `verify_internal_api_key` untuk evaluasi berkala (timer harian).
4. **Penyaringan Judul Placeholder:**
   - Judul bernilai `untitled`, `untitled document`, `tanpa judul`, `dokumen`, `document`, atau berawalan `microsoft word - document*` diabaikan sehingga dokumen tanpa judul tetap berstatus `perlu_koreksi`.
5. **Mask IP Audit Log Saat Login Mati:**
   - Pada `GET /api/v1/audit-logs/`, jika `AUTH_ENABLED=false`, seluruh entri respons mengembalikan `ip_address: null` demi privasi akses terbuka, tanpa mengubah data asli IP yang tersimpan di database.

---

## 2. Versi Dependensi Baru

Dipin pada `requirements.txt`:
- **`pypdf==6.21.4`**
- **`cryptography==50.0.2`**

---

## 3. Hasil Pemeriksaan Constraint Enum Database (`\d documents`)

Perintah yang dijalankan:
```bash
docker compose exec db psql -U hero_user -d hero_db -c "\d documents"
```

Output mentah terminal:
```text
                                             Table "public.documents"
             Column             |            Type             | Collation | Nullable |            Default            
--------------------------------+-----------------------------+-----------+----------+-------------------------------
 id                             | integer                     |           | not null | nextval('documents_id_seq'::regclass)
 title                          | character varying(255)      |           |          | 
 regulation_number              | character varying(100)      |           |          | 
 regulation_type                | character varying(50)       |           |          | 
 release_date                   | date                        |           |          | 
 regulation_year                | integer                     |           |          | 
 category_id                    | integer                     |           |          | 
 status_keberlakuan             | character varying(15)       |           |          | 
 access_classification          | character varying(20)       |           | not null | 
 file_path_pdf                  | character varying(500)      |           | not null | 
 standardized_filename          | character varying(255)      |           |          | 
 file_hash                      | character varying(64)       |           | not null | 
 file_size_bytes                | integer                     |           | not null | 
 processing_status              | character varying(20)       |           | not null | 
 created_at                     | timestamp without time zone |           | not null | now()
 updated_at                     | timestamp without time zone |           | not null | now()
 job_id                         | integer                     |           |          | 
 document_role                  | character varying(20)       |           | not null | 
 is_active                      | boolean                     |           | not null | true
 source_url                     | character varying(1000)     |           |          | 
 duplicate_of_id                | integer                     |           |          | 
 extracted_at                   | timestamp with time zone    |           |          | 
 extraction_attempts            | integer                     |           | not null | 0
 extraction_claimed_at          | timestamp with time zone    |           |          | 
 extraction_confidence          | jsonb                       |           |          | 
 extraction_engine              | character varying(100)      |           |          | 
 extraction_method              | character varying(50)       |           |          | 
 full_text                      | text                        |           |          | 
 bidang                         | character varying(100)      |           |          | 
 metadata_corrected_at          | timestamp with time zone    |           |          | 
 identity_key                   | character varying(120)      |           |          | 
 page_count                     | integer                     |           |          | 
 status_source                  | character varying(20)       |           |          | 
 attachment_label               | character varying(100)      |           |          | 
 effective_date                 | date                        |           |          | 
 is_attachment                  | boolean                     |           | not null | false
 parent_document_id             | integer                     |           |          | 
 parent_identity_key            | character varying(120)      |           |          | 
 analysis_stale_since           | timestamp with time zone    |           |          | 
 harmonization_stale_since      | timestamp with time zone    |           |          | 
Indexes:
    "documents_pkey" PRIMARY KEY, btree (id)
    "ix_documents_category_id" btree (category_id)
    "ix_documents_document_role" btree (document_role)
    "ix_documents_effective_date" btree (effective_date)
    "ix_documents_file_hash" btree (file_hash)
    "ix_documents_id" btree (id)
    "ix_documents_identity_key" btree (identity_key)
    "ix_documents_is_active" btree (is_active)
    "ix_documents_is_attachment" btree (is_attachment)
    "ix_documents_job_id" btree (job_id)
    "ix_documents_parent_document_id" btree (parent_document_id)
    "ix_documents_parent_identity_key" btree (parent_identity_key)
    "ix_documents_processing_status" btree (processing_status)
    "ix_documents_regulation_number" btree (regulation_number)
    "ix_documents_regulation_type" btree (regulation_type)
    "ix_documents_regulation_year" btree (regulation_year)
    "ix_documents_status_keberlakuan" btree (status_keberlakuan)
Foreign-key constraints:
    "documents_category_id_fkey" FOREIGN KEY (category_id) REFERENCES categories(id)
    "documents_duplicate_of_id_fkey" FOREIGN KEY (duplicate_of_id) REFERENCES documents(id)
    "documents_job_id_fkey" FOREIGN KEY (job_id) REFERENCES ingest_jobs(id)
    "documents_parent_document_id_fkey" FOREIGN KEY (parent_document_id) REFERENCES documents(id)
    "fk_documents_duplicate_of_id" FOREIGN KEY (duplicate_of_id) REFERENCES documents(id) ON DELETE SET NULL
    "fk_documents_parent_document_id" FOREIGN KEY (parent_document_id) REFERENCES documents(id) ON DELETE SET NULL
```

**Alasan Tidak Perlu Migrasi DB:**  
Kolom `status_keberlakuan` didefinisikan sebagai `character varying(15)`. String `"belum_berlaku"` memiliki panjang 13 karakter sehingga muat dalam batas panjang kolom (maksimal 15 karakter). Tidak ada CHECK constraint atau tipe PostgreSQL enum native pada tabel `documents`. Oleh karena itu, penambahan nilai pada enum SQLAlchemy python berjalan aman tanpa memerlukan migrasi DDL di database PostgreSQL.

---

## 4. Tabel Verifikasi Kasus Uji R01–R19

| # | Kasus Uji | Ekspektasi | Hasil |
|---|---|---|:---:|
| **R01** | Berkas 65 byte corrupt stream (`b"%PDF-1.4\n1 0 obj\n<<>>\nstream\nabc"`) | `FileValidationError` `pdf_rusak` ("PDF rusak atau tidak bisa dibuka") | **PASSED** |
| **R02** | PDF valid tanpa halaman | `FileValidationError` `pdf_rusak` ("PDF tidak memiliki halaman") | **PASSED** |
| **R03** | PDF dengan user password terenkripsi AES | `FileValidationError` `pdf_terenkripsi` | **PASSED** |
| **R04** | PDF dengan owner password saja (user password kosong) | Lolos validasi (diizinkan untuk uji keterbacaan) | **PASSED** |
| **R05** | PDF valid 1 halaman | Lolos validasi | **PASSED** |
| **R06** | Unggah batch 5 berkas (4 valid + 1 rusak) via `POST /api/v1/ingest/upload-pdf` | 4 berhasil, 1 failed; antrean kegagalan memuat 1 entri `pdf_rusak`; job tetap berlanjut | **PASSED** |
| **R07** | Unggah PDF dengan user password | Gagal, antrean kegagalan memuat entri `pdf_terenkripsi` | **PASSED** |
| **R08** | `failure_service` fallback dengan PDF valid | `is_valid_pdf=True`, argumen `max_upload_bytes` berhasil dipasok tanpa galat | **PASSED** |
| **R09** | PATCH ekstraksi, `full_text=""`, metode `teks_langsung` | Status `gagal`, `IngestFailure` `teks_kosong`, metadata tersimpan, tidak ke `kb/` | **PASSED** |
| **R10** | PATCH ekstraksi, `full_text=""`, metode `ocr` | Status `gagal`, `IngestFailure` `teks_kosong_ocr` | **PASSED** |
| **R11** | PATCH ekstraksi teks kosong 2 kali (`force=true`) | Hanya 1 kegagalan terbuka (idempoten) | **PASSED** |
| **R12** | `effective_date` = besok, tanpa relasi masuk | Status `belum_berlaku`, `status_source="tanggal_berlaku"` | **PASSED** |
| **R13** | `effective_date` = kemarin | Status `berlaku`, `status_source="tanggal_berlaku"` | **PASSED** |
| **R14** | `effective_date` = besok + relasi masuk mencabut penuh | Status `dicabut` (relasi hukum menang atas tanggal berlaku) | **PASSED** |
| **R15** | `status_source="manual"` + `effective_date` = besok | Status manual tidak ditimpa/tidak berubah | **PASSED** |
| **R16** | Dokumen `belum_berlaku`, tanggal tiba (geser ke kemarin), lalu `POST /internal/documents/status/recompute` | Berubah menjadi `berlaku`; respons `{"berubah": >= 1}`; tanpa/salah kunci 401 | **PASSED** |
| **R17** | Judul placeholder `"untitled"` pada dokumen baru | Judul diabaikan (tetap kosong), status `perlu_koreksi` | **PASSED** |
| **R18** | `GET /audit-logs/` dengan auth nonaktif (`AUTH_ENABLED=false`) | `ip_address: null` di semua entri respons; IP asli di DB tetap utuh | **PASSED** |
| **R19** | `GET /dashboard/summary` | Memuat kunci `kb.by_status_keberlakuan.belum_berlaku` (nilai >= 0) | **PASSED** |

---

## 5. Daftar Tes Lama yang Fixture-nya Diganti

1. **`tests/test_step12_ingest_support.py` (`test_g04`, `test_g05`, `test_g07`):**
   - *Sebelum:* Menggunakan string byte `%PDF-1.4 ...` tiruan tanpa trailer, xref, dan struktur halaman PDF yang valid.
   - *Sesudah:* Menggunakan helper `make_pdf()` yang menghasilkan struktur PDF 1.4 lengkap dan valid dengan halaman sebenarnya.
2. **`tests/test_step18_versioning.py` (`_seed_test_doc`):**
   - *Sebelum:* Tidak menyertakan `full_text` pada objek `Document`.
   - *Sesudah:* Menambahkan `full_text=f"Teks lengkap peraturan {title}."` agar dokumen berstatus valid secara konten saat diekstraksi ulang.
3. **`tests/test_step19_berlaku_lampiran.py` (`_seed_test_doc` & `test_t02`):**
   - *Sebelum:* Fixture tidak memiliki `full_text`; `test_t02` mengasumsikan tanggal di masa depan mempertahankan status `tidak_diketahui`.
   - *Sesudah:* Menambahkan `full_text` pada fixture `_seed_test_doc`; `test_t02` diperbarui untuk menguji ekspektasi Langkah 26 bahwa tanggal masa depan otomatis berstatus `belum_berlaku`.
4. **`tests/test_naming_step9.py` (`test_n12`):**
   - *Sebelum:* Payload ekstraksi tidak menyertakan `full_text`.
   - *Sesudah:* Menambahkan `full_text` pada payload ekstraksi agar mencerminkan ekstraksi riil yang berhasil.

---

## 6. Hasil Verifikasi Pytest & Ruff

### Ruff Linting
```text
All checks passed!
```

### Pytest Berkas Baru (`tests/test_step26_qa_ingest.py`)
```text
============================= test session starts =============================
platform win32 -- Python 3.13.7, pytest-9.1.1, pluggy-1.6.0 -- C:\Hero\hero-backend\venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Hero\hero-backend
plugins: anyio-4.15.1
collecting ... collected 19 items

tests/test_step26_qa_ingest.py::test_r01_corrupt_stream_65_bytes PASSED  [  5%]
tests/test_step26_qa_ingest.py::test_r02_valid_pdf_no_pages PASSED       [ 10%]
tests/test_step26_qa_ingest.py::test_r03_user_password_encrypted_pdf PASSED [ 15%]
tests/test_step26_qa_ingest.py::test_r04_owner_password_only_passes_validation PASSED [ 21%]
tests/test_step26_qa_ingest.py::test_r05_valid_one_page_pdf PASSED       [ 26%]
tests/test_step26_qa_ingest.py::test_r06_upload_batch_5_files_4_valid_1_corrupt PASSED [ 31%]
tests/test_step26_qa_ingest.py::test_r07_upload_user_password_encrypted PASSED [ 36%]
tests/test_step26_qa_ingest.py::test_r08_failure_service_fallback_with_valid_pdf PASSED [ 42%]
tests/test_step26_qa_ingest.py::test_r09_patch_extraction_empty_text_direct PASSED [ 47%]
tests/test_step26_qa_ingest.py::test_r10_patch_extraction_empty_text_ocr PASSED [ 52%]
tests/test_step26_qa_ingest.py::test_r11_patch_extraction_empty_text_twice_force PASSED [ 57%]
tests/test_step26_qa_ingest.py::test_r12_effective_date_tomorrow_without_relation PASSED [ 63%]
tests/test_step26_qa_ingest.py::test_r13_effective_date_yesterday PASSED [ 68%]
tests/test_step26_qa_ingest.py::test_r14_effective_date_tomorrow_with_repeal_relation PASSED [ 73%]
tests/test_step26_qa_ingest.py::test_r15_status_source_manual_not_overwritten PASSED [ 78%]
tests/test_step26_qa_ingest.py::test_r16_recompute_endpoint PASSED       [ 84%]
tests/test_step26_qa_ingest.py::test_r17_placeholder_title_ignored PASSED [ 89%]
tests/test_step26_qa_ingest.py::test_r18_audit_logs_ip_mask_when_auth_disabled PASSED [ 94%]
tests/test_step26_qa_ingest.py::test_r19_dashboard_summary_has_belum_berlaku PASSED [100%]

======================= 19 passed, 2 warnings in 15.23s =======================
```

### Pytest Seluruh Suite (`pytest -q`)
```text
484 passed, 1 skipped, 172 warnings in 747.07s (0:12:27)
```

---

## 7. Hasil Uji Live (Terminal Mentah)

Catatan: Endpoint `/upload-pdf` pada `app/routers/ingest.py` mewajibkan form parameter `access_classification` (kebijakan NDA/keamanan). Sesuai petunjuk pada Bagian 8, ditambahkan `-F "access_classification=publik"`.

### Health Check
```text
{"status":"ok","database":"ok","version":"0.10.0","app_env":"development","alembic_revision":"a3b4c5d6e7f8","alembic_head":"a3b4c5d6e7f8","migrations_up_to_date":true,"storage_writable":true,"crawler_backend":"simple_http","crawler_loaded":true,"auth_enabled":false,"protect_non_public":true}
```

### POST `/api/v1/ingest/upload-pdf` (uji_rusak.pdf & uji_terkunci.pdf)
```text
{"message":"Proses unggah selesai: 0 berhasil, 0 duplikat, 2 gagal dari total 2 file.","job_id":33,"job_status":"gagal","total_files":2,"success_count":0,"duplicate_count":0,"failed_count":2,"details":[{"filename":"uji_rusak.pdf","status":"failed","document_id":null,"duplicate_of_document_id":null,"failure_id":11,"title":null,"regulation_number":null,"file_size_bytes":null,"file_hash":null,"message":null,"error":"PDF rusak atau tidak bisa dibuka: Stream has ended unexpectedly","reason_code":"pdf_rusak","placement":null},{"filename":"uji_terkunci.pdf","status":"failed","document_id":null,"duplicate_of_document_id":null,"failure_id":12,"title":null,"regulation_number":null,"file_size_bytes":null,"file_hash":null,"message":null,"error":"PDF terenkripsi (butuh kata sandi untuk dibuka).","reason_code":"pdf_terenkripsi","placement":null}]}
```

### GET `/api/v1/ingest/failures?limit=2`
```text
{"total":3,"items":[{"id":12,"job_id":33,"original_filename":"uji_terkunci.pdf","source_url":null,"failure_type":"format_tidak_didukung","reason_code":"pdf_terenkripsi","message":"PDF terenkripsi (butuh kata sandi untuk dibuka).","is_retryable":false,"quarantine_path":null,"file_hash":"c1966b1303cd9cf16c76feb9bbc25a69f7bc7a42e7b560c0694b5e0ac402a156","file_size_bytes":828,"duplicate_of_document_id":null,"duplicate_of_document":null,"ingest_options":{"category_id":null,"document_role":"corpus_eksisting","access_classification":"publik"},"follow_up_status":"belum_ditangani","attempt_count":0,"last_retry_at":null,"last_retry_job_id":null,"resolved_document_id":null,"handled_by_user_id":null,"handling_note":null,"created_at":"2026-10-30T04:33:55.291470Z","updated_at":"2026-10-30T04:33:55.291470Z"},{"id":11,"job_id":33,"original_filename":"uji_rusak.pdf","source_url":null,"failure_type":"format_tidak_didukung","reason_code":"pdf_rusak","message":"PDF rusak atau tidak bisa dibuka: Stream has ended unexpectedly","is_retryable":false,"quarantine_path":null,"file_hash":"e16fa5d9b51928755db85b917f0297babaf22c7a47e97d9212adab56e61ba04e","file_size_bytes":8,"duplicate_of_document_id":null,"duplicate_of_document":null,"ingest_options":{"category_id":null,"document_role":"corpus_eksisting","access_classification":"publik"},"follow_up_status":"belum_ditangani","attempt_count":0,"last_retry_at":null,"last_retry_job_id":null,"resolved_document_id":null,"handled_by_user_id":null,"handling_note":null,"created_at":"2026-10-30T04:33:55.203086Z","updated_at":"2026-10-30T04:33:55.203086Z"}]}
```

### Eksekusi Smoke Test Fase 2
```text
================================================================================
       HERO BACKEND SMOKE TEST FASE 2 (READ-ONLY) - http://localhost:8000
       Revisi Alembic Diharapkan: a3b4c5d6e7f8
       Autentikasi: Tidak ada HERO_SMOKE_TOKEN (mode anonim/dev)
================================================================================
================================================================================
Kode   | Cek                                  | Status   | Keterangan
--------------------------------------------------------------------------------
S01    | GET /health                          | OK       | rev=a3b4c5d6e7f8
S02    | GET /api/v1/auth/me                  | OK       | auth_enabled=False
S03    | GET /api/v1/ml/health                | LEWATI   | ML tidak siap: layanan_analisa_belum_dikonfigurasi
S04    | Pilih dokumen uji                    | LEWATI   | Tidak ada dokumen publik aktif terindeks/perlu_koreksi
S05    | GET /documents/{id}/versi            | LEWATI   | Tidak ada dokumen uji
S06    | GET /ml/analisa/{id} (panggilan 1)   | LEWATI   | Tidak ada dokumen uji
S07    | GET /ml/analisa/{id} (panggilan 2)   | LEWATI   | Tidak ada dokumen uji
S08    | GET /documents/{id}/analisa/banding  | LEWATI   | Tidak ada dokumen uji
S09    | GET /documents/{id}/analisa/riwayat  | LEWATI   | Tidak ada dokumen uji
S10    | GET .../riwayat/{run_id}             | LEWATI   | Tidak ada run_id dari analisa
S11    | Ekspor format=json                   | LEWATI   | Tidak ada dokumen uji
S12    | Ekspor format=csv                    | LEWATI   | Tidak ada dokumen uji
S13    | Ekspor format=docx                   | LEWATI   | Tidak ada dokumen uji
S14    | GET /api/v1/audit-logs               | LEWATI   | Belum ada entri audit RUN_ANALYSIS
S15    | Penjaga non-publik                   | OK       | doc_id=64 ditolak 403 saat auth mati
================================================================================
RINGKASAN: 3 OK, 0 GAGAL, 12 LEWATI
PERINGATAN: cek analisa/riwayat/ekspor (S05–S13) tidak dijalankan karena tidak ada dokumen uji. Pakai --doc-id atau pastikan ada dokumen publik terindeks.
```

---

## 8. Catatan untuk Lapisan Data (Fathir)

1. **Timer Harian Evaluasi Status Keberlakuan:**
   - Disediakan endpoint internal baru: `POST /api/v1/internal/documents/status/recompute`
   - Endpoint ini mengevaluasi seluruh dokumen yang memiliki `effective_date IS NOT NULL` dan `status_source IN ('tanggal_berlaku', None)` untuk beralih dari `belum_berlaku` menjadi `berlaku` saat tanggalnya telah tiba.
   - Harap jadwalkan cron/timer harian (misal setiap pukul 00:05 WIB) dengan request:
     ```bash
     curl -s -X POST "http://localhost:8000/api/v1/internal/documents/status/recompute" \
       -H "X-Internal-API-Key: <kunci>"
     ```
   - Respons sukses 200 OK:
     ```json
     {
       "diperiksa": 120,
       "berubah": 2
     }
     ```
2. **Penanganan Ekstraksi Teks Kosong:**
   - Pastikan worker ekstraksi selalu menyertakan `full_text` yang valid. Bila hasil ekstraksi teks kosong atau hanya spasi, backend kini otomatis mencatatnya sebagai kegagalan terbuka (`teks_kosong` atau `teks_kosong_ocr`) dan dokumen tidak akan dimajukan ke `kb/`. Metadata (judul dan nomor) tetap disimpan untuk memudahkan perbaikan.

---

## 9. Catatan untuk Frontend (Ikhwan)

1. **Status Keberlakuan Baru (`belum_berlaku`):**
   - Nilai enum: `belum_berlaku`
   - Label tampilan UI Indonesia: **"Belum berlaku"**
   - Muncul pada filter status pencarian regulasi, badge status dokumen, riwayat versi, dan dashboard eksekutif (`data.kb.by_status_keberlakuan.belum_berlaku`).
2. **Alasan Kegagalan Baru di Riwayat / Antrean Gagal:**
   - `pdf_rusak`: Berkas PDF corrupt, stream terputus, atau tidak memiliki halaman ("PDF rusak atau tidak bisa dibuka: ...").
   - `pdf_terenkripsi`: Berkas dilindungi kata sandi pengguna / user password ("PDF terenkripsi (butuh kata sandi untuk dibuka).").
   - `teks_kosong`: Ekstraksi teks reguler menghasilkan teks kosong ("Ekstraksi tidak menghasilkan teks — periksa manual atau proses ulang dengan OCR.").
   - `teks_kosong_ocr`: Ekstraksi OCR tidak menghasilkan teks ("OCR tidak menghasilkan teks — periksa manual (kemungkinan hasil pindai buram).").
3. **Penyembunyian Alamat IP Log Audit Saat Mode Auth Nonaktif:**
   - Pada halaman Riwayat Audit Aktivitas (`GET /api/v1/audit-logs/`), saat login belum diaktifkan di server (`AUTH_ENABLED=false`), kolom `ip_address` pada respons akan bernilai `null`. Pastikan UI menampilkan tanda strip `"-"` atau teks `"Tidak ditampilkan"` secara rapi.

---

## 10. Status Git & Diff

### `git diff main --stat`
```text
 app/models/enums.py                   |   1 +
 app/routers/audit.py                  |   3 +-
 app/routers/internal.py               | 258 +++++++++++++++++++++++++---------
 app/services/audit_service.py         |   1 +
 app/services/failure_service.py       |  16 ++-
 app/services/file_validation.py       |  32 +++++
 app/services/version_service.py       |  28 ++--
 docs/api/KONTRAK-API-FASE1.md         |  51 ++++++-
 docs/api/openapi-fase1.json           |  51 ++++++-
 requirements.txt                      |   4 +-
 scripts/build_api_contract.py         |   1 +
 tests/test_naming_step9.py            |   4 +-
 tests/test_step12_ingest_support.py   |   9 +-
 tests/test_step18_versioning.py       |   2 +
 tests/test_step19_berlaku_lampiran.py |   9 +-
 15 files changed, 372 insertions(+), 97 deletions(-)
```

### `git log --oneline -3`
```text
501c1a8 feat(backend): Langkah 25 - tandai cache analisa usang setelah mesin ML diperbarui
7e42d9c fix(step25): validasi panjang & kind di invalidate cache, bulk update
ce5e4c1 feat: tandai cache analisa usang setelah mesin ML diperbarui
```

### `git status --short`
```text
 M app/models/enums.py
 M app/routers/audit.py
 M app/routers/internal.py
 M app/services/audit_service.py
 M app/services/failure_service.py
 M app/services/file_validation.py
 M app/services/version_service.py
 M docs/api/KONTRAK-API-FASE1.md
 M docs/api/openapi-fase1.json
?? docs/reports/step26-report.md
 M requirements.txt
 M scripts/build_api_contract.py
 M tests/test_naming_step9.py
 M tests/test_step12_ingest_support.py
 M tests/test_step18_versioning.py
 M tests/test_step19_berlaku_lampiran.py
?? tests/test_step26_qa_ingest.py
```
