# Laporan Eksekusi Langkah 32 — Masukan Frontend: Bug Corong, Skema OpenAPI, Perbaikan Kecil, Dokumen Kontrak

> **Branch:** `fix/step32-masukan-fe`  
> **Tanggal:** 2026-11-01  
> **Komitmen:** Tidak mengubah atau menghapus struktur data eksisting; menambahkan field dan skema OpenAPI terstruktur untuk kebutuhan integrasi frontend.

---

## 1. Ringkasan Perubahan Berdasarkan Temuan Frontend

| No | Temuan Frontend | Masalah Semula | Solusi & Perubahan Backend |
|---|---|---|---|
| 1 | FE #14: Corong source_id tidak ada | Mengembalikan HTTP 500 saat `source_id` tidak ada di tabel `scraping_sources` | Mengembalikan HTTP 404 `HTTPException(404, "Sumber dokumen tidak ditemukan")` di `app/services/corong_service.py` & router |
| 2 | FE #12, #13: Harmonisasi ringkasan | `ringkasan.per_jenis` menghitung temuan mentah termasuk rujukan yang tidak lolos filter; tidak ada rincian yang disaring | Menghitung ulang `per_jenis` pada sisa temuan setelah penyaringan rujukan pada 3 jalur (fresh ML, cache hit, cache basi); menambahkan dict `disaring_rincian` (`temuan`, `rujukan`, `alternatif`, `lainnya`) sambil mempertahankan `disaring_backend` |
| 3 | FE #5: Pesan 403 izin akun | Respons 403 hanya memuat `detail.code` dan `detail.izin` | Menambahkan `detail.message: "Akun Anda tidak memiliki izin <IZIN> untuk aksi ini."` di `app/core/permissions.py` |
| 4 | FE #15: Filter failures tanpa sumber | Tidak ada filter untuk kegagalan unggah manual di `GET /api/v1/ingest/failures` | Menambahkan parameter query `tanpa_sumber: bool = False`; jika `tanpa_sumber=True` dan `source_id` disertakan bersamaan -> HTTP 422 |
| 5 | FE #18: Dokumen nonaktif di kategori | Tree dan detail kategori hanya menghitung dokumen aktif; DELETE 409 tidak memberi rincian status dokumen | Menambahkan `jumlah_dokumen_nonaktif` pada `CategoryTreeNode` & `CategoryDetailResponse`; respons 409 DELETE memuat `dokumen_aktif`, `dokumen_nonaktif`, dan pesan informatif |
| 6 | FE #21: Penanda kategori_manual | Field `kategori_manual` tidak muncul di pencarian dokumen, detail dokumen, maupun PATCH metadata | Mengekspor `kategori_manual` di dict `SearchService.search()`, `get_document_detail()`, dan router `documents.py` |
| 7 | FE #22: Respons PATCH metadata placement | Field `placement` null bila metadata belum cukup untuk penempatan fisik | Memberikan objek eksplisit `{"placed": false, "reason": "metadata_belum_cukup", "destination_path": None, "category_id": None}` jika field penempatan berubah namun metadata belum cukup |
| 8 | FE #16: Skema OpenAPI kosong `{}` | 5 endpoint tidak memiliki model OpenAPI (`POST /ml/harmonisasi/{id}`, `GET /dashboard/corong`, `GET /categories/tree`, `POST /categories/`, `PATCH /documents/{id}/metadata`) | Membuat model skema Pydantic (`app/schemas/corong.py`, `harmonisasi.py`, `category.py`, `document.py`) dengan `extra="allow"` dan response_model terpasang; kontrak disinkronkan via `build_api_contract.py` |
| 9 | FE #17: Cache corong in-memory 60s | Agregasi SQL 7 tabel di corong lambat saat diakses berulang | Cache in-memory berbasis `threading.Lock` dengan TTL 60 detik; parameter `segar: bool = False` untuk bypass cache |
| 10 | FE #6–#10: Sinkronisasi kontrak | Inkonsistensi dokumentasi terhadap implementasi kode | Sinkronisasi `docs/api/KONTRAK-API-FASE1.md` dengan fakta implementasi kode |

---

## 2. Hasil Pengujian F01–F15 (`test_step32_masukan_fe.py`)

| Kode | Nama Uji | Aspek yang Diuji | Status |
|---|---|---|---|
| F01 | `test_f01_corong_source_id_not_found` | `source_id` tidak ada mengembalikan 404 | PASSED |
| F02 | `test_f02_corong_source_id_exists` | `source_id` ada mengembalikan metrik per sumber dan `source_id` null mengembalikan total | PASSED |
| F03 | `test_f03_harmonisasi_ringkasan_and_disaring_rincian` | Fresh ML response: per_jenis dihitung ulang dan disaring_rincian terisi | PASSED |
| F04 | `test_f04_harmonisasi_from_cache_recomputes_per_jenis` | Cache hit harmonisasi tetap menghitung ulang per_jenis dan memuat disaring_rincian | PASSED |
| F05 | `test_f05_auth_active_forbidden_message` | 403 Forbidden memuat code, izin, dan pesan user-friendly | PASSED |
| F06 | `test_f06_failures_tanpa_sumber_and_422_on_conflict` | Filter tanpa_sumber=true memuat unggah manual, dan konflik dengan source_id menghasilkan 422 | PASSED |
| F07 | `test_f07_category_with_inactive_documents_tree_and_delete_409` | Kategori dengan dokumen nonaktif terlihat di tree & 409 DELETE memuat rincian | PASSED |
| F08 | `test_f08_documents_contain_kategori_manual` | Detail dan daftar dokumen memuat boolean `kategori_manual` | PASSED |
| F09 | `test_f09_patch_metadata_insufficient_returns_explicit_placement` | PATCH metadata tidak cukup menghasilkan objek placement `placed: false` | PASSED |
| F10 | `test_f10_patch_metadata_no_placement_fields_changed` | PATCH metadata tanpa field penempatan menghasilkan `placement: null` | PASSED |
| F11 | `test_f11_post_categories_model_compatibility` | POST dan PATCH kategori kompatibel dengan model Pydantic | PASSED |
| F12 | `test_f12_openapi_response_models_not_empty` | Kelima endpoint OpenAPI tidak lagi memiliki skema kosong `{}` | PASSED |
| F13 | `test_f13_harmonisasi_extra_allow_and_nullable_pembanding` | Harmonisasi mendukung extra fields dan nullable pembanding/penjelas | PASSED |
| F14 | `test_f14_corong_cache_and_segar_and_ttl` | Cache corong 60 detik bekerja dan `segar=true` me-refresh cache | PASSED |
| F15 | `test_f15_csv_corong_bom_and_total` | Ekspor CSV corong memuat UTF-8 BOM dan baris TOTAL | PASSED |

---

## 3. Potongan Skema OpenAPI

### 3.1 `POST /api/v1/ml/harmonisasi/{id}` (`HarmonisasiResponse`)
```json
"HarmonisasiResponse": {
  "properties": {
    "status": {
      "type": "string",
      "title": "Status"
    },
    "ringkasan": {
      "$ref": "#/components/schemas/HarmonisasiRingkasan"
    },
    "disaring_backend": {
      "type": "integer",
      "title": "Disaring Backend",
      "default": 0
    },
    "disaring_rincian": {
      "$ref": "#/components/schemas/HarmonisasiDisaringRincian"
    },
    "analisis_per_pasal": {
      "items": {
        "$ref": "#/components/schemas/HarmonisasiPasalAnalisis"
      },
      "type": "array",
      "title": "Analisis Per Pasal",
      "default": []
    },
    "cache": {
      "$ref": "#/components/schemas/HarmonisasiCacheInfo"
    }
  },
  "type": "object",
  "required": [
    "status",
    "ringkasan",
    "disaring_rincian",
    "cache"
  ],
  "title": "HarmonisasiResponse"
}
```

### 3.2 `GET /api/v1/dashboard/corong` (`CorongResponse`)
```json
"CorongResponse": {
  "properties": {
    "sumber": {
      "items": {
        "$ref": "#/components/schemas/CorongSourceMetrics"
      },
      "type": "array",
      "title": "Sumber",
      "default": []
    },
    "total": {
      "$ref": "#/components/schemas/CorongTotalMetrics"
    }
  },
  "type": "object",
  "required": [
    "total"
  ],
  "title": "CorongResponse"
}
```

---

## 4. Output Mentah Terminal

### 4.1 Pytest Step 32 (`test_step32_masukan_fe.py`)
```
PS C:\Hero\hero-backend> .\venv\Scripts\python.exe -m pytest tests/test_step32_masukan_fe.py -q
...............                                                          [100%]
============================== warnings summary ===============================
venv\Lib\site-packages\fastapi\testclient.py:1
  C:\Hero\hero-backend\venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

venv\Lib\site-packages\starlette\testclient.py:53
  C:\Hero\hero-backend\venv\Lib\site-packages\starlette\testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

tests/test_step32_masukan_fe.py::test_f06_failures_tanpa_sumber_and_422_on_conflict
  C:\Users\IBUCOMP\Downloads\hero-backend\venv\Lib\site-packages\anyio\_backends\_asyncio.py:1100: StarletteDeprecationWarning: 'HTTP_422_UNPROCESSABLE_ENTITY' is deprecated. Use 'HTTP_422_UNPROCESSABLE_CONTENT' instead.

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
15 passed, 3 warnings in 16.16s
```

### 4.2 Ruff Check
```
PS C:\Hero\hero-backend> .\venv\Scripts\ruff.exe check --select E9,F app scripts tests\test_step32_masukan_fe.py
All checks passed!
```

### 4.3 Seluruh Suite Pytest (`python -m pytest -q`)
```
PS C:\Hero\hero-backend> .\venv\Scripts\python.exe -m pytest -q
........................................................................ [ 12%]
.............................................s.......................... [ 25%]
........................................................................ [ 37%]
........................................................................ [ 50%]
........................................................................ [ 62%]
........................................................................ [ 75%]
........................................................................ [ 87%]
........................................................................ [100%]
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
  C:\Users\IBUCOMP\Downloads\hero-backend\venv\Lib\site-packages\anyio\_backends\_asyncio.py:1100: StarletteDeprecationWarning: 'HTTP_422_UNPROCESSABLE_ENTITY' is deprecated. Use 'HTTP_422_UNPROCESSABLE_CONTENT' instead.

tests/test_step13_articles.py::test_p09_migration_cleans_duplicates_and_creates_index
  C:\Hero\hero-backend\alembic\versions\c5d6e7f8a9b0_step28_kategori_manual.py:35: SADeprecationWarning: Empty parameter sequence passed to execute(). This use is deprecated and will raise an exception in a future SQLAlchemy release
    op.drop_column('documents', 'kategori_manual')

tests/test_step13_articles.py: 22 warnings
  C:\Hero\hero-backend\alembic\env.py:84: SADeprecationWarning: Empty parameter sequence passed to execute(). This use is deprecated and will raise an exception in a future SQLAlchemy release
    context.run_migrations()

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
575 passed, 1 skipped, 185 warnings in 819.79s (0:13:39)
```

### 4.4 Uji Live Lokal

#### 4.4.1 Curl Corong 404 pada `source_id=99999`
```
PS C:\Hero\hero-backend> curl.exe -s -o NUL -w "%{http_code}`n" "http://localhost:8000/api/v1/dashboard/corong?source_id=99999"
404
```

#### 4.4.2 Curl Ingest Failures tanpa sumber (`tanpa_sumber=true&limit=3`)
```
PS C:\Hero\hero-backend> curl.exe -s "http://localhost:8000/api/v1/ingest/failures?tanpa_sumber=true&limit=3"
{"total":3,"items":[{"id":12,"job_id":33,"original_filename":"uji_terkunci.pdf","source_url":null,"failure_type":"format_tidak_didukung","reason_code":"pdf_terenkripsi","message":"PDF terenkripsi (butuh kata sandi untuk dibuka).","is_retryable":false,"quarantine_path":null,"file_hash":"c1966b1303cd9cf16c76feb9bbc25a69f7bc7a42e7b560c0694b5e0ac402a156","file_size_bytes":828,"duplicate_of_document_id":null,"duplicate_of_document":null,"ingest_options":{"category_id":null,"document_role":"corpus_eksisting","access_classification":"publik"},"follow_up_status":"belum_ditangani","attempt_count":0,"last_retry_at":null,"last_retry_job_id":null,"resolved_document_id":null,"handled_by_user_id":null,"handling_note":null,"created_at":"2026-10-30T04:33:55.291470Z","updated_at":"2026-10-30T04:33:55.291470Z"},{"id":11,"job_id":33,"original_filename":"uji_rusak.pdf","source_url":null,"failure_type":"format_tidak_didukung","reason_code":"pdf_rusak","message":"PDF rusak atau tidak bisa dibuka: Stream has ended unexpectedly","is_retryable":false,"quarantine_path":null,"file_hash":"e16fa5d9b51928755db85b917f0297babaf22c7a47e97d9212adab56e61ba04e","file_size_bytes":8,"duplicate_of_document_id":null,"duplicate_of_document":null,"ingest_options":{"category_id":null,"document_role":"corpus_eksisting","access_classification":"publik"},"follow_up_status":"belum_ditangani","attempt_count":0,"last_retry_at":null,"last_retry_job_id":null,"resolved_document_id":null,"handled_by_user_id":null,"handling_note":null,"created_at":"2026-10-30T04:33:55.203086Z","updated_at":"2026-10-30T04:33:55.203086Z"},{"id":6,"job_id":15,"original_filename":"b04_fake.pdf","source_url":null,"failure_type":"format_tidak_didukung","reason_code":"format_tidak_didukung","message":"Isi berkas bukan PDF yang valid meskipun berekstensi .pdf.","is_retryable":false,"quarantine_path":null,"file_hash":"51e6d54ae2751e2624038cf7da96abb6a2229b6d357c64694d0192cefa27b5a7","file_size_bytes":66,"duplicate_of_document_id":null,"duplicate_of_document":null,"ingest_options":{"metadata":{"title":"b04 fake","release_date":null,"regulation_type":"POJK","regulation_number":null},"category_id":null,"document_role":"corpus_eksisting","access_classification":"publik"},"follow_up_status":"belum_ditangani","attempt_count":0,"last_retry_at":null,"last_retry_job_id":null,"resolved_document_id":null,"handled_by_user_id":null,"handling_note":null,"created_at":"2026-10-04T18:23:24.876872Z","updated_at":"2026-10-04T18:23:24.876872Z"}]}
```

#### 4.4.3 Curl Categories Tree
```
PS C:\Hero\hero-backend> curl.exe -s http://localhost:8000/api/v1/categories/tree
[{"id":7,"name":"Draft Kajian","parent_id":null,"auto_created":false,"document_count":0,"total_document_count":0,"jumlah_dokumen":0,"jumlah_dokumen_nonaktif":0,"classification_rule":null,"children":[]},{"id":23,"name":"KEPDIR","parent_id":null,"auto_created":true,"document_count":0,"total_document_count":2,"jumlah_dokumen":0,"jumlah_dokumen_nonaktif":0,"classification_rule":null,"children":[{"id":25,"name":"1993","parent_id":23,"auto_created":true,"document_count":1,"total_document_count":1,"jumlah_dokumen":1,"jumlah_dokumen_nonaktif":0,"classification_rule":null,"children":[]},{"id":24,"name":"1995","parent_id":23,"auto_created":true,"document_count":1,"total_document_count":1,"jumlah_dokumen":1,"jumlah_dokumen_nonaktif":0,"classification_rule":null,"children":[]}]},{"id":6,"name":"Lainnya","parent_id":null,"auto_created":false,"document_count":0,"total_document_count":0,"jumlah_dokumen":0,"jumlah_dokumen_nonaktif":0,"classification_rule":null,"children":[{"id":9,"name":"Tanpa Tahun","parent_id":6,"auto_created":true,"document_count":0,"total_document_count":0,"jumlah_dokumen":0,"jumlah_dokumen_nonaktif":0,"classification_rule":null,"children":[]}]},{"id":12,"name":"PADK","parent_id":null,"auto_created":true,"document_count":0,"total_document_count":21,"jumlah_dokumen":0,"jumlah_dokumen_nonaktif":0,"classification_rule":null,"children":[{"id":42,"name":"2014","parent_id":12,"auto_created":true,"document_count":1,"total_document_count":1,"jumlah_dokumen":1,"jumlah_dokumen_nonaktif":0,"classification_rule":null,"children":[]},{"id":31,"name":"2015","parent_id":12,"auto_created":true,"document_count":1,"total_document_count":1,"jumlah_dokumen":1,"jumlah_dokumen_nonaktif":0,"classification_rule":null,"children":[]},{"id":34,"name":"2017","parent_id":12,"auto_created":true,"document_count":1,"total_document_count":1,"jumlah_dokumen":1,"jumlah_dokumen_nonaktif":0,"classification_rule":null,"children":[]},{"id":32,"name":"2022","parent_id":12,"auto_created":true,"document_count":1,"total_document_count":1,"jumlah_dokumen":1,"jumlah_dokumen_nonaktif":0,"classification_rule":null,"children":[]},{"id":41,"name":"2024","parent_id":12,"auto_created":true,"document_count":1,"total_document_count":1,"jumlah_dokumen":1,"jumlah_dokumen_nonaktif":0,"classification_rule":null,"children":[]},{"id":14,"name":"2025","parent_id":12,"auto_created":true,"document_count":8,"total_document_count":8,"jumlah_dokumen":8,"jumlah_dokumen_nonaktif":0,"classification_rule":null,"children":[]},{"id":13,"name":"2026","parent_id":12,"auto_created":true,"document_count":8,"total_document_count":8,"jumlah_dokumen":8,"jumlah_dokumen_nonaktif":0,"classification_rule":null,"children":[]},{"id":21,"name":"Tanpa Tahun","parent_id":12,"auto_created":true,"document_count":0,"total_document_count":0,"jumlah_dokumen":0,"jumlah_dokumen_nonaktif":0,"classification_rule":null,"children":[]}]},{"id":26,"name":"PBI","parent_id":null,"auto_created":true,"document_count":0,"total_document_count":1,"jumlah_dokumen":0,"jumlah_dokumen_nonaktif":0,"classification_rule":null,"children":[{"id":35,"name":"1992","parent_id":26,"auto_created":true,"document_count":1,"total_document_count":1,"jumlah_dokumen":1,"jumlah_dokumen_nonaktif":0,"classification_rule":null,"children":[]},{"id":27,"name":"Tanpa Tahun","parent_id":26,"auto_created":true,"document_count":0,"total_document_count":0,"jumlah_dokumen":0,"jumlah_dokumen_nonaktif":0,"classification_rule":null,"children":[]}]},{"id":5,"name":"Peraturan Internal DPEA","parent_id":null,"auto_created":false,"document_count":0,"total_document_count":0,"jumlah_dokumen":0,"jumlah_dokumen_nonaktif":0,"classification_rule":null,"children":[]},{"id":1,"name":"POJK","parent_id":null,"auto_created":false,"document_count":2,"total_document_count":37,"jumlah_dokumen":2,"jumlah_dokumen_nonaktif":0,"classification_rule":null,"children":[{"id":37,"name":"2014","parent_id":1,"auto_created":true,"document_count":3,"total_document_count":3,"jumlah_dokumen":3,"jumlah_dokumen_nonaktif":0,"classification_rule":null,"children":[]},{"id":29,"name":"2015","parent_id":1,"auto_created":true,"document_count":3,"total_document_count":3,"jumlah_dokumen":3,"jumlah_dokumen_nonaktif":0,"classification_rule":null,"children":[]},{"id":39,"name":"2016","parent_id":1,"auto_created":true,"document_count":1,"total_document_count":1,"jumlah_dokumen":1,"jumlah_dokumen_nonaktif":0,"classification_rule":null,"children":[]},{"id":40,"name":"2020","parent_id":1,"auto_created":true,"document_count":1,"total_document_count":1,"jumlah_dokumen":1,"jumlah_dokumen_nonaktif":0,"classification_rule":null,"children":[]},{"id":30,"name":"2021","parent_id":1,"auto_created":true,"document_count":2,"total_document_count":2,"jumlah_dokumen":2,"jumlah_dokumen_nonaktif":0,"classification_rule":null,"children":[]},{"id":38,"name":"2022","parent_id":1,"auto_created":true,"document_count":2,"total_document_count":2,"jumlah_dokumen":2,"jumlah_dokumen_nonaktif":0,"classification_rule":null,"children":[]},{"id":8,"name":"2023","parent_id":1,"auto_created":true,"document_count":4,"total_document_count":4,"jumlah_dokumen":4,"jumlah_dokumen_nonaktif":0,"classification_rule":null,"children":[]},{"id":11,"name":"2024","parent_id":1,"auto_created":true,"document_count":2,"total_document_count":2,"jumlah_dokumen":2,"jumlah_dokumen_nonaktif":0,"classification_rule":null,"children":[]},{"id":10,"name":"2025","parent_id":1,"auto_created":true,"document_count":4,"total_document_count":4,"jumlah_dokumen":4,"jumlah_dokumen_nonaktif":0,"classification_rule":null,"children":[]},{"id":16,"name":"2026","parent_id":1,"auto_created":true,"document_count":13,"total_document_count":13,"jumlah_dokumen":13,"jumlah_dokumen_nonaktif":0,"classification_rule":null,"children":[]},{"id":20,"name":"Tanpa Tahun","parent_id":1,"auto_created":true,"document_count":0,"total_document_count":0,"jumlah_dokumen":0,"jumlah_dokumen_nonaktif":0,"classification_rule":null,"children":[]}]},{"id":4,"name":"PP","parent_id":null,"auto_created":false,"document_count":0,"total_document_count":0,"jumlah_dokumen":0,"jumlah_dokumen_nonaktif":0,"classification_rule":null,"children":[]},{"id":2,"name":"SEOJK","parent_id":null,"auto_created":false,"document_count":0,"total_document_count":11,"jumlah_dokumen":0,"jumlah_dokumen_nonaktif":0,"classification_rule":null,"children":[{"id":33,"name":"2016","parent_id":2,"auto_created":true,"document_count":2,"total_document_count":2,"jumlah_dokumen":2,"jumlah_dokumen_nonaktif":0,"classification_rule":null,"children":[]},{"id":19,"name":"2023","parent_id":2,"auto_created":true,"document_count":2,"total_document_count":2,"jumlah_dokumen":2,"jumlah_dokumen_nonaktif":0,"classification_rule":null,"children":[]},{"id":18,"name":"2024","parent_id":2,"auto_created":true,"document_count":2,"total_document_count":2,"jumlah_dokumen":2,"jumlah_dokumen_nonaktif":0,"classification_rule":null,"children":[]},{"id":17,"name":"2025","parent_id":2,"auto_created":true,"document_count":5,"total_document_count":5,"jumlah_dokumen":5,"jumlah_dokumen_nonaktif":0,"classification_rule":null,"children":[]},{"id":15,"name":"2027","parent_id":2,"auto_created":true,"document_count":0,"total_document_count":0,"jumlah_dokumen":0,"jumlah_dokumen_nonaktif":0,"classification_rule":null,"children":[]},{"id":22,"name":"Tanpa Tahun","parent_id":2,"auto_created":true,"document_count":0,"total_document_count":0,"jumlah_dokumen":0,"jumlah_dokumen_nonaktif":0,"classification_rule":null,"children":[]}]},{"id":3,"name":"UU","parent_id":null,"auto_created":false,"document_count":0,"total_document_count":1,"jumlah_dokumen":0,"jumlah_dokumen_nonaktif":0,"classification_rule":null,"children":[{"id":36,"name":"2012","parent_id":3,"auto_created":true,"document_count":1,"total_document_count":1,"jumlah_dokumen":1,"jumlah_dokumen_nonaktif":0,"classification_rule":null,"children":[]},{"id":28,"name":"Tanpa Tahun","parent_id":3,"auto_created":true,"document_count":0,"total_document_count":0,"jumlah_dokumen":0,"jumlah_dokumen_nonaktif":0,"classification_rule":null,"children":[]}]}]
```

#### 4.4.4 Smoke Test Fase 2
```
PS C:\Hero\hero-backend> .\venv\Scripts\python.exe scripts/smoke_fase2.py --base-url http://localhost:8000
====================================================================================
       HERO BACKEND SMOKE TEST FASE 2 - http://localhost:8000
       Revisi Alembic Diharapkan: c5d6e7f8a9b0
       Autentikasi: Tidak ada HERO_SMOKE_TOKEN (mode anonim/dev)
====================================================================================
====================================================================================
Kode   | Cek                                      | Status   | Keterangan
------------------------------------------------------------------------------------
S01    | GET /health                              | OK       | rev=c5d6e7f8a9b0
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
S14    | GET /api/v1/audit-logs                   | LEWATI   | Belum ada entri audit RUN_ANALYSIS
S15    | Penjaga non-publik                       | OK       | doc_id=64 ditolak 403 saat auth mati
S16    | GET /api/v1/dashboard/summary            | OK       | belum_berlaku=0
S17    | GET /api/v1/dashboard/corong             | OK       | sumber=5, di_kb=92, terbaca=0 (0.0%)
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

### 4.5 Git Diff Stat terhadap `main`
```
PS C:\Hero\hero-backend> git diff main --stat
 app/core/permissions.py          |    1 +
 app/routers/categories.py        |   45 +-
 app/routers/dashboard.py         |   27 +-
 app/routers/documents.py         |   63 +-
 app/routers/ingest.py            |    8 +
 app/routers/ml_gateway.py        |   81 +-
 app/schemas/__init__.py          |   42 +
 app/schemas/category.py          |   44 +
 app/schemas/corong.py            |   51 +
 app/schemas/document.py          |   28 +
 app/schemas/harmonisasi.py       |   60 +
 app/services/category_service.py |   28 +-
 app/services/corong_service.py   |   97 +-
 app/services/failure_service.py  |   19 +-
 app/services/search_service.py   |    1 +
 docs/api/KONTRAK-API-FASE1.md    |   93 +-
 docs/api/openapi-fase1.json      | 2517 +++++++++++++++++++++++++++++---------
 docs/reports/step32-report.md    |  300 +++++
 scripts/tarik_semua.py           |    5 +-
 tests/conftest.py                |    2 +
 tests/test_step32_masukan_fe.py  |  696 +++++++++++
 21 files changed, 3536 insertions(+), 672 deletions(-)
```

### 4.6 Tiga Commit Terakhir di Branch
```
PS C:\Hero\hero-backend> git log --oneline -3
a0864fd chore(backend): Langkah 31 - skrip tarik semua hasil scan ke KB
788acd7 docs(step31): placeholder domain dan langkah scan ulang sebelum tarik semua
a0e6d70 chore: skrip tarik semua hasil scan ke KB (dry-run default) untuk persiapan UAT
```

---
*Laporan disusun lengkap sebelum commit. Seluruh perubahan diverifikasi bersih dan memenuhi aturan integrasi kompatibilitas ke belakang.*
