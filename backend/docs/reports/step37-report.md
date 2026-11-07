# Laporan Langkah 37 — Penarikan Dokumen Utama, Pengenal Lampiran, Pemeriksaan Non-Utama & Konsistensi Pasal

Tanggal: 6 November 2026  
Branch: `fix/step37-tarik-utama`  
Basis: `main` (commit `95d58b4 chore: hapus salinan kamus data & panduan pengguna (sumber utama di docs/ monorepo)`)  

---

## 1. Ringkasan Eksekutif

Langkah 37 menuntaskan penyempurnaan alur penarikan scan ke Knowledge Base (KB), identifikasi berkas lampiran/non-regulasi, dan konsistensi pasal regulasi:

1. **Pemisahan Helper `deactivate_document` ke Service Layer (`app/services/document_service.py`)**:
   - Helper `deactivate_document` dipindahkan dari `app/routers/documents.py` ke modul baru `app/services/document_service.py` untuk memutus ketergantungan langsung skrip CLI terhadap layer router FastAPI.
   - Endpoint `PUT /api/v1/documents/{document_id}/active` tetap memakai helper tersebut untuk bagian penonaktifan dokumen. Struktur audit `DEACTIVATE_DOCUMENT` tetap konsisten (`reason`, `before.is_active: True`, `after.is_active: False`).
   - Skrip `scripts/periksa_dokumen_non_utama.py` dan `scripts/periksa_konsistensi_pasal.py` mengimpor `deactivate_document` dari `app.services.document_service`.
   - Router `app/routers/documents.py` tetap mere-ekspor `deactivate_document` untuk kompatibilitas balik.

2. **Perbaikan Bug Inisialisasi StorageService (`scripts/periksa_konsistensi_pasal.py`)**:
   - `StorageService` memerlukan argumen posisi `base_path`. Fungsi `periksa_konsistensi_pasal` kini menginisialisasi storage secara default dengan `StorageService(base_path=settings.storage_path)` (seperti pada `get_storage_service()`).
   - Ditambahkan tes `test_k05_konsistensi_pasal_default_storage_service` di `tests/test_step37_tarik_utama.py` untuk menguji pemanggilan tanpa argumen storage tiruan (menggunakan filesystem riil via `settings.storage_path`).

3. **Penyaringan Dokumen Utama pada `tarik_semua.py` (§1 — T01–T05)**:
   - Konstanta `NON_UTAMA_DOC_KINDS = {"abstrak", "faq", "lampiran", "non_regulasi"}` di `scripts/tarik_semua.py` identik dengan `app/services/scan_service.py`.
   - Kandidat non-utama otomatis dilewati kecuali flag `--termasuk-non-utama` diberikan.
   - Pembatasan `--batas` dihitung setelah kandidat non-utama disaring.
   - Kandidat dengan `doc_kind = None` tetap diperlakukan sebagai `utama`.

4. **Pengenal Lampiran Tepat di `determine_doc_kind` (`app/crawlers/url_utils.py`) (§2 — L01–L09)**:
   - Berkas/judul yang diawali penanda regulasi resmi (`POJK`, `SEOJK`, `Peraturan`, `Surat Edaran`, `Salinan`, `UU`, `PP`) atau memuat frase "Perubahan atas Lampiran" diklasifikasikan sebagai `utama`.
   - Berkas hanya diklasifikasikan sebagai `lampiran` bila diawali kata lampiran (`Lampiran SP - FAQ ...`), pola kompak (`lampiran1pojktrust.pdf`, `lamppojk12.pdf`, `2024lampiranseojk3.pdf`), atau bila label dari situs pemindaian bernilai `Lampiran`.

5. **Pemeriksaan Dokumen Non-Utama di KB (`scripts/periksa_dokumen_non_utama.py`) (§3 — N01–N02)**:
   - Mengidentifikasi dokumen aktif di KB yang berjenis non-utama dari metadata kandidat pemindaian, nama berkas asli, maupun judul.
   - Dokumen yang memiliki tanggal koreksi manual (`metadata_corrected_at is not None`) dilewati untuk menghormati keputusan kurasi manual admin.
   - Mode `--apply` menonaktifkan dokumen dengan alasan `"bukan_dokumen_utama"` dan mencatat log audit `DEACTIVATE_DOCUMENT`.

6. **Pemeriksaan Konsistensi PDF & Pasal (`scripts/periksa_konsistensi_pasal.py`) (§4 — K01–K05)**:
   - **Kelompok A**: Dokumen aktif tanpa berkas fisik PDF di storage. Opsi `--nonaktifkan-tanpa-pdf` menonaktifkannya dengan alasan `"berkas_pdf_hilang"` dan audit `DEACTIVATE_DOCUMENT`.
   - **Kelompok B**: Dokumen aktif ber-PDF status terindeks/perlu_koreksi tetapi tanpa pasal (`articles = 0`). Opsi `--antrekan-ulang-tanpa-pasal` mengembalikan status ke `diterima`, mengosongkan `extraction_claimed_at`, dan mencatat audit `EXTRACTION_REQUEUED`.
   - **Kelompok C**: Baris pasal yatim (merujuk dokumen nonaktif atau dokumen yang tidak ada). Dilaporkan tanpa mengubah database.

---

## 2. Penjelasan Mengenai `tests/conftest.py`

File `tests/conftest.py` sempat diuji dengan penambahan `db.rollback()` pada blok `finally:` fixture `db_session`. Namun setelah dilakukan verifikasi menyeluruh, seluruh 21 pengujian Langkah 37 serta seluruh suite pengujian (694 tes) berjalan 100% lulus tanpa perubahan apa pun pada `tests/conftest.py`. Oleh karena itu, sesuai instruksi, file `tests/conftest.py` telah dikembalikan ke kondisi aslinya (`git checkout -- tests/conftest.py`) sehingga riwayat git tetap bersih.

---

## 3. Mekanisme Antre Ulang Dokumen Kelompok B

Pada `scripts/periksa_konsistensi_pasal.py`, penanganan dokumen Kelompok B (dokumen aktif yang memiliki berkas fisik PDF di storage dengan status `terindeks` atau `perlu_koreksi`, namun belum memiliki catatan pasal/articles di database) dilakukan langsung dalam skrip dengan mekanisme:

```python
doc.processing_status = StatusPemrosesan.diterima
doc.extraction_claimed_at = None
record_audit(
    db,
    action=EXTRACTION_REQUEUED,
    target_resource=f"document:{doc.id}",
    detail={"reason": "antrekan_ulang_tanpa_pasal", "attempt": doc.extraction_attempts},
    commit=False,
)
```

- **Alasan**: Dokumen dikembalikan ke status `diterima` dan kolom `extraction_claimed_at` di-reset ke `None`, sehingga worker ekstraksi background (lapisan data worker / `POST /api/v1/internal/extraction/claim` pada `app/routers/extraction_internal.py`) dapat mengklaim kembali dokumen ini untuk diproses ulang ekstraksi pasalnya.
- **Audit**: Setiap dokumen yang diantrekan ulang mencatat riwayat audit resmi `EXTRACTION_REQUEUED` dengan detail alasan dan jumlah percobaan ekstraksi sebelumnya.

---

## 4. Output Mentah Pemeriksaan Linting & Pengujian

### 4.1 Pemeriksaan Ruff
```powershell
.\venv\Scripts\python.exe -m ruff check --select E9,F app scripts tests\test_step37_tarik_utama.py
```
Output:
```
All checks passed!
```

### 4.2 Pengujian Unit & Integrasi Langkah 37 (`tests/test_step37_tarik_utama.py`)
```powershell
.\venv\Scripts\python.exe -m pytest tests\test_step37_tarik_utama.py -q
```
Output:
```
.....................                                                    [100%]
============================== warnings summary ===============================
venv\Lib\site-packages\fastapi\testclient.py:1
  C:\Hero\hero-backend\venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

venv\Lib\site-packages\starlette\testclient.py:53
  C:\Hero\hero-backend\venv\Lib\site-packages\starlette\testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
21 passed, 2 warnings in 37.32s
```

### 4.3 Pengujian Keseluruhan Suite Backend
```powershell
.\venv\Scripts\python.exe -m pytest -q
```
Output:
```
........................................................................ [ 10%]
................................................s....................... [ 20%]
........................................................................ [ 31%]
........................................................................ [ 41%]
........................................................................ [ 51%]
........................................................................ [ 62%]
........................................................................ [ 72%]
........................................................................ [ 82%]
........................................................................ [ 93%]
...............................................                          [100%]
============================== warnings summary ===============================
venv\Lib\site-packages\fastapi\testclient.py:1
  C:\Hero\hero-backend\venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

venv\Lib\site-packages\starlette\testclient.py:53
  C:\Hero\hero-backend\venv\Lib\site-packages\starlette\testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
694 passed, 1 skipped, 225 warnings in 1295.44s (0:21:35)
```

### 4.4 Pengujian Ulang Endpoint Aktif/Nonaktif Dokumen (Langkah 14 / US-30)
```powershell
.\venv\Scripts\python.exe -m pytest tests/test_step14_active.py -v
```
Output:
```
============================= test session starts =============================
platform win32 -- Python 3.13.7, pytest-9.1.1, pluggy-1.6.0 -- C:\Hero\hero-backend\venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Hero\hero-backend
plugins: anyio-4.15.1
collecting ... collected 11 items

tests/test_step14_active.py::test_n01_deactivate_with_reason PASSED      [  9%]
tests/test_step14_active.py::test_n02_deactivate_without_reason_or_too_short PASSED [ 18%]
tests/test_step14_active.py::test_n03_deactivate_idempotent_twice PASSED [ 27%]
tests/test_step14_active.py::test_n04_get_documents_filtering PASSED     [ 36%]
tests/test_step14_active.py::test_n05_get_inactive_document_detail_and_pdf PASSED [ 45%]
tests/test_step14_active.py::test_n06_dashboard_and_category_tree PASSED [ 54%]
tests/test_step14_active.py::test_n07_duplicate_detection_matches_inactive PASSED [ 63%]
tests/test_step14_active.py::test_n08_reactivate_document PASSED         [ 72%]
tests/test_step14_active.py::test_n09_move_category_via_patch_metadata PASSED [ 81%]
tests/test_step14_active.py::test_n10_extraction_claim_ignores_inactive PASSED [ 90%]
tests/test_step14_active.py::test_n11_deactivate_non_existent_document PASSED [100%]

============================== warnings summary ===============================
venv\Lib\site-packages\fastapi\testclient.py:1
  C:\Hero\hero-backend\venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

venv\Lib\site-packages\starlette\testclient.py:53
  C:\Hero\hero-backend\venv\Lib\site-packages\starlette\testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================= 11 passed, 2 warnings in 20.63s =======================
```

---

## 5. Output Mentah Eksekusi Live Docker Compose & Dry-Run Skrip

### 5.1 Rebuild & Start Backend Container
```powershell
docker compose up -d --build backend ; Start-Sleep -Seconds 25
```
Output:
```
#1 [internal] load local bake definitions
#1 reading from stdin 512B done
#1 DONE 0.0s

#2 [internal] load build definition from Dockerfile
#2 transferring dockerfile: 825B 0.0s done
#2 DONE 0.1s

#3 [internal] load metadata for docker.io/library/python:3.11-slim
#3 DONE 2.6s

#4 [internal] load .dockerignore
#4 transferring context: 110B done
#4 DONE 0.0s

#5 [internal] load build context
#5 DONE 0.0s

#6 [1/7] FROM docker.io/library/python:3.11-slim@sha256:65bd3d9f1d7fa268dd1909973ba7eb4bdf41f6dcf2cfbe76ba9528b170f3fd79
#6 resolve docker.io/library/python:3.11-slim@sha256:65bd3d9f1d7fa268dd1909973ba7eb4bdf41f6dcf2cfbe76ba9528b170f3fd79 0.1s done
#6 DONE 0.1s

#5 [internal] load build context
#5 transferring context: 995.51kB 1.0s done
#5 DONE 1.1s

#7 [3/7] RUN apt-get update && apt-get install -y     gcc     libpq-dev     && rm -rf /var/lib/apt/lists/*
#7 CACHED

#8 [4/7] COPY requirements.txt .
#8 CACHED

#9 [2/7] WORKDIR /app
#9 CACHED

#10 [5/7] RUN pip install --no-cache-dir -r requirements.txt
#10 CACHED

#11 [6/7] COPY . .
#11 DONE 9.0s

#12 [7/7] RUN chmod +x scripts/entrypoint.sh
#12 DONE 0.8s

#13 exporting to image
#13 exporting layers
#13 exporting layers 18.9s done
#13 exporting manifest sha256:386dfe5baa7b64014f8a3edb841fae3fec5a84e6001959e8c9e415fe8328fb76 0.1s done
#13 exporting config sha256:cef8835113c6fa9ffa6b6580350c013f4ea442a3aff6be0147cb49ea38cd5796 0.1s done
#13 exporting attestation manifest sha256:5e9760bc45a452f8cfaedaf9a5f97faafdfb5c2e3ff2c403228d1b2e5822cb45 0.1s done
#13 exporting manifest list sha256:a5489c95daa4500697704ac15323ec9a8a7362749aac881c13065a9572f639a2
#13 exporting manifest list sha256:a5489c95daa4500697704ac15323ec9a8a7362749aac881c13065a9572f639a2 0.1s done
#13 naming to docker.io/library/hero-backend-backend:latest 0.0s done
#13 unpacking to docker.io/library/hero-backend-backend:latest
#13 unpacking to docker.io/library/hero-backend-backend:latest 6.2s done
#13 DONE 25.6s

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

### 5.2 Dry-Run: `periksa_konsistensi_pasal.py`
```powershell
docker compose exec backend python scripts/periksa_konsistensi_pasal.py
```
Output:
```
=========================================================================================================
                     LAPORAN PEMERIKSAAN KONSISTENSI PDF - PASAL
=========================================================================================================

[KELOMPOK A] Dokumen Aktif Tanpa Berkas PDF (0 dokumen):
  (Nihil - semua dokumen aktif memiliki berkas PDF di penyimpanan)

[KELOMPOK B] Dokumen Ber-PDF Tanpa Pasal (0 dokumen):
  (Nihil - tidak ada dokumen terindeks/perlu_koreksi tanpa pasal)

[KELOMPOK C] Pasal Yatim (0 grup dokumen, total 0 pasal):
  (Nihil - tidak ada pasal yatim)

---------------------------------------------------------------------------------------------------------
RINGKASAN JUMLAH:
  - Kelompok A (Tanpa PDF)         : 0 dokumen
  - Kelompok B (Ber-PDF tanpa pasal): 0 dokumen
  - Kelompok C (Pasal Yatim)       : 0 pasal pada 0 dokumen
---------------------------------------------------------------------------------------------------------
[DRY-RUN] Mode tinjauan saja. Tidak ada perubahan status atau antrean pada basis data.
=========================================================================================================
```

### 5.3 Dry-Run: `periksa_dokumen_non_utama.py`
```powershell
docker compose exec backend python scripts/periksa_dokumen_non_utama.py
```
Output:
```
=========================================================================================================
               PEMERIKSAAN DOKUMEN NON-UTAMA DI KNOWLEDGE BASE (KB)
               Mode: DRY-RUN (Hanya Tinjauan)
=========================================================================================================
ID     | Jenis        | Sumber Deteksi       | Judul (60 Karakter)                                          | Nama Berkas
---------------------------------------------------------------------------------------------------------
45     | abstrak      | kandidat/nama berkas | Pelaksanaan Penawaran Umum Efek Bersifat Utang dan/atau Suku | Abstrak PADK 11 Tahun 2026 Pelaksanaan Penawaran Umum Efek Bersifat Utang danatau Sukuk secara Elektronik.pdf
46     | faq          | kandidat/nama berkas | Pelaksanaan Penawaran Umum Efek Bersifat Utang dan/atau Suku | FAQ PADK 11 Tahun 2026 Pelaksanaan Penawaran Umum Efek Bersifat Utang danatau Sukuk secara Elektronik.pdf
47     | abstrak      | kandidat/nama berkas | Laporan Bulanan Perusahaan Pembiayaan dan Perusahaan Pembiay | Abstrak PADK 45-PADK06-2025 Laporan Bulanan Perusahaan Pembiayaan dan Perusahaan Pembiayaan Syariah.pdf
49     | abstrak      | kandidat/nama berkas | Perubahan Atas Surat Edaran Otoritas Jasa Keuangan Nomor 25/ | Abstrak SEOJK 23-SEOJK06-2025 Laporan Bulanan Perusahaan Modal Ventura dan Perusahaan Modal Ventura Syariah.pdf
50     | abstrak      | kandidat/nama berkas | Laporan Berkala Lembaga Penjamin                             | Abstrak POJK 11 Tahun 2026 Laporan Berkala Lembaga Penjamin.pdf
51     | faq          | kandidat/nama berkas | Perubahan Atas Surat Edaran Otoritas Jasa Keuangan Nomor 25/ | FAQ SEOJK 23-SEOJK06-2025 Laporan Bulanan Perusahaan Modal Ventura dan Perusahaan Modal Ventura Syariah.pdf
52     | faq          | kandidat/nama berkas | Laporan Berkala Lembaga Penjamin                             | FAQ POJK 11 Tahun 2026 Laporan Berkala Lembaga Penjamin.pdf
73     | abstrak      | kandidat/nama berkas | Penyelenggaraan Bursa Mineral dan Komoditas Strategis        | Abstrak POJK 16 Tahun 2026 Penyelenggaraan Bursa Mineral dan Komoditas Strategis.pdf
74     | faq          | nama berkas          | Penyelenggaraan Bursa Mineral dan Komoditas Strategis        | FAQ POJK 16 Tahun 2026 Penyelenggaraan Bursa Mineral dan Komoditas Strategis.pdf
76     | faq          | kandidat/nama berkas/judul | FAQ SEOJK 18-SEOJK.08-2024 Penilaian Sendiri Terhadap Pemenu | FAQ_20SEOJK_2018-SEOJK.08-2024_20Penilaian_20Sendiri_20Terhadap_20Pemenuhan_20Ketentuan_20Pelindungan_20Konsumen_20dan_20Mas.pdf
81     | abstrak      | kandidat/nama berkas/judul | Abstrak SEOJK 19-SEOJK06-2025 Penyelenggaraan Layanan Pendan | Abstrak_20SEOJK_2019-SEOJK06-2025_20Penyelenggaraan_20Layanan_20Pendanaan_20Bersama_20Berbasis_20Teknologi_20Informasi.pdf
87     | faq          | kandidat/nama berkas/judul | FAQ PADK 2 Tahun 2026 Penyelenggaraan Beli Sekarang Bayar Na | FAQ_20PADK_202_20Tahun_202026_20Penyelenggaraan_20Beli_20Sekarang_20Bayar_20Nanti_20_28Buy_20Now_20Pay_20Later_29_20Bagi_20P.pdf
88     | abstrak      | kandidat/nama berkas/judul | Abstrak POJK 16 Tahun 2024 Pengawasan PT Sarana Multi Infras | Abstrak_20POJK_2016_20Tahun_202024_20Pengawasan_20PT_20Sarana_20Multi_20Infrastruktur_20_Persero_.pdf
90     | abstrak      | kandidat/nama berkas/judul | Abstrak POJK 9 Tahun 2024 Penerapan Tata Kelola bagi BPR dan | Abstrak_20POJK_209_20Tahun_202024_20Penerapan_20Tata_20Kelola_20bagi_20BPR_20dan_20BPRS.pdf
---------------------------------------------------------------------------------------------------------
Total Dokumen Ditemukan : 14 (abstrak: 8, faq: 6, lampiran: 0, non_regulasi: 0)

---------------------------------------------------------------------------------------------------------
DOKUMEN DILEWATI (Koreksi Manual - Terindikasi Sengaja Dimasukkan Admin): 1
ID     | Jenis        | Sumber Deteksi       | Judul (60 Karakter)                                          | Dibuat / Dikoreksi
---------------------------------------------------------------------------------------------------------
48     | faq          | kandidat/nama berkas | Laporan Bulanan Perusahaan Pembiayaan dan Perusahaan Pembiay | 2026-10-05T16:21:48.656459+00:00
---------------------------------------------------------------------------------------------------------

[DRY-RUN] Tidak ada data dokumen yang diubah. Jalankan dengan --apply untuk menonaktifkan.
=========================================================================================================
```

### 5.4 Dry-Run: `tarik_semua.py`
```powershell
docker compose exec backend python scripts/tarik_semua.py --base-url http://127.0.0.1:8000
```
Output:
```
Autentikasi: Tidak ada HERO_API_TOKEN (mode anonim/dev)
Regulasi OJK (Situs Resmi) | sesi #12 | perlu ditarik: 2 (utama 2, dilewati non-utama 12: abstrak 6, faq 6, lampiran 0, non_regulasi 0) | sudah ada di KB: 14
[LEWATI] JDIH OJK (Situs Resmi) | tidak ada sesi scan siap — jalankan scan dulu
OneDrive Public DPEA | sesi #8 | perlu ditarik: 2265 (utama 2265, dilewati non-utama 312: abstrak 154, faq 155, lampiran 3, non_regulasi 0) | sudah ada di KB: 15
uji_folder | sesi #16 | perlu ditarik: 0 (utama 0, dilewati non-utama 0: abstrak 0, faq 0, lampiran 0, non_regulasi 0) | sudah ada di KB: 2
demo_ojk_peraturan | sesi #18 | perlu ditarik: 0 (utama 0, dilewati non-utama 0: abstrak 0, faq 0, lampiran 0, non_regulasi 0) | sudah ada di KB: 5

==========================================================================================
                    RINGKASAN PENARIKAN HASIL SCAN KE KB
                    Mode: DRY-RUN (Hanya Tinjauan)
==========================================================================================
Sumber                       | Sesi   | Perlu Ditarik (Baru / Ulang)   | Di KB  | Catatan
------------------------------------------------------------------------------------------
Regulasi OJK (Situs Resmi)   | #12    | 2 (baru 2, ulang 0)            | 14     | dry-run
JDIH OJK (Situs Resmi)       | -      | 0 (baru 0, ulang 0)            | 0      | tidak ada sesi scan siap — jalankan scan dulu
OneDrive Public DPEA         | #8     | 2265 (baru 2265, ulang 0)      | 15     | dry-run
uji_folder                   | #16    | 0 (baru 0, ulang 0)            | 2      | dry-run
demo_ojk_peraturan           | #18    | 0 (baru 0, ulang 0)            | 5      | dry-run

------------------------------------------------------------------------------------------
Metrik Corong                        | Sebelum      | Sesudah      | Perubahan
------------------------------------------------------------------------------------------
Total Dokumen di KB                  | 94           | 94           | +0
Total Scan Belum Ditarik             | 3134         | 3134         | +0
==========================================================================================
RINGKASAN: 5 sumber diproses | Perlu Ditarik: 2267 | Dilewati Non-Utama: 324 | Mode: DRY-RUN (tidak ada berkas ditarik)
```

---

## 6. Catatan Koordinasi

### Catatan untuk Pipeline / Infra (Fathir)
1. **Penentuan Dokumen Utama & Lampiran**:
   - Berkas yang diawali nama peraturan (misalnya `"POJK 5 2024 - Lampiran I.pdf"` atau `"SEOJK tentang Pedoman Pengisian Lampiran Laporan Bulanan"`) **kini dianggap dokumen utama** kecuali jika label pada halaman sumber/situs secara eksplisit bernilai `"Lampiran"`.
   - Logika ini memastikan berkas salinan regulasi utama yang memuat kata "lampiran" di tengah judul tidak terbuang atau terlewat saat penarikan ke Knowledge Base.
2. **Penarikan Otomatis UAT**:
   - Skrip `scripts/tarik_semua.py` secara default menyaring seluruh berkas `abstrak`, `faq`, `lampiran`, dan `non_regulasi`. Pada dry-run live di atas, sebanyak 324 berkas non-utama berhasil dilewati secara otomatis.
   - Bila ingin menarik seluruh berkas termasuk non-utama, tambahkan flag `--termasuk-non-utama`.
3. **Pembersihan Rutin KB**:
   - Jalankan `docker compose exec backend python scripts/periksa_dokumen_non_utama.py --apply` untuk menonaktifkan 14 dokumen non-utama yang telanjur masuk ke KB pada pengujian awal.
   - Jalankan `docker compose exec backend python scripts/periksa_konsistensi_pasal.py` untuk memantau integritas berkas PDF dan kelengkapan pasal regulasi.
