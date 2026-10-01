# Hasil Live Scan Benchmark — HERO Backend (Langkah 10b)

> **Tanggal Pengujian:** 02 October 2026 02:36:30 WIB  
> **Metode:** Uji live benchmark penuh ke endpoint publik internet (tanpa Playwright / browser headless).

## 1. Ringkasan Performa Benchmark dan Perbandingan Ground Truth

| Sumber Data | Adapter | Batas Paging | Halaman Terakhir | Regulasi | PDF | Lengkap 4 Atribut | Match Warnings | Ground Truth | Selisih | Durasi | Requests | Status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **JDIH OJK** | `jdih_api` | penuh (tanpa batas, default max=200) | 20 | 985 | 1652 | 1630/1652 (98.7%) | 67 | ± 400–500 regulasi | +535 | 837.12s | 2680 | Sukses |

## 2. Rincian dan Berkas CSV Hasil Pemindaian

### 2.1 JDIH OJK (`jdih`)
- **URL Target:** https://jdih.ojk.go.id/
- **Adapter:** `jdih_api`
- **Batas Paging:** penuh (tanpa batas, default max=200)
- **Waktu Eksekusi:** 837.12 detik (2680 requests)
- **Halaman/Folder Dikunjungi:** 20
- **Jumlah Regulasi Ditemukan:** 985
- **Jumlah Berkas PDF Ditemukan:** 1652
- **Lengkap 4 Atribut (URL, Judul, Nama Berkas, Ukuran):** 1630/1652 (98.7%)
- **Ukuran Terdeteksi:** 1630/1652 (98.7%)
- **Jumlah Match Warnings:** 67
- **Ground Truth:** ± 400–500 regulasi (Selisih: +535)
- **Berkas CSV Ekspor:** [`docs\reports\scan-benchmark-jdih.csv`](docs\reports\scan-benchmark-jdih.csv)
- **Rincian doc_kind:** `{'utama': 1231, 'abstrak': 219, 'faq': 202}`
- **Total Rekod Situs (recordsTotal):** 986
- **Statistik Lengkap:**
  ```json
  {'records_total': 986, 'regulations_found': 985, 'pdfs_found': 1652, 'match_warnings_count': 67, 'by_doc_kind': {'utama': 1231, 'abstrak': 219, 'faq': 202}, 'pages_visited': 20, 'requests_made': 2680, 'non_pdf_links': 0, 'duration_seconds': 837.11}
  ```
