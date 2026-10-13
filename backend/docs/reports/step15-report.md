# Laporan Langkah 15 HERO Backend (Bug #117: Penempatan Gagal Dijawab 200)

**Tanggal:** 13 Oktober 2026  
**Branch:** `fix/step15-penempatan-gagal`  
**Base Commit:** `f09d2a2` (Langkah 14: Nonaktifkan & Pindahkan Dokumen)  
**Referensi:** Bug #117, US-20, US-21, US-23  

---

## 1. Ringkasan Eksekutif & Latar Masalah (Bug #117)

Pada insiden 13 Oktober (dokumen 93, 94, dan 137 di VPS):
1. Worker Data mengirimkan `PATCH /api/v1/internal/documents/{id}/extraction` dengan `judul` sepanjang 298 karakter, melebihi kolom `documents.title` (`String(255)`).
2. Endpoint `patch_extraction_result` mengubah atribut dokumen di memori, lalu memanggil `PlacementService.place()`.
3. Di dalam `PlacementService.place()`, pemanggilan `self.db.commit()` ikut membawa perubahan ekstraksi yang belum di-commit. Hal ini memicu error batas karakter database, lalu blok `except` melakukan `rollback()` dan mengembalikan `PlacementResult(placed=False, reason="gagal: ...")`.
4. Router tetap mencatat audit, melakukan commit, dan menjawab **200 OK**. Status dokumen tertinggal di `diproses`, terus diklaim ulang tiap 30 menit, dan tidak meninggalkan jejak di antrean kegagalan (`ingest_failures`).
5. Pola kegagalan serupa juga ditemukan pada `PATCH /documents/{id}/metadata` (koreksi metadata pengguna hilang diam-diam dengan respons 200) dan `POST /documents/{id}/place`.

### Solusi yang Diimplementasikan:
1. **Validasi Panjang Input:**
   - Menambahkan `max_length` pada schema `ExtractionResultIn` dan `UpdateMetadataIn` yang membaca langsung batas kolom model `Document` (`title: 255`, `regulation_number: 100`, `regulation_type: 100`, `bidang: 150`, `extraction_engine: 100`, `extraction_method: 13`).
   - Input yang melebihi batas langsung ditolak dengan **422 Unprocessable Entity** sebelum data diproses.
2. **Pemisahan Transaksi Simpan Ekstraksi vs Penempatan:**
   - Hasil ekstraksi dan status awal (`terindeks` / `perlu_koreksi`) disimpan dan di-commit terlebih dahulu secara mandiri. Bila commit ini gagal, status diubah menjadi `gagal`, dicatat ke `IngestFailure` (`simpan_ekstraksi_gagal`), dan dijawab **500**.
   - Baru setelah ekstraksi aman, `PlacementService.place()` dipanggil.
   - Bila penempatan gagal (`reason` diawali `gagal:`), di transaksi baru status diset ke `perlu_koreksi`, dicatat ke `IngestFailure` (`reason_code="penempatan_gagal"`, `is_retryable=True`), audit `PLACE_DOCUMENT_FAILED` dicatat, dan endpoint mengembalikan **422**.
   - Jika reason `metadata_belum_cukup`, tetap dijawab 200 karena bukan kegagalan sistem.
3. **Pencegahan Duplikasi Entri Kegagalan:**
   - Bila worker mengirimkan payload `error` lanjutan (`force=true`) setelah 4xx, sistem memperbarui pesan pada `IngestFailure` terbuka yang sudah ada, tanpa membuat baris baru dan tanpa mengubah status `perlu_koreksi` menjadi `gagal`.
4. **Alur Pemrosesan Ulang (Retry):**
   - Pada `FailureService.retry`, kegagalan dengan `reason_code="penempatan_gagal"` akan memicu penempatan ulang berkas (`place(force=True)`). Bila berhasil, status dokumen dievaluasi kembali (`terindeks`) dan status tindak lanjut kegagalan ditandai selesai (`diproses_ulang`).
5. **Endpoint Pengguna:**
   - `PATCH /documents/{id}/metadata`: bila penempatan gagal, seluruh perubahan di-rollback dan mengembalikan **422**.
   - `POST /documents/{id}/place`: bila penempatan gagal, mengembalikan **422** beserta alasan galat.
   - `POST /documents/place-pending`: batch penempatan tetap mengembalikan 200, dilengkapi `failed_count` dan daftar dokumen yang gagal.

---

## 2. Catatan untuk Lapisan Data

> [!IMPORTANT]
> **Penyesuaian Respons API Internal Ekstraksi untuk Pipeline Data/ML:**
> 1. **Respons Galat HTTP 422 & 500:**
>    - `PATCH /api/v1/internal/documents/{id}/extraction` kini **tidak lagi menjawab 200 saat penempatan gagal**.
>    - Jika ada field payload melebihi panjang kolom model (misalnya `judul` > 255 karakter), server langsung menjawab **422 Unprocessable Entity** dengan rincian field dan batasnya.
>    - Jika penyimpanan hasil ekstraksi gagal di database, server menjawab **500 Internal Server Error** dengan kode `"simpan_ekstraksi_gagal"` dan `failure_id`.
>    - Jika penyimpanan ekstraksi sukses namun pemindahan fisik/penamaan berkas gagal, server menjawab **422 Unprocessable Entity** dengan body:
>      ```json
>      {
>        "detail": {
>          "code": "penempatan_gagal",
>          "message": "gagal: <alasan>",
>          "failure_id": 123,
>          "processing_status": "perlu_koreksi"
>        }
>      }
>      ```
> 2. **Komentar di Worker Data (`pipeline/hero/bridge/extract_worker.py` ± baris 157):**
>    - Komentar historis yang menyatakan *"PATCH menjawab 200 tetapi … tetap diproses"* kini sudah usang dan dapat disesuaikan oleh Fathir karena backend kini mengembalikan 422 secara eksplisit dan dokumen dipindahkan ke status `perlu_koreksi` serta masuk ke antrean kegagalan (`ingest_failures`).

---

## 3. Git Diff Stat Ringkas

```
 app/routers/documents.py               |  41 +++++++--
 app/routers/internal.py                | 182 +++++++++++++++++++++++++++++++++++-----
 app/services/audit_service.py          |   1 +
 app/services/failure_service.py        |  74 ++++++++++++++++
 docs/api/KONTRAK-API-FASE1.md          |   8 +-
 docs/api/openapi-fase1.json            |  30 ++++---
 tests/test_placement.py                |   8 +-
 tests/test_step15_placement_failure.py | 212 +++++++++++++++++++++++++++++++++++++++++
 8 files changed, 512 insertions(+), 44 deletions(-)
```

---

## 4. Tabel Hasil Pengujian Backend (B01 – B10)

Seluruh pengujian pada `tests/test_step15_placement_failure.py` lulus 100%:

| # | Kasus Uji | Ekspektasi | Hasil | Status |
|---|---|---|---|:---:|
| **B01** | PATCH extraction dengan `judul` 298 karakter | 422 menyebut `title`/`judul` dan batas 255; dokumen tidak berubah | HTTP 422, pesan memuat `title`/`judul` dan `255`, judul di DB tetap | **PASSED** |
| **B02** | PATCH extraction valid, `move` dipaksa gagal | 422 `penempatan_gagal`; status `perlu_koreksi` (bukan `diproses`); teks dan metadata tersimpan; ada `IngestFailure` dengan `document_id` dan `reason_code=penempatan_gagal`; ada audit `PLACE_DOCUMENT_FAILED` | HTTP 422, status `perlu_koreksi`, metadata tersimpan, `IngestFailure` tercatat, audit log tersimpan | **PASSED** |
| **B03** | Setelah B02, worker mengirim payload `error` (`force=true`) | Tidak ada `IngestFailure` kedua; status tetap `perlu_koreksi` | HTTP 200 `gagal_dicatat`, failure_id sama, total failure tetap 1, status tetap `perlu_koreksi` | **PASSED** |
| **B04** | Proses ulang kegagalan B02 lewat endpoint retry, `move` sudah normal | Berkas ditempatkan di `kb/`; kegagalan `selesai`; status `terindeks` | HTTP 200, outcome `success`, berkas di `kb/`, failure `diproses_ulang`, status doc `terindeks` | **PASSED** |
| **B05** | `POST /documents/{id}/place` dengan `move` gagal | 422 berisi alasan | HTTP 422, kode `penempatan_gagal` beserta pesan alasan | **PASSED** |
| **B06** | `PATCH /documents/{id}/metadata` mengubah `regulation_number`, `move` gagal | 422; nomor di DB tidak berubah; `file_path_pdf` tidak berubah | HTTP 422, rollback DB berhasil, nomor dan path PDF di DB tidak berubah | **PASSED** |
| **B07** | Regresi: PATCH extraction valid dan `move` normal | 200 seperti sebelumnya; `placement.placed = true` | HTTP 200, status `terindeks`, `placed: true`, path berawalan `kb/` | **PASSED** |
| **B08** | `metadata_belum_cukup` | Tetap 200; tidak ada `IngestFailure` | HTTP 200, `placed: false`, `reason: "metadata_belum_cukup"`, 0 IngestFailure | **PASSED** |
| **B09** | `place-pending` dengan satu dokumen gagal | 200; `failed_count = 1` dan id-nya tercantum | HTTP 200, `failed_count = 1`, ID dokumen gagal tercantum pada `failed_documents` dan `results` | **PASSED** |
| **B10** | `UpdateMetadataIn` dengan `title` 300 karakter | 422 | HTTP 422, penolakan schema Pydantic, data di DB tidak tersentuh | **PASSED** |

---

## 5. Hasil Eksekusi Terminal (Output Mentah)

### 5.1. Eksekusi Unit Test Langkah 15 (`pytest tests/test_step15_placement_failure.py -v`)
```
============================= test session starts =============================
platform win32 -- Python 3.13.7, pytest-9.1.1, pluggy-1.6.0 -- C:\Hero\hero-backend\venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Hero\hero-backend
plugins: anyio-4.15.1
collecting ... collected 10 items

tests/test_step15_placement_failure.py::test_b01_patch_extraction_title_too_long PASSED [ 10%]
tests/test_step15_placement_failure.py::test_b02_patch_extraction_valid_move_fails PASSED [ 20%]
tests/test_step15_placement_failure.py::test_b03_after_b02_worker_sends_error_payload_no_duplicate_failure PASSED [ 30%]
tests/test_step15_placement_failure.py::test_b04_retry_b02_failure_when_move_normal PASSED [ 40%]
tests/test_step15_placement_failure.py::test_b05_post_place_document_fails_returns_422 PASSED [ 50%]
tests/test_step15_placement_failure.py::test_b06_patch_metadata_changing_reg_num_move_fails_rollback PASSED [ 60%]
tests/test_step15_placement_failure.py::test_b07_regression_patch_extraction_valid_and_move_normal PASSED [ 70%]
tests/test_step15_placement_failure.py::test_b08_metadata_belum_cukup_returns_200_no_failure PASSED [ 80%]
tests/test_step15_placement_failure.py::test_b09_place_pending_with_one_document_failure PASSED [ 90%]
tests/test_step15_placement_failure.py::test_b10_update_metadata_title_too_long_returns_422 PASSED [100%]

============================== warnings summary ===============================
venv\Lib\site-packages\fastapi\testclient.py:1
  C:\Hero\hero-backend\venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

venv\Lib\site-packages\starlette\testclient.py:53
  C:\Hero\hero-backend\venv\Lib\site-packages\starlette\testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

tests/test_step15_placement_failure.py::test_b02_patch_extraction_valid_move_fails
tests/test_step15_placement_failure.py::test_b03_after_b02_worker_sends_error_payload_no_duplicate_failure
tests/test_step15_placement_failure.py::test_b04_retry_b02_failure_when_move_normal
tests/test_step15_placement_failure.py::test_b05_post_place_document_fails_returns_422
tests/test_step15_placement_failure.py::test_b06_patch_metadata_changing_reg_num_move_fails_rollback
  C:\Users\IBUCOMP\Downloads\hero-backend\venv\Lib\site-packages\anyio\_backends\_asyncio.py:1100: StarletteDeprecationWarning: 'HTTP_422_UNPROCESSABLE_ENTITY' is deprecated. Use 'HTTP_422_UNPROCESSABLE_CONTENT' instead.
    result = context.run(func, *args)

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================= 10 passed, 7 warnings in 17.35s =======================
```

### 5.2. Eksekusi Ruff Check
Perintah:
```powershell
.\venv\Scripts\ruff.exe check --select E9,F821,F822,F823 app scripts tests
```
Output:
```
All checks passed!
```

### 5.3. Eksekusi Seluruh Suite Pytest (`python -m pytest -q`)
Perintah:
```powershell
.\venv\Scripts\python.exe -m pytest -q
```
Output:
```
272 passed, 1 skipped, 34 warnings in 431.60s (0:07:11)
```

---

## 6. Pengujian Live (Docker & Endpoint Dokumen #71)

### 6.1. Rebuild & Start Backend Container
Perintah:
```powershell
docker compose up -d --build backend
```
Output mentah:
```
#1 [internal] load local bake definitions
#1 reading from stdin 512B done
#1 DONE 0.0s

#2 [internal] load build definition from Dockerfile
#2 transferring dockerfile:
#2 transferring dockerfile: 825B 0.0s done
#2 DONE 0.2s

#3 [internal] load metadata for docker.io/library/python:3.11-slim
#3 DONE 4.0s

#4 [internal] load .dockerignore
#4 transferring context: 110B 0.0s done
#4 DONE 0.1s

#5 [internal] load build context
#5 DONE 0.0s

#6 [1/7] FROM docker.io/library/python:3.11-slim@sha256:e88e9763f943ec1834f992a4b51e0f24500486803e8bc534e5767af9ea65f6ce
#6 resolve docker.io/library/python:3.11-slim@sha256:e88e9763f943ec1834f992a4b51e0f24500486803e8bc534e5767af9ea65f6ce 0.1s done
#6 DONE 0.1s

#5 [internal] load build context
#5 transferring context: 1.28MB 1.2s done
#5 DONE 1.4s

#7 [4/7] COPY requirements.txt .
#7 CACHED

#8 [2/7] WORKDIR /app
#8 CACHED

#9 [3/7] RUN apt-get update && apt-get install -y     gcc     libpq-dev     && rm -rf /var/lib/apt/lists/*
#9 CACHED

#10 [5/7] RUN pip install --no-cache-dir -r requirements.txt
#10 CACHED

#11 [6/7] COPY . .
#11 DONE 9.7s

#12 [7/7] RUN chmod +x scripts/entrypoint.sh
#12 DONE 2.8s

#13 exporting to image
#13 exporting layers
#13 exporting layers 20.0s done
#13 exporting manifest sha256:57bfd2e1df174e3e34c354f92f79f4410d56a3b2db2a6ac8a4f6c62c93300d2a 0.1s done
#13 exporting config sha256:70d3b2cb3a1c4032501ce48c6d512354773f505ad10f3216c086b669dd450cec 0.0s done
#13 exporting attestation manifest sha256:ab5248f13f64564c18197f1a72cc73b6195e75cf30299a4c76a3bbde7c57d310
#13 exporting attestation manifest sha256:ab5248f13f64564c18197f1a72cc73b6195e75cf30299a4c76a3bbde7c57d310 0.1s done
#13 exporting manifest list sha256:a3ebe96b4b6e253c915e54cbe9896e750b22f41d1c3e6cb6843f51d561fb408e
#13 exporting manifest list sha256:a3ebe96b4b6e253c915e54cbe9896e750b22f41d1c3e6cb6843f51d561fb408e 0.1s done
#13 naming to docker.io/library/hero-backend-backend:latest 0.0s done
#13 unpacking to docker.io/library/hero-backend-backend:latest
#13 unpacking to docker.io/library/hero-backend-backend:latest 3.0s done
#13 DONE 23.4s

#14 resolving provenance for metadata file
#14 DONE 0.1s
 hero-backend-backend  Built
 Container hero_postgres  Running
 Container hero_fastapi  Recreate
 Container hero_fastapi  Recreated
 Container hero_postgres  Waiting
 Container hero_postgres  Healthy
 Container hero_fastapi  Starting
 Container hero_fastapi  Started
```

### 6.2. Health Check
Perintah:
```powershell
Start-Sleep -Seconds 15; curl.exe -s http://localhost:8000/health
```
Output mentah:
```json
{"status":"ok","database":"ok","version":"0.10.0","app_env":"development","alembic_revision":"f6a7b8c9d0e1","alembic_head":"f6a7b8c9d0e1","migrations_up_to_date":true,"storage_writable":true,"crawler_backend":"simple_http","crawler_loaded":true,"auth_enabled":false,"protect_non_public":true}
```

### 6.3. Uji Live Penempatan Dokumen #71 (`POST /api/v1/documents/71/place`)
Perintah:
```powershell
curl.exe -s -X POST http://localhost:8000/api/v1/documents/71/place
```
Output mentah:
```json
{"document_id":71,"placed":true,"reason":"sudah_ditempatkan","old_path":"kb/POJK/POJK 21 Tahun 2023 POJK 21 2023 Layanan Digital Bank Umum 2023.pdf","new_path":"kb/POJK/POJK 21 Tahun 2023 POJK 21 2023 Layanan Digital Bank Umum 2023.pdf","category_id":1,"category_path":["POJK"]}
```
*Keterangan: Dokumen #71 sudah berada di `kb/`, mengembalikan status 200 dengan reason `"sudah_ditempatkan"`, membuktikan tidak ada kegagalan regresi pada data live.*

---

## 7. Riwayat Git Log & Git Status

### 7.1. Git Log (`git log --oneline -4`)
Perintah:
```powershell
git log --oneline -4
```
Output mentah:
```
106f0dd fix(step15): penanganan kegagalan penempatan dokumen dan antrean kegagalan (issue #117)
f09d2a2 docs(step14): ganti hasil uji live dengan output asli
98a2b34 feat(step14): nonaktifkan dan pindahkan dokumen (US-30, FR-KB-08, TC-15)
2ef90a1 feat(articles): kontrak pasal untuk lapisan data (Langkah 13)
```

### 7.2. Git Status (`git status --short`)
Perintah:
```powershell
git status --short
```
Output mentah:
```
(clean working tree, tidak ada berkas tersisa)
```

