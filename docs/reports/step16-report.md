# Laporan Langkah 16 HERO Backend (Gerbang `/api/v1/ml/*` untuk Layar Analisa, Issue #116)

**Tanggal:** 13 Oktober 2026  
**Branch:** `feat/step16-gerbang-ml`  
**Base Branch / Commit:** `fix/step15-penempatan-gagal` (`363ad3b`)  
**Referensi:** Issue #116, API_CONTRACT_ML.md, URD 3.3, URD 3.4, FR-HRM-01..13  

---

## 1. Ringkasan Eksekutif & Latar Belakang

Layanan analisa regulasi dan harmonisasi milik lapisan data (`hero bridge serve`, port 8100) sebelumnya dipasang langsung melalui reverse proxy web server (Caddy) yang melewati backend. Hal tersebut menimbulkan sejumlah masalah arsitektural dan keamanan:
1. **Tidak Ada Pemeriksaan Akses:** Aturan proteksi backend `protect_non_public_when_auth_disabled` (dokumen non-publik dilarang diakses sebelum autentikasi aktif) tidak berlaku di layanan analisa. Endpoint pencarian, analisa, dan harmonisasi berpotensi membocorkan isi dokumen rahasia/non-publik.
2. **Dokumen Nonaktif Ikut Terbaca:** Dokumen yang telah dinonaktifkan secara administratif oleh Admin KB (`is_active = false`, Langkah 14) tetap muncul dalam hasil pencarian, daftar draft, dan korpus harmonisasi.
3. **Kompleksitas Pengembangan Lokal:** Frontend yang mengarah ke backend port 8000 tidak dapat mengakses `/api/v1/ml/*` tanpa konfigurasi proxy tambahan.

### Solusi yang Diimplementasikan:
1. **Bagian A (Perapian Langkah 15 - Commit Sendiri):**
   - Pada `patch_extraction_result` (`app/routers/internal.py`), penggabungan pesan galat penempatan saat worker mengirim laporan galat disesuaikan menjadi format `"<pesan lama> | laporan worker: <pesan worker>"` (dipotong maksimal 1000 karakter).
   - Pengiriman ulang pesan yang identik tidak lagi menduplikasi teks.
   - Kasus uji B03 di `tests/test_step15_placement_failure.py` diperbarui dan diverifikasi memuat alasan asli dan laporan worker.
   - Commit: `45cd17f` `fix(step15): pertahankan alasan penempatan saat worker melapor galat`.

2. **Bagian B (Gerbang `/api/v1/ml/*` - Commit Sendiri):**
   - **Konfigurasi Baru (`app/config.py`):**
     - `ml_service_url: str = ""` (bawaan kosong, merespons 503 `layanan_analisa_belum_dikonfigurasi`).
     - `ml_timeout_seconds: float = 120.0` (toleransi waktu harmonisasi panjang).
     - `ml_default_search_method: str = "lsa"` (metode bawaan ringan di VPS).
   - **Router Baru `app/routers/ml_gateway.py` (Prefix `/api/v1/ml`, Tag `Analisa (ML)`):**
     - Menerapkan whitelist 7 endpoint eksplisit:
       - `GET /health` -> `GET /health`
       - `GET /dokumen` -> `GET /dokumen` (`peran`, `limit`)
       - `GET /analisa/{document_id}` -> `GET /analisa/{id}` (`mode`)
       - `GET /analisa/{document_id}/klausul` -> `GET /analisa/{id}/klausul` (`kebutuhan`, `k`)
       - `POST /harmonisasi/{document_id}` -> `POST /harmonisasi/{id}` (`body` pembatas korpus)
       - `GET /cari` -> `GET /cari` (`q`, `metode`, `k`)
       - `GET /pasal-mirip` -> `GET /pasal-mirip` (`teks`, `k`, `kecuali_dokumen`, `hanya_publik`)
     - Parameter divalidasi ketat di gerbang backend (`q >= 2`, `teks >= 20`, `kebutuhan >= 3`, limit & k rentang numerik, enum valid) sehingga 422 keluar dalam format standar backend.
     - Header kredensial frontend (`Authorization`, cookie) tidak diteruskan ke layanan downstream.
   - **Aturan Akses & Penyaringan Hasil:**
     - Helper `allowed_document_ids(db)` memastikan hanya dokumen `is_active=True`, status `terindeks`/`perlu_koreksi`, dan `publik` (bila proteksi non-publik aktif tanpa autentikasi) yang dapat diakses.
     - Pada `/analisa/{id}` & `/analisa/{id}/klausul`: dokumen nonaktif ditolak 404 `dokumen_nonaktif`, dokumen non-publik ditolak 403 `Dokumen non-publik hanya dapat dibuka setelah login diaktifkan.` sebelum request dikirim ke ML.
     - Pada `/harmonisasi/{id}`: jika body `null`, backend menggantinya dengan daftar eksplisit seluruh dokumen yang diizinkan (minus draft itu sendiri). Hasil response disaring: `kandidat` dan `temuan` dokumen nonaktif dibuang, relasi `rujukan` di luar izin diset `document_id = null`.
     - Respons yang mengalami penyaringan menyertakan field debug `"disaring_backend": <jumlah>`.
     - Jejak audit `RUN_HARMONIZATION` dicatat pada `POST /harmonisasi/{id}` yang berhasil dengan detail `{document_id, jumlah_temuan, korpus_dokumen}`.
   - **Pemetaan Galat Tanpa 500 Mentah:**
     - `ML_SERVICE_URL` kosong -> 503 `layanan_analisa_belum_dikonfigurasi`.
     - `httpx.ConnectError` -> 503 `layanan_analisa_tidak_tersedia`.
     - `httpx.TimeoutException` -> 504 `layanan_analisa_timeout`.
     - Respons non-JSON -> 502 `layanan_analisa_jawaban_tidak_valid`.
     - Galat 4xx/5xx dari layanan diteruskan dengan kode status dan payload yang sama.

---

## 2. Catatan untuk Tim

### Frontend
1. **Satu Asal (API Base URL):** Panggil endpoint `/api/v1/ml/*` melalui `API_BASE_URL` yang sama dengan backend reguler (misal: `http://localhost:8000/api/v1/ml/*` di lokal atau `https://<domain>/api/v1/ml/*` di VPS). Tidak perlu memanggil port 8100 secara langsung.
2. **Penanganan Status 503 & 504:** Tangani kode status 503 dan 504 dengan pesan ramah pengguna: *"Layanan analisa belum siap / sedang memulai ulang"*, bukan layar error (crash / error boundary).
3. **Pencarian Cepat:** Endpoint `/api/v1/ml/cari` otomatis menggunakan metode `lsa` jika parameter `metode` tidak dikirimkan.

### Lapisan Data & Tim Deploy
1. **Konfigurasi Variabel Lingkungan:** Tambahkan variabel berikut pada berkas `.env` dan `.env.prod`:
   ```bash
   ML_SERVICE_URL=http://172.17.0.1:8100
   ML_TIMEOUT_SECONDS=120.0
   ML_DEFAULT_SEARCH_METHOD=lsa
   ```
   *(Pada Docker Desktop pengujian lokal dapat menggunakan `http://host.docker.internal:8100`).*
2. **Penghapusan Blok Bypass di Caddy:** Setelah gerbang backend aktif di VPS, blok `handle /api/v1/ml/*` di reverse proxy Caddy (`deploy/Caddyfile`) sebaiknya dihapus agar seluruh lalu lintas melewati backend demi penegakan hak akses. Layanan ML cukup mendengarkan di IP internal bridge (`172.17.0.1` / `127.0.0.1`). *(Sesuai instruksi aturan main, `deploy/Caddyfile` tidak diubah pada langkah ini).*
3. **Penyaringan Harmonisasi di Lapisan Data:**
   > **Lapisan data:** `POST /harmonisasi` menghitung terhadap seluruh korpus lalu baru menyaring `temuan` dengan `pembanding`. Angka di `ringkasan` dan kalimat `rekomendasi` karena itu masih dihitung dari korpus penuh. Sebaiknya korpus dibatasi **sebelum** `harmonise()` dijalankan, dan `[]` dibedakan dari `null`.

---

## 3. Git Diff Stat Pembangkitan Kontrak API

Berikut output mentah `git diff --stat` setelah penambahan seksi Gerbang Analisa dan eksekusi `python scripts/build_api_contract.py`:

```
 app/config.py                 |   5 +
 app/main.py                   |   2 +
 app/services/audit_service.py |   1 +
 docs/api/KONTRAK-API-FASE1.md |  64 +++++-
 docs/api/openapi-fase1.json   | 475 ++++++++++++++++++++++++++++++++++++++++++
 scripts/build_api_contract.py |  64 +++++-
 6 files changed, 599 insertions(+), 12 deletions(-)
```

---

## 4. Tabel Hasil Pengujian Gerbang ML (M01 – M17)

Pengujian dilakukan menggunakan `httpx.MockTransport` tanpa layanan ML sungguhan.

| # | Kasus Uji | Ekspektasi | Hasil Terminal | Status |
|---|---|---|---|---|
| **M01** | `ml_service_url` kosong, `GET /api/v1/ml/health` | 503 `layanan_analisa_belum_dikonfigurasi` | Status 503, detail code `layanan_analisa_belum_dikonfigurasi` | **PASSED** |
| **M02** | Transport melempar `httpx.ConnectError` | 503 `layanan_analisa_tidak_tersedia` | Status 503, detail code `layanan_analisa_tidak_tersedia` | **PASSED** |
| **M03** | Transport melempar `httpx.ReadTimeout` | 504 `layanan_analisa_timeout` | Status 504, detail code `layanan_analisa_timeout` | **PASSED** |
| **M04** | `GET /analisa/{id}` dokumen publik aktif | 200, body diteruskan, path `/analisa/{id}` benar | Status 200, captured path benar, payload identitas utuh | **PASSED** |
| **M05** | `GET /analisa/{id}` dokumen nonaktif | 404 `dokumen_nonaktif`, handler **tidak** dipanggil | Status 404, pesan `dokumen_nonaktif`, transport 0 call | **PASSED** |
| **M06** | `GET /analisa/{id}` non-publik, mode lindung | 403, handler **tidak** dipanggil | Status 403, detail proteksi login, transport 0 call | **PASSED** |
| **M07** | `POST /harmonisasi/{id}` body `null` (ada nonaktif & non-publik) | Body ke ML = daftar eksplisit dokumen terfilter | Status 200, request body ke downstream hanya ID valid | **PASSED** |
| **M08** | Jawaban harmonisasi memuat kandidat/temuan/rujukan nonaktif | Kandidat/temuan dibuang; `rujukan` `document_id=null` & kunci sensitif dihapus; `disaring_backend` = 3 (1 kandidat + 1 temuan + 1 rujukan); audit ringkas | Status 200, kandidat/temuan dibuang, rujukan dinetralkan, disaring=3, audit format ringkas | **PASSED** |
| **M09** | `GET /cari?q=modal` tanpa `metode` | Layanan menerima `metode=lsa`; item nonaktif dibuang, `total` disesuaikan | Parameter `metode=lsa` diteruskan, item disaring, total=1 | **PASSED** |
| **M10** | `GET /pasal-mirip?teks=...&hanya_publik=false` (mode lindung) | Layanan menerima `hanya_publik=true` | Query parameter dipaksa `hanya_publik=true` | **PASSED** |
| **M11** | Layanan menjawab 404 `{"detail":"belum siap"}` | Gerbang menjawab 404 dengan body yang sama | Status 404, payload `{"detail":"belum siap"}` | **PASSED** |
| **M12** | `GET /cari?q=a` (1 karakter) | 422 dari backend, handler **tidak** dipanggil | Status 422 Unprocessable, transport 0 call | **PASSED** |
| **M13** | Harmonisasi: temuan memuat `alternatif` dokumen nonaktif | Temuan tetap ada, `alternatif` dibuang, penanda rahasia hilang, `disaring_backend` ≥ 1 | Alternatif kosong `[]`, teks penanda hilang, disaring ≥ 1 | **PASSED** |
| **M14** | `/analisa/{id}` memuat `dasar_hukum` non-publik & `terdekat` nonaktif | Elemen list dibuang; `terdekat.document_id = null`, kutipan hilang, teks tetap ada; penanda rahasia hilang | `dasar_hukum` `[]`, `terdekat` tereduksi tanpa kutipan, teks penanda hilang | **PASSED** |
| **M15** | Harmonisasi dengan body `[<id non-publik>]` | 422 `pembanding_kosong`, handler **tidak** dipanggil | Status 422 `pembanding_kosong`, transport 0 call | **PASSED** |
| **M16** | Harmonisasi sukses | Audit: `jumlah_korpus` int, `korpus_dibatasi_pengguna` bool, tidak ada list ID | Audit terekam dengan `jumlah_korpus: 1`, `korpus_dibatasi_pengguna: true` | **PASSED** |
| **M17** | `/analisa/{id}/klausul` memuat `hasil` dokumen nonaktif | Elemen list dibuang, penanda rahasia hilang, `disaring_backend` ≥ 1 | Hasil kosong `[]`, teks penanda hilang, disaring ≥ 1 | **PASSED** |

> *Catatan Penyesuaian M08:* Nilai `disaring_backend` berubah dari 2 menjadi 3 karena pada penyaring rekursif baru (`saring_rujukan`), penentralan `document_id = null` dan pembersihan atribut sensitif pada entri `rujukan` dokumen nonaktif kini ikut dihitung sebagai 1 item penyaringan backend (1 kandidat + 1 temuan + 1 rujukan).

---

## 5. Output Mentah Eksekusi Terminal

### A. Ruff Check
```
.\venv\Scripts\ruff.exe check --select E9,F821,F822,F823 app scripts tests
All checks passed!
```

### B. Pytest Suite Gerbang ML (`tests/test_step16_ml_gateway.py`)
```
============================= test session starts =============================
platform win32 -- Python 3.13.7, pytest-9.1.1, pluggy-1.6.0 -- C:\Hero\hero-backend\venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Hero\hero-backend
plugins: anyio-4.15.1
collecting ... collected 17 items

tests/test_step16_ml_gateway.py::test_m01_ml_service_url_empty_returns_503 PASSED [  5%]
tests/test_step16_ml_gateway.py::test_m02_connect_error_returns_503 PASSED [ 11%]
tests/test_step16_ml_gateway.py::test_m03_timeout_returns_504 PASSED     [ 17%]
tests/test_step16_ml_gateway.py::test_m04_analisa_active_public_doc_returns_200 PASSED [ 23%]
tests/test_step16_ml_gateway.py::test_m05_analisa_inactive_doc_returns_404_handler_not_called PASSED [ 29%]
tests/test_step16_ml_gateway.py::test_m06_analisa_non_public_doc_protected_mode_returns_403 PASSED [ 35%]
tests/test_step16_ml_gateway.py::test_m07_harmonisasi_body_null_filters_inactive_and_non_public PASSED [ 41%]
tests/test_step16_ml_gateway.py::test_m08_harmonisasi_response_filtering_and_audit PASSED [ 47%]
tests/test_step16_ml_gateway.py::test_m09_cari_default_method_and_filtering PASSED [ 52%]
tests/test_step16_ml_gateway.py::test_m10_pasal_mirip_protected_mode_forces_hanya_publik PASSED [ 58%]
tests/test_step16_ml_gateway.py::test_m11_ml_service_returns_404_gateway_forwards PASSED [ 64%]
tests/test_step16_ml_gateway.py::test_m12_cari_query_too_short_returns_422_backend PASSED [ 70%]
tests/test_step16_ml_gateway.py::test_m13_harmonisasi_alternatif_with_inactive_doc_discarded PASSED [ 76%]
tests/test_step16_ml_gateway.py::test_m14_analisa_recursive_filtering_dasar_hukum_and_terdekat PASSED [ 82%]
tests/test_step16_ml_gateway.py::test_m15_harmonisasi_body_all_unauthorized_returns_422_pembanding_kosong PASSED [ 88%]
tests/test_step16_ml_gateway.py::test_m16_harmonisasi_success_audit_format PASSED [ 94%]
tests/test_step16_ml_gateway.py::test_m17_analisa_klausul_hasil_inactive_doc_discarded PASSED [100%]

============================== warnings summary ===============================
venv\Lib\site-packages\fastapi\testclient.py:1
  C:\Hero\hero-backend\venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

venv\Lib\site-packages\starlette\testclient.py:53
  C:\Hero\hero-backend\venv\Lib\site-packages\starlette\testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

tests/test_step16_ml_gateway.py::test_m15_harmonisasi_body_all_unauthorized_returns_422_pembanding_kosong
  C:\Hero\hero-backend\venv\Lib\site-packages\fastapi\routing.py:352: StarletteDeprecationWarning: 'HTTP_422_UNPROCESSABLE_ENTITY' is deprecated. Use 'HTTP_422_UNPROCESSABLE_CONTENT' instead.
    return await dependant.call(**values)

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================= 17 passed, 3 warnings in 24.06s =======================
```

### C. Pytest Seluruh Suite (`python -m pytest -q`)
```
289 passed, 1 skipped, 35 warnings in 375.70s (0:06:15)
```

### D. Uji Live Kontainer Docker (dari Langkah 16)
```powershell
docker compose up -d --build backend
Start-Sleep -Seconds 15
curl.exe -s http://localhost:8000/health
curl.exe -s -i http://localhost:8000/api/v1/ml/health
```

Output nyata:
```
{"status":"ok","database":"ok","version":"0.10.0","app_env":"development","alembic_revision":"f6a7b8c9d0e1","alembic_head":"f6a7b8c9d0e1","migrations_up_to_date":true,"storage_writable":true,"crawler_backend":"simple_http","crawler_loaded":true,"auth_enabled":false,"protect_non_public":true}
HTTP/1.1 503 Service Unavailable
date: Tue, 13 Oct 2026 09:26:10 GMT
server: uvicorn
content-length: 130
content-type: application/json
vary: Origin
x-content-type-options: nosniff
x-frame-options: DENY
referrer-policy: strict-origin-when-cross-origin

{"detail":{"code":"layanan_analisa_belum_dikonfigurasi","message":"Layanan analisa belum dikonfigurasi (ML_SERVICE_URL kosong)."}}
```

---

## 6. Riwayat Commit dan Status Git

### A. `git log --oneline -6`
```
<commit 16b> fix(step16): saring rujukan dokumen secara rekursif di gerbang ml
1ed2d6f feat(step16): gerbang analisa ml untuk proteksi akses dan harmonisasi (issue #116)
45cd17f fix(step15): pertahankan alasan penempatan saat worker melapor galat
363ad3b fix(step15): penanganan kegagalan penempatan dokumen dan antrean kegagalan (issue #117)
f09d2a2 docs(step14): ganti hasil uji live dengan output asli
98a2b34 feat(step14): nonaktifkan dan pindahkan dokumen (US-30, FR-KB-08, TC-15)
```

### B. `git status --short`
```
(bersih / working tree clean setelah commit)
```


