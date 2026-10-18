# LAPORAN LANGKAH 21 — RIWAYAT EKSEKUSI ANALISA & AUDIT ANALISA PER MODE (US-10 #56, US-08 #34)

**Tanggal:** 18 Oktober 2026  
**Branch:** `feat/step21-riwayat-analisa`  
**Basis:** `main` (`640eb6b`)

---

## 1. Ringkasan Perubahan

Langkah 21 mengimplementasikan pencatatan riwayat eksekusi analisa dan harmonisasi regulasi (*append-only*) untuk memenuhi kriteria penerimaan **US-10 #56** (*"Sebagai Analis, saya ingin setiap eksekusi analisa tersimpan riwayatnya, agar hasil dapat diulang dan ditelusuri"*) serta menutup celah audit log pada **US-08 #34**:

1. **Model & Migrasi Basis Data (`analysis_runs`):**
   - Migrasi Alembic `e1f2a3b4c5d6_step21_analysis_runs.py` membuat tabel *append-only* `analysis_runs` (baris tidak pernah di-update atau dihapus oleh aplikasi).
   - Menggunakan kembali enum `JenisAnalisa` (`analisa`, `harmonisasi`) dan `ModeAnalisa` (`deterministik`, `ai`) tanpa membuat tipe enum baru di PostgreSQL (`create_type=False`).
   - Kolom-kolom:
     - `id` (PK), `document_id` (FK `documents.id` ON DELETE CASCADE, index), `kind` (Enum `JenisAnalisa`).
     - `mode_diminta` (Enum `ModeAnalisa`), `mode_dipakai` (Enum `ModeAnalisa`, nullable).
     - `sumber` (`String(20)`: `ml`, `cache`, `cache_basi`, `gagal`), `segar` (`Boolean`).
     - `params` (`JSONB`: input analisa/harmonisasi), `params_hash` (`String(64)`).
     - `source_fingerprint` (`String(200)`: sidik jari dokumen saat eksekusi).
     - `ml_version` (`String(100)`: field `versi` dari jawaban ML / versi aturan).
     - `result_hash` (`String(64)`, index: SHA-256 canonical JSON jawaban mentah).
     - `result` (`JSONB`, nullable: diisi hanya bila `sumber = "ml"`; hemat ruang bila `cache`/`cache_basi`).
     - `ringkasan_output` (`JSONB`, nullable: `jumlah_poin`, `kata_ringkasan`, `waktu_ms`, atau `jumlah_temuan`).
     - `http_status` (`Integer`), `error_code` (`String(100)`, nullable), `duration_ms` (`Integer`, nullable).
     - `created_at` (`TIMESTAMPTZ`, index), `created_by` (`Integer` FK `users.id` ON DELETE SET NULL, nullable).
   - Composite Index: `(document_id, kind, created_at DESC)`.
   - Mendukung `downgrade` (tabel di-drop, enum tetap dipertahankan).

2. **Layanan Riwayat Eksekusi (`app/services/analysis_run_service.py`):**
   - `record_run`: Mencatat eksekusi secara terisolasi dengan transaksi aman (`try/except/rollback`). Kegagalan pencatatan riwayat tidak menggagalkan pengembalian hasil analisa ke klien.
   - `extract_ringkasan_output`: Ekstraksi metrik/ringkasan defensif menggunakan `.get()` tanpa potensi KeyError/AttributeError.
   - `compute_result_hash`: Menghitung SHA-256 canonical JSON dari data mentah ML sebelum penyaringan hak akses.
   - `get_analysis_runs_list`: Mengembalikan daftar riwayat paginasi untuk dokumen tertentu, diurutkan terbaru dahulu, tanpa menyertakan payload `hasil` penuh.
   - `get_analysis_run_detail`: Mengembalikan detail run beserta output mentah lengkap `hasil` (bila `sumber == "cache"`, diresolusi dari baris `sumber == "ml"` pertama dengan `result_hash` yang sama). Hasil selalu disaring melalui `saring_rujukan` secara dinamis sesuai hak akses dokumen terkini. Menyertakan petunjuk `cara_ulang`.

3. **Pencatatan Gerbang ML (`app/routers/ml_gateway.py`):**
   - `GET /ml/analisa/{id}` dan `POST /ml/harmonisasi/{id}` mencatat riwayat eksekusi untuk setiap permintaan yang lolos pemeriksaan akses (termasuk pada jalur gagal 503/504).
   - Objek respons `cache` kini menyertakan `run_id` (misal `{"hit": true, "dibuat": "...", "basi": false, "mode_tersimpan": "deterministik", "run_id": 123}`). Jika pencatatan gagal, `run_id = null`.

4. **Jejak Audit Log (`app/services/audit_service.py` & `app/routers/audit.py`):**
   - Menambahkan konstanta `RUN_ANALYSIS = "RUN_ANALYSIS"`.
   - `GET /ml/analisa` mencatat audit `RUN_ANALYSIS` dengan detail `{"mode_diminta", "mode_dipakai", "sumber", "http_status", "run_id"}`.
   - `POST /ml/harmonisasi` memperluas audit `RUN_HARMONIZATION` dengan menyertakan `mode_dipakai`, `sumber`, `http_status`, dan `run_id` di samping field-field audit yang sudah ada (`cache_hit`, `jumlah_korpus`, dll.).
   - `GET /api/v1/audit-logs/` kini mendukung filter query opsional `mode: Literal["deterministik", "ai"]` yang mencocokkan `detail->>'mode_dipakai'`.

5. **Endpoint Riwayat Dokumen (`app/routers/documents.py`):**
   - `GET /api/v1/documents/{document_id}/analisa/riwayat`: Daftar riwayat eksekusi analisa dokumen (filter `kind`, `mode`, `skip`, `limit`).
   - `GET /api/v1/documents/{document_id}/analisa/riwayat/{run_id}`: Detail satu riwayat eksekusi, deduplikasi via `result_hash`, penyaringan rujukan dinamis, dan petunjuk `cara_ulang`.
   - Proteksi akses konsisten: 404 jika dokumen tidak ada / nonaktif; 403 jika non-publik dalam mode lindung tanpa login.

---

## 2. Tabel Kasus Uji H01–H19 (`tests/test_step21_riwayat_analisa.py`)

| # | Kasus Uji | Deskripsi Skenario | Ekspektasi | Status |
|---|---|---|---|:---:|
| **H01** | Analisa Cache Miss | `GET /ml/analisa/{id}` sekali (miss) | 1 baris `analysis_runs`, `sumber=ml`, `result` terisi, `ml_version` = versi mock, `params={"mode":"deterministik"}`, `result_hash` terisi | **LULUS** |
| **H02** | Analisa Cache Hit | Panggil lagi endpoint yang sama (cache hit) | Baris ke-2 `sumber=cache`, `result=NULL`, `result_hash` sama dengan H01; `analysis_results` tetap 1 baris | **LULUS** |
| **H03** | Analisa Paksa Segar | Panggil lagi dengan parameter `segar=true` | Baris ke-3 `sumber=ml`, `segar=true` | **LULUS** |
| **H04** | Fallback Mode AI | Minta `mode=ai`, ML menjawab `mode_dipakai: "deterministik"` | `mode_diminta=ai`, `mode_dipakai=deterministik` tercatat di baris run | **LULUS** |
| **H05** | ML Offline dengan Cache | Hasil tersimpan ada, ML melempar `ConnectError` | Fallback cache basi dikembalikan HTTP 200, tercatat `sumber=cache_basi`, `http_status=200` | **LULUS** |
| **H06** | ML Offline tanpa Cache | Belum ada hasil tersimpan, ML melempar `ConnectError` | Klien menerima 503; tercatat baris `sumber=gagal`, `http_status=503`, `error_code=layanan_analisa_tidak_tersedia` | **LULUS** |
| **H07** | Akses Ditolak Awal | Dokumen nonaktif / non-publik (mode lindung) / tidak ada | Permintaan ditolak (404/403) sebelum analisa; tidak ada baris riwayat dan tidak ada audit `RUN_ANALYSIS` | **LULUS** |
| **H08** | Harmonisasi Korpus Disaring | Harmonisasi dengan dokumen pembanding aktif & nonaktif | Tercatat `kind=harmonisasi`, `params.pembanding` hanya memuat dokumen aktif setelah disaring | **LULUS** |
| **H09** | Audit `RUN_ANALYSIS` | Verifikasi entri audit setelah eksekusi analisa H01 | Ada 1 entri audit `RUN_ANALYSIS` dengan `detail.mode_dipakai`, `detail.sumber`, dan `detail.run_id` sesuai baris H01 | **LULUS** |
| **H10** | Audit `RUN_HARMONIZATION` | Verifikasi detail audit harmonisasi yang diperluas | `detail` memuat `cache_hit` (lama) DAN `mode_dipakai`, `sumber`, `run_id` (baru) | **LULUS** |
| **H11** | Filter Audit Berdasarkan Mode | `GET /audit-logs/?mode=ai` | Mengembalikan hanya entri audit dengan `detail.mode_dipakai == "ai"` | **LULUS** |
| **H12** | Daftar Riwayat Dokumen | `GET /documents/{id}/analisa/riwayat` setelah H01–H03 | `total=3`, urut terbaru dahulu, ringkasan output ada, tanpa memuat field `hasil` penuh | **LULUS** |
| **H13** | Filter Riwayat Dokumen | Filter riwayat dengan `kind=harmonisasi` dan `mode=ai` | Hanya baris yang cocok dengan filter yang dikembalikan | **LULUS** |
| **H14** | Resolusi Hasil Cache | `GET .../riwayat/{run_id}` untuk baris `cache` (H02) | `hasil` berhasil diresolusi dari baris `ml` H01 via `result_hash`, `cara_ulang` terbentuk benar | **LULUS** |
| **H15** | Saring Dinamis Dokumen Riwayat | Dokumen rujukan dinonaktifkan setelah run disimpan | Dokumen rujukan tersebut otomatis tersaring dari `hasil`, `disaring_backend >= 1` | **LULUS** |
| **H16** | Validasi Kepemilikan Run | Akses `run_id` milik dokumen lain melalui endpoint dokumen A | Mengembalikan HTTP 404 Not Found | **LULUS** |
| **H17** | Proteksi Riwayat Non-Publik | Akses `/analisa/riwayat` untuk dokumen non-publik pada mode lindung | Mengembalikan HTTP 403 Forbidden | **LULUS** |
| **H18** | Keamanan Transaksi Fail-Safe | `record_run` dipaksa melempar runtime exception (monkeypatch) | `GET /ml/analisa` tetap sukses 200 mengembalikan hasil analisa, dan `cache.run_id = null` | **LULUS** |
| **H19** | Kesesuaian ID Respons Analisa | Panggilan normal analisa | `cache.run_id` pada respons JSON persis sama dengan id baris yang baru terbentuk di DB | **LULUS** |

---

## 3. Catatan untuk Frontend

Untuk mempermudah integrasi fitur penelusuran riwayat analisa (US-10) dan tombol pengulangan eksekusi:

1. **Atribut `cache.run_id` pada Respons Analisa & Harmonisasi:**
   Setiap pemanggilan `GET /api/v1/ml/analisa/{id}` dan `POST /api/v1/ml/harmonisasi/{id}` kini mengembalikan `run_id`:
   ```json
   {
     "cache": {
       "hit": true,
       "dibuat": "2026-10-18T02:00:00Z",
       "basi": false,
       "mode_tersimpan": "deterministik",
       "run_id": 123
     },
     "mode_dipakai": "deterministik",
     ...
   }
   ```
   Frontend dapat langsung menggunakan `cache.run_id` untuk menavigasi ke halaman/modal detail riwayat eksekusi spesifik ini. Jika terjadi kendala penyimpanan database riwayat, `cache.run_id` akan bernilai `null`.

2. **Daftar Riwayat Eksekusi Dokumen:**
   Untuk merender tabel riwayat eksekusi pada halaman detail dokumen regulasi:
   ```http
   GET /api/v1/documents/{document_id}/analisa/riwayat?kind=analisa&mode=deterministik&skip=0&limit=20
   ```
   - Item respons memuat metadata eksekusi, status HTTP, durasi eksekusi (`duration_ms`), dan `ringkasan_output` (misal `{"jumlah_poin": 12, "kata_ringkasan": 150}`).
   - Respons ini **sengaja tidak memuat payload hasil lengkap** agar ukuran data tetap ringan dan cepat dimuat.
   - Kolom `fingerprint_sama_dengan_sekarang`: Bernilai `true` jika berkas dokumen belum pernah diubah/diekstrak ulang sejak eksekusi tersebut dijalankan.

3. **Detail Satu Riwayat Eksekusi:**
   Untuk melihat detail lengkap hasil analisa masa lalu:
   ```http
   GET /api/v1/documents/{document_id}/analisa/riwayat/{run_id}
   ```
   - Menyertakan payload `hasil` lengkap yang telah disaring hak akses rujukannya secara dinamis.
   - Hasil tetap dapat dibuka secara transparan meskipun baris riwayat tersebut berasal dari `cache` (sistem backend otomatis meresolusi hasilnya via `result_hash`).

4. **Arti Nilai Kolom `sumber`:**
   - `"ml"`: Hasil dihitung baru secara langsung oleh layanan ML. Output mentah lengkap disimpan di database.
   - `"cache"`: Hasil diambil dari cache database lokal yang masih segar (*fresh hit*).
   - `"cache_basi"`: Layanan ML sedang tidak dapat dihubungi (503/504), sehingga backend menyajikan cache historis sebagai cadangan darurat (*stale fallback*).
   - `"gagal"`: Panggilan ke layanan ML mengalami kegagalan dan tidak terdapat cache cadangan.

5. **Tombol "Ulangi Eksekusi Ini" (`cara_ulang`):**
   Field `cara_ulang` disediakan langsung pada respons detail riwayat untuk memenuhi kriteria penerimaan *"hasil dapat diulang"*:
   - Analisa: `"GET /api/v1/ml/analisa/{id}?mode=<mode_diminta>&segar=true"`
   - Harmonisasi: `"POST /api/v1/ml/harmonisasi/{id}?segar=true"` dengan request body berupa daftar ID pembanding pada `params.pembanding`.
   Frontend dapat memetakan klik tombol *"Ulangi Eksekusi Ini"* untuk mengeksekusi instruksi pada `cara_ulang` tersebut.

---

## 4. Hasil Pengujian Pytest & Ruff

### 4.1 Pytest Berkas Step 21 (`tests/test_step21_riwayat_analisa.py`)
```text
============================= test session starts =============================
platform win32 -- Python 3.13.7, pytest-9.1.1, pluggy-1.6.0 -- C:\Hero\hero-backend\venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Hero\hero-backend
plugins: anyio-4.15.1
collecting ... collected 19 items

tests/test_step21_riwayat_analisa.py::test_h01_analisa_miss_creates_ml_run PASSED [  5%]
tests/test_step21_riwayat_analisa.py::test_h02_analisa_cache_hit_creates_cache_run PASSED [ 10%]
tests/test_step21_riwayat_analisa.py::test_h03_analisa_segar_creates_third_ml_run PASSED [ 15%]
tests/test_step21_riwayat_analisa.py::test_h04_mode_diminta_ai_actual_deterministik PASSED [ 21%]
tests/test_step21_riwayat_analisa.py::test_h05_ml_connect_error_fallback_cache_basi PASSED [ 26%]
tests/test_step21_riwayat_analisa.py::test_h06_ml_connect_error_no_cached_result_fails PASSED [ 31%]
tests/test_step21_riwayat_analisa.py::test_h07_rejected_before_analysis_no_run_or_audit PASSED [ 36%]
tests/test_step21_riwayat_analisa.py::test_h08_harmonisasi_records_run_with_filtered_pembanding PASSED [ 42%]
tests/test_step21_riwayat_analisa.py::test_h09_audit_run_analysis_after_h01 PASSED [ 47%]
tests/test_step21_riwayat_analisa.py::test_h10_audit_run_harmonization_extended_detail PASSED [ 52%]
tests/test_step21_riwayat_analisa.py::test_h11_audit_filter_by_mode PASSED [ 57%]
tests/test_step21_riwayat_analisa.py::test_h12_get_document_analysis_runs_list PASSED [ 63%]
tests/test_step21_riwayat_analisa.py::test_h13_filter_history_by_kind_and_mode PASSED [ 68%]
tests/test_step21_riwayat_analisa.py::test_h14_detail_cache_run_resolves_hasil_from_ml_run PASSED [ 73%]
tests/test_step21_riwayat_analisa.py::test_h15_detail_run_filters_subsequently_deactivated_reference PASSED [ 78%]
tests/test_step21_riwayat_analisa.py::test_h16_run_id_belongs_to_different_document_returns_404 PASSED [ 84%]
tests/test_step21_riwayat_analisa.py::test_h17_history_non_public_protected_mode_returns_403 PASSED [ 89%]
tests/test_step21_riwayat_analisa.py::test_h18_record_run_exception_does_not_break_response PASSED [ 94%]
tests/test_step21_riwayat_analisa.py::test_h19_response_cache_run_id_matches_database PASSED [100%]

======================= 19 passed, 2 warnings in 30.72s =======================
```

### 4.2 Pytest Seluruh Suite (`pytest -q`)
```text
388 passed, 1 skipped, 144 warnings in 566.92s (0:09:26)
```

### 4.3 Ruff Linting Check
```powershell
.\venv\Scripts\ruff.exe check --select E9,F app scripts tests/test_step21_riwayat_analisa.py
```
Output:
```text
All checks passed!
```

---

## 5. Verifikasi Kontrak OpenAPI & Bebas Path Lokal

Perintah verifikasi ketersediaan path di `openapi-fase1.json`:
```powershell
.\venv\Scripts\python.exe -c "import json;p=json.load(open('docs/api/openapi-fase1.json',encoding='utf-8'))['paths'];[print(k, k in p) for k in ['/api/v1/documents/{document_id}/analisa/riwayat','/api/v1/documents/{document_id}/analisa/riwayat/{run_id}']]"
```
Output:
```text
/api/v1/documents/{document_id}/analisa/riwayat True
/api/v1/documents/{document_id}/analisa/riwayat/{run_id} True
```

Pemeriksaan kebocoran path lokal (`Users/` atau `IBUCOMP`):
```powershell
Select-String -Path docs/api/KONTRAK-API-FASE1.md,docs/api/openapi-fase1.json -Pattern 'Users/|IBUCOMP' | Measure-Object | Select-Object Count
```
Output:
```text
Count
-----
    0
```

---

## 6. Uji Live Kontainer Docker Backend

Perintah:
```powershell
docker compose up -d --build backend
Start-Sleep -Seconds 15
curl.exe -s http://localhost:8000/health
curl.exe -s "http://localhost:8000/api/v1/documents/71/analisa/riwayat"
curl.exe -s "http://localhost:8000/api/v1/audit-logs/?action=RUN_ANALYSIS&limit=3"
```
Output:
```json
{"status":"ok","database":"ok","version":"0.10.0","app_env":"development","alembic_revision":"e1f2a3b4c5d6","alembic_head":"e1f2a3b4c5d6","migrations_up_to_date":true,"storage_writable":true,"crawler_backend":"simple_http","crawler_loaded":true,"auth_enabled":false,"protect_non_public":true}
---
{"document_id":71,"total":0,"items":[],"catatan":"Draft / Rekomendasi — riwayat eksekusi analisa untuk penelusuran."}
---
[]
```

---

## 7. Status Git & Diff

### `git diff main --stat`
```text
 app/main.py                   |   1 +
 app/models/__init__.py        |   1 +
 app/models/document.py        |   5 +
 app/routers/audit.py          |   5 +-
 app/routers/documents.py      | 124 +++++++-
 app/routers/ml_gateway.py     | 526 ++++++++++++++++++++++++++++----
 app/services/audit_service.py |   1 +
 docs/api/KONTRAK-API-FASE1.md |  97 ++++++
 docs/api/openapi-fase1.json   | 688 +++++++++++++++++++++++++++++++++++++++++-
 scripts/build_api_contract.py |   3 +
 tests/conftest.py             |   1 +
 11 files changed, 1392 insertions(+), 60 deletions(-)
```

### `git log --oneline -3`
```text
640eb6b chore: Langkah 20b snapshot OpenAPI, env ML_CACHE_ENABLED, lint
d495a52 chore: perbarui snapshot OpenAPI, template env ML_CACHE_ENABLED, dan perapian lint
65e8ca5 feat: Langkah 20 simpan hasil analisa per mode (US-05)
```

### `git status --short`
```text
 M app/main.py
 M app/models/__init__.py
 M app/models/document.py
 M app/routers/audit.py
 M app/routers/documents.py
 M app/routers/ml_gateway.py
 M app/services/audit_service.py
 M docs/api/KONTRAK-API-FASE1.md
 M docs/api/openapi-fase1.json
?? docs/reports/step21-report.md
 M scripts/build_api_contract.py
 M tests/conftest.py
?? alembic/versions/e1f2a3b4c5d6_step21_analysis_runs.py
?? app/models/analysis_run.py
?? app/services/analysis_run_service.py
?? tests/test_step21_riwayat_analisa.py
```
