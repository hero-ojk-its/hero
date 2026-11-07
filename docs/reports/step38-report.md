# Laporan Langkah 38 — Temuan QA & Persiapan UAT

Tanggal: 7 November 2026  
Branch: `fix/step38-qa-uat`  
Basis: `main` (commit `69ec2e7 Merge branch 'fix/step37-tarik-utama' into main`)  

---

## 1. Ringkasan Temuan QA Hamdan & Solusi Teknis (Butir 1–6)

### Butir 1: Asal Status Keberlakuan (`status_source`) & Graf Relasi
- **Masalah QA**: Pada `GET /documents/{id}/versi`, field `status_source` selalu bernilai `null` dan seluruh relasi kosong (#211 "dicabut" tapi `dicabut_oleh` kosong).
- **Akar Masalah**: Dokumen hasil penarikan scan / ingest metadata mengisi `status_keberlakuan` dari sumber tanpa menetapkan `status_source = "sumber"`. Selain itu, relasi regulasi hanya ada di DB jika disinkronkan oleh lapisan data/ML melalui `POST /internal/relations`.
- **Tindakan**:
  1. `app/services/ingest_service.py` & `app/routers/ingest.py`: Saat dokumen dibuat/di-ingest dan `status_keberlakuan != tidak_diketahui`, field `status_source` otomatis diisi `"sumber"`.
  2. `app/services/version_service.py` (`recompute_status`): Menetapkan urutan prioritas resmi: `manual` > `relasi` / `lapisan_data` / `tanggal_berlaku` > `sumber`. Status dari `"sumber"` boleh ditimpa oleh relasi atau tanggal berlaku, tetapi **tidak** dikembalikan ke `tidak_diketahui` oleh aturan penghapusan relasi (`relasi_dihapus`).
  3. `app/routers/documents.py` & `app/services/version_service.py`: Menambahkan field pada `GET /documents/{id}/versi`:
     - `status_keterangan`: Kalimat penjelas berbahasa Indonesia (`manual` → "Diubah manual oleh admin", `relasi` → "Dihitung dari relasi antarperaturan", `tanggal_berlaku` → "Dihitung dari tanggal berlaku", `sumber` → "Mengikuti status di situs sumber", `null` → "Belum diketahui").
     - `jumlah_relasi`: Total relasi masuk dan keluar yang ditemukan untuk `identity_key` dokumen (0 jika nihil).
     - `identity_key_kosong`: `true` bila dokumen belum memiliki `identity_key` (relasi tidak dapat dicocokkan), `false` jika terisi.
  4. Skrip `scripts/backfill_status_source.py`: Meninjau (dry-run) dan memperbarui (`--apply`) dokumen berstatus non-`tidak_diketahui` yang memiliki `status_source IS NULL` menjadi `"sumber"`, dengan pencatatan audit log `UPDATE_DOCUMENT_STATUS` (`detail.alasan = "langkah38_backfill_status_source"`).
  5. Pembaruan kontrak API `docs/api/KONTRAK-API-FASE1.md` Bagian 8.4 mencatat dependensi sinkronisasi relasi dari lapisan data (`POST /internal/relations`).

### Butir 2: Batas Ukuran Unggah Manual vs Unduh Scan
- **Masalah QA**: Berkas PDF berukuran 26 MB lolos masuk ke Knowledge Base (#90), padahal batas unggah yang diharapkan adalah 25 MB.
- **Akar Masalah**: `MAX_UPLOAD_MB` sebelumnya bernilai 100 MB dan digunakan bersama baik untuk unggah manual pengguna maupun penarikan web crawler.
- **Tindakan**:
  1. Memisahkan konfigurasi di `app/config.py`:
     - `max_upload_mb: int = 25` (property `max_upload_bytes` = 25 * 1024 * 1024): Batas unggah manual (`POST /ingest/upload-pdf`) dan retry kegagalan unggahan manual.
     - `max_fetch_mb: int = 100` (property `max_fetch_bytes` = 100 * 1024 * 1024): Batas unduhan penarikan crawling/scan, runner folder lokal, dan retry unduh URL.
  2. Memperbarui `.env.example` dan `.env.prod.example` dengan dokumentasi batasan baru tersebut.
  3. Berkas > 25 MB yang diunggah manual ditolak dengan kode `FileRejectCode.ukuran_melebihi_batas`, pesan berbahasa Indonesia yang menyebutkan batas 25 MB, dan tidak ada baris dokumen yang dibuat di basis data.

### Butir 3: Duplikat Identitas di Ringkasan Job
- **Masalah QA**: Ringkasan hasil unggah menulis "Duplikat 0", padahal dokumen duplikatnya (#88) dinonaktifkan.
- **Akar Masalah**: Kolom `duplicate_count` pada `JobIngest` hanya menghitung duplikat berkas fisik (hash SHA-256) saat awal ingest. Duplikat identitas (jenis, nomor, tahun) baru terdeteksi belakangan saat worker memproses ekstraksi identitas, lalu dokumen dinonaktifkan (`is_active = False`) tanpa memperbarui entitas `job_ingest`.
- **Tindakan**:
  1. Pada respons `GET /api/v1/ingest/jobs/{job_id}` (`JobDetailResponse`) dan `GET /api/v1/ingest/jobs` (`JobListItemResponse`), ditambahkan field `duplikat_identitas_count: int`.
  2. Nilai dihitung secara dinamis dari jumlah dokumen non-aktif (`is_active == False`) yang terhubung dengan `job_id` tersebut yang memiliki `duplicate_of_id IS NOT NULL` atau `deactivated_reason` diawali `"duplikat_identitas"`.
  3. Nilai `duplicate_count` lama tetap dipertahankan untuk kompatibilitas balik (duplikat berkas instan saat ingest).

### Butir 4: Pesan PDF Rusak & Label Kegagalan
- **Masalah QA**: Berkas PDF rusak tampil berlabel "Format Tidak Didukung" dengan pesan error teknis Python/pypdf mentah ("Stream has ended unexpectedly").
- **Akar Masalah**: Galat pypdf diteruskan langsung ke pengguna, dan belum ada label bahasa Indonesia yang ramah pengguna untuk kegagalan ingest.
- **Tindakan**:
  1. `app/services/file_validation.py`: Galat pembacaan PDF rusak diformat menjadi pesan ramah pengguna: `"Berkas PDF rusak atau tidak lengkap sehingga tidak bisa dibuka. Unduh ulang atau minta berkas aslinya."`. Detail teknis pypdf dicatat pada log aplikasi internal (`logger.info`).
  2. `app/schemas/ingest.py`: Menambahkan helper `format_label_alasan(reason_code)` dan field `label_alasan: Optional[str]` pada schema respons `FailureResponse`, `JobFailureSummary`, dan `IngestItemDetailResponse`.
  3. Pemetaan label mencakup: `pdf_rusak` → "PDF rusak", `pdf_terenkripsi` → "PDF terkunci kata sandi", `ukuran_melebihi_batas` → "Ukuran melebihi batas", `halaman_kosong` → "Dokumen tidak memiliki halaman", `format_tidak_didukung` → "Format tidak didukung", dll.
  4. Berkas dengan `pdf_rusak` tetap berstatus `is_retryable = False` sehingga pengguna diarahkan mengunggah berkas baru.

### Butir 5: Header Charset UTF-8 pada Respons API
- **Masalah QA**: Respons API tidak menyertakan parameter `charset=utf-8` pada header `Content-Type`, sehingga karakter khusus seperti em-dash ("—") rusak saat ditampilkan di PowerShell / Windows.
- **Akar Masalah**: `FastAPI` / `JSONResponse` secara default menghasilkan `Content-Type: application/json` tanpa penegasan `charset=utf-8`.
- **Tindakan**:
  1. Membuat kelas respons kustom `Utf8JSONResponse` pada `app/responses.py` yang menetapkan header `Content-Type: application/json; charset=utf-8`.
  2. Mendaftarkan `default_response_class=Utf8JSONResponse` pada inisialisasi aplikasi FastAPI di `app/main.py`.
  3. Menambahkan middleware `ensure_utf8_charset` di `app/main.py` untuk memastikan setiap respons bertipe `application/json` secara konsisten menyertakan `; charset=utf-8`.
  4. Seluruh string multibyte/UTF-8 (termasuk em-dash "—") terkirim utuh.

### Butir 6: Dokumen Macet di Status `diproses`
- **Masalah QA**: 131 dokumen aktif berstatus `diproses` memiliki berkas fisik PDF di storage, namun panggilan ke ML Gateway menghasilkan 404 (tidak dapat diproses lebih lanjut).
- **Akar Masalah**: Klaim antrean ekstraksi (`/internal/extraction/claim`) mensyaratkan `extraction_attempts < EXTRACTION_MAX_ATTEMPTS`. Dokumen `diproses` yang klaimnya kedaluwarsa (> `EXTRACTION_CLAIM_TIMEOUT_MINUTES`) namun jumlah percobaannya sudah mencapai batas maksimal (>= 3) tidak akan pernah diklaim ulang oleh worker, sehingga terjebak selamanya di `diproses`.
- **Tindakan**:
  1. Memperluas skrip `scripts/periksa_konsistensi_pasal.py` dengan kategori **Kelompok D**: Dokumen aktif berstatus `diproses` dengan `extraction_claimed_at` lebih lampau dari timeout (atau `null`). Skrip menampilkan daftar dokumen dan menandai dokumen yang percobaannya sudah habis (`extraction_attempts >= EXTRACTION_MAX_ATTEMPTS`).
  2. Menambahkan opsi `--antrekan-ulang-macet`: Mengembalikan dokumen Kelompok D yang **memiliki berkas PDF** di storage ke status `diterima`, mengosongkan `extraction_claimed_at = None`, mereset `extraction_attempts = 0`, dan mencatat riwayat audit `EXTRACTION_REQUEUED` (`{"reason": "antrekan_ulang_macet", "attempt_sebelumnya": n}`).
  3. Dokumen tanpa berkas PDF di storage dilewati dari antre ulang dan hanya dilaporkan sebagai peringatan.
  4. Menambahkan panduan operasional pada `docs/deploy/RUNBOOK-VPS.md` Bagian 2 dan Bagian 15.

---

## 2. Pengelompokan Pemakaian `max_upload_bytes` Hasil Grep

Berdasarkan penelusuran menyeluruh pada modul `app/` dan `scripts/`:

### A. Alur Unggah Manual (`max_upload_mb` = 25 MB / `settings.max_upload_bytes`)
1. **`app/routers/ingest.py:325`**: Validasi ukuran berkas PDF pada endpoint unggah manual `POST /api/v1/ingest/upload-pdf` (`IngestService(..., max_upload_bytes=settings.max_upload_bytes)`).
2. **`app/services/failure_service.py:162`**: Penanganan karantina kegagalan berkas pada alur validasi upload manual.
3. **`app/services/failure_service.py:707`**: Retry kegagalan unggahan manual (`retry_max_bytes = settings.max_upload_bytes`).
4. **`app/services/ingest_service.py:115`**: Nilai parameter default pada konstruktor `IngestService`.
5. **`scripts/build_api_contract.py:665`**: Generator dokumentasi kontrak API untuk batas unggah manual pengguna (25 MB).

### B. Alur Penarikan Web/Crawl & Background Runner (`max_fetch_mb` = 100 MB / `settings.max_fetch_bytes`)
1. **`app/services/scan_service.py:953`**: Inisialisasi `IngestService` pada saat eksekusi penarikan kandidat pemindaian (`execute_pull`).
2. **`app/services/scan_service.py:1016`**: Pemanggilan crawler HTTP untuk mengunduh kandidat PDF (`crawler.fetch(..., max_bytes=settings.max_fetch_bytes)`).
3. **`app/services/scan_service.py:1125`**: Validasi integritas dan batas ukuran berkas hasil unduhan pemindaian situs.
4. **`app/services/source_runner.py:250`**: Inisialisasi `IngestService` pada background runner sinkronisasi folder lokal dan penjadwalan scraping.
5. **`app/services/failure_service.py:493`**: Validasi ulang berkas PDF hasil crawling saat sinkronisasi metadata.
6. **`app/services/failure_service.py:558`**: Validasi ulang berkas PDF hasil crawling saat penggantian berkas.
7. **`app/services/failure_service.py:607`**: Pengunduhan ulang berkas dari URL sumber saat retry kegagalan pemindaian.
8. **`app/services/failure_service.py:707`**: Penentuan dinamis batas retry unduh URL (`retry_max_bytes = settings.max_fetch_bytes` bila `is_scan` bernilai `True`).
9. **`scripts/backfill_pdf_info.py:81`**: Skrip inspeksi dan backfill berkas PDF yang sudah berada di KB/storage.

---

## 3. Data Statistik Database Lokal (Query Mentah)

Query dieksekusi langsung pada kontainer `db` (`hero_postgres`) di database `hero_db`:

```sql
SELECT COUNT(*) AS total_document_relations FROM document_relations;
SELECT COUNT(*) AS active_docs_without_identity_key FROM documents WHERE is_active = true AND identity_key IS NULL;
```

**Hasil Terminal**:
```text
 total_document_relations 
--------------------------
                        1
(1 row)

 active_docs_without_identity_key 
----------------------------------
                               94
(1 row)
```

- **`total_document_relations`**: 1 baris relasi.
- **`active_docs_without_identity_key`**: 94 dokumen aktif tanpa kunci identitas resmi.

---

## 4. Tabel Hasil Pengujian Q01–Q13

Seluruh 13 skenario uji pada `tests/test_step38_qa_uat.py` berhasil dieksekusi dengan status **LULUS (PASSED)**:

| Kode | Deskripsi Skenario Pengujian | Status |
|:---|:---|:---:|
| **Q01** | Ingest dokumen dengan status sumber `'dicabut'` → `status_source = 'sumber'`; endpoint `/versi` memuat `status_keterangan` & `jumlah_relasi` | **LULUS** |
| **Q02** | Dokumen `status_source = 'sumber'` lalu relasi mencabut disinkronkan → status berubah dari relasi, `status_source = 'relasi'` | **LULUS** |
| **Q03** | Dokumen `status_source = 'manual'` → kebal terhadap penimpaan relasi (`recompute_status` tidak mengubah) | **LULUS** |
| **Q04** | Dokumen `status_source = 'sumber'` tanpa relasi saat `recompute_status` → status sumber tetap bertahan (tidak kembali ke `'tidak_diketahui'`) | **LULUS** |
| **Q05** | `backfill_status_source.py`: mode dry-run tidak mengubah baris; mode `--apply` mengisi `"sumber"` dan mencatat log audit `UPDATE_DOCUMENT_STATUS` | **LULUS** |
| **Q06** | Endpoint `/versi` pada dokumen tanpa `identity_key` → mengembalikan `identity_key_kosong: true` dan `jumlah_relasi: 0` | **LULUS** |
| **Q07** | Unggah manual berkas 26 MB → ditolak dengan kode `ukuran_melebihi_batas`, pesan menyebut batas 25 MB, dan tidak ada baris dokumen di DB | **LULUS** |
| **Q08** | Unduhan pemindaian (scan) berkas 26 MB → diterima sukses masuk KB karena batas fetch adalah 100 MB | **LULUS** |
| **Q09** | Ringkasan job dengan dokumen yang kemudian dinonaktifkan karena duplikat identitas → `duplikat_identitas_count = 1`, `duplicate_count` lama tetap 0 | **LULUS** |
| **Q10** | Unggah PDF rusak → pesan Indonesia tanpa teks pypdf mentah; `label_alasan = "PDF rusak"`; `is_retryable = false` | **LULUS** |
| **Q11** | Respons JSON seluruh endpoint API menyertakan header `Content-Type: application/json; charset=utf-8`; karakter em-dash ("—") utuh | **LULUS** |
| **Q12** | `periksa_konsistensi_pasal.py` mengidentifikasi dokumen macet di `diproses` (Kelompok D) yang percobaannya habis maupun belum; dry-run tidak mengubah status | **LULUS** |
| **Q13** | Opsi `--antrekan-ulang-macet` → dokumen ber-PDF kembali ke `diterima` dengan percobaan di-reset ke 0 dan dapat diklaim worker; dokumen tanpa PDF dilewati | **LULUS** |

---

## 5. Penyesuaian Pengujian Suite Lama

Dua berkas tes lama disesuaikan agar selaras dengan kontrak baru Langkah 38:

1. **`tests/test_step26_qa_ingest.py`**:
   - *Pengujian*: `test_r01_pesan_human_readable_tidak_bocor_library`.
   - *Alasan*: Pesan galat `pdf_rusak` distandarkan ke kalimat bahasa Indonesia resmi: `"Berkas PDF rusak atau tidak lengkap sehingga tidak bisa dibuka. Unduh ulang atau minta berkas aslinya."`. Assertion disesuaikan untuk memverifikasi kalimat baru ini dan memastikan string mentah `"Stream has ended unexpectedly"` tidak bocor ke klien.
2. **`tests/test_scan_flow.py`**:
   - *Pengujian*: `test_k08_k09_k10_pull_failures_and_duplicates`.
   - *Alasan*: Pengujian ini memverifikasi penolakan berkas besar saat scan pull dengan me-monkeypatch ukuran maksimal. Karena alur penarikan scan kini menggunakan setting `max_fetch_bytes` (bukan `max_upload_bytes`), monkeypatch diperluas untuk mencakup `Settings.max_fetch_bytes`.

---

## 6. Output Terminal Pengujian Pytest

### A. Pengujian Berkas Baru (`tests/test_step38_qa_uat.py`)
```text
.\venv\Scripts\python.exe -m pytest tests/test_step38_qa_uat.py -q
.............                                                            [100%]
13 passed, 2 warnings in 20.49s
```

### B. Seluruh Rangkaian Pengujian Backend (`pytest -q`)
```text
.\venv\Scripts\python.exe -m pytest -q
........................................................................ [ 10%]
................................................s....................... [ 20%]
........................................................................ [ 30%]
........................................................................ [ 40%]
........................................................................ [ 50%]
........................................................................ [ 60%]
........................................................................ [ 71%]
........................................................................ [ 81%]
........................................................................ [ 91%]
.............................................................            [100%]
708 passed, 1 skipped, 225 warnings in 1091.25s (0:18:11)
```

---

## 7. Output Terminal Pemeriksaan Linting Ruff (`E9,F`)

```text
.\venv\Scripts\python.exe -m ruff check --select E9,F app scripts tests\test_step38_qa_uat.py
All checks passed!
```

---

## 8. Output Uji Live Dry-Run & Integrasi Kontainer

### A. Pemeriksaan Header Charset UTF-8 pada Endpoint Live Backend
```text
curl.exe -s -D - -o NUL http://localhost:8000/health
HTTP/1.1 200 OK
date: Sat, 07 Nov 2026 10:12:32 GMT
server: uvicorn
content-length: 292
content-type: application/json; charset=utf-8
vary: Origin
x-content-type-options: nosniff
x-frame-options: DENY
referrer-policy: strict-origin-when-cross-origin
```

### B. Dry-Run Skrip Backfill Status Source
```text
docker compose exec backend python scripts/backfill_status_source.py

===============================================================================================
           BACKFILL STATUS_SOURCE KE 'sumber' (Langkah 38)
===============================================================================================
Total dokumen ditemukan: 14
ID     | Status Keberlakuan   | Status Source Lama   | Judul (45 Karakter)
-----------------------------------------------------------------------------------------------
16     | berlaku              | None                 | Peraturan Otoritas Jasa Keuangan Republik Ind
17     | berlaku              | None                 | Peraturan Otoritas Jasa Keuangan Republik Ind
18     | berlaku              | None                 | Peraturan Otoritas Jasa Keuangan Republik Ind
19     | berlaku              | None                 | Surat Edaran Otoritas Jasa Keuangan Republik 
20     | berlaku              | None                 | Surat Edaran Otoritas Jasa Keuangan Republik 
21     | dicabut              | None                 | Surat Edaran Otoritas Jasa Keuangan Republik 
22     | berlaku              | None                 | Peraturan Anggota Dewan Komisioner Otoritas J
23     | berlaku              | None                 | Peraturan Anggota Dewan Komisioner Otoritas J
24     | berlaku              | None                 | Peraturan Anggota Dewan Komisioner Otoritas J
25     | berlaku              | None                 | Peraturan Anggota Dewan Komisioner Otoritas J
26     | berlaku              | None                 | Peraturan Anggota Dewan Komisioner Otoritas J
27     | dicabut              | None                 | Surat Edaran Otoritas Jasa Keuangan Republik 
43     | diubah               | None                 | Peraturan Otoritas Jasa Keuangan Nomor 27 /PO
44     | diubah               | None                 | Peraturan Otoritas Jasa Keuangan Republik Ind

[DRY-RUN] Mode tinjauan saja. Tidak ada perubahan basis data yang disimpan.
Gunakan flag --apply untuk mengeksekusi pembaruan.
===============================================================================================
```

### C. Dry-Run Skrip Pemeriksa Konsistensi PDF & Pasal
```text
docker compose exec backend python scripts/periksa_konsistensi_pasal.py

==============================================================================================================
                     LAPORAN PEMERIKSAAN KONSISTENSI PDF - PASAL
==============================================================================================================

[KELOMPOK A] Dokumen Aktif Tanpa Berkas PDF (0 dokumen):
  (Nihil - semua dokumen aktif memiliki berkas PDF di penyimpanan)

[KELOMPOK B] Dokumen Ber-PDF Tanpa Pasal (0 dokumen):
  (Nihil - tidak ada dokumen terindeks/perlu_koreksi tanpa pasal)

[KELOMPOK C] Pasal Yatim (0 grup dokumen, total 0 pasal):
  (Nihil - tidak ada pasal yatim)

[KELOMPOK D] Dokumen Macet di 'diproses' (0 dokumen, 0 tidak akan pernah diklaim lagi):
  (Nihil - tidak ada dokumen macet di 'diproses' yang melebihi timeout)

--------------------------------------------------------------------------------------------------------------
RINGKASAN JUMLAH:
  - Kelompok A (Tanpa PDF)         : 0 dokumen
  - Kelompok B (Ber-PDF tanpa pasal): 0 dokumen
  - Kelompok C (Pasal Yatim)       : 0 pasal pada 0 dokumen
  - Kelompok D (Macet Diproses)    : 0 dokumen (0 percobaan habis)
--------------------------------------------------------------------------------------------------------------
[DRY-RUN] Mode tinjauan saja. Tidak ada perubahan status atau antrean pada basis data.
==============================================================================================================
```

### D. Smoke Test Integrasi Fase 2
```text
.\venv\Scripts\python.exe scripts/smoke_fase2.py --base-url http://localhost:8000
====================================================================================
       HERO BACKEND SMOKE TEST FASE 2 - http://localhost:8000
       Revisi Alembic Diharapkan: f8a9b0c1d2e3
       Autentikasi: Tidak ada HERO_SMOKE_TOKEN (mode anonim/dev)
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
S15    | Penjaga non-publik                       | OK       | doc_id=95 ditolak 403 saat auth mati
S16    | GET /api/v1/dashboard/summary            | OK       | belum_berlaku=0
S17    | GET /api/v1/dashboard/corong             | OK       | sumber=5, di_kb=94, terbaca=0 (0.0%)
S18    | GET /api/v1/dashboard/corong?format=csv  | OK       | BOM=ada, TOTAL=ada, filename*=ada, bytes=1169
S19    | GET /ingest/failures filter kode         | OK       | items=2, filter bekerja
S20    | GET /api/v1/categories/tree              | OK       | nodes=42, kunci Langkah 28 lengkap
S21    | Dokumen di kategori 'Tanpa Tahun'        | OK       | 0 dokumen di 'Tanpa Tahun'
S22    | Harmonisasi per pasal                    | LEWATI   | ML tidak siap
====================================================================================
RINGKASAN: 9 OK, 0 GAGAL, 13 LEWATI
```

---

## 9. Catatan untuk Pipeline (Fathir)

1. **Relasi Antarperaturan**:
   - Field relasi pada `GET /documents/{id}/versi` (seperti `mencabut`, `dicabut_oleh`, `mengubah`, `diubah_oleh`) saat ini kosong pada mayoritas dokumen karena tabel `document_relations` di basis data baru memuat 1 baris.
   - Status keberlakuan yang dihitung dari relasi hanya aktif bila relasi dikirimkan oleh pipeline Data/ML melalui endpoint `POST /api/v1/internal/relations`.
   - Selain itu, terdapat **94 dokumen aktif** di basis data lokal yang belum memiliki `identity_key` (`identity_key IS NULL`), sehingga pencocokan relasi belum dapat dilakukan untuk dokumen-dokumen tersebut sampai ekstraksi metadata identitas diselesaikan.
2. **Dokumen Macet di Status `diproses`**:
   - Sebanyak 131 dokumen aktif di VPS yang berstatus `diproses` dan percobaannya habis kini dapat dipulihkan antreannya.
   - Setelah branch ini digabungkan ke server, jalankan perintah CLI:
     `docker compose exec backend python scripts/periksa_konsistensi_pasal.py --antrekan-ulang-macet`
   - Tindakan ini akan mereset status dokumen ber-PDF ke `diterima`, mengosongkan waktu klaim, dan mereset `extraction_attempts = 0`, sehingga worker ekstraksi Data/ML dapat mengklaimnya kembali.

---

## 10. Catatan untuk Frontend (Ikhwan)

1. **Field Baru pada Respons Kegagalan Ingest**:
   - Endpoint `GET /api/v1/ingest/failures`, `GET /api/v1/ingest/failures/{id}`, dan respons `POST /api/v1/ingest/upload-pdf` kini menyertakan field `label_alasan` (string bahasa Indonesia, misal: "PDF rusak", "Ukuran melebihi batas", "PDF terkunci kata sandi").
   - UI dapat langsung menampilkan `label_alasan` pada badge/tabel kegagalan tanpa perlu hardcode pemetaan kode galat di frontend.
   - Tombol "Coba Lagi" (Retry) cukup dipandu oleh nilai boolean `is_retryable` (untuk berkas rusak atau ukuran melebihi batas, nilainya otomatis `false`).
2. **Field Baru pada Endpoint `/versi`**:
   - `GET /api/v1/documents/{id}/versi` kini menyertakan:
     - `status_keterangan`: Kalimat ramah pengguna yang menjelaskan asal usul status keberlakuan.
     - `jumlah_relasi`: Angka total relasi yang tercatat untuk regulasi tersebut.
     - `identity_key_kosong`: Boolean penanda apakah dokumen memiliki kunci identitas untuk pencocokan relasi.
3. **Ringkasan Job Ingest**:
   - `JobDetailResponse` dan `JobListItemResponse` kini memuat `duplikat_identitas_count`. UI dapat menampilkan rincian duplikat berkas fisik vs duplikat identitas regulasi yang dinonaktifkan.

---

## 11. Catatan Deploy (DevOps)

1. **Variabel Lingkungan Baru (`.env.prod`)**:
   Tambahkan konfigurasi batas ukuran berkas pada `.env.prod`:
   ```bash
   MAX_UPLOAD_MB=25   # Batas unggah manual PDF via portal web (default: 25 MB)
   MAX_FETCH_MB=100   # Batas unduh crawling/scan web & sync folder (default: 100 MB)
   ```
2. **Urutan Eksekusi Skrip di VPS Pasca-Deploy**:
   Jalankan skrip secara berurutan:
   ```bash
   # 1. Backfill status_source ke 'sumber' untuk dokumen eksisting
   docker compose exec backend python scripts/backfill_status_source.py --apply

   # 2. Periksa konsistensi dan pulihkan dokumen yang macet di status diproses
   docker compose exec backend python scripts/periksa_konsistensi_pasal.py --antrekan-ulang-macet
   ```

---

## 12. Ringkasan Perubahan Git

### Output `git diff main --stat`
```text
 .env.example                         |   5 +-
 .env.prod.example                    |   5 +-
 app/config.py                        |   9 ++-
 app/main.py                          |  17 ++++-
 app/responses.py                     |  19 +++++
 app/routers/documents.py             |   3 +
 app/routers/ingest.py                |  38 ++++++++++
 app/routers/ml_gateway.py            |   2 +-
 app/schemas/ingest.py                |  26 +++++++
 app/services/failure_service.py      |  11 +--
 app/services/file_validation.py      |   7 +-
 app/services/ingest_service.py       |   8 +++
 app/services/scan_service.py         |   6 +-
 app/services/source_runner.py        |   2 +-
 app/services/version_service.py      |  37 ++++++++--
 docs/api/KONTRAK-API-FASE1.md        |   7 +-
 docs/deploy/RUNBOOK-VPS.md           |  41 ++++++++++-
 scripts/backfill_pdf_info.py         |   2 +-
 scripts/backfill_status_source.py    | 122 ++++++++++++++++++++++++++++++
 scripts/periksa_konsistensi_pasal.py | 135 +++++++++++++++++++++++++++++++----
 tests/test_scan_flow.py              |   3 +-
 tests/test_step26_qa_ingest.py       |   2 +-
 tests/test_step38_qa_uat.py          | 636 +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
 23 files changed, 1099 insertions(+), 48 deletions(-)
```

---
