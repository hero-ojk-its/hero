# Hasil Live Scan Benchmark — HERO Backend (Langkah 10b)

> **Tanggal Pengujian:** 02 October 2026 13:31:10 WIB  
> **Metode:** Uji live benchmark penuh ke endpoint publik internet (tanpa Playwright / browser headless).

## 1. Ringkasan Performa Benchmark dan Perbandingan Ground Truth

| Sumber Data | Adapter | Batas Paging | Halaman Terakhir | Regulasi | PDF | Lengkap 4 Atribut | Match Warnings | Ground Truth | Selisih | Durasi | Requests | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **OneDrive Public DPEA** | `onedrive_share` | penuh (tanpa batas, default max=1000) | 5 | 2619 | 2619 | 2619/2619 (100.0%) | 180 | Belum ada dari mitra | Belum ada dari mitra | 8.77s | 11 | Sukses |

## 2. Rincian dan Berkas CSV Hasil Pemindaian

### 2.1 OneDrive Public DPEA (`onedrive`)
- **URL Target:** https://oneojk-my.sharepoint.com/:f:/g/personal/redacted_user_ojk_go_id/redacted_iduRwqT5X1zPBi_d1AAfA8Ec-W6i3BTN66ZgJI1rA?e=redacted_token
- **Adapter:** `onedrive_share`
- **Batas Paging:** penuh (tanpa batas, default max=1000)
- **Waktu Eksekusi:** 8.77 detik (11 requests)
- **Halaman/Folder Dikunjungi:** 5
- **Jumlah Regulasi Ditemukan:** 2619
- **Jumlah Berkas PDF Ditemukan:** 2619
- **Lengkap 4 Atribut (URL, Judul, Nama Berkas, Ukuran):** 2619/2619 (100.0%)
- **Ukuran Terdeteksi:** 2619/2619 (100.0%)
- **Jumlah Match Warnings:** 180
- **Ground Truth:** Belum ada dari mitra (Selisih: Belum ada dari mitra)
- **Berkas CSV Ekspor:** [`docs\reports\scan-benchmark-onedrive.csv`](docs\reports\scan-benchmark-onedrive.csv)
- **Rincian doc_kind:** `{'utama': 2303, 'faq': 156, 'abstrak': 157, 'lampiran': 3}`
- **Rincian Berkas per Subfolder:** `{'downloads': 2612, 'Administration': 5, 'User Requirement & Project Charter': 2}`
- **Statistik Lengkap:**
  ```json
  {'regulations_found': 2619, 'pdfs_found': 2619, 'subfolders_count': {'downloads': 2612, 'Administration': 5, 'User Requirement & Project Charter': 2}, 'match_warnings_count': 180, 'by_doc_kind': {'utama': 2303, 'faq': 156, 'abstrak': 157, 'lampiran': 3}, 'pages_visited': 5, 'requests_made': 11, 'non_pdf_links': 1, 'duration_seconds': 8.76}
  ```
