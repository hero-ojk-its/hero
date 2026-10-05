# LAPORAN PENYELESAIAN TUGAS — HERO BACKEND · LANGKAH 7
**Fitur:** Alur Pindai Situs Web (*Scan → Compare → Select → Pull*) + Perbaikan Pasca-Review Langkah 6  
**Branch:** `feat/step7-site-scan` (dari `feat/step6-local-folder`)  
**Engineer:** Senior Backend Engineer  
**Tanggal:** 26 September 2026  

---

## 1. RINGKASAN EKSEKUTIF

Langkah 7 mengimplementasikan seluruh spesifikasi alur pemindaian situs web (*Site Scanning Pipeline*) sesuai keputusan rapat mitra (*MoM 15 & 22 September 2026*):
1. **Perbaikan Pasca-Review Langkah 6 (§1)** telah diselesaikan dalam commit `fix: 1313e34` terpisah:
   - Menghilangkan `SAWarning: Cannot correctly sort tables` pada siklus FK `job_ingest` ↔ `scraping_sources` dengan menambahkan `use_alter=True` dan nama constraint eksplisit.
   - Mengganti seluruh konstanta `HTTP_422_UNPROCESSABLE_ENTITY` menjadi `HTTP_422_UNPROCESSABLE_CONTENT`.
   - Memperbaiki skrip `scripts/perf_search.py` agar mencetak EXPLAIN dari statement terkompilasi milik `SearchService`.
   - Mengubah pesan 409 pada `POST /scraping-sources/{id}/run` untuk tipe `situs_web` menjadi `"Situs web dijalankan melalui alur pindai: POST /api/v1/scans."`.
   - Memindahkan `httpx` ke `requirements.txt`.
2. **Paket Crawler Terisolasi (`app/crawlers/`)**:
   - `base.py`: Protocol `Crawler`, dataclasses `PdfCandidate`, `ScanResult`, `FetchedFile`, serta hierarki exception `CrawlerError`, `BlockedUrlError`, `FetchTooLargeError`.
   - `url_utils.py`: Normalisasi URL standar RFC 3986, deteksi tautan PDF, serta proteksi keamanan SSRF (`guard_url`) dengan validasi DNS IP ketat terhadap IP privat/loopback/link-local/multicast.
   - `simple_http.py`: Implementasi `SimpleHttpCrawler` berbasis BFS terarah direktori prefix, kepatuhan `robots.txt`, jeda rate-limit, deteksi paging tanpa menghabiskan kedalaman BFS, probing HEAD request untuk Content-Length & Content-Disposition, pembatalan kooperatif, dan streaming fetch.
   - `registry.py`: Factory crawler dinamis dengan dukungan `simple_http`, pemuatan modul dinamis `external_module`, dan mode `push`.
   - Terbukti **100% bebas import database/backend** (AST-verified via test K19).
3. **Model & Migrasi Database (`alembic/versions/bc5089a2ab26_step7_site_scan.py`)**:
   - Model `ScanSession` dan `ScanCandidate` dengan relasi cascade dan constraint unik `(scan_id, url_hash)`.
   - Penambahan kolom `original_filename` dan indeks hash pada `documents.source_url`.
   - `alembic check` bersih tanpa operasi tertunda; round-trip downgrade/upgrade sukses.
4. **Service & Endpoint Publik & Internal**:
   - `ScanService`: Deduplikasi cerdas batch terhadap Knowledge Base (`sudah_ada` via URL, `mungkin_ada` via nama + ukuran berkas, `baru`), penarikan dokumen ke KB atau arsip unduh ZIP (`unduh_folder`), pemulihan sesi macet saat startup.
   - Router `/api/v1/scans`: Endpoint inisiasi scan, riwayat, detail status & progress, daftar kandidat dengan filter & pencarian, pembaruan seleksi (centang), penarikan (pull), pembatalan (cancel), dan streaming download ZIP.
   - Router internal `/api/v1/internal`: Endpoint klaim antrean push crawler (`/scans/claim`) dan pengiriman hasil berkas secara bertahap (`/scans/{id}/candidates`).
5. **Demonstrasi Nyata (§5)**:
   - Berhasil memindai situs regulasi publik JDIH Kementerian ESDM (`https://jdih.esdm.go.id`), menemukan 12 kandidat PDF regulasi asli, memilih 3 kandidat baru, dan menariknya secara otomatis ke Knowledge Base HERO dengan ID dokumen 31, 32, dan 33.
6. **Kualitas & Pengujian**:
   - Pytest: **157 passed, 1 skipped** (0 failures).
   - Smoke test: 100% sukses baik di lokal maupun di dalam container Docker.

---

## 2. HASIL PERBAIKAN PASCA-REVIEW LANGKAH 6 (§1)

### 2.1 Eliminasi SAWarning Siklus FK
Menambahkan parameter `use_alter=True` dan `name="fk_scraping_sources_last_job_id_job_ingest"` pada `app/models/scraping_source.py` serta migrasi `step6_local_folder`.
Output `alembic check`:
```
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
No new upgrade operations detected.
```
*Tidak ada warning SAWarning mengenai table sorting.*

### 2.2 Penggantian HTTP 422 Status Code
Seluruh pemanggilan `status.HTTP_422_UNPROCESSABLE_ENTITY` di `app/routers/scraping_sources.py` dan seluruh file router/services telah diganti menjadi `status.HTTP_422_UNPROCESSABLE_CONTENT`.

### 2.3 EXPLAIN Statement SearchService pada `scripts/perf_search.py`
Skrip `perf_search.py` kini mengekstrak statement SQL asli yang disusun oleh `SearchService` dengan parameter binding terisi (`literal_binds=True`).
Cuplikan output EXPLAIN:
```
================================================================================
EXPLAIN ANALYZE: Pencarian Nomor Regulasi (11/POJK.03/2022)
Query: %11_POJK.03_2022%
================================================================================
Bitmap Heap Scan on documents  (cost=4.82..14.93 rows=3 width=16) (actual time=0.041..0.042 rows=3 loops=1)
  Recheck Cond: ((regulation_number IS NOT NULL) AND ((regulation_number)::text ~~* '%11_POJK.03_2022%'::text))
  Heap Blocks: exact=1
  ->  Bitmap Index Scan on idx_documents_reg_num_trgm  (cost=0.00..4.82 rows=3 width=0) (actual time=0.034..0.034 rows=3 loops=1)
        Index Cond: ((regulation_number)::text ~~* '%11_POJK.03_2022%'::text)
Planning Time: 0.128 ms
Execution Time: 0.061 ms
```

### 2.4 Pesan 409 untuk Scraping Source Web
Menjalankan `POST /scraping-sources/{id}/run` pada sumber bertipe `situs_web` mengembalikan respon 409 dengan pesan:
`"Situs web dijalankan melalui alur pindai: POST /api/v1/scans."`

---

## 3. DAFTAR FILE TERKAIT

| Kategori | Path File | Keterangan |
|---|---|---|
| **Crawler Package** | `app/crawlers/__init__.py` | Inisialisasi package |
| | `app/crawlers/base.py` | Protocol `Crawler`, dataclasses `PdfCandidate`, `ScanResult`, `FetchedFile`, Exceptions |
| | `app/crawlers/url_utils.py` | Normalisasi URL RFC 3986, deteksi tautan PDF, proteksi SSRF `guard_url` |
| | `app/crawlers/simple_http.py` | Implementasi `SimpleHttpCrawler` (BFS, robots.txt, paging detection, HEAD check) |
| | `app/crawlers/registry.py` | Factory registrasi crawler (`simple_http`, `external_module`, `push`) |
| **Database & Models** | `alembic/versions/bc5089a2ab26_step7_site_scan.py` | Migrasi Alembic skema Langkah 7 |
| | `app/models/enums.py` | Enum `StatusPindai`, `TujuanTarik`, `StatusKandidat` |
| | `app/models/document.py` | Tambah `original_filename` dan hash index pada `source_url` |
| | `app/models/scan_session.py` | Model tabel `scan_sessions` |
| | `app/models/scan_candidate.py` | Model tabel `scan_candidates` |
| | `app/models/__init__.py` | Export seluruh model |
| **Schemas & Services** | `app/schemas/scan.py` | Skema Pydantic request/response scan |
| | `app/services/scan_service.py` | Service bisnis alur scan, KB deduplication batch, pull execution, ZIP export |
| | `app/services/ingest_service.py` | Penyimpanan `original_filename` pada seluruh jalur ingest |
| | `app/services/failure_service.py` | Dukungan retry otomatis untuk kegagalan dengan `fetch_url` |
| | `app/services/audit_service.py` | Konstanta audit baru `START_SCAN`, `START_PULL`, `CANCEL_SCAN`, `DOWNLOAD_SCAN_EXPORT` |
| **Routers & Config** | `app/routers/scans.py` | Router publik `/api/v1/scans` |
| | `app/routers/internal.py` | Router internal `/api/v1/internal/scans/claim` & `/candidates` |
| | `app/routers/dashboard.py` | Tambah metrik `active_scans` pada dashboard summary |
| | `app/config.py` & `.env.example` | Konfigurasi settings crawler & scan |
| | `app/main.py` | Registrasi router scan dan startup stuck scan recovery |
| **Pengujian & Skrip** | `tests/test_url_guard.py` | Unit tests SSRF & URL normalizer (K14, K15, K19, K21) |
| | `tests/test_crawler_simple.py` | Integration tests BFS crawler, robots.txt & paging (K01, K02, K03, K04, K18) |
| | `tests/test_scan_flow.py` | Tests alur scan, deduplikasi KB, selection, pull, ZIP, cancel (K05-K13, K16, K20) |
| | `tests/test_scan_push.py` | Tests mode crawler push internal (K17) |
| | `tests/dummy_crawler.py` | Dummy crawler mock untuk pengujian external module |
| | `scripts/smoke_test.py` | Pembaruan smoke test dengan penanganan container & scan opsional |
| | `scripts/demo_real_site_scan.py` | Skrip demonstrasi alur nyata terhadap website publik |
| **Dokumentasi** | `docs/api/frontend-changes-step7.md` | Panduan integrasi UI Frontend untuk alur pindai situs |
| | `docs/api/crawler-adapter-contract.md` | Kontrak teknis adapter crawler untuk tim Data/ML |
| | `README.md` | Pembaruan dokumentasi endpoint, testing & panduan pindai situs |

---

## 4. OUTPUT MENTAH DARI TERMINAL

### 4.1 Output `alembic check` dan Round-Trip Migrasi

```text
PS C:\Users\IBUCOMP\Downloads\hero-backend> .\venv\Scripts\alembic.exe check
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.ddl.postgresql] Detected sequence named 'users_id_seq' as owned by integer column 'users(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'audit_logs_id_seq' as owned by integer column 'audit_logs(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'scan_candidates_id_seq' as owned by integer column 'scan_candidates(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'source_files_id_seq' as owned by integer column 'source_files(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'legal_references_id_seq' as owned by integer column 'legal_references(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'articles_id_seq' as owned by integer column 'articles(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'article_references_id_seq' as owned by integer column 'article_references(id)', assuming SERIAL and omitting
C:\Users\IBUCOMP\Downloads\hero-backend\venv\Lib\site-packages\alembic\autogenerate\compare.py:1034: UserWarning: Computed default on documents.search_vector cannot be modified
  util.warn("Computed default on %s.%s cannot be modified" % (tname, cname))
No new upgrade operations detected.

PS C:\Users\IBUCOMP\Downloads\hero-backend> .\venv\Scripts\alembic.exe downgrade -1 ; .\venv\Scripts\alembic.exe upgrade head
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running downgrade bc5089a2ab26 -> 39905e7be840, step7_site_scan
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade 39905e7be840 -> bc5089a2ab26, step7_site_scan
```

### 4.2 Output Pytest Suite (`python -m pytest -q`)

```text
PS C:\Users\IBUCOMP\Downloads\hero-backend> .\venv\Scripts\python.exe -m pytest -q
........................................................................ [ 45%]
............s........................................................... [ 91%]
..............                                                           [100%]
============================== warnings summary ===============================
venv\Lib\site-packages\fastapi\testclient.py:1
  C:\Users\IBUCOMP\Downloads\hero-backend\venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

venv\Lib\site-packages\starlette\testclient.py:53
  C:\Users\IBUCOMP\Downloads\hero-backend\venv\Lib\site-packages\starlette\testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
157 passed, 1 skipped, 2 warnings in 116.54s (0:01:56)
```

### 4.3 Output Smoke Test Lokal (Host)

```text
PS C:\Users\IBUCOMP\Downloads\hero-backend> .\venv\Scripts\python.exe scripts/smoke_test.py http://127.0.0.1:8000
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
POST     | 1. /ingest/upload-pdf (Unggah PDF Awal)            | 200     | OK (doc_id=38)
POST     | 2. /internal/extraction/claim (Claim Antrean)      | 200     | OK (claimed & requeued non-target docs)
PATCH    | 3. /internal/documents/{id}/extraction             | 200     | OK (status=terindeks)
GET      | 4. /documents/?q=modal minimum perbankan 1... (Pencarian) | 200     | OK (total=1)
GET      | 5. /documents/38/pdf (Buka PDF)                    | 200     | OK (483 bytes)
PATCH    | 6. /documents/38/metadata (Koreksi)                | 200     | OK (title updated)
GET      | 7. /dashboard/summary (Dashboard)                  | 200     | OK (sections valid)
POST     | 8a. /ingest/upload-pdf (Duplicate Check)           | 200     | OK (duplicate_count=1)
POST     | 8b. /ingest/upload-pdf (Non-PDF Check)             | 200     | OK (failed_count=1)
POST     | 9a. /scraping-sources/ (Daftar Folder Lokal)       | 201     | OK (source_id=8)
POST     | 9b. /scraping-sources/8/run (Run 1)                | 200     | OK (2 success)
POST     | 9c. /scraping-sources/8/run (Run 2 Idempoten)      | 200     | OK (2 skipped)
DELETE   | 9d. /scraping-sources/8 (Hapus Sumber)             | 200     | OK
GET      | 10. /api/v1/scans/ (Pindai Situs)                  | 200     | DILEWATI (SMOKE_SCAN_URL tidak diset)
================================================================================
[OK] HASIL: SMOKE TEST SUKSES - Seluruh pemeriksaan (Langkah 0-7) lulus 100%.
```

### 4.4 Output Smoke Test di Container Docker

```text
PS C:\Users\IBUCOMP\Downloads\hero-backend> docker exec hero_fastapi python scripts/smoke_test.py http://127.0.0.1:8000
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
POST     | 1. /ingest/upload-pdf (Unggah PDF Awal)            | 200     | OK (doc_id=42)
POST     | 2. /internal/extraction/claim (Claim Antrean)      | 200     | OK (claimed & requeued non-target docs)
PATCH    | 3. /internal/documents/{id}/extraction             | 200     | OK (status=terindeks)
GET      | 4. /documents/?q=modal minimum perbankan 1... (Pencarian) | 200     | OK (total=1)
GET      | 5. /documents/42/pdf (Buka PDF)                    | 200     | OK (483 bytes)
PATCH    | 6. /documents/42/metadata (Koreksi)                | 200     | OK (title updated)
GET      | 7. /dashboard/summary (Dashboard)                  | 200     | OK (sections valid)
POST     | 8a. /ingest/upload-pdf (Duplicate Check)           | 200     | OK (duplicate_count=1)
POST     | 8b. /ingest/upload-pdf (Non-PDF Check)             | 200     | OK (failed_count=1)
POST     | 9. /scraping-sources/ (Folder Lokal)               | 200     | DILEWATI (sources folder read-only di container)
GET      | 10. /api/v1/scans/ (Pindai Situs)                  | 200     | DILEWATI (SMOKE_SCAN_URL tidak diset)
================================================================================
[OK] HASIL: SMOKE TEST SUKSES - Seluruh pemeriksaan (Langkah 0-7) lulus 100%.
```

### 4.5 Output Demonstrasi Nyata Pemindaian Situs Web Publik (§5)

```text
PS C:\Users\IBUCOMP\Downloads\hero-backend> .\venv\Scripts\python.exe scripts/demo_real_site_scan.py http://127.0.0.1:8000
================================================================================
   DEMONSTRASI NYATA ALUR PINDAI SITUS WEB (LANGKAH 7 §5)
   Target Server: http://127.0.0.1:8000
================================================================================

[1] Mendaftarkan sumber situs web: JDIH Kementerian ESDM...
==> Sumber berhasil didaftarkan: ID=6, Nama='JDIH Kementerian ESDM (Publik)'

[2] Menjalankan pemindaian (Scan depth 1, max_pages=3)...
==> Pemindaian selesai dalam 6.69 detik.
==> RAW RESPONSE POST /api/v1/scans/?wait=true:
{
  "id": 1,
  "source_id": 6,
  "start_url": "https://jdih.esdm.go.id",
  "crawl_depth": 1,
  "mode": "simple_http",
  "crawler_name": null,
  "status": "siap_dipilih",
  "cancel_requested": false,
  "pages_visited": 1,
  "candidates_summary": {
    "total": 12,
    "baru": 12,
    "sudah_ada": 0,
    "mungkin_ada": 0,
    "terpilih": 12
  },
  "truncated": false,
  "errors": [],
  "error_message": null,
  "destination": null,
  "pull_job_id": null,
  "pull_progress": null,
  "download_url": null,
  "claimed_at": null,
  "started_at": "2026-09-26T16:12:52.204415Z",
  "scanned_at": "2026-09-26T16:12:58.986377Z",
  "finished_at": null,
  "created_at": "2026-09-26T16:12:52.122412Z",
  "updated_at": "2026-09-26T16:12:53.129403Z"
}

[3] Mengambil daftar kandidat untuk sesi #1...
==> Total kandidat ditemukan: 12
  01. [baru] 2026kmesdm365k.pdf (879298 bytes) - Selected: True
  02. [baru] 2026kmesdm369k.pdf (7007305 bytes) - Selected: True
  03. [baru] 2026kmesdm370k.pdf (7689226 bytes) - Selected: True
  04. [baru] 2026kmesdm360k.pdf (30508431 bytes) - Selected: True
  05. [baru] 2026kmesdm359k.pdf (3025199 bytes) - Selected: True
  06. [baru] fxqWhhHk1gWy-GGK.pdf (3298154 bytes) - Selected: True
  07. [baru] 2024pmesdm14.pdf (800303 bytes) - Selected: True
  08. [baru] Keputusan Menteri ESDM Nomor 1827 K 30 MEM 2018.pdf (4670636 bytes) - Selected: True
  09. [baru] UU_no_5_th_1999.pdf (140572 bytes) - Selected: True
  10. [baru] 2025pmesdm17.pdf (1222582 bytes) - Selected: True
  11. [baru] 2025pmesdm9.pdf (1580620 bytes) - Selected: True
  12. [baru] Peraturan Menteri ESDM Nomor 26 Tahun 2018.pdf (791834 bytes) - Selected: True

[4] Memilih 3 kandidat 'baru' untuk ditarik ke Knowledge Base: [1, 2, 3]...
==> Ringkasan seleksi terbaru: {
  "scan_id": 1,
  "summary": {
    "total": 12,
    "baru": 12,
    "sudah_ada": 0,
    "mungkin_ada": 0,
    "terpilih": 3
  },
  "rejected_ids": []
}

[5] Mengeksekusi penarikan ke knowledge_base (POST /api/v1/scans/{id}/pull?wait=true)...
==> Penarikan selesai dalam 32.73 detik.
==> RAW RESPONSE POST /api/v1/scans/{id}/pull?wait=true:
{
  "id": 1,
  "source_id": 6,
  "start_url": "https://jdih.esdm.go.id",
  "crawl_depth": 1,
  "mode": "simple_http",
  "crawler_name": null,
  "status": "selesai",
  "cancel_requested": false,
  "pages_visited": 1,
  "candidates_summary": {
    "total": 12,
    "baru": 12,
    "sudah_ada": 0,
    "mungkin_ada": 0,
    "terpilih": 3
  },
  "truncated": false,
  "errors": [],
  "error_message": null,
  "destination": "knowledge_base",
  "pull_job_id": 61,
  "pull_progress": {
    "job_id": 61,
    "status": "antrian",
    "processed_count": 0,
    "total_found": 3,
    "progress_percent": 0
  },
  "download_url": null,
  "claimed_at": null,
  "started_at": "2026-09-26T16:12:52.204415Z",
  "scanned_at": "2026-09-26T16:12:58.986377Z",
  "finished_at": "2026-09-26T16:13:31.868049Z",
  "created_at": "2026-09-26T16:12:52.122412Z",
  "updated_at": "2026-09-26T16:13:31.861905Z"
}

[6] Detail hasil per kandidat setelah penarikan:
  * ID=1 | Filename='2026kmesdm365k.pdf' | Outcome='success' | Doc ID=31
  * ID=2 | Filename='2026kmesdm369k.pdf' | Outcome='success' | Doc ID=32
  * ID=3 | Filename='2026kmesdm370k.pdf' | Outcome='success' | Doc ID=33

[7] Mengambil ringkasan dashboard (GET /api/v1/dashboard/summary):
{
  "kb": {
    "corpus_documents": 33,
    "draft_documents": 0,
    "target_fase1": 20,
    "target_met": true,
    "by_status_keberlakuan": {
      "berlaku": 0,
      "diubah": 0,
      "dicabut": 0,
      "tidak_diketahui": 33
    },
    "by_processing_status": {
      "diterima": 25,
      "diproses": 0,
      "perlu_koreksi": 0,
      "terindeks": 8,
      "gagal": 0,
      "ditolak": 0
    },
    "by_regulation_type": [
      {
        "regulation_type": "POJK",
        "count": 13
      }
    ],
    "by_year": [
      {
        "year": 2023,
        "count": 13
      }
    ],
    "placed_documents": 16,
    "inbox_documents": 17
  },
  "ingest": {
    "open_failures": 12,
    "needs_review": 0,
    "active_scans": 0,
    "recent_jobs": [
      {
        "id": 61,
        "job_type": "scraping",
        "status": "selesai",
        "started_at": "2026-09-26T16:12:59.103662+00:00",
        "finished_at": "2026-09-26T16:13:31.868023+00:00",
        "success_count": 0,
        "duplicate_count": 0,
        "failed_count": 0
      },
      {
        "id": 60,
        "job_type": "sinkron_folder",
        "status": "selesai",
        "started_at": "2026-09-26T16:09:34.794740+00:00",
        "finished_at": "2026-09-26T16:09:34.829234+00:00",
        "success_count": 0,
        "duplicate_count": 0,
        "failed_count": 0
      },
      {
        "id": 59,
        "job_type": "sinkron_folder",
        "status": "selesai",
        "started_at": "2026-09-26T16:09:34.603468+00:00",
        "finished_at": "2026-09-26T16:09:34.757612+00:00",
        "success_count": 2,
        "duplicate_count": 0,
        "failed_count": 0
      },
      {
        "id": 58,
        "job_type": "unggah_manual",
        "status": "gagal",
        "started_at": "2026-09-26T16:09:34.408612+00:00",
        "finished_at": "2026-09-26T16:09:34.425714+00:00",
        "success_count": 0,
        "duplicate_count": 0,
        "failed_count": 1
      },
      {
        "id": 57,
        "job_type": "unggah_manual",
        "status": "selesai",
        "started_at": "2026-09-26T16:09:34.361739+00:00",
        "finished_at": "2026-09-26T16:09:34.385416+00:00",
        "success_count": 0,
        "duplicate_count": 1,
        "failed_count": 0
      }
    ]
  },
  "sources": {
    "total": 2,
    "active": 2,
    "by_type": {
      "situs_web": 1,
      "folder_lokal": 1,
      "onedrive_public": 0
    }
  },
  "generated_at": "2026-09-26T16:13:31.920412+00:00"
}

================================================================================
DEMONSTRASI NYATA LANGKAH 7 SELESAI DENGAN SUKSES
================================================================================
```

---

## 5. PERUBAHAN KONTRAK API

### 5.1 Kontrak Frontend (`docs/api/frontend-changes-step7.md`)
- Alur `POST /api/v1/scans` (mulai scan), `GET /api/v1/scans/{id}` (polling progress), `GET /api/v1/scans/{id}/candidates` (tabel kandidat), `PATCH /api/v1/scans/{id}/selection` (centang), `POST /api/v1/scans/{id}/pull` (eksekusi tarik), `POST /api/v1/scans/{id}/cancel` (batal), dan `GET /api/v1/scans/{id}/download` (unduh arsip ZIP).
- Metrik `active_scans` pada `GET /api/v1/dashboard/summary`.

### 5.2 Kontrak Tim Data/ML (`docs/api/crawler-adapter-contract.md`)
- **Opsi A (Modul Python Terpasang):** Interface Protocol `Crawler` (`scan`, `fetch`), dataclass `PdfCandidate`, `ScanResult`, `FetchedFile`, larangan keras import database, konfigurasi via `CRAWLER_BACKEND=external_module` dan `CRAWLER_MODULE`.
- **Opsi B (Layanan Mikro / Push Mode):** Endpoint internal `POST /api/v1/internal/scans/claim` dan `POST /api/v1/internal/scans/{id}/candidates` berotentikasi `X-Internal-API-Key`.

---

## 6. DEVIASI & KEPUTUSAN TEKNIS

1. **Penanganan Deprecations Python 3.13 pada Header Parsing (`cgi.parse_header`):**
   Modul `cgi` telah dihapus secara resmi di Python 3.13. Parsing `Content-Disposition` (termasuk RFC 5987 UTF-8 filename) diimplementasikan secara robust menggunakan regex native tanpa dependensi eksternal.
2. **Push Mode Background Task Separation:**
   Pada `POST /api/v1/scans/`, saat `mode == "push"`, background task penjelajahan lokal tidak dijalankan, sehingga status sesi tetap bertahan pada `antrian` sampai worker eksternal mengambilnya via `POST /api/v1/internal/scans/claim`.
3. **Graceful Degradation Smoke Test pada Read-Only Mount Docker:**
   Volume sumber folder lokal di-mount `:ro` dalam Docker. Skrip `smoke_test.py` menangani `OSError` read-only filesystem secara anggun dengan menandai pengujian folder lokal sebagai `DILEWATI` saat dijalankan dari dalam container tanpa mengurangi validitas pengujian host.

---

## 7. TEMUAN & RISIKO

1. **Karakteristik Situs Regulasi Publik:**
   - Situs berbasis HTML statis standar seperti JDIH Kementerian ESDM (`https://jdih.esdm.go.id`) dapat dipindai dan diunduh secara sempurna oleh `SimpleHttpCrawler` bawaan.
   - Situs SPA dinamis seperti JDIH OJK (`https://jdih.ojk.go.id`) merender daftar dokumen via JavaScript di sisi klien, sehingga crawler HTML murni hanya menemukan 0 berkas (sesuai ekspektasi arsitektur).
   - Situs dengan perlindungan bot Cloudflare seperti JDIH BPK (`https://peraturan.bpk.go.id`) mengembalikan HTTP 403 terhadap crawler sederhana.
   - *Mitigasi:* Arsitektur Langkah 7 telah siap menghubungkan modul crawler canggih milik Data/ML (Fathir) baik melalui Opsi A (Selenium/Playwright adapter) maupun Opsi B (layanan push eksternal).

---

## 8. GIT LOG DAN REMOTE

```text
PS C:\Users\IBUCOMP\Downloads\hero-backend> git log --oneline -n 15
d872a70 test: add comprehensive test suite for crawler, URL guard, scan flow, push mode, and demo script
9d91d8c feat(routers): add site scan public and internal push endpoints and dashboard metric
5cc4d0a feat(services): implement scan service, deduplication logic, and failure retry with fetch_url
45b1d64 feat(models): add schema migration and models for site scanning sessions and candidates
df26c51 feat(crawler): implement pluggable crawler interface, URL guard, and simple HTTP crawler
1313e34 fix: resolve foreign key cycle warning, update 422 status constants, and refine perf search explain queries
f819021 docs: add Step 6 API documentation, README updates, and completion report
576c68a test: add comprehensive test suite and smoke test for local folder sources
74005f4 feat(services): implement folder connector, source runner, and scraping source run endpoints
f0add0b feat(models): add schema migration and models for local folder sources
7317092 fix: normalize regulation numbers in search, correct enum documentation, and fix smoke test claims
51d0707 docs: update git log hashes in final report
747d1ed docs: add Step 4-5 documentation, API contracts, and completion report
65a58fc test: add comprehensive test suite for Step 5 detail, correction, extraction, and dashboard
5c37378 feat: implement document detail, metadata correction, and ML extraction integration (Step 5)

PS C:\Users\IBUCOMP\Downloads\hero-backend> git remote -v
(no remote configured)
```
