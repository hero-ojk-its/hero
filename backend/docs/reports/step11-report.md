# LAPORAN LANGKAH 11: DUKUNGAN INTEGRASI FRONTEND & DATA UJI NYATA

> **Proyek:** HERO Backend — Sistem Regulasi & Kepatuhan OJK  
> **Branch:** `feat/step11-fe-support`  
> **Tanggal:** 2026-10-03  
> **Penanggung Jawab:** Senior Backend Engineer  

---

## 1. Ringkasan Pelaksanaan (§1–§4)

### 1.1 Koreksi Sisa Langkah 10c (§1)
- Laporan `docs/reports/step10c-report.md` telah diperbarui dengan catatan koreksi di awal dokumen.
- Bagian §6 git history dikoreksi dengan hash git riil dari repository lokal (`5b64248`).
- Benchmark OneDrive dijalankan ulang pada koneksi langsung (durasi 7.86 detik untuk 2.619 berkas) dan ground truth ditandai secara jujur sebagai `belum ada dari mitra`.
- Fungsi `determine_doc_kind` pada `app/crawlers/url_utils.py` disempurnakan untuk mengenali pola underscore/tanpa spasi (`faq_*`, `abs_*`, `abstrak_*`, `ringkasan_*`, `summary_*`).

### 1.2 CORS dan Unduhan PDF untuk Frontend (§2)
- **CORS Middleware:** `app/main.py` kini menambahkan `expose_headers=["Content-Disposition", "Content-Length"]` sehingga client web Vite React di port `5173` dapat mengakses header respons untuk membaca nama berkas asli.
- **RFC 5987 Filename:** Endpoint `GET /documents/{id}/pdf` menyertakan `filename*=UTF-8''<percent-encoded>` dan fallback `filename="<ascii-safe>"` pada header `Content-Disposition`, serta mendukung query parameter `download=true` (`attachment`) vs `download=false` (`inline`).
- **Konfigurasi Lingkungan:** `.env.example` menyertakan default `CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000`.
- **Kontrak API:** Bagian CORS, port 5173, dan header `Content-Disposition` disinkronkan ke `KONTRAK-API-FASE1.md` melalui builder.

### 1.3 Status Keberlakuan dari Sumber Resmi (§3)
- Menambahkan kolom `status_keberlakuan` pada model `ScanCandidate` via migrasi database Alembic `f11a84880e5e`.
- Nilai `status_keberlakuan` dipropagasikan secara otomatis ke entitas `Document` saat kandidat di-pull ke Knowledge Base (`app/services/scan_service.py`), dengan tetap memprioritaskan koreksi manual pengguna.
- Parsing status JDIH memetakan teks detail dan kolom 7 DataTables API ke enum `StatusKeberlakuan` (`berlaku`, `dicabut`, `diubah`, `tidak_diketahui`).
- Investigasi situs Regulasi OJK dan folder OneDrive mengonfirmasi tidak tersedianya metadata status keberlakuan resmi, sehingga status tetap dibiarkan `tidak_diketahui`.

### 1.4 Data Uji Nyata untuk Integrasi Frontend (§4)
- Skrip `scripts/seed_from_sources.py` dibuat untuk mengisi data uji nyata langsung melalui REST API publik (`POST /api/v1/sources/`, `POST /api/v1/scans/`, `PATCH /api/v1/scans/{id}/selection`, `POST /api/v1/scans/{id}/pull`).
- Menyediakan opsi `--reset` yang memanggil utilitas pembersih operasional `scripts/demo_reset.py --yes`.
- Berhasil mengeksekusi pemindaian dan penarikan berkas asli dari 3 sumber resmi (Regulasi OJK, JDIH OJK, OneDrive DPEA), menghasilkan 41 dokumen riil dengan 15 variasi bidang/sektor dan 3 variasi status keberlakuan.

---

## 2. Distribusi Status JDIH & Potongan Bukti

### 2.1 Analisis Distribusi Seluruh Regulasi JDIH OJK (986 Regulasi)
Dari total 986 entri regulasi pada API DataTables JDIH OJK (`https://jdih.ojk.go.id/Web/ViewPeraturanHome/ListDataPeraturan`):

| Label Status Mentah (DataTables Kolom 7) | Frekuensi | Pemetaan Enum `StatusKeberlakuan` |
|---|---|---|
| `Berlaku` | 717 | `berlaku` |
| `Tidak Berlaku` | 253 | `dicabut` |
| `Berlaku (Perubahan) (Diubah)` | 15 | `diubah` |
| `Berlaku (Dicabut Sebagian)` | 1 | `diubah` |
| **Total** | **986** | — |

**Ringkasan Pemetaan:**
- `berlaku`: 717 (72.7%)
- `dicabut`: 253 (25.7%)
- `diubah`: 16 (1.6%)
- `tidak_diketahui`: 0 (0.0%)

### 2.2 Potongan Bukti Mentah dari Sumber JDIH

#### A. Status `berlaku`
```html
<!-- Dari halaman detail regulasi PADK 4 Tahun 2026 -->
<tr>
    <th style="width:200px; vertical-align:top !important;"><h4>Status Peraturan</h4></th>
    <td style="vertical-align:top !important;"><label style="font-size:16px">:</label></td>
    <td>Berlaku Sejak Tanggal 09-02-2026</td>
</tr>
```
*Kolom 7 DataTables:* `"Berlaku"`  
*Hasil pemetaan:* `StatusKeberlakuan.berlaku`

#### B. Status `dicabut`
```html
<!-- Dari halaman detail regulasi POJK 4/POJK.03/2015 -->
<tr>
    <th style="width:200px; vertical-align:top !important;"><h4>Status Peraturan</h4></th>
    <td style="vertical-align:top !important;"><label style="font-size:16px">:</label></td>
    <td>Tidak Berlaku Sejak Tanggal 28-11-2016 Dicabut Oleh POJK Nomor 43/POJK.03/2016</td>
</tr>
```
*Kolom 7 DataTables:* `"Tidak Berlaku"`  
*Hasil pemetaan:* `StatusKeberlakuan.dicabut`

#### C. Status `diubah`
```html
<!-- Dari halaman detail regulasi POJK 11/POJK.03/2015 -->
<tr>
    <th style="width:200px; vertical-align:top !important;"><h4>Status Peraturan</h4></th>
    <td style="vertical-align:top !important;"><label style="font-size:16px">:</label></td>
    <td>Berlaku Sejak Tanggal 18-08-2015 Diubah Oleh POJK Nomor 38/POJK.03/2016</td>
</tr>
```
*Kolom 7 DataTables:* `"Berlaku (Perubahan) (Diubah)"`  
*Hasil pemetaan:* `StatusKeberlakuan.diubah`

### 2.3 Status pada Regulasi OJK dan OneDrive DPEA
- **Regulasi OJK (`ojk.go.id/id/regulasi/default.aspx`):** Portal daftar regulasi OJK berbasis SharePoint tidak memiliki kolom atau penanda status keberlakuan terstruktur dalam tabel dokumen publik. Nilai status diisi sebagai `tidak_diketahui`.
- **OneDrive Public DPEA:** Repositori folder OneDrive publik hanya menyajikan struktur berkas dan tanggal modifikasi berkas tanpa metadata hukum status keberlakuan. Nilai status diisi sebagai `tidak_diketahui`.

---

## 3. Output Mentah Eksekusi `seed_from_sources.py` & `GET /dashboard/summary`

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
=================================================================
HERO BACKEND - DEMO DATA RESET UTILITY
Environment aktif : development
Database target   : hero_db @ localhost
Storage path      : ./storage
=================================================================

Saran: Pastikan Anda telah melakukan backup sebelum reset data:
  bash deploy/backup.sh

Ringkasan data operasional yang akan dihapus:
  - article_references  :     0 baris
  - legal_references    :     0 baris
  - articles            :     0 baris
  - ingest_failures     :     0 baris
  - scan_candidates     :  3142 baris
  - scan_sessions       :     3 baris
  - source_files        :     0 baris
  - job_ingest          :     2 baris
  - documents           :    15 baris
  - scraping_sources    :     3 baris
  - audit_logs          :    38 baris
Total baris data  : 3203 baris

--> 1/3 Mengosongkan tabel data operasional (TRUNCATE CASCADE)...
    Tabel database berhasil dikosongkan.
--> 2/3 Memastikan seeding kategori awal tetap utuh...
    Kategori awal terverifikasi.
--> 3/3 Membersihkan berkas pada direktori storage...
    Direktori storage berhasil dibersihkan.

=================================================================
RESET DEMO SELESAI DENGAN SUKSES!
Tabel users, categories, dan alembic_version tetap dipertahankan.
=================================================================
[RESET KONFIRMASI] Operasional database dan berkas staging fisik telah dikosongkan secara bersih.

--> Memeriksa konektivitas dan kesehatan REST API server...
    Server online (Versi: 0.10.0, Status: ok)

-----------------------------------------------------------------
PROSES SUMBER: [OJK] Regulasi OJK (Situs Resmi)
URL: https://ojk.go.id/id/regulasi/default.aspx | Tipe: situs_web | Batas Paging: 3
-----------------------------------------------------------------
  [1/4] Sumber berhasil didaftarkan (Source ID: 1).
  [2/4] Menjadwalkan pemindaian (POST /api/v1/scans/, depth=1, max_pages=3)...
        [Memindai...] Halaman: 1, Kandidat: 0
        [Memindai...] Halaman: 1, Kandidat: 0
        [Memindai...] Halaman: 2, Kandidat: 0
        [Memindai...] Halaman: 2, Kandidat: 0
        [Memindai...] Halaman: 3, Kandidat: 0
        [Memindai...] Halaman: 3, Kandidat: 90
        Pemindaian selesai (Scan #1, Status: siap_dipilih). Total kandidat PDF ditemukan: 90
  [3/4] Menganalisis 90 kandidat berkas...
        Terpilih 15 kandidat 'utama' bervariasi:
          01. [ID:1] PADK 11 Tahun 2026 (PADK, -) | Bidang: Pasar Modal | Status: tidak_diketahui
          02. [ID:4] 45/PADK.06/2025 (PADK, -) | Bidang: PVML | Status: tidak_diketahui
          03. [ID:7] 23/SEOJK.06/2025 (SEOJK, -) | Bidang: PVML | Status: tidak_diketahui
          04. [ID:10] 11 Tahun 2026 (POJK, -) | Bidang: PPDP | Status: tidak_diketahui
          05. [ID:13] 16 Tahun 2026 (POJK, -) | Bidang: BMKS | Status: tidak_diketahui
          06. [ID:16] 20/SEOJK.08/2025 (SEOJK, -) | Bidang: EPK | Status: tidak_diketahui
          07. [ID:22] PADK 10 Tahun 2026 (PADK, -) | Bidang: Perbankan | Status: tidak_diketahui
          08. [ID:25] 12 Tahun 2026 (POJK, -) | Bidang: Pasar Modal | Status: tidak_diketahui
          09. [ID:34] 3 Tahun 2026 (PADK, -) | Bidang: ITSK | Status: tidak_diketahui
          10. [ID:52] 4 Tahun 2026 (PADK, -) | Bidang: OJK Wide | Status: tidak_diketahui
          11. [ID:55] 8 Tahun 2026 (POJK, -) | Bidang: PVML | Status: tidak_diketahui
          12. [ID:61] 30 Tahun 2025 (POJK, -) | Bidang: ITSK | Status: tidak_diketahui
          13. [ID:64] 7 Tahun 2026 (POJK, -) | Bidang: Perbankan | Status: tidak_diketahui
          14. [ID:73] 6 Tahun 2026 (POJK, -) | Bidang: EPK | Status: tidak_diketahui
          15. [ID:19] PADK 8 Tahun 2026 (PADK, -) | Bidang: Pasar Modal | Status: tidak_diketahui
  [4/4] Menjadwalkan penarikan 15 dokumen ke Knowledge Base (format=['nama', 'jenis', 'tahun'])...
        [Menarik berkas...] Selesai: 1/15
        [Menarik berkas...] Selesai: 2/15
        [Menarik berkas...] Selesai: 4/15
        [Menarik berkas...] Selesai: 5/15
        [Menarik berkas...] Selesai: 7/15
        [Menarik berkas...] Selesai: 10/15
        [Menarik berkas...] Selesai: 10/15
        [Menarik berkas...] Selesai: 12/15
        [Menarik berkas...] Selesai: 13/15
        Penarikan selesai. Berhasil di-ingest ke Knowledge Base: 15/15 dokumen.

-----------------------------------------------------------------
PROSES SUMBER: [JDIH] JDIH OJK (Situs Resmi)
URL: https://jdih.ojk.go.id/ | Tipe: situs_web | Batas Paging: 2
-----------------------------------------------------------------
  [1/4] Sumber berhasil didaftarkan (Source ID: 2).
  [2/4] Menjadwalkan pemindaian (POST /api/v1/scans/, depth=1, max_pages=2)...
        [Memindai...] Halaman: 1, Kandidat: 0
        [Memindai...] Halaman: 1, Kandidat: 0
        [Memindai...] Halaman: 1, Kandidat: 0
        [Memindai...] Halaman: 1, Kandidat: 0
        [Memindai...] Halaman: 1, Kandidat: 0
        [Memindai...] Halaman: 1, Kandidat: 0
        [Memindai...] Halaman: 1, Kandidat: 0
        [Memindai...] Halaman: 1, Kandidat: 0
        [Memindai...] Halaman: 1, Kandidat: 0
        [Memindai...] Halaman: 1, Kandidat: 0
        [Memindai...] Halaman: 1, Kandidat: 0
        [Memindai...] Halaman: 2, Kandidat: 0
        [Memindai...] Halaman: 2, Kandidat: 0
        [Memindai...] Halaman: 2, Kandidat: 0
        [Memindai...] Halaman: 2, Kandidat: 0
        [Memindai...] Halaman: 2, Kandidat: 0
        [Memindai...] Halaman: 2, Kandidat: 0
        [Memindai...] Halaman: 2, Kandidat: 0
        [Memindai...] Halaman: 2, Kandidat: 0
        [Memindai...] Halaman: 2, Kandidat: 0
        [Memindai...] Halaman: 2, Kandidat: 0
        [Memindai...] Halaman: 2, Kandidat: 0
        Pemindaian selesai (Scan #2, Status: siap_dipilih). Total kandidat PDF ditemukan: 300
  [3/4] Menganalisis 200 kandidat berkas...
        Terpilih 15 kandidat 'utama' bervariasi:
          01. [ID:91] PADK 4 Tahun 2026 (PADK, -) | Bidang: Pasar Modal, Keuangan Derivatif, dan Bursa Karbon | Status: tidak_diketahui
          02. [ID:94] POJK 10 Tahun 2026 (POJK, -) | Bidang: Pasar Modal, Keuangan Derivatif, dan Bursa Karbon | Status: tidak_diketahui
          03. [ID:100] POJK 8 Tahun 2026 (POJK, -) | Bidang: Lembaga Pembiayaan,Perusahaan Modal Ventura,Lembaga Keuangan Mikro,dan Lembaga Jasa Keuangan Lainnya | Status: tidak_diketahui
          04. [ID:103] POJK 6 Tahun 2026 (POJK, -) | Bidang: Perilaku Pelaku Usaha Jasa Keuangan, Edukasi dan Pelindungan Konsumen | Status: tidak_diketahui
          05. [ID:106] POJK 7 Tahun 2026 (POJK, -) | Bidang: Perbankan | Status: tidak_diketahui
          06. [ID:112] 19/SEOJK.06/2024 (SEOJK, -) | Bidang: Lembaga Pembiayaan,Perusahaan Modal Ventura,Lembaga Keuangan Mikro,dan Lembaga Jasa Keuangan Lainnya | Status: tidak_diketahui
          07. [ID:117] 20/SEOJK.07/2024 (SEOJK, -) | Bidang: Inovasi Teknologi Sektor Keuangan, Aset Keuangan Digital dan Aset Kripto | Status: tidak_diketahui
          08. [ID:120] 21/SEOJK.05/2023 (SEOJK, -) | Bidang: Perasuransian, Penjaminan , dan Dana Pensiun | Status: tidak_diketahui
          09. [ID:124] PADK 2 Tahun 2026 (PADK, -) | Bidang: Lembaga Pembiayaan,Perusahaan Modal Ventura,Lembaga Keuangan Mikro,dan Lembaga Jasa Keuangan Lainnya | Status: tidak_diketahui
          10. [ID:142] 47/PADK.05/2025 (PADK, -) | Bidang: Perasuransian, Penjaminan , dan Dana Pensiun | Status: tidak_diketahui
          11. [ID:151] 44/PADK.01/2025 (PADK, -) | Bidang: Kebijakan Strategis | Status: tidak_diketahui
          12. [ID:154] 42/PADK.03/2025 (PADK, -) | Bidang: Perbankan | Status: tidak_diketahui
          13. [ID:169] 37/PADK.08/2025 (PADK, -) | Bidang: Perilaku Pelaku Usaha Jasa Keuangan, Edukasi dan Pelindungan Konsumen | Status: tidak_diketahui
          14. [ID:181] 31/SEOJK.03/2025 (SEOJK, -) | Bidang: Perbankan | Status: tidak_diketahui
          15. [ID:196] 25/SEOJK.04/2025 (SEOJK, -) | Bidang: Pasar Modal, Keuangan Derivatif, dan Bursa Karbon | Status: tidak_diketahui
  [4/4] Menjadwalkan penarikan 15 dokumen ke Knowledge Base (format=['nama', 'jenis', 'tahun'])...
        [Menarik berkas...] Selesai: 1/15
        [Menarik berkas...] Selesai: 3/15
        [Menarik berkas...] Selesai: 4/15
        [Menarik berkas...] Selesai: 8/15
        [Menarik berkas...] Selesai: 11/15
        [Menarik berkas...] Selesai: 11/15
        [Menarik berkas...] Selesai: 13/15
        Penarikan selesai. Berhasil di-ingest ke Knowledge Base: 11/15 dokumen.

-----------------------------------------------------------------
PROSES SUMBER: [ONEDRIVE] OneDrive Public DPEA
URL: https://oneojk-my.sharepoint.com/:f:/g/personal/faris_budi_ojk_go_id/IgC2eHe7uRwqT5X1zPBi_d1AAfA8Ec-W6i3BTN66ZgJI1rA?e=0yRyoP | Tipe: onedrive_public | Batas Paging: 3
-----------------------------------------------------------------
  [1/4] Sumber berhasil didaftarkan (Source ID: 3).
  [2/4] Menjadwalkan pemindaian (POST /api/v1/scans/, depth=2, max_pages=3)...
        [Memindai...] Halaman: 3, Kandidat: 0
        Pemindaian selesai (Scan #3, Status: siap_dipilih). Total kandidat PDF ditemukan: 2612
  [3/4] Menganalisis 200 kandidat berkas...
        Terpilih 15 kandidat 'utama' bervariasi:
          01. [ID:391] 3 (POJK, -) | Bidang: - | Status: tidak_diketahui
          02. [ID:394] 19 (PADK, -) | Bidang: - | Status: tidak_diketahui
          03. [ID:396] 6 (SEOJK, -) | Bidang: - | Status: tidak_diketahui
          04. [ID:407] 20 (-, -) | Bidang: - | Status: tidak_diketahui
          05. [ID:488] 27-164-KEP-DIR-1995 (KEPDIR, -) | Bidang: - | Status: tidak_diketahui
          06. [ID:528] 7 (PBI, -) | Bidang: - | Status: tidak_diketahui
          07. [ID:572] 17 (UU, -) | Bidang: - | Status: tidak_diketahui
          08. [ID:392] 27 (POJK, -) | Bidang: - | Status: tidak_diketahui
          09. [ID:395] 4 (PADK, -) | Bidang: - | Status: tidak_diketahui
          10. [ID:404] 22 (SEOJK, -) | Bidang: - | Status: tidak_diketahui
          11. [ID:408] 9685 (-, -) | Bidang: - | Status: tidak_diketahui
          12. [ID:492] 26-68-KEP-DIR-1993 (KEPDIR, -) | Bidang: - | Status: tidak_diketahui
          13. [ID:393] 3 (POJK, -) | Bidang: - | Status: tidak_diketahui
          14. [ID:400] 19 (PADK, -) | Bidang: - | Status: tidak_diketahui
          15. [ID:421] 31 (SEOJK, -) | Bidang: - | Status: tidak_diketahui
  [4/4] Menjadwalkan penarikan 15 dokumen ke Knowledge Base (format=['nama', 'jenis', 'tahun'])...
        [Menarik berkas...] Selesai: 6/15
        [Menarik berkas...] Selesai: 14/15
        Penarikan selesai. Berhasil di-ingest ke Knowledge Base: 15/15 dokumen.

=================================================================
EVALUASI DISTRIBUSI DOKUMEN KNOWLEDGE BASE SETELAH SEEDING
=================================================================

--- 1. Dokumen Masuk per Sumber ---
Kode Sumber  | Nama Sumber                      | Target   | Berhasil Masuk 
---------------------------------------------------------------------------
ojk          | Regulasi OJK (Situs Resmi)       | 15       | 15             
jdih         | JDIH OJK (Situs Resmi)           | 15       | 11             
onedrive     | OneDrive Public DPEA             | 15       | 15             
TOTAL        | Semua Sumber                     | 45       | 41             

--- 2. Distribusi Bidang (15 kategori, Total: 41) ---
Bidang / Sektor                               | Jumlah Dokumen 
-----------------------------------------------------------------
(kosong)                                      | 15             
Perbankan                                     | 4              
PVML                                          | 3              
Pasar Modal                                   | 3              
Pasar Modal, Keuangan Derivatif, dan Bursa Ka | 2              
ITSK                                          | 2              
EPK                                           | 2              
Lembaga Pembiayaan,Perusahaan Modal Ventura,L | 2              
Perasuransian, Penjaminan , dan Dana Pensiun  | 2              
BMKS                                          | 1              
PPDP                                          | 1              
OJK Wide                                      | 1              
Kebijakan Strategis                           | 1              
Perilaku Pelaku Usaha Jasa Keuangan, Edukasi  | 1              
Inovasi Teknologi Sektor Keuangan, Aset Keuan | 1              

--- 3. Distribusi Jenis Regulasi (7 jenis) ---
Jenis Regulasi                 | Jumlah Dokumen 
--------------------------------------------------
PADK                           | 14             
POJK                           | 11             
SEOJK                          | 10             
KEPDIR                         | 2              
(kosong)                       | 2              
UU                             | 1              
PBI                            | 1              

--- 4. Distribusi Tahun Regulasi (6 tahun) ---
Tahun                | Jumlah Dokumen 
----------------------------------------
2027                 | 1              
2026                 | 13             
2025                 | 9              
2024                 | 2              
2023                 | 1              
(kosong)             | 15             

--- 5. Distribusi Status Keberlakuan (3 nilai status) ---
Status Keberlakuan        | Jumlah Dokumen 
---------------------------------------------
tidak_diketahui           | 30             
berlaku                   | 10             
dicabut                   | 1              

=================================================================
OUTPUT MENTAH: GET /api/v1/dashboard/summary
=================================================================
{
  "kb": {
    "corpus_documents": 41,
    "draft_documents": 0,
    "target_fase1": 20,
    "target_met": true,
    "by_status_keberlakuan": {
      "berlaku": 10,
      "diubah": 0,
      "dicabut": 1,
      "tidak_diketahui": 30
    },
    "by_processing_status": {
      "diterima": 41,
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
        "count": 11
      },
      {
        "regulation_type": "SEOJK",
        "label": "SEOJK",
        "count": 10
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
        "regulation_type": "UU",
        "label": "UU",
        "count": 1
      },
      {
        "regulation_type": "PBI",
        "label": "PBI",
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
        "year": 2027,
        "label": "2027",
        "count": 1
      },
      {
        "year": 2026,
        "label": "2026",
        "count": 13
      },
      {
        "year": 2025,
        "label": "2025",
        "count": 9
      },
      {
        "year": 2024,
        "label": "2024",
        "count": 2
      },
      {
        "year": 2023,
        "label": "2023",
        "count": 1
      }
    ],
    "placed_documents": 41,
    "inbox_documents": 0
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
        "started_at": "2026-10-02T19:20:36.575000+00:00",
        "finished_at": "2026-10-02T19:21:00.050027+00:00",
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
        "started_at": "2026-10-02T19:18:54.831590+00:00",
        "finished_at": "2026-10-02T19:20:07.089121+00:00",
        "success_count": 11,
        "duplicate_count": 4,
        "skipped_count": 0,
        "failed_count": 0,
        "processed_count": 15,
        "total_found": 15
      },
      {
        "id": 1,
        "job_type": "scraping",
        "status": "selesai",
        "started_at": "2026-10-02T19:13:24.815876+00:00",
        "finished_at": "2026-10-02T19:15:00.756364+00:00",
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
  "generated_at": "2026-10-02T19:21:02.518914+00:00"
}

[SELESAI] Seeding data uji integrasi frontend selesai dilakukan.
```

---

## 4. Pengujian Otomatis & Determinisme Kontrak API

### 4.1 Output Pytest Langkah 11 (`tests/test_step11_frontend_support.py -v`)
```text
============================= test session starts =============================
platform win32 -- Python 3.13.7, pytest-9.1.1, pluggy-1.6.0 -- C:\Hero\hero-backend\venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Hero\hero-backend
plugins: anyio-4.15.1
collecting ... collected 5 items

tests/test_step11_frontend_support.py::test_f01_cors_preflight_and_get_5173 PASSED [ 20%]
tests/test_step11_frontend_support.py::test_f02_pdf_content_disposition_rfc5987 PASSED [ 40%]
tests/test_step11_frontend_support.py::test_f03_jdih_status_mapping_real_fixtures PASSED [ 60%]
tests/test_step11_frontend_support.py::test_f04_pull_candidate_jdih_dicabut PASSED [ 80%]
tests/test_step11_frontend_support.py::test_f05_doc_kind_detection_patterns PASSED [100%]

============================== warnings summary ===============================
venv\Lib\site-packages\fastapi\testclient.py:1
  C:\Hero\hero-backend\venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

venv\Lib\site-packages\starlette\testclient.py:53
  C:\Hero\hero-backend\venv\Lib\site-packages\starlette\testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================== 5 passed, 2 warnings in 7.56s ========================
```

### 4.2 Output Keseluruhan Test Suite (`pytest -q`)
```text
........................................................................ [ 33%]
............................................s........................... [ 66%]
........................................................................ [ 99%]
..                                                                       [100%]
============================== warnings summary ===============================
venv\Lib\site-packages\fastapi\testclient.py:1
  C:\Hero\hero-backend\venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

venv\Lib\site-packages\starlette\testclient.py:53
  C:\Hero\hero-backend\venv\Lib\site-packages\starlette\testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
217 passed, 1 skipped, 2 warnings in 320.51s (0:05:20)
```

### 4.3 Verifikasi Build Kontrak Ganda (SHA-256 Identik)
Pembangkit kontrak API dijalankan dua kali berturut-turut untuk memastikan keluaran 100% deterministik:
```text
Build 1 SHA256: 44e81297e8f91f67add1332d7b3597c2bbd9949173519583be8ca07a757d5df7
Build 2 SHA256: 44e81297e8f91f67add1332d7b3597c2bbd9949173519583be8ca07a757d5df7
Status Determinisme: IDENTIK (True)
```

---

## 5. Ringkasan Panduan Perubahan Frontend (`docs/api/frontend-changes-step11.md`)
Dokumen panduan khusus untuk frontend engineer telah disusun di `docs/api/frontend-changes-step11.md` yang merinci:
1. **Expose Headers CORS:** Header `Content-Disposition` dan `Content-Length` kini diekspos sehingga kode TypeScript frontend dapat mem-parsing nama berkas asli dari server.
2. **Parsing Nama Berkas RFC 5987:** Cuplikan implementasi JavaScript/TypeScript untuk membaca parameter `filename*` (UTF-8) dengan fallback ke `filename`.
3. **Pemanfaatan Status Keberlakuan:** Nilai status keberlakuan (`berlaku`, `dicabut`, `diubah`, `tidak_diketahui`) kini terisi langsung dari sumber resmi dan siap dikonsumsi oleh widget dashboard serta filter status.
4. **Cara Menjalankan Seeding Ulang:** Panduan penggunaan `scripts/seed_from_sources.py` bagi tim UI yang membutuhkan data uji bersih sewaktu-waktu.

---

## 6. Status Git Mentah (Terminal Output)

### 6.1 `git log --oneline -6`
```text
cedcfac docs(api): sinkronisasi kontrak api fase 1 hasil rebuild ganda deterministik
215ecb4 feat(seed): tambah scripts/seed_from_sources dan panduan perubahan frontend langkah 11
fbbbe55 feat(api): dukung CORS frontend, RFC 5987 filename, dan propagasi status keberlakuan dari JDIH
3a27cc2 docs(report): koreksi sisa langkah 10c dan penyempurnaan deteksi doc_kind variasi tanpa spasi
d35627a feat(crawler): finalize JDIH doc_kind synchronization and clarify record attribution
0306660 feat(crawler): align doc_kind consistency across sources and update benchmark stats
```

### 6.2 `git status --short`
```text
?? docs/reports/step11-report.md
```

### 6.3 `git remote -v`
```text
(kosong / tidak ada remote terkonfigurasi pada repositori lokal ini)
```
