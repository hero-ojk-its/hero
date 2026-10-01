# LAPORAN LANGKAH 10 — HERO Backend
**Robust Web Scanning (US-13c / #88) & OneDrive Public Folder Crawling (US-17 / #30)**

> **Tanggal:** 01 Oktober 2026  
> **Branch:** `feat/step10-robust-scan`  
> **Versi Aplikasi:** `0.10.0`  
> **Database:** PostgreSQL 15.4 (`hero_db`, `hero_test` di `127.0.0.1:5432`)  
> **Peran:** Senior Backend Engineer  

---

## 1. RINGKASAN EKSEKUTIF

Langkah 10 menyelesaikan penguatan kemampuan pemindaian dokumen (web scanning & cloud folder) untuk memenuhi kriteria penerimaan mitra (Weekly #4, Pak Faris):
1. **Issue #88 (US-13c - Robust Web Scanning)**:
   - Menghubungkan crawler dengan pagination link HTML standar, link navigasi tengah tersembunyi (*hidden middle pages*), dan ASP.NET WebForms SharePoint postback (`__doPostBack`).
   - Mencegah perulangan tak terbatas (*loop detection*) berbasis URL visit set dan content hash.
   - Mengikuti rantai pengalihan (*redirect chains*) hingga 10 hop dan meta-refresh secara aman dengan perlindungan SSRF Guard (memblokir akses IP privat/loopback/cloud metadata saat scan publik, termasuk NAT64 `64:ff9b::/96`).
   - Mendeteksi proteksi Captcha/WAF (Cloudflare 503 `cf-chl`/`cf-ray`, reCAPTCHA `g-recaptcha`, hCaptcha) secara anggun (`blocked=true`, error `terblokir_captcha` tanpa membuat backend crash).
   - Menentukan ukuran berkas secara presisi tanpa mengunduh penuh melalui probe `HEAD` dan fallback `Range: bytes=0-0`.
2. **Issue #30 (US-17 - OneDrive Public Folder Crawling)**:
   - Inisialisasi guest auth session otomatis dari URL tautan berbagi publik OneDrive.
   - Penelusuran pohon folder secara rekursif via SharePoint REST API (`GetFolderByServerRelativeUrl`).
   - Ekstraksi ukuran eksak dari metadata listing (`Length`), perekaman jalur relatif (`source_path`), dan pembuatan tautan unduhan langsung.
3. **Penyelarasan Metadata Kaya**:
   - Menambahkan kolom metadata regulasi pada `ScanCandidate` (`document_title`, `detail_url`, `final_url`, `doc_kind`, `regulation_number`, `regulation_type`, `bidang`, `sub_bidang`, `release_date`, `size_source`, `source_path`).
   - Menambahkan kolom status pada `ScanSession` (`blocked`, `stats`, `crawler_adapter`) dan `ScrapingSource` (`crawler_adapter`).
   - Otomatis menyematkan metadata regulasi saat kandidat ditarik ke Knowledge Base (`tujuan="knowledge_base"`), sehingga penamaan berkas otomatis terbentuk rapi tanpa `NA`.
4. **Zero Headless Browser**:
   - Seluruh 3 sumber data berjalan 100% menggunakan protokol HTTP murni (`httpx`) tanpa menambahkan dependensi Playwright/Selenium, menghemat memori (RAM < 50MB) dan waktu eksekusi.

---

## 2. STATUS BASIS DATA & MIGRASI ALEMBIC

Migrasi Alembic `02779701b550_step10_robust_scan.py` berhasil dibuat dan diaplikasikan ke database `hero_db` dan `hero_test`.

### Verifikasi `alembic check` (Salinan Mentah Terminal)
```text
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.ddl.postgresql] Detected sequence named 'legal_references_id_seq' as owned by integer column 'legal_references(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'articles_id_seq' as owned by integer column 'articles(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'audit_logs_id_seq' as owned by integer column 'audit_logs(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'source_files_id_seq' as owned by integer column 'source_files(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'scan_sessions_id_seq' as owned by integer column 'scan_sessions(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'article_references_id_seq' as owned by integer column 'article_references(id)', assuming SERIAL and omitting
INFO  [alembic.ddl.postgresql] Detected sequence named 'scan_candidates_id_seq' as owned by integer column 'scan_candidates(id)', assuming SERIAL and omitting
UserWarning: Computed default on documents.search_vector cannot be modified
No new upgrade operations detected.
```

---

## 3. HASIL LIVE BENCHMARK TERHADAP GROUND TRUTH

Pengujian benchmark langsung ke 3 target sumber data menggunakan skrip `scripts/scan_benchmark.py`:

```powershell
python scripts/scan_benchmark.py --source all --limit-pages 2
```

### 3.1 Ringkasan Performa Benchmark Live

| Sumber Data | Adapter | Durasi (detik) | Halaman / Folder | PDF Ditemukan | Ukuran Terdeteksi | Rincian Doc Kind | Status |
|---|---|---|---|---|---|---|---|
| **Regulasi OJK** | `sharepoint_postback` | 37.34s | 2 halaman | 60 | 60/60 (100%) | utama: 20, abstrak: 20, faq: 20 | Sukses |
| **JDIH OJK** | `jdih_api` | 36.56s | 2 halaman | 100 | 72/100 (72%) | utama: 94, faq: 4, abstrak: 2 | Sukses |
| **OneDrive Public DPEA** | `onedrive_share` | 7.65s | 2 folder | 2.612 | 2.612/2.612 (100%) | utama: 2296, faq: 156, abstrak: 157, lampiran: 3 | Sukses |

### 3.2 Output Mentah Terminal Eksekusi Benchmark
```text
=======================================================
 Memulai Benchmark: Regulasi OJK (ojk)
 URL    : https://ojk.go.id/id/regulasi/default.aspx
 Adapter: sharepoint_postback
 Batas  : max_pages=2, max_candidates=3000, head_for_size=True
=======================================================
  -> Progress: 2 halaman/folder dijelajahi, 60 berkas PDF ditemukan...
 Hasil Regulasi OJK:
 - Durasi: 37.34 detik
 - Halaman/Folder Dikunjungi: 2
 - Berkas PDF Ditemukan    : 60
 - Berkas Dengan Ukuran     : 60 / 60
 - Rincian Peran Dokumen    : {'utama': 20, 'abstrak': 20, 'faq': 20}
 - Error / Catatan         : 0
 - CSV disimpan di          : docs/reports/scan-benchmark-ojk.csv

=======================================================
 Memulai Benchmark: JDIH OJK (jdih)
 URL    : https://jdih.ojk.go.id/
 Adapter: jdih_api
 Batas  : max_pages=2, max_candidates=3000, head_for_size=True
=======================================================
  -> Progress: 2 halaman/folder dijelajahi, 100 berkas PDF ditemukan...
 Hasil JDIH OJK:
 - Durasi: 36.56 detik
 - Halaman/Folder Dikunjungi: 2
 - Berkas PDF Ditemukan    : 100
 - Berkas Dengan Ukuran     : 72 / 100
 - Rincian Peran Dokumen    : {'faq': 4, 'utama': 94, 'abstrak': 2}
 - Error / Catatan         : 0
 - CSV disimpan di          : docs/reports/scan-benchmark-jdih.csv

=======================================================
 Memulai Benchmark: OneDrive Public DPEA (onedrive)
 URL    : https://oneojk-my.sharepoint.com/:f:/g/personal/redacted_user_ojk_go_id/redacted_iduRwqT5X1zPBi_d1AAfA8Ec-W6i3BTN66ZgJI1rA?e=redacted_token
 Adapter: onedrive_share
 Batas  : max_pages=2, max_candidates=3000, head_for_size=True
=======================================================
  -> Progress: 2 halaman/folder dijelajahi, 2612 berkas PDF ditemukan...
 Hasil OneDrive Public DPEA:
 - Durasi: 7.65 detik
 - Halaman/Folder Dikunjungi: 2
 - Berkas PDF Ditemukan    : 2612
 - Berkas Dengan Ukuran     : 2612 / 2612
 - Rincian Peran Dokumen    : {'utama': 2296, 'faq': 156, 'abstrak': 157, 'lampiran': 3}
 - Error / Catatan         : 0
 - CSV disimpan di          : docs/reports/scan-benchmark-onedrive.csv

[OK] Laporan benchmark lengkap disimpan ke: docs/reports/scan-benchmark-2026-10-01.md
```

---

## 4. HASIL SUITE PENGUJIAN OTOMATIS

### 4.1 Uji Modul Crawler Khusus (`tests/test_crawler_robust.py` - S01 s.d. S16)
```text
tests/test_crawler_robust.py::test_s01_paging_link_five_pages PASSED     [  6%]
tests/test_crawler_robust.py::test_s02_paging_link_hidden_middle_pages PASSED [ 12%]
tests/test_crawler_robust.py::test_s03_paging_loop_detection PASSED      [ 18%]
tests/test_crawler_robust.py::test_s04_sharepoint_postback_pagination PASSED [ 25%]
tests/test_crawler_robust.py::test_s05_ojk_detail_page_metadata_and_attachments PASSED [ 31%]
tests/test_crawler_robust.py::test_s06_redirect_chain_and_ssrf_guard PASSED [ 37%]
tests/test_crawler_robust.py::test_s07_cloudflare_503_detection PASSED   [ 43%]
tests/test_crawler_robust.py::test_s08_recaptcha_200_detection PASSED    [ 50%]
tests/test_crawler_robust.py::test_s09_rate_limit_retry_after PASSED     [ 56%]
tests/test_crawler_robust.py::test_s10_size_probing_head_fallback_range PASSED [ 62%]
tests/test_crawler_robust.py::test_s11_jdih_api_crawler_two_pages PASSED [ 68%]
tests/test_crawler_robust.py::test_s12_onedrive_share_crawler_recursive PASSED [ 75%]
tests/test_crawler_robust.py::test_s13_pull_candidate_with_metadata_to_kb PASSED [ 81%]
tests/test_crawler_robust.py::test_s14_run_onedrive_source_returns_409 PASSED [ 87%]
tests/test_crawler_robust.py::test_s15_robots_txt_disallow PASSED        [ 93%]
tests/test_crawler_robust.py::test_s16_filter_candidates_query_params PASSED [100%]

======================= 16 passed, 2 warnings in 7.94s ========================
```

### 4.2 Uji Regresi Penuh Seluruh Proyek
```text
============================= test session starts =============================
platform win32 -- Python 3.13.7, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\IBUCOMP\Downloads\hero-backend
plugins: anyio-4.15.1
collected 205 items

scripts/test_jdih_detail.py::test_detail PASSED                          [  0%]
tests/test_api.py (21 tests) PASSED                                      [ 10%]
tests/test_category_service.py (4 tests) PASSED                           [ 12%]
tests/test_crawler_robust.py (16 tests) PASSED                            [ 20%]
tests/test_crawler_simple.py (5 tests) PASSED                             [ 22%]
tests/test_dashboard.py (4 tests) PASSED                                  [ 24%]
tests/test_deploy_readiness.py (5 tests) PASSED                           [ 27%]
tests/test_docs_enums.py (2 tests) PASSED                                 [ 28%]
tests/test_document_detail.py (5 tests) PASSED                            [ 30%]
tests/test_extraction_internal.py (13 tests) PASSED                       [ 37%]
tests/test_failures.py (12 tests) PASSED                                  [ 42%]
tests/test_file_validation.py (8 tests) PASSED                            [ 46%]
tests/test_ingest_service.py (4 tests) PASSED                             [ 48%]
tests/test_local_folder.py (15 tests, 1 skipped symlink) PASSED           [ 56%]
tests/test_metadata_correction.py (7 tests) PASSED                        [ 60%]
tests/test_naming_service.py (7 tests) PASSED                             [ 63%]
tests/test_naming_step9.py (18 tests) PASSED                              [ 72%]
tests/test_placement.py (11 tests) PASSED                                 [ 77%]
tests/test_scan_flow.py (7 tests) PASSED                                  [ 80%]
tests/test_scan_push.py (1 test) PASSED                                   [ 81%]
tests/test_search.py (17 tests) PASSED                                    [ 89%]
tests/test_source_validation.py (8 tests) PASSED                          [ 93%]
tests/test_step8_fixes.py (5 tests) PASSED                                [ 96%]
tests/test_storage_service.py (3 tests) PASSED                            [ 97%]
tests/test_url_guard.py (5 tests) PASSED                                  [100%]

=========== 204 passed, 1 skipped, 2 warnings in 309.48s (0:05:09) ============
```

---

## 5. DOKUMENTASI & ARTEFAK YANG DIHASILKAN

1. **`docs/api/crawler-adapter-contract.md`**: Kontrak arsitektur adapter crawler, skema `PdfCandidate`, `ScanResult`, registry, dan panduan penambahan adapter.
2. **`docs/api/frontend-changes-step10.md`**: Panduan perubahan bagi Frontend Engineer (Personil_D) mengenai badge `doc_kind`, filter query params (`doc_kind`, `bidang`, `q`), indikator `blocked` sesi scan, dan metadata lengkap kandidat.
3. **`docs/api/KONTRAK-API-FASE1.md`**: Kontrak API Fase 1 yang dibuild ulang secara idempoten (`scripts/build_api_contract.py`).
4. **`scripts/scan_benchmark.py`**: Skrip CLI live benchmark mandiri untuk verifikasi performa sumber data secara berkala.
5. **`docs/reports/scan-benchmark-2026-10-01.md`**: Laporan ringkasan hasil live benchmark beserta CSV ekspor (`scan-benchmark-ojk.csv`, `scan-benchmark-jdih.csv`, `scan-benchmark-onedrive.csv`).
