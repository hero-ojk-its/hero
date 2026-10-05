# LAPORAN LANGKAH 12c: PERBAIKAN NOMOR & NAMA BERKAS + KOREKSI LAPORAN 12b

**HERO Backend · FASE 1**  
**Branch:** `feat/step12-ingest-support`  
**Tanggal:** 4 Oktober 2026  
**Status:** SELESAI & TERVERIFIKASI  

---

## 1. RINGKASAN EKSEKUTIF

Langkah 12c menindaklanjuti review independen atas hasil integrasi dan Laporan Langkah 12b. Semua perbaikan telah diuji dan diverifikasi secara langsung pada basis data operasional lokal tanpa melakukan reset (ID dokumen 1–44 tetap utuh):
1. **Nomor Regulasi Terpotong**: Diperbaiki pada parser `extract_jdih_regulation_number` sehingga mengenali nomor regulasi dengan format garis miring berspasi (misal `27 /POJK.03/2015` menjadi `27/POJK.03/2015`). Dokumen ID 43 telah diperbarui dari sebelumnya `03/2015` menjadi `27/POJK.03/2015`.
2. **Garis Miring Nama Berkas**: Fungsi `_clean_field` dan `build_standard_filename` pada `app/services/naming_service.py` kini mengganti `/` dan `\` dengan `-` (bukan menghapusnya), sehingga nomor regulasi `26/POJK.04/2014` menjadi `26-POJK.04-2014` (bukan `26POJK.042014`).
3. **Pencegahan Nama `NA_NA_NA.pdf`**: Memperbaiki logika pemotongan judul panjang pada `build_standard_filename` yang menggunakan pemisah underscore `_` (Dokumen 36 dan Dokumen 31), sehingga judul tidak terbuang menjadi `NA`.
4. **Skrip Perbaikan Berkas Fisik & Audit Log**: Berkas fisik dipindahkan ke path baru yang konsisten, metadata dokumen diperbarui di database, dan entri `UPDATE_METADATA` dicatat di `audit_logs`.
5. **Koreksi Laporan 12b**: Seluruh bagian §1.3, §2, §3.1, §3.3, §4.1, §5, dan H03 di `docs/reports/step12b-report.md` telah diganti dengan data mentah asli yang diverifikasi langsung di sistem lokal.

---

## 2. PERBAIKAN NOMOR REGULASI TERPOTONG (TEMUAN 1)

### 2.1 Nilai Mentah dari JDIH untuk POJK 27/2015

#### 1. Baris Mentah Kolom DataTables (`ListDataPeraturan` offset 100):
```python
[
    "<a href='http://jdih.ojk.go.id/Web/ViewPeraturan/Detail/97931ea1-23a4-bfba-e775-accf8527b9c6/All/'>Peraturan Otoritas Jasa Keuangan Nomor 27 /POJK.03/2015 tentang Kegiatan Usaha Bank berupa Penitipan dengan Pengelolaan (Trust)</a>",
    "27",
    "Perbankan",
    None,
    None,
    "Peraturan OJK",
    "",
    "Berlaku (Perubahan) (Diubah)"
]
```
*Catatan: Kolom 0 memuat judul dengan spasi sebelum garis miring (`Nomor 27 /POJK.03/2015`), dan Kolom 1 memuat angka `27`.*

#### 2. Potongan HTML Mentah Halaman Detail (`/Detail/97931ea1-23a4-bfba-e775-accf8527b9c6/All/`):
```html
<th><h4>Judul</h4></th>
<td><label style="font-size:16px">:</label></td>
<td><label style="font-size:16px">Peraturan Otoritas Jasa Keuangan Nomor 27 /POJK.03/2015 tentang Kegiatan Usaha Bank berupa Penitipan dengan Pengelolaan (Trust)</label></td>

<th><h4>Nomor Peraturan</h4></th>
<td><label style="font-size:16px">:</label></td>
<td><label style="font-size:16px">27</label></td>

<th><h4>Singkatan Jenis/Bentuk Peraturan</h4></th>
<td><label style="font-size:16px">:</label></td>
<td><label style="font-size:16px">POJK</label></td>
```

### 2.2 Penyebab Nomor Terpotong Menjadi `03/2015`
Regex lama pada `app/crawlers/jdih_api.py` baris 358 menggunakan:
```python
slash_num_m = re.search(r'\b(\d+/[A-Z0-9\.]+(?:/\d{4})?)\b', doc_title)
```
Pada string judul `"Peraturan Otoritas Jasa Keuangan Nomor 27 /POJK.03/2015..."`:
- Karena terdapat spasi antara `27` dan `/`, regex tidak menangkap `27 /POJK.03/2015`.
- Regex kemudian melompat ke segmen berikutnya dan menemukan `03/2015`.
- Karena `03` berupa digit dan `2015` berupa karakter alfanumerik, regex mencocokkan `03/2015` sebagai nomor regulasi.

### 2.3 Perbaikan Parser (`extract_jdih_regulation_number`)
Di `app/crawlers/jdih_api.py`, diterapkan parser baru:
```python
def extract_jdih_regulation_number(
    doc_title: str,
    raw_reg_num: Optional[str] = None,
    reg_type: Optional[str] = None,
    year: Optional[int] = None,
) -> Optional[str]:
    if not doc_title:
        return None

    # 1. Pola nomor slash 3 segmen dengan jenis (toleran spasi sekitar slash)
    slash3_m = re.search(
        r'(?:Nomor|No\.?|\b)\s*(\d+)\s*/\s*([A-Za-z0-9\._-]+[A-Za-z][A-Za-z0-9\._-]*)\s*/\s*((?:19|20)\d{2})\b',
        doc_title,
        re.IGNORECASE,
    )
    if slash3_m:
        return f"{slash3_m.group(1)}/{slash3_m.group(2).upper()}/{slash3_m.group(3)}"

    # 2. Pola nomor slash 2 segmen dengan jenis
    slash2_m = re.search(
        r'(?:Nomor|No\.?|\b)\s*(\d+)\s*/\s*([A-Za-z0-9\._-]*[A-Za-z][A-Za-z0-9\._-]*)\b',
        doc_title,
        re.IGNORECASE,
    )
    if slash2_m:
        cand_num = f"{slash2_m.group(1)}/{slash2_m.group(2).upper()}"
        if not re.match(r'^\d+/\d+$', cand_num):
            return cand_num

    # 3. Format regulasi sintetis dari reg_num kolom DataTables (jika bukan potongan angka murni)
    if raw_reg_num and str(raw_reg_num).strip() not in ("None", "", "-"):
        clean_num = str(raw_reg_num).strip()
        if not re.match(r'^\d+/\d{4}$', clean_num):
            type_label = reg_type or "Nomor"
            if year:
                return f"{type_label} {clean_num} Tahun {year}"
            return f"{type_label} Nomor {clean_num}"

    return None
```

### 2.4 Hasil Pemindaian Pola Nomor Terpotong (`^\d+/\d{4}$`)
Hasil pemindaian menggunakan skrip verifikasi otomatis:
- **Tabel `documents` (Basis Data HERO)**: Ditemukan **1 dokumen**, yaitu **Dokumen ID 43** (`03/2015`).
- **Tabel `scan_candidates` (Basis Data HERO)**: Ditemukan **4 kandidat**:
  - ID 522, 523, 524: `03/2015` (POJK 27/2015 tentang Trust)
  - ID 514: `03/2017` (SEOJK 56/SEOJK.03/2017)
- **Berkas CSV `docs/reports/scan-benchmark-jdih.csv`**: Ditemukan **37 baris** nomor terpotong serupa (contoh: baris 425 `03/2017`, baris 433–435 `03/2015`, baris 762 `03/2016`, baris 1109 `04/2018`, baris 1245 `05/2020`, baris 1366 `03/2021`, dll). Seluruh 37 kasus tersebut disebabkan oleh adanya spasi sebelum tanda garis miring pada judul regulasi asli JDIH.

---

## 3. GARIS MIRING PADA NAMA BERKAS & PENANGANAN JUDUL PANJANG (TEMUAN 2 & 3)

### 3.1 Garis Miring Menjadi Minus (`/` dan `\` $\rightarrow$ `-`)
Pada `app/services/naming_service.py`, fungsi `_clean_field(val)` diperbarui agar mengganti `/` dan `\` menjadi tanda minus `-`:
```python
def _clean_field(val: str) -> str:
    r"""Ganti / dan \ dengan -, hapus karakter terlarang : * ? \" < > |, dan rapikan whitespace."""
    if not val:
        return ""
    replaced = val.replace("/", "-").replace("\\", "-")
    cleaned = re.sub(r'[:*?"<>|]', "", replaced)
    return re.sub(r"\s+", " ", cleaned).strip()
```
Dampaknya:
- Nomor regulasi `26/POJK.04/2014` disanitasi menjadi `26-POJK.04-2014`.
- Judul regulasi yang memuat nomor slash disanitasi menjadi `...Nomor 26-POJK.04-2014...`, tidak lagi menjadi `26POJK.042014`.

### 3.2 Penanganan Judul Panjang Bertanda Underscore (Dokumen 36 & Dokumen 31)
- **Akar Masalah**: Judul Dokumen 36 dan Dokumen 31 berasal dari nama berkas OneDrive yang menggunakan pemisah garis bawah `_` (snake_case) tanpa spasi. Ketika panjang berkas melebihi 150 karakter, fungsi pemotongan `words = nama_str.split()` menganggap string sepanjang 211 karakter sebagai 1 kata tunggal. Saat kata tersebut di-pop, string nama menjadi kosong `""`, dan fallback menggantinya dengan wildcard `"NA"`, menghasilkan nama berkas cacat `NA_NA_NA.pdf` atau `NA_PADK_2015.pdf`.
- **Solusi**: Diterapkan pemotongan bertingkat:
  1. Pemotongan per batas spasi (`split(" ")`).
  2. Jika tidak ada spasi, pemotongan per batas underscore (`split("_")`).
  3. Jika masih melebihi kuota, pemotongan langsung pada sisa panjang karakter yang diizinkan (`nama_str[:avail].rstrip(" _-")`).
  4. Fallback ke stem nama berkas asli (`original_filename`) bila judul kosong atau hanya berupa `"NA"`.

---

## 4. PEMINDAHAN BERKAS FISIK & AUDIT LOG (TEMUAN 4)

Skrip `scripts/fix_document_filenames_step12c.py` dijalankan untuk memperbarui data fisik dan database tanpa mengubah ID dokumen.

### 4.1 Output Mentah Mode Simulasi (`--dry-run`):
```
================================================================================
HERO BACKEND - PERBAIKAN NOMOR REGULASI & NAMA BERKAS (LANGKAH 12c)
Mode         : DRY-RUN (Simulasi saja)
Storage Path : storage
================================================================================

[PERUBAHAN] Dokumen ID 36 (Tahun_izin_usaha_dan_pencabutan_izin_usaha_Manajer_Investasi...):
  Standard Filename: NA_NA_NA.pdf
                  -> Tahun_izin_usaha_dan_pencabutan_izin_usaha_Manajer_Investasi_dan_Penasihat_Investasi_20_Perbaikan_Keputusan_OJK_tentang_izin_usaha_dan_NA_NA.pdf
  Path Relatif   : pdf/_inbox/NA_NA_NA__08a1586b.pdf
                -> pdf/_inbox/Tahun_izin_usaha_dan_pencabutan_izin_usaha_Manajer_Investasi_dan_Penasihat_Investasi_20_Perbaikan_Keputusan_OJK_tentang_izin_usaha_dan_NA_NA__08a1586b.pdf
  Berkas fisik ada: True (storage\pdf\_inbox\NA_NA_NA__08a1586b.pdf)

[PERUBAHAN] Dokumen ID 43 (Peraturan Otoritas Jasa Keuangan Nomor 27 /POJK.03/2015 tent...):
  Nomor Regulasi : 03/2015 -> 27/POJK.03/2015
  Standard Filename: Peraturan Otoritas Jasa Keuangan Nomor 27 POJK.032015 tentang Kegiatan Usaha Bank berupa Penitipan dengan Pengelolaan (Trust)_POJK_2015.pdf
                  -> Peraturan Otoritas Jasa Keuangan Nomor 27 -POJK.03-2015 tentang Kegiatan Usaha Bank berupa Penitipan dengan Pengelolaan (Trust)_POJK_2015.pdf
  Path Relatif   : kb/POJK/2015/Peraturan Otoritas Jasa Keuangan Nomor 27 POJK.032015 tentang Kegiatan Usaha Bank berupa Penitipan dengan Pengelolaan (Trust)_POJK_2015.pdf
                -> kb/POJK/2015/Peraturan Otoritas Jasa Keuangan Nomor 27 -POJK.03-2015 tentang Kegiatan Usaha Bank berupa Penitipan dengan Pengelolaan (Trust)_POJK_2015.pdf
  Berkas fisik ada: True (storage\kb\POJK\2015\Peraturan Otoritas Jasa Keuangan Nomor 27 POJK.032015 tentang Kegiatan Usaha Bank berupa Penitipan dengan Pengelolaan (Trust)_POJK_2015.pdf)

[PERUBAHAN] Dokumen ID 44 (Peraturan Otoritas Jasa Keuangan Republik Indonesia Nomor 26...):
  Standard Filename: Peraturan Otoritas Jasa Keuangan Republik Indonesia Nomor 26POJK.042014 tentang Penjaminan Penyelesaian Transaksi Bursa_POJK_2014.pdf
                  -> Peraturan Otoritas Jasa Keuangan Republik Indonesia Nomor 26-POJK.04-2014 tentang Penjaminan Penyelesaian Transaksi Bursa_POJK_2014.pdf
  Path Relatif   : kb/POJK/2014/Peraturan Otoritas Jasa Keuangan Republik Indonesia Nomor 26POJK.042014 tentang Penjaminan Penyelesaian Transaksi Bursa_POJK_2014.pdf
                -> kb/POJK/2014/Peraturan Otoritas Jasa Keuangan Republik Indonesia Nomor 26-POJK.04-2014 tentang Penjaminan Penyelesaian Transaksi Bursa_POJK_2014.pdf
  Berkas fisik ada: True (storage\kb\POJK\2014\Peraturan Otoritas Jasa Keuangan Republik Indonesia Nomor 26POJK.042014 tentang Penjaminan Penyelesaian Transaksi Bursa_POJK_2014.pdf)

[PERUBAHAN] Dokumen ID 31 (Peraturan_ADK_19_Tahun_2015_PERUBAHAN_KEEMPAT_SURAT_EDARAN_D...):
  Standard Filename: NA_PADK_2015.pdf
                  -> Peraturan_ADK_19_Tahun_2015_PERUBAHAN_KEEMPAT_SURAT_EDARAN_DEWAN_KOMISIONER_OTORITAS_JASA_KEUANGAN_NOMOR_33_SEDK.02_2013_TENTANG_PEDOMAN_PADK_2015.pdf
  Path Relatif   : kb/PADK/2015/NA_PADK_2015.pdf
                -> kb/PADK/2015/Peraturan_ADK_19_Tahun_2015_PERUBAHAN_KEEMPAT_SURAT_EDARAN_DEWAN_KOMISIONER_OTORITAS_JASA_KEUANGAN_NOMOR_33_SEDK.02_2013_TENTANG_PEDOMAN_PADK_2015.pdf
  Berkas fisik ada: True (storage\kb\PADK\2015\NA_PADK_2015.pdf)

--- Pemeriksaan Kandidat Scan Database ---
  Kandidat ID 522: 03/2015 -> 27/POJK.03/2015
  Kandidat ID 523: 03/2015 -> 27/POJK.03/2015
  Kandidat ID 524: 03/2015 -> 27/POJK.03/2015
  Kandidat ID 514: 03/2017 -> 56/SEOJK.03/2017

[SIMULASI SELESAI] Tidak ada berkas maupun database yang diubah.
```

### 4.2 Output Mentah Mode Eksekusi Nyata (`--apply`):
```
================================================================================
HERO BACKEND - PERBAIKAN NOMOR REGULASI & NAMA BERKAS (LANGKAH 12c)
Mode         : APPLY (Eksekusi nyata)
Storage Path : storage
================================================================================

[PERUBAHAN] Dokumen ID 36 (Tahun_izin_usaha_dan_pencabutan_izin_usaha_Manajer_Investasi...):
  Standard Filename: NA_NA_NA.pdf
                  -> Tahun_izin_usaha_dan_pencabutan_izin_usaha_Manajer_Investasi_dan_Penasihat_Investasi_20_Perbaikan_Keputusan_OJK_tentang_izin_usaha_dan_NA_NA.pdf
  Path Relatif   : pdf/_inbox/NA_NA_NA__08a1586b.pdf
                -> pdf/_inbox/Tahun_izin_usaha_dan_pencabutan_izin_usaha_Manajer_Investasi_dan_Penasihat_Investasi_20_Perbaikan_Keputusan_OJK_tentang_izin_usaha_dan_NA_NA__08a1586b.pdf
  Berkas fisik ada: True (storage\pdf\_inbox\NA_NA_NA__08a1586b.pdf)
  -> Berkas fisik berhasil dipindahkan ke: storage\pdf\_inbox\Tahun_izin_usaha_dan_pencabutan_izin_usaha_Manajer_Investasi_dan_Penasihat_Investasi_20_Perbaikan_Keputusan_OJK_tentang_izin_usaha_dan_NA_NA__08a1586b.pdf

[PERUBAHAN] Dokumen ID 43 (Peraturan Otoritas Jasa Keuangan Nomor 27 /POJK.03/2015 tent...):
  Nomor Regulasi : 03/2015 -> 27/POJK.03/2015
  Standard Filename: Peraturan Otoritas Jasa Keuangan Nomor 27 POJK.032015 tentang Kegiatan Usaha Bank berupa Penitipan dengan Pengelolaan (Trust)_POJK_2015.pdf
                  -> Peraturan Otoritas Jasa Keuangan Nomor 27 -POJK.03-2015 tentang Kegiatan Usaha Bank berupa Penitipan dengan Pengelolaan (Trust)_POJK_2015.pdf
  Path Relatif   : kb/POJK/2015/Peraturan Otoritas Jasa Keuangan Nomor 27 POJK.032015 tentang Kegiatan Usaha Bank berupa Penitipan dengan Pengelolaan (Trust)_POJK_2015.pdf
                -> kb/POJK/2015/Peraturan Otoritas Jasa Keuangan Nomor 27 -POJK.03-2015 tentang Kegiatan Usaha Bank berupa Penitipan dengan Pengelolaan (Trust)_POJK_2015.pdf
  Berkas fisik ada: True (storage\kb\POJK\2015\Peraturan Otoritas Jasa Keuangan Nomor 27 POJK.032015 tentang Kegiatan Usaha Bank berupa Penitipan dengan Pengelolaan (Trust)_POJK_2015.pdf)
  -> Berkas fisik berhasil dipindahkan ke: storage\kb\POJK\2015\Peraturan Otoritas Jasa Keuangan Nomor 27 -POJK.03-2015 tentang Kegiatan Usaha Bank berupa Penitipan dengan Pengelolaan (Trust)_POJK_2015.pdf

[PERUBAHAN] Dokumen ID 44 (Peraturan Otoritas Jasa Keuangan Republik Indonesia Nomor 26...):
  Standard Filename: Peraturan Otoritas Jasa Keuangan Republik Indonesia Nomor 26POJK.042014 tentang Penjaminan Penyelesaian Transaksi Bursa_POJK_2014.pdf
                  -> Peraturan Otoritas Jasa Keuangan Republik Indonesia Nomor 26-POJK.04-2014 tentang Penjaminan Penyelesaian Transaksi Bursa_POJK_2014.pdf
  Path Relatif   : kb/POJK/2014/Peraturan Otoritas Jasa Keuangan Republik Indonesia Nomor 26POJK.042014 tentang Penjaminan Penyelesaian Transaksi Bursa_POJK_2014.pdf
                -> kb/POJK/2014/Peraturan Otoritas Jasa Keuangan Republik Indonesia Nomor 26-POJK.04-2014 tentang Penjaminan Penyelesaian Transaksi Bursa_POJK_2014.pdf
  Berkas fisik ada: True (storage\kb\POJK\2014\Peraturan Otoritas Jasa Keuangan Republik Indonesia Nomor 26POJK.042014 tentang Penjaminan Penyelesaian Transaksi Bursa_POJK_2014.pdf)
  -> Berkas fisik berhasil dipindahkan ke: storage\kb\POJK\2014\Peraturan Otoritas Jasa Keuangan Republik Indonesia Nomor 26-POJK.04-2014 tentang Penjaminan Penyelesaian Transaksi Bursa_POJK_2014.pdf

[PERUBAHAN] Dokumen ID 31 (Peraturan_ADK_19_Tahun_2015_PERUBAHAN_KEEMPAT_SURAT_EDARAN_D...):
  Standard Filename: NA_PADK_2015.pdf
                  -> Peraturan_ADK_19_Tahun_2015_PERUBAHAN_KEEMPAT_SURAT_EDARAN_DEWAN_KOMISIONER_OTORITAS_JASA_KEUANGAN_NOMOR_33_SEDK.02_2013_TENTANG_PEDOMAN_PADK_2015.pdf
  Path Relatif   : kb/PADK/2015/NA_PADK_2015.pdf
                -> kb/PADK/2015/Peraturan_ADK_19_Tahun_2015_PERUBAHAN_KEEMPAT_SURAT_EDARAN_DEWAN_KOMISIONER_OTORITAS_JASA_KEUANGAN_NOMOR_33_SEDK.02_2013_TENTANG_PEDOMAN_PADK_2015.pdf
  Berkas fisik ada: True (storage\kb\PADK\2015\NA_PADK_2015.pdf)
  -> Berkas fisik berhasil dipindahkan ke: storage\kb\PADK\2015\Peraturan_ADK_19_Tahun_2015_PERUBAHAN_KEEMPAT_SURAT_EDARAN_DEWAN_KOMISIONER_OTORITAS_JASA_KEUANGAN_NOMOR_33_SEDK.02_2013_TENTANG_PEDOMAN_PADK_2015.pdf

--- Pemeriksaan Kandidat Scan Database ---
  Kandidat ID 522: 03/2015 -> 27/POJK.03/2015
  Kandidat ID 523: 03/2015 -> 27/POJK.03/2015
  Kandidat ID 524: 03/2015 -> 27/POJK.03/2015
  Kandidat ID 514: 03/2017 -> 56/SEOJK.03/2017

[SUKSES] Seluruh perubahan berhasil di-commit ke database.
```

---

## 5. VERIFIKASI LANGSUNG DARI REST API (OUTPUT MENTAH CURL)

### 5.1 `curl.exe -s "http://localhost:8000/api/v1/documents/43"`
```json
{"id":43,"title":"Peraturan Otoritas Jasa Keuangan Nomor 27 /POJK.03/2015 tentang Kegiatan Usaha Bank berupa Penitipan dengan Pengelolaan (Trust)","regulation_number":"27/POJK.03/2015","regulation_type":"POJK","release_date":"2015-12-04","regulation_year":2015,"bidang":"Perbankan","naming_format":["nama","jenis","tahun"],"naming_separator":"_","source_url":"https://jdih.ojk.go.id/Web/ViewPeraturan/DownloadDokumen/167604d9-1b16-bc7c-cda1-bb3ff505cbb4","original_filename":"POJK 27-2015.pdf","file_path_pdf":"kb/POJK/2015/Peraturan Otoritas Jasa Keuangan Nomor 27 -POJK.03-2015 tentang Kegiatan Usaha Bank berupa Penitipan dengan Pengelolaan (Trust)_POJK_2015.pdf","standardized_filename":"Peraturan Otoritas Jasa Keuangan Nomor 27 -POJK.03-2015 tentang Kegiatan Usaha Bank berupa Penitipan dengan Pengelolaan (Trust)_POJK_2015.pdf","access_classification":"publik","document_role":"corpus_eksisting","status_keberlakuan":"diubah","processing_status":"diterima","extraction_method":null,"extraction_engine":null,"category_id":29,"category_path":["POJK","2015"],"is_placed":true,"job_id":4,"pdf_url":"/api/v1/documents/43/pdf","text_url":"/api/v1/documents/43/text","full_text_length":0,"extraction_confidence":null,"low_confidence_fields":[],"metadata_corrected_at":null,"extracted_at":null,"created_at":"2026-10-03T05:33:40.497439+00:00","updated_at":"2026-10-04T05:12:00.194128+00:00","articles":[],"legal_references":[]}
```

### 5.2 `curl.exe -s "http://localhost:8000/api/v1/documents/44"`
```json
{"id":44,"title":"Peraturan Otoritas Jasa Keuangan Republik Indonesia Nomor 26/POJK.04/2014 tentang Penjaminan Penyelesaian Transaksi Bursa","regulation_number":"26/POJK.04/2014","regulation_type":"POJK","release_date":"2014-11-19","regulation_year":2014,"bidang":"Pasar Modal, Keuangan Derivatif, dan Bursa Karbon","naming_format":["nama","jenis","tahun"],"naming_separator":"_","source_url":"https://jdih.ojk.go.id/Web/ViewPeraturan/DownloadDokumen/c2ade27d-eb4d-0913-eff6-8af6bc801d3e","original_filename":"Peraturan OJK Nomor 26 Tahun 2014.pdf","file_path_pdf":"kb/POJK/2014/Peraturan Otoritas Jasa Keuangan Republik Indonesia Nomor 26-POJK.04-2014 tentang Penjaminan Penyelesaian Transaksi Bursa_POJK_2014.pdf","standardized_filename":"Peraturan Otoritas Jasa Keuangan Republik Indonesia Nomor 26-POJK.04-2014 tentang Penjaminan Penyelesaian Transaksi Bursa_POJK_2014.pdf","access_classification":"publik","document_role":"corpus_eksisting","status_keberlakuan":"diubah","processing_status":"diterima","extraction_method":null,"extraction_engine":null,"category_id":37,"category_path":["POJK","2014"],"is_placed":true,"job_id":4,"pdf_url":"/api/v1/documents/44/pdf","text_url":"/api/v1/documents/44/text","full_text_length":0,"extraction_confidence":null,"low_confidence_fields":[],"metadata_corrected_at":null,"extracted_at":null,"created_at":"2026-10-03T05:33:42.285152+00:00","updated_at":"2026-10-04T05:12:00.194128+00:00","articles":[],"legal_references":[]}
```

### 5.3 `curl.exe -s "http://localhost:8000/api/v1/documents/36"`
```json
{"id":36,"title":"Tahun_izin_usaha_dan_pencabutan_izin_usaha_Manajer_Investasi_dan_Penasihat_Investasi_20_Perbaikan_Keputusan_OJK_tentang_izin_usaha_dan_pencabutan_izin_usaha_Reksa_Dana_berbentuk_Perseroan_serta_izin_usaha_dan_su","regulation_number":null,"regulation_type":null,"release_date":null,"regulation_year":null,"bidang":null,"naming_format":["nama","jenis","tahun"],"naming_separator":"_","source_url":"https://oneojk-my.sharepoint.com/personal/faris_budi_ojk_go_id/_layouts/15/download.aspx?SourceUrl=/personal/faris_budi_ojk_go_id/Documents/PUBLIC_GPSI/ITS%20Capstone%20Project%202026/HERO/downloads/Tahun_izin_usaha_dan_pencabutan_izin_usaha_Manajer_Investasi_dan_Penasihat_Investasi_20_Perbaikan_Keputusan_OJK_tentang_izin_usaha_dan_pencabutan_izin_usaha_Reksa_Dana_berbentuk_Perseroan_serta_izin_usaha_dan_su.pdf","original_filename":"Tahun_izin_usaha_dan_pencabutan_izin_usaha_Manajer_Investasi_dan_Penasihat_Investasi_20_Perbaikan_Keputusan_OJK_tentang_izin.pdf","file_path_pdf":"pdf/_inbox/Tahun_izin_usaha_dan_pencabutan_izin_usaha_Manajer_Investasi_dan_Penasihat_Investasi_20_Perbaikan_Keputusan_OJK_tentang_izin_usaha_dan_NA_NA__08a1586b.pdf","standardized_filename":"Tahun_izin_usaha_dan_pencabutan_izin_usaha_Manajer_Investasi_dan_Penasihat_Investasi_20_Perbaikan_Keputusan_OJK_tentang_izin_usaha_dan_NA_NA.pdf","access_classification":"publik","document_role":"corpus_eksisting","status_keberlakuan":"tidak_diketahui","processing_status":"diterima","extraction_method":null,"extraction_engine":null,"category_id":null,"category_path":null,"is_placed":false,"job_id":3,"pdf_url":"/api/v1/documents/36/pdf","text_url":"/api/v1/documents/36/text","full_text_length":0,"extraction_confidence":null,"low_confidence_fields":[],"metadata_corrected_at":null,"extracted_at":null,"created_at":"2026-10-03T04:35:25.717908+00:00","updated_at":"2026-10-04T05:12:00.194128+00:00","articles":[],"legal_references":[]}
```

---

## 6. HASIL PENGUJIAN OTOMATIS (§3)

| # | Kasus Uji | Ekspektasi | Hasil | Status |
|---|---|---|---|---|
| **J01** | Parser JDIH untuk dokumen POJK 27/POJK.03/2015 (fixture mentah) | `27/POJK.03/2015` | Sesuai ekspektasi (`extract_jdih_regulation_number`) | **PASS** |
| **J02** | `build_standard_filename` dengan nomor `26/POJK.04/2014` | Mengandung `26-POJK.04-2014` | Sesuai ekspektasi (tidak menjadi `26POJK.042014`) | **PASS** |
| **J03** | Dokumen berjudul tanpa nomor/jenis/tahun | `nama` ≠ `NA` | Sesuai ekspektasi (`Tahun_izin_usaha..._NA_NA.pdf`) | **PASS** |
| **J04** | Skrip rename `--dry-run` | Tidak ada perubahan berkas/DB | Simulasi berhasil tanpa mengubah berkas/DB | **PASS** |
| **J05** | `pytest -q` seluruh test suite | Semua tes lulus tanpa kegagalan | **233 passed, 1 skipped** | **PASS** |

### Output Mentah Pytest
```
........................................................................ [ 30%]
............................................s........................... [ 61%]
........................................................................ [ 92%]
..................                                                       [100%]
============================== warnings summary ===============================
venv\Lib\site-packages\fastapi\testclient.py:1
  C:\Hero\hero-backend\venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

venv\Lib\site-packages\starlette\testclient.py:53
  C:\Hero\hero-backend\venv\Lib\site-packages\starlette\testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
233 passed, 1 skipped, 2 warnings in 351.35s (0:05:51)
```

---

## 7. INFORMASI GIT REPOSITORI

### 7.1 Git Remote
*(Perintah: `git remote -v`)*
```
(Tidak ada remote yang terkonfigurasi pada repositori lokal ini)
```

### 7.2 Git Status
*(Perintah: `git status --short` sebelum commit laporan)*
```
 M docs/reports/step12b-report.md
?? docs/reports/step12c-report.md
```

### 7.3 Git Log
*(Perintah: `git log --oneline -5`)*
```
d88dbad fix(scripts): skrip perbaikan nama berkas, verifikasi duplikat, dan penghitung frekuensi
e6f2b3a fix(naming): ganti slash dengan minus pada nama berkas dan perbaiki pemotongan judul
2d16578 fix(crawlers): perbaiki parsing nomor regulasi slash pada jdih_api
9215275 docs(reports): laporan langkah 12b koreksi kecil setelah review
d1d82ee docs(api): sinkronisasi kontrak API dan panduan frontend untuk regulation_year
```
