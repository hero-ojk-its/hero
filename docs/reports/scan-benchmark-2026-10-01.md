# Hasil Live Scan Benchmark — HERO Backend (Langkah 10)

> **Tanggal Pengujian:** 01 October 2026 21:27:13 WIB  
> **Metode:** Uji live benchmark penuh ke endpoint publik internet (tanpa Playwright / browser headless).

## 1. Ringkasan Performa Benchmark dan Perbandingan Ground Truth

| Sumber Data | Adapter | Durasi | Requests | Halaman/Folder | Regulasi | PDF Ditemukan | Lengkap 4 Atribut | Ukuran Terdeteksi | Ground Truth | Selisih | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Regulasi OJK** | `sharepoint_postback` | 91.22s | 206 | 5 | 50 | 151 | 151/151 (100.0%) | 151/151 (100.0%) | ± 1.700 regulasi | -1650 | Sukses |
| **JDIH OJK** | `jdih_api` | 214.95s | 609 | 5 | 250 | 340 | 340/340 (100.0%) | 340/340 (100.0%) | ± 400–500 regulasi | -200 | Sukses |
| **OneDrive Public DPEA** | `onedrive_share` | 7.54s | 11 | 5 | 2619 | 2619 | 2619/2619 (100.0%) | 2619/2619 (100.0%) | ± 2.612 berkas | +7 | Sukses |

## 2. Rincian dan Berkas CSV Hasil Pemindaian

### 2.1 Regulasi OJK (`ojk`)
- **URL Target:** https://ojk.go.id/id/regulasi/default.aspx
- **Adapter:** `sharepoint_postback`
- **Waktu Eksekusi:** 91.22 detik (206 requests)
- **Halaman/Folder Dikunjungi:** 5
- **Jumlah Regulasi Ditemukan:** 50
- **Jumlah Berkas PDF Ditemukan:** 151
- **Lengkap 4 Atribut (URL, Judul, Nama Berkas, Ukuran):** 151/151 (100.0%)
- **Ukuran Terdeteksi:** 151/151 (100.0%)
- **Ground Truth:** ± 1.700 regulasi (Selisih: -1650)
- **Berkas CSV Ekspor:** [`docs\reports\scan-benchmark-ojk.csv`](docs\reports\scan-benchmark-ojk.csv)
- **Rincian doc_kind:** `{'utama': 50, 'abstrak': 50, 'faq': 51}`
- **Statistik Lengkap:**
  ```json
  {'regulations_found': 50, 'pdfs_found': 151, 'by_doc_kind': {'utama': 50, 'abstrak': 50, 'faq': 51}, 'pages_visited': 5, 'requests_made': 206, 'non_pdf_links': 0, 'duration_seconds': 91.22}
  ```

### 2.2 JDIH OJK (`jdih`)
- **URL Target:** https://jdih.ojk.go.id/
- **Adapter:** `jdih_api`
- **Waktu Eksekusi:** 214.95 detik (609 requests)
- **Halaman/Folder Dikunjungi:** 5
- **Jumlah Regulasi Ditemukan:** 250
- **Jumlah Berkas PDF Ditemukan:** 340
- **Lengkap 4 Atribut (URL, Judul, Nama Berkas, Ukuran):** 340/340 (100.0%)
- **Ukuran Terdeteksi:** 340/340 (100.0%)
- **Ground Truth:** ± 400–500 regulasi (Selisih: -200)
- **Berkas CSV Ekspor:** [`docs\reports\scan-benchmark-jdih.csv`](docs\reports\scan-benchmark-jdih.csv)
- **Rincian doc_kind:** `{'faq': 52, 'utama': 281, 'abstrak': 7}`
- **Statistik Lengkap:**
  ```json
  {'regulations_found': 250, 'pdfs_found': 340, 'by_doc_kind': {'faq': 52, 'utama': 281, 'abstrak': 7}, 'pages_visited': 5, 'requests_made': 609, 'non_pdf_links': 0, 'duration_seconds': 214.95}
  ```

### 2.3 OneDrive Public DPEA (`onedrive`)
- **URL Target:** [link share OneDrive DPEA]
- **Adapter:** `onedrive_share`
- **Waktu Eksekusi:** 7.54 detik (11 requests)
- **Halaman/Folder Dikunjungi:** 5
- **Jumlah Regulasi Ditemukan:** 2619
- **Jumlah Berkas PDF Ditemukan:** 2619
- **Lengkap 4 Atribut (URL, Judul, Nama Berkas, Ukuran):** 2619/2619 (100.0%)
- **Ukuran Terdeteksi:** 2619/2619 (100.0%)
- **Ground Truth:** ± 2.612 berkas (Selisih: +7)
- **Berkas CSV Ekspor:** [`docs\reports\scan-benchmark-onedrive.csv`](docs\reports\scan-benchmark-onedrive.csv)
- **Rincian doc_kind:** `{'utama': 2303, 'faq': 156, 'abstrak': 157, 'lampiran': 3}`
- **Statistik Lengkap:**
  ```json
  {'regulations_found': 2619, 'pdfs_found': 2619, 'by_doc_kind': {'utama': 2303, 'faq': 156, 'abstrak': 157, 'lampiran': 3}, 'pages_visited': 5, 'requests_made': 11, 'non_pdf_links': 1, 'duration_seconds': 7.54}
  ```
