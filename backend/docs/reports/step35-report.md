# Laporan Langkah 35 — Draft Kajian Publik Wajib Persetujuan & Pengaman Judul Ekstraksi

Tanggal: 2 November 2026
Branch: `fix/step35-draft-publik-judul`
Basis: `main` (`f64b53a`)

---

## 1. Ringkasan Eksekutif

Langkah 35 menyelesaikan dua temuan kritis QA Hamdan (1 Nov malam):
1. **Pencegahan Publikasi Draft Kajian Tanpa Persetujuan (FR-SCR-04a)**:
   - Menambahkan kolom `publik_disetujui_oleh`, `publik_disetujui_alasan`, dan `publik_disetujui_pada` pada tabel `documents` via migrasi Alembic `f8a9b0c1d2e3`.
   - Modul terpusat `app/services/klasifikasi_service.py` (`periksa_publikasi_draft`) memvalidasi syarat: peran `draft_kajian` + akses `publik` wajib menyertakan `disetujui_oleh` dan `alasan` (minimal 10 karakter).
   - Menerapkan pengamanan di seluruh jalur pembuatan/perubahan dokumen (`upload-pdf`, `patch_document_metadata`, konfigurasi default `scraping-sources`, dan retry failure).
   - Pengosongan otomatis ketiga kolom persetujuan bila dokumen beralih keluar dari kombinasi `draft_kajian` + `publik`.
   - Menambahkan izin baru `DRAFT_PUBLIKASI` untuk peran `admin_kb` di `app/core/permissions.py`. Bila `AUTH_ENABLED=true`, hanya `admin_kb` yang berhak menyetujui publikasi draft, dan nama penyetuju otomatis disematkan dari user yang login.
   - Skrip audit dan remediasi `scripts/periksa_draft_publik.py` (dry-run dan `--apply`).

2. **Pengaman Judul Hasil Ekstraksi (Pencegahan Judul Menelan Paragraf/Isi Regulasi)**:
   - Skema masukan `ExtractionResultIn.title` diperlonggar ke `max_length=5000` di `app/routers/internal.py` agar pipeline ekstraksi tidak gagal 422 saat mengekstrak judul panjang, menjaga agar teks lengkap, nomor, tanggal, dan relasi tetap tersimpan.
   - Modul terpusat `app/services/judul_service.py` (`periksa_judul`) mengevaluasi judul:
     * Aturan 1: Normalisasi spasi dan strip.
     * Aturan 2: Penanda isi peraturan (`DENGAN RAHMAT TUHAN`, `Menimbang`, `Mengingat`, `MEMUTUSKAN`, `Menetapkan :`, `BAB I`, `Pasal 1`, `bahwa ` setelah karakter ke-15) dipotong sebelum penanda pertama. Bila sisa >= 10 karakter dan lolos aturan panjang/paragraf -> `dipotong`; selain itu -> `ditolak`.
     * Aturan 3: Terlalu panjang (> min(JUDUL_MAKS_KARAKTER, 255)), > JUDUL_MAKS_KATA (45 kata), atau berbentuk paragraf (>= 2 batas kalimat di luar nomor regulasi) -> `ditolak`.
   - Penerapan di `patch_extraction_result`:
     * Status `ok`: judul dipakai normal.
     * Status `dipotong`: judul terpotong disimpan, status dokumen menjadi `perlu_koreksi`, dicatat di respons dan audit `EXTRACTION_RESULT`.
     * Status `ditolak`: judul lama dipertahankan (tidak menimpa dengan teks rusak), status dokumen menjadi `perlu_koreksi`, dicatat di respons dan audit `EXTRACTION_RESULT`.
   - Skrip audit `scripts/periksa_judul.py` (dry-run dan `--apply`).

---

## 2. Daftar Jalur Pembuatan Dokumen yang Diperiksa (§1c)

| Jalur | Lokasi Kode | Penanganan & Validasi |
|---|---|---|
| **Unggah Manual PDF** | `app/routers/ingest.py` (`upload_pdf`) | Menerima Form `persetujuan_publik_oleh` dan `persetujuan_publik_alasan`. Memvalidasi via `periksa_publikasi_draft` sebelum menyimpan berkas atau membuat job (ditolak 422 jika tidak lengkap). Bila lolos, 3 kolom persetujuan disimpan, dan dicatat di audit `UPLOAD_DOCUMENT` serta `PUBLIKASI_DRAFT`. |
| **Koreksi Metadata Dokumen** | `app/routers/documents.py` (`patch_document_metadata`) | Menerima field `persetujuan_publik_oleh` dan `persetujuan_publik_alasan`. Memvalidasi transisi status; ditolak 422 bila draft beralih ke publik tanpa persetujuan. Mengosongkan 3 kolom bila beralih ke non_publik atau peran diubah ke corpus_eksisting. Audit `PUBLIKASI_DRAFT` dicatat saat persetujuan diberikan. |
| **Konfigurasi Sumber Scraping** | `app/routers/scraping_sources.py` (`create_scraping_source`, `patch_scraping_source`) | Menolak dengan HTTP 422 `sumber_draft_publik_tidak_diizinkan` jika pengguna mencoba membuat/mengubah default sumber dengan kombinasi `default_document_role="draft_kajian"` dan `default_access_classification="publik"`. |
| **Retry Ingest Failure** | `app/services/failure_service.py` (`retry_failure`) | Menolak retry dengan HTTP 422 `draft_publik_butuh_persetujuan` jika payload ingest_options lama memuat kombinasi `draft_kajian` + `publik` tanpa persetujuan. |
| **Pencarian Dokumen** | `app/services/search_service.py` | Menambahkan pemetaan field respons `persetujuan_publik` pada payload ringkasan dokumen. |

---

## 3. Tabel Hasil Pengujian D01–D13 dan J01–J10

Pengujian diimplementasikan pada file `tests/test_step35_draft_publik_judul.py`:

| # | Kasus Uji | Ekspektasi | Hasil |
|---|---|---|---|
| **D01** | Unggah `draft_kajian` + `publik` tanpa persetujuan | 422 `draft_publik_butuh_persetujuan`; tidak ada dokumen, berkas, maupun job baru | **LULUS** |
| **D02** | Unggah draft publik, alasan < 10 karakter | 422 `draft_publik_butuh_persetujuan` | **LULUS** |
| **D03** | Unggah draft publik, persetujuan lengkap (auth mati) | 200/201; tiga kolom terisi; audit `UPLOAD_DOCUMENT` memuat `persetujuan_publik`; audit `PUBLIKASI_DRAFT` tercatat | **LULUS** |
| **D04** | Unggah `draft_kajian` + `non_publik` dan `corpus_eksisting` + `publik` tanpa persetujuan | diterima 200 | **LULUS** |
| **D05** | PATCH draft `non_publik` → `publik` tanpa persetujuan | 422; dokumen tidak berubah | **LULUS** |
| **D06** | PATCH dengan persetujuan lengkap | 200; kolom terisi; `persetujuan_publik` ada di respons dan detail | **LULUS** |
| **D07** | PATCH dokumen `corpus_eksisting` + `publik` → `document_role=draft_kajian` tanpa persetujuan | 422 `draft_publik_butuh_persetujuan` | **LULUS** |
| **D08** | PATCH draft yang sudah disetujui → `non_publik` | 200; tiga kolom dikosongkan | **LULUS** |
| **D09** | PATCH judul saja pada draft yang sudah disetujui publik | 200 tanpa persetujuan ulang | **LULUS** |
| **D10** | `AUTH_ENABLED=true`, pengguna `analis` dengan persetujuan | 403 `akses_ditolak` | **LULUS** |
| **D11** | `AUTH_ENABLED=true`, pengguna `admin_kb` | diterima 200; `disetujui_oleh` = username login | **LULUS** |
| **D12** | Buat/ubah sumber dengan default `draft_kajian` + `publik` | 422 `sumber_draft_publik_tidak_diizinkan` | **LULUS** |
| **D13** | `periksa_draft_publik.py` dry-run lalu `--apply` | dry-run tidak mengubah; apply hanya mengubah 2 dokumen jadi `non_publik` + audit | **LULUS** |
| **J01** | `periksa_judul` judul OJK wajar (termasuk No. dan POJK.03) | status `ok` | **LULUS** |
| **J02** | Judul + `Menimbang : a. bahwa …` | status `dipotong`, judul tanpa paragraf | **LULUS** |
| **J03** | Judul hanya berisi paragraf tanpa penanda, 60 kata | status `ditolak` (`terlalu_banyak_kata`) | **LULUS** |
| **J04** | Judul 400 karakter | `ditolak` (dan extraction-result tidak 422) | **LULUS** |
| **J05** | Judul dengan 3 kalimat | status `ditolak` (`berbentuk_paragraf`) | **LULUS** |
| **J06** | extraction-result dengan judul `ditolak` | judul lama dipertahankan; status `perlu_koreksi`; `detail.judul` di audit & respons; teks lengkap tetap tersimpan | **LULUS** |
| **J07** | extraction-result dengan judul `dipotong` | judul potongan dipakai; status `perlu_koreksi` | **LULUS** |
| **J08** | extraction-result untuk dokumen yang sudah dikoreksi manual | perilaku lama (judul diabaikan) | **LULUS** |
| **J09** | PATCH manual judul panjang (≤ panjang kolom) | diterima 200 (aturan §2 tidak berlaku) | **LULUS** |
| **J10** | `periksa_judul.py` dry-run lalu `--apply` | judul tidak berubah; status jadi `perlu_koreksi`; audit tercatat | **LULUS** |

---

## 4. Penyesuaian Tes Lama

Sesuai aturan kompatibilitas Langkah 35, 2 tes lama disesuaikan:
1. `tests/test_step15_placement_failure.py::test_b01_patch_extraction_title_too_long`:
   - *Sebelum*: Mengharapkan HTTP 422 karena batas Pydantic `_DOC_TITLE_MAX_LEN=255`.
   - *Sesudah*: Sesuai §2a dan §2c, skema menerima payload longgar (tidak 422). Judul 298 karakter ditolak oleh `periksa_judul` (`terlalu_panjang`), judul asli dipertahankan, teks ekstraksi tetap tersimpan, dan status dokumen berubah menjadi `perlu_koreksi`.
2. `tests/test_step30_kemiripan_draft.py::test_d14_unggah_ulang_pdf_byte_identik_duplicate`:
   - *Sebelum*: Mengunggah PDF sebagai `draft_kajian` + `publik` tanpa menyertakan persetujuan.
   - *Sesudah*: Menambahkan field form `persetujuan_publik_oleh` dan `persetujuan_publik_alasan` pada payload unggah agar memenuhi syarat kepatuhan Langkah 35.

---

## 5. Hasil Pengujian Pytest

### 5.1 Pytest Berkas Langkah 35 (`tests/test_step35_draft_publik_judul.py`)
```
============================= test session starts =============================
platform win32 -- Python 3.13.7, pytest-9.1.1, pluggy-1.6.0 -- C:\Hero\hero-backend\venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Hero\hero-backend
plugins: anyio-4.15.1
collecting ... collected 23 items

tests/test_step35_draft_publik_judul.py .......................          [100%]

============================== warnings summary ===============================
...
23 passed, 8 warnings in 32.88s
```

### 5.2 Pytest Seluruh Suite
```
============================= test session starts =============================
platform win32 -- Python 3.13.7, pytest-9.1.1, pluggy-1.6.0 -- C:\Hero\hero-backend\venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Hero\hero-backend
plugins: anyio-4.15.1
collecting ... collected 642 items

........................................................................ [ 11%]
.............................................s.......................... [ 22%]
........................................................................ [ 33%]
........................................................................ [ 44%]
........................................................................ [ 56%]
........................................................................ [ 67%]
........................................................................ [ 78%]
........................................................................ [ 89%]
..................................................................       [100%]

================== 641 passed, 1 skipped, 225 warnings in 1185.09s (0:19:45) ==================
```

---

## 6. Pemeriksaan Linting (Ruff)

```powershell
.\venv\Scripts\python.exe -m ruff check --select E9,F app scripts tests/test_step35_draft_publik_judul.py
```
Output:
```
All checks passed!
```

---

## 7. Hasil Uji Live (Docker Compose)

### 7.1 Pemeriksaan Kesehatan Kontainer (`/health`)
```bash
curl.exe -s http://localhost:8000/health
```
Output:
```json
{"status":"ok","database":"ok","version":"0.10.0","app_env":"development","alembic_revision":"f8a9b0c1d2e3","alembic_head":"f8a9b0c1d2e3","migrations_up_to_date":true,"storage_writable":true,"crawler_backend":"simple_http","crawler_loaded":true,"auth_enabled":false,"protect_non_public":true}
```

### 7.2 Eksekusi Skrip `periksa_draft_publik.py`
Dry-run:
```bash
docker compose exec backend python scripts/periksa_draft_publik.py
```
Output:
```
=== Menjalankan Periksa Draft Publik [DRY-RUN (bawaan - tanpa perubahan DB)] ===
Total draft kajian publik tanpa persetujuan ditemukan: 2
---------------------------------------------------------------------------------------------------------
ID     | Judul (maks 60 kar)                                            | Dibuat              | Persetujuan
---------------------------------------------------------------------------------------------------------
56     | b06 draft                                                      | 2026-10-04 18:23:39 | None
62     | Draft Kajian Regulasi AI Nasional                              | 2026-10-04 18:26:21 | None
---------------------------------------------------------------------------------------------------------
Gunakan flag --apply untuk mengubah 2 dokumen di atas menjadi non_publik.
```

Apply:
```bash
docker compose exec backend python scripts/periksa_draft_publik.py --apply
```
Output:
```
=== Menjalankan Periksa Draft Publik [APPLY (mengubah ke non_publik)] ===
Total draft kajian publik tanpa persetujuan ditemukan: 2
---------------------------------------------------------------------------------------------------------
ID     | Judul (maks 60 kar)                                            | Dibuat              | Persetujuan
---------------------------------------------------------------------------------------------------------
56     | b06 draft                                                      | 2026-10-04 18:23:39 | None
62     | Draft Kajian Regulasi AI Nasional                              | 2026-10-04 18:26:21 | None
---------------------------------------------------------------------------------------------------------
Sukses mengupdate 2 dokumen menjadi non_publik.
```

### 7.3 Eksekusi Skrip `periksa_judul.py`
```bash
docker compose exec backend python scripts/periksa_judul.py
```
Output:
```
=== Menjalankan Periksa Judul Ekstraksi [DRY-RUN (bawaan - tanpa perubahan DB)] ===
Total dokumen diperiksa: 84
Hasil: OK=84, Dipotong=0, Ditolak=0
-------------------------------------------------------------------------------------------------------------------
ID     | Status    | Alasan                     | Panjang | Cuplikan Judul (80 kar)
-------------------------------------------------------------------------------------------------------------------
```

### 7.4 Smoke Test Fase 2 (`smoke_fase2.py`)
```bash
.\venv\Scripts\python.exe scripts/smoke_fase2.py --base-url http://localhost:8000
```
Output:
```
====================================================================================
       HERO BACKEND SMOKE TEST FASE 2 - http://localhost:8000
       Revisi Alembic Diharapkan: f8a9b0c1d2e3
       Autentikasi: Tidak ada HERO_SMOKE_TOKEN (mode anonim/dev)
====================================================================================
====================================================================================
Kode   | Cek                                      | Status   | Keterangan
------------------------------------------------------------------------------------
S01    | GET /health                              | OK       | rev=f8a9b0c1d2e3
S02    | GET /api/v1/auth/me                      | OK       | auth_enabled=False
S03    | GET /api/v1/ml/health                    | LEWATI   | ML tidak siap: layanan_analisa_belum_dikonfigurasi
S04    | Pilih dokumen uji                        | LEWATI   | Tidak ada dokumen publik aktif terindeks/perlu_koreksi
S05    | GET /documents/{id}/versi                | LEWATI   | Tidak ada dokumen uji
S06    | GET /ml/analisa/{id} (panggilan 1)       | LEWATI   | Tidak ada dokumen uji
S07    | GET /ml/analisa/{id} (panggilan 2)       | LEWATI   | Tidak ada dokumen uji
S08    | GET /documents/{id}/analisa/banding      | LEWATI   | Tidak ada dokumen uji
S09    | GET /documents/{id}/analisa/riwayat      | LEWATI   | Tidak ada dokumen uji
S10    | GET .../riwayat/{run_id}                 | LEWATI   | Tidak ada run_id dari analisa
S11    | Ekspor format=json                       | LEWATI   | Tidak ada dokumen uji
S12    | Ekspor format=csv                        | LEWATI   | Tidak ada dokumen uji
S13    | Ekspor format=docx                       | LEWATI   | Tidak ada dokumen uji
S14    | GET /api/v1/audit-logs                   | LEWATI   | butuh login / kunci internal (403)
S15    | Penjaga non-publik                       | OK       | doc_id=64 ditolak 403 saat auth mati
S16    | GET /api/v1/dashboard/summary            | OK       | belum_berlaku=0
S17    | GET /api/v1/dashboard/corong             | OK       | sumber=5, di_kb=93, terbaca=0 (0.0%)
S18    | GET /api/v1/dashboard/corong?format=csv  | OK       | BOM=ada, TOTAL=ada, filename*=ada, bytes=1169
S19    | GET /ingest/failures filter kode         | OK       | items=2, filter bekerja
S20    | GET /api/v1/categories/tree              | OK       | nodes=42, kunci Langkah 28 lengkap
S21    | Dokumen di kategori 'Tanpa Tahun'        | OK       | 0 dokumen di 'Tanpa Tahun'
S22    | Harmonisasi per pasal                    | LEWATI   | ML tidak siap
====================================================================================
RINGKASAN: 9 OK, 0 GAGAL, 13 LEWATI
PERINGATAN: cek analisa/riwayat/ekspor (S05–S13) tidak dijalankan karena tidak ada dokumen uji. Pakai --doc-id atau pastikan ada dokumen publik terindeks.
PERINGATAN: 3134 hasil scan belum ditarik ke KB — Pak Faris meminta semua hasil scan masuk KB (Weekly #7).
```

### 7.5 Uji Live Unggah PDF Tanpa & Dengan Persetujuan
1. Tanpa persetujuan:
```
--- TEST 1: TANPA PERSETUJUAN ---
Status Code: 422
Response JSON: {'detail': {'code': 'draft_publik_butuh_persetujuan', 'message': 'Draft kajian hanya boleh publik dengan persetujuan (disetujui_oleh dan alasan wajib diisi).'}}
```
2. Dengan persetujuan:
```
--- TEST 2: DENGAN PERSETUJUAN ---
Status Code: 200
Response JSON: {'message': 'Proses unggah selesai: 1 berhasil, 0 duplikat, 0 gagal dari total 1 file.', 'job_id': 38, 'job_status': 'selesai', 'total_files': 1, 'success_count': 1, 'duplicate_count': 0, 'failed_count': 0, 'details': [{'filename': 'live_test_draft_dengan_persetujuan.pdf', 'status': 'success', 'document_id': 95, ...}]}
```
Verifikasi Database (dokumen ID 95):
```
 id | access_classification | document_role |  publik_disetujui_oleh   |          publik_disetujui_alasan          |    publik_disetujui_pada     
----+-----------------------+---------------+--------------------------+-------------------------------------------+------------------------------
 95 | publik                | draft_kajian  | Direktur Eksekutif Riset | Draft uji live Langkah 35 publikasi resmi | 2026-11-01 20:53:46.15397+00
```
Verifikasi Audit Trail (dokumen ID 95):
```
 id  |     action      | target_resource | detail
-----+-----------------+-----------------+-----------------------------------------------------------------------
 305 | PUBLIKASI_DRAFT | document:95     | {"jalur": "unggah", "alasan": "Draft uji live Langkah 35 publikasi resmi", "document_id": 95, "disetujui_oleh": "Direktur Eksekutif Riset"}
 304 | UPLOAD_DOCUMENT | document:95     | {..., "persetujuan_publik": {"pada": "2026-11-01T20:53:46.153970+00:00", "alasan": "Draft uji live Langkah 35 publikasi resmi", "disetujui_oleh": "Direktur Eksekutif Riset"}}
```

---

## 8. Catatan untuk Tim

### 8.1 Catatan untuk Frontend (Ikhwan)
1. **Formulir Unggah PDF (`POST /api/v1/ingest/upload-pdf`) & Form Koreksi Metadata (`PATCH /api/v1/documents/{id}/metadata`)**:
   - Jika pengguna memilih kombinasi peran `draft_kajian` dan klasifikasi akses `publik`, tampilkan field isian wajib:
     * **Disetujui oleh** (`persetujuan_publik_oleh`): Nama pejabat/kurator yang menyetujui.
     * **Alasan persetujuan** (`persetujuan_publik_alasan`): Keterangan justifikasi (wajib minimal 10 karakter).
   - Tampilkan pesan peringatan di UI: *"Draft kajian bersifat sensitif dan internal secara default. Mempublikasikan draft kajian ke publik memerlukan persetujuan dan pertanggungjawaban resmi."*
   - Tangani galat HTTP 422 dengan membaca `detail.code == 'draft_publik_butuh_persetujuan'` dan tampilkan `detail.message`.
2. **Tampilan Detail Dokumen**:
   - Skema respons dokumen sekarang menyertakan objek `persetujuan_publik`:
     ```json
     "persetujuan_publik": {
       "disetujui_oleh": "Nama Penyetuju",
       "alasan": "Alasan persetujuan...",
       "pada": "2026-11-01T20:53:46.153970+00:00"
     }
     ```
   - Tampilkan badge/kartu persetujuan ini pada panel informasi dokumen jika nilainya tidak null.
3. **Pemberitahuan Koreksi Judul**:
   - Dokumen yang judulnya ditolak atau dipotong oleh pengaman ekstraksi otomatis masuk ke status `perlu_koreksi` dengan penanda pada `low_confidence_fields` (`["title"]`). Kurator dapat meninjau dan memperbaiki judul secara manual di menu koreksi metadata.

### 8.2 Catatan untuk Pipeline / Data ML (Fathir)
1. **Kelonggaran Skema Ekstraksi**:
   - `PATCH /api/v1/internal/documents/{id}/extraction` tidak lagi menolak request dengan HTTP 422 jika judul hasil ekstraksi panjang. Field teks lengkap, nomor peraturan, tanggal terbit, dan hierarki tetap tersimpan.
2. **Pemeriksaan Judul Otomatis**:
   - Judul dievaluasi terhadap pola penanda isi peraturan (`DENGAN RAHMAT TUHAN`, `Menimbang`, `Mengingat`, `MEMUTUSKAN`, `Menetapkan :`, `BAB I`, `Pasal 1`, `bahwa `).
   - Bila judul mengandung penanda isi setelah karakter ke-15, judul akan dipotong otomatis sebelum penanda tersebut (`status: dipotong`).
   - Bila judul berbentuk paragraf (>= 2 kalimat tanpa nomor regulasi), melebihi 45 kata, atau melebihi 255 karakter, judul lama dipertahankan (`status: ditolak`).
   - Hasil pemeriksaan disertakan pada respons endpoint dan dicatat di audit log:
     ```json
     "judul": {
       "status": "dipotong" | "ditolak",
       "alasan": "mengandung_isi_peraturan" | "terlalu_panjang" | "berbentuk_paragraf",
       "panjang_asli": 340,
       "cuplikan_asli": "..."
     }
     ```
   - Status dokumen akan disetel ke `perlu_koreksi` agar ditinjau oleh kurator manusia di web UI.

### 8.3 Catatan Deploy & Operasional VPS
1. **Migrasi Database**:
   - Revisi Alembic terbaru: `f8a9b0c1d2e3`.
   - Jalankan `docker compose exec backend alembic upgrade head`.
2. **Urutan Pemeliharaan Pasca-Deploy**:
   - Jalankan audit draft publik:
     ```bash
     docker compose exec backend python scripts/periksa_draft_publik.py --apply
     ```
   - Jalankan audit anomali judul ekstraksi:
     ```bash
     docker compose exec backend python scripts/periksa_judul.py --apply
     ```
   - Prosedur lengkap tercatat pada bab 5.3 dan bab 14 dokumen `docs/deploy/RUNBOOK-VPS.md`.

---

## 9. Ringkasan Status Git

### 9.1 `git diff main --stat`
```
 .env.example                           |   3 +
 app/config.py                          |   4 +-
 app/core/permissions.py                |  68 ++++++++++++++++++++++
 app/models/document.py                 |  17 ++++++
 app/routers/documents.py               | 101 ++++++++++++++++++++++++++++++++-
 app/routers/ingest.py                  |  25 ++++++++
 app/routers/internal.py                |  63 +++++++++++++++-----
 app/routers/scraping_sources.py        |  36 ++++++++++--
 app/schemas/document.py                |  12 ++++
 app/services/audit_service.py          |   1 +
 app/services/failure_service.py        |  10 ++++
 app/services/ingest_service.py         |  30 +++++++++-
 app/services/search_service.py         |   5 ++
 app/services/storage_service.py        |  17 +++++-
 docs/api/KONTRAK-API-FASE1.md          |  10 +++-
 docs/api/openapi-fase1.json            |  76 ++++++++++++++++++++++++-
 docs/deploy/RUNBOOK-VPS.md             |  58 +++++++++++++++++--
 tests/test_step15_placement_failure.py |  18 ++++--
 tests/test_step30_kemiripan_draft.py   |   2 +
 19 files changed, 517 insertions(+), 39 deletions(-)
```

### 9.2 `git log --oneline -3`
```
f64b53a Merge Langkah 34 + 34b: detail audit, lockout login, kunci endpoint admin
9c8c6db fix(step34): insert aman bersamaan, bcrypt tiruan, kunci smoke hanya dari HERO_INTERNAL_API_KEY
5c07ace fix: detail audit log lengkap, lockout login, kunci endpoint admin saat login mati
```
