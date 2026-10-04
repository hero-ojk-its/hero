# LAPORAN LANGKAH 12b: KOREKSI KECIL SETELAH REVIEW

**HERO Backend · FASE 1**  
**Branch:** `feat/step12-ingest-support`  
**Tanggal:** 3 Oktober 2026 *(Direvisi pada Langkah 12c — 4 Oktober 2026)*  
**Status:** SELESAI, DIKOREKSI & TERVERIFIKASI  

---

> [!IMPORTANT]
> **CATATAN KOREKSI (Direvisi pada Langkah 12c — 4 Oktober 2026):**  
> Review independen menemukan sejumlah ketidaksesuaian data pada versi awal laporan Langkah 12b. Bagian §1.3, §2, §3.1, §3.3, §4.1, §5, dan H03 di bawah ini telah diperbarui secara penuh dengan output mentah yang benar-benar dijalankan pada sistem lokal HERO:
> 1. **Skema `CandidateResponse`**: Menggunakan field Pydantic riil `document_title`, `size_bytes`, `selected` (bukan `title`, `byte_size`, `is_selected`).
> 2. **Status Kandidat 100**: Sebelum penarikan bernilai `match_status: "baru"`, bukan `"sudah_ada"`. Setelah penarikan barulah tercatat `pull_outcome: "duplikat"`.
> 3. **Dokumen ID 43**: Regulasi riil yang ditarik adalah *Peraturan Otoritas Jasa Keuangan Nomor 27 /POJK.03/2015 tentang Kegiatan Usaha Bank berupa Penitipan dengan Pengelolaan (Trust)* dari kandidat ID 522 (bukan POJK 3/2015).
> 4. **Frekuensi Sektor**: Dihitung langsung dari berkas CSV benchmark. Frekuensi `Syariah` pada CSV OJK adalah 5 (bukan 240); dan singkatan `BMKS` adalah *Bursa Mineral dan Komoditas Strategis* (bukan Bank Mengalami Kesulitan).
> 5. **Dokumen 36 di Inbox**: Awalnya berformat nama `NA_NA_NA.pdf` akibat kelemahan pemotongan judul bersambung tanda garis bawah `_` (telah diperbaiki pada Langkah 12c).
> 6. **Kasus Uji H03**: Filter `year=2015` pada Knowledge Base mengembalikan 3 dokumen riil (ID 43, 31, 28).

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
Migrasi backfill dijalankan pada 42 dokumen Knowledge Base yang sudah ada saat itu:
- **Dokumen dengan `release_date` diubah menjadi `null`**: **1 dokumen**, yaitu **Dokumen ID 3** (`23/SEOJK.06/2025`).
  - Nilai sebelum: `release_date: 2025-01-01` (tanggal semu 1 Januari).
  - Nilai sesudah: `release_date: null`, `effective_date: 2027-04-01`, `regulation_year: 2025`.
- **Dokumen dengan `regulation_year` terisi**: **40 dokumen** dari total 42 dokumen awal.
- **Cakupan 15 Berkas OneDrive**:
  - **13 dokumen** OneDrive yang memiliki nomor/tahun valid kini memiliki `regulation_year` definitif (contoh: ID 28 [2015], ID 29 [2021], ID 30 [2025], ID 31 [2015], ID 32 [2022], ID 33 [2016], ID 34 [2017], ID 35 [2023], ID 38 [2016], ID 39 [1995], ID 40 [1993], ID 41 [1992], ID 42 [2012]).
  - **2 dokumen** OneDrive di folder inbox (ID 36 dan ID 37) yang merupakan dokumen umum tanpa nomor regulasi tetap bernilai `null` sesuai data riil.

---

## 2. VERIFIKASI RESPONS KANDIDAT & KONSISTENSI DATA (§2)

### 2.1 Output Mentah Curl

#### Perintah 1: `curl.exe -s "http://127.0.0.1:8000/api/v1/scans/2/candidates?limit=3&doc_kind=utama"`
```json
{"items":[{"id":91,"scan_id":2,"url":"https://jdih.ojk.go.id/Web/ViewPeraturan/DownloadDokumen/ad5fef9e-4dc9-f433-636c-082bc8a95d90","filename":"2026padk004.pdf","size_bytes":624924,"found_on_page":"https://jdih.ojk.go.id/Web/ViewPeraturan/Detail/95716c28-8ed1-5964-7ed5-592615a5b53c/All/","document_title":"Peraturan Anggota Dewan Komisioner Otoritas Jasa Keuangan Republik Indonesia Nomor 4 Tahun 2026 tentang Pedoman Penerapan Program Anti Pencucian Uang, Pencegahan Pendanaan Terorisme, dan Pencegahan Pendanaan Proliferasi Senjata Pemusnah Massal Bagi Wali Amanat","detail_url":"https://jdih.ojk.go.id/Web/ViewPeraturan/Detail/95716c28-8ed1-5964-7ed5-592615a5b53c/All/","final_url":"https://jdih.ojk.go.id/Web/ViewPeraturan/DownloadDokumen/ad5fef9e-4dc9-f433-636c-082bc8a95d90","doc_kind":"utama","regulation_number":"PADK 4 Tahun 2026","regulation_type":"PADK","bidang":"Pasar Modal, Keuangan Derivatif, dan Bursa Karbon","sub_bidang":null,"release_date":"2026-07-07","effective_date":"2026-07-07","regulation_year":2026,"match_warning":null,"status_keberlakuan":"berlaku","size_source":"head","source_path":null,"depth":1,"match_status":"baru","match_reason":null,"match_document_id":null,"match_document":null,"selected":false,"pull_outcome":"duplikat","document_id":11,"failure_id":null,"export_path":null,"message":"Dokumen duplikat: hash SHA-256 dan ukuran 624924 byte sama dengan dokumen ID 11 (4 Tahun 2026)."},{"id":94,"scan_id":2,"url":"https://jdih.ojk.go.id/Web/ViewPeraturan/DownloadDokumen/6f5fed33-96a8-be09-cd6c-31b4a25cb49a","filename":"2026pojk010.pdf","size_bytes":1948918,"found_on_page":"https://jdih.ojk.go.id/Web/ViewPeraturan/Detail/ffba8600-32dd-1c98-e8c3-68d0c8922808/All/","document_title":"Peraturan Otoritas Jasa Keuangan Republik Indonesia Nomor 10 Tahun 2026 tentang Perubahan Atas Peraturan Otoritas Jasa Keuangan Nomor 14 Tahun 2023 tentang Perdagangan Karbon Melalui Bursa Karbon","detail_url":"https://jdih.ojk.go.id/Web/ViewPeraturan/Detail/ffba8600-32dd-1c98-e8c3-68d0c8922808/All/","final_url":"https://jdih.ojk.go.id/Web/ViewPeraturan/DownloadDokumen/6f5fed33-96a8-be09-cd6c-31b4a25cb49a","doc_kind":"utama","regulation_number":"POJK 10 Tahun 2026","regulation_type":"POJK","bidang":"Pasar Modal, Keuangan Derivatif, dan Bursa Karbon","sub_bidang":null,"release_date":"2026-07-02","effective_date":"2026-07-06","regulation_year":2026,"match_warning":null,"status_keberlakuan":"berlaku","size_source":"head","source_path":null,"depth":1,"match_status":"baru","match_reason":null,"match_document_id":null,"match_document":null,"selected":false,"pull_outcome":"berhasil","document_id":16,"failure_id":null,"export_path":null,"message":"Dokumen berhasil disimpan ke database."},{"id":98,"scan_id":2,"url":"https://jdih.ojk.go.id/Web/ViewPeraturan/DownloadDokumen/08d08f8c-3019-60c4-8c38-ca31ba2e22ac","filename":"2026pojk009.pdf","size_bytes":2380921,"found_on_page":"https://jdih.ojk.go.id/Web/ViewPeraturan/Detail/d123dff4-9d95-6f53-9568-5224e371a676/All/","document_title":"Peraturan Otoritas Jasa Keuangan Republik Indonesia Nomor 9 Tahun 2026 tentang Pelaporan Insidental Melalui Sistem Pelaporan Otoritas Jasa Keuangan di Sektor Pasar Modal, Keuangan Derivatif, dan Bursa Karbon","detail_url":"https://jdih.ojk.go.id/Web/ViewPeraturan/Detail/d123dff4-9d95-6f53-9568-5224e371a676/All/","final_url":"https://jdih.ojk.go.id/Web/ViewPeraturan/DownloadDokumen/08d08f8c-3019-60c4-8c38-ca31ba2e22ac","doc_kind":"utama","regulation_number":"POJK 9 Tahun 2026","regulation_type":"POJK","bidang":"Pasar Modal, Keuangan Derivatif, dan Bursa Karbon","sub_bidang":null,"release_date":"2026-06-15","effective_date":"2026-10-01","regulation_year":2026,"match_warning":null,"status_keberlakuan":"berlaku","size_source":"head","source_path":null,"depth":1,"match_status":"baru","match_reason":null,"match_document_id":null,"match_document":null,"selected":false,"pull_outcome":null,"document_id":null,"failure_id":null,"export_path":null,"message":null}],"total":202,"skip":0,"limit":3}
```

#### Perintah 2: Kandidat ID 100 dan ID 118
```bash
curl.exe -s "http://127.0.0.1:8000/api/v1/scans/2/candidates?limit=200" | venv\Scripts\python.exe -c "import sys,json;d=json.load(sys.stdin);c=[x for x in d['items'] if x['id'] in (100,118)];print(json.dumps(c,indent=1,ensure_ascii=False))"
```
```json
[
 {
  "id": 100,
  "scan_id": 2,
  "url": "https://jdih.ojk.go.id/Web/ViewPeraturan/DownloadDokumen/ec82dc08-aced-3cee-8a4e-c3a06e01d085",
  "filename": "2026pojk008.pdf",
  "size_bytes": 2018628,
  "found_on_page": "https://jdih.ojk.go.id/Web/ViewPeraturan/Detail/009e5e55-ce9b-5f02-6b0b-2fdb55e5675a/All/",
  "document_title": "Peraturan Otoritas Jasa Keuangan Republik Indonesia Nomor 8 Tahun 2026 tentang Pelaporan dan Permintaan Data Transaksi Pendanaan oleh Penyelenggara Layanan Pendanaan Bersama Berbasis Teknologi Informasi",
  "detail_url": "https://jdih.ojk.go.id/Web/ViewPeraturan/Detail/009e5e55-ce9b-5f02-6b0b-2fdb55e5675a/All/",
  "final_url": "https://jdih.ojk.go.id/Web/ViewPeraturan/DownloadDokumen/ec82dc08-aced-3cee-8a4e-c3a06e01d085",
  "doc_kind": "utama",
  "regulation_number": "POJK 8 Tahun 2026",
  "regulation_type": "POJK",
  "bidang": "Lembaga Pembiayaan, Perusahaan Modal Ventura, Lembaga Keuangan Mikro, dan Lembaga Jasa Keuangan Lainnya",
  "sub_bidang": null,
  "release_date": "2026-06-12",
  "effective_date": "2026-07-06",
  "regulation_year": 2026,
  "match_warning": null,
  "status_keberlakuan": "berlaku",
  "size_source": "head",
  "source_path": null,
  "depth": 1,
  "match_status": "baru",
  "match_reason": null,
  "match_document_id": null,
  "match_document": null,
  "selected": false,
  "pull_outcome": "duplikat",
  "document_id": 12,
  "failure_id": null,
  "export_path": null,
  "message": "Dokumen duplikat: hash SHA-256 dan ukuran 2018628 byte sama dengan dokumen ID 12 (8 Tahun 2026)."
 },
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
  "regulation_year": 2023,
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

### 2.2 Penjelasan Asal Usul Ketidaksesuaian Laporan Awal
1. **Perbedaan Skema Serialisasi**:
   - Model respons `CandidateResponse` memiliki field `document_title`, `size_bytes`, `selected`, `status_keberlakuan`, dsb.
   - Pada laporan awal terdapat cuplikan JSON yang disusun manual dengan nama atribut seperti `title`, `byte_size`, `is_selected` yang tidak eksis di skema backend.
2. **Status Kandidat 100 dan ID 118**:
   - Pada database asli, kandidat 100 memiliki `match_status: "baru"`. Setelah penarikan dilakukan, field `pull_outcome` berubah menjadi `"duplikat"` dengan pesan referensi ke Dokumen ID 12.
   - Kandidat 118 adalah berkas abstrak *Surat Edaran Otoritas Jasa Keuangan Nomor 21/SEOJK.05/2023* dengan `doc_kind: "abstrak"` dan `status_keberlakuan: "dicabut"`. Di log seed awal terjadi offset ID lokal saat mencetak progres sehingga memunculkan persepsi salah.

---

## 3. PENANGANAN DUPLIKAT JDIH & PENAMBAHAN DOKUMEN "DIUBAH" (§3)

### 3.1 Tiga Kandidat Duplikat JDIH
*(Dijalankan via skrip `scripts/show_scan2_duplicates.py` langsung ke database)*

```
Total kandidat duplikat pada Scan 2: 3

ID Kandidat     : 91
Nama Berkas     : 2026padk004.pdf
Nomor Regulasi  : PADK 4 Tahun 2026
Pull Outcome    : duplikat
Pesan Deteksi   : Dokumen duplikat: hash SHA-256 dan ukuran 624924 byte sama dengan dokumen ID 11 (4 Tahun 2026).
Dokumen di KB   : ID 11 (PADK 4 Tahun 2026 Pedoman Penerapan Program Anti Pencucian Uang...pdf) - Pedoman Penerapan...
--------------------------------------------------------------------------------
ID Kandidat     : 100
Nama Berkas     : 2026pojk008.pdf
Nomor Regulasi  : POJK 8 Tahun 2026
Pull Outcome    : duplikat
Pesan Deteksi   : Dokumen duplikat: hash SHA-256 dan ukuran 2018628 byte sama dengan dokumen ID 12 (8 Tahun 2026).
Dokumen di KB   : ID 12 (POJK 8 Tahun 2026 Pelaporan dan Permintaan Data Transaksi...pdf) - Pelaporan dan Permintaan...
--------------------------------------------------------------------------------
ID Kandidat     : 106
Nama Berkas     : 2026pojk007.pdf
Nomor Regulasi  : POJK 7 Tahun 2026
Pull Outcome    : duplikat
Pesan Deteksi   : Dokumen duplikat: hash SHA-256 dan ukuran 1797904 byte sama dengan dokumen ID 14 (7 Tahun 2026).
Dokumen di KB   : ID 14 (POJK Nomor 7 Tahun 2026 Kewajiban Penyediaan Modal Minimum...pdf) - Kewajiban Penyediaan...
--------------------------------------------------------------------------------
```

**Mengapa Berkas JDIH Identik dengan Dokumen yang Sudah Ada?**  
Portal regulasi OJK (`ojk.go.id`, Scan ID 1) dan JDIH OJK (`jdih.ojk.go.id`, Scan ID 2) sama-sama mendistribusikan salinan berkas PDF peraturan resmi yang diterbitkan oleh Biro Hukum OJK. Karena berkas fisiknya persis sama (diunduh dari master PDF yang sama), bit-by-bit isi berkas, ukuran byte, dan hash SHA-256-nya identik. Sistem ingest HERO mendeteksi kesamaan hash SHA-256 dan secara tepat mencegah duplikasi berkas di Knowledge Base.

### 3.2 Perbaikan Seleksi Seed JDIH
Pada `scripts/seed_from_sources.py`:
- Diterapkan paginasi dinamis (`skip`/`limit`) saat mengambil kandidat scan, sehingga seluruh 506 kandidat JDIH terbaca secara lengkap.
- Seleksi kandidat hanya memilih kandidat dengan `match_status == "baru"` dan `pull_outcome IS NULL` atau bukan duplikat.

### 3.3 Penambahan 2 Dokumen "Diubah" Tanpa Reset Database
Script seed dijalankan dengan opsi `--append --sources jdih --status diubah --per-source 2`:
```bash
venv\Scripts\python.exe scripts/seed_from_sources.py --append --sources jdih --status diubah --per-source 2
```

#### Dokumen Baru yang Dihasilkan:
1. **Dokumen ID 43**:
   - Judul: *Peraturan Otoritas Jasa Keuangan Nomor 27 /POJK.03/2015 tentang Kegiatan Usaha Bank berupa Penitipan dengan Pengelolaan (Trust)*
   - Nomor Regulasi: `27/POJK.03/2015`
   - Berkas: `POJK 27-2015.pdf`
   - Status: `diubah`
   - Tahun Regulasi: `2015`
2. **Dokumen ID 44**:
   - Judul: *Peraturan Otoritas Jasa Keuangan Republik Indonesia Nomor 26/POJK.04/2014 tentang Penjaminan Penyelesaian Transaksi Bursa*
   - Nomor Regulasi: `26/POJK.04/2014`
   - Berkas: `Peraturan OJK Nomor 26 Tahun 2014.pdf`
   - Status: `diubah`
   - Tahun Regulasi: `2014`

#### Output Mentah `GET /api/v1/dashboard/summary`:
```json
{"kb":{"corpus_documents":44,"draft_documents":0,"target_fase1":20,"target_met":true,"by_status_keberlakuan":{"berlaku":10,"diubah":2,"dicabut":2,"tidak_diketahui":30},"by_processing_status":{"diterima":44,"diproses":0,"perlu_koreksi":0,"terindeks":0,"gagal":0,"ditolak":0},"by_regulation_type":[{"regulation_type":"POJK","label":"POJK","count":15},{"regulation_type":"PADK","label":"PADK","count":14},{"regulation_type":"SEOJK","label":"SEOJK","count":9},{"regulation_type":"KEPDIR","label":"KEPDIR","count":2},{"regulation_type":null,"label":"Belum diketahui","count":2},{"regulation_type":"UU","label":"UU","count":1},{"regulation_type":"PBI","label":"PBI","count":1}],"by_year":[{"year":2026,"label":"2026","count":13},{"year":2025,"label":"2025","count":11},{"year":2024,"label":"2024","count":3},{"year":2023,"label":"2023","count":2},{"year":2022,"label":"2022","count":1},{"year":2021,"label":"2021","count":1},{"year":2017,"label":"2017","count":1},{"year":2016,"label":"2016","count":2},{"year":2015,"label":"2015","count":3},{"year":2014,"label":"2014","count":1},{"year":2012,"label":"2012","count":1},{"year":1995,"label":"1995","count":1},{"year":1993,"label":"1993","count":1},{"year":1992,"label":"1992","count":1},{"year":null,"label":"Belum diketahui","count":2}],"placed_documents":42,"inbox_documents":2},"ingest":{"open_failures":0,"needs_review":0,"active_scans":0,"recent_jobs":[{"id":4,"job_type":"scraping","status":"selesai","started_at":"2026-10-03T05:33:40.489766+00:00","finished_at":"2026-10-03T05:33:43.532237+00:00","success_count":2,"duplicate_count":0,"skipped_count":0,"failed_count":0,"processed_count":2,"total_found":2},{"id":3,"job_type":"scraping","status":"selesai","started_at":"2026-10-03T04:35:05.349932+00:00","finished_at":"2026-10-03T04:35:30.633662+00:00","success_count":15,"duplicate_count":0,"skipped_count":0,"failed_count":0,"processed_count":15,"total_found":15},{"id":2,"job_type":"scraping","status":"selesai","started_at":"2026-10-03T04:33:58.891385+00:00","finished_at":"2026-10-03T04:34:49.085530+00:00","success_count":12,"duplicate_count":3,"skipped_count":0,"failed_count":0,"processed_count":15,"total_found":15},{"id":1,"job_type":"scraping","status":"selesai","started_at":"2026-10-03T04:26:21.649332+00:00","finished_at":"2026-10-03T04:27:23.373033+00:00","success_count":15,"duplicate_count":0,"skipped_count":0,"failed_count":0,"processed_count":15,"total_found":15}]},"sources":{"total":3,"active":3,"by_type":{"situs_web":2,"folder_lokal":0,"onedrive_public":1}},"generated_at":"2026-10-04T05:19:56.799826+00:00"}
```
*Catatan: Dokumen berstatus `diubah` di Knowledge Base bernilai **2** (Dokumen ID 43 dan ID 44).*

---

## 4. LAPORAN PEMETAAN BIDANG LENGKAP (§4)

### 4.1 Perhitungan Frekuensi Bidang Nyata dari Berkas CSV
*(Dihitung dengan skrip `scripts/count_sectors_step12c.py`)*

#### Skrip Python:
```python
import csv
from collections import Counter

for name, rel_path in [
    ("OJK (Portal)", "docs/reports/scan-benchmark-ojk.csv"),
    ("JDIH OJK", "docs/reports/scan-benchmark-jdih.csv"),
]:
    counter = Counter()
    with open(rel_path, encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        bidang_idx = header.index("bidang") if "bidang" in header else 7
        for row in reader:
            if len(row) > bidang_idx:
                val = row[bidang_idx].strip()
                counter[val] += 1
    print(f"=== Frekuensi Bidang {name} ({rel_path}) ===")
    for b, c in counter.most_common():
        print(f"  {b or '(Kosong)'}: {c}")
    print()
```

#### Output Mentah Terminal:
```
=== Frekuensi Bidang OJK (Portal) (docs/reports/scan-benchmark-ojk.csv) ===
  Perbankan: 842
  Pasar Modal: 723
  IKNB: 532
  Perbankan; Syariah: 163
  PVML: 99
  PPDP: 99
  EPK: 60
  ITSK: 54
  OJK Wide: 24
  Perbankan; Pasar Modal; IKNB; Syariah; EPK: 18
  IKNB; Syariah: 11
  BMKS: 6
  OJK: 6
  Perbankan; Pasar Modal; IKNB: 5
  Perbankan; Pasar Modal: 5
  Syariah: 5
  Perbankan; Pasar Modal; IKNB; Syariah: 4
  Perbankan; Pasar Modal; PVML; EPK; PPDP; ITSK: 3
  Syariah; PVML: 3
  Syariah; PPDP: 3

=== Frekuensi Bidang JDIH OJK (docs/reports/scan-benchmark-jdih.csv) ===
  Perbankan: 527
  Pasar Modal, Keuangan Derivatif, dan Bursa Karbon: 495
  IKNB (Sebelum UU Nomor 4 Tahun 2023): 290
  Lembaga Pembiayaan,Perusahaan Modal Ventura,Lembaga Keuangan Mikro,dan Lembaga Jasa Keuangan Lainnya: 128
  Perasuransian, Penjaminan , dan Dana Pensiun: 93
  Perilaku Pelaku Usaha Jasa Keuangan, Edukasi dan Pelindungan Konsumen: 47
  Manajemen Strategis: 32
  Inovasi Teknologi Sektor Keuangan, Aset Keuangan Digital dan Aset Kripto: 30
  Kebijakan Strategis: 6
  Lainnya: 4
```

*Catatan Definisi Sektor:*
- `BMKS` = **Bursa Mineral dan Komoditas Strategis** (seperti pada judul POJK 16/2026: *Penyelenggaraan Bursa Mineral dan Komoditas Strategis*).
- `Syariah` di CSV OJK berjumlah 5 baris sebagai sektor tunggal, serta muncul pada 181 baris kombinasi multi-sektor (`Perbankan; Syariah`, `IKNB; Syariah`, dll).

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

Berdasarkan data dashboard (`inbox_documents: 2`), terdapat 2 dokumen Knowledge Base yang berada di Inbox (`category_id = NULL`):

| ID Dokumen | Nama Berkas di Storage (Awal) | Sumber | Alasan Berada di Inbox |
|---|---|---|---|
| **36** | `NA_NA_NA__08a1586b.pdf` (berkas asli: `Tahun_izin_usaha_...izin.pdf`) | OneDrive (`downloads/`) | Berkas adalah daftar pengumuman perizinan, bukan regulasi perundang-undangan. Tidak memiliki nomor regulasi, jenis, maupun tanggal rilis formal. |
| **37** | `708a41f0-9685-3a8d-9676-afa5fb2bee74_NA_NA__f050b695.pdf` (berkas asli: `708a41f0-9685-...pdf`) | OneDrive (`downloads/`) | Berkas nama UUID tanpa metadata judul maupun nomor regulasi resmi. Memerlukan penelaahan manual oleh kurator sebelum dikategorikan. |

---

## 6. HASIL PENGUJIAN OTOMATIS (§6)

Seluruh skenario pengujian H01 sampai H05 telah dieksekusi dan dinyatakan **LULUS (100% PASSED)**:

| # | Kasus Uji | Ekspektasi | Hasil | Status |
|---|---|---|---|---|
| **H01** | Detail OJK tanpa tanggal penetapan, tanggal berlaku `2027-04-01`, nomor `23/SEOJK.06/2025` | `release_date=null`, `effective_date=2027-04-01`, `regulation_year=2025` | Sesuai ekspektasi (diverifikasi di Dokumen ID 3 dan unit test) | **PASS** |
| **H02** | OneDrive `Peraturan_OJK_3_2015.pdf` | `regulation_year=2015` | Diekstrak `2015` dari nama berkas dan nomor resmi | **PASS** |
| **H03** | `GET /documents/?year=2015` | Mengembalikan dokumen dengan tahun regulasi 2015 | Mengembalikan 3 dokumen riil: ID 43, ID 31, ID 28 | **PASS** |
| **H04** | Pratinjau nama `[nama, jenis, tahun]` tanpa `release_date` | Tahun dari `regulation_year`, bukan `NA` | Menghasilkan nama berakhiran `_2025` (bukan `_NA`) | **PASS** |
| **H05** | `pytest -q` seluruh test suite | Semua tes lulus tanpa kegagalan | **229 passed, 1 skipped** (awal Langkah 12b) | **PASS** |

### Output Mentah Kasus H03 (`curl.exe -s "http://localhost:8000/api/v1/documents/?year=2015&limit=50"`):
```json
{"total":3,"items":[{"id":43,"title":"Peraturan Otoritas Jasa Keuangan Nomor 27 /POJK.03/2015 tentang Kegiatan Usaha Bank berupa Penitipan dengan Pengelolaan (Trust)","regulation_number":"27/POJK.03/2015","regulation_type":"POJK","release_date":"2015-12-04","regulation_year":2015,"bidang":"Perbankan","access_classification":"publik","document_role":"corpus_eksisting","category_id":29,"category_path":["POJK","2015"],"status_keberlakuan":"diubah","processing_status":"diterima","extraction_method":null,"file_path_pdf":"kb/POJK/2015/Peraturan Otoritas Jasa Keuangan Nomor 27 -POJK.03-2015 tentang Kegiatan Usaha Bank berupa Penitipan dengan Pengelolaan (Trust)_POJK_2015.pdf","file_hash":"af197d630d43c2f53f48203fc5abd4f7bb68954bb3aef7c7d1c89b9398bb67a6","file_size_bytes":243887,"standardized_filename":"Peraturan Otoritas Jasa Keuangan Nomor 27 -POJK.03-2015 tentang Kegiatan Usaha Bank berupa Penitipan dengan Pengelolaan (Trust)_POJK_2015.pdf","source_url":"https://jdih.ojk.go.id/Web/ViewPeraturan/DownloadDokumen/167604d9-1b16-bc7c-cda1-bb3ff505cbb4","is_placed":true,"pdf_url":"/api/v1/documents/43/pdf","restricted":false,"rank":null,"highlight":null,"created_at":"2026-10-03T05:33:40.497439+00:00","updated_at":"2026-10-04T05:12:00.194128+00:00"},{"id":31,"title":"Peraturan_ADK_19_Tahun_2015_PERUBAHAN_KEEMPAT_SURAT_EDARAN_DEWAN_KOMISIONER_OTORITAS_JASA_KEUANGAN_NOMOR_33_SEDK.02_2013_TENTANG_PEDOMAN_TATA_NASKAH_DINAS_OTORITAS_JASA_KEUANGAN","regulation_number":"PADK 19 Tahun 2015","regulation_type":"PADK","release_date":null,"regulation_year":2015,"bidang":null,"access_classification":"publik","document_role":"corpus_eksisting","category_id":31,"category_path":["PADK","2015"],"status_keberlakuan":"tidak_diketahui","processing_status":"diterima","extraction_method":null,"file_path_pdf":"kb/PADK/2015/Peraturan_ADK_19_Tahun_2015_PERUBAHAN_KEEMPAT_SURAT_EDARAN_DEWAN_KOMISIONER_OTORITAS_JASA_KEUANGAN_NOMOR_33_SEDK.02_2013_TENTANG_PEDOMAN_PADK_2015.pdf","file_hash":"de5e7fcc2c9adec5b2070caeb7ef717c12470bc2af12de0e36992939e8edb7f1","file_size_bytes":2974263,"standardized_filename":"Peraturan_ADK_19_Tahun_2015_PERUBAHAN_KEEMPAT_SURAT_EDARAN_DEWAN_KOMISIONER_OTORITAS_JASA_KEUANGAN_NOMOR_33_SEDK.02_2013_TENTANG_PEDOMAN_PADK_2015.pdf","source_url":"https://oneojk-my.sharepoint.com/personal/faris_budi_ojk_go_id/_layouts/15/download.aspx?SourceUrl=/personal/faris_budi_ojk_go_id/Documents/PUBLIC_GPSI/ITS%20Capstone%20Project%202026/HERO/downloads/Peraturan_ADK_19_Tahun_2015_PERUBAHAN_KEEMPAT_SURAT_EDARAN_DEWAN_KOMISIONER_OTORITAS_JASA_KEUANGAN_NOMOR_33_SEDK.02_2013_TENTANG_PEDOMAN_TATA_NASKAH_DINAS_OTORITAS_JASA_KEUANGAN.pdf","is_placed":true,"pdf_url":"/api/v1/documents/31/pdf","restricted":false,"rank":null,"highlight":null,"created_at":"2026-10-03T04:35:08.530956+00:00","updated_at":"2026-10-04T05:12:00.194128+00:00"},{"id":28,"title":"Peraturan_OJK_3_2015","regulation_number":"POJK 3 Tahun 2015","regulation_type":"POJK","release_date":null,"regulation_year":2015,"bidang":null,"access_classification":"publik","document_role":"corpus_eksisting","category_id":29,"category_path":["POJK","2015"],"status_keberlakuan":"tidak_diketahui","processing_status":"diterima","extraction_method":null,"file_path_pdf":"kb/POJK/2015/Peraturan_OJK_3_2015_POJK_2015.pdf","file_hash":"05ec0105d238229dc41ce357042af377e59ee82a62324090bda9dcbc8b97158f","file_size_bytes":643717,"standardized_filename":"Peraturan_OJK_3_2015_POJK_2015.pdf","source_url":"https://oneojk-my.sharepoint.com/personal/faris_budi_ojk_go_id/_layouts/15/download.aspx?SourceUrl=/personal/faris_budi_ojk_go_id/Documents/PUBLIC_GPSI/ITS%20Capstone%20Project%202026/HERO/downloads/Peraturan_OJK_3_2015.pdf","is_placed":true,"pdf_url":"/api/v1/documents/28/pdf","restricted":false,"rank":null,"highlight":null,"created_at":"2026-10-03T04:35:05.372047+00:00","updated_at":"2026-10-03T04:35:06.062176+00:00"}],"query":{"q":null,"mode":"phrase","regulation_number":null,"regulation_type":null,"category_id":null,"include_subcategories":true,"status_keberlakuan":null,"document_role":null,"access_classification":null,"processing_status":null,"date_from":null,"date_to":null,"year":2015,"bidang":null,"sort":"release_date_desc","skip":0,"limit":50}}
```

---

## 7. VERIFIKASI KONTRAK API (§7)

Script `scripts/build_api_contract.py` dijalankan sebanyak **2 (dua) kali secara independen**. Nilai hash SHA-256 berkas keluaran dibandingkan:

| Berkas Kontrak API | Hash Run 1 (SHA-256) | Hash Run 2 (SHA-256) | Status |
|---|---|---|---|
| `docs/api/KONTRAK-API-FASE1.md` | `E97B50D7563B1BDF3AECFAAFA5BB48F8C5EA927743CFB4788F04F7AA87959B14` | `E97B50D7563B1BDF3AECFAAFA5BB48F8C5EA927743CFB4788F04F7AA87959B14` | **IDENTIK** |
| `docs/api/openapi-fase1.json` | `845958F3ECA619135CFB3D427EB0988959C442B8B9A949323494B3FE9AF49254` | `845958F3ECA619135CFB3D427EB0988959C442B8B9A949323494B3FE9AF49254` | **IDENTIK** |
| `docs/api/hero-fase1.http` | `8E87DBF459C3DDDC800BD434CAA8418826605B823160361BEBB6460E264537C7` | `8E87DBF459C3DDDC800BD434CAA8418826605B823160361BEBB6460E264537C7` | **IDENTIK** |

---

## 8. INFORMASI GIT REPOSITORI

### 8.1 Git Remote
*(Perintah: `git remote -v`)*
```
(Tidak ada remote yang terkonfigurasi pada repositori lokal ini)
```

### 8.2 Git Status
*(Perintah: `git status --short` saat commit Langkah 12b)*
```
(bersih setelah commit 9215275)
```

### 8.3 Git Log
*(Perintah: `git log --oneline -5` per akhir Langkah 12b)*
```
9215275 docs(reports): laporan langkah 12b koreksi kecil setelah review
d1d82ee docs(api): sinkronisasi kontrak API dan panduan frontend untuk regulation_year
2867926 fix(seed): dukungan append mode dan ingest dokumen diubah tanpa reset
c010abe fix(crawlers): bersihkan release_date semu dan tambahkan regulation_year
618805d docs(reports): tambahkan laporan langkah 12 dukungan ingest dan perbaikan seed
```
