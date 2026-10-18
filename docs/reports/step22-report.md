# LAPORAN LANGKAH 22 — EKSPOR HASIL ANALISA (US-40 #62)

**Tanggal:** 18 Oktober 2026  
**Branch:** `feat/step22-ekspor-analisa`  
**Basis:** `main` (`641d9e0`)

---

## 1. Ringkasan Perubahan

Langkah 22 mengimplementasikan fitur ekspor hasil analisa dokumen regulasi per dokumen ke format DOCX, CSV, dan JSON untuk memenuhi kriteria penerimaan **US-40 #62** (*"Sebagai Analis, saya ingin mengekspor hasil analisa"* memuat summary, Key Takeaways, dan rujukan pasal):

1. **Dependensi Baru (`requirements.txt`):**
   - Menambahkan pustaka `python-docx==1.1.2` ke `requirements.txt` untuk pembentukan berkas DOCX terformat secara native dan in-memory.
   - Pustaka telah diinstal ke virtual environment (`.\venv`) dan image Docker backend.

2. **Layanan Ekspor Analisa (`app/services/analysis_export_service.py`):**
   - Membaca data analisa secara defensif dari penyimpanan lokal (`analysis_results` atau `analysis_runs` bila `run_id` diisi) tanpa pernah memanggil layanan ML.
   - Resolusi data eksekusi: Bila `run_id` mengacu pada baris cache (`sumber = 'cache'`), sistem otomatis meresolusi payload hasil mentah dari eksekusi `sumber = 'ml'` yang memiliki `result_hash` sama.
   - Penyaringan dinamis: Payload hasil selalu dilewatkan ke `saring_rujukan` dengan dokumen terotorisasi aktif saat ini (`allowed_document_ids`).
   - Evaluasi kedaluwarsa (`basi`): Mendeteksi apakah sidik jari dokumen saat ini berbeda dari sidik jari saat hasil analisa dibuat.
   - **Format DOCX:** Memuat label peringatan "DRAFT / REKOMENDASI", judul regulasi, tabel identitas dokumen, tabel informasi eksekusi analisa, ringkasan per kalimat beserta rujukan pasal, subbagian "Narasi AI-Assisted" (bila mode AI), daftar bernomor Key Takeaways (lengkap dengan kategori, teks, rujukan pasal/halaman, indikator `(dipotong)`, dan parafrase AI), dasar hukum, sanksi, catatan kaki, serta tautan relatif PDF asli.
   - **Format CSV:** Ditulis dalam encoding UTF-8 dengan BOM (`\ufeff`) agar terbaca otomatis dengan rapi dan tanpa masalah karakter di Microsoft Excel. Kolom: `bagian,urutan,kategori,pasal_rujukan,halaman,teks,parafrase`.
   - **Format JSON:** Menghasilkan payload terstruktur: `{"label": "Draft / Rekomendasi", "document_id": ..., "mode_dipakai": "...", "run_id": ..., "basi": ..., "dibuat": "...", "diekspor": "...", "hasil": { ... }}`.
   - Penamaan berkas standar: `analisa_{jenis}_{nomor}_{tahun}_{mode}.{ext}` (dibersihkan dari karakter tidak aman) dan dikirim melalui header `Content-Disposition` sesuai standar RFC 5987 (`filename="..."` dan `filename*=UTF-8''...`).

3. **Router Dokumen (`app/routers/documents.py`):**
   - Menambahkan endpoint `GET /api/v1/documents/{document_id}/analisa/ekspor`.
   - Mendukung parameter query: `format` (`docx`, `csv`, `json`), `mode` (`deterministik`, `ai`), dan `run_id` (opsional).
   - Mematuhi aturan proteksi akses: 404 bila dokumen tidak ditemukan atau nonaktif; 403 bila dokumen non-publik pada mode lindung tanpa login.
   - Mengembalikan 404 dengan `code: belum_dianalisa` bila dokumen belum pernah dianalisa pada mode yang diminta (tanpa `run_id`).
   - Mengembalikan 404 dengan `code: hasil_tidak_tersedia` bila `run_id` berstatus gagal atau tidak memiliki output.

4. **Jejak Audit Log (`app/services/audit_service.py`):**
   - Menambahkan konstanta aksi audit baru: `EXPORT_ANALYSIS = "EXPORT_ANALYSIS"`.
   - Setiap panggilan ekspor yang berhasil otomatis mencatat jejak audit `EXPORT_ANALYSIS` dengan detail `{"format", "mode", "run_id", "basi"}` pada target `document:{id}`.

---

## 2. Tabel Kasus Uji X01–X15 (`tests/test_step22_ekspor_analisa.py`)

| # | Kasus Uji | Deskripsi Skenario | Ekspektasi | Status |
|---|---|---|---|:---:|
| **X01** | Ekspor Format DOCX | `format=docx` | 200; content-type docx; dibuka dengan docx memuat label "DRAFT / REKOMENDASI", setiap kalimat ringkasan, setiap teks poin utama, dan setiap "Pasal …" rujukan | **LULUS** |
| **X02** | Ekspor Format CSV | `format=csv` | 200; diawali BOM; baris `label`, 2 baris `ringkasan` dengan `pasal_rujukan` terisi, 3 baris `poin_utama` dengan `pasal_rujukan` dan `halaman` terisi | **LULUS** |
| **X03** | Ekspor Format JSON | `format=json` | 200; memuat `label`, `hasil.poin_utama` panjang 3, `basi=false` | **LULUS** |
| **X04** | Belum Dianalisa | Ekspor dokumen yang belum pernah dianalisa | 404 `belum_dianalisa` | **LULUS** |
| **X05** | Mode AI Belum Ada | Ekspor `mode=ai` tetapi baru ada hasil deterministik | 404 `belum_dianalisa` (tidak diam-diam memakai mode lain) | **LULUS** |
| **X06** | Ekspor Mode AI Lengkap | Hasil AI dengan `ringkasan_ai` + `parafrase` | DOCX memuat ringkasan deterministik DAN subbagian "Narasi AI-Assisted" serta "Parafrase AI:" | **LULUS** |
| **X07** | Resolusi Run Cache | `run_id` dari baris riwayat `sumber=cache` | Hasil berhasil diresolusi lewat `result_hash`; isi sama persis dengan run `ml` | **LULUS** |
| **X08** | Validasi Run ID & Status | `run_id` milik dokumen lain / `sumber=gagal` | Mengembalikan 404 / 404 `hasil_tidak_tersedia` | **LULUS** |
| **X09** | Peringatan Dokumen Basi | `extracted_at` dokumen berubah setelah analisa | DOCX memuat peringatan "Dokumen telah berubah sejak analisa ini dibuat — jalankan analisa ulang."; JSON `basi=true` | **LULUS** |
| **X10** | Saring Dinamis Rujukan | Hasil memuat rujukan ke dokumen yang kemudian dinonaktifkan | Rujukan tersebut dinetralkan/tersaring dari ekspor JSON; `disaring_backend >= 1` | **LULUS** |
| **X11** | Proteksi Mode Lindung | Ekspor dokumen non-publik pada mode lindung tanpa login | 403 Forbidden | **LULUS** |
| **X12** | Header Content-Disposition | Pengecekan nama berkas unduhan | Header memuat `filename*=` dan nama `analisa_POJK_11_2024_deterministik.docx` sesuai identitas dokumen | **LULUS** |
| **X13** | Jejak Audit Log | Panggilan ekspor berhasil | Satu entri audit `EXPORT_ANALYSIS` tercatat dengan `detail.format` dan `detail.mode` | **LULUS** |
| **X14** | Resiliensi Field Kosong | Hasil dengan field hilang (tanpa `identitas`, `dasar_hukum`, `sanksi`) | 200 untuk ketiga format tanpa error; nilai kosong tampil `-` atau bagiannya dilewati dengan aman | **LULUS** |
| **X15** | Tanpa Panggilan ML | Verifikasi isolasi ekspor dari ML layer | Handler `MockTransport` melempar kegagalan bila dipanggil; terbukti tidak pernah dipanggil pada seluruh tes | **LULUS** |

---

## 3. Catatan untuk Frontend

1. **Pemanggilan Endpoint Ekspor:**
   - Tombol "Ekspor" pada halaman analisa atau modal riwayat memanggil endpoint:
     ```http
     GET /api/v1/documents/{document_id}/analisa/ekspor?format=docx&mode=deterministik
     ```
   - Bila ekspor dipicu dari baris tertentu pada tabel riwayat eksekusi (US-10), sertakan parameter `run_id`:
     ```http
     GET /api/v1/documents/{document_id}/analisa/ekspor?format=docx&run_id=45
     ```
     Dengan menyertakan `run_id`, berkas yang diunduh mencerminkan hasil analisa pada eksekusi historis tersebut.

2. **Pengambilan Nama Berkas:**
   - Nama berkas unduhan dikirimkan oleh backend melalui header `Content-Disposition`:
     ```http
     Content-Disposition: attachment; filename="analisa_POJK_11_2024_deterministik.docx"; filename*=UTF-8''analisa_POJK_11_2024_deterministik.docx
     ```
   - Frontend disarankan membaca nama berkas langsung dari header `Content-Disposition` (RFC 5987 `filename*` atau `filename`) saat memicu unduhan di browser.

3. **Penanganan Galat HTTP 404 `belum_dianalisa`:**
   - Bila dokumen belum pernah dianalisa pada mode yang diminta (misal pengguna meminta ekspor mode `ai` padahal dokumen baru dianalisa dengan mode `deterministik`), backend membalas:
     ```json
     {
       "detail": {
         "code": "belum_dianalisa",
         "message": "Dokumen belum pernah dianalisa pada mode ini. Jalankan analisa terlebih dahulu."
       }
     }
     ```
   - Frontend dapat menangani kode galat `belum_dianalisa` ini dengan menampilkan pemberitahuan kepada analis untuk menjalankan analisa terlebih dahulu sebelum mengunduh hasil.

---

## 4. Hasil Pengujian Pytest & Ruff

### 4.1 Pytest Berkas Step 22 (`tests/test_step22_ekspor_analisa.py`)
```text
============================= test session starts =============================
platform win32 -- Python 3.13.7, pytest-9.1.1, pluggy-1.6.0 -- C:\Hero\hero-backend\venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Hero\hero-backend
plugins: anyio-4.15.1
collecting ... collected 15 items

tests/test_step22_ekspor_analisa.py::test_x01_export_docx_structure PASSED [  6%]
tests/test_step22_ekspor_analisa.py::test_x02_export_csv_structure PASSED [ 13%]
tests/test_step22_ekspor_analisa.py::test_x03_export_json_structure PASSED [ 20%]
tests/test_step22_ekspor_analisa.py::test_x04_not_yet_analyzed_returns_404 PASSED [ 26%]
tests/test_step22_ekspor_analisa.py::test_x05_mode_ai_requested_but_only_deterministik_exists PASSED [ 33%]
tests/test_step22_ekspor_analisa.py::test_x06_export_ai_with_ringkasan_ai_and_parafrase PASSED [ 40%]
tests/test_step22_ekspor_analisa.py::test_x07_run_id_from_cache_run_resolves_result_hash PASSED [ 46%]
tests/test_step22_ekspor_analisa.py::test_x08_run_id_different_document_or_failed_returns_404 PASSED [ 53%]
tests/test_step22_ekspor_analisa.py::test_x09_extracted_at_changed_shows_stale_warning PASSED [ 60%]
tests/test_step22_ekspor_analisa.py::test_x10_filtered_deactivated_reference PASSED [ 66%]
tests/test_step22_ekspor_analisa.py::test_x11_non_public_protected_mode_returns_403 PASSED [ 73%]
tests/test_step22_ekspor_analisa.py::test_x12_content_disposition_header PASSED [ 80%]
tests/test_step22_ekspor_analisa.py::test_x13_audit_entry_created PASSED [ 86%]
tests/test_step22_ekspor_analisa.py::test_x14_result_with_missing_fields_renders_gracefully PASSED [ 93%]
tests/test_step22_ekspor_analisa.py::test_x15_ml_never_called PASSED     [100%]

======================= 15 passed, 2 warnings in 28.67s =======================
```

### 4.2 Pytest Seluruh Suite (`pytest -q`)
```text
403 passed, 1 skipped, 144 warnings in 586.65s (0:09:46)
```

### 4.3 Ruff Linting Check
```powershell
.\venv\Scripts\ruff.exe check --select E9,F app scripts tests/test_step22_ekspor_analisa.py
```
Output:
```text
All checks passed!
```

---

## 5. Verifikasi Kontrak OpenAPI & Pengecekan Path Lokal

```powershell
.\venv\Scripts\python.exe -c "import json;p=json.load(open('docs/api/openapi-fase1.json',encoding='utf-8'))['paths'];print('/api/v1/documents/{document_id}/analisa/ekspor' in p)"
Select-String -Path docs/api/KONTRAK-API-FASE1.md,docs/api/openapi-fase1.json -Pattern 'Users/|IBUCOMP' | Measure-Object | Select-Object Count
```
Output mentah:
```text
True

Count
-----
    0
```

---

## 6. Uji Live Kontainer Docker Backend & Log

Perintah:
```powershell
docker compose up -d --build backend
Start-Sleep -Seconds 20
curl.exe -s http://localhost:8000/health
curl.exe -s -i "http://localhost:8000/api/v1/documents/71/analisa/ekspor?format=json"
docker compose logs --tail=30 backend
```
Output mentah:
```json
{"status":"ok","database":"ok","version":"0.10.0","app_env":"development","alembic_revision":"e1f2a3b4c5d6","alembic_head":"e1f2a3b4c5d6","migrations_up_to_date":true,"storage_writable":true,"crawler_backend":"simple_http","crawler_loaded":true,"auth_enabled":false,"protect_non_public":true}
---
HTTP/1.1 404 Not Found
date: Sun, 18 Oct 2026 05:19:06 GMT
server: uvicorn
content-length: 129
content-type: application/json
vary: Origin
x-content-type-options: nosniff
x-frame-options: DENY
referrer-policy: strict-origin-when-cross-origin

{"detail":{"code":"belum_dianalisa","message":"Dokumen belum pernah dianalisa pada mode ini. Jalankan analisa terlebih dahulu."}}
---
hero_fastapi  | ==> Menjalankan migrasi database Alembic...
hero_fastapi  | INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
hero_fastapi  | INFO  [alembic.runtime.migration] Will assume transactional DDL.
hero_fastapi  | ==> Menjalankan server HERO Backend Uvicorn pada port 8000 dengan 1 worker...
hero_fastapi  | INFO:     Started server process [1]
hero_fastapi  | INFO:     Waiting for application startup.
hero_fastapi  | INFO:     Application startup complete.
hero_fastapi  | INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
hero_fastapi  | INFO:     127.0.0.1:46002 - "GET /health HTTP/1.1" 200 OK
hero_fastapi  | INFO:     127.0.0.1:50896 - "GET /health HTTP/1.1" 200 OK
hero_fastapi  | INFO:     127.0.0.1:47428 - "GET /health HTTP/1.1" 200 OK
hero_fastapi  | INFO:     127.0.0.1:55802 - "GET /health HTTP/1.1" 200 OK
hero_fastapi  | INFO:     172.21.0.1:56330 - "GET /health HTTP/1.1" 200 OK
hero_fastapi  | INFO:     172.21.0.1:56346 - "GET /api/v1/documents/71/analisa/ekspor?format=json HTTP/1.1" 404 Not Found
```

---

## 7. Status Git & Diff

### `git diff main --stat`
```text
 app/routers/documents.py      |  88 ++++++++++++++++++++++++++++++++++-
 app/services/audit_service.py |   1 +
 docs/api/KONTRAK-API-FASE1.md |  24 ++++++++++
 docs/api/openapi-fase1.json   | 105 ++++++++++++++++++++++++++++++++++++++++++
 requirements.txt              |   3 +-
 5 files changed, 219 insertions(+), 2 deletions(-)
```

### `git log --oneline -3`
```text
641d9e0 feat: Langkah 21 riwayat eksekusi analisa + audit per mode (US-10, US-08)
664c199 fix(step21): hapus alias rute /api/v1/audit, gunakan /api/v1/audit-logs
1159769 feat: riwayat eksekusi analisa dan audit analisa per mode (US-10, US-08)
```

### `git status --short`
```text
 M app/routers/documents.py
 M app/services/audit_service.py
 M docs/api/KONTRAK-API-FASE1.md
 M docs/api/openapi-fase1.json
?? docs/reports/step22-report.md
 M requirements.txt
?? app/services/analysis_export_service.py
?? tests/test_step22_ekspor_analisa.py
```
