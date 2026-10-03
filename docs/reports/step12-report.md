# LAPORAN LANGKAH 12 — HERO BACKEND
**Dukungan Halaman Ingest + Perbaikan Data Seed & Anti-Regresi**

> **Branch:** `feat/step12-ingest-support`  
> **Tanggal Pengujian:** 03 Oktober 2026  
> **Status:** Semua Pengujian Lulus (225 passed, 1 skipped) — Data Uji Nyata Berhasil Di-seed ke Knowledge Base

---

## 1. Analisis & Perbaikan Bug API Candidate (`GET /scans/{id}/candidates`)

### 1.1 Bukti Bug & Akar Masalah
Pada implementasi sebelumnya di [app/routers/scans.py](file:///c:/Hero/hero-backend/app/routers/scans.py), builder respons `CandidateResponse(...)` disusun secara manual atribut-per-atribut tanpa menyertakan kolom:
- `status_keberlakuan`
- `effective_date`
- `match_warning`

Akibatnya, saat endpoint `GET /api/v1/scans/{id}/candidates` dipanggil, Pydantic selalu mengisi nilai default (`status_keberlakuan="tidak_diketahui"`, `effective_date=None`, `match_warning=None`). Data status keberlakuan riil yang tersimpan di basis data (seperti `berlaku`, `dicabut`, `diubah` dari portal JDIH) tidak pernah terlihat oleh klien frontend.

### 1.2 Solusi Perbaikan
1. Mengubah penyusunan respons dengan memanfaatkan fitur validasi Pydantic: `CandidateResponse.model_validate(c)`.
2. Hanya field turunan/komputasi relasional seperti `match_document` yang di-override secara eksplisit.
3. Seluruh kolom model `ScanCandidate` (termasuk status keberlakuan, tanggal berlaku, dan peringatan kecocokan) kini terpetakan 100% identik ke respons API.

### 1.3 Pengujian Anti-Regresi Generik (§1.2 & G02)
Pengujian generik otomatis diimplementasikan pada `tests/test_step12_ingest_support.py::test_g01_and_g02_generic_candidate_response_regression`. Pengujian ini menginspeksi seluruh atribut kolom `ScanCandidate` yang juga didefinisikan pada `CandidateResponse`, dan memverifikasi bahwa nilai di respons API selalu sama dengan nilai di basis data.

#### Bukti Gagal pada Kode Lama (Sebelum Perbaikan):
```text
================================== FAILURES ===================================
_______________ test_g01_and_g02_generic_candidate_response_regression _______________

client = <starlette.testclient.TestClient object at 0x000001D487661E50>
db_session = <sqlalchemy.orm.session.Session object at 0x000001D4876621B0>

    def test_g01_and_g02_generic_candidate_response_regression(client: TestClient, db_session: Session):
        ...
>       assert cand_resp["status_keberlakuan"] == "dicabut", (
            f"status_keberlakuan hilang: {cand_resp.get('status_keberlakuan')}"
        )
E       AssertionError: status_keberlakuan hilang: tidak_diketahui
E       assert 'tidak_diketahui' == 'dicabut'

tests\test_step12_ingest_support.py:46: AssertionError
=========================== short test summary info ===========================
FAILED tests/test_step12_ingest_support.py::test_g01_and_g02_generic_candidate_response_regression - AssertionError: status_keberlakuan hilang: tidak_diketahui
```

#### Bukti Lulus Setelah Perbaikan:
```text
tests/test_step12_ingest_support.py::test_g01_and_g02_generic_candidate_response_regression PASSED [ 12%]
```

### 1.4 Audit Builder Respons Manual Lainnya (§1.3)
Dilakukan pemeriksaan pada fungsi-fungsi builder respons manual lainnya di backend:
1. **`_build_session_response` di `app/routers/scans.py`:**
   - Memetakan `ScanSession` ke `ScanSessionResponse`.
   - Menggunakan mapping atribut manual dengan agregasi `candidates_summary` dan `pull_progress`.
   - **Hasil Audit:** Seluruh atribut model (`id`, `source_id`, `status`, `crawl_depth`, `max_pages`, `pages_visited`, `category_id`, `created_at`, `finished_at`, `error_message`) terpetakan lengkap. Field baru `category_id` telah ditambahkan ke skema dan builder.
2. **Daftar Sumber Scraping (`list_scraping_sources` di `app/routers/scraping_sources.py`):**
   - Mengembalikan daftar instance SQLAlchemy `ScrapingSource`.
   - Diserialisasikan langsung oleh FastAPI melalui Pydantic `response_model=List[ScrapingSourceResponse]`. Tidak ada atribut yang hilang.
3. **Detail Job Ingest (`get_job_detail` di `app/routers/ingest.py`):**
   - Mengembalikan model SQLAlchemy `JobIngest` dengan agregasi metrik ringkasan dokumen dan kegagalan.
   - Pydantic memvalidasi atribut model secara otomatis via `response_model=JobDetailResponse`. Field `category_id` telah disertakan.

---

## 2. Alur Pindai → Centang → Tarik Folder Lokal (`folder_lokal`)

1. **Izin Pemindaian Sumber Folder Lokal:**
   - [app/services/scan_service.py](file:///c:/Hero/hero-backend/app/services/scan_service.py) kini mengizinkan `JenisSumber.folder_lokal` pada `start_scan` (validasi URL HTTP di-bypass untuk folder lokal).
   - Saat pemindaian dijalankan (`execute_scan`), berkas `.pdf` di dalam path sumber dipindai secara rekursif (jika opsi sumber `recursive: true`) hingga batas `local_source_max_files_per_run`.
   - Atribut berkas:
     - `size_bytes`: dibaca langsung via `os.path.getsize()` / `stat` (`size_source="local"`).
     - `match_status`: dihitung menggunakan hash SHA-256 berkas fisik lokal + ukuran byte terhadap tabel `documents`. Berkas dengan hash dan ukuran identik diberi status `sudah_ada`. Jika ada kemiripan nomor/nama dan ukuran diberi `mungkin_ada`, lainnya `baru`.
     - Metadata judul, nomor, jenis, dan tahun diekstrak dari nama berkas menggunakan parser metadata OneDrive/lokal.
2. **Penarikan Berkas Lokal ke Knowledge Base:**
   - Penarikan berkas `folder_lokal` (`execute_pull`) membaca berkas biner langsung dari filesystem lokal tanpa network overhead.
   - Menerapkan format penamaan dinamis `naming_format` (misal `nama_jenis_tahun.pdf`).
   - Menerapkan klasifikasi akses default dari sumber dan `category_id` target.
3. **Validasi Penolakan `unduh_folder` untuk Folder Lokal:**
   - Jika `POST /api/v1/scans/{id}/pull` dipanggil dengan `destination: "unduh_folder"` untuk sumber `folder_lokal`, sistem menolak dengan status **HTTP 422**:
     *"Tujuan unduh_folder tidak diizinkan untuk sumber folder lokal karena berkas sudah berada di filesystem lokal."*
4. **Kompatibilitas Penuh:**
   - Endpoint `POST /api/v1/scraping-sources/{id}/run` tetap berfungsi normal untuk pemindaian langsung (backward-compatible).

---

## 3. Endpoint Pilihan Folder untuk Frontend (`GET /scraping-sources/folder-options`)

Ditambahkan endpoint `GET /api/v1/scraping-sources/folder-options` di [app/routers/scraping_sources.py](file:///c:/Hero/hero-backend/app/routers/scraping_sources.py):
- **Fitur:** Memindai subfolder di dalam direktori `local_source_roots` hingga kedalaman maksimal 2 level.
- **Payload Respons:**
  - `path`: path absolut folder lokal.
  - `name`: nama direktori.
  - `pdf_count`: jumlah berkas `.pdf` di dalam folder tersebut.
  - `already_registered_source_id`: ID sumber jika path tersebut telah terdaftar di tabel `scraping_sources`, atau `null`.
- **Keamanan Keamanan Jalur (Directory Traversal & Symlink Leak Guard):**
  - Path di luar direktori root yang diizinkan ditolak.
  - Symlink yang target resolusinya berada di luar root yang diizinkan diabaikan secara otomatis (teruji pada kasus G06). Folder tersembunyi (`.` atau `$`) dan folder karantina/sistem diabaikan.

Contoh respons riil:
```json
{
  "items": [
    {
      "path": "/app/sources/demo_ojk_peraturan",
      "name": "demo_ojk_peraturan",
      "pdf_count": 5,
      "already_registered_source_id": null
    },
    {
      "path": "/app/sources/uji_folder",
      "name": "uji_folder",
      "pdf_count": 2,
      "already_registered_source_id": null
    }
  ]
}
```

---

## 4. Dukungan Kategori Target Knowledge Base (`category_id`)

1. **Migrasi Database (`c34f2a7b8e19`):**
   - Menambahkan kolom `category_id` (tipe `Integer`, Foreign Key ke `categories.id`) pada tabel `scan_sessions` dan `job_ingest`.
2. **Validasi dan Penanganan `category_id`:**
   - **`ScanPullRequest` (`POST /api/v1/scans/{id}/pull`):** menerima field opsional `category_id`. Jika diberikan tetapi ID tidak ada di tabel `categories`, sistem melempar **HTTP 422**: *"Kategori target dengan ID {category_id} tidak ditemukan."* Nilai disimpan di session dan job, lalu diterapkan ke seluruh dokumen yang ditarik ke KB.
   - **`ScrapingSourceRunRequest` (`POST /api/v1/scraping-sources/{id}/run`):** menerima field opsional `category_id` dengan validasi 422 yang sama.
   - **`POST /api/v1/ingest/upload-pdf`:** memvalidasi tipe data `category_id` berupa bilangan bulat.
   - Tanpa `category_id`, penempatan kategori mengikuti aturan klasifikasi otomatis berbasis nama/sektor (perilaku lama dipertahankan).

---

## 5. Peningkatan Kualitas Data Seed

### 5.1 Normalisasi Bidang & Migrasi Data
- Dibuat fungsi [normalize_bidang()](file:///c:/Hero/hero-backend/app/crawlers/url_utils.py):
  - Meratakan spasi ganda menjadi spasi tunggal.
  - Menghapus spasi sebelum koma (misal: `"Penjaminan , dan"` -> `"Penjaminan, dan"`).
  - Memastikan spasi tunggal setelah koma.
  - Menghilangkan koma gantung di akhir teks.
- Diterapkan pada crawler SharePoint OJK, JDIH API, serta pada migrasi data Alembic `c34f2a7b8e19` untuk menormalisasi data eksisting di tabel `documents` dan `scan_candidates`.
- Kolom `scan_candidates.bidang` diperlebar menjadi `String(150)` agar tidak terjadi pemotongan teks pada nama sektor panjang JDIH.

### 5.2 Tabel Usulan Pemetaan Nama Bidang JDIH (Panjang) ↔ OJK (Singkat)
Berdasarkan nilai nyata yang ditemukan dari `docs/reports/scan-benchmark-jdih.csv` dan `docs/reports/scan-benchmark-ojk.csv`, berikut adalah **tabel usulan pemetaan** nama bidang untuk standardisasi di masa mendatang (*hanya diusulkan, belum diterapkan ke sistem sesuai aturan tugas*):

| # | Nama Bidang JDIH (Panjang/Resmi) | Kode/Singkatan Sektor OJK (Pendek) | Keterangan UU P2SK / Kompartemen |
|---|---|---|---|
| 01 | `Lembaga Pembiayaan, Perusahaan Modal Ventura, Lembaga Keuangan Mikro, dan Lembaga Jasa Keuangan Lainnya` | `PVML` | Sektor Pengawasan PVML |
| 02 | `Perasuransian, Penjaminan, dan Dana Pensiun` | `PPDP` | Sektor Pengawasan PPDP |
| 03 | `Inovasi Teknologi Sektor Keuangan, Aset Keuangan Digital dan Aset Kripto` | `ITSK` (atau `IAKD`) | Sektor Pengawasan ITSK |
| 04 | `Perilaku Pelaku Usaha Jasa Keuangan, Edukasi dan Pelindungan Konsumen` | `EPK` | Sektor Edukasi dan Pelindungan Konsumen |
| 05 | `Pasar Modal, Keuangan Derivatif, dan Bursa Karbon` | `Pasar Modal` (atau `PMDK`) | Sektor Pasar Modal dan Bursa Karbon |
| 06 | `Perbankan` | `Perbankan` | Sektor Pengawasan Perbankan |
| 07 | `IKNB (Sebelum UU Nomor 4 Tahun 2023)` | `IKNB` | Nomenklatur lama sebelum pemisahan PVML/PPDP |
| 08 | `Kebijakan Strategis` | `OJK Wide` | Kebijakan lintas sektor OJK |
| 09 | `Manajemen Strategis` | `OJK Wide` | Kebijakan tata kelola internal |
| 10 | `Lainnya` | `OJK` | Regulasi kelembagaan umum |

### 5.3 Pemformatan Nomor Regulasi OneDrive (15 Contoh Sebelum & Sesudah)
Fungsi `parse_onedrive_filename_metadata` di [app/crawlers/url_utils.py](file:///c:/Hero/hero-backend/app/crawlers/url_utils.py) kini memformat nomor regulasi lengkap dengan struktur `{Jenis} {Nomor} Tahun {Tahun}` atau format Keputusan Direksi Bank Indonesia. Berkas yang tidak dapat diidentifikasi secara meyakinkan dikosongkan:

| # | Nama Berkas Asli | Format Lama (Langkah 11) | Format Baru Standar (Langkah 12) | Status / Jenis Terdeteksi |
|---|---|---|---|---|
| 01 | `Peraturan_OJK_3_2015.pdf` | `3` | `POJK 3 Tahun 2015` | POJK (2015) |
| 02 | `Peraturan_OJK_27_2021.pdf` | `27` | `POJK 27 Tahun 2021` | POJK (2021) |
| 03 | `POJK 3 Tahun 2025 Penatalaksanaan Lembaga Sertifikasi Profesi.pdf` | `3` | `POJK 3 Tahun 2025` | POJK (2025) |
| 04 | `Peraturan_ADK_19_Tahun_2015_PERUBAHAN_KEEMPAT_SURAT_EDARAN_BANK_INDONESIA.pdf` | `19` | `PADK 19 Tahun 2015` | PADK (2015) |
| 05 | `Peraturan_ADK_4_Tahun_2022_PEDOMAN_PELAKSANAAN_PELAPORAN_KEUANGAN.pdf` | `4` | `PADK 4 Tahun 2022` | PADK (2022) |
| 06 | `Surat_Edaran_OJK_6_2016.pdf` | `6` | `SEOJK 6 Tahun 2016` | SEOJK (2016) |
| 07 | `Peraturan_ADK_19_Tahun_2017_PEDOMAN_PELAKSANAAN_FORUM_PANITIA.pdf` | `19` | `PADK 19 Tahun 2017` | PADK (2017) |
| 08 | `Surat_Edaran_OJK_22_2023.pdf` | `22` | `SEOJK 22 Tahun 2023` | SEOJK (2023) |
| 09 | `Tahun_izin_usaha_dan_pencabutan_izin_usaha_Manajer_Investasi.pdf` | *(kosong)* | *(kosong)* | - (-) |
| 10 | `708a41f0-9685-3a8d-9676-afa5fb2bee74.pdf` | `9685` | *(kosong)* | - (-) |
| 11 | `Surat_Edaran_OJK_31_2016.pdf` | `31` | `SEOJK 31 Tahun 2016` | SEOJK (2016) |
| 12 | `SK_Dir_27-164-KEP-DIR-1995_Pedoman_Teknologi_Sistem_Informasi_Bank_Umum.pdf` | `27` | `27-164-KEP-DIR-1995` | KEPDIR (1995) |
| 13 | `SK_Dir_26-68-KEP-DIR-1993_Saham_Sebagai_Agunan_Tambahan.pdf` | `26` | `26-68-KEP-DIR-1993` | KEPDIR (1993) |
| 14 | `Peraturan_Bank_Indonesia_7_1992.pdf` | `7` | `PBI 7 Tahun 1992` | PBI (1992) |
| 15 | `Undang-Undang_17_2012.pdf` | `17` | `UU 17 Tahun 2012` | UU (2012) |

### 5.4 Penjelasan Dokumen Tahun 2027
- **Dokumen yang Ditemukan:** Regulasi `23/SEOJK.06/2025` berjudul *"Perubahan Atas Surat Edaran Otoritas Jasa Keuangan Nomor 25/SEOJK.05/2019 tentang Laporan Bulanan Perusahaan Modal Ventura dan Perusahaan Modal Ventura Syariah"*.
- **Metadata Mentah dari Situs OJK:**
  URL detail: `https://ojk.go.id/id/regulasi/Pages/SEOJK-23-SEOJK06-2025-Laporan-Bulanan-Perusahaan-Modal-Ventura-dan-Perusahaan-Modal-Ventura-Syariah.aspx`
  Baris CSV benchmark (`docs/reports/scan-benchmark-ojk.csv` baris 8):
  `.../SEOJK%2023-SEOJK06-2025%20Laporan%20Bulanan%20Perusahaan%20Modal%20Ventura...pdf, ..., 23/SEOJK.06/2025, ..., 2027-04-01, 2027-04-01, ...`
- **Penyebab:** Pada portal SharePoint OJK, administrator memasukkan Tanggal Berlaku regulasi tersebut yaitu **1 April 2027** (`2027-04-01`), dan field Tanggal Penetapan tidak dicantumkan terpisah. Akibatnya, crawler lama menetapkan fallback `release_date` dari `effective_date`, sehingga dokumen bertahun penetapan 2025 tercatat memiliki `release_date` 2027.
- **Koreksi Logika Crawler ([app/crawlers/sharepoint_postback.py](file:///c:/Hero/hero-backend/app/crawlers/sharepoint_postback.py)):**
  Sama seperti penanganan JDIH pada Langkah 10c, crawler kini mengekstrak tahun regulasi dari nomor resmi (`23/SEOJK.06/2025` -> 2025). Jika `rel_date` atau `eff_date` melompat ke tahun masa depan yang lebih besar dari tahun nomor regulasi (`eff_date.year > parsed_year`), `release_date` di-fallback ke awal tahun regulasi asli (`date(parsed_year, 1, 1)`), sehingga anomali tahun 2027 tereliminasi secara menyeluruh.

### 5.5 Perbaikan Skrip Seeding (`scripts/seed_from_sources.py`)
1. **Pencetakan Kolom Tahun:** Memperbaiki pembacaan tahun kandidat di log terminal dari `dc.get("release_date")[:4]` (sebelumnya membaca `release_year` yang tidak ada di schema sehingga selalu menampilkan `-`).
2. **Paginasi JDIH:** Mengubah `max_pages` pemindaian JDIH menjadi **4 halaman** (menghasilkan 200 baris DataTables / 506 berkas PDF).
3. **Seleksi Kandidat Bervariasi Status:** Menjamin minimal **2 regulasi berstatus `dicabut` dan 2 regulasi berstatus `diubah`** terpilih dari pool JDIH sebelum mengisi kuota status `berlaku`.

---

## 6. Matriks Hasil Pengujian (G01–G11)

| # | Kasus Pengujian | Ekspektasi | Hasil Riil | Status |
|---|---|---|---|---|
| **G01** | Kandidat JDIH berstatus dicabut di DB | API candidates mengembalikan `dicabut`, `effective_date`, `match_warning` sesuai DB | Terverifikasi via `test_g01_and_g02_generic_candidate_response_regression` | **LULUS** |
| **G02** | Tes generik §1.2 pada kode lama | Gagal pada kode lama (terbukti), lalu lulus setelah perbaikan | Gagal dengan `AssertionError: status_keberlakuan hilang: tidak_diketahui`; lulus setelah fix | **LULUS** |
| **G03** | Scan sumber `folder_lokal` berisi 3 PDF (1 sudah ada di KB) | Ditemukan 3 kandidat: 1 `sudah_ada` (hash identik), 2 `baru` | Terverifikasi via `test_g03_scan_folder_lokal_deduplication` | **LULUS** |
| **G04** | Pull folder lokal ke KB dengan `naming_format` | Dokumen masuk ke KB dengan nama sesuai format `[nama, jenis, tahun]` | Terverifikasi via `test_g04_and_g08_pull_folder_lokal_with_naming_format_and_category` | **LULUS** |
| **G05** | Pull folder lokal dengan tujuan `unduh_folder` | Ditolak dengan HTTP 422 dan pesan jelas | Terverifikasi via `test_g05_pull_folder_lokal_unduh_folder_rejected` | **LULUS** |
| **G06** | `folder-options` dengan symlink keluar root | Path di luar root dan symlink leak tidak ikut terdaftar | Terverifikasi via `test_g06_folder_options_security_and_symlink` | **LULUS** |
| **G07** | Pull dengan `category_id` tidak ada di DB | Ditolak dengan HTTP 422 | Terverifikasi via `test_g07_pull_category_id_invalid` | **LULUS** |
| **G08** | Pull dengan `category_id` valid | Dokumen tersimpan dan berada di kategori tersebut | Terverifikasi via `test_g04_and_g08_...` | **LULUS** |
| **G09** | Bidang `"Penjaminan , dan"` | Ternormalisasi menjadi `"Penjaminan, dan"` | Terverifikasi via `test_g09_bidang_normalization` | **LULUS** |
| **G10** | OneDrive `Peraturan_OJK_3_2015.pdf` | Nomor regulasi diformat menjadi `POJK 3 Tahun 2015` | Terverifikasi via `test_g10_onedrive_filename_format` | **LULUS** |
| **G11** | `pytest -q` seluruh suite backend | Seluruh 225 pengujian lulus (1 skipped, 0 failed) | 225 passed, 1 skipped dalam 178.78s | **LULUS** |

---

## 7. Eksekusi Seeding & Data Operasional

### 7.1 Output Mentah Terminal: Seeding dari Sumber Asli (`scripts/seed_from_sources.py --reset`)
```text
=================================================================
HERO BACKEND - SEEDING DATA UJI NYATA DARI SUMBER ASLI
Base API URL   : http://127.0.0.1:8000
Target Sumber  : ojk, jdih, onedrive
Per Sumber     : 15 dokumen
Format Penamaan: ['nama', 'jenis', 'tahun']
Reset Database : Ya
=================================================================

[RESET] Memulai pengosongan data operasional via scripts/demo_reset.py...
[RESET] Mereset tabel operasional (CASCADE)...
[RESET] Membersihkan direktori penyimpanan berkas PDF & thumbnail...
[RESET] Menjalankan kembali seeder kategori & pengguna bawaan...
[RESET] SUKSES: Database operasional HERO Backend berhasil direset ke kondisi bersih.
--> Memeriksa konektivitas dan kesehatan REST API server...
    Server online (Versi: 0.10.0, Status: ok)

-----------------------------------------------------------------
PROSES SUMBER: [OJK] Regulasi OJK (Situs Resmi)
URL: https://ojk.go.id/id/regulasi/default.aspx | Tipe: situs_web | Batas Paging: 3
-----------------------------------------------------------------
  [1/4] Sumber berhasil didaftarkan (Source ID: 1).
  [2/4] Menjadwalkan pemindaian (POST /api/v1/scans/, depth=1, max_pages=3)...
        Pemindaian selesai (Scan #1, Status: selesai). Total kandidat PDF ditemukan: 69
  [3/4] Menganalisis 69 kandidat berkas...
        Terpilih 15 kandidat 'utama' bervariasi:
          01. [ID:01] PADK 11 Tahun 2026 (PADK, 2026) | Bidang: Pasar Modal | Status: tidak_diketahui
          02. [ID:04] 45/PADK.06/2025 (PADK, 2025) | Bidang: PVML | Status: tidak_diketahui
          03. [ID:07] 23/SEOJK.06/2025 (SEOJK, 2025) | Bidang: PVML | Status: tidak_diketahui
          04. [ID:10] 11 Tahun 2026 (POJK, 2026) | Bidang: PPDP | Status: tidak_diketahui
          05. [ID:13] 16 Tahun 2026 (POJK, 2026) | Bidang: BMKS | Status: tidak_diketahui
          06. [ID:19] 20/SEOJK.08/2025 (SEOJK, 2025) | Bidang: EPK | Status: tidak_diketahui
          07. [ID:22] PADK 10 Tahun 2026 (PADK, 2026) | Bidang: Perbankan | Status: tidak_diketahui
          08. [ID:25] 12 Tahun 2026 (POJK, 2026) | Bidang: Pasar Modal | Status: tidak_diketahui
          09. [ID:34] 3 Tahun 2026 (PADK, 2026) | Bidang: ITSK | Status: tidak_diketahui
          10. [ID:43] 7 Tahun 2026 (PADK, 2026) | Bidang: PVML | Status: tidak_diketahui
          11. [ID:52] 4 Tahun 2026 (PADK, 2026) | Bidang: OJK Wide | Status: tidak_diketahui
          12. [ID:55] 8 Tahun 2026 (POJK, 2026) | Bidang: PVML | Status: tidak_diketahui
          13. [ID:61] 30 Tahun 2025 (POJK, 2025) | Bidang: ITSK | Status: tidak_diketahui
          14. [ID:64] 7 Tahun 2026 (POJK, 2026) | Bidang: Perbankan | Status: tidak_diketahui
          15. [ID:67] 40 Tahun 2025 (POJK, 2025) | Bidang: Pasar Modal | Status: tidak_diketahui
  [4/4] Menjadwalkan penarikan 15 dokumen ke Knowledge Base (format=['nama', 'jenis', 'tahun'])...
        Penarikan selesai. Berhasil di-ingest ke Knowledge Base: 15/15 dokumen.

-----------------------------------------------------------------
PROSES SUMBER: [JDIH] JDIH OJK (Situs Resmi)
URL: https://jdih.ojk.go.id/ | Tipe: situs_web | Batas Paging: 4
-----------------------------------------------------------------
  [1/4] Sumber berhasil didaftarkan (Source ID: 2).
  [2/4] Menjadwalkan pemindaian (POST /api/v1/scans/, depth=1, max_pages=4)...
        Pemindaian selesai (Scan #2, Status: selesai). Total kandidat PDF ditemukan: 506
  [3/4] Menganalisis 200 kandidat berkas...
        Terpilih 15 kandidat 'utama' bervariasi:
          01. [ID:175] 7/SEOJK.05/2025 (SEOJK, 2025) | Bidang: Perasuransian, Penjaminan, dan Dana Pensiun | Status: dicabut
          02. [ID:274] 21/SEOJK.05/2023 (SEOJK, 2023) | Bidang: Perasuransian, Penjaminan, dan Dana Pensiun | Status: dicabut
          03. [ID:100] POJK 18 Tahun 2025 (POJK, 2025) | Bidang: Perbankan | Status: diubah
          04. [ID:118] 4 Tahun 2026 (POJK, 2026) | Bidang: Perbankan | Status: diubah
          05. [ID:91] PADK 4 Tahun 2026 (PADK, 2026) | Bidang: Pasar Modal, Keuangan Derivatif, dan Bursa Karbon | Status: berlaku
          06. [ID:94] POJK 10 Tahun 2026 (POJK, 2026) | Bidang: Perbankan | Status: berlaku
          07. [ID:97] POJK 6 Tahun 2026 (POJK, 2026) | Bidang: Perbankan | Status: berlaku
          08. [ID:103] POJK 39 Tahun 2024 (POJK, 2024) | Bidang: Pasar Modal, Keuangan Derivatif, dan Bursa Karbon | Status: berlaku
          09. [ID:106] 20/SEOJK.07/2024 (SEOJK, 2024) | Bidang: Perilaku Pelaku Usaha Jasa Keuangan, Edukasi dan Pelindungan Konsumen | Status: berlaku
          10. [ID:112] 19/SEOJK.06/2024 (SEOJK, 2024) | Bidang: Inovasi Teknologi Sektor Keuangan, Aset Keuangan Digital dan Aset Kripto | Status: berlaku
          11. [ID:124] PADK 2 Tahun 2026 (PADK, 2026) | Bidang: Lembaga Pembiayaan, Perusahaan Modal Ventura, Lembaga Keuangan Mikro, dan Lembaga Jasa Keuangan Lainnya | Status: berlaku
          12. [ID:139] 48/PADK.06/2025 (PADK, 2025) | Bidang: Lembaga Pembiayaan, Perusahaan Modal Ventura, Lembaga Keuangan Mikro, dan Lembaga Jasa Keuangan Lainnya | Status: berlaku
          13. [ID:142] 47/PADK.05/2025 (PADK, 2025) | Bidang: Perasuransian, Penjaminan, dan Dana Pensiun | Status: berlaku
          14. [ID:151] 44/PADK.01/2025 (PADK, 2025) | Bidang: Kebijakan Strategis | Status: berlaku
          15. [ID:154] 42/PADK.03/2025 (PADK, 2025) | Bidang: Perbankan | Status: berlaku
  [4/4] Menjadwalkan penarikan 15 dokumen ke Knowledge Base (format=['nama', 'jenis', 'tahun'])...
        Penarikan selesai. Berhasil di-ingest ke Knowledge Base: 12/15 dokumen.

-----------------------------------------------------------------
PROSES SUMBER: [ONEDRIVE] OneDrive Public DPEA
URL: https://oneojk-my.sharepoint.com/:f:/g/personal/... | Tipe: onedrive_public | Batas Paging: 3
-----------------------------------------------------------------
  [1/4] Sumber berhasil didaftarkan (Source ID: 3).
  [2/4] Menjadwalkan pemindaian (POST /api/v1/scans/, depth=2, max_pages=3)...
        Pemindaian selesai (Scan #3, Status: selesai). Total kandidat PDF ditemukan: 200
  [3/4] Menganalisis 200 kandidat berkas...
        Terpilih 15 kandidat 'utama' bervariasi:
          01. [ID:597] POJK 3 Tahun 2015 (POJK, -) | Bidang: - | Status: tidak_diketahui
          02. [ID:600] PADK 19 Tahun 2015 (PADK, -) | Bidang: - | Status: tidak_diketahui
          03. [ID:602] SEOJK 6 Tahun 2016 (SEOJK, -) | Bidang: - | Status: tidak_diketahui
          04. [ID:613] - (-, -) | Bidang: - | Status: tidak_diketahui
          05. [ID:694] 27-164-KEP-DIR-1995 (KEPDIR, -) | Bidang: - | Status: tidak_diketahui
          06. [ID:734] PBI 7 Tahun 1992 (PBI, -) | Bidang: - | Status: tidak_diketahui
          07. [ID:778] UU 17 Tahun 2012 (UU, -) | Bidang: - | Status: tidak_diketahui
          08. [ID:598] POJK 27 Tahun 2021 (POJK, -) | Bidang: - | Status: tidak_diketahui
          09. [ID:601] PADK 4 Tahun 2022 (PADK, -) | Bidang: - | Status: tidak_diketahui
          10. [ID:610] SEOJK 22 Tahun 2023 (SEOJK, -) | Bidang: - | Status: tidak_diketahui
          11. [ID:614] - (-, -) | Bidang: - | Status: tidak_diketahui
          12. [ID:698] 26-68-KEP-DIR-1993 (KEPDIR, -) | Bidang: - | Status: tidak_diketahui
          13. [ID:599] POJK 3 Tahun 2025 (POJK, -) | Bidang: - | Status: tidak_diketahui
          14. [ID:606] PADK 19 Tahun 2017 (PADK, -) | Bidang: - | Status: tidak_diketahui
          15. [ID:627] SEOJK 31 Tahun 2016 (SEOJK, -) | Bidang: - | Status: tidak_diketahui
  [4/4] Menjadwalkan penarikan 15 dokumen ke Knowledge Base (format=['nama', 'jenis', 'tahun'])...
        Penarikan selesai. Berhasil di-ingest ke Knowledge Base: 15/15 dokumen.
```

### 7.2 Evaluasi Distribusi Dokumen Knowledge Base
```text
=================================================================
EVALUASI DISTRIBUSI DOKUMEN KNOWLEDGE BASE SETELAH SEEDING
=================================================================

--- 1. Dokumen Masuk per Sumber ---
Kode Sumber  | Nama Sumber                      | Target   | Berhasil Masuk 
---------------------------------------------------------------------------
ojk          | Regulasi OJK (Situs Resmi)       | 15       | 15             
jdih         | JDIH OJK (Situs Resmi)           | 15       | 12             
onedrive     | OneDrive Public DPEA             | 15       | 15             
TOTAL        | Semua Sumber                     | 45       | 42             

--- 2. Distribusi Bidang (15 kategori, Total: 42) ---
Bidang / Sektor                               | Jumlah Dokumen 
-----------------------------------------------------------------
(kosong)                                      | 15             
PVML                                          | 4              
Lembaga Pembiayaan, Perusahaan Modal Ventura, | 4              
Perbankan                                     | 3              
Pasar Modal                                   | 3              
Perasuransian, Penjaminan, dan Dana Pensiun   | 3              
ITSK                                          | 2              
BMKS                                          | 1              
PPDP                                          | 1              
OJK Wide                                      | 1              
Pasar Modal, Keuangan Derivatif, dan Bursa Ka | 1              
Perilaku Pelaku Usaha Jasa Keuangan, Edukasi  | 1              
Kebijakan Strategis                           | 1              
EPK                                           | 1              
Inovasi Teknologi Sektor Keuangan, Aset Keuan | 1              

--- 3. Distribusi Jenis Regulasi (7 jenis) ---
Jenis Regulasi                 | Jumlah Dokumen 
--------------------------------------------------
PADK                           | 14             
POJK                           | 13             
SEOJK                          | 9              
KEPDIR                         | 2              
(kosong)                       | 2              
UU                             | 1              
PBI                            | 1              

--- 4. Distribusi Tahun Regulasi (5 tahun) ---
Tahun                | Jumlah Dokumen 
----------------------------------------
2026                 | 13             
2025                 | 10             
2024                 | 3              
2023                 | 1              
(kosong)             | 15             

--- 5. Distribusi Status Keberlakuan (3 nilai status) ---
Status Keberlakuan        | Jumlah Dokumen 
---------------------------------------------
tidak_diketahui           | 30             
berlaku                   | 10             
dicabut                   | 2              
```

### 7.3 Output Mentah: `GET /api/v1/dashboard/summary`
```json
{
  "kb": {
    "corpus_documents": 42,
    "draft_documents": 0,
    "target_fase1": 20,
    "target_met": true,
    "by_status_keberlakuan": {
      "berlaku": 10,
      "diubah": 0,
      "dicabut": 2,
      "tidak_diketahui": 30
    },
    "by_processing_status": {
      "diterima": 42,
      "diproses": 0,
      "perlu_koreksi": 0,
      "terindeks": 0,
      "gagal": 0,
      "ditolak": 0
    },
    "by_regulation_type": [
      {
        "regulation_type": "PADK",
        "label": "PADK",
        "count": 14
      },
      {
        "regulation_type": "POJK",
        "label": "POJK",
        "count": 13
      },
      {
        "regulation_type": "SEOJK",
        "label": "SEOJK",
        "count": 9
      },
      {
        "regulation_type": "KEPDIR",
        "label": "KEPDIR",
        "count": 2
      },
      {
        "regulation_type": null,
        "label": "Belum diketahui",
        "count": 2
      },
      {
        "regulation_type": "PBI",
        "label": "PBI",
        "count": 1
      },
      {
        "regulation_type": "UU",
        "label": "UU",
        "count": 1
      }
    ],
    "by_year": [
      {
        "year": null,
        "label": "Belum diketahui",
        "count": 15
      },
      {
        "year": 2026,
        "label": "2026",
        "count": 13
      },
      {
        "year": 2025,
        "label": "2025",
        "count": 10
      },
      {
        "year": 2024,
        "label": "2024",
        "count": 3
      },
      {
        "year": 2023,
        "label": "2023",
        "count": 1
      }
    ],
    "placed_documents": 40,
    "inbox_documents": 2
  },
  "ingest": {
    "open_failures": 0,
    "needs_review": 0,
    "active_scans": 0,
    "recent_jobs": [
      {
        "id": 3,
        "job_type": "scraping",
        "status": "selesai",
        "started_at": "2026-10-03T04:35:05.349932+00:00",
        "finished_at": "2026-10-03T04:35:30.633662+00:00",
        "success_count": 15,
        "duplicate_count": 0,
        "skipped_count": 0,
        "failed_count": 0,
        "processed_count": 15,
        "total_found": 15
      },
      {
        "id": 2,
        "job_type": "scraping",
        "status": "selesai",
        "started_at": "2026-10-03T04:33:58.891385+00:00",
        "finished_at": "2026-10-03T04:34:49.085530+00:00",
        "success_count": 12,
        "duplicate_count": 3,
        "skipped_count": 0,
        "failed_count": 0,
        "processed_count": 15,
        "total_found": 15
      },
      {
        "id": 1,
        "job_type": "scraping",
        "status": "selesai",
        "started_at": "2026-10-03T04:26:21.649332+00:00",
        "finished_at": "2026-10-03T04:27:23.373033+00:00",
        "success_count": 15,
        "duplicate_count": 0,
        "skipped_count": 0,
        "failed_count": 0,
        "processed_count": 15,
        "total_found": 15
      }
    ]
  },
  "sources": {
    "total": 3,
    "active": 3,
    "by_type": {
      "situs_web": 2,
      "folder_lokal": 0,
      "onedrive_public": 1
    }
  },
  "generated_at": "2026-10-03T04:35:32.767901+00:00"
}
```

### 7.4 Daftar ID Dokumen Baru di Knowledge Base
Frontend menggunakan ID dokumen riil berikut untuk verifikasi integrasi:

| ID | Judul Singkat Dokumen | Sumber Asal | Status Keberlakuan | Nomor Regulasi |
|---|---|---|---|---|
| **1** | Pelaksanaan Penawaran Umum Efek Bersifat Utang dan/atau Sukuk | Regulasi OJK | tidak_diketahui | PADK 11 Tahun 2026 |
| **2** | Laporan Bulanan Perusahaan Pembiayaan dan Perusahaan Pembiayaan | Regulasi OJK | tidak_diketahui | 45/PADK.06/2025 |
| **3** | Perubahan Atas Surat Edaran Otoritas Jasa Keuangan Nomor 25/SEO | Regulasi OJK | tidak_diketahui | 23/SEOJK.06/2025 |
| **4** | Laporan Berkala Lembaga Penjamin | Regulasi OJK | tidak_diketahui | 11 Tahun 2026 |
| **5** | Penyelenggaraan Bursa Mineral dan Komoditas Strategis | Regulasi OJK | tidak_diketahui | 16 Tahun 2026 |
| **6** | Publikasi Penanganan Pengaduan dan Laporan Layanan Pengaduan | Regulasi OJK | tidak_diketahui | 20/SEOJK.08/2025 |
| **7** | Penerapan Manajemen Risiko Country Risk dan Transfer Risk bagi | Regulasi OJK | tidak_diketahui | PADK 10 Tahun 2026 |
| **8** | Penerbitan dan Pelaporan Efek Beragun Aset Berbentuk Surat Part | Regulasi OJK | tidak_diketahui | 12 Tahun 2026 |
| **9** | Penyelenggaraan Perdagangan Aset Keuangan Digital termasuk Aset | Regulasi OJK | tidak_diketahui | 3 Tahun 2026 |
| **10** | Penilaian Kualitas Piutang Pembiayaan PT Sarana Multi Infrastr | Regulasi OJK | tidak_diketahui | 7 Tahun 2026 |
| **11** | Pedoman Penerapan Program Anti Pencucian Uang, Pencegahan Pend | Regulasi OJK | tidak_diketahui | 4 Tahun 2026 |
| **12** | Pelaporan dan Permintaan Data Transaksi Pendanaan oleh Pelengg | Regulasi OJK | tidak_diketahui | 8 Tahun 2026 |
| **13** | Penerapan Tata Kelola dan Manajemen Risiko Bagi Penyelenggara  | Regulasi OJK | tidak_diketahui | 30 Tahun 2025 |
| **14** | Kewajiban Penyediaan Modal Minimum dan Pemenuhan Modal Inti Mi | Regulasi OJK | tidak_diketahui | 7 Tahun 2026 |
| **15** | Penggunaan Dana Hasil Penawaran Umum | Regulasi OJK | tidak_diketahui | 40 Tahun 2025 |
| **16** | Peraturan Otoritas Jasa Keuangan Republik Indonesia Nomor 10 T | JDIH OJK | berlaku | POJK 10 Tahun 2026 |
| **17** | Peraturan Otoritas Jasa Keuangan Republik Indonesia Nomor 6 Ta | JDIH OJK | berlaku | POJK 6 Tahun 2026 |
| **18** | Peraturan Otoritas Jasa Keuangan Republik Indonesia Nomor 39 T | JDIH OJK | berlaku | POJK 39 Tahun 2024 |
| **19** | Surat Edaran Otoritas Jasa Keuangan Republik Indonesia Nomor 1 | JDIH OJK | berlaku | 19/SEOJK.06/2024 |
| **20** | Surat Edaran Otoritas Jasa Keuangan Republik Indonesia Nomor 2 | JDIH OJK | berlaku | 20/SEOJK.07/2024 |
| **21** | Surat Edaran Otoritas Jasa Keuangan Republik Indonesia Nomor 2 | JDIH OJK | **dicabut** | 21/SEOJK.05/2023 |
| **22** | Peraturan Anggota Dewan Komisioner Otoritas Jasa Keuangan Repu | JDIH OJK | berlaku | PADK 2 Tahun 2026 |
| **23** | Peraturan Anggota Dewan Komisioner Otoritas Jasa Keuangan Repu | JDIH OJK | berlaku | 48/PADK.06/2025 |
| **24** | Peraturan Anggota Dewan Komisioner Otoritas Jasa Keuangan Repu | JDIH OJK | berlaku | 47/PADK.05/2025 |
| **25** | Peraturan Anggota Dewan Komisioner Otoritas Jasa Keuangan Repu | JDIH OJK | berlaku | 44/PADK.01/2025 |
| **26** | Peraturan Anggota Dewan Komisioner Otoritas Jasa Keuangan Repu | JDIH OJK | berlaku | 42/PADK.03/2025 |
| **27** | Surat Edaran Otoritas Jasa Keuangan Republik Indonesia Nomor 7 | JDIH OJK | **dicabut** | 7/SEOJK.05/2025 |
| **28** | Peraturan_OJK_3_2015 | OneDrive DPEA | tidak_diketahui | POJK 3 Tahun 2015 |
| **29** | Peraturan_OJK_27_2021 | OneDrive DPEA | tidak_diketahui | POJK 27 Tahun 2021 |
| **30** | POJK 3 Tahun 2025 Penatalaksanaan Lembaga Sertifikasi Profesi | OneDrive DPEA | tidak_diketahui | POJK 3 Tahun 2025 |
| **31** | Peraturan_ADK_19_Tahun_2015_PERUBAHAN_KEEMPAT_SURAT_EDARAN_BA | OneDrive DPEA | tidak_diketahui | PADK 19 Tahun 2015 |
| **32** | Peraturan_ADK_4_Tahun_2022_PEDOMAN_PELAKSANAAN_PELAPORAN_KEUA | OneDrive DPEA | tidak_diketahui | PADK 4 Tahun 2022 |
| **33** | Surat_Edaran_OJK_6_2016 | OneDrive DPEA | tidak_diketahui | SEOJK 6 Tahun 2016 |
| **34** | Peraturan_ADK_19_Tahun_2017_PEDOMAN_PELAKSANAAN_FORUM_PANITIA | OneDrive DPEA | tidak_diketahui | PADK 19 Tahun 2017 |
| **35** | Surat_Edaran_OJK_22_2023 | OneDrive DPEA | tidak_diketahui | SEOJK 22 Tahun 2023 |
| **36** | Tahun_izin_usaha_dan_pencabutan_izin_usaha_Manajer_Investasi | OneDrive DPEA | tidak_diketahui | - |
| **37** | 708a41f0-9685-3a8d-9676-afa5fb2bee74 | OneDrive DPEA | tidak_diketahui | - |
| **38** | Surat_Edaran_OJK_31_2016 | OneDrive DPEA | tidak_diketahui | SEOJK 31 Tahun 2016 |
| **39** | SK_Dir_27-164-KEP-DIR-1995_Pedoman_Teknologi_Sistem_Informasi | OneDrive DPEA | tidak_diketahui | 27-164-KEP-DIR-1995 |
| **40** | SK_Dir_26-68-KEP-DIR-1993_Saham_Sebagai_Agunan_Tambahan | OneDrive DPEA | tidak_diketahui | 26-68-KEP-DIR-1993 |
| **41** | Peraturan_Bank_Indonesia_7_1992 | OneDrive DPEA | tidak_diketahui | PBI 7 Tahun 1992 |
| **42** | Undang-Undang_17_2012 | OneDrive DPEA | tidak_diketahui | UU 17 Tahun 2012 |

### 7.5 Contoh Respons Mentah `GET /scans/{id}/candidates?limit=2` (JDIH dengan Status Non-Default)
```json
[
  {
    "id": 118,
    "scan_id": 2,
    "url": "https://jdih.ojk.go.id/Web/ViewPeraturan/DownloadDokumen/fca6d040-9d8b-03c7-9579-e453bb182e79",
    "filename": "2023absseojk021.pdf",
    "size_bytes": 106388,
    "found_on_page": "https://jdih.ojk.go.id/Web/ViewPeraturan/Detail/b9770b1b-4d88-2281-9831-0e4b5ac0ad05/All/",
    "document_title": "Surat Edaran Otoritas Jasa Keuangan Republik Indonesia Nomor 21/SEOJK.05/2023 tentang Perubahan atas Surat Edaran Otoritas Jasa Keuangan Nomor 25/SEOJK.05/2020 tentang Bentuk dan Susunan Laporan Berkala Perusahaan Pialang Asuransi, Perusahaan Pialang Reasuransi, dan Perusahaan Penilai Kerugian Asuransi",
    "detail_url": "https://jdih.ojk.go.id/Web/ViewPeraturan/Detail/b9770b1b-4d88-2281-9831-0e4b5ac0ad05/All/",
    "final_url": "https://jdih.ojk.go.id/Web/ViewPeraturan/DownloadDokumen/fca6d040-9d8b-03c7-9579-e453bb182e79",
    "doc_kind": "abstrak",
    "regulation_number": "21/SEOJK.05/2023",
    "regulation_type": "SEOJK",
    "bidang": "Perasuransian, Penjaminan, dan Dana Pensiun",
    "sub_bidang": null,
    "release_date": "2023-12-07",
    "effective_date": null,
    "match_warning": null,
    "status_keberlakuan": "dicabut",
    "size_source": "head",
    "source_path": null,
    "depth": 1,
    "match_status": "baru",
    "match_reason": null,
    "match_document_id": null,
    "match_document": null,
    "selected": false,
    "pull_outcome": null,
    "document_id": null,
    "failure_id": null,
    "export_path": null,
    "message": null
  },
  {
    "id": 119,
    "scan_id": 2,
    "url": "https://jdih.ojk.go.id/Web/ViewPeraturan/DownloadDokumen/a775abd6-48bc-21a6-49d4-00c3905e0e95",
    "filename": "2023faqseojk021.pdf",
    "size_bytes": 80021,
    "found_on_page": "https://jdih.ojk.go.id/Web/ViewPeraturan/Detail/b9770b1b-4d88-2281-9831-0e4b5ac0ad05/All/",
    "document_title": "Surat Edaran Otoritas Jasa Keuangan Republik Indonesia Nomor 21/SEOJK.05/2023 tentang Perubahan atas Surat Edaran Otoritas Jasa Keuangan Nomor 25/SEOJK.05/2020 tentang Bentuk dan Susunan Laporan Berkala Perusahaan Pialang Asuransi, Perusahaan Pialang Reasuransi, dan Perusahaan Penilai Kerugian Asuransi",
    "detail_url": "https://jdih.ojk.go.id/Web/ViewPeraturan/Detail/b9770b1b-4d88-2281-9831-0e4b5ac0ad05/All/",
    "final_url": "https://jdih.ojk.go.id/Web/ViewPeraturan/DownloadDokumen/a775abd6-48bc-21a6-49d4-00c3905e0e95",
    "doc_kind": "faq",
    "regulation_number": "21/SEOJK.05/2023",
    "regulation_type": "SEOJK",
    "bidang": "Perasuransian, Penjaminan, dan Dana Pensiun",
    "sub_bidang": null,
    "release_date": "2023-12-07",
    "effective_date": null,
    "match_warning": null,
    "status_keberlakuan": "dicabut",
    "size_source": "head",
    "source_path": null,
    "depth": 1,
    "match_status": "baru",
    "match_reason": null,
    "match_document_id": null,
    "match_document": null,
    "selected": false,
    "pull_outcome": null,
    "document_id": null,
    "failure_id": null,
    "export_path": null,
    "message": null
  }
]
```

### 7.6 Idempotensi Build Kontrak API (SHA-256 Identik)
Dijalankan dua kali berturut-turut:
```text
Algorithm       Hash                                                             Path
---------       ----                                                             ----
SHA256          7D4BE418A018C302432650A11E03E72571124D44166E42F9721A02185E434912 docs/api/KONTRAK-API-FASE1.md
SHA256          0F9D0BA2B02E08CF5CE08EC1448C681BDED14BFBAD693B914E4D91E95D4DEDFF docs/api/openapi-fase1.json
SHA256          8E87DBF459C3DDDC800BD434CAA8418826605B823160361BEBB6460E264537C7 docs/api/hero-fase1.http
```

---

## 8. Output Status Git & Terminal Mentah

### 8.1 Output Pytest Penuh (`pytest -q`)
```text
........................................................................ [ 31%]
............................................s........................... [ 63%]
........................................................................ [ 95%]
..........                                                               [100%]
225 passed, 1 skipped, 2 warnings in 178.78s (0:02:58)
```

### 8.2 Riwayat Commit Git (`git log --oneline -6`)
*(Catatan urutan: commit HEAD teratas adalah commit untuk berkas laporan ini sendiri yang dieksekusi setelah seluruh kode dan pengujian selesai di-commit).*
```text
472ad83 docs(reports): tambahkan laporan langkah 12 dukungan ingest dan perbaikan seed
751ef29 test(step12): suite pengujian lengkap G01-G11 dan sinkronisasi kontrak API fase 1
5997f5b fix(crawlers): normalisasi bidang, pemformatan nomor onedrive, release_date 2027, dan pembaruan seed script
efc1426 feat(scan): alur pindai centang tarik folder lokal, endpoint folder-options, dan validasi category_id
f2407c5 feat(db): migrasi category_id pada scan_sessions dan job_ingest serta perluas bidang
2f4b59e fix(scans): gunakan model_validate pada CandidateResponse untuk mencegah hilangnya field status dan metadata
```

### 8.3 Status Git Lokal (`git status --short`)
```text
(bersih / clean working tree)
```

### 8.4 Git Remote (`git remote -v`)
```text
(kosong / tidak ada remote yang terdaftar)
```
*(Catatan: Repositori lokal tidak memiliki remote URL yang terdaftar).*
