# Hasil Live Scan Benchmark — HERO Backend (Langkah 10)

> **Tanggal Pengujian:** 01 October 2026 20:12:52 WIB  
> **Metode:** Uji live langsung ke endpoint publik internet (tanpa Playwright / browser headless).

## 1. Ringkasan Performa Benchmark

| Sumber Data | Adapter | Durasi (detik) | Halaman / Folder | PDF Ditemukan | Ukuran Terdeteksi | Rincian Doc Kind | Status |
|---|---|---|---|---|---|---|---|
| **Regulasi OJK** | `sharepoint_postback` | 37.34s | 2 | 60 | 60/60 | utama: 20, abstrak: 20, faq: 20 | Sukses |
| **JDIH OJK** | `jdih_api` | 36.56s | 2 | 100 | 72/100 | faq: 4, utama: 94, abstrak: 2 | Sukses |
| **OneDrive Public DPEA** | `onedrive_share` | 7.65s | 2 | 2612 | 2612/2612 | utama: 2296, faq: 156, abstrak: 157, lampiran: 3 | Sukses |

## 2. Rincian dan Berkas CSV Hasil Pemindaian

### 2.1 Regulasi OJK (`ojk`)
- **URL Target:** https://ojk.go.id/id/regulasi/default.aspx
- **Adapter:** `sharepoint_postback`
- **Waktu Eksekusi:** 37.34 detik
- **Halaman/Folder Dikunjungi:** 2
- **Total Berkas PDF:** 60
- **Berkas dengan Ukuran:** 60 (100%)
- **Berkas CSV Ekspor:** [`docs\reports\scan-benchmark-ojk.csv`](docs\reports\scan-benchmark-ojk.csv)
- **Statistik Lengkap:**
  ```json
  {'regulations_found': 20, 'pdfs_found': 60, 'by_doc_kind': {'utama': 20, 'abstrak': 20, 'faq': 20}, 'pages_visited': 2, 'requests_made': 82, 'non_pdf_links': 0, 'duration_seconds': 37.34}
  ```

### 2.2 JDIH OJK (`jdih`)
- **URL Target:** https://jdih.ojk.go.id/
- **Adapter:** `jdih_api`
- **Waktu Eksekusi:** 36.56 detik
- **Halaman/Folder Dikunjungi:** 2
- **Total Berkas PDF:** 100
- **Berkas dengan Ukuran:** 72 (72.0%)
- **Berkas CSV Ekspor:** [`docs\reports\scan-benchmark-jdih.csv`](docs\reports\scan-benchmark-jdih.csv)
- **Statistik Lengkap:**
  ```json
  {'regulations_found': 100, 'pdfs_found': 100, 'by_doc_kind': {'faq': 4, 'utama': 94, 'abstrak': 2}, 'pages_visited': 2, 'requests_made': 130, 'non_pdf_links': 0, 'duration_seconds': 36.56}
  ```

### 2.3 OneDrive Public DPEA (`onedrive`)
- **URL Target:** https://oneojk-my.sharepoint.com/:f:/g/personal/redacted_user_ojk_go_id/redacted_iduRwqT5X1zPBi_d1AAfA8Ec-W6i3BTN66ZgJI1rA?e=redacted_token
- **Adapter:** `onedrive_share`
- **Waktu Eksekusi:** 7.65 detik
- **Halaman/Folder Dikunjungi:** 2
- **Total Berkas PDF:** 2612
- **Berkas dengan Ukuran:** 2612 (100%)
- **Berkas CSV Ekspor:** [`docs\reports\scan-benchmark-onedrive.csv`](docs\reports\scan-benchmark-onedrive.csv)
- **Statistik Lengkap:**
  ```json
  {'regulations_found': 2612, 'pdfs_found': 2612, 'by_doc_kind': {'utama': 2296, 'faq': 156, 'abstrak': 157, 'lampiran': 3}, 'pages_visited': 2, 'requests_made': 5, 'non_pdf_links': 0, 'duration_seconds': 7.64}
  ```
