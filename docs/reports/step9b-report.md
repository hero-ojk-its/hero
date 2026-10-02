# LAPORAN LANGKAH 9B: PERBAIKAN KONTRAK API FASE 1 & BUILDER GENERATOR

> **Branch:** `feat/step9-api-contract-rename`  
> **Role:** Senior Backend Engineer  
> **Tujuan:** Memperbaiki seluruh temuan review (§1.1–§1.6) pada kontrak API `docs/api/KONTRAK-API-FASE1.md`, artefak pendamping (`hero-fase1.http`, `frontend-changes-step9.md`), skrip pembangkit `scripts/build_api_contract.py`, dan membersihkan dead code validasi di `scan_service.py`.

---

## 1. RINGKASAN PERBAIKAN PER TEMUAN REVIEW (§1.1 – §1.6)

### 1.1 Endpoint Pencarian yang Tidak Ada (KRITIS)
- **Masalah:** §7.2 mendokumentasikan rute `GET /api/v1/documents/search` yang tidak ada di router FastAPI sehingga menghasilkan galat 422 (`"search"` diparse sebagai integer `document_id`). Istilah "Semantik" juga salah karena sistem menggunakan PostgreSQL Full-Text Search.
- **Perbaikan:**
  1. Menggabungkan §7.1 dan §7.2 menjadi satu endpoint `GET /api/v1/documents/` dengan dua contoh nyata:
     - **Contoh A:** Filter & daftar KB tanpa `q` (`GET /api/v1/documents/?bidang=Perbankan&skip=0&limit=10`).
     - **Contoh B:** Pencarian frasa teks hukum dengan `q` + `highlight` terisi (`GET /api/v1/documents/?q=modal+inti&bidang=Perbankan&highlight=true`).
  2. Menghapus seluruh kemunculan kata **"Semantik"** dan menjelaskan bahwa pencarian regulasi Fase 1 berbasis PostgreSQL Full-Text Search (`tsvector`, `phraseto_tsquery`/`plainto_tsquery`/`websearch_to_tsquery`) dan trigram GIN untuk nomor regulasi.
  3. Memperbarui koleksi `docs/api/hero-fase1.http` dan catatan `docs/api/frontend-changes-step9.md`.

### 1.2 Skrip Pembangkit Wajib Memeriksa Kode Status (KRITIS)
- **Masalah:** Skrip builder menangkap respons HTTP tanpa memvalidasi status code yang diharapkan.
- **Perbaikan:**
  1. Menambahkan fungsi penangkap ketat:
     ```python
     def capture(block_name: str, response: Any, expect: int = 200) -> None:
         if response.status_code != expect:
             raise RuntimeError(
                 f"[BUILD ERROR] Blok '{block_name}' gagal! "
                 f"Diharapkan status code {expect}, tetapi menerima {response.status_code}. "
                 f"Detail: {response.text}"
             )
         auto_blocks[block_name] = format_json_block(response.json())
     ```
  2. Semua blok respons nyata kini memvalidasi status code secara eksplisit (`expect=200`, `expect=201`, `expect=202`, `expect=404`, `expect=422`). Jika status code tidak cocok, proses build langsung gagal dengan exit code 1 dan menampilkan nama blok serta detail kegagalan.

### 1.3 Contoh Detail Dokumen Tidak Konsisten
- **Masalah:** Skrip lama menulis langsung ke ORM database (`doc_row.`, `db.add_all`), sehingga pipeline placement dan rename tidak terpicu (menghasilkan status `terindeks` tetapi `is_placed: false`, path `_inbox`, dan `full_text_length: 0`).
- **Perbaikan:**
  1. Menghapus penulisan langsung ke DB untuk dokumen.
  2. Membangun seluruh contoh dokumen melalui alur HTTP API murni:
     - `POST /api/v1/ingest/upload-pdf` (dengan `naming_format`, `naming_separator`, `bidang`);
     - `PATCH /api/v1/internal/documents/{id}/extraction` (dengan `X-Internal-API-Key`, mengirimkan metadata, `bidang`, `full_text`, confidence, dan memicu `PlacementService`);
     - `POST /api/v1/internal/articles` (bulk insert chunk pasal);
     - `GET /api/v1/documents/{id}` untuk menangkap respons detail konsisten.
  3. Hasil respons detail (§8.1) kini konsisten: `is_placed: true`, `file_path_pdf: "kb/POJK/2026/Penyelenggaraan Usaha Bank Umum_POJK_2026_Perbankan.pdf"`, `standardized_filename: "Penyelenggaraan Usaha Bank Umum_POJK_2026_Perbankan.pdf"`, `full_text_length: 338`, dan memuat pasal.
  4. Baris kegagalan ingest dibangun secara realistis melalui upload berkas corrupt dan pelaporan timeout ekstraksi via internal API.

### 1.4 Klaim Teks yang Tidak Sesuai Kode
- **Perbaikan:**
  1. Batas ukuran upload pada §12 diubah dari 50 MB menjadi **100 MB** dan dibangkitkan dinamis dari `settings.max_upload_bytes // (1024 * 1024)`.
  2. Default parameter `limit` pada pembaca teks mentah (§8.2) diperbaiki dari 10.000 menjadi **20.000** (maks 100.000) sesuai kode `app/routers/documents.py`.
  3. Mengaudit seluruh klaim teks non-AUTO terhadap kode sumber dan schema OpenAPI.

### 1.5 Status dan Format Dokumen
- **Perbaikan:**
  1. Mengubah header kontrak dari "Resmi Disepakati" menjadi:  
     `Status: DRAF v0.9 — untuk disepakati Tim Frontend & Tim Backend (rapat internal 1 Okt 2026)`
  2. Menambahkan tabel kosong **Persetujuan** (Nama / Peran · Tanggal · Catatan).
  3. Memperbaiki seluruh tautan file lokal `file:///docs/api/...` menjadi tautan relatif GitHub (`hero-fase1.http`, `openapi-fase1.json`, `frontend-changes-step9.md`).
  4. Memperbaiki penomoran tabel enum (§11) menjadi urut `11.1` sampai `11.13` menggunakan indeks perulangan `enumerate(..., 1)`.
  5. Mengganti contoh sumber situs web perayapan dari JDIH OJK (SPA) ke `https://jdih.esdm.go.id` (HTML murni) dan menambahkan catatan teknis mengenai backlog dukungan SPA (#88) dan OneDrive (#30).

### 1.6 Kebersihan Kode Kecil
- **Perbaikan:** Menghapus blok `except ValueError` yang tidak pernah tercapai pada `app/services/scan_service.py` (`start_pull`), karena `validate_naming_format` dan `validate_naming_separator` sudah langsung melempar `HTTPException(422)`.

---

## 2. TABEL KOREKSI KLAIM TEKS (§1.4)

| Lokasi Bagian | Klaim Lama | Nilai Benar | Sumber Kode / OpenAPI |
|---|---|---|---|
| §12 (HTTP 413) | "Ukuran berkas melebihi batas default 50 MB" | **100 MB** | `app/config.py:max_upload_bytes = 100 * 1024 * 1024` |
| §8.2 (Query limit) | "limit (panjang karakter, default 10000)" | **default 20000, maks 100000** | `app/routers/documents.py:read_document_text` (`Query(20000, ge=1, le=100000)`) |
| §7.1 & §7.2 (Routing) | `GET /api/v1/documents/search` | **`GET /api/v1/documents/?q=...`** | `app/routers/documents.py:list_documents` |
| §7 (Jenis Search) | "Pencarian Semantik" | **PostgreSQL Full-Text Search (tsvector/tsquery & trigram)** | `app/services/document_search_service.py` |
| §3.1, §5.1, §5.2, §6.2 | "Respons (200 OK)" | **Respons (202 Accepted)** | `app/routers/scans.py` & `app/routers/scraping_sources.py` |
| §11 (Penomoran Enum) | Loncat `11.9`, `11.16`, `11.23`, ... | **`11.1` – `11.13` berurutan** | `scripts/build_api_contract.py:generate_enum_tables` |
| Header Dokumen | "Status: Resmi Disepakati" | **"Status: DRAF v0.9 — untuk disepakati Tim Frontend & Tim Backend"** | Kesepakatan kerja tim (belum ditandatangani) |

---

## 3. OUTPUT MENTAH PENGUJIAN (K01 – K06)

### K01: Uji Build Gagal saat Status Code Tidak Sesuai / Path Salah
*(Menjalankan capture dengan endpoint salah `/api/v1/documents/search` dengan `expect=200`)*

```text
C:\Users\IBUCOMP\Downloads\hero-backend\venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
  from starlette.testclient import TestClient as TestClient  # noqa
Memulai build API Contract HERO Backend...
Traceback (most recent call last):
  File "C:\Users\IBUCOMP\Downloads\hero-backend\scripts\build_api_contract.py", line 1213, in <module>
    run_contract_builder()
    ~~~~~~~~~~~~~~~~~~~~^^
  File "C:\Users\IBUCOMP\Downloads\hero-backend\scripts\build_api_contract.py", line 326, in run_contract_builder
    capture("documents_search_fake", r_wrong, expect=200)
    ~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\IBUCOMP\Downloads\hero-backend\scripts\build_api_contract.py", line 313, in capture
    raise RuntimeError(
    ...<3 lines>...
    )
RuntimeError: [BUILD ERROR] Blok 'documents_search_fake' gagal! Diharapkan status code 200, tetapi menerima 422. Detail: {"detail":[{"type":"int_parsing","loc":["path","document_id"],"msg":"Input should be a valid integer, unable to parse string as an integer","input":"search"}]}
```

---

### K02: Uji Build Normal Dua Kali (Idempoten & Tanpa Diff)

```text
C:\Users\IBUCOMP\Downloads\hero-backend\venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
  from starlette.testclient import TestClient as TestClient  # noqa
Memulai build API Contract HERO Backend...
Kontrak API berhasil ditulis ke: C:\Users\IBUCOMP\Downloads\hero-backend\docs\api\KONTRAK-API-FASE1.md
Snapshot OpenAPI berhasil ditulis ke: C:\Users\IBUCOMP\Downloads\hero-backend\docs\api\openapi-fase1.json
REST Client collection berhasil ditulis ke: C:\Users\IBUCOMP\Downloads\hero-backend\docs\api\hero-fase1.http
Pembuatan kontrak API selesai!
H1: E9AEEBC6CD32058CE3FF3D0FF2A1D45FF9B5825D57F05EB6C28D409DD355B7E8
H2: E9AEEBC6CD32058CE3FF3D0FF2A1D45FF9B5825D57F05EB6C28D409DD355B7E8
Match: True
```

---

### K03: Grep Dokumen Kontrak & Artefak untuk Istilah Terlarang

```powershell
Get-ChildItem -Path "docs\api\*" | Select-String -Pattern "documents/search", "semantik", "file:///", "Resmi Disepakati", "50 MB"
```

```text
(Tidak ada output - 0 kecocokan)
```

---

### K04: Verifikasi Hasil Contoh Detail Dokumen (§8.1)

Cuplikan JSON respons nyata dari `docs/api/KONTRAK-API-FASE1.md`:
```json
{
  "id": 1,
  "title": "Penyelenggaraan Usaha Bank Umum",
  "regulation_number": "POJK 10/POJK.03/2026",
  "regulation_type": "POJK",
  "release_date": "2026-03-15",
  "bidang": "Perbankan",
  "naming_format": [
    "nama",
    "jenis",
    "tahun",
    "bidang"
  ],
  "naming_separator": "_",
  "source_url": null,
  "original_filename": "POJK 10 Tahun 2026 Bank Umum.pdf",
  "file_path_pdf": "kb/POJK/2026/Penyelenggaraan Usaha Bank Umum_POJK_2026_Perbankan.pdf",
  "standardized_filename": "Penyelenggaraan Usaha Bank Umum_POJK_2026_Perbankan.pdf",
  "access_classification": "publik",
  "document_role": "corpus_eksisting",
  "status_keberlakuan": "tidak_diketahui",
  "processing_status": "terindeks",
  "extraction_method": "teks_langsung",
  "extraction_engine": null,
  "category_id": 8,
  "category_path": [
    "POJK",
    "2026"
  ],
  "is_placed": true,
  "job_id": 3,
  "pdf_url": "/api/v1/documents/1/pdf",
  "text_url": "/api/v1/documents/1/text",
  "full_text_length": 338,
  "extraction_confidence": {
    "title": 0.98,
    "bidang": 0.92,
    "release_date": 0.9,
    "regulation_type": 0.95,
    "regulation_number": 0.96
  },
  "low_confidence_fields": [],
  "metadata_corrected_at": null,
  "extracted_at": "2026-10-01T10:00:00Z",
  "created_at": "2026-10-01T10:00:00Z",
  "updated_at": "2026-10-01T10:00:00Z",
  "articles": [
    {
      "id": 1,
      "level": "pasal",
      "chapter_title": "BAB I KETENTUAN UMUM",
      "article_number": "Pasal 1",
      "content_text": "Dalam Peraturan Otoritas Jasa Keuangan ini yang dimaksud dengan Bank Umum adalah bank yang melaksanakan kegiatan usaha secara konvensional dan atau berdasarkan prinsip syariah yang dalam kegiatannya memberikan jasa dalam lalu lintas pembayaran.",
      "order_index": 1
    },
    {
      "id": 2,
      "level": "pasal",
      "chapter_title": "BAB II MODAL INTI",
      "article_number": "Pasal 2",
      "content_text": "Modal inti minimum bagi Bank Umum ditetapkan paling sedikit sebesar Rp3.000.000.000.000 (tiga triliun rupiah) yang wajib dipenuhi oleh setiap entitas perbankan.",
      "order_index": 2
    }
  ],
  "legal_references": []
}
```

---

### K05: Grep Skrip untuk Mutasi DB Langsung (`db.add`, `db.add_all`, `doc_row.`)

```powershell
Select-String -Path "scripts\build_api_contract.py" -Pattern "db\.add", "db\.add_all", "doc_row\."
```

```text
scripts\build_api_contract.py:412:            db.add_all([c1, c2])
```
*Catatan Penjelasan:* Satu-satunya pemanggilan `db.add_all([c1, c2])` adalah untuk menyemai kandidat perayapan `ScanCandidate` (c1 dan c2) pada sesi scan situs web, agar endpoint seleksi kandidat dapat diuji tanpa menjalankan spider eksternal aktif saat build dokumen. Seluruh data dokumen, ekstraksi, pasal, dan failure dibuat murni via alur HTTP API.

---

### K06: Uji Regresi Pytest Penuh (`pytest -q`)

```text
........................................................................ [ 38%]
...................s.................................................... [ 76%]
............................................                             [100%]
============================== warnings summary ===============================
venv\Lib\site-packages\fastapi\testclient.py:1
  C:\Users\IBUCOMP\Downloads\hero-backend\venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

venv\Lib\site-packages\starlette\testclient.py:53
  C:\Users\IBUCOMP\Downloads\hero-backend\venv\Lib\site-packages\starlette\testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
187 passed, 1 skipped, 2 warnings in 157.32s (0:02:37)
```

---

## 4. STATUS GIT & LOG COMMIT

### `git log --oneline -4`
```text
69c93ef docs(api): perbaiki kontrak API Fase 1, hapus search palsu, dan sesuaikan klaim kode
54e0210 fix(builder): validasi status code ketat, alur ekstraksi API murni, dan pembersihan dead code
e01d678 docs(report): laporan langkah 9 kontrak API dan rename dinamis
095b003 test: unit and integration tests N01-N14, C01-C04 dan pembaruan smoke test
```

### `git status --short`
```text
(bersih, working tree clean)
```

### `git remote -v`
```text
(tidak ada konfigurasi remote)
```

