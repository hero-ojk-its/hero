# Laporan Langkah 10e — Koreksi Review 10d & Verifikasi Penuh

> **Status:** Selesai & Terverifikasi Penuh  
> **Tanggal:** 2 Oktober 2026  
> **Branch:** `feat/step10-robust-scan`  
> **Prinsip:** Tidak mengarang angka; seluruh angka diverifikasi langsung dari output terminal dan berkas CSV/cache hasil regenerasi; data yang tidak terbukti dinyatakan "belum diketahui". Seluruh tautan lokal `file:///` dan label non-standar telah dihapus.

---

## 1. Ringkasan Tindakan & Koreksi Keamanan

Sesuai arahan review Langkah 10d, tindakan perbaikan keamanan berikut telah dilaksanakan:

1. **Pemisahan Kredensial & URL Share OneDrive:**
   - URL share folder publik OneDrive pada `scripts/scan_benchmark.py` dipindahkan ke environment variable `SCAN_ONEDRIVE_URL` (dengan fallback default aman).
   - Variabel `SCAN_ONEDRIVE_URL` ditambahkan ke `.env.example` dengan nilai placeholder deskriptif.
2. **Redaksi URL Share, Path, dan Fixture di HEAD:**
   - Seluruh tautan SharePoint publik (kode token `redacted_id...` dan query `?e=...`) serta path akun OneDrive pada seluruh berkas HEAD laporan (`step10-report.md`, `step10b-report.md`, `step10c-report.md`, `step10d-report.md`, `scan-benchmark-2026-10-01.md`, `scan-benchmark-2026-10-02.md`, kontrak API, dan runbook) telah diganti dengan `"[link share OneDrive DPEA]"`.
   - Nama-nama personil NDA pada berkas pengujian (`tests/test_crawler_robust.py`) diganti dengan nama sintetis (`NDA Personil Synthetic Name_Backend.pdf`).
   - Tiga nilai `formDigestValue` pada berkas fixture HTML OJK (`tests/fixtures/live_snapshots/ojk_regulasi_detail_sample.html`, `ojk_regulasi_page1.html`, dan `ojk_regulasi_page2_postback.html`) diredaksi menjadi `"REDACTED"`.
3. **Pembersihan Riwayat Git Penuh (*git-filter-repo*):**
   - Riwayat Git telah dibersihkan secara menyeluruh menggunakan `git-filter-repo --replace-text` untuk menghapus seluruh jejak token SharePoint, nama pengguna, dan personil NDA.
   - Branch cadangan `backup/pre-scrub` telah dihapus secara permanen.
   - Diverifikasi dengan `git cat-file --batch-all-objects --batch | grep -a -c` dan `git log --all -S`.

---

## 2. Perbaikan Parser OneDrive (Regresi Nomor & 0 Warnings)

### 2.1 Analisis & Solusi Regresi Nomor
- **Penyebab Regresi:** Pada Langkah 10d, pembersihan SharePoint hex decoding `_20` $\to$ spasi secara global memakan angka `20` pada dokumen seperti `Surat_Edaran_OJK_20_2017.pdf`, `Surat_Edaran_OJK_20_2014.pdf`, dan `Peraturan_Bank_Indonesia_20_2008.pdf`. Hal serupa terjadi pada `_29` (`Surat_Edaran_OJK_29_2016.pdf`, `Surat_Edaran_OJK_29_2025.pdf`).
- **Solusi di `app/crawlers/url_utils.py`:**
  Pola decoding SharePoint dibatasi khusus untuk sequence escape encoding SharePoint (seperti `_20[A-Za-z]` atau `_20_28`) dan bukan pasangan angka murni yang merupakan nomor regulasi.
- **Pembuangan Awalan Indeks:**
  Pola awalan penomoran arsip seperti `^\d+_-_` dibuang sebelum ekstraksi nomor hukum, sehingga nomor regulasi yang dihasilkan adalah nomor resmi (`9` dan `357`) dan `match_warning` turun menjadi **0**.

### 2.2 Verifikasi Komparasi Nomor 10c vs 10e
Perbandingan baris per baris terhadap hasil ekstraksi Langkah 10c menunjukkan bahwa tidak ada nomor regulasi valid yang hilang secara tidak sengaja. Terdapat **7 baris** yang kehilangan nomor regulasi dibandingkan versi 10c, di mana pada versi 10c nomor tersebut merupakan hasil ekstraksi keliru (*false positive*):

1. `7378797e-ca66-8d2a-93c6-237751767052.pdf`:
   - *Versi 10c:* Nomor `237751767052` (mengambil segmen akhir GUID SharePoint).
   - *Versi 10e:* Dikenali secara benar sebagai GUID tanpa nomor regulasi.
2. `19_-_522DPNP.pdf`:
   - *Versi 10c:* Nomor `19` (mengambil awalan indeks folder `19_-_`).
   - *Pemeriksaan Nomor Asli:* Nomor surat edaran Bank Indonesia sebenarnya adalah `5/22/DPNP`, namun pada berkas tertulis menyatu `522DPNP` tanpa pemisah. Angka `19` adalah indeks arsip, bukan nomor regulasi.
3. `13_-_SE_BI_1324DPNP.pdf`:
   - *Versi 10c:* Nomor `13` (mengambil awalan indeks folder `13_-_`).
   - *Pemeriksaan Nomor Asli:* Nomor surat edaran Bank Indonesia sebenarnya adalah `13/24/DPNP`, namun tertulis menyatu `1324DPNP`. Angka `13` adalah indeks arsip, bukan nomor regulasi.
4. `Lampiran_Lampiran_20RPADK_20Country_20dan_20Transfer_20Risk.pdf`:
   - *Versi 10c:* Nomor `20` (mengambil `_20` sebelum RPADK yang sebenarnya merupakan escape encoding spasi SharePoint `%20`).
   - *Versi 10e:* Dikenali sebagai naskah rancangan/draft RPADK tanpa nomor resmi.
5. `Rancangan_20PADK_20Penerapan_20Tata_20Kelola_20Terintegrasi_20Bagi_20PIKK.pdf`:
   - *Versi 10c:* Nomor `20` (mengambil `_20` spasi). Merupakan rancangan PADK tanpa nomor resmi.
6. `RPOJK_20Penyelenggaraan_20Structured_20Product_20oleh_20Bank_20Umum_20_28RPOJK_20SP_29.pdf`:
   - *Versi 10c:* Nomor `20` (mengambil `_20` spasi). Merupakan naskah draft RPOJK tanpa nomor resmi.
7. `Lampiran_20RPOJK_20Penyelenggaraan_20Structured_20Product_20oleh_20Bank_20Umum_20_28RPOJK_20SP_29.pdf`:
   - *Versi 10c:* Nomor `20` (mengambil `_20` spasi). Merupakan naskah lampiran draft RPOJK tanpa nomor resmi.

Kasus uji spesifik di `tests/test_crawler_robust.py` (`test_t05`) telah diperbarui dan memvalidasi nama-nama asli berikut:
- `Surat_Edaran_OJK_20_2017.pdf` $\to$ Nomor: `20`, Tahun: `2017`, Jenis: `SEOJK`
- `Surat_Edaran_OJK_20_2014.pdf` $\to$ Nomor: `20`, Tahun: `2014`, Jenis: `SEOJK`
- `Peraturan_Bank_Indonesia_20_2008.pdf` $\to$ Nomor: `20`, Tahun: `2008`, Jenis: `PBI`
- `Surat_Edaran_OJK_29_2016.pdf` $\to$ Nomor: `29`, Tahun: `2016`, Jenis: `SEOJK`
- `Surat_Edaran_OJK_29_2025.pdf` $\to$ Nomor: `29`, Tahun: `2025`, Jenis: `SEOJK`
- `43_-_Rijksblaad_dari_Daerah_Paku_Alaman_Tahun_1937_Nomor_9.pdf` $\to$ Nomor: `9`, Tahun: `1937`
- `42_-_Staatsblad_Tahun_1929_Nomor_357.pdf` $\to$ Nomor: `357`, Tahun: `1929`

---

## 3. Rujukan Hasil Live Scan Benchmark

Rincian lengkap hasil live scan benchmark 3 sumber data merujuk langsung pada berkas laporan [docs/reports/scan-benchmark-2026-10-02.md](docs/reports/scan-benchmark-2026-10-02.md) dan cache [docs/reports/benchmark_cache.json](docs/reports/benchmark_cache.json) tanpa modifikasi:

- **Portal Regulasi OJK (`ojk_portal` / `sharepoint_postback`):**
  - Halaman Terakhir: 158 halaman (postback p1–p158)
  - Jumlah Regulasi Ditemukan: 1.577 regulasi
  - Jumlah Berkas PDF Ditemukan: 2.665 berkas
  - Lengkap Metadata Hukum: 2.665 / 2.665 (100,0%)
  - Match Warnings: 25 warnings
  - Ground Truth: ± 1.700 regulasi (Selisih: -123)
  - HTTP Requests: 4.400 requests
  - Durasi Eksekusi: 3.017,22 detik (~50m 17s)
  - Status: Sukses
- **Portal JDIH OJK (`jdih_api`):**
  - Halaman Terakhir: 20 batch offset (iDisplayStart 0–985)
  - Jumlah Regulasi Ditemukan: 985 regulasi
  - Jumlah Berkas PDF Ditemukan: 1.652 berkas
  - Lengkap Metadata Hukum: 1.652 / 1.652 (100,0%)
  - Match Warnings: 67 warnings
  - Ground Truth: ± 400–500 regulasi (Selisih: +535 terhadap titik tengah 450)
  - HTTP Requests: 2.680 requests
  - Durasi Eksekusi: 837,12 detik (~13m 57s)
  - Total Rekod Portal API: 986 rekod
  - Status: Sukses
- **OneDrive Public DPEA (`onedrive_share`):**
  - Folder Traversal: 5 subfolder dikunjungi
  - Total Berkas Ditemukan: 2.619 berkas (2.612 berkas di subfolder `downloads`, 7 berkas non-regulasi pada subfolder `Administration` dan `User Requirement & Project Charter`)
  - Berkas Berkunci Hukum Lengkap: 2.135 / 2.619 (81,5%)
  - Match Warnings: 0 warning
  - Ground Truth: Belum ada dari mitra
  - HTTP Requests: 11 requests
  - Durasi Eksekusi: 7,34 detik
  - Status: Sukses

---

## 4. Perhitungan Akurat Metadata OneDrive (§4.1)

Perhitungan berikut dihitung langsung dari berkas regenerasi `docs/reports/scan-benchmark-onedrive.csv` (2.619 baris).

### 4.1 Perintah Terminal Perhitungan
```bash
.\venv\Scripts\python.exe -c "
import csv
with open('docs/reports/scan-benchmark-onedrive.csv', mode='r', encoding='utf-8') as f:
    r = list(csv.DictReader(f))
total = len(r)
num_ok = sum(1 for x in r if x.get('regulation_number'))
yr_ok = sum(1 for x in r if x.get('release_year'))
tp_ok = sum(1 for x in r if x.get('regulation_type'))
warn_ok = sum(1 for x in r if bool(x.get('match_warning')))
full_legal = sum(1 for x in r if x.get('regulation_number') and x.get('release_year') and x.get('regulation_type'))

print(f'Total: {total}')
print(f'regulation_number: {num_ok} ({num_ok/total*100:.1f}%), kosong: {total-num_ok} ({(total-num_ok)/total*100:.1f}%)')
print(f'release_year: {yr_ok} ({yr_ok/total*100:.1f}%), kosong: {total-yr_ok} ({(total-yr_ok)/total*100:.1f}%)')
print(f'regulation_type: {tp_ok} ({tp_ok/total*100:.1f}%), kosong: {total-tp_ok} ({(total-tp_ok)/total*100:.1f}%)')
print(f'metadata hukum lengkap (nomor+tahun+jenis): {full_legal} ({full_legal/total*100:.1f}%)')
print(f'match_warning: {warn_ok} ({warn_ok/total*100:.1f}%)')
"
```

### 4.2 Hasil Perhitungan Metadata OneDrive
- **Total Baris Berkas:** 2.619 berkas (2.612 subfolder `downloads`, 7 subfolder non-regulasi).
- **`regulation_number`:**
  - Terisi: **2.511 berkas (95,9%)**
  - Kosong: **108 berkas (4,1%)** *(nama GUID SharePoint, topik umum tanpa nomor, dan 7 berkas administrasi)*.
- **`release_year`:**
  - Terisi: **2.489 berkas (95,0%)**
  - Kosong: **130 berkas (5,0%)**
- **`regulation_type`:**
  - Terisi: **2.176 berkas (83,1%)**
  - Kosong: **443 berkas (16,9%)**
- **Metadata Hukum Lengkap (`regulation_number` + `release_year` + `regulation_type`):**
  - Terisi Lengkap: **2.135 berkas (81,5%)**
- **`release_date` & `effective_date`:**
  - Terisi: **0 berkas (0,0%)** *(dikosongkan karena nama berkas OneDrive hanya memuat tahun tanpa tanggal/bulan pasti)*.
- **`match_warning`:**
  - Terisi True: **0 berkas (0,0%)** (dihitung menggunakan `bool(x['match_warning'])`).
  - Bersih (kosong / False): **2.619 berkas (100,0%)**.

---

## 5. Pencocokan Data OneDrive vs Portal OJK (§4.4)

Pencocokan dilakukan menggunakan skrip reprodusibel `scripts/match_onedrive_ojk.py` dan menghasilkan CSV keluaran `docs/reports/match-onedrive-ojk.csv`.

### 5.1 Perintah Terminal Pencocokan
```bash
.\venv\Scripts\python.exe scripts/match_onedrive_ojk.py
```

### 5.2 Hasil Ringkasan Pencocokan (Folder Downloads: 2.612 Berkas)

Dari total 2.612 berkas pada folder `downloads`, pencocokan otomatis terhadap Portal Regulasi OJK membagi berkas menjadi:
- **Berkas dengan Kunci Lengkap (Jenis + Nomor + Tahun):** **2.135 berkas**
  - **Cocok Tepat (*Exact Match* pada Portal OJK):** **1.094 berkas (41,9% dari total, atau 51,2% dari berkas berkunci lengkap)**
  - **Tidak Cocok (*Unmatched* pada Portal OJK):** **1.041 berkas (39,9% dari total, atau 48,8% dari berkas berkunci lengkap)**
- **Berkas Tanpa Kunci Lengkap (*Incomplete Key*):** **477 berkas (18,3% dari total)**  
  *(Tidak dapat dicocokkan secara otomatis karena tidak memiliki salah satu atau lebih atribut kunci: jenis, nomor, atau tahun)*.

### 5.3 Rincian 1.041 Berkas Berkunci Lengkap yang Tidak Cocok

| Kelompok Periode | Jenis Regulasi | Jumlah Berkas | Keterangan / Analisis |
|---|---|---|---|
| **Tahun $\ge 2013$ (Era OJK)** | **PADK (Peraturan ADK)** | **891 berkas** | [Hipotesis] Regulasi Anggota Dewan Komisioner internal OJK tidak seluruhnya dipublikasikan pada portal web publik OJK (hasil crawl portal publik OJK hanya menemukan 69 PADK). |
| | **SEOJK** | 32 berkas | [Hipotesis] Surat Edaran teknis spesifik perbankan/IKNB atau naskah penetapan internal yang tidak diindeks pada portal web umum. |
| | **POJK** | 10 berkas | [Hipotesis] Naskah lampiran atau penomoran internal tertentu. |
| | **PBI (Era OJK)** | 7 berkas | [Hipotesis] Regulasi transisi Bank Indonesia tahun 2013 yang disimpan di repositori kerja. |
| | **Lainnya (UU, KDK, PDK)** | 3 berkas | [Hipotesis] Regulasi perundang-undangan nasional atau keputusan dewan komisioner. |
| **Tahun $< 2013$ (Historis)** | **PADK (Historis)** | 43 berkas | [Hipotesis] Arsip naskah komisioner awal pembentukan OJK. |
| | **PBI (Peraturan BI)** | 17 berkas | [Hipotesis] Regulasi perbankan sebelum pengalihan pengawasan perbankan ke OJK. |
| | **KEPDIR (SK Direksi BI)** | 16 berkas | [Hipotesis] Ketentuan perbankan lama era Bank Indonesia. |
| | **UU (Perundang-undangan)** | 12 berkas | [Hipotesis] Undang-Undang perbankan/pasar modal lama. |
| | **POJK (Historis)** | 8 berkas | [Hipotesis] Regulasi awal pembentukan OJK. |
| | **KDK (Keputusan DK)** | 2 berkas | [Hipotesis] Naskah keputusan Dewan Komisioner awal. |
| **Total Tidak Cocok (Kunci Lengkap)** | | **1.041 berkas** | |

---

## 6. Temuan & Bukti Teknis JDIH OJK

### 6.1 Analisis Distribusi Status Regulasi JDIH API
Pemeriksaan langsung pada endpoint API JDIH (`https://jdih.ojk.go.id/Web/ViewPeraturanHome/ListDataPeraturan`) untuk seluruh 986 rekod menghasilkan distribusi sebagai berikut:

- **Total Rekod Peraturan Aktif di JDIH:** **986 rekod** (`iTotalRecords = 986`, `iTotalDisplayRecords = 986`).
- **Distribusi Status:**
  - **Berlaku:** 717 rekod (72,72%)
  - **Tidak Berlaku (Dicabut/Tidak Berlaku):** 253 rekod (25,66%)
  - **Berlaku (Dicabut Sebagian):** 11 rekod (1,12%)
  - **Berlaku (Perubahan) (Diubah):** 4 rekod (0,41%)
  - **Berlaku (Perubahan) (Mengubah):** 1 rekod (0,10%)
  - *Total status berlaku / perubahannya:* 733 rekod (74,34%).
- **Distribusi per Jenis Regulasi:**
  - **Peraturan OJK (POJK):** 565 rekod (410 Berlaku, 139 Tidak Berlaku, 11 Dicabut Sebagian, 4 Diubah, 1 Mengubah).
  - **Surat Edaran OJK / PADK:** 408 rekod (295 Berlaku, 113 Tidak Berlaku).
  - **Undang-Undang:** 12 rekod (11 Berlaku, 1 Tidak Berlaku).
  - **Peraturan Pemerintah:** 1 rekod (1 Berlaku).

### 6.2 Evaluasi Hipotesis Rentang 400–500
- Hipotesis bahwa JDIH memuat 400–500 regulasi karena "hanya memuat POJK" **tidak terbukti secara empiris**, karena jumlah total POJK sendiri mencapai **565 rekod** ($> 500$).
- Namun, jumlah **POJK berstatus Berlaku (410 rekod)** dan jumlah **SEOJK/PADK (408 rekod)** berada pada rentang 400–500. Angka ground truth mitra (400–500) kemungkinan merujuk pada salah satu subhimpunan tersebut, sedangkan keseluruhan database JDIH memuat 986 regulasi induk yang menghasilkan 1.652 berkas dokumen.

### 6.3 Analisis Selisih 986 Rekod API vs 985 Regulasi Tersimpan
Pemeriksaan rekod demi rekod antara API JDIH (986) dan CSV scan (985) mengidentifikasi rekod tunggal yang tidak tersimpan di CSV:
- **GUID Rekod:** `61e9d691-dfeb-9ea2-8b38-42696bfad8e9`
- **Judul Regulasi:** *Surat Edaran Otoritas Jasa Keuangan Republik Indonesia Nomor 21/SEOJK.04/2021 tentang Penilaian Kemampuan dan Kepatutan bagi Calon Pihak Utama Perusahaan Pemeringkat Efek*.
- **Pemeriksaan Deduplikasi Judul:** Tidak ditemukan duplikasi judul pada CSV (0 rekod berulang).
- **Penyebab:** Pada halaman detail server JDIH (`https://jdih.ojk.go.id/Web/ViewPeraturan/Detail/61e9d691-dfeb-9ea2-8b38-42696bfad8e9/All/`), **tidak terdapat berkas dokumen lampiran apa pun** (`DownloadDokumen: False`, daftar lampiran kosong `[]`). Karena arsitektur crawler JDIH hanya menyimpan regulasi yang memiliki berkas lampiran unduhan (`if found_any_for_reg: regulations_count += 1`), rekod ini tidak menghasilkan entri berkas pada CSV.

### 6.4 Investigasi 22 PDF Tanpa Ukuran (`size_source="unknown"`)
- **Status Unduh Dokumen JDIH:** **PDF dapat diunduh: 1.630 dari 1.652 berkas**.
- Sebanyak 22 berkas lampiran/ringkasan lama tertentu mengembalikan **HTTP 500 Internal Server Error** (dengan badan respons HTML) saat diakses oleh crawler pada endpoint dokumen lampiran JDIH (`https://jdih.ojk.go.id/Web/ViewPeraturan/DownloadDokumen/<UUID>`), sehingga crawler mencatat `size_bytes = None` dan `size_source = "unknown"`.

Berikut adalah daftar lengkap status HTTP hasil pengujian langsung terhadap seluruh 22 UUID dokumen:

| No | UUID Dokumen | Nomor Regulasi | Nama Berkas | HEAD Status | Content-Type | GET Range Status | Keterangan Server |
|---|---|---|---|---|---|---|---|
| 1 | `41b95752-62d7-f761-9eab-3a7732742446` | 14/SEOJK.03/2017 | `11 - FAQ SEOJK 14 - 2017.pdf` | 500 | `text/html; charset=utf-8` | 500 | Server Gagal Menyajikan Berkas |
| 2 | `45287961-0ac1-2010-96ea-a61b8e75b7fc` | 14/SEOJK.03/2017 | `12 - Ringkasan SEOJK 14 - 2017.pdf` | 500 | `text/html; charset=utf-8` | 500 | Server Gagal Menyajikan Berkas |
| 3 | `8a4f7789-6378-2bfc-c4e1-455a3ddae470` | 12/SEOJK.03/2017 | `7 - Ringkasan SEOJK 12 - 2017.pdf` | 500 | `text/html; charset=utf-8` | 500 | Server Gagal Menyajikan Berkas |
| 4 | `15495364-5b37-048d-58d5-b529bf30c570` | 12/SEOJK.03/2017 | `8 - FAQ SEOJK 12 - 2017.pdf` | 500 | `text/html; charset=utf-8` | 500 | Server Gagal Menyajikan Berkas |
| 5 | `8f71d2bd-7da5-281a-306f-2655d9f38d55` | 11/SEOJK.03/2017 | `5 - Ringkasan SEOJK 11 - 2017.pdf` | 500 | `text/html; charset=utf-8` | 500 | Server Gagal Menyajikan Berkas |
| 6 | `e8022755-f9eb-628f-2f7b-cf09e8d164f4` | 11/SEOJK.03/2017 | `6 - FAQ SEOJK 11 - 2017.pdf` | 500 | `text/html; charset=utf-8` | 500 | Server Gagal Menyajikan Berkas |
| 7 | `f4154397-7ff1-c80f-08bd-0bb46e6d8097` | 14/POJK.03/2017 | `FAQ POJK 14.pdf` | 500 | `text/html; charset=utf-8` | 500 | Server Gagal Menyajikan Berkas |
| 8 | `698835d6-0b81-1492-cb88-c69b7eb5e6d7` | 14/POJK.03/2017 | `Ringkasan POJK 14.pdf` | 500 | `text/html; charset=utf-8` | 500 | Server Gagal Menyajikan Berkas |
| 9 | `fec97213-45f0-29bf-f6ad-178650c34b5c` | 15/POJK.03/2017 | `FAQ POJK 15.pdf` | 500 | `text/html; charset=utf-8` | 500 | Server Gagal Menyajikan Berkas |
| 10 | `7b8e76db-9d2c-fcbe-f76e-e2f04e2f073f` | 15/POJK.03/2017 | `Ringkasan POJK 15.pdf` | 500 | `text/html; charset=utf-8` | 500 | Server Gagal Menyajikan Berkas |
| 11 | `d45e84c8-afde-0880-8df7-0c50b8271e8d` | 38/POJK.03/2017 | `Ringkasan 38 POJK.pdf` | 500 | `text/html; charset=utf-8` | 500 | Server Gagal Menyajikan Berkas |
| 12 | `f8e8afee-28b5-7808-3e45-ca6f045e144b` | 38/POJK.03/2017 | `FAQ POJK 38.pdf` | 500 | `text/html; charset=utf-8` | 500 | Server Gagal Menyajikan Berkas |
| 13 | `cc93b740-0d5f-ad3f-bc76-213cc402075c` | 45/POJK.03/2017 | `Ringkasan POJK 45.pdf` | 500 | `text/html; charset=utf-8` | 500 | Server Gagal Menyajikan Berkas |
| 14 | `d05ae8e7-1fa1-4ecf-9bce-8dd02b73e889` | 45/POJK.03/2017 | `FAQ POJK 45.pdf` | 500 | `text/html; charset=utf-8` | 500 | Server Gagal Menyajikan Berkas |
| 15 | `7ebedc4e-c874-18cb-b3ef-b6b9495c0521` | 48/POJK.03/2017 | `Ringkasan POJK 48.pdf` | 500 | `text/html; charset=utf-8` | 500 | Server Gagal Menyajikan Berkas |
| 16 | `c27d66fe-907f-fd58-7706-37c8a6ed67dd` | 48/POJK.03/2017 | `FAQ POJK 48.pdf` | 500 | `text/html; charset=utf-8` | 500 | Server Gagal Menyajikan Berkas |
| 17 | `e8944864-2052-84c8-a737-b2158edb5eeb` | 51/POJK.03/2017 | `Ringkasan POJK 51.pdf` | 500 | `text/html; charset=utf-8` | 500 | Server Gagal Menyajikan Berkas |
| 18 | `5b6bcd52-fa45-a44d-720f-50fdfc761519` | 1/SEOJK.03/2019 | `Ringkasan SEOJK 1 - 2019.pdf` | 500 | `text/html; charset=utf-8` | 500 | Server Gagal Menyajikan Berkas |
| 19 | `c8633da9-cbd5-e361-85e3-658c61933dcc` | 37/POJK.03/2019 | `FAQ POJK 37 - 2019.pdf` | 500 | `text/html; charset=utf-8` | 500 | Server Gagal Menyajikan Berkas |
| 20 | `ce7f54d3-aac0-dc9e-34e1-16196c70977a` | 11/POJK.03/2019 | `Ringkasan POJK 11 - 2019.pdf` | 500 | `text/html; charset=utf-8` | 500 | Server Gagal Menyajikan Berkas |
| 21 | `cf0cef55-b3d2-400a-7399-2e03403050b6` | 11/POJK.03/2016 | `POJK 27-2022.pdf` | 500 | `text/html; charset=utf-8` | 500 | Server Gagal Menyajikan Berkas |
| 22 | `d330a525-22ce-cad7-79b6-6006061605d6` | 11/POJK.03/2016 | `Ringkasan POJK 27-2022.pdf` | 500 | `text/html; charset=utf-8` | 500 | Server Gagal Menyajikan Berkas |

---

## 7. Bukti Eksekusi & Verifikasi Keamanan Mentah

### 7.1 Bukti Scrubbing Riwayat Git (`git cat-file`)
```text
PS C:\Users\IBUCOMP\Downloads\hero-backend> git cat-file --batch-all-objects --batch | grep -a -c "[link share OneDrive DPEA]"
0
PS C:\Users\IBUCOMP\Downloads\hero-backend> git cat-file --batch-all-objects --batch | grep -a -c "redacted_token5Zz0xHv3V1d8iK"
0
PS C:\Users\IBUCOMP\Downloads\hero-backend> git cat-file --batch-all-objects --batch | grep -a -c "redacted_id9P3pSZ1l19Hq"
0
PS C:\Users\IBUCOMP\Downloads\hero-backend> git cat-file --batch-all-objects --batch | grep -a -c "Personil_A"
0
PS C:\Users\IBUCOMP\Downloads\hero-backend> git cat-file --batch-all-objects --batch | grep -a -c "Personil_B"
0
PS C:\Users\IBUCOMP\Downloads\hero-backend> git log --all -S "[link share OneDrive DPEA]"
PS C:\Users\IBUCOMP\Downloads\hero-backend> git log --all -S "redacted_token5Zz0xHv3V1d8iK"
PS C:\Users\IBUCOMP\Downloads\hero-backend> git log --all -S "redacted_id9P3pSZ1l19Hq"
```

### 7.2 Status Branch Lokal
```text
PS C:\Users\IBUCOMP\Downloads\hero-backend> git branch -a
  feat/step0-1-ingest-pipeline
* feat/step10-robust-scan
  feat/step2-3-failures-naming
  feat/step4-5-search-detail
  feat/step6-local-folder
  feat/step7-site-scan
  feat/step8-deploy-readiness
  feat/step9-api-contract-rename
  main
```

### 7.3 Output Pengujian Unit Test Penuh (`pytest -q`)
```text
PS C:\Users\IBUCOMP\Downloads\hero-backend> .\venv\Scripts\python.exe -m pytest -q
........................................................................ [ 33%]
............................................s........................... [ 67%]
.....................................................................    [100%]
============================== warnings summary ===============================
venv\Lib\site-packages\fastapi\testclient.py:1
  C:\Users\IBUCOMP\Downloads\hero-backend\venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

venv\Lib\site-packages\starlette\testclient.py:53
  C:\Users\IBUCOMP\Downloads\hero-backend\venv\Lib\site-packages\starlette\testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
212 passed, 1 skipped, 2 warnings in 186.54s (0:03:06)
```

### 7.4 Log Commit Terakhir (`git log --oneline -5`)
```text
PS C:\Users\IBUCOMP\Downloads\hero-backend> git log --oneline -5
fbd9859 docs(report): koreksi laporan langkah 10e dan redaksi formDigestValue fixture
e4f2737 feat(crawler): add onedrive vs ojk matcher and step10e verification report
6e17533 fix(crawler): resolve onedrive regex regression for regulation numbers and strip index prefixes
4468071 fix(security): sanitize onedrive share url and redact personnel metadata
6e9b5bb docs(report): create comprehensive Langkah 10d benchmark and review report
```

---

## 8. Kesimpulan & Status Akhir

1. Seluruh tautan sensitif, kredensial OneDrive, 3 formDigestValue HTML fixture, dan nama personil telah dibersihkan secara permanen dari HEAD dan riwayat commit.
2. Regresi parser OneDrive berhasil diselesaikan dengan 0 match warning dan penjelasan transparan atas 7 nomor false-positive dari Langkah 10c.
3. Seluruh angka benchmark dan pencocokan telah dihitung secara matematis dan diverifikasi dari CSV/cache aktif.
4. Investigasi teknis JDIH membuktikan rekod tanpa lampiran (1 rekod hilang) dan kendala HTTP 500 server JDIH pada 22 berkas lama.
5. Kode backend dan dokumentasi laporan berada dalam kondisi stabil dan terverifikasi penuh.
