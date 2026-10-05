# Hasil Live Scan Benchmark — HERO Backend (Langkah 10d)

> **Tanggal Pengujian:** 03 October 2026 00:41:29 WIB  
> **Metode:** Uji live benchmark penuh ke endpoint publik internet (tanpa Playwright / browser headless).

## 1. Ringkasan Performa Benchmark dan Perbandingan Ground Truth

| Sumber Data | Adapter | Batas Paging | Halaman Terakhir | Regulasi | PDF | Lengkap Metadata Hukum | Match Warnings | Ground Truth | Selisih | Durasi | Requests | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Regulasi OJK** | `sharepoint_postback` | penuh (tanpa batas, default max=500) | 158 | 1577 | 2665 | 2665/2665 (100.0%) | 25 | ± 1.700 regulasi | -123 (terhadap estimasi mitra ± 1.700) | 3017.22s | 4400 | Sukses |
| **JDIH OJK** | `jdih_api` | penuh (tanpa batas, default max=200) | 20 | 985 | 1652 | 1652/1652 (100.0%) | 67 | ± 400–500 regulasi | +485 s.d. +585 (+535 terhadap titik tengah 450) dari 985 regulasi tersimpan; +486 s.d. +586 (+536 terhadap titik tengah 450) dari 986 total rekod API | 837.12s | 2680 | Sukses |
| **OneDrive Public DPEA** | `onedrive_share` | penuh (tanpa batas, default max=1000) | 5 | 2619 | 2619 | 2135/2619 (81.5%) | 0 | Belum ada dari mitra | Belum ada dari mitra | 7.86s | 11 | Sukses |

## 2. Rincian dan Berkas CSV Hasil Pemindaian

### 2.1 Regulasi OJK (`ojk`)
- **URL Target:** https://ojk.go.id/id/regulasi/default.aspx
- **Adapter:** `sharepoint_postback`
- **Batas Paging:** penuh (tanpa batas, default max=500)
- **Waktu Eksekusi:** 3017.22 detik (4400 requests)
- **Halaman/Folder Dikunjungi:** 158
- **Jumlah Regulasi Ditemukan:** 1577
- **Jumlah Berkas PDF Ditemukan:** 2665
- **Lengkap Metadata Hukum (Jenis + Nomor + Tahun/Tanggal):** 2665/2665 (100.0%)
- **Ukuran Terdeteksi:** 2665/2665 (100.0%)
- **Jumlah Match Warnings:** 25
- **Ground Truth:** ± 1.700 regulasi (Selisih: -123 (terhadap estimasi mitra ± 1.700))
- **Berkas CSV Ekspor:** [`docs/reports/scan-benchmark-ojk.csv`](docs/reports/scan-benchmark-ojk.csv)
- **Rincian doc_kind:** `{'utama': 1650, 'abstrak': 509, 'faq': 387, 'lampiran': 119}`
- **Statistik Lengkap:**
  ```json
  {'regulations_found': 1577, 'pdfs_found': 2665, 'by_doc_kind': {'utama': 1650, 'abstrak': 509, 'faq': 387, 'lampiran': 119}, 'pages_visited': 158, 'requests_made': 4400, 'match_warnings_count': 25, 'duration_seconds': 3017.22}
  ```

### 2.2 JDIH OJK (`jdih`)
- **URL Target:** https://jdih.ojk.go.id/
- **Adapter:** `jdih_api`
- **Batas Paging:** penuh (tanpa batas, default max=200)
- **Waktu Eksekusi:** 837.12 detik (2680 requests)
- **Halaman/Folder Dikunjungi:** 20
- **Jumlah Regulasi Ditemukan:** 985
- **Jumlah Berkas PDF Ditemukan:** 1652
- **Lengkap Metadata Hukum (Jenis + Nomor + Tahun/Tanggal):** 1652/1652 (100.0%)
- **Ukuran Terdeteksi:** 1630/1652 (98.7%)
- **Jumlah Match Warnings:** 67
- **Ground Truth:** ± 400–500 regulasi (Selisih: +485 s.d. +585 (+535 terhadap titik tengah 450) dari 985 regulasi tersimpan; +486 s.d. +586 (+536 terhadap titik tengah 450) dari 986 total rekod API)
- **Berkas CSV Ekspor:** [`docs/reports/scan-benchmark-jdih.csv`](docs/reports/scan-benchmark-jdih.csv)
- **Rincian doc_kind:** `{'utama': 990, 'abstrak': 460, 'faq': 202}`
- **Total Rekod Situs (recordsTotal):** 986
- **Statistik Lengkap:**
  ```json
  {'regulations_found': 985, 'regulations_without_files': 1, 'pdfs_found': 1652, 'by_doc_kind': {'utama': 990, 'abstrak': 460, 'faq': 202}, 'pages_visited': 20, 'requests_made': 2680, 'records_total': 986, 'match_warnings_count': 67, 'duration_seconds': 837.12}
  ```

### 2.3 OneDrive Public DPEA (`onedrive`)
- **URL Target:** [link share OneDrive DPEA]
- **Adapter:** `onedrive_share`
- **Batas Paging:** penuh (tanpa batas, default max=1000)
- **Waktu Eksekusi:** 7.86 detik (11 requests)
- **Halaman/Folder Dikunjungi:** 5
- **Jumlah Regulasi Ditemukan:** 2619
- **Jumlah Berkas PDF Ditemukan:** 2619
- **Lengkap Metadata Hukum (Jenis + Nomor + Tahun/Tanggal):** 2135/2619 (81.5%)
- **Ukuran Terdeteksi:** 2619/2619 (100.0%)
- **Jumlah Match Warnings:** 0
- **Ground Truth:** Belum ada dari mitra (Selisih: Belum ada dari mitra)
- **Berkas CSV Ekspor:** [`docs\reports\scan-benchmark-onedrive.csv`](docs\reports\scan-benchmark-onedrive.csv)
- **Rincian doc_kind:** `{'utama': 2295, 'faq': 156, 'abstrak': 158, 'lampiran': 3, 'non_regulasi': 7}`
- **Rincian Berkas per Subfolder:** `{'downloads': 2612, 'Administration': 5, 'User Requirement & Project Charter': 2}`
- **Statistik Lengkap:**
  ```json
  {'regulations_found': 2619, 'pdfs_found': 2619, 'subfolders_count': {'downloads': 2612, 'Administration': 5, 'User Requirement & Project Charter': 2}, 'match_warnings_count': 0, 'by_doc_kind': {'utama': 2295, 'faq': 156, 'abstrak': 158, 'lampiran': 3, 'non_regulasi': 7}, 'pages_visited': 5, 'requests_made': 11, 'non_pdf_links': 1, 'duration_seconds': 7.86}
  ```
