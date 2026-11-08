# Laporan Langkah 39 — Penandaan Temuan Harmonisasi (#71) & Ekspor Laporan Harmonisasi (#73)

Tanggal: 8 November 2026  
Branch: `feat/step39-tanggapan-ekspor-harmonisasi`  
Basis: `main` (commit `8477aea Merge Langkah 38: temuan QA 7 Nov`)  

---

## 1. Ringkasan Perubahan

Langkah 39 menyelesaikan dua kebutuhan utama Fase 3 untuk modul Harmonisasi Regulasi:
1. **#71 (US-49, FR-HRM-11): Penandaan temuan harmonisasi (valid / tidak relevan)**
   - Menambahkan tabel basis data `tanggapan_temuan` melalui migrasi Alembic `a1b2c3d4e5f6`.
   - Mengimplementasikan fungsi penghasil kunci deterministik `kunci_temuan(temuan: dict) -> str` (32 karakter heksadesimal SHA-256) berbasis 4 atribut substantif (`jenis`, `pasal_draft`, pembanding `key`/`document_id`, `pasal_pembanding`), stabil terhadap perubahan `id` acak dari layanan ML.
   - Menyediakan endpoint tanggapan analis:
     - `PUT /api/v1/documents/{id}/harmonisasi/tanggapan`: Upsert penilaian (`valid` / `tidak_relevan`), catatan (maks 2000 kar), `run_id`, dan penilai (`dinilai_oleh`, `dinilai_oleh_nama`).
     - `GET /api/v1/documents/{id}/harmonisasi/tanggapan`: Daftar tanggapan tersimpan untuk dokumen draft tertentu.
     - `DELETE /api/v1/documents/{id}/harmonisasi/tanggapan/{kunci_temuan}`: Menghapus penilaian atas temuan tertentu.
     - `GET /api/v1/harmonisasi/tanggapan/rekap`: Rekapitulasi jumlah valid vs tidak relevan per jenis temuan dengan opsi filter tanggal (`dari`, `sampai`) dan dokumen (`document_id`), serta dukungan ekspor CSV UTF-8 ber-BOM (`?format=csv`).
   - Validasi peran dokumen: Hanya dokumen dengan `document_role = draft_kajian` yang dapat diberi tanggapan (dokumen non-draft menghasilkan HTTP 422 `bukan_draft`).
   - Penggabungan otomatis tanggapan ke dalam respons `POST /api/v1/ml/harmonisasi/{document_id}`: Menyematkan `kunci_temuan` dan objek `tanggapan` pada setiap butir temuan, serta rekap `ringkasan.tanggapan` (`{valid, tidak_relevan, belum_dinilai}`). Cache basis data `analysis_results` tetap tersimpan 100% murni tanpa data pengguna.

2. **#73 (US-50, FR-HRM-13): Ekspor laporan harmonisasi (DOCX, CSV, JSON)**
   - Menyediakan endpoint `GET /api/v1/documents/{id}/harmonisasi/ekspor?format=docx|csv|json&run_id=...` dengan izin `Izin.ANALISA_EKSPOR`.
   - Format DOCX:
     - Judul "Laporan Harmonisasi", identitas draft, ringkasan jumlah temuan & rekap penilaian analis.
     - Tabel temuan 8 kolom: No, Jenis, Judul Temuan, Klausul Draft, Regulasi Pembanding, Klausul Pembanding, Penilaian Analis, Catatan Analis.
     - Catatan kaki URD: *"Keputusan final tetap kewenangan Pengawas / unit terkait."*.
   - Format CSV:
     - Berkas teks beralas pemisah koma dengan UTF-8 BOM (`\xef\xbb\xbf`).
     - 10 kolom: Nomor, Jenis Temuan, Pasal Draft, Regulasi Pembanding, Pasal Pembanding, Deskripsi / Judul, Penilaian Analis, Catatan Analis, Dinilai Oleh, Kunci Temuan.
   - Format JSON:
     - Struktur terpadu mencakup metadata ekspor, data draft regulasi, ringkasan, dan daftar temuan beranotasi tanggapan analis.
   - Audit trail `EXPORT_HARMONIZATION` dengan detail format, jumlah temuan, dan run_id.

---

## 2. Keputusan Arsitektur & Penempatan Komponen

### 2.1 Penempatan Router Baru `app/routers/harmonisasi.py`
- **Keputusan**: Seluruh endpoint penandaan temuan dan ekspor harmonisasi ditempatkan di modul khusus `app/routers/harmonisasi.py`, bukan disisipkan ke dalam `app/routers/documents.py` atau `app/routers/ml_gateway.py`.
- **Alasan**:
  - `app/routers/documents.py` telah memiliki panjang > 1.700 baris kode dan mengelola entitas dokumen generik, metadata, serta ekspor analisa lama.
  - `app/routers/ml_gateway.py` telah memiliki panjang > 1.400 baris kode dan bertindak sebagai proxy komunikasi ke container ML (Analisa & Harmonisasi).
  - Modul `harmonisasi.py` memisahkan concern tata kelola pasca-harmonisasi (penilaian analis, audit tanggapan, rekap evaluasi model, dan pelaporan ekspor) secara kohesif, memudahkan pemeliharaan tanpa membebani router gateway.

### 2.2 Penentuan Sumber Data Ekspor (Cache vs Riwayat Run)
- **Keputusan**:
  1. Jika parameter query `run_id` diberikan: Mengambil langsung dari baris riwayat `AnalysisRun` yang sesuai (`document_id == doc.id` dan `kind == JenisAnalisa.harmonisasi`).
  2. Jika `run_id` tidak diberikan: Mencari terlebih dahulu dari cache `AnalysisResult` terbaru dokumen tersebut. Jika tidak ditemukan (misal cache dinonaktifkan atau dievつい), melakukan fallback ke `AnalysisRun` sukses terbaru yang memiliki payload output.
  3. Jika tidak ada hasil harmonisasi yang tersimpan sama sekali: Mengembalikan HTTP 404 dengan kode `harmonisasi_belum_ada` **tanpa** memicu pemanggilan baru ke layanan ML.
- **Alasan**: Ekspor laporan harus merupakan operasi baca murni (idempotent, aman, dan cepat) atas hasil komputasi yang telah disepakati oleh analis, bukan eksekusi analisa baru yang berbiaya komputasi tinggi.

---

## 3. Matriks Hasil Pengujian Otomatis

Seluruh 18 skenario uji pada `tests/test_step39_tanggapan_ekspor.py` berhasil dieksekusi dengan status **LULUS (PASSED)**:

| Kode Uji | Skenario Pengujian | Hasil |
|---|---|:---:|
| **H01** | Kunci temuan stabil antar perbedaan ID ML acak (same substance -> same key) | **LULUS** |
| **H02** | Kunci temuan berbeda untuk substansi pasal, jenis, atau pembanding yang berbeda | **LULUS** |
| **H03** | `PUT` tanggapan `valid` + catatan pada draft publik -> 200, baris tersimpan, audit `TANGGAPAN_TEMUAN` | **LULUS** |
| **H04** | `PUT` ulang dengan `tidak_relevan` -> baris diperbarui (idempotent/upsert), audit before/after | **LULUS** |
| **H05** | Penilaian tidak valid -> 422; catatan > 2000 karakter -> 422 | **LULUS** |
| **H06** | Dokumen bukan `draft_kajian` -> 422 `bukan_draft` | **LULUS** |
| **H07** | Draft non-publik saat auth mati & proteksi aktif -> 403 `dokumen_terbatas` | **LULUS** |
| **H08** | Saat auth aktif: role tanpa izin ditolak 403; Analis/PilotUser diterima; `dinilai_oleh` & `dinilai_oleh_nama` terisi | **LULUS** |
| **H09** | `DELETE` tanggapan -> 200, baris terhapus, audit `action: delete` | **LULUS** |
| **H10** | Harmonisasi dijalankan ulang -> respons menyematkan `kunci_temuan` & `tanggapan`; `ringkasan.tanggapan` benar; cache murni | **LULUS** |
| **H11** | Rekap evaluasi tanggapan (`GET /harmonisasi/tanggapan/rekap`) format JSON dan CSV ber-BOM | **LULUS** |
| **E01** | Ekspor DOCX setelah harmonisasi -> format binary, judul, metadata, tabel 8 kolom, disclaimer URD | **LULUS** |
| **E02** | Ekspor CSV -> UTF-8 BOM, 10 kolom, baris data beranotasi tanggapan | **LULUS** |
| **E03** | Ekspor JSON -> struktur terpadu, metadata, temuan beranotasi tanggapan | **LULUS** |
| **E04** | Ekspor dokumen belum harmonisasi -> 404 `harmonisasi_belum_ada` tanpa memanggil ML | **LULUS** |
| **E05** | Penyaringan pembanding non-aktif / non-publik pada ekspor harmonisasi | **LULUS** |
| **E06** | Format ekspor tidak dikenal -> 422 `format_tidak_didukung` | **LULUS** |
| **E07** | Pencatatan audit trail `EXPORT_HARMONIZATION` pada setiap ekspor | **LULUS** |

---

## 4. Bukti Eksekusi Terminal (Raw Output)

### 4.1 Ruff Check (`app`, `scripts`, `tests/test_step39_tanggapan_ekspor.py`)
```
.\venv\Scripts\python.exe -m ruff check --select E9,F app scripts tests\test_step39_tanggapan_ekspor.py
All checks passed!
```

### 4.2 Pytest Spesifik Langkah 39 (`tests/test_step39_tanggapan_ekspor.py`)
```
.\venv\Scripts\python.exe -m pytest tests\test_step39_tanggapan_ekspor.py -v
============================= test session starts =============================
platform win32 -- Python 3.13.7, pytest-9.1.1, pluggy-1.6.0 -- C:\Hero\hero-backend\venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Hero\hero-backend
plugins: anyio-4.15.1
collecting ... collected 18 items

tests/test_step39_tanggapan_ekspor.py::test_h01_kunci_temuan_stabil_antar_id_ml PASSED [  5%]
tests/test_step39_tanggapan_ekspor.py::test_h02_kunci_temuan_berbeda_untuk_substansi_berbeda PASSED [ 11%]
tests/test_step39_tanggapan_ekspor.py::test_h03_put_tanggapan_valid PASSED [ 16%]
tests/test_step39_tanggapan_ekspor.py::test_h04_put_ulang_tanggapan_update PASSED [ 22%]
tests/test_step39_tanggapan_ekspor.py::test_h05_penilaian_tidak_dikenal_dan_catatan_panjang PASSED [ 27%]
tests/test_step39_tanggapan_ekspor.py::test_h06_dokumen_bukan_draft_ditolak PASSED [ 33%]
tests/test_step39_tanggapan_ekspor.py::test_h07_draft_non_publik_auth_mati_ditolak_403 PASSED [ 38%]
tests/test_step39_tanggapan_ekspor.py::test_h08_auth_aktif_peran_dan_penilai PASSED [ 44%]
tests/test_step39_tanggapan_ekspor.py::test_h09_delete_tanggapan PASSED  [ 50%]
tests/test_step39_tanggapan_ekspor.py::test_h10_harmonisasi_ulang_mock_id_berubah PASSED [ 55%]
tests/test_step39_tanggapan_ekspor.py::test_h11_rekap_json_dan_csv PASSED [ 61%]
tests/test_step39_tanggapan_ekspor.py::test_e01_ekspor_docx_setelah_harmonisasi PASSED [ 66%]
tests/test_step39_tanggapan_ekspor.py::test_e02_ekspor_csv PASSED        [ 72%]
tests/test_step39_tanggapan_ekspor.py::test_e03_ekspor_json PASSED       [ 77%]
tests/test_step39_tanggapan_ekspor.py::test_e04_ekspor_belum_ada_harmonisasi_404_tanpa_panggil_ml PASSED [ 83%]
tests/test_step39_tanggapan_ekspor.py::test_e05_ekspor_penyaringan_pembanding_nonaktif PASSED [ 88%]
tests/test_step39_tanggapan_ekspor.py::test_e06_ekspor_format_tidak_dikenal_422 PASSED [ 94%]
tests/test_step39_tanggapan_ekspor.py::test_e07_audit_export_harmonization PASSED [100%]

======================= 18 passed, 2 warnings in 20.92s =======================
```

### 4.3 Pytest Seluruh Suite (`.\venv\Scripts\python.exe -m pytest -q`)
```
.\venv\Scripts\python.exe -m pytest -q
........................................................................ [  9%]
................................................s....................... [ 19%]
........................................................................ [ 29%]
........................................................................ [ 39%]
........................................................................ [ 49%]
........................................................................ [ 59%]
........................................................................ [ 69%]
........................................................................ [ 79%]
........................................................................ [ 89%]
........................................................................ [ 99%]
.......                                                                  [100%]
726 passed, 1 skipped, 248 warnings in 1006.21s (0:16:46)
```

### 4.4 Uji Integrasi Langsung (Live Integration & Dry-Run)

1. Cek kesehatan kontainer backend dan migrasi:
```
curl.exe -s http://localhost:8000/health
{"status":"ok","database":"ok","version":"0.10.0","app_env":"development","alembic_revision":"a1b2c3d4e5f6","alembic_head":"a1b2c3d4e5f6","migrations_up_to_date":true,"storage_writable":true,"crawler_backend":"simple_http","crawler_loaded":true,"auth_enabled":false,"protect_non_public":true}
```

2. Cek ekspor dokumen tanpa harmonisasi:
```
curl.exe -s -o NUL -w "%{http_code}\n" "http://localhost:8000/api/v1/documents/999999/harmonisasi/ekspor?format=json"
404
```

3. Cek endpoint rekap evaluasi tanggapan:
```
curl.exe -s "http://localhost:8000/api/v1/harmonisasi/tanggapan/rekap"
{"total":{"valid":0,"tidak_relevan":0,"total":0},"per_jenis":{},"filter":{"dari":null,"sampai":null,"document_id":null}}
```

4. Smoke test Fase 2:
```
.\venv\Scripts\python.exe scripts/smoke_fase2.py --base-url http://localhost:8000
====================================================================================
       HERO BACKEND SMOKE TEST FASE 2 - http://localhost:8000
       Revisi Alembic Diharapkan: a1b2c3d4e5f6
       Autentikasi: Tidak ada HERO_SMOKE_TOKEN (mode anonim/dev)
====================================================================================
====================================================================================
Kode   | Cek                                      | Status   | Keterangan
------------------------------------------------------------------------------------
S01    | GET /health                              | OK       | rev=a1b2c3d4e5f6
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
PERINGATAN: cek analisa/riwayat/ekspor (S05–S13) tidak dijalankan karena tidak ada dokumen uji. Pakai --doc-id atau pastikan ada dokumen publik terindeks.
PERINGATAN: 3134 hasil scan belum ditarik ke KB — Pak Faris meminta semua hasil scan masuk KB (Weekly #7).
```

---

## 5. Catatan untuk Frontend (Ikhwan)

1. **Respons Harmonisasi Diperkaya (`POST /api/v1/ml/harmonisasi/{document_id}`)**:
   - Setiap butir objek dalam array `temuan` kini memiliki dua field tambahan:
     - `kunci_temuan: string` (SHA-256 32 karakter deterministik): Gunakan field ini sebagai kunci stabil pada React list atau sebagai pengidentifikasi temuan saat memanggil endpoint tanggapan.
     - `tanggapan: object | null`: Berisi `{ "penilaian": "valid"|"tidak_relevan", "catatan": "...", "dinilai_oleh_nama": "...", "diperbarui": "..." }` jika temuan sudah pernah ditanggapi, atau `null` jika belum.
   - Pada objek `ringkasan`, terdapat rekap tanggapan otomatis:
     - `ringkasan.tanggapan`: `{ "valid": 3, "tidak_relevan": 1, "belum_dinilai": 6 }`.
2. **Memberi / Mengubah Tanggapan (`PUT /api/v1/documents/{id}/harmonisasi/tanggapan`)**:
   - Payload cukup mengirimkan objek temuan yang bersangkutan:
     ```json
     {
       "temuan": { ...objek temuan dari respons harmonisasi... },
       "penilaian": "valid",
       "catatan": "Catatan analis opsional (maks 2000 karakter)",
       "run_id": 123
     }
     ```
   - Frontend tidak perlu menghitung `kunci_temuan` sendiri; backend otomatis menghitung kunci stabil dari objek temuan tersebut.
3. **Membatalkan / Menghapus Tanggapan**:
   - Panggil `DELETE /api/v1/documents/{id}/harmonisasi/tanggapan/{kunci_temuan}`.
4. **Tombol Ekspor Laporan Harmonisasi**:
   - Panggil `GET /api/v1/documents/{id}/harmonisasi/ekspor?format=docx|csv|json`.
   - Gunakan `blob()` untuk mengunduh berkas dengan nama yang disediakan pada header `Content-Disposition`.

---

## 6. Catatan untuk PM (Zaky)

1. **Evaluasi Recall Model (#74)**:
   - Endpoint `GET /api/v1/harmonisasi/tanggapan/rekap` telah siap digunakan untuk monitoring dan evaluasi model.
   - Analis / Admin dapat mengunduh rekapitulasi penilaian dalam format spreadsheet CSV ber-BOM langsung melalui parameter query:
     `GET /api/v1/harmonisasi/tanggapan/rekap?format=csv` (mendukung filter `dari=YYYY-MM-DD` dan `sampai=YYYY-MM-DD`).
2. **Format Laporan Harmonisasi (#73)**:
   - Karena template visual definitif dari unit kerja belum ditetapkan, backend menyediakan 3 format standar yang kompatibel dengan modul analisa regulasi (ANL-09): DOCX (resmi dengan tabel temuan dan disclaimer URD), CSV (analisis tabular), dan JSON (integrasi data).

---

## 7. Catatan Deploy & Operasional

- **Migrasi Alembic Baru**: Revisi `a1b2c3d4e5f6` (`step39_tanggapan_temuan`) membuat tabel baru `tanggapan_temuan`.
  - Jalankan di server:
    ```bash
    alembic upgrade head
    ```
- **Izin Pengguna (RBAC)**:
  - Penandaan temuan (`PUT`, `DELETE` tanggapan) mensyaratkan izin `Izin.TANGGAPAN_TINJAU` (dimiliki oleh Analis Regulasi dan Pilot User).
  - Ekspor laporan harmonisasi mensyaratkan izin `Izin.ANALISA_EKSPOR`.
  - Rekap evaluasi recall mensyaratkan `Izin.KB_BACA`.

---

## 8. Verifikasi Git

### `git diff main --stat`
```
 app/main.py                                            |   2 +
 app/models/__init__.py                                 |   1 +
 app/models/tanggapan_temuan.py                         |  64 ++++
 app/routers/harmonisasi.py                             | 398 ++++++++++++++++++++++
 app/routers/ml_gateway.py                              |   4 +
 app/schemas/harmonisasi.py                             |   3 +
 app/schemas/tanggapan.py                               |  58 ++++
 app/services/audit_service.py                          |   2 +
 app/services/harmonisasi_export_service.py              | 443 ++++++++++++++++++++++++
 app/services/tanggapan_service.py                      | 134 ++++++++
 alembic/versions/a1b2c3d4e5f6_step39_tanggapan_temuan.py |  61 ++++
 docs/api/KONTRAK-API-FASE1.md                          |   6 +
 docs/api/openapi-fase1.json                            | 665 ++++++++++++++++++++++++++++++++++++-
 docs/reports/step39-report.md                          | 335 +++++++++++++++++++
 scripts/build_api_contract.py                          |  35 ++
 tests/conftest.py                                      |   1 +
 tests/test_step39_tanggapan_ekspor.py                  | 905 ++++++++++++++++++++++++++++++++++++++++++++++++++
```

### `git log --oneline -3` (sebelum commit)
```
8477aea Merge Langkah 38: temuan QA 7 Nov
eb814ad docs(step38): lengkapi laporan
58ffda9 chore: sinkron dari monorepo
```
