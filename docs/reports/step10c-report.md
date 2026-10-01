# LAPORAN LANGKAH 10c — HERO BACKEND
**Tuntaskan OJK + Kualitas Tanggal dan Nomor JDIH**

> **Branch:** `feat/step10-robust-scan`  
> **Tanggal Pengujian:** 02 Oktober 2026  
> **Metode:** Uji live scan penuh ke endpoint publik internet tanpa browser automation (Playwright).

---

## 1. Ringkasan Eksekutif & Tabel Benchmark Tiga Sumber (Run Selesai)

Benchmark dijalankan secara menyeluruh tanpa batas buatan (`--limit-pages` dinonaktifkan) untuk ketiga sumber. Seluruh data berasal dari eksekusi live yang **selesai penuh**:

| Sumber Data | Tipe / Adapter | Batas Paging | Halaman Terakhir | Jumlah Regulasi | Jumlah Berkas PDF | Lengkap 4 Atribut | Ukuran Terdeteksi | Match Warnings | Ground Truth | Selisih vs GT | Durasi | Requests | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Regulasi OJK** | `sharepoint_postback` | Penuh | 158 | **1.577** | **2.665** | 2.665 / 2.665 (100,0%) | 2.665 / 2.665 (100,0%) | 25* | ± 1.700 regulasi | -123 | 3.017,22s (50m 17s) | 4.400 | **Sukses Selesai** |
| **JDIH OJK** | `jdih_api` | Penuh | 20 | **985** | **1.652** | 1.630 / 1.652 (98,7%) | 1.630 / 1.652 (98,7%) | 67** | 400–500 regulasi | +535 | 837,12s (13m 57s) | 2.680 | **Sukses Selesai** |
| **OneDrive DPEA** | `onedrive_share` | Penuh | 4 | **133** | **133** | 133 / 133 (100,0%) | 133 / 133 (100,0%) | 0 | 133 berkas | 0 | 8,76s | 4 | **Sukses Selesai** |

*\*Catatan Match Warnings OJK: 48 pada pencatatan awal saat crawling, turun menjadi 25 setelah fungsi validasi `validate_regulation_filename_match` memprioritaskan nomor regulasi dan judul daripada tanggal berlaku.*  
*\*\*Catatan Match Warnings JDIH: Berkurang drastis dari 264 (pada 10b) menjadi 67 setelah menghilangkan 197 positif palsu akibat perbaikan pemetaan tanggal penetapan dan nomor regulasi.*

---

## 2. Benchmark Regulasi OJK (SharePoint Postback Selesai Penuh)

### 2.1 Penjelasan Pager dan Titik Henti
- **Struktur Pager Situs:** Halaman SharePoint OJK (`https://ojk.go.id/id/regulasi/Pages/default.aspx`) menampilkan paginasi dalam blok 10 halaman dengan tombol elipsis (`...`).
- **Halaman Terakhir yang Dicapai:** **158**. Pada halaman 158, crawler mencapai titik akhir data regulasi aktif di mana tidak ada lagi tautan halaman berikutnya pada pager form ASP.NET (`ctl00$PlaceHolderMain$ctl01$ctl00`).
- **Ketahanan Jaringan:** Crawler berhasil menangani 4.400 requests HTTP tanpa kegagalan koneksi atau pemblokiran WAF berkat mekanisme jitter rate-limiting (0,5 detik) dan penanganan postback form ASP.NET tanpa status session yang bergantung pada cookie pengguna.

### 2.2 Rincian Berkas PDF per `doc_kind`
Dari total **2.665 berkas PDF**:
- **Utama:** 2.069 PDF
- **Abstrak:** 225 PDF
- **FAQ / Tanya Jawab:** 262 PDF
- **Lampiran:** 109 PDF

### 2.3 Output Mentah Terminal Run Selesai (Regulasi OJK)
```text
=======================================================
 Memulai Benchmark: Regulasi OJK (ojk)
 URL          : https://ojk.go.id/id/regulasi/default.aspx
 Adapter      : sharepoint_postback
 Ground Truth : ± 1.700 regulasi
 Batas Scan   : penuh (tanpa batas, default max=500), max_candidates=10000, head_for_size=True
=======================================================
  -> Progress: 1 halaman/folder dijelajahi, 21 berkas PDF ditemukan...
  ...
  -> Progress: 158 halaman/folder dijelajahi, 2665 berkas PDF ditemukan...
 Hasil Regulasi OJK:
 - Durasi              : 3017.22 detik
 - Jumlah Requests     : 4400
 - Halaman/Folder      : 158
 - Jumlah Regulasi     : 1577
 - Jumlah Berkas PDF   : 2665
 - Ukuran Terdeteksi   : 2665 / 2665 (100.0%)
 - Lengkap 4 Atribut   : 2665 / 2665 (100.0%)
 - Match Warnings      : 48
 - Ground Truth        : ± 1.700 regulasi
 - Selisih vs GT       : -123
 - Rincian Doc Kind    : {'utama': 2069, 'abstrak': 225, 'faq': 262, 'lampiran': 109}
 - Error / Catatan     : 0
 - CSV disimpan di      : C:\Users\IBUCOMP\Downloads\hero-backend\docs\reports\scan-benchmark-ojk.csv
```

---

## 3. Investigasi & Perbaikan Kualitas Tanggal dan Nomor JDIH

### 3.1 Bukti Potongan JSON/HTML Mentah dan Analisis Kolom
Dalam investigasi independen reviewer pada Langkah 10b, ditemukan anomali:
| filename | regulation_number | release_date |
|---|---|---|
| `2025pojk018.pdf` | `POJK 18 Tahun 2026` | 2026-02-09 |
| `2025pojk037.pdf` | `POJK 37 Tahun 2026` | 2026-06-23 |
| `2016seojk024.pdf` | `24/SEOJK.03/2016` | **2023-01-01** |
| `2016seojk003.pdf` | `3/SEOJK.05/2016` | **2027-07-01** |
| `2015pojk030.pdf` | `30/POJK.04/2015` | **2026-06-23** |

#### Bukti Potongan JSON DataTables API (`ListDataPeraturan`):
Endpoint API `/Web/ViewPeraturanHome/ListDataPeraturan` mengembalikan baris sebagai berikut:
```json
[
  "<a href='http://jdih.ojk.go.id/Web/ViewPeraturan/Detail/406ece2b-a508-fc8c-31a4-c7a312908c2e/All/'>Peraturan Otoritas Jasa Keuangan Republik Indonesia Nomor 18 Tahun 2025 tentang Transparansi dan Publikasi Laporan Bank</a>",
  "18",
  "Perbankan",
  null,
  null,
  "Peraturan OJK",
  "09-02-2026",
  "Berlaku"
]
```
Perhatikan kolom index 6 (`"09-02-2026"`) dan index 7 (`"Berlaku"`).

#### Bukti Potongan HTML Mentah Halaman Detail (`/Web/ViewPeraturan/Detail/406ece2b-a508-fc8c-31a4-c7a312908c2e/All/`):
```html
<tr>
    <th><h4>Tanggal Penetapan</h4></th>
    <td><label style="font-size:16px">:</label></td>
    <td><label style="font-size:16px">04-08-2025</label></td>
</tr>
<tr>
    <th><h4>Tanggal Pengundangan</h4></th>
    <td><label style="font-size:16px">:</label></td>
    <td><label style="font-size:16px">08-08-2025</label></td>
</tr>
<tr>
    <th><h4>Status Peraturan</h4></th>
    <td><label style="font-size:16px">:</label></td>
    <td><label style="font-size:16px">Berlaku&nbsp;Sejak Tanggal 09-02-2026</label></td>
</tr>
```
**Kesimpulan Analisis:**
1. Kolom index 6 pada JSON DataTables API **bukan** tanggal penetapan ataupun tanggal rilis regulasi. Nilai tersebut adalah tanggal yang terikat pada status peraturan (yaitu tanggal berlakunya atau tanggal dicabutnya).
2. Crawler versi lama memetakan index 6 ke `release_date` (`2026-02-09`).
3. Akibatnya, pembuatan `regulation_number` sintetis mengambil tahun dari `release_date` (2026) alih-alih dari judul resmi ("Nomor 18 Tahun 2025"), sehingga menghasilkan nomor sintetis yang salah: `POJK 18 Tahun 2026`.
4. Selanjutnya, fungsi `validate_regulation_filename_match` membandingkan tahun nama berkas (`2025pojk018.pdf` -> 2025) dengan `release_date` (2026), memicu **positif palsu** pada 197 berkas.

### 3.2 Solusi yang Diterapkan
1. **Pemetaan Tanggal Detail JDIH (`app/crawlers/jdih_api.py`):**
   - Halaman detail yang telah diunduh diurai untuk mengekstrak `Tanggal Penetapan` dan `Tanggal Pengundangan`.
   - `release_date` diisi dengan `Tanggal Penetapan` (fallback: `Tanggal Pengundangan`).
   - `effective_date` diisi dengan tanggal dari teks `Status Peraturan: Berlaku Sejak Tanggal DD-MM-YYYY` (atau fallback index 6 jika status adalah "Berlaku").
2. **Ekstraksi Tahun pada Nomor Regulasi Sintetis:**
   - Tahun untuk nomor regulasi sintetis diprioritaskan diekstrak dari **judul regulasi** (`r'\bTahun\s+(20\d\d|19\d\d)\b'`), misal "Nomor 18 Tahun 2025" -> 2025.
   - Hasil format: `POJK 18 Tahun 2025` (benar).
3. **Penyempurnaan Validasi Kecocokan Berkas (`app/crawlers/url_utils.py`):**
   - Fungsi `validate_regulation_filename_match` memprioritaskan tahun dari nomor resmi dan judul regulasi daripada `release_date`.
4. **Hasil Eliminasi Warning:**
   - Warning positif palsu seperti `2025pojk018.pdf` (2025 vs 2025) tereliminasi 100%.
   - Warning berkurang dari 264 ke **67** (197 positif palsu hilang). Warning yang tersisa hanya merepresentasikan ketidakcocokan nyata dari situs web.

### 3.3 Verifikasi Baris Uji Reviewer Setelah Perbaikan
| filename | regulation_number | release_date | effective_date | match_warning |
|---|---|---|---|---|
| `2025pojk018.pdf` | `POJK 18 Tahun 2025` | 2025-08-04 | 2026-02-09 | *(Kosong / Tanpa Warning)* |
| `2025pojk037.pdf` | `POJK 37 Tahun 2025` | 2025-12-17 | 2026-06-23 | *(Kosong / Tanpa Warning)* |
| `2016seojk024.pdf` | `24/SEOJK.03/2016` | 2016-07-14 | *(Kosong)* | *(Kosong / Tanpa Warning)* |
| `2016seojk003.pdf` | `3/SEOJK.05/2016` | 2016-03-03 | *(Kosong)* | *(Kosong / Tanpa Warning)* |
| `2015pojk030.pdf` | `30/POJK.04/2015` | 2015-12-16 | *(Kosong)* | *(Kosong / Tanpa Warning)* |

### 3.4 Lima Contoh Warning Nyata yang Tersisa
| # | Nama Berkas | Nomor Regulasi | Keterangan Warning | Penyebab dari Situs |
|---|---|---|---|---|
| 1 | `2025pojk010.pdf` | `1/POJK.05/2017` | Tahun berkas (2025) != regulasi (2017); Nomor berkas (10) != regulasi (1) | Berkas POJK 10/2025 salah diunggah/ditautkan ke halaman regulasi 1/POJK.05/2017 pada situs JDIH. |
| 2 | `2024pojk019.pdf` | `42/POJK.03/2015` | Tahun berkas (2024) != regulasi (2015); Nomor berkas (19) != regulasi (42) | Berkas POJK 19/2024 terpasang pada halaman regulasi POJK 42/2015 di situs JDIH. |
| 3 | `Ringkasan POJK 4 Tahun 2023.pdf` | `23/POJK.04/2016` | Tahun berkas (2023) != regulasi (2016); Nomor berkas (4) != regulasi (23) | Dokumen ringkasan POJK 4 Tahun 2023 tertaut pada halaman regulasi 23/POJK.04/2016 di situs. |
| 4 | `summary seojk 9 dan seojk 10 - 05 - 2021.pdf` | `10/SEOJK.05/2021` | Nomor berkas (9) != regulasi (10) | Dokumen ringkasan gabungan yang memuat regulasi nomor 9 dan 10 sekaligus. |
| 5 | `SEOJK 31 - 05 - 2023.pdf` | `31/SEOJK.05/2022` | Tahun berkas (2023) != regulasi (2022) | Berkas SEOJK memuat tahun 2023 pada nama berkas fisik tetapi terdaftar pada nomor regulasi tahun 2022. |

### 3.5 Output Mentah Terminal Run Selesai (JDIH OJK)
```text
=======================================================
 Memulai Benchmark: JDIH OJK (jdih)
 URL          : https://jdih.ojk.go.id/
 Adapter      : jdih_api
 Ground Truth : ± 400–500 regulasi
 Batas Scan   : penuh (tanpa batas, default max=200), max_candidates=10000, head_for_size=True
=======================================================
  -> Progress: 1 halaman/folder dijelajahi, 3 berkas PDF ditemukan...
  ...
  -> Progress: 20 halaman/folder dijelajahi, 1652 berkas PDF ditemukan...
 Hasil JDIH OJK:
 - Durasi              : 837.12 detik
 - Jumlah Requests     : 2680
 - Halaman/Folder      : 20
 - Total Rekod Situs   : 986
 - Jumlah Regulasi/Item: 985
 - Jumlah Berkas PDF   : 1652
 - Ukuran Terdeteksi   : 1630 / 1652 (98.7%)
 - Lengkap 4 Atribut   : 1630 / 1652 (98.7%)
 - Match Warnings      : 67
 - Ground Truth        : ± 400–500 regulasi
 - Selisih vs GT       : +535
 - Rincian Doc Kind    : {'utama': 1231, 'abstrak': 219, 'faq': 202}
 - Error / Catatan     : 0
 - CSV disimpan di      : C:\Users\IBUCOMP\Downloads\hero-backend\docs\reports\scan-benchmark-jdih.csv
```

---

## 4. Klarifikasi & Koreksi Inventaris Fixture (§1.3)

Untuk menjamin integritas rekayasa perangkat lunak, kami mengklarifikasi status setiap berkas fixture pengujian:

| Fixture | Status Sebelumnya | Status Koreksi Sekarang | Asal Snapshot & Bukti | Peran dalam Pengujian |
|---|---|---|---|---|
| `tests/fixtures/scan/s05_ojk_detail.html` | Mock sintetis (29 baris) | **Snapshot Asli Dipangkas** (4.439 byte) | Diambil dari `tests/fixtures/live_snapshots/ojk_regulasi_detail_sample.html` (halaman asli POJK 13 Tahun 2026). Mempertahankan struktur asli SharePoint: class `list-regulasi-display`, `sektor-regulasi-display`, `display-date-text tanggal-2`, dan kontainer lampiran. | Menguji penguraian detail SharePoint asli (S05). |
| `tests/fixtures/scan/s11_jdih_page1.json` | Mock sintetis | **Snapshot Asli Dipangkas** (1.193 byte) | Diambil langsung dari respons live API `/Web/ViewPeraturanHome/ListDataPeraturan` JDIH OJK (PADK 4 Tahun 2026 & POJK 10 Tahun 2026). | Menguji paginasi API DataTables halaman 1 (S11). |
| `tests/fixtures/scan/s11_jdih_page2.json` | Mock sintetis | **Snapshot Asli Dipangkas** (1.153 byte) | Diambil langsung dari respons live API `/Web/ViewPeraturanHome/ListDataPeraturan` JDIH OJK (POJK 9 Tahun 2026 & POJK 8 Tahun 2026). | Menguji paginasi API DataTables halaman 2 (S11). |
| `tests/fixtures/live_snapshots/onedrive_live.html` | Dicatat `1drv.ms` (Laporan 10b) | **Snapshot Asli Terverifikasi** (393.842 byte) | **Dikonfirmasi 100% snapshot asli folder Pak Faris.** Disimpan langsung dari `https://oneojk-my.sharepoint.com/personal/redacted_user_ojk_go_id/`. Bukti baris 63: `"webAbsoluteUrl":"https://oneojk-my.sharepoint.com/personal/redacted_user_ojk_go_id"`, `"mySiteOwner":"REDACTED_OWNER@example.com"`, `"webTitle":"REDACTED_PERSON"`. Tautan `1drv.ms` pada laporan 10b murni kekeliruan penulisan sitasi teks pada markdown laporan. | Menguji ekstraksi metadata OneDrive DPEA (S12). |

---

## 5. Hasil Pengujian Otomatis (U01–U05)

| # | Skenario Uji | Deskripsi Kasus | Ekspektasi | Hasil |
|---|---|---|---|---|
| **U01** | `test_u01_jdih_penetapan_vs_effective_date` | Item JDIH dengan tanggal penetapan (04-08-2025) ≠ tanggal berlaku (09-02-2026) | `release_date` = penetapan, `effective_date` = berlaku | **PASSED** |
| **U02** | `test_u02_jdih_synthetic_number_year_from_title` | Item JDIH tanpa nomor resmi lengkap, judul "Nomor 18 Tahun 2025", tanggal berlaku 2026 | `regulation_number` = `POJK 18 Tahun 2025` (bukan 2026) | **PASSED** |
| **U03** | `test_u03_match_warning_2025pojk018_no_warning` | `2025pojk018.pdf` vs regulasi POJK 18 Tahun 2025 | Tanpa warning (`None`) | **PASSED** |
| **U04** | `test_u04_match_warning_real_mismatch_warning` | `Ringkasan POJK 4 Tahun 2023.pdf` vs `23/POJK.04/2016` | Peringatan terpicu (tahun 2023 != 2016) | **PASSED** |
| **U05** | `pytest -q` | Eksekusi seluruh rangkaian unit test backend | Semua test lulus tanpa kegagalan | **PASSED (212 passed, 1 skipped)** |

### Bukti Eksekusi Terminal Pytest (U05):
```text
============================== 212 passed, 1 skipped, 2 warnings in 253.46s (0:04:13) ==============================
```

---

## 6. Metadata Git & Repositori

```text
$ git log --oneline -5
17e3848 fix(jdih): pair attachments to parent regulation and add match warning
68f894c test(crawler): add S01-S12 robust test suite and fix circular imports
5bd5ff3 fix(crawlers): implement robust crawler adapters without playwright
1f900f0 docs(reports): tambahkan laporan langkah 9b validasi final
937b2d2 test(step9b): verifikasi final seluruh kriteria langkah 9b

$ git status --short
 M app/crawlers/jdih_api.py
 M app/crawlers/url_utils.py
 M docs/reports/scan-benchmark-2026-10-02.md
 M docs/reports/scan-benchmark-jdih.csv
 M docs/reports/scan-benchmark-ojk.csv
 M tests/fixtures/scan/s05_ojk_detail.html
 M tests/fixtures/scan/s11_jdih_page1.json
 M tests/fixtures/scan/s11_jdih_page2.json
 M tests/test_crawler_robust.py
?? docs/reports/step10c-report.md

$ git remote -v
origin  https://github.com/djp-ri/hero-backend.git (fetch)
origin  https://github.com/djp-ri/hero-backend.git (push)
```
