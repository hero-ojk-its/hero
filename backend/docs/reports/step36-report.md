# Laporan Langkah 36 — Pengamanan Job Analisa, Batas Tunggu ML, Konsistensi Audit & Kelengkapan Respons Dokumen

Tanggal: 6 November 2026  
Branch: `fix/step36-job-analisa`  
Basis: `main` (commit `ce2ac80 chore: sinkron dari monorepo (PR Fathir #174-#188)`)  

---

## 1. Ringkasan Eksekutif

Langkah 36 menuntaskan enam area perbaikan kritis hasil tinjauan arsitektur PR #174 dan #182:

1. **Pengamanan Job Analisa di Latar Belakang (`_AnalisaJobStore`)**:
   - **Pencegahan Garbage Collection**: Menyimpan seluruh referensi task asinkron ke dalam `self._tasks = set()` di memori store, dibersihkan secara otomatis via `task.add_done_callback(self._tasks.discard)` saat eksekusi selesai.
   - **Validasi Akses & Layanan Sebelum Job Dibuat**: `POST /ml/analisa/{document_id}/mulai` kini memvalidasi konfigurasi layanan ML (503 jika kosong) dan hak akses dokumen (`check_document_access`, 404 jika tidak ditemukan/nonaktif, 403 jika non-publik tanpa izin) secara sinkron sebelum job dibuat. Tidak ada job menggantung yang dibuat sia-sia jika validasi awal gagal.
   - **Isolasi Kepemilikan Job (Ownership)**: Menyimpan `pemilik_id`, `document_id`, dan `mode` pada metadata job. Saat `AUTH_ENABLED=true`, polling `GET /ml/analisa-job/{job_id}` oleh pengguna selain pembuat job akan mengembalikan `404 job_tidak_ditemukan` (mencegah kebocoran hasil analisa dan eksistensi job).
   - **Pembersihan Job Berjalan Melampaui Batas**: Job dengan status `berjalan` yang melampaui `ml_job_timeout_seconds + 120` detik otomatis ditandai `gagal` dengan kode galat `analisa_terlalu_lama` (HTTP 504) saat `_bersihkan` berjalan.
   - **Penanganan Galat HTTP (JSONResponse)**: Deteksi respons `JSONResponse` dengan status >= 400 dari proses internal untuk memastikan status job berubah menjadi `gagal` beserta detail galat yang sesuai.

2. **Batas Waktu ML yang Tetap Aman & Reaktivasi Fallback Cache Basi**:
   - Default `ml_timeout_seconds` diubah dari `0.0` menjadi `300.0` (5 menit) untuk panggilan sinkron.
   - Ditambahkan setting baru `ml_job_timeout_seconds: float = 900.0` (15 menit) untuk eksekusi di dalam job latar belakang.
   - Nilai `<= 0` tetap didukung via env untuk mode tanpa batas, namun diberi dokumentasi jelas bahwa tanpa batas baca akan mematikan mekanisme fallback ke cache basi (skenario #55) saat layanan ML mengalami gangguan/stuck.
   - Eksekusi job dibungkus dengan batas waktu pembacaan httpx dan pengaman `asyncio.wait_for(..., timeout=ml_job_timeout_seconds + 60)`. Bila ML timeout (504), fallback cache basi di dalam `_jalankan_analisa` otomatis terpicu.

3. **Temuan Evaluasi Harmonisasi (§2f)**:
   - Mesin harmonisasi regulasi (`pipeline/hero/harmonisasi/engine.py` & `pipeline/hero/bridge/ml_api.py`) bekerja secara **leksikal dan deterministik** menggunakan TF-IDF / cosine similarity matriks jarang (`scipy.sparse`).
   - Eksekusi lokal berlangsung dalam hitungan detik (< 5 detik) bahkan untuk perbandingan terhadap ratusan korpus regulasi, dan **sama sekali tidak memanggil LLM atau API eksternal**.
   - Kesimpulan: Endpoint `POST /ml/harmonisasi/{document_id}` **TIDAK** membutuhkan endpoint job latar belakang karena tidak berisiko diputus Cloudflare (~100 detik).

4. **Konsistensi Audit Sumber Scraping (§3)**:
   - Menyeragamkan pencatatan jejak audit `UPDATE_SOURCE` pada `scripts/periksa_draft_publik.py` dari `target_resource=f"source:{src.id}"` menjadi `target_resource=f"scraping_source:{src.id}"` sesuai standar router `app/routers/scraping_sources.py`.

5. **Peringatan Multi-Worker Startup (§2e)**:
   - Pada startup lifespan `app/main.py`, sistem mendeteksi jika `UVICORN_WORKERS > 1` dan mengeluarkan log peringatan (`logger.warning`) bahwa job analisa disimpan dalam memori per-worker sehingga polling status job dapat mengembalikan 404 jika mendarat di worker berbeda.

6. **Kelengkapan Peran (`document_role`) dan Klasifikasi (`access_classification`) (§4)**:
   - Mengidentifikasi dan menambahkan kedua field (sebagai string nilai enum) pada seluruh respons yang mengembalikan objek dokumen atau ringkasan dokumen:
     * `GET /api/v1/documents/needs-review`
     * `lampiran` dan `induk` pada `_format_single_document_response` (`GET /documents/{id}`)
     * Root dan relasi (`induk`, `diubah_oleh`, `dicabut_oleh`, `mencabut`) pada `GET /documents/{id}/versi`
     * `draft_mirip` pada `GET /documents/{id}/kemiripan-draft`
     * `match_document` pada `GET /api/v1/scans/{id}/candidates`
     * `documents` (`JobDocumentSummary`) dan `duplicate_of_document` (`DuplicateDocumentInfo`) pada ingest jobs dan failures.

---

## 2. Tabel Kelengkapan Field Peran & Klasifikasi Respons Dokumen (§4)

| Endpoint | Punya `access_classification`? | Punya `document_role`? | Keterangan & Tindakan Perbaikan |
|---|---|---|---|
| `GET /api/v1/documents/` (Pencarian & Daftar Dokumen) | Ya (sudah ada) | Ya (sudah ada) | Difilter dan dipetakan di `SearchService.search`. |
| `GET /api/v1/documents/{id}` (Detail Dokumen Tunggal — root) | Ya (sudah ada) | Ya (sudah ada) | Diformat di `_format_single_document_response`. |
| `GET /api/v1/documents/{id}` (Objek dalam array `lampiran`) | **Belum -> Ditambahkan** | **Belum -> Ditambahkan** | Sebelumnya hanya memuat `document_id`, `title`, `attachment_label`. Ditambahkan string enum keduanya. |
| `GET /api/v1/documents/{id}` (Objek dokumen `induk`) | **Belum -> Ditambahkan** | **Belum -> Ditambahkan** | Sebelumnya hanya memuat `document_id`, `title`, `status_keberlakuan`. Ditambahkan string enum keduanya. |
| `GET /api/v1/documents/needs-review` (Daftar dokumen perlu koreksi) | **Belum -> Ditambahkan** | **Belum -> Ditambahkan** | Sebelumnya tidak memuat kedua field, menyebabkan modal koreksi frontend defaulting ke `publik`/`corpus_eksisting`. Ditambahkan string enum keduanya. |
| `GET /api/v1/documents/{id}/versi` (Root response) | **Belum -> Ditambahkan** | **Belum -> Ditambahkan** | Ditambahkan di skema `DocumentVersionResponse` dan `version_service.get_versioning_details`. |
| `GET /api/v1/documents/{id}/versi` (Relasi `induk`, `diubah_oleh`, `dicabut_oleh`, `mencabut`) | **Belum -> Ditambahkan** | **Belum -> Ditambahkan** | Ditambahkan di skema `VersionRelationItem` dan `version_service.resolve_doc`. |
| `GET /api/v1/documents/{id}/kemiripan-draft` (Item dalam `draft_mirip`) | **Belum -> Ditambahkan** | **Belum -> Ditambahkan** | Ditambahkan di skema `DraftMiripItem` dan `kemiripan_service.cari_draft_mirip`. |
| `PATCH /api/v1/documents/{id}/metadata` (Respons patch dokumen) | Ya (sudah ada) | Ya (sudah ada) | `DocumentMetadataPatchResponse` sudah memiliki kedua field. |
| `GET /api/v1/scans/{id}/candidates` (Field `match_document`) | **Belum -> Ditambahkan** | **Belum -> Ditambahkan** | Ditambahkan di skema `CandidateMatchDocument`. |
| `GET /api/v1/ingest/jobs/{job_id}` (Item dalam `documents`) | **Belum -> Ditambahkan** | **Belum -> Ditambahkan** | Ditambahkan di skema `JobDocumentSummary` dan `get_job_detail`. |
| `GET /api/v1/ingest/jobs/{job_id}` & `GET /failures/{id}` (`duplicate_of_document`) | **Belum -> Ditambahkan** | **Belum -> Ditambahkan** | Ditambahkan di skema `DuplicateDocumentInfo` dan pemetaannya. |
| `GET /api/v1/categories/tree` | N/A (hanya agregat count) | N/A (hanya agregat count) | Tidak mengembalikan objek dokumen, hanya `document_count`. |
| `GET /api/v1/categories/{id}` | N/A (hanya agregat count) | N/A (hanya agregat count) | Tidak mengembalikan objek dokumen, hanya `document_count`. |
| `GET /api/v1/documents/{id}/analisa/banding` | N/A (objek analisa) | N/A (objek analisa) | Hanya mengembalikan perbandingan deterministik vs AI. |
| `GET /api/v1/documents/{id}/analisa/riwayat` | N/A (objek run analisa) | N/A (objek run analisa) | Hanya mengembalikan riwayat eksekusi analisa. |

---

## 3. Catatan Koordinasi

### Catatan untuk Pipeline / Infra (Fathir)
1. **Timeout ML Baru**:
   - Default batas waktu baca untuk panggilan analisa sinkron kini adalah **300 detik** (`ML_TIMEOUT_SECONDS=300.0`).
   - Batas waktu baca untuk job analisa latar belakang adalah **900 detik** (`ML_JOB_TIMEOUT_SECONDS=900.0`).
   - **Alasan**: Pengaturan tanpa batas waktu (`0.0`) mematikan fallback otomatis ke cache basi (skenario #55) saat layanan AI macet/hang, karena HTTP timeout (504) tidak pernah terpicu. Dengan timeout ini, jika model AI hang, sistem akan otomatis melempar 504 dan mengambil hasil analisa sebelumnya dari cache bila tersedia.
   - Jika di masa mendatang Anda ingin mengembalikan perilaku tanpa batas, Anda tetap dapat mengatur `ML_TIMEOUT_SECONDS=0` dan `ML_JOB_TIMEOUT_SECONDS=0` di environment VPS Anda tanpa perlu mengubah kode backend.
2. **Uvicorn Worker**:
   - `UVICORN_WORKERS=1` **wajib** digunakan pada deployment VPS selama antrian job analisa disimpan dalam memori in-memory worker. Menjalankan > 1 worker dapat menyebabkan polling `GET /ml/analisa-job/{id}` mendarat di worker berbeda dan menghasilkan 404.

### Catatan untuk Frontend (Ikhwan)
1. **Respons Endpoint Job Analisa**:
   - `POST /api/v1/ml/analisa/{id}/mulai` dan `GET /api/v1/ml/analisa-job/{id}` kompatibel penuh dengan kode FE yang ada.
   - Respons polling `GET /ml/analisa-job/{id}` kini menyertakan field tambahan: `document_id` (integer) dan `mode` (string, misal `"ai"` atau `"deterministik"`).
   - Interval polling yang disarankan adalah **3 detik**.
   - Bila autentikasi aktif, job hanya dapat dibaca oleh pengguna yang membuatnya (pengguna lain akan menerima 404).
2. **Harmonisasi Regulasi**:
   - Endpoint `POST /api/v1/ml/harmonisasi/{document_id}` tetap berjalan sinkron karena pemrosesan TF-IDF lokal sangat cepat (< 5 detik) dan tidak memerlukan polling job latar belakang.
3. **Kelengkapan Field Dokumen**:
   - Seluruh endpoint dokumen (`needs-review`, `versi`, relasi versi, lampiran, induk dokumen, kemiripan draft, dan scan candidates) kini dipastikan menyertakan `access_classification` dan `document_role`. Frontend tidak perlu lagi melakukan fallback senyap (`publik`/`corpus_eksisting`).
   - Silakan jalankan `npm run gen:api` untuk memperbarui tipe TypeScript frontend dari snapshot OpenAPI terbaru (`docs/api/openapi-fase1.json`).

---

## 4. Hasil Pengujian Pytest

### 4.1 Pytest Kasus Uji Langkah 36 (`tests/test_step36_job_analisa.py`)
```
============================= test session starts =============================
platform win32 -- Python 3.13.7, pytest-9.1.1, pluggy-1.6.0 -- C:\Hero\hero-backend\venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Hero\hero-backend
plugins: anyio-4.15.1
collecting ... collected 15 items

tests/test_step36_job_analisa.py::test_j01_post_mulai_sukses_lalu_poll PASSED [  6%]
tests/test_step36_job_analisa.py::test_j02_post_mulai_doc_tidak_ada_404_langsung PASSED [ 13%]
tests/test_step36_job_analisa.py::test_j03_post_mulai_doc_non_publik_auth_mati_403 PASSED [ 20%]
tests/test_step36_job_analisa.py::test_j04_post_mulai_ml_service_url_kosong_503 PASSED [ 26%]
tests/test_step36_job_analisa.py::test_j05_poll_job_tidak_ada_404 PASSED [ 33%]
tests/test_step36_job_analisa.py::test_j06_poll_job_milik_pengguna_lain_auth_aktif_404 PASSED [ 40%]
tests/test_step36_job_analisa.py::test_j07_ml_timeout_fallback_cache_atau_504 PASSED [ 46%]
tests/test_step36_job_analisa.py::test_j08_ml_gagal_500_status_job_gagal PASSED [ 53%]
tests/test_step36_job_analisa.py::test_j09_task_reference_disimpan_dan_dibersihkan PASSED [ 60%]
tests/test_step36_job_analisa.py::test_j10_bersih_bersih_ttl_1_jam PASSED [ 66%]
tests/test_step36_job_analisa.py::test_j11_bersih_bersih_job_berjalan_lewat_timeout PASSED [ 73%]
tests/test_step36_job_analisa.py::test_j12_startup_warning_multi_worker PASSED [ 80%]
tests/test_step36_job_analisa.py::test_j13_audit_sumber_scraping_source_di_periksa_draft_publik PASSED [ 86%]
tests/test_step36_job_analisa.py::test_r01_kelengkapan_access_classification_dan_document_role_needs_review_dan_detail PASSED [ 93%]
tests/test_step36_job_analisa.py::test_r02_kelengkapan_access_classification_dan_document_role_versi_dan_kemiripan PASSED [100%]

======================= 15 passed, 2 warnings in 19.88s =======================
```

### 4.2 Pytest Seluruh Suite

Perintah:
```powershell
.\venv\Scripts\python.exe -m pytest -q
```

Output:
```
........................................................................ [ 10%]
................................................s....................... [ 21%]
........................................................................ [ 32%]
........................................................................ [ 42%]
........................................................................ [ 53%]
........................................................................ [ 64%]
........................................................................ [ 74%]
........................................................................ [ 85%]
........................................................................ [ 96%]
..........................                                               [100%]
============================== warnings summary ===============================
venv\Lib\site-packages\fastapi\testclient.py:1
  C:\Hero\hero-backend\venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

venv\Lib\site-packages\starlette\testclient.py:53
  C:\Hero\hero-backend\venv\Lib\site-packages\starlette\testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

tests/test_placement.py::test_p09_placement_rollback_on_commit_failure
tests/test_step15_placement_failure.py::test_b02_patch_extraction_valid_move_fails
tests/test_step15_placement_failure.py::test_b03_after_b02_worker_sends_error_payload_no_duplicate_failure
tests/test_step15_placement_failure.py::test_b04_retry_b02_failure_when_move_normal
tests/test_step15_placement_failure.py::test_b05_post_place_document_fails_returns_422
tests/test_step15_placement_failure.py::test_b06_patch_metadata_changing_reg_num_move_fails_rollback
tests/test_step17_duplicate_identity.py::test_d19_patch_metadata_placement_failure_preserves_state
tests/test_step32_masukan_fe.py::test_f06_failures_tanpa_sumber_and_422_on_conflict
tests/test_step35_draft_publik_judul.py::test_d12_sumber_draft_publik_ditolak_422
  C:\Users\IBUCOMP\Downloads\hero-backend\venv\Lib\site-packages\anyio\_backends\_asyncio.py:1100: StarletteDeprecationWarning: 'HTTP_422_UNPROCESSABLE_ENTITY' is deprecated. Use 'HTTP_422_UNPROCESSABLE_CONTENT' instead.

tests/test_step13_articles.py::test_p09_migration_cleans_duplicates_and_creates_index
  C:\Hero\hero-backend\alembic\versions\f8a9b0c1d2e3_step35_persetujuan_draft_publik.py:52: SADeprecationWarning: Empty parameter sequence passed to execute(). This use is deprecated and will raise an exception in a future SQLAlchemy release
    op.drop_column('documents', 'publik_disetujui_pada')

tests/test_step13_articles.py::test_p09_migration_cleans_duplicates_and_creates_index
  C:\Hero\hero-backend\alembic\versions\f8a9b0c1d2e3_step35_persetujuan_draft_publik.py:53: SADeprecationWarning: Empty parameter sequence passed to execute(). This use is deprecated and will raise an exception in a future SQLAlchemy release
    op.drop_column('documents', 'publik_disetujui_alasan')

tests/test_step13_articles.py::test_p09_migration_cleans_duplicates_and_creates_index
  C:\Hero\hero-backend\alembic\versions\f8a9b0c1d2e3_step35_persetujuan_draft_publik.py:54: SADeprecationWarning: Empty parameter sequence passed to execute(). This use is deprecated and will raise an exception in a future SQLAlchemy release
    op.drop_column('documents', 'publik_disetujui_oleh')

tests/test_step13_articles.py: 28 warnings
  C:\Hero\hero-backend\alembic\env.py:84: SADeprecationWarning: Empty parameter sequence passed to execute(). This use is deprecated and will raise an exception in a future SQLAlchemy release
    context.run_migrations()

tests/test_step13_articles.py::test_p09_migration_cleans_duplicates_and_creates_index
  C:\Hero\hero-backend\alembic\versions\e7f8a9b0c1d2_step34_percobaan_login.py:37: SADeprecationWarning: Empty parameter sequence passed to execute(). This use is deprecated and will raise an exception in a future SQLAlchemy release
    op.drop_index(op.f('ix_percobaan_login_kunci'), table_name='percobaan_login')

tests/test_step16_ml_gateway.py::test_m15_harmonisasi_body_all_unauthorized_returns_422_pembanding_kosong
  C:\Hero\hero-backend\venv\Lib\site-packages\fastapi\routing.py:352: StarletteDeprecationWarning: 'HTTP_422_UNPROCESSABLE_ENTITY' is deprecated. Use 'HTTP_422_UNPROCESSABLE_CONTENT' instead.
    return await dependant.call(**values)

tests/test_step35_draft_publik_judul.py::test_d01_unggah_draft_publik_tanpa_persetujuan
tests/test_step35_draft_publik_judul.py::test_d02_unggah_draft_publik_alasan_kurang_panjang
  C:\Hero\hero-backend\app\routers\ingest.py:205: StarletteDeprecationWarning: 'HTTP_422_UNPROCESSABLE_ENTITY' is deprecated. Use 'HTTP_422_UNPROCESSABLE_CONTENT' instead.
    persetujuan_data = periksa_publikasi_draft(

tests/test_step35_draft_publik_judul.py::test_d05_patch_draft_nonpublik_ke_publik_tanpa_persetujuan
tests/test_step35_draft_publik_judul.py::test_d07_patch_corpus_ke_draft_tanpa_persetujuan
  C:\Hero\hero-backend\app\routers\documents.py:854: StarletteDeprecationWarning: 'HTTP_422_UNPROCESSABLE_ENTITY' is deprecated. Use 'HTTP_422_UNPROCESSABLE_CONTENT' instead.
    persetujuan_data = periksa_publikasi_draft(

tests/test_step35_draft_publik_judul.py::test_d12_sumber_draft_publik_ditolak_422
  C:\Hero\hero-backend\app\routers\scraping_sources.py:552: StarletteDeprecationWarning: 'HTTP_422_UNPROCESSABLE_ENTITY' is deprecated. Use 'HTTP_422_UNPROCESSABLE_CONTENT' instead.
    return _process_update(source_id, payload, request, db, current_user)

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
673 passed, 1 skipped, 225 warnings in 1134.37s (0:18:54)
```

---

## 5. Pemeriksaan Linting (Ruff)

Perintah:
```powershell
.\venv\Scripts\python.exe -m ruff check app scripts tests/test_step36_job_analisa.py --select E9,F
```
Output:
```
All checks passed!
```

---

## 6. Git Diff Stat (`git diff main --stat`)

```
 .env.example                            |   8 +-
 .env.prod.example                       |   7 +-
 app/config.py                           |  12 +-
 app/main.py                             |   9 ++
 app/routers/documents.py                |  12 ++
 app/routers/ingest.py                   |  34 +++++
 app/routers/ml_gateway.py               | 134 ++++++++++++++--
 app/schemas/ingest.py                   |   4 +
 app/schemas/scan.py                     |   2 +
 app/services/kemiripan_service.py       |  12 ++
 app/services/version_service.py         |  28 +++-
 docs/api/openapi-fase1.json             | 261 +++++++++++++++++++++++++++++++-
 docs/deploy/RUNBOOK-VPS.md              |  13 ++
 scripts/build_api_contract.py           |  87 ++++++++++-
 scripts/periksa_draft_publik.py         |   2 +-
 tests/test_step35_draft_publik_judul.py |   2 +-
 16 files changed, 593 insertions(+), 34 deletions(-)
```

