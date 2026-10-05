# LAPORAN LANGKAH 12e: PEMBERSIHAN TANGGAL KARANGAN 1 JANUARI DI FOLDER LOKAL

**HERO Backend · FASE 1**  
**Branch:** `fix/step12e-tanggal-folder`  
**Tanggal:** 6 Oktober 2026  
**Status:** SELESAI & TERVERIFIKASI  

---

## 1. RINGKASAN EKSEKUTIF & DIFF RINGKAS

### 1.1 Ringkasan Perbaikan
1. **`app/services/scan_service.py`**:
   - Menghapus pembuatan tanggal tiruan `date(meta["release_year"], 1, 1)`.
   - Mengatur `rel_d = None` sehingga kandidat hasil pindaian folder lokal (`file://`) memiliki `release_date = None`.
   - Memastikan tahun regulasi tetap diekstraksi ke `regulation_year` melalui `meta.get("regulation_year") or meta.get("release_year") or extract_regulation_year(...)`.
2. **`app/crawlers/sharepoint_postback.py`**:
   - Memodifikasi fungsi `_parse_indonesian_date` agar saat menerima teks yang hanya berupa angka tahun, mengembalikan `None` (bukan mengarang `date(tahun, 1, 1)`).
   - Menjaga pemanggil di baris penelusuran tanggal terbit/penetapan agar saat `rel_date` adalah `None`, angka tahun dari teks tanggal tersebut tetap tersimpan ke `parsed_year` dan dialirkan ke `regulation_year` (`cand_year = extract_regulation_year(...) or parsed_year`).
3. **Pembersihan Data Eksisting (`scripts/fix_folder_jan1_dates.py`)**:
   - Mengubah `release_date` menjadi `None` untuk 6 dokumen lokal (`#65`, `#67`, `#68`, `#69`, `#70`, `#71`) dan 13 kandidat `ScanCandidate`.
   - Memastikan `regulation_year` terisi dan `standardized_filename` tidak diubah.
   - Mencatat seluruh modifikasi dokumen ke dalam `audit_logs` dengan aksi `UPDATE_METADATA`.
4. **Pengujian**:
   - Menambahkan file tes `tests/test_step12e_fixes.py` (4 pengujian).
   - Seluruh test suite `pytest -q` lulus: **240 passed, 1 skipped, 2 warnings**.

### 1.2 Diff Ringkas (`git diff app/`)
```diff
diff --git a/app/crawlers/sharepoint_postback.py b/app/crawlers/sharepoint_postback.py
index c8a834b..6e9aec0 100644
--- a/app/crawlers/sharepoint_postback.py
+++ b/app/crawlers/sharepoint_postback.py
@@ -97,13 +97,10 @@ def _parse_indonesian_date(raw_text: str) -> Optional[date]:
         except ValueError:
             pass
 
-    # Format tahun saja
+    # Format tahun saja (Langkah 12e: dilarang mengarang tanggal 1 Januari; return None)
     year_m = re.search(r"\b(20\d\d|19\d\d)\b", cleaned)
     if year_m:
-        try:
-            return date(int(year_m.group(1)), 1, 1)
-        except ValueError:
-            pass
+        return None
 
     return None
 
@@ -325,15 +322,18 @@ class SharepointPostbackCrawler:
         if tb_m:
             eff_date = _parse_indonesian_date(html.unescape(tb_m.group(1)).strip())
 
+        tp_raw = None
         tp_m = re.search(r"Tanggal\s*(?:Penetapan|Terbit)\s*:\s*<span[^>]*>([^<]+)</span>", html_text, re.IGNORECASE)
         if not tp_m:
             tp_m = re.search(r"Tanggal\s*(?:Penetapan|Terbit)\s*:\s*([^\r\n<]+)", clean_plain, re.IGNORECASE)
         if tp_m:
-            rel_date = _parse_indonesian_date(html.unescape(tp_m.group(1)).strip())
+            tp_raw = html.unescape(tp_m.group(1)).strip()
+            rel_date = _parse_indonesian_date(tp_raw)
         else:
             det_tgl_m = re.search(r"ditetapkan\s+(?:pada\s+)?tanggal\s+([0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4})", clean_plain, re.IGNORECASE)
             if det_tgl_m:
-                rel_date = _parse_indonesian_date(det_tgl_m.group(1))
+                tp_raw = det_tgl_m.group(1)
+                rel_date = _parse_indonesian_date(tp_raw)
 
         # Ekstraksi tahun dari nomor atau judul untuk fallback release_date (seperti JDIH di 10c)
         parsed_year = None
@@ -345,6 +345,11 @@ class SharepointPostbackCrawler:
             ym = re.search(r"\b(19\d\d|20\d\d)\b", title)
             if ym:
                 parsed_year = int(ym.group(1))
+        # Langkah 12e: jika teks terbit/penetapan hanya ada tahun (rel_date=None), gunakan untuk regulation_year agar tahun tidak hilang
+        if not parsed_year and tp_raw:
+            ym = re.search(r"\b(19\d\d|20\d\d)\b", tp_raw)
+            if ym:
+                parsed_year = int(ym.group(1))
 
         # Jangan mengarang tanggal release_date bila penetapan tidak ada di sumber (tetap None).
         # Tanggal berlaku tetap berada di eff_date.
@@ -403,7 +408,7 @@ class SharepointPostbackCrawler:
                 title=title,
                 filename=fn,
                 release_date=rel_date,
-            )
+            ) or parsed_year
 
             cand = PdfCandidate(
                 url=norm_pdf_url,
diff --git a/app/services/scan_service.py b/app/services/scan_service.py
index 2edd8f2..dfbc30a 100644
--- a/app/services/scan_service.py
+++ b/app/services/scan_service.py
@@ -316,7 +316,8 @@ class ScanService:
                         u_hash = hashlib.sha256(f_url.encode("utf-8")).hexdigest()
 
                         meta = parse_onedrive_filename_metadata(entry.absolute_path.name)
-                        rel_d = date(meta["release_year"], 1, 1) if meta.get("release_year") else None
+                        # Langkah 12e: Jangan mengarang tanggal 1 Januari untuk folder lokal
+                        rel_d = None
 
                         # Cocokkan terhadap KB:
                         # 1. hash + size sama -> sudah_ada
@@ -364,11 +365,11 @@ class ScanService:
                                 is_selected = True
                                 c_new += 1
 
-                        cand_reg_year = meta.get("regulation_year") or extract_regulation_year(
+                        cand_reg_year = meta.get("regulation_year") or meta.get("release_year") or extract_regulation_year(
                             regulation_number=meta.get("regulation_number"),
                             title=entry.absolute_path.stem.replace("_", " "),
                             filename=entry.absolute_path.name,
-                            release_date=rel_d,
+                            release_date=None,
                         )
                         cand_row = ScanCandidate(
                             scan_id=session.id,
```

---

## 2. HASIL PENELUSURAN POLA SERUPA (GREP)

### 2.1 Perintah: `git grep -n ", 1, 1)" app/`
```
app/routers/naming.py:42:DEFAULT_SAMPLE_RELEASE_DATE = date(2026, 1, 1)
```
*Catatan: `app/routers/naming.py` baris 42 adalah konstanta contoh pratinjau format penamaan (`DEFAULT_SAMPLE_RELEASE_DATE`), sehingga dibiarkan sesuai ketentuan spesifikasi.*

---

## 3. OUTPUT EKSEKUSI SKRIP PERBAIKAN DATA

### 3.1 Mode Simulasi: `.\venv\Scripts\python scripts/fix_folder_jan1_dates.py --dry-run`
```
================================================================================
HERO BACKEND - PERBAIKAN TANGGAL 1 JANUARI FOLDER LOKAL (LANGKAH 12e)
Mode : DRY-RUN (Simulasi saja)
================================================================================

[DOKUMEN] Ditemukan 6 dokumen ber-source_url 'file://' dengan release_date 1 Januari:
  - Dokumen ID 65:
      Title               : HERO-UJI-1 POJK-99-2025 Sepatu-Roda
      Source URL          : file:///app/sources/uji_folder/HERO-UJI-1_POJK-99-2025_Sepatu-Roda.pdf
      Standard Filename   : NA HERO-UJI-1 POJK-99-2025 Sepatu-Roda 2025.pdf (TIDAK DIUBAH)
      Release Date        : 2025-01-01 -> None
      Regulation Year     : 2025 -> 2025
  - Dokumen ID 67:
      Title               : POJK 11 2022 Penyelenggaraan Teknologi Informasi
      Source URL          : file:///app/sources/demo_ojk_peraturan/POJK_11_2022_Penyelenggaraan_Teknologi_Informasi.pdf
      Standard Filename   : POJK 11 Tahun 2022 POJK 11 2022 Penyelenggaraan Teknologi Informasi 2022.pdf (TIDAK DIUBAH)
      Release Date        : 2022-01-01 -> None
      Regulation Year     : 2022 -> 2022
  - Dokumen ID 68:
      Title               : POJK 12 2023 Penerapan Tata Kelola Syariah
      Source URL          : file:///app/sources/demo_ojk_peraturan/POJK_12_2023_Penerapan_Tata_Kelola_Syariah.pdf
      Standard Filename   : POJK 12 Tahun 2023 POJK 12 2023 Penerapan Tata Kelola Syariah 2023.pdf (TIDAK DIUBAH)
      Release Date        : 2023-01-01 -> None
      Regulation Year     : 2023 -> 2023
  - Dokumen ID 69:
      Title               : POJK 17 2023 Penerapan Tata Kelola Bank Umum
      Source URL          : file:///app/sources/demo_ojk_peraturan/POJK_17_2023_Penerapan_Tata_Kelola_Bank_Umum.pdf
      Standard Filename   : POJK 17 Tahun 2023 POJK 17 2023 Penerapan Tata Kelola Bank Umum 2023.pdf (TIDAK DIUBAH)
      Release Date        : 2023-01-01 -> None
      Regulation Year     : 2023 -> 2023
  - Dokumen ID 70:
      Title               : POJK 19 2023 Pengembangan Kualitas SDM BPR
      Source URL          : file:///app/sources/demo_ojk_peraturan/POJK_19_2023_Pengembangan_Kualitas_SDM_BPR.pdf
      Standard Filename   : POJK 19 Tahun 2023 POJK 19 2023 Pengembangan Kualitas SDM BPR 2023.pdf (TIDAK DIUBAH)
      Release Date        : 2023-01-01 -> None
      Regulation Year     : 2023 -> 2023
  - Dokumen ID 71:
      Title               : POJK 21 2023 Layanan Digital Bank Umum
      Source URL          : file:///app/sources/demo_ojk_peraturan/POJK_21_2023_Layanan_Digital_Bank_Umum.pdf
      Standard Filename   : POJK 21 Tahun 2023 POJK 21 2023 Layanan Digital Bank Umum 2023.pdf (TIDAK DIUBAH)
      Release Date        : 2023-01-01 -> None
      Regulation Year     : 2023 -> 2023

[KANDIDAT SCAN] Ditemukan 13 kandidat folder lokal dengan release_date 1 Januari:
  - Kandidat ID 6151 (Scan ID 14):
      Filename        : HERO-UJI-1_POJK-99-2025_Sepatu-Roda.pdf
      Release Date    : 2025-01-01 -> None
      Regulation Year : 2025 -> 2025
  - Kandidat ID 6157 (Scan ID 17):
      Filename        : POJK_11_2022_Penyelenggaraan_Teknologi_Informasi.pdf
      Release Date    : 2022-01-01 -> None
      Regulation Year : 2022 -> 2022
  - Kandidat ID 6158 (Scan ID 17):
      Filename        : POJK_12_2023_Penerapan_Tata_Kelola_Syariah.pdf
      Release Date    : 2023-01-01 -> None
      Regulation Year : 2023 -> 2023
  - Kandidat ID 6159 (Scan ID 17):
      Filename        : POJK_17_2023_Penerapan_Tata_Kelola_Bank_Umum.pdf
      Release Date    : 2023-01-01 -> None
      Regulation Year : 2023 -> 2023
  - Kandidat ID 6160 (Scan ID 17):
      Filename        : POJK_19_2023_Pengembangan_Kualitas_SDM_BPR.pdf
      Release Date    : 2023-01-01 -> None
      Regulation Year : 2023 -> 2023
  - Kandidat ID 6161 (Scan ID 17):
      Filename        : POJK_21_2023_Layanan_Digital_Bank_Umum.pdf
      Release Date    : 2023-01-01 -> None
      Regulation Year : 2023 -> 2023
  - Kandidat ID 6153 (Scan ID 15):
      Filename        : HERO-UJI-1_POJK-99-2025_Sepatu-Roda.pdf
      Release Date    : 2025-01-01 -> None
      Regulation Year : 2025 -> 2025
  - Kandidat ID 6162 (Scan ID 18):
      Filename        : POJK_11_2022_Penyelenggaraan_Teknologi_Informasi.pdf
      Release Date    : 2022-01-01 -> None
      Regulation Year : 2022 -> 2022
  - Kandidat ID 6163 (Scan ID 18):
      Filename        : POJK_12_2023_Penerapan_Tata_Kelola_Syariah.pdf
      Release Date    : 2023-01-01 -> None
      Regulation Year : 2023 -> 2023
  - Kandidat ID 6164 (Scan ID 18):
      Filename        : POJK_17_2023_Penerapan_Tata_Kelola_Bank_Umum.pdf
      Release Date    : 2023-01-01 -> None
      Regulation Year : 2023 -> 2023
  - Kandidat ID 6165 (Scan ID 18):
      Filename        : POJK_19_2023_Pengembangan_Kualitas_SDM_BPR.pdf
      Release Date    : 2023-01-01 -> None
      Regulation Year : 2023 -> 2023
  - Kandidat ID 6166 (Scan ID 18):
      Filename        : POJK_21_2023_Layanan_Digital_Bank_Umum.pdf
      Release Date    : 2023-01-01 -> None
      Regulation Year : 2023 -> 2023
  - Kandidat ID 6155 (Scan ID 16):
      Filename        : HERO-UJI-1_POJK-99-2025_Sepatu-Roda.pdf
      Release Date    : 2025-01-01 -> None
      Regulation Year : 2025 -> 2025

================================================================================
[SIMULASI SELESAI] Target perbaikan:
  - Dokumen target : 6
  - Kandidat target: 13
  Tidak ada data database yang diubah.
================================================================================
```

### 3.2 Mode Eksekusi Nyata: `.\venv\Scripts\python scripts/fix_folder_jan1_dates.py --apply`
```
================================================================================
HERO BACKEND - PERBAIKAN TANGGAL 1 JANUARI FOLDER LOKAL (LANGKAH 12e)
Mode : APPLY (Eksekusi nyata)
================================================================================

[DOKUMEN] Ditemukan 6 dokumen ber-source_url 'file://' dengan release_date 1 Januari:
  - Dokumen ID 65:
      Title               : HERO-UJI-1 POJK-99-2025 Sepatu-Roda
      Source URL          : file:///app/sources/uji_folder/HERO-UJI-1_POJK-99-2025_Sepatu-Roda.pdf
      Standard Filename   : NA HERO-UJI-1 POJK-99-2025 Sepatu-Roda 2025.pdf (TIDAK DIUBAH)
      Release Date        : 2025-01-01 -> None
      Regulation Year     : 2025 -> 2025
  - Dokumen ID 67:
      Title               : POJK 11 2022 Penyelenggaraan Teknologi Informasi
      Source URL          : file:///app/sources/demo_ojk_peraturan/POJK_11_2022_Penyelenggaraan_Teknologi_Informasi.pdf
      Standard Filename   : POJK 11 Tahun 2022 POJK 11 2022 Penyelenggaraan Teknologi Informasi 2022.pdf (TIDAK DIUBAH)
      Release Date        : 2022-01-01 -> None
      Regulation Year     : 2022 -> 2022
  - Dokumen ID 68:
      Title               : POJK 12 2023 Penerapan Tata Kelola Syariah
      Source URL          : file:///app/sources/demo_ojk_peraturan/POJK_12_2023_Penerapan_Tata_Kelola_Syariah.pdf
      Standard Filename   : POJK 12 Tahun 2023 POJK 12 2023 Penerapan Tata Kelola Syariah 2023.pdf (TIDAK DIUBAH)
      Release Date        : 2023-01-01 -> None
      Regulation Year     : 2023 -> 2023
  - Dokumen ID 69:
      Title               : POJK 17 2023 Penerapan Tata Kelola Bank Umum
      Source URL          : file:///app/sources/demo_ojk_peraturan/POJK_17_2023_Penerapan_Tata_Kelola_Bank_Umum.pdf
      Standard Filename   : POJK 17 Tahun 2023 POJK 17 2023 Penerapan Tata Kelola Bank Umum 2023.pdf (TIDAK DIUBAH)
      Release Date        : 2023-01-01 -> None
      Regulation Year     : 2023 -> 2023
  - Dokumen ID 70:
      Title               : POJK 19 2023 Pengembangan Kualitas SDM BPR
      Source URL          : file:///app/sources/demo_ojk_peraturan/POJK_19_2023_Pengembangan_Kualitas_SDM_BPR.pdf
      Standard Filename   : POJK 19 Tahun 2023 POJK 19 2023 Pengembangan Kualitas SDM BPR 2023.pdf (TIDAK DIUBAH)
      Release Date        : 2023-01-01 -> None
      Regulation Year     : 2023 -> 2023
  - Dokumen ID 71:
      Title               : POJK 21 2023 Layanan Digital Bank Umum
      Source URL          : file:///app/sources/demo_ojk_peraturan/POJK_21_2023_Layanan_Digital_Bank_Umum.pdf
      Standard Filename   : POJK 21 Tahun 2023 POJK 21 2023 Layanan Digital Bank Umum 2023.pdf (TIDAK DIUBAH)
      Release Date        : 2023-01-01 -> None
      Regulation Year     : 2023 -> 2023

[KANDIDAT SCAN] Ditemukan 13 kandidat folder lokal dengan release_date 1 Januari:
  - Kandidat ID 6151 (Scan ID 14):
      Filename        : HERO-UJI-1_POJK-99-2025_Sepatu-Roda.pdf
      Release Date    : 2025-01-01 -> None
      Regulation Year : 2025 -> 2025
  - Kandidat ID 6157 (Scan ID 17):
      Filename        : POJK_11_2022_Penyelenggaraan_Teknologi_Informasi.pdf
      Release Date    : 2022-01-01 -> None
      Regulation Year : 2022 -> 2022
  - Kandidat ID 6158 (Scan ID 17):
      Filename        : POJK_12_2023_Penerapan_Tata_Kelola_Syariah.pdf
      Release Date    : 2023-01-01 -> None
      Regulation Year : 2023 -> 2023
  - Kandidat ID 6159 (Scan ID 17):
      Filename        : POJK_17_2023_Penerapan_Tata_Kelola_Bank_Umum.pdf
      Release Date    : 2023-01-01 -> None
      Regulation Year : 2023 -> 2023
  - Kandidat ID 6160 (Scan ID 17):
      Filename        : POJK_19_2023_Pengembangan_Kualitas_SDM_BPR.pdf
      Release Date    : 2023-01-01 -> None
      Regulation Year : 2023 -> 2023
  - Kandidat ID 6161 (Scan ID 17):
      Filename        : POJK_21_2023_Layanan_Digital_Bank_Umum.pdf
      Release Date    : 2023-01-01 -> None
      Regulation Year : 2023 -> 2023
  - Kandidat ID 6153 (Scan ID 15):
      Filename        : HERO-UJI-1_POJK-99-2025_Sepatu-Roda.pdf
      Release Date    : 2025-01-01 -> None
      Regulation Year : 2025 -> 2025
  - Kandidat ID 6162 (Scan ID 18):
      Filename        : POJK_11_2022_Penyelenggaraan_Teknologi_Informasi.pdf
      Release Date    : 2022-01-01 -> None
      Regulation Year : 2022 -> 2022
  - Kandidat ID 6163 (Scan ID 18):
      Filename        : POJK_12_2023_Penerapan_Tata_Kelola_Syariah.pdf
      Release Date    : 2023-01-01 -> None
      Regulation Year : 2023 -> 2023
  - Kandidat ID 6164 (Scan ID 18):
      Filename        : POJK_17_2023_Penerapan_Tata_Kelola_Bank_Umum.pdf
      Release Date    : 2023-01-01 -> None
      Regulation Year : 2023 -> 2023
  - Kandidat ID 6165 (Scan ID 18):
      Filename        : POJK_19_2023_Pengembangan_Kualitas_SDM_BPR.pdf
      Release Date    : 2023-01-01 -> None
      Regulation Year : 2023 -> 2023
  - Kandidat ID 6166 (Scan ID 18):
      Filename        : POJK_21_2023_Layanan_Digital_Bank_Umum.pdf
      Release Date    : 2023-01-01 -> None
      Regulation Year : 2023 -> 2023
  - Kandidat ID 6155 (Scan ID 16):
      Filename        : HERO-UJI-1_POJK-99-2025_Sepatu-Roda.pdf
      Release Date    : 2025-01-01 -> None
      Regulation Year : 2025 -> 2025

================================================================================
[SUKSES] Berhasil menerapkan perbaikan ke database:
  - Dokumen diperbarui : 6
  - Kandidat diperbarui: 13
================================================================================
```

---

## 4. HASIL SUITE PENGUJIAN OTOMATIS PYTEST

### 4.1 Pengujian Khusus Langkah 12e (`tests/test_step12e_fixes.py`)
*(Perintah: `.\venv\Scripts\python -m pytest tests/test_step12e_fixes.py -v`)*

```
============================= test session starts =============================
platform win32 -- Python 3.13.7, pytest-9.1.1, pluggy-1.6.0 -- C:\Hero\hero-backend\venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Hero\hero-backend
plugins: anyio-4.15.1
collecting ... collected 4 items

tests/test_step12e_fixes.py::test_e01_parse_indonesian_date_year_only_returns_none PASSED [ 25%]
tests/test_step12e_fixes.py::test_e02_parse_indonesian_date_full_date_returns_date PASSED [ 50%]
tests/test_step12e_fixes.py::test_e03_scan_folder_pojk_2022_release_date_null_and_regulation_year_2022 PASSED [ 75%]
tests/test_step12e_fixes.py::test_e04_pull_folder_candidate_preserves_null_release_date PASSED [100%]

============================== warnings summary ===============================
venv\Lib\site-packages\fastapi\testclient.py:1
  C:\Hero\hero-backend\venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

venv\Lib\site-packages\starlette\testclient.py:53
  C:\Hero\hero-backend\venv\Lib\site-packages\starlette\testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================== 4 passed, 2 warnings in 3.51s ========================
```

### 4.2 Seluruh Suite Pytest (`pytest -q`)
*(Perintah: `.\venv\Scripts\python -m pytest -q`)*

```
........................................................................ [ 29%]
............................................s........................... [ 59%]
........................................................................ [ 89%]
.........................                                                [100%]
============================== warnings summary ===============================
venv\Lib\site-packages\fastapi\testclient.py:1
  C:\Hero\hero-backend\venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

venv\Lib\site-packages\starlette\testclient.py:53
  C:\Hero\hero-backend\venv\Lib\site-packages\starlette\testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
240 passed, 1 skipped, 2 warnings in 224.83s (0:03:44)
```

---

## 5. UJI LIVE SESUAI INSTRUKSI SPESIFIKASI

### 5.1 Restart Container Backend
*(Perintah: `docker compose restart backend`)*

```
 Container hero_fastapi  Restarting
 Container hero_fastapi  Started
```

### 5.2 Pengujian Dokumen #67
*(Perintah: `curl.exe -s http://localhost:8000/api/v1/documents/67`)*

```json
{"id":67,"title":"POJK 11 2022 Penyelenggaraan Teknologi Informasi","regulation_number":"POJK 11 Tahun 2022","regulation_type":"POJK","release_date":null,"regulation_year":2022,"bidang":"PVML uji","naming_format":["nomor","nama","tahun"],"naming_separator":" ","source_url":"file:///app/sources/demo_ojk_peraturan/POJK_11_2022_Penyelenggaraan_Teknologi_Informasi.pdf","original_filename":"POJK_11_2022_Penyelenggaraan_Teknologi_Informasi.pdf","file_path_pdf":"kb/POJK/POJK 11 Tahun 2022 POJK 11 2022 Penyelenggaraan Teknologi Informasi 2022.pdf","standardized_filename":"POJK 11 Tahun 2022 POJK 11 2022 Penyelenggaraan Teknologi Informasi 2022.pdf","access_classification":"publik","document_role":"corpus_eksisting","status_keberlakuan":"tidak_diketahui","processing_status":"diterima","extraction_method":null,"extraction_engine":null,"category_id":1,"category_path":["POJK"],"is_placed":true,"job_id":32,"pdf_url":"/api/v1/documents/67/pdf","text_url":"/api/v1/documents/67/text","full_text_length":0,"extraction_confidence":null,"low_confidence_fields":[],"metadata_corrected_at":"2026-10-05T16:44:44.848041+00:00","extracted_at":null,"created_at":"2026-10-05T16:21:12.485497+00:00","updated_at":"2026-10-05T16:55:25.369762+00:00","articles":[],"legal_references":[]}
```
*Hasil Verifikasi: `release_date: null` dan `regulation_year: 2022`.*

### 5.3 Pengujian Ringkasan Dashboard
*(Perintah: `curl.exe -s http://localhost:8000/api/v1/dashboard/summary`)*

```json
{"kb":{"corpus_documents":69,"draft_documents":2,"target_fase1":20,"target_met":true,"by_status_keberlakuan":{"berlaku":10,"diubah":2,"dicabut":2,"tidak_diketahui":57},"by_processing_status":{"diterima":71,"diproses":0,"perlu_koreksi":0,"terindeks":0,"gagal":0,"ditolak":0},"by_regulation_type":[{"regulation_type":"POJK","label":"POJK","count":28},{"regulation_type":"PADK","label":"PADK","count":18},{"regulation_type":"SEOJK","label":"SEOJK","count":11},{"regulation_type":null,"label":"Belum diketahui","count":8},{"regulation_type":"KEPDIR","label":"KEPDIR","count":2},{"regulation_type":"UU","label":"UU","count":1},{"regulation_type":"PBI","label":"PBI","count":1}],"by_year":[{"year":2026,"label":"2026","count":19},{"year":2025,"label":"2025","count":16},{"year":2024,"label":"2024","count":3},{"year":2023,"label":"2023","count":6},{"year":2022,"label":"2022","count":2},{"year":2021,"label":"2021","count":1},{"year":2017,"label":"2017","count":1},{"year":2016,"label":"2016","count":2},{"year":2015,"label":"2015","count":3},{"year":2014,"label":"2014","count":1},{"year":2012,"label":"2012","count":1},{"year":1995,"label":"1995","count":1},{"year":1993,"label":"1993","count":1},{"year":1992,"label":"1992","count":1},{"year":null,"label":"Belum diketahui","count":11}],"placed_documents":57,"inbox_documents":14},"ingest":{"open_failures":1,"needs_review":0,"active_scans":5,"recent_jobs":[{"id":32,"job_type":"sinkron_folder","status":"selesai","started_at":"2026-10-05T16:21:12.475170+00:00","finished_at":"2026-10-05T16:21:12.885907+00:00","success_count":5,"duplicate_count":0,"skipped_count":0,"failed_count":0,"processed_count":5,"total_found":5},{"id":31,"job_type":"sinkron_folder","status":"selesai","started_at":"2026-10-05T16:11:19.538369+00:00","finished_at":"2026-10-05T16:11:19.874489+00:00","success_count":2,"duplicate_count":0,"skipped_count":0,"failed_count":0,"processed_count":2,"total_found":2},{"id":30,"job_type":"unggah_manual","status":"selesai","started_at":"2026-10-04T18:26:36.044464+00:00","finished_at":"2026-10-04T18:26:36.174939+00:00","success_count":1,"duplicate_count":0,"skipped_count":0,"failed_count":0,"processed_count":1,"total_found":1},{"id":29,"job_type":"unggah_manual","status":"selesai","started_at":"2026-10-04T18:26:28.157501+00:00","finished_at":"2026-10-04T18:26:28.202537+00:00","success_count":1,"duplicate_count":0,"skipped_count":0,"failed_count":0,"processed_count":1,"total_found":1},{"id":28,"job_type":"unggah_manual","status":"selesai","started_at":"2026-10-04T18:26:21.670558+00:00","finished_at":"2026-10-04T18:26:21.712093+00:00","success_count":1,"duplicate_count":0,"skipped_count":0,"failed_count":0,"processed_count":1,"total_found":1}]},"sources":{"total":5,"active":5,"by_type":{"situs_web":2,"folder_lokal":2,"onedrive_public":1}},"generated_at":"2026-10-05T17:00:51.967396+00:00"}
```

---

## 6. INFORMASI GIT REPOSITORI

### 6.1 Git Log
*(Perintah: `git log --oneline -3`)*

```
0dc512c fix: tambah import os dan SimpleHttpCrawler yang hilang
41285f3 docs(reports): tambah laporan langkah 12d
7a6857e fix(scan): kunci advisory pada koneksi khusus, import time, dan pemulihan sesi macet
```

### 6.2 Git Status
*(Perintah: `git status --short`)*

```
 M app/crawlers/sharepoint_postback.py
 M app/services/scan_service.py
?? docs/reports/step12e-report.md
?? scripts/fix_folder_jan1_dates.py
?? tests/test_step12e_fixes.py
```
