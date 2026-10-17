# LAPORAN LANGKAH 20 — SIMPAN HASIL ANALISA PER MODE & CACHE GERBANG ML (US-05 #49)

**Tanggal:** 17 Oktober 2026  
**Branch:** `feat/step20-hasil-analisa`  
**Basis:** `main` (`bce305e`)

---

## 1. Ringkasan Perubahan

Langkah 20 mengimplementasikan penyimpanan hasil analisa dan harmonisasi per mode serta mekanisme caching pada gerbang ML (`/api/v1/ml/*`) untuk memenuhi kriteria penerimaan **US-05** (*"Sebagai Analis, saya ingin hasil deterministik dan hasil AI disimpan terpisah, agar dapat membandingkan keduanya"*):

1. **Model & Migrasi Basis Data (`analysis_results`):**
   - Migrasi Alembic `d0e1f2a3b4c5_step20_analysis_results.py` membuat tabel baru `analysis_results`.
   - Kolom: `id`, `document_id` (FK `documents.id` `ON DELETE CASCADE`), `kind` (`analisa`, `harmonisasi`), `mode` (`deterministik`, `ai`), `params_hash` (`varchar(64)`), `source_fingerprint` (`varchar(200)`), `result` (`jsonb` menyimpan jawaban mentah ML), `ml_version` (`varchar(100)`), `duration_ms` (`integer`), `created_at`, dan `created_by` (FK `users.id`).
   - Batasan unik: `uq_analysis_results_doc_kind_mode_params` atas `(document_id, kind, mode, params_hash)`.
   - Didukung fungsi migrasi balik (`downgrade`).

2. **Lapisan Logika Cache (`app/services/analysis_result_service.py`):**
   - Sidik jari dokumen `source_fingerprint` dihitung dari `"{file_hash}:{extracted_at ISO atau '-'}"`.
   - `params_hash` untuk analisa dihitung dari `sha256("analisa")` (mode disimpan di kolom terpisah).
   - `params_hash` untuk harmonisasi dihitung dari `sha256(json.dumps(sorted(forward_body)))` sehingga perubahan korpus pembanding otomatis memperbarui kunci.
   - **Penyimpanan Mentah & Saring Dinamis:** Jawaban mentah ML disimpan sebelum difilter. Penyaringan hak akses rujukan (`saring_rujukan`) selalu dieksekusi secara dinamis saat pembacaan (baik cache hit maupun miss).
   - **Fallback Mode AI:** Jika klien meminta `mode=ai` tetapi ML mengembalikan `mode_dipakai="deterministik"`, hasil disimpan sebagai `deterministik` dan tidak membuat atau menimpa entri `ai`.
   - **Offline Stale Cache:** Jika ML melempar galat koneksi (503/504 / `ConnectError`), backend mencari cache tersimpan mode tersebut (meski sidik jari dokumen telah berubah) dan mengembalikannya dengan HTTP 200 dan tanda `cache.basi: true`.

3. **Gerbang ML (`app/routers/ml_gateway.py`):**
   - Mendukung parameter query `segar=false|true` pada `GET /ml/analisa/{id}` dan `POST /ml/harmonisasi/{id}`.
   - Menambahkan metadata objek `cache` pada respons: `{"hit": bool, "dibuat": str, "basi": bool, "mode_tersimpan": str}`.
   - Audit `RUN_HARMONIZATION` kini mencatat atribut `"cache_hit": true|false`.

4. **Endpoint Perbandingan Berdampingan (`app/routers/documents.py`):**
   - `GET /api/v1/documents/{document_id}/analisa/banding`.
   - Membaca data tersimpan langsung dari database tanpa memanggil layanan ML.
   - Mengembalikan slot `deterministik` dan `ai`. Jika salah satu atau kedua mode belum pernah dianalisa, nilainya `null`.
   - Mengembalikan `basi: true` jika sidik jari dokumen berbeda dengan sidik jari saat hasil disimpan.
   - Mematuhi aturan hak akses yang sama persis dengan `GET /documents/{id}` (404 untuk tidak ditemukan/nonaktif, 403 untuk dokumen non-publik pada mode lindung tanpa login).

5. **Konfigurasi Sistem (`app/config.py`):**
   - Menambahkan `ml_cache_enabled: bool = True`. Bila diatur `False`, gerbang berperilaku transparan (tanpa simpan, tanpa baca cache), namun endpoint perbandingan tetap dapat membaca data historis yang sudah ada.

---

## 2. Tabel Kasus Uji A01–A14 (`tests/test_step20_hasil_analisa.py`)

| # | Kasus Uji | Deskripsi Skenario | Ekspektasi | Status |
|---|---|---|---|:---:|
| **A01** | Analisa Dua Kali | Panggilan `GET /ml/analisa/{id}` dua kali berurutan | ML dipanggil 1 kali; panggilan kedua `cache.hit=true` | **LULUS** |
| **A02** | Parameter Segar | Panggilan kedua dengan parameter `segar=true` | ML dipanggil kembali, `cache.hit=false`, data diperbarui tanpa duplikasi | **LULUS** |
| **A03** | Perubahan Fingerprint | Dokumen mengalami perubahan `extracted_at` | Panggilan berikutnya memanggil ML lagi (cache invalid karena fingerprint beda) | **LULUS** |
| **A04** | Fallback Mode AI | Minta `mode=ai`, ML fallback mengembalikan `mode_dipakai: "deterministik"` | Tersimpan sebagai baris `deterministik`, tidak ada baris `ai` yang terbentuk | **LULUS** |
| **A05** | Simpan Mode AI Sukses | Minta `mode=ai`, ML sukses mengembalikan `mode_dipakai: "ai"` | Tersimpan sebagai `ai`; baris `deterministik` sebelumnya tetap utuh terpisah | **LULUS** |
| **A06** | ML Offline dengan Cache | Hasil tersimpan ada di DB, namun ML melempar `ConnectError` | Mengembalikan 200 dengan data tersimpan dan tanda `cache.basi=true` | **LULUS** |
| **A07** | ML Offline tanpa Cache | Belum ada hasil tersimpan, ML melempar `ConnectError` | Mengembalikan 503 `layanan_analisa_tidak_tersedia` | **LULUS** |
| **A08** | Saring Akses Pasca-Cache | Hasil memuat rujukan dokumen yang kemudian dinonaktifkan | Saat dibaca dari cache, rujukan dinonaktifkan tersaring (`disaring_backend >= 1`) | **LULUS** |
| **A09** | Harmonisasi Cache Hit | Harmonisasi dijalankan dua kali dengan korpus yang sama | ML dipanggil 1 kali; audit log kedua mencatat `cache_hit=true` | **LULUS** |
| **A10** | Harmonisasi Korpus Berubah | Dokumen korpus dinonaktifkan di antara dua panggilan harmonisasi | ML dipanggil kembali karena `params_hash` berbeda | **LULUS** |
| **A11** | Endpoint Perbandingan | `GET /documents/{id}/analisa/banding` setelah deterministik & AI ada | Mengembalikan kedua mode terisi tanpa melakukan panggilan ke ML | **LULUS** |
| **A12** | Dokumen Belum Dianalisa | `/analisa/banding` untuk dokumen yang belum pernah dianalisa | Mengembalikan HTTP 200 dengan mode `deterministik: null` dan `ai: null` | **LULUS** |
| **A13** | Cache Dinonaktifkan | Analisa dua kali saat `ml_cache_enabled=False` | ML dipanggil 2 kali; tidak ada rekaman yang disimpan di database | **LULUS** |
| **A14** | Proteksi Akses Banding | `/analisa/banding` pada dokumen non-publik dalam mode lindung | Mengembalikan HTTP 403 Forbidden | **LULUS** |

---

## 3. Catatan untuk Frontend

Untuk mempermudah integrasi antarmuka perbandingan (US-05) dan fitur analisa:

1. **Objek Metadata `cache` pada Respons Analisa & Harmonisasi:**
   Setiap respons dari `GET /api/v1/ml/analisa/{id}` maupun `POST /api/v1/ml/harmonisasi/{id}` kini menyertakan objek `cache`:
   ```json
   {
     "cache": {
       "hit": true,
       "dibuat": "2026-10-17T10:00:00Z",
       "basi": false,
       "mode_tersimpan": "deterministik"
     },
     "mode_dipakai": "deterministik",
     ...
   }
   ```
   - `hit: true`: Hasil diambil langsung dari cache database lokal (instan, < 20 ms).
   - `hit: false`: Hasil baru saja dihitung oleh layanan ML backend.
   - `dibuat`: Timestamp saat kalkulasi ML pertama kali dijalankan dan disimpan.
   - `basi: true`: Ditampilkan saat dokumen asli telah mengalami perubahan berkas/ekstraksi sejak analisa dibuat, ATAU saat layanan ML sedang mati sehingga backend menggunakan cache lama sebagai fallback darurat. Frontend disarankan menampilkan lencana kuning *"Hasil Kedaluwarsa"* bila `basi === true`.

2. **Parameter `segar=true` untuk Tombol "Analisa Ulang" / "Harmonisasi Ulang":**
   Secara default (`segar=false`), backend akan selalu mengembalikan cache hit jika dokumen tidak berubah. Bila pengguna menekan tombol *"Analisa Ulang"* atau *"Hitung Ulang"*, tambahkan query param `?segar=true`:
   ```http
   GET /api/v1/ml/analisa/71?mode=deterministik&segar=true
   POST /api/v1/ml/harmonisasi/71?segar=true
   ```

3. **Endpoint Perbandingan Berdampingan (Side-by-Side Comparison):**
   Gunakan endpoint baru untuk merender tab komparasi atau layar belah (split-screen):
   ```http
   GET /api/v1/documents/{document_id}/analisa/banding
   ```
   Bentuk respons:
   ```json
   {
     "document_id": 71,
     "deterministik": {
       "dibuat": "2026-10-17T10:00:00Z",
       "basi": false,
       "ml_version": "v1.2.0",
       "hasil": {
         "mode_dipakai": "deterministik",
         "ringkasan": "...",
         "poin_kunci": [...]
       }
     },
     "ai": null,
     "catatan": "Draft / Rekomendasi — hasil AI tidak menggantikan hasil deterministik; bandingkan keduanya."
   }
   ```
   - Jika `deterministik === null`, pengguna belum pernah menjalankan analisa reguler.
   - Jika `ai === null`, pengguna belum pernah menjalankan analisa AI. Frontend dapat menampilkan tombol *"Jalankan Analisa AI"* di kolom kanan.
   - Endpoint ini **ringan dan cepat** karena tidak pernah menyentuh layanan ML.

---

## 4. Hasil Verifikasi Terminal (Salinan Mentah)

### A. Pengujian Spesifik Step 20 (`tests/test_step20_hasil_analisa.py`)
```
============================= test session starts =============================
platform win32 -- Python 3.13.7, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Hero\hero-backend
plugins: anyio-4.15.1
collected 14 items

tests\test_step20_hasil_analisa.py ..............                        [100%]

============================== warnings summary ===============================
...
======================= 14 passed, 2 warnings in 22.10s =======================
```

### B. Pengujian Seluruh Suite (`python -m pytest -q`)
```
........................................................................ [ 19%]
........................................................................ [ 39%]
........................................................................ [ 58%]
........................................................................ [ 78%]
.......................................................................s [ 97%]
..........                                                               [100%]
369 passed, 1 skipped, 113 warnings in 518.98s (0:08:38)
```

### C. Pemeriksaan Linting Ruff
```
PS C:\Hero\hero-backend> .\venv\Scripts\ruff.exe check --select E9,F821,F822,F823 app scripts tests
All checks passed!
```

### D. Uji Live Docker Compose
```powershell
PS C:\Hero\hero-backend> docker compose up -d --build backend
#1 [internal] load local bake definitions
...
 hero-backend-backend  Built
 Container hero_postgres  Running
 Container hero_fastapi  Recreate
 Container hero_fastapi  Recreated
 Container hero_postgres  Waiting
 Container hero_postgres  Healthy
 Container hero_fastapi  Starting
 Container hero_fastapi  Started

PS C:\Hero\hero-backend> Start-Sleep -Seconds 15; curl.exe -s http://localhost:8000/health; Write-Host ""; curl.exe -s http://localhost:8000/api/v1/documents/71/analisa/banding
{"status":"ok","database":"ok","version":"0.10.0","app_env":"development","alembic_revision":"d0e1f2a3b4c5","alembic_head":"d0e1f2a3b4c5","migrations_up_to_date":true,"storage_writable":true,"crawler_backend":"simple_http","crawler_loaded":true,"auth_enabled":false,"protect_non_public":true}
{"document_id":71,"deterministik":null,"ai":null,"catatan":"Draft / Rekomendasi — hasil AI tidak menggantikan hasil deterministik; bandingkan keduanya."}
```

### E. Git Diff Stat
```
PS C:\Hero\hero-backend> git diff main --stat
 app/config.py                 |   3 +-
 app/models/__init__.py        |   3 +
 app/models/document.py        |   5 +
 app/models/enums.py           |  13 +++
 app/routers/documents.py      |  44 ++++++-
 app/routers/ml_gateway.py     | 259 +++++++++++++++++++++++++++++++++++++++---
 docs/api/KONTRAK-API-FASE1.md |  66 ++++++++++-
 tests/conftest.py             |   1 +
 8 files changed, 375 insertions(+), 19 deletions(-)
```

### F. Git Log Terakhir
```
PS C:\Hero\hero-backend> git log --oneline -3
bce305e feat: Langkah 19 tanggal berlaku + lampiran
2829a20 fix(step19): heuristik lampiran dari nama berkas hanya bila diawali LAMPIRAN
07b0e44 feat: tanggal berlaku, status berlaku otomatis, dan penautan lampiran ke induk
```

### G. Git Status Short
```
PS C:\Hero\hero-backend> git status --short
 M app/config.py
 M app/models/__init__.py
 M app/models/document.py
 M app/models/enums.py
 M app/routers/documents.py
 M app/routers/ml_gateway.py
 M docs/api/KONTRAK-API-FASE1.md
 M tests/conftest.py
?? alembic/versions/d0e1f2a3b4c5_step20_analysis_results.py
?? app/models/analysis_result.py
?? app/services/analysis_result_service.py
?? docs/reports/step20-report.md
?? tests/test_step20_hasil_analisa.py
```
