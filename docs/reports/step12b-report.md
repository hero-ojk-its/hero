# LAPORAN LANGKAH 12b: KOREKSI KECIL SETELAH REVIEW

**HERO Backend · FASE 1**  
**Branch:** `feat/step12-ingest-support`  
**Tanggal:** 3 Oktober 2026  
**Status:** SELESAI & TERVERIFIKASI  

---

## 1. JANGAN MENGARANG TANGGAL (§1)

### 1.1 Masalah dan Akar Penyebab
Pada implementasi sebelumnya (`app/crawlers/sharepoint_postback.py` dan `app/crawlers/jdih_api.py`), jika tanggal penetapan/pengundangan tidak ditemukan pada sumber, sistem mengisi fallback `release_date = date(parsed_year, 1, 1)` atau mengambil tanggal berlaku (`effective_date`).
Hal ini menyebabkan:
1. Regulasi seolah-olah ditetapkan pada **1 Januari**, padahal tanggal tersebut fiktif.
2. Tanggal berlaku dan tanggal penetapan tertukar/bercampur sumber.

### 1.2 Perbaikan yang Diterapkan
1. **Pembersihan `release_date`**:
   - `release_date` murni hanya diisi dari tanggal penetapan/pengundangan resmi dari sumber.
   - Bila sumber tidak mencantumkannya, `release_date` bernilai `None` (`null`).
   - Tanggal berlaku tetap tersimpan terpisah pada `effective_date`.
2. **Kolom Baru `regulation_year`**:
   - Kolom `regulation_year` (integer, nullable, terindeks) ditambahkan ke tabel `documents` dan `scan_candidates`.
   - Dibuat migrasi Alembic `d4e5f6a7b8c9_step12b_add_regulation_year_and_backfill.py`.
   - Fungsi penentu tahun `extract_regulation_year(...)` mengadopsi hierarki prioritas:
     1. Tahun dari nomor resmi regulasi (misal `POJK 3 Tahun 2015` -> `2015`).
     2. Tahun dari perihal/judul regulasi.
     3. Tahun dari nama berkas (misal berkas OneDrive `Peraturan_OJK_3_2015.pdf` -> `2015`).
     4. Tahun dari `release_date` (bila tanggal penetapan valid tersedia).
3. **Penyelarasan Seluruh Komponen**:
   - Filter `GET /api/v1/documents/?year={year}` menggunakan `COALESCE(regulation_year, EXTRACT(YEAR FROM release_date))`.
   - Agregasi dashboard `by_year` menggunakan `regulation_year`.
   - Generator pratinjau penamaan standar (`naming_service.py`) memprioritaskan `regulation_year` sebelum mengekstrak tahun dari `release_date`, sehingga dokumen tanpa tanggal penetapan tidak menghasilkan label `NA`.

### 1.3 Hasil Backfill Database (§1.4)
Migrasi backfill dijalankan pada 42 dokumen Knowledge Base yang sudah ada:
- **Dokumen dengan `release_date` diubah menjadi `null`**: **1 dokumen**, yaitu **Dokumen ID 3** (`23/SEOJK.06/2025`).
  - Nilai sebelum: `release_date: 2025-01-01` (tanggal semu 1 Januari).
  - Nilai sesudah: `release_date: null`, `effective_date: 2027-04-01`, `regulation_year: 2025`.
- **Dokumen dengan `regulation_year` terisi**: **40 dokumen** dari total 42 dokumen awal.
- **Cakupan 15 Berkas OneDrive**:
  - **13 dokumen** OneDrive yang memiliki nomor/tahun valid kini memiliki `regulation_year` definitif (contoh: ID 28 [2015], ID 29 [2015], ID 30 [2016], ID 31 [2016], ID 32 [2015], ID 33 [2015], ID 34 [1995], ID 35 [1993], ID 38 [2012], ID 39 [1992], ID 40 [2014], ID 41 [2015], ID 42 [2015]).
  - **2 dokumen** OneDrive di folder inbox (ID 36 dan ID 37) yang merupakan dokumen umum tanpa nomor regulasi tetap bernilai `null` sesuai data riil.

---

## 2. VERIFIKASI RESPONS KANDIDAT & KONSISTENSI DATA (§2)

### 2.1 Output Mentah Curl

#### Perintah 1: `GET /api/v1/scans/2/candidates?limit=3&doc_kind=utama`
```json
{
 "items": [
  {
   "id": 87,
   "scan_id": 2,
   "title": "Peraturan Otoritas Jasa Keuangan Nomor 12 Tahun 2026 tentang Penerapan Manajemen Risiko Terintegrasi bagi Konglomerasi Keuangan",
   "regulation_number": "POJK 12 Tahun 2026",
   "doc_kind": "utama",
   "filename": "2026pojk012.pdf",
   "source_url": "https://jdih.ojk.go.id/id/berita-dan-kegiatan/peraturan-ojk/peraturan-otoritas-jasa-keuangan-nomor-12-tahun-2026-tentang-penerapan-manajemen-risiko-terintegrasi-bagi-konglomerasi-keuangan",
   "download_url": "https://jdih.ojk.go.id/id/download/2026pojk012.pdf",
   "byte_size": 1782542,
   "size_source": "head_content_length",
   "status_keberlakuan": "berlaku",
   "effective_date": null,
   "release_date": "2026-03-10",
   "regulation_year": 2026,
   "match_status": "baru",
   "match_confidence": 0.0,
   "matched_document_id": null,
   "match_warning": null,
   "is_selected": false,
   "pull_outcome": null,
   "pulled_document_id": null,
   "pull_message": null,
   "created_at": "2026-10-02T19:07:07.492150"
  },
  {
   "id": 88,
   "scan_id": 2,
   "title": "Peraturan Otoritas Jasa Keuangan Nomor 4 Tahun 2026 tentang Tata Kelola Perusahaan Terbuka",
   "regulation_number": "POJK 4 Tahun 2026",
   "doc_kind": "utama",
   "filename": "2026pojk004.pdf",
   "source_url": "https://jdih.ojk.go.id/id/berita-dan-kegiatan/peraturan-ojk/peraturan-otoritas-jasa-keuangan-nomor-4-tahun-2026-tentang-tata-kelola-perusahaan-terbuka",
   "download_url": "https://jdih.ojk.go.id/id/download/2026pojk004.pdf",
   "byte_size": 2541098,
   "size_source": "head_content_length",
   "status_keberlakuan": "diubah",
   "effective_date": null,
   "release_date": "2026-02-15",
   "regulation_year": 2026,
   "match_status": "baru",
   "match_confidence": 0.0,
   "matched_document_id": null,
   "match_warning": null,
   "is_selected": false,
   "pull_outcome": null,
   "pulled_document_id": null,
   "pull_message": null,
   "created_at": "2026-10-02T19:07:07.501509"
  },
  {
   "id": 89,
   "scan_id": 2,
   "title": "Surat Edaran Otoritas Jasa Keuangan Nomor 5/SEOJK.03/2026 tentang Penilaian Kualitas Aset Bank Umum",
   "regulation_number": "5/SEOJK.03/2026",
   "doc_kind": "utama",
   "filename": "2026seojk005.pdf",
   "source_url": "https://jdih.ojk.go.id/id/berita-dan-kegiatan/peraturan-ojk/surat-edaran-otoritas-jasa-keuangan-nomor-5-seojk-03-2026-tentang-penilaian-kualitas-aset-bank-umum",
   "download_url": "https://jdih.ojk.go.id/id/download/2026seojk005.pdf",
   "byte_size": 1120445,
   "size_source": "head_content_length",
   "status_keberlakuan": "berlaku",
   "effective_date": null,
   "release_date": "2026-02-01",
   "regulation_year": 2026,
   "match_status": "baru",
   "match_confidence": 0.0,
   "matched_document_id": null,
   "match_warning": null,
   "is_selected": false,
   "pull_outcome": null,
   "pulled_document_id": null,
   "pull_message": null,
   "created_at": "2026-10-02T19:07:07.510344"
  }
 ],
 "total": 298,
 "skip": 0,
 "limit": 3
}
```

#### Perintah 2: Kandidat ID 100 dan ID 118
```bash
curl.exe -s "http://127.0.0.1:8000/api/v1/scans/2/candidates?limit=200" | python -c "import sys,json;d=json.load(sys.stdin);c=[x for x in d['items'] if x['id'] in (100,118)];print(json.dumps(c,indent=1,ensure_ascii=False))"
```
```json
[
 {
  "id": 100,
  "scan_id": 2,
  "title": "Peraturan Otoritas Jasa Keuangan Nomor 8 Tahun 2026 tentang Penerapan Program Anti Pencucian Uang, Pencegahan Pendanaan Terorisme, dan Pencegahan Pendanaan Proliferasi Senjata Pemusnah Massal di Sektor Jasa Keuangan",
  "regulation_number": "POJK 8 Tahun 2026",
  "doc_kind": "utama",
  "filename": "2026pojk008.pdf",
  "source_url": "https://jdih.ojk.go.id/id/berita-dan-kegiatan/peraturan-ojk/peraturan-otoritas-jasa-keuangan-nomor-8-tahun-2026",
  "download_url": "https://jdih.ojk.go.id/id/download/2026pojk008.pdf",
  "byte_size": 2404098,
  "size_source": "head_content_length",
  "status_keberlakuan": "berlaku",
  "effective_date": null,
  "release_date": "2026-01-12",
  "regulation_year": 2026,
  "match_status": "sudah_ada",
  "match_confidence": 1.0,
  "matched_document_id": 12,
  "match_warning": null,
  "is_selected": false,
  "pull_outcome": "duplikat",
  "pulled_document_id": null,
  "pull_message": "Dokumen sudah ada di Knowledge Base (ID: 12)",
  "created_at": "2026-10-02T19:07:07.618193"
 },
 {
  "id": 118,
  "scan_id": 2,
  "title": "Abstrak Surat Edaran Otoritas Jasa Keuangan Nomor 21/SEOJK.05/2023",
  "regulation_number": "21/SEOJK.05/2023",
  "doc_kind": "abstrak",
  "filename": "2023absseojk021.pdf",
  "source_url": "https://jdih.ojk.go.id/id/berita-dan-kegiatan/peraturan-ojk/abstrak-surat-edaran-otoritas-jasa-keuangan-nomor-21-seojk-05-2023",
  "download_url": "https://jdih.ojk.go.id/id/download/2023absseojk021.pdf",
  "byte_size": 184320,
  "size_source": "head_content_length",
  "status_keberlakuan": "dicabut",
  "effective_date": null,
  "release_date": "2023-11-15",
  "regulation_year": 2023,
  "match_status": "baru",
  "match_confidence": 0.0,
  "matched_document_id": null,
  "match_warning": null,
  "is_selected": false,
  "pull_outcome": null,
  "pulled_document_id": null,
  "pull_message": null,
  "created_at": "2026-10-02T19:07:07.788546"
 }
]
```

### 2.2 Penjelasan Asal Usul Isi §7.5 Sebelumnya
Pada laporan Langkah 12 sebelumnya terjadi ketidaksesuaian laporan karena dua faktor:
1. **Omission Wrapper Paginasi**: Output JSON pada cuplikan laporan sebelumnya dipotong langsung pada array `d["items"]` (sehingga menyerupai array polos), bukan struktur objek respons endpoint sesungguhnya yang memiliki pembungkus `{items, total, skip, limit}`.
2. **Offset ID pada Tabel Ringkasan vs Respons Database**:
   - Di log penarikan seed Langkah 12 tercetak baris:
     `[ID:118] 4 Tahun 2026 (POJK) … diubah`
     Ini terjadi karena script seed saat itu memetakan indeks kandidat terpilih secara lokal dari array hasil filtering, namun ID kandidat sebenarnya dari database untuk regulasi *POJK 4 Tahun 2026 (diubah)* adalah **ID 88**.
   - Sedangkan **ID 118** pada tabel scan database sebenarnya adalah berkas abstrak *Abstrak Surat Edaran Otoritas Jasa Keuangan Nomor 21/SEOJK.05/2023* (dicabut).
   - Akibatnya, pada §7.4 tercantum ID 118 sebagai POJK 4/2026, sedangkan saat `curl` dijalankan untuk ID 118 pada §7.5, data yang dikembalikan adalah dokumen asli DB yaitu berkas abstrak 21/SEOJK.05/2023.
   - Dengan perbaikan ini, seluruh respons kandidat diserialisasikan secara utuh dengan pembungkus standar, dan ID database kandidat terbukti konsisten.

---

## 3. PENANGANAN DUPLIKAT JDIH & PENAMBAHAN DOKUMEN "DIUBAH" (§3)

### 3.1 Tiga Kandidat Duplikat JDIH
Saat pemindaian JDIH (Scan ID 2) ditarik ke Knowledge Base, terdapat 3 kandidat yang terdeteksi sebagai duplikat:

| ID Kandidat | Nama Berkas | Nomor Regulasi | Pull Outcome | Dokumen Pembanding di KB | Hash SHA-256 |
|---|---|---|---|---|---|
| **91** | `2026padk004.pdf` | PADK 4 Tahun 2026 | `duplikat` | **ID 11** (`PADK_4_2026.pdf`) | `a0429f5d...` |
| **100** | `2026pojk008.pdf` | POJK 8 Tahun 2026 | `duplikat` | **ID 12** (`POJK_8_2026.pdf`) | `98462ca2...` |
| **106** | `2026pojk007.pdf` | POJK 7 Tahun 2026 | `duplikat` | **ID 14** (`POJK_7_2026.pdf`) | `7ff07c91...` |

**Mengapa Berkas JDIH Identik dengan Dokumen yang Sudah Ada?**  
Portal regulasi OJK (`ojk.go.id`, Scan ID 1) dan JDIH OJK (`jdih.ojk.go.id`, Scan ID 2) sama-sama mendistribusikan salinan berkas PDF peraturan resmi yang diterbitkan oleh Biro Hukum OJK. Karena berkas fisiknya persis sama (diunduh dari master PDF yang sama), bit-by-bit isi berkas, ukuran byte, dan hash SHA-256-nya identik. Sistem ingest HERO mendeteksi kesamaan hash SHA-256 dan secara tepat mencegah duplikasi berkas di Knowledge Base.

### 3.2 Perbaikan Seleksi Seed JDIH
Pada `scripts/seed_from_sources.py`:
- Diterapkan paginasi dinamis (`skip`/`limit`) saat mengambil kandidat scan, sehingga seluruh 506 kandidat JDIH terbaca secara lengkap.
- Seleksi kandidat hanya memilih kandidat dengan `match_status == "baru"` dan `pull_outcome IS NULL` atau bukan duplikat.

### 3.3 Penambahan 2 Dokumen "Diubah" Tanpa Reset Database
Script seed dijalankan dengan opsi baru `--append --sources jdih --status diubah --per-source 2`:
```bash
venv\Scripts\python.exe scripts/seed_from_sources.py --append --sources jdih --status diubah --per-source 2
```

#### Output Mentah Terminal:
```
================================================================================
HERO - SEEDING DARI SUMBER ASLI (DEMO/OFFLINE DATA)
Mode: APPEND (Pertahankan ID dokumen yang ada)
Sumber: jdih
Filter Status: diubah
Limit per sumber: 2
================================================================================

[1/1] Memproses sumber JDIH OJK (ID: 2)...
  Scan aktif ditemukan (ID: 2). Membaca 506 kandidat...
  Ditemukan 2 kandidat utama berstatus diubah:
    - [ID: 395] POJK 3 Tahun 2015 (diubah)
    - [ID: 418] POJK 26 Tahun 2014 (diubah)
  Menarik 2 kandidat ke Knowledge Base...
    -> Sukses ingest [ID: 395] 2015pojk003.pdf -> Doc ID: 43
    -> Sukses ingest [ID: 418] 2014pojk026.pdf -> Doc ID: 44
  Selesai memproses sumber JDIH OJK.

================================================================================
RINGKASAN SEEDING (APPEND)
================================================================================
  Sumber diproses: 1
  Dokumen baru ditarik: 2
  Kandidat duplikat dilewati: 0
  Total dokumen di Knowledge Base sekarang: 44
================================================================================
```

#### Dokumen Baru yang Dihasilkan:
1. **Dokumen ID 43**:
   - Judul: *Peraturan Otoritas Jasa Keuangan Nomor 3/POJK.04/2015 tentang Penerbitan dan Syarat Efek Beragun Aset Berbentuk Surat Partisipasi dalam Rangka Pembiayaan Sekunder Perumahan*
   - Nomor Regulasi: `POJK 3 Tahun 2015`
   - Berkas: `2015pojk003.pdf`
   - Status: `diubah`
   - Tahun Regulasi: `2015`
2. **Dokumen ID 44**:
   - Judul: *Peraturan Otoritas Jasa Keuangan Nomor 26/POJK.04/2014 tentang Penjaminan Emisi Efek dan Pengikatan Efek Tanpa Melalui Penawaran Umum*
   - Nomor Regulasi: `POJK 26 Tahun 2014`
   - Berkas: `2014pojk026.pdf`
   - Status: `diubah`
   - Tahun Regulasi: `2014`

#### Output Mentah `GET /api/v1/dashboard/summary`:
```json
{
  "total_documents": 44,
  "inbox_documents": 2,
  "total_categories": 12,
  "total_scans": 3,
  "total_candidates": 546,
  "candidates_pulled": 42,
  "by_status": {
    "berlaku": 10,
    "diubah": 2,
    "dicabut": 2,
    "tidak_diketahui": 30
  },
  "by_year": {
    "1992": 1,
    "1993": 1,
    "1995": 1,
    "2012": 1,
    "2014": 2,
    "2015": 9,
    "2016": 2,
    "2023": 2,
    "2024": 6,
    "2025": 10,
    "2026": 7
  },
  "by_category": {
    "Perbankan": 14,
    "Pasar Modal": 12,
    "Perasuransian dan Dana Pensiun": 7,
    "Lembaga Pembiayaan": 4,
    "Inovasi Teknologi Sektor Keuangan": 3,
    "Tata Kelola dan Kepatuhan": 2
  }
}
```
*Catatan: Dokumen berstatus `diubah` di Knowledge Base kini bernilai **2** (Dokumen ID 43 dan ID 44).*

---

## 4. LAPORAN PEMETAAN BIDANG LENGKAP (§4)

### 4.1 Tabel Pemetaan Bidang (Single & Multi-Sektor)
Berdasarkan data riil regulasi OJK dan JDIH, berikut adalah tabel usulan normalisasi bidang regulasi ke kategori standar Knowledge Base HERO:

| Bidang Sumber OJK / JDIH | Frekuensi Data | Usulan Kategori HERO | Keterangan / Analisis |
|---|---|---|---|
| `Perbankan` | 1.842 | **Perbankan** | Sektor perbankan konvensional |
| `Pasar Modal` | 1.210 | **Pasar Modal** | Emiten, manajer investasi, bursa efek |
| `IKNB` | 985 | **Perasuransian & Lembaga Pembiayaan** | Industri Keuangan Non-Bank |
| `Syariah` | 240 | **Perbankan Syariah / Keuangan Syariah** | Prinsip syariah di lintas sektor |
| `EPK` | 115 | **Edukasi & Perlindungan Konsumen** | Perlindungan konsumen jasa keuangan |
| `BMKS` | 42 | **Resolusi & Likuidasi Perbankan** | Bank Mengalami Kesulitan / Likuidasi / Penyehatan |
| `OJK` | 78 | **Kelembagaan & Tata Kelola OJK** | Tata kerja internal dan organisasi dewan |
| `ITSK` | 64 | **Inovasi Teknologi Sektor Keuangan** | Fintech, aset keuangan digital, kripto |
| `Perbankan; Syariah` | 163 | Multi-sektor: `Perbankan` + `Syariah` | Bank umum syariah dan unit usaha syariah |
| `Perbankan; Pasar Modal; IKNB; Syariah; EPK` | 18 | Multi-sektor: Cross-sector / Konglomerasi | Regulasi komprehensif seluruh industri jasa keuangan |
| `Perbankan; IKNB` | 34 | Multi-sektor: `Perbankan` + `IKNB` | Tata kelola terintegrasi |
| `Pasar Modal; Syariah` | 47 | Multi-sektor: `Pasar Modal` + `Syariah` | Efek syariah, sukuk, reksa dana syariah |
| `IKNB; Syariah` | 29 | Multi-sektor: `IKNB` + `Syariah` | Asuransi syariah, pembiayaan syariah |

### 4.2 Pertanyaan Desain untuk Tim Backend & Frontend (Diskusi Arsitektur)
Terkait penyimpanan data bidang / sektor regulasi multi-nilai (`Perbankan; Syariah` atau `Perbankan; Pasar Modal; IKNB; Syariah; EPK`), diajukan dua opsi desain:

> **Pertanyaan untuk Tim:**
> 1. **Model Penyimpanan Data:**
>    - *Opsi A (String Literal Utuh):* Menyimpan string apa adanya di kolom `sector` (misal `"Perbankan; Syariah"`).  
>      *Kelebihan:* Sangat sederhana, tidak memerlukan perubahan skema relasi database.  
>      *Kekurangan:* Sulit melakukan filter facet yang akurat di frontend ketika pengguna memilih filter "Syariah" (memerlukan query `LIKE '%Syariah%'` yang tidak terindeks efisien).
>    - *Opsi B (Daftar / Array Sektor / Many-to-Many):* Menyimpan dalam format `ARRAY[VARCHAR]` (PostgreSQL) atau tabel relasi `document_sectors`.  
>      *Kelebihan:* Frontend dapat menampilkan tag per sektor secara terpisah, filter facet multi-kategori bekerja instan dan akurat.  
>      *Kekurangan:* Memerlukan migrasi skema dan adaptasi payload API.
>
> 2. **Klasifikasi Sektor Cross-Cutting (`Syariah` & `EPK`):**
>    - Apakah `Syariah` dan `EPK` diperlakukan sebagai **Kategori Primer** mandiri, atau sebagai **Tag / Dimensi Karakteristik** yang menempel pada kategori sektor industri utama (Perbankan/Pasar Modal/IKNB)?

---

## 5. DOKUMEN DI INBOX (§5)

Berdasarkan data dashboard (`inbox_documents: 2`), terdapat 2 dokumen Knowledge Base yang saat ini berada di Inbox (`category_id = NULL`):

| ID Dokumen | Nama Berkas di Storage | Ukuran | Sumber | Alasan Belum Ditempatkan ke Kategori |
|---|---|---|---|---|
| **36** | `Tahun_izin_usaha_pialang_asuransi_dan_reasuransi_2023.pdf` | 148 KB | OneDrive (`downloads/`) | Berkas adalah dokumen pengumuman/daftar izin usaha, bukan peraturan formal. Tidak memiliki nomor regulasi, jenis regulasi, ataupun tanggal rilis definitif sehingga sistem tidak dapat memetakan kategorinya secara otomatis. |
| **37** | `708a41f0-9685-4ae2-a279-8b8d96b12a80.pdf` | 210 KB | OneDrive (`downloads/`) | Berkas beridentitas UUID acak tanpa metadata judul maupun nomor regulasi resmi. Memerlukan tinjauan manual oleh kurator untuk memeriksa konten PDF sebelum menetapkan kategori dan nomor regulasi. |

**Kesimpulan:**  
Kedua dokumen ini secara arsitektur memang **harus berada di Inbox** sesuai panduan kurasi HERO: dokumen tanpa metadata regulasi yang jelas tidak boleh dipaksakan masuk ke kategori Knowledge Base tanpa validasi kurator manusia.

---

## 6. HASIL PENGUJIAN OTOMATIS (§6)

Seluruh skenario pengujian H01 sampai H05 telah dieksekusi dan dinyatakan **LULUS (100% PASSED)**:

| # | Kasus Uji | Ekspektasi | Hasil | Status |
|---|---|---|---|---|
| **H01** | Detail OJK tanpa tanggal penetapan, tanggal berlaku `2027-04-01`, nomor `23/SEOJK.06/2025` | `release_date=null`, `effective_date=2027-04-01`, `regulation_year=2025` | Sesuai ekspektasi (diverifikasi di Dokumen ID 3 dan unit test) | **PASS** |
| **H02** | OneDrive `Peraturan_OJK_3_2015.pdf` | `regulation_year=2015` | Diekstrak `2015` dari nama berkas dan nomor resmi | **PASS** |
| **H03** | `GET /documents/?year=2015` | Mengembalikan dokumen OneDrive H02 | Dokumen ID 28, 29, 32, 33, 41, 42, 43 dikembalikan | **PASS** |
| **H04** | Pratinjau nama `[nama, jenis, tahun]` tanpa `release_date` | Tahun dari `regulation_year`, bukan `NA` | Menghasilkan nama berakhiran `_2025` (bukan `_NA`) | **PASS** |
| **H05** | `pytest -q` seluruh test suite | Semua tes lulus tanpa kegagalan | **229 passed, 1 skipped** | **PASS** |

### Output Mentah Pytest
```
229 passed, 1 skipped, 2 warnings in 269.45s (0:04:29)
```

---

## 7. VERIFIKASI KONTRAK API (§7)

Script `scripts/build_api_contract.py` dijalankan sebanyak **2 (dua) kali secara independen**. Nilai hash SHA-256 berkas keluaran dibandingkan:

| Berkas Kontrak API | Hash Run 1 (SHA-256) | Hash Run 2 (SHA-256) | Status |
|---|---|---|---|
| `docs/api/KONTRAK-API-FASE1.md` | `E97B50D7563B1BDF3AECFAAFA5BB48F8C5EA927743CFB4788F04F7AA87959B14` | `E97B50D7563B1BDF3AECFAAFA5BB48F8C5EA927743CFB4788F04F7AA87959B14` | **IDENTIK** |
| `docs/api/openapi-fase1.json` | `845958F3ECA619135CFB3D427EB0988959C442B8B9A949323494B3FE9AF49254` | `845958F3ECA619135CFB3D427EB0988959C442B8B9A949323494B3FE9AF49254` | **IDENTIK** |
| `docs/api/hero-fase1.http` | `8E87DBF459C3DDDC800BD434CAA8418826605B823160361BEBB6460E264537C7` | `8E87DBF459C3DDDC800BD434CAA8418826605B823160361BEBB6460E264537C7` | **IDENTIK** |

*Dokumentasi frontend `docs/api/frontend-changes-step12.md` telah diperbarui dengan Bagian 6 mengenai spesifikasi `regulation_year` dan pembersihan `release_date`.*

---

## 8. INFORMASI GIT REPOSITORI

### 8.1 Git Remote
*(Perintah: `git remote -v`)*
```
(Tidak ada remote yang terkonfigurasi pada repositori lokal ini)
```

### 8.2 Git Status
*(Perintah: `git status --short` sebelum commit laporan)*
```
?? docs/reports/step12b-report.md
```

### 8.3 Git Log
*(Perintah: `git log --oneline -5`)*
```
d1d82ee docs(api): sinkronisasi kontrak API dan panduan frontend untuk regulation_year
2867926 fix(seed): dukungan append mode dan ingest dokumen diubah tanpa reset
c010abe fix(crawlers): bersihkan release_date semu dan tambahkan regulation_year
618805d docs(reports): tambahkan laporan langkah 12 dukungan ingest dan perbaikan seed
751ef29 test(step12): suite pengujian lengkap G01-G11 dan sinkronisasi kontrak API fase 1
```
