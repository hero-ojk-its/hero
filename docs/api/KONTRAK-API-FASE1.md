# KONTRAK API HERO BACKEND — FASE 1 (MVP)

> **Untuk Tim Frontend (Personil_D)**  
> **Status:** DRAF v0.9 — untuk disepakati Personil_D & Personil_E (rapat internal 1 Okt 2026)  
> **Basis Implementasi:** FastAPI · PostgreSQL 15.4 · SQLAlchemy 2.x  
> **Artefak Pendamping:**
> - [Koleksi Request Siap Eksekusi (REST Client / VS Code)](hero-fase1.http)
> - [Snapshot Skema OpenAPI JSON untuk Type Generator](openapi-fase1.json)
> - [Catatan Perubahan Frontend Step 9](frontend-changes-step9.md)

### Tabel Persetujuan

| Nama | Peran | Tanggal | Catatan |
|---|---|---|---|
| Personil_D | Frontend Lead | - | Belum ditandatangani |
| Personil_E | Backend Lead / PM | - | Belum ditandatangani |

---

## DAFTAR ISI

1. [Konvensi Umum & Pola Komunikasi](#1-konvensi-umum--pola-komunikasi)
2. [Alur 1: Tambah & Kelola Sumber Dokumen](#2-alur-1-tambah--kelola-sumber-dokumen)
3. [Alur 2: Pemindaian Situs Web, Seleksi & Centang Kandidat](#3-alur-2-pemindaian-situs-web-seleksi--centang-kandidat)
4. [Alur 3: Pemilihan Format Penamaan Berkas Dinamis](#4-alur-3-pemilihan-format-penamaan-berkas-dinamis)
5. [Alur 4: Penarikan Berkas (Knowledge Base & Unduh ZIP)](#5-alur-4-penarikan-berkas-knowledge-base--unduh-zip)
6. [Alur 5: Unggah Berkas Manual & Sinkronisasi Folder Lokal](#6-alur-5-unggah-berkas-manual--sinkronisasi-folder-lokal)
7. [Alur 6: Eksplorasi Knowledge Base & Pencarian Regulasi](#7-alur-6-eksplorasi-knowledge-base--pencarian-regulasi)
8. [Alur 7: Detail Dokumen, Pembaca Teks & Penampil PDF](#8-alur-7-detail-dokumen-pembaca-teks--penampil-pdf)
9. [Alur 8: Kurasi & Koreksi Metadata serta Antrean Penanganan Gagal](#9-alur-8-kurasi--koreksi-metadata-serta-antrean-penanganan-gagal)
10. [Alur 9: Dashboard Ringkasan Eksekutif](#10-alur-9-dashboard-ringkasan-eksekutif)
11. [Tabel Referensi Enum & Label Bahasa Indonesia](#11-tabel-referensi-enum--label-bahasa-indonesia)
12. [Daftar Kode Galat HTTP & Penanganan di UI](#12-daftar-kode-galat-http--penanganan-di-ui)
13. [Catatan & Pertanyaan untuk Frontend](#13-catatan--pertanyaan-untuk-frontend)

---

## 1. KONVENSI UMUM & POLA KOMUNIKASI

### 1.1 Base URL & Prefix
- **Lokal (Pengembangan):** `http://localhost:8000` (atau `NEXT_PUBLIC_API_URL`)
- **Prefix Endpoint:** Semua rute API diawali dengan `/api/v1`.

### 1.2 Format Waktu & Paginasi
- **Format Tanggal:** ISO 8601 UTC (contoh: `2026-10-01T10:00:00Z`).
- **Paginasi Standar:** Menggunakan query parameter `skip` (offset, default `0`) dan `limit` (ukuran halaman, default `20` atau `50`).
- **Struktur Respons Daftar:**
  ```json
  {
    "total": 100,
    "items": [ ... ],
    "skip": 0,
    "limit": 20
  }
  ```

### 1.3 Dua Bentuk Format Galat (Error Response)
Frontend wajib menangani **2 format error**:

1. **Galat Logika Bisnis / HTTP 4xx (dari Backend Application):**
   ```json
   {
     "detail": "Pesan galat dalam bahasa Indonesia yang ramah pengguna."
   }
   ```
   *Contoh Riil 404 (Dokumen tidak ditemukan):*
<!-- AUTO:error_404_sample -->
```json
{
  "detail": "Dokumen tidak ditemukan"
}
```
<!-- /AUTO:error_404_sample -->

2. **Galat Validasi Schema (HTTP 422 dari FastAPI/Pydantic):**
   ```json
   {
     "detail": [
       {
         "loc": ["body", "naming_format", 1],
         "msg": "Komponen naming_format tidak valid: 'warna_invalid'. Komponen yang didukung: 'nama', 'nomor', 'tahun', 'jenis', 'bidang'.",
         "type": "value_error"
       }
     ]
   }
   ```
   *Contoh Riil 422:*
<!-- AUTO:error_422_sample -->
```json
{
  "detail": "Komponen naming_format tidak valid: 'warna_invalid'. Komponen yang didukung: 'nama', 'nomor', 'tahun', 'jenis', 'bidang'."
}
```
<!-- /AUTO:error_422_sample -->

### 1.4 Status Autentikasi & CORS
- **`AUTH_ENABLED=false` (Default Fase 1):** Header `Authorization: Bearer <token>` **tidak wajib** disertakan pada seluruh endpoint publik/operasional.
- **CORS:** Backend mengizinkan origin yang didefinisikan pada `CORS_ORIGINS` di `.env` (misal: `http://localhost:3000,http://127.0.0.1:3000`).

### 1.5 Pola Operasi Panjang (Long-Running Operations)
Operasi penarikan berkas (`/pull`) dan pemindaian situs (`/scans/`) menggunakan pola polling:
1. Frontend mengirim request dengan query `wait=false` (default).
2. Backend merespons langsung dengan status `202 Accepted` (atau `200 OK`) berisi `job_id` atau `scan_id`.
3. Frontend melakukan polling `GET /api/v1/scans/{id}` atau `GET /api/v1/ingest/jobs/{job_id}` setiap 2 detik hingga mencapai **status final**: `selesai`, `gagal`, atau `dibatalkan`.

---

## 2. ALUR 1: TAMBAH & KELOLA SUMBER DOKUMEN

Mendukung pendaftaran situs web dan folder lokal sebagai sumber regulasi.

> [!NOTE]
> Contoh URL menggunakan `https://jdih.esdm.go.id` yang telah divalidasi dengan crawler standar (`SimpleHttpCrawler`). Dukungan untuk situs berbasis SPA (seperti JDIH OJK) dan integrasi Microsoft OneDrive sedang dikerjakan pada isu terpisah (#88, #30).

### 2.1 Tambah Sumber Situs Web
- **Method & Path:** `POST /api/v1/scraping-sources/`
- **Request Body:**
<!-- AUTO:source_create_web_request -->
```json
{
  "name": "JDIH ESDM",
  "url": "https://jdih.esdm.go.id",
  "source_type": "situs_web",
  "crawl_depth": 2,
  "default_access_classification": "publik",
  "default_document_role": "corpus_eksisting",
  "default_naming_format": [
    "nomor",
    "nama",
    "tahun"
  ],
  "default_naming_separator": " ",
  "is_active": true
}
```
<!-- /AUTO:source_create_web_request -->
- **Respons (201 Created):**
<!-- AUTO:source_create_web_response -->
```json
{
  "id": 1,
  "name": "JDIH ESDM",
  "url": "https://jdih.esdm.go.id",
  "address": "https://jdih.esdm.go.id",
  "source_type": "situs_web",
  "crawl_depth": 2,
  "recursive": true,
  "default_access_classification": "publik",
  "default_document_role": "corpus_eksisting",
  "default_naming_format": [
    "nomor",
    "nama",
    "tahun"
  ],
  "default_naming_separator": " ",
  "is_active": true,
  "last_run_at": null,
  "last_run_status": null,
  "last_run_message": null,
  "last_job_id": null,
  "created_at": "2026-10-01T10:00:00Z",
  "updated_at": null
}
```
<!-- /AUTO:source_create_web_response -->

### 2.2 Tambah Sumber Folder Lokal
- **Method & Path:** `POST /api/v1/scraping-sources/`
- **Respons (201 Created):**
<!-- AUTO:source_create_local_response -->
```json
{
  "id": 2,
  "name": "Folder Regulasi Lokal Perbankan",
  "url": "C:\\Users\\IBUCOMP\\Downloads\\hero-backend\\sources",
  "address": "C:\\Users\\IBUCOMP\\Downloads\\hero-backend\\sources",
  "source_type": "folder_lokal",
  "crawl_depth": null,
  "recursive": true,
  "default_access_classification": "non_publik",
  "default_document_role": "corpus_eksisting",
  "default_naming_format": [
    "nama",
    "tahun",
    "bidang"
  ],
  "default_naming_separator": "_",
  "is_active": true,
  "last_run_at": null,
  "last_run_status": null,
  "last_run_message": null,
  "last_job_id": null,
  "created_at": "2026-10-01T10:00:00Z",
  "updated_at": null
}
```
<!-- /AUTO:source_create_local_response -->

### 2.3 Daftar Sumber Dokumen
- **Method & Path:** `GET /api/v1/scraping-sources/`
- **Respons (200 OK):**
<!-- AUTO:source_list_response -->
```json
[
  {
    "id": 1,
    "name": "JDIH ESDM",
    "url": "https://jdih.esdm.go.id",
    "address": "https://jdih.esdm.go.id",
    "source_type": "situs_web",
    "crawl_depth": 2,
    "recursive": true,
    "default_access_classification": "publik",
    "default_document_role": "corpus_eksisting",
    "default_naming_format": [
      "nomor",
      "nama",
      "tahun"
    ],
    "default_naming_separator": " ",
    "is_active": true,
    "last_run_at": null,
    "last_run_status": null,
    "last_run_message": null,
    "last_job_id": null,
    "created_at": "2026-10-01T10:00:00Z",
    "updated_at": null
  },
  {
    "id": 2,
    "name": "Folder Regulasi Lokal Perbankan",
    "url": "C:\\Users\\IBUCOMP\\Downloads\\hero-backend\\sources",
    "address": "C:\\Users\\IBUCOMP\\Downloads\\hero-backend\\sources",
    "source_type": "folder_lokal",
    "crawl_depth": null,
    "recursive": true,
    "default_access_classification": "non_publik",
    "default_document_role": "corpus_eksisting",
    "default_naming_format": [
      "nama",
      "tahun",
      "bidang"
    ],
    "default_naming_separator": "_",
    "is_active": true,
    "last_run_at": null,
    "last_run_status": null,
    "last_run_message": null,
    "last_job_id": null,
    "created_at": "2026-10-01T10:00:00Z",
    "updated_at": null
  }
]
```
<!-- /AUTO:source_list_response -->

---

## 3. ALUR 2: PEMINDAIAN SITUS WEB, SELEKSI & CENTANG KANDIDAT

### 3.1 Memulai Sesi Pemindaian
- **Method & Path:** `POST /api/v1/scans/`
- **Request Body:**
<!-- AUTO:scan_create_request -->
```json
{
  "source_id": 1,
  "crawl_depth": 1,
  "max_pages": 10
}
```
<!-- /AUTO:scan_create_request -->
- **Respons (202 Accepted):**
<!-- AUTO:scan_create_response -->
```json
{
  "scan_id": 1,
  "status": "antrian",
  "message": "Sesi pemindaian #1 berhasil dijadwalkan."
}
```
<!-- /AUTO:scan_create_response -->

### 3.2 Memeriksa Detail & Status Sesi Pemindaian
- **Method & Path:** `GET /api/v1/scans/{scan_id}`
- **Respons (200 OK):**
<!-- AUTO:scan_detail_response -->
```json
{
  "id": 1,
  "source_id": 1,
  "start_url": "https://jdih.esdm.go.id",
  "crawl_depth": 1,
  "mode": "simple_http",
  "crawler_name": null,
  "status": "siap_dipilih",
  "cancel_requested": false,
  "pages_visited": 5,
  "candidates_summary": {
    "total": 2,
    "baru": 1,
    "sudah_ada": 1,
    "mungkin_ada": 0,
    "terpilih": 1
  },
  "truncated": false,
  "errors": [],
  "error_message": null,
  "destination": null,
  "naming_format": null,
  "naming_separator": null,
  "pull_job_id": null,
  "pull_progress": null,
  "download_url": null,
  "claimed_at": null,
  "started_at": null,
  "scanned_at": null,
  "finished_at": null,
  "created_at": "2026-10-01T10:00:00Z",
  "updated_at": "2026-10-01T10:00:00Z"
}
```
<!-- /AUTO:scan_detail_response -->

### 3.3 Mengambil Daftar Kandidat Berkas
- **Method & Path:** `GET /api/v1/scans/{scan_id}/candidates`
- **Query Params:** `match_status` (`baru`, `sudah_ada`, `mungkin_ada`), `selected` (`true`, `false`).
- **Respons (200 OK):**
<!-- AUTO:scan_candidates_response -->
```json
{
  "items": [
    {
      "id": 1,
      "scan_id": 1,
      "url": "https://jdih.esdm.go.id/docs/Permen_ESDM_16_2026.pdf",
      "filename": "Permen_ESDM_16_2026.pdf",
      "size_bytes": 1048576,
      "found_on_page": null,
      "depth": 1,
      "match_status": "baru",
      "match_reason": null,
      "match_document_id": null,
      "match_document": null,
      "selected": true,
      "pull_outcome": null,
      "document_id": null,
      "failure_id": null,
      "export_path": null,
      "message": null
    },
    {
      "id": 2,
      "scan_id": 1,
      "url": "https://jdih.esdm.go.id/docs/Kepmen_05_2025.pdf",
      "filename": "Kepmen_05_2025.pdf",
      "size_bytes": 524288,
      "found_on_page": null,
      "depth": 1,
      "match_status": "sudah_ada",
      "match_reason": "url_sama",
      "match_document_id": null,
      "match_document": null,
      "selected": false,
      "pull_outcome": null,
      "document_id": null,
      "failure_id": null,
      "export_path": null,
      "message": null
    }
  ],
  "total": 2,
  "skip": 0,
  "limit": 50
}
```
<!-- /AUTO:scan_candidates_response -->

### 3.4 Mengubah Pilihan Centang Berkas (Selection)
- **Method & Path:** `PATCH /api/v1/scans/{scan_id}/selection`
- **Aksi yang Didukung:**
  - `select_all`: Centang semua berkas berstatus `baru`.
  - `select_none`: Hapus semua centangan.
  - `set`: Atur centang berkas tertentu berdasarkan daftar `candidate_ids`.
- **Respons (200 OK):**
<!-- AUTO:scan_selection_response -->
```json
{
  "scan_id": 1,
  "summary": {
    "total": 2,
    "baru": 0,
    "sudah_ada": 0,
    "mungkin_ada": 0,
    "terpilih": 1
  },
  "rejected_ids": []
}
```
<!-- /AUTO:scan_selection_response -->

---

## 4. ALUR 3: PEMILIHAN FORMAT PENAMAAN BERKAS DINAMIS

Mendukung personalisasi nama berkas sesuai urutan tombol di UI (`nama`, `tahun`, `jenis`, `bidang`, `nomor`).

### 4.1 Mendapatkan Komponen & Aturan Penamaan
- **Method & Path:** `GET /api/v1/naming/components`
- **Respons (200 OK):**
<!-- AUTO:naming_components_response -->
```json
{
  "components": [
    {
      "key": "nama",
      "label": "Nama"
    },
    {
      "key": "tahun",
      "label": "Tahun"
    },
    {
      "key": "jenis",
      "label": "Jenis"
    },
    {
      "key": "bidang",
      "label": "Bidang"
    },
    {
      "key": "nomor",
      "label": "Nomor"
    }
  ],
  "separators": [
    " ",
    "_",
    "-"
  ],
  "wildcard": "NA",
  "default_format": [
    "nomor",
    "nama",
    "tahun"
  ],
  "max_components": 8
}
```
<!-- /AUTO:naming_components_response -->

### 4.2 Pratinjau Live Penamaan Berkas
- **Method & Path:** `POST /api/v1/naming/preview`
- **Respons Contoh Bawaan (Default Sample):**
<!-- AUTO:naming_preview_default_response -->
```json
{
  "filename": "Penyelenggaraan Bursa Mineral dan Komoditas Strategis POJK 2026.pdf",
  "missing_components": []
}
```
<!-- /AUTO:naming_preview_default_response -->
- **Respons Contoh Kustom (Custom Sample):**
<!-- AUTO:naming_preview_custom_response -->
```json
{
  "filename": "POJK 12-POJK.03-2025_Kesehatan Bank Perkreditan Rakyat_2025_Perbankan.pdf",
  "missing_components": []
}
```
<!-- /AUTO:naming_preview_custom_response -->

---

## 5. ALUR 4: PENARIKAN BERKAS (KNOWLEDGE BASE & UNDUH ZIP)

### 5.1 Tarik ke Knowledge Base (Asinkron)
- **Method & Path:** `POST /api/v1/scans/{scan_id}/pull`
- **Respons (202 Accepted):**
<!-- AUTO:scan_pull_kb_response -->
```json
{
  "job_id": 1,
  "status": "antrian",
  "message": "Penarikan 1 berkas untuk sesi #1 ke 'knowledge_base' berhasil dijadwalkan."
}
```
<!-- /AUTO:scan_pull_kb_response -->

### 5.2 Tarik ke Folder Unduhan (Arsip ZIP)
- **Method & Path:** `POST /api/v1/scans/{scan_id}/pull`
- **Respons (202 Accepted):**
<!-- AUTO:scan_pull_zip_response -->
```json
{
  "job_id": 2,
  "status": "antrian",
  "message": "Penarikan 1 berkas untuk sesi #1 ke 'unduh_folder' berhasil dijadwalkan."
}
```
<!-- /AUTO:scan_pull_zip_response -->
- **Unduh ZIP:** `GET /api/v1/scans/{scan_id}/download` setelah status sesi `selesai`.

---

## 6. ALUR 5: UNGGAH BERKAS MANUAL & SINKRONISASI FOLDER LOKAL

### 6.1 Unggah Berkas PDF (Multipart Form Data)
- **Method & Path:** `POST /api/v1/ingest/upload-pdf`
- **Form Data:**
  - `files`: File PDF tunggal atau jamak.
  - `access_classification`: `publik` | `non_publik` (Wajib).
  - `document_role`: `corpus_eksisting` | `draft_kajian` (Wajib).
  - `naming_format`: String dipisah koma (contoh: `"nama,jenis,tahun,bidang"`).
  - `naming_separator`: `" "` | `"_"` | `"-"`.
  - `bidang`: Sektor regulasi (contoh: `"Perbankan"`).
- **Respons (200 OK):**
<!-- AUTO:upload_pdf_response -->
```json
{
  "message": "Proses unggah selesai: 1 berhasil, 0 duplikat, 0 gagal dari total 1 file.",
  "job_id": 3,
  "job_status": "selesai",
  "total_files": 1,
  "success_count": 1,
  "duplicate_count": 0,
  "failed_count": 0,
  "details": [
    {
      "filename": "POJK 10 Tahun 2026 Bank Umum.pdf",
      "status": "success",
      "document_id": 1,
      "duplicate_of_document_id": null,
      "failure_id": null,
      "title": "POJK 10 Tahun 2026 Bank Umum",
      "regulation_number": null,
      "file_size_bytes": 754,
      "file_hash": "2df8e641bbc42600c3546af4f941782fd956cb7fc91e56753f41dfd6a471468d",
      "message": null,
      "error": null,
      "reason_code": null,
      "placement": {
        "placed": false,
        "reason": "metadata_belum_cukup",
        "category_path": null,
        "standardized_filename": "POJK 10 Tahun 2026 Bank Umum_NA_NA_Perbankan.pdf"
      }
    }
  ]
}
```
<!-- /AUTO:upload_pdf_response -->

### 6.2 Sinkronisasi Folder Lokal
- **Method & Path:** `POST /api/v1/scraping-sources/{source_id}/run`
- **Respons (202 Accepted):**
<!-- AUTO:source_run_response -->
```json
{
  "job_id": 4,
  "status": "antrian",
  "message": "Job sinkronisasi folder ID 4 telah dijadwalkan."
}
```
<!-- /AUTO:source_run_response -->

### 6.3 Daftar Berkas Sumber Folder
- **Method & Path:** `GET /api/v1/scraping-sources/{source_id}/files`
- **Respons (200 OK):**
<!-- AUTO:source_files_response -->
```json
{
  "total": 0,
  "items": []
}
```
<!-- /AUTO:source_files_response -->

---

## 7. ALUR 6: EKSPLORASI KNOWLEDGE BASE & PENCARIAN REGULASI

Pencarian regulasi pada MVP Fase 1 menggunakan **PostgreSQL Full-Text Search** berbasis `tsvector` dan `tsquery` berbobot (`title` [A], `regulation_number` [A], `articles.content_text` [B], `full_text` [C]) serta pencocokan nomor regulasi via indeks trigram GIN. Belum ada pencarian berbasis model vektor atau embedding pada Fase 1.

### 7.1 Daftar, Filter & Pencarian Dokumen KB
- **Method & Path:** `GET /api/v1/documents/`
- **Query Params:**
  - `q` (string, opsional): Kata kunci / frasa teks hukum (contoh: `modal inti bank umum`).
  - `mode` (string, opsional): Mode full-text PostgreSQL: `phrase` (default, frasa urut) | `all` (semua kata) | `web` (boolean websearch).
  - `highlight` (boolean, opsional): `true` (default) untuk menyertakan cuplikan teks dengan tag `<b>...</b>`.
  - `bidang` (string, opsional): Filter sektor regulasi (contoh: `Perbankan`, `Pasar Modal`, `BMKS`, `IKNB`).
  - `category_id` (integer, opsional): Filter kategori KB.
  - `regulation_type` (string, opsional): Filter jenis regulasi (contoh: `POJK`, `SEOJK`, `UU`, `PP`).
  - `year` (integer, opsional): Filter tahun regulasi.
  - `status_keberlakuan` (string, opsional): `berlaku`, `dicabut`, `diubah`, `tidak_diketahui`.
  - `regulation_number` (string, opsional): Pencocokan nomor regulasi (contoh: `POJK 10/POJK.03/2026`).
  - `access_classification` (string, opsional): `publik`, `non_publik`.
  - `document_role` (string, opsional): `corpus_eksisting`, `draft_kajian`.
  - `skip` (integer, opsional): Offset paginasi (default `0`).
  - `limit` (integer, opsional): Batas dokumen per halaman (default `20`, min `1`, max `100`).

#### Contoh A: Daftar & Filter Dokumen (Tanpa Parameter `q`)
*Request:* `GET /api/v1/documents/?bidang=Perbankan&skip=0&limit=10`
- **Respons (200 OK):**
<!-- AUTO:documents_list_response -->
```json
{
  "total": 1,
  "items": [
    {
      "id": 1,
      "title": "Penyelenggaraan Usaha Bank Umum",
      "regulation_number": "POJK 10/POJK.03/2026",
      "regulation_type": "POJK",
      "release_date": "2026-03-15",
      "bidang": "Perbankan",
      "access_classification": "publik",
      "document_role": "corpus_eksisting",
      "category_id": 8,
      "category_path": [
        "POJK",
        "2026"
      ],
      "status_keberlakuan": "tidak_diketahui",
      "processing_status": "terindeks",
      "extraction_method": "teks_langsung",
      "file_path_pdf": "kb/POJK/2026/Penyelenggaraan Usaha Bank Umum_POJK_2026_Perbankan.pdf",
      "file_hash": "2df8e641bbc42600c3546af4f941782fd956cb7fc91e56753f41dfd6a471468d",
      "file_size_bytes": 754,
      "standardized_filename": "Penyelenggaraan Usaha Bank Umum_POJK_2026_Perbankan.pdf",
      "source_url": null,
      "is_placed": true,
      "pdf_url": "/api/v1/documents/1/pdf",
      "restricted": false,
      "rank": null,
      "highlight": null,
      "created_at": "2026-10-01T10:00:00Z",
      "updated_at": "2026-10-01T10:00:00Z"
    }
  ],
  "query": {
    "q": null,
    "mode": "phrase",
    "regulation_number": null,
    "regulation_type": null,
    "category_id": null,
    "include_subcategories": true,
    "status_keberlakuan": null,
    "document_role": null,
    "access_classification": null,
    "processing_status": null,
    "date_from": null,
    "date_to": null,
    "year": null,
    "bidang": "Perbankan",
    "sort": "release_date_desc",
    "skip": 0,
    "limit": 10
  }
}
```
<!-- /AUTO:documents_list_response -->

#### Contoh B: Pencarian Full-Text & Highlight (Dengan Parameter `q`)
*Request:* `GET /api/v1/documents/?q=modal+inti&bidang=Perbankan&highlight=true`
- **Respons (200 OK):**
<!-- AUTO:documents_search_response -->
```json
{
  "total": 1,
  "items": [
    {
      "id": 1,
      "title": "Penyelenggaraan Usaha Bank Umum",
      "regulation_number": "POJK 10/POJK.03/2026",
      "regulation_type": "POJK",
      "release_date": "2026-03-15",
      "bidang": "Perbankan",
      "access_classification": "publik",
      "document_role": "corpus_eksisting",
      "category_id": 8,
      "category_path": [
        "POJK",
        "2026"
      ],
      "status_keberlakuan": "tidak_diketahui",
      "processing_status": "terindeks",
      "extraction_method": "teks_langsung",
      "file_path_pdf": "kb/POJK/2026/Penyelenggaraan Usaha Bank Umum_POJK_2026_Perbankan.pdf",
      "file_hash": "2df8e641bbc42600c3546af4f941782fd956cb7fc91e56753f41dfd6a471468d",
      "file_size_bytes": 754,
      "standardized_filename": "Penyelenggaraan Usaha Bank Umum_POJK_2026_Perbankan.pdf",
      "source_url": null,
      "is_placed": true,
      "pdf_url": "/api/v1/documents/1/pdf",
      "restricted": false,
      "rank": 0.4,
      "highlight": "Bank Umum adalah bank konvensional dan syariah. BAB II <mark>MODAL</mark> <mark>INTI</mark> Pasal 2: <mark>Modal</mark> <mark>inti</mark> minimum bagi Bank Umum ditetapkan sebesar Rp3.000.000.000.000 (tiga triliun rupiah",
      "created_at": "2026-10-01T10:00:00Z",
      "updated_at": "2026-10-01T10:00:00Z"
    }
  ],
  "query": {
    "q": "modal inti",
    "mode": "phrase",
    "regulation_number": null,
    "regulation_type": null,
    "category_id": null,
    "include_subcategories": true,
    "status_keberlakuan": null,
    "document_role": null,
    "access_classification": null,
    "processing_status": null,
    "date_from": null,
    "date_to": null,
    "year": null,
    "bidang": "Perbankan",
    "sort": "relevance",
    "skip": 0,
    "limit": 20
  }
}
```
<!-- /AUTO:documents_search_response -->

---

## 8. ALUR 7: DETAIL DOKUMEN, PEMBACA TEKS & PENAMPIL PDF

### 8.1 Detail Lengkap Dokumen
- **Method & Path:** `GET /api/v1/documents/{document_id}`
- **Respons (200 OK):**
<!-- AUTO:document_detail_response -->
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
<!-- /AUTO:document_detail_response -->

### 8.2 Membaca Teks Mentah Dokumen
- **Method & Path:** `GET /api/v1/documents/{document_id}/text`
- **Query Params:** `offset` (karakter awal, default `0`), `limit` (panjang karakter, default `20000`, maks `100000`).
- **Respons (200 OK):**
<!-- AUTO:document_text_response -->
```json
{
  "document_id": 1,
  "total_length": 338,
  "offset": 0,
  "limit": 20000,
  "text": "Peraturan Otoritas Jasa Keuangan tentang Penyelenggaraan Usaha Bank Umum. BAB I KETENTUAN UMUM Pasal 1: Dalam Peraturan Otoritas Jasa Keuangan ini yang dimaksud dengan Bank Umum adalah bank konvensional dan syariah. BAB II MODAL INTI Pasal 2: Modal inti minimum bagi Bank Umum ditetapkan sebesar Rp3.000.000.000.000 (tiga triliun rupiah).",
  "extraction_method": "teks_langsung",
  "extraction_engine": null,
  "extracted_at": "2026-10-01T10:00:00Z"
}
```
<!-- /AUTO:document_text_response -->

### 8.3 Menampilkan Berkas PDF Asli di Browser
- **Method & Path:** `GET /api/v1/documents/{document_id}/pdf`
- **Header Respons:**
  - `Content-Type: application/pdf`
  - `Content-Disposition: inline; filename="Nama_Standar.pdf"`
- **Integrasi Frontend:**
  - Dapat langsung dimuat dalam tag `<iframe>`, `<embed>`, `<object>`, atau library PDF viewer seperti `pdf.js` / `@react-pdf-viewer`.
  - Contoh tag HTML:
    ```html
    <iframe src="http://localhost:8000/api/v1/documents/1/pdf" width="100%" height="800px" />
    ```
  - **Perilaku 403 Forbidden:** Jika dokumen berstatus `non_publik` dan autentikasi belum aktif, endpoint mengembalikan galat 403 dengan pesan `"Dokumen non-publik hanya dapat dibuka setelah login diaktifkan."`.

---

## 9. ALUR 8: KURASI & KOREKSI METADATA SERTA ANTREAN PENANGANAN GAGAL

### 9.1 Koreksi Metadata Dokumen
- **Method & Path:** `PATCH /api/v1/documents/{document_id}/metadata`
- **Body:** Mendukung pembaruan `title`, `regulation_number`, `regulation_type`, `release_date`, `bidang`, `category_id`, `status_keberlakuan`, `access_classification`, `document_role`.
- **Respons (200 OK):**
<!-- AUTO:document_patch_metadata_response -->
```json
{
  "id": 1,
  "title": "Penyelenggaraan Usaha Bank Umum Terkoreksi",
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
  "file_path_pdf": "kb/POJK/2026/Penyelenggaraan Usaha Bank Umum Terkoreksi_POJK_2026_Perbankan.pdf",
  "standardized_filename": "Penyelenggaraan Usaha Bank Umum Terkoreksi_POJK_2026_Perbankan.pdf",
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
  "metadata_corrected_at": "2026-10-01T10:00:00Z",
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
  "legal_references": [],
  "changed_fields": [
    "title"
  ],
  "placement": {
    "document_id": 1,
    "placed": true,
    "reason": "ditempatkan",
    "old_path": "kb/POJK/2026/Penyelenggaraan Usaha Bank Umum_POJK_2026_Perbankan.pdf",
    "new_path": "kb/POJK/2026/Penyelenggaraan Usaha Bank Umum Terkoreksi_POJK_2026_Perbankan.pdf",
    "category_id": 8,
    "category_path": [
      "POJK",
      "2026"
    ]
  }
}
```
<!-- /AUTO:document_patch_metadata_response -->

### 9.2 Daftar Antrean Gagal (Ingest Failures)
- **Method & Path:** `GET /api/v1/ingest/failures`
- **Query Params:** `job_id`, `failure_type`, `follow_up_status` (`belum_ditangani`, `diproses_ulang`, `diabaikan`, `all`), `include_duplicates` (`false`), `skip` (`0`), `limit` (`50`).
- **Respons (200 OK):**
<!-- AUTO:failures_list_response -->
```json
{
  "total": 2,
  "items": [
    {
      "id": 2,
      "job_id": 6,
      "original_filename": "NA Regulasi_Retry_2026 NA.pdf",
      "source_url": null,
      "failure_type": "ekstraksi_gagal",
      "reason_code": "ocr_timeout",
      "message": "Proses OCR timeout saat ekstraksi berkas.",
      "is_retryable": true,
      "quarantine_path": null,
      "file_hash": "1b8a579c5d1442d53c966ad651fefeb84b2fcb3f35c9e18cb9b5cc791c1ca298",
      "file_size_bytes": 451,
      "duplicate_of_document_id": null,
      "duplicate_of_document": null,
      "ingest_options": {},
      "follow_up_status": "belum_ditangani",
      "attempt_count": 0,
      "last_retry_at": null,
      "last_retry_job_id": null,
      "resolved_document_id": null,
      "handled_by_user_id": null,
      "handling_note": null,
      "created_at": "2026-10-01T10:00:00Z",
      "updated_at": "2026-10-01T10:00:00Z"
    },
    {
      "id": 1,
      "job_id": 5,
      "original_filename": "Peraturan_Rusak_2026.pdf",
      "source_url": null,
      "failure_type": "format_tidak_didukung",
      "reason_code": "format_tidak_didukung",
      "message": "Isi berkas bukan PDF yang valid meskipun berekstensi .pdf.",
      "is_retryable": false,
      "quarantine_path": null,
      "file_hash": "df3a7b99e39e3c376acdc68a06f7335a7ff7246596c9ac32c40836c74d891a7e",
      "file_size_bytes": 26,
      "duplicate_of_document_id": null,
      "duplicate_of_document": null,
      "ingest_options": {
        "metadata": {
          "title": null,
          "release_date": null,
          "regulation_type": null,
          "regulation_number": null
        },
        "category_id": null,
        "document_role": "corpus_eksisting",
        "access_classification": "publik"
      },
      "follow_up_status": "belum_ditangani",
      "attempt_count": 0,
      "last_retry_at": null,
      "last_retry_job_id": null,
      "resolved_document_id": null,
      "handled_by_user_id": null,
      "handling_note": null,
      "created_at": "2026-10-01T10:00:00Z",
      "updated_at": "2026-10-01T10:00:00Z"
    }
  ]
}
```
<!-- /AUTO:failures_list_response -->

### 9.3 Mencoba Ulang (Retry) Berkas Gagal
- **Method & Path:** `POST /api/v1/ingest/failures/{failure_id}/retry`
- **Respons (200 OK):**
<!-- AUTO:failure_retry_response -->
```json
{
  "failure": {
    "id": 2,
    "job_id": 6,
    "original_filename": "NA Regulasi_Retry_2026 NA.pdf",
    "source_url": null,
    "failure_type": "ekstraksi_gagal",
    "reason_code": "ocr_timeout",
    "message": "Proses OCR timeout saat ekstraksi berkas.",
    "is_retryable": true,
    "quarantine_path": null,
    "file_hash": "1b8a579c5d1442d53c966ad651fefeb84b2fcb3f35c9e18cb9b5cc791c1ca298",
    "file_size_bytes": 451,
    "duplicate_of_document_id": null,
    "duplicate_of_document": null,
    "ingest_options": {},
    "follow_up_status": "diproses_ulang",
    "attempt_count": 1,
    "last_retry_at": "2026-10-01T10:00:00Z",
    "last_retry_job_id": null,
    "resolved_document_id": null,
    "handled_by_user_id": null,
    "handling_note": null,
    "created_at": "2026-10-01T10:00:00Z",
    "updated_at": "2026-10-01T10:00:00Z"
  },
  "outcome": "requeued",
  "document_id": 2,
  "job_id": 6,
  "message": "Dokumen ID 2 berhasil di-antrekan ulang untuk ekstraksi."
}
```
<!-- /AUTO:failure_retry_response -->

### 9.4 Mengabaikan (Ignore) Berkas Gagal
- **Method & Path:** `PATCH /api/v1/ingest/failures/{failure_id}`
- **Body:** `{"follow_up_status": "diabaikan", "handling_note": "Catatan alasan pengabaian"}`
- **Respons (200 OK):**
<!-- AUTO:failure_ignore_response -->
```json
{
  "id": 2,
  "job_id": 6,
  "original_filename": "NA Regulasi_Retry_2026 NA.pdf",
  "source_url": null,
  "failure_type": "ekstraksi_gagal",
  "reason_code": "ocr_timeout",
  "message": "Proses OCR timeout saat ekstraksi berkas.",
  "is_retryable": true,
  "quarantine_path": null,
  "file_hash": "1b8a579c5d1442d53c966ad651fefeb84b2fcb3f35c9e18cb9b5cc791c1ca298",
  "file_size_bytes": 451,
  "duplicate_of_document_id": null,
  "duplicate_of_document": null,
  "ingest_options": {},
  "follow_up_status": "diabaikan",
  "attempt_count": 1,
  "last_retry_at": "2026-10-01T10:00:00Z",
  "last_retry_job_id": null,
  "resolved_document_id": null,
  "handled_by_user_id": null,
  "handling_note": "Abaikan berkas corrupt hasil pengujian.",
  "created_at": "2026-10-01T10:00:00Z",
  "updated_at": "2026-10-01T10:00:00Z"
}
```
<!-- /AUTO:failure_ignore_response -->

---

## 10. ALUR 9: DASHBOARD RINGKASAN EKSEKUTIF

### 10.1 Ringkasan Metrik Dashboard
- **Method & Path:** `GET /api/v1/dashboard/summary`
- **Respons (200 OK):**
<!-- AUTO:dashboard_summary_response -->
```json
{
  "kb": {
    "corpus_documents": 2,
    "draft_documents": 0,
    "target_fase1": 20,
    "target_met": false,
    "by_status_keberlakuan": {
      "berlaku": 0,
      "diubah": 0,
      "dicabut": 0,
      "tidak_diketahui": 2
    },
    "by_processing_status": {
      "diterima": 1,
      "diproses": 0,
      "perlu_koreksi": 0,
      "terindeks": 1,
      "gagal": 0,
      "ditolak": 0
    },
    "by_regulation_type": [
      {
        "regulation_type": "POJK",
        "label": "POJK",
        "count": 1
      },
      {
        "regulation_type": null,
        "label": "Belum diketahui",
        "count": 1
      }
    ],
    "by_year": [
      {
        "year": null,
        "label": "Belum diketahui",
        "count": 1
      },
      {
        "year": 2026,
        "label": "2026",
        "count": 1
      }
    ],
    "placed_documents": 1,
    "inbox_documents": 1
  },
  "ingest": {
    "open_failures": 1,
    "needs_review": 0,
    "active_scans": 1,
    "recent_jobs": [
      {
        "id": 6,
        "job_type": "unggah_manual",
        "status": "selesai",
        "started_at": "2026-10-01T10:00:00Z",
        "finished_at": "2026-10-01T10:00:00Z",
        "success_count": 1,
        "duplicate_count": 0,
        "skipped_count": 0,
        "failed_count": 0,
        "processed_count": 1,
        "total_found": 1
      },
      {
        "id": 5,
        "job_type": "unggah_manual",
        "status": "gagal",
        "started_at": "2026-10-01T10:00:00Z",
        "finished_at": "2026-10-01T10:00:00Z",
        "success_count": 0,
        "duplicate_count": 0,
        "skipped_count": 0,
        "failed_count": 1,
        "processed_count": 1,
        "total_found": 1
      },
      {
        "id": 4,
        "job_type": "sinkron_folder",
        "status": "antrian",
        "started_at": "2026-10-01T10:00:00Z",
        "finished_at": null,
        "success_count": 0,
        "duplicate_count": 0,
        "skipped_count": 0,
        "failed_count": 0,
        "processed_count": 0,
        "total_found": 0
      },
      {
        "id": 3,
        "job_type": "unggah_manual",
        "status": "selesai",
        "started_at": "2026-10-01T10:00:00Z",
        "finished_at": "2026-10-01T10:00:00Z",
        "success_count": 1,
        "duplicate_count": 0,
        "skipped_count": 0,
        "failed_count": 0,
        "processed_count": 1,
        "total_found": 1
      },
      {
        "id": 2,
        "job_type": "scraping",
        "status": "antrian",
        "started_at": "2026-10-01T10:00:00Z",
        "finished_at": null,
        "success_count": 0,
        "duplicate_count": 0,
        "skipped_count": 0,
        "failed_count": 0,
        "processed_count": 0,
        "total_found": 1
      }
    ]
  },
  "sources": {
    "total": 2,
    "active": 2,
    "by_type": {
      "situs_web": 1,
      "folder_lokal": 1,
      "onedrive_public": 0
    }
  },
  "generated_at": "2026-10-01T10:00:00Z"
}
```
<!-- /AUTO:dashboard_summary_response -->

---

## 11. TABEL REFERENSI ENUM & LABEL BAHASA INDONESIA

<!-- AUTO:enum_tables -->
### 11.1 Jenis Sumber Dokumen (`JenisSumber`)

Field respons/parameter: `source_type`

| Nilai Enum (Backend) | Label UI Indonesia | Keterangan |
|---|---|---|
| `situs_web` | **Situs Web** | Situs eksternal (misal: JDIH ESDM) untuk perayapan berkas. |
| `folder_lokal` | **Folder Lokal** | Direktori penyimpanan lokal di peladen. |
| `onedrive_public` | **OneDrive Publik** | Tautan folder publik Microsoft OneDrive. |


### 11.2 Klasifikasi Akses Dokumen (`KlasifikasiAkses`)

Field respons/parameter: `access_classification`

| Nilai Enum (Backend) | Label UI Indonesia | Keterangan |
|---|---|---|
| `publik` | **Publik** | Dapat diakses oleh publik tanpa batasan login. |
| `non_publik` | **Non-Publik** | Dokumen internal atau rahasia yang memerlukan autentikasi. |


### 11.3 Peran Dokumen (`PeranDokumen`)

Field respons/parameter: `document_role`

| Nilai Enum (Backend) | Label UI Indonesia | Keterangan |
|---|---|---|
| `corpus_eksisting` | **Corpus Eksisting** | Dokumen regulasi induk/utama dalam basis pengetahuan. |
| `draft_kajian` | **Draft Kajian** | Dokumen pendukung atau draft rancangan kajian regulasi. |


### 11.4 Status Sesi Pemindaian (`StatusPindai`)

Field respons/parameter: `status`

| Nilai Enum (Backend) | Label UI Indonesia | Keterangan |
|---|---|---|
| `antrian` | **Dalam Antrian** | Sesi pemindaian baru dibuat dan menunggu worker. |
| `memindai` | **Sedang Memindai** | Crawler sedang merambati halaman dan mengumpulkan tautan. |
| `siap_dipilih` | **Siap Dipilih** | Pemindaian selesai, pengguna dapat memilih berkas. |
| `menarik` | **Sedang Menarik** | Worker sedang mengunduh berkas terpilih. |
| `selesai` | **Selesai** | Seluruh proses pemindaian dan penarikan telah rampung. |
| `gagal` | **Gagal** | Pemindaian atau penarikan mengalami kesalahan fatal. |
| `dibatalkan` | **Dibatalkan** | Sesi dibatalkan atas permintaan pengguna. |


### 11.5 Status Kecocokan Kandidat (`StatusKandidat`)

Field respons/parameter: `match_status`

| Nilai Enum (Backend) | Label UI Indonesia | Keterangan |
|---|---|---|
| `baru` | **Baru** | Berkas belum pernah ada di sistem HERO (default dicentang). |
| `sudah_ada` | **Sudah Ada** | Berkas persis sama sudah ada di Knowledge Base (tidak dapat ditarik ulang). |
| `mungkin_ada` | **Mungkin Ada** | Nama berkas mirip atau hash belum pasti (memerlukan tinjauan). |


### 11.6 Tujuan Penarikan Berkas (`TujuanTarik`)

Field respons/parameter: `destination`

| Nilai Enum (Backend) | Label UI Indonesia | Keterangan |
|---|---|---|
| `knowledge_base` | **Knowledge Base** | Dimasukkan ke basis pengetahuan HERO dan diekstrak metadata/pasal. |
| `unduh_folder` | **Unduh Folder (ZIP)** | Hanya diunduh sebagai berkas terkompresi ZIP tanpa diekstrak ke KB. |


### 11.7 Hasil Penarikan Berkas (`HasilTarik`)

Field respons/parameter: `pull_outcome`

| Nilai Enum (Backend) | Label UI Indonesia | Keterangan |
|---|---|---|
| `berhasil` | **Berhasil** | Berkas berhasil diunduh dan disimpan. |
| `duplikat` | **Duplikat** | Berkas terdeteksi duplikat saat ingest. |
| `gagal` | **Gagal** | Gagal mengunduh atau validasi format gagal. |
| `diunduh` | **Diunduh** | Tersimpan di direktori ekspor untuk ZIP. |


### 11.8 Status Pemrosesan Dokumen KB (`StatusPemrosesan`)

Field respons/parameter: `processing_status`

| Nilai Enum (Backend) | Label UI Indonesia | Keterangan |
|---|---|---|
| `diterima` | **Diterima** | Berkas PDF diterima di sistem, belum diproses. |
| `diproses` | **Diproses** | Teks dan layout sedang diekstrak oleh worker. |
| `perlu_koreksi` | **Perlu Koreksi** | Dokumen membutuhkan verifikasi/koreksi metadata manual oleh kurator. |
| `terindeks` | **Terindeks** | Teks dan metadata telah terindeks untuk pencarian. |
| `gagal` | **Gagal** | Gagal memproses dokumen pada salah satu tahapan pipeline. |
| `ditolak` | **Ditolak** | Dokumen ditolak karena tidak memenuhi kriteria regulasi. |


### 11.9 Status Keberlakuan Regulasi (`StatusKeberlakuan`)

Field respons/parameter: `status_keberlakuan`

| Nilai Enum (Backend) | Label UI Indonesia | Keterangan |
|---|---|---|
| `berlaku` | **Berlaku** | Peraturan sedang berlaku aktif. |
| `diubah` | **Diubah** | Sebagian ketentuan peraturan telah diubah. |
| `dicabut` | **Dicabut** | Peraturan telah dicabut seluruhnya oleh regulasi baru. |
| `tidak_diketahui` | **Tidak Diketahui** | Status keberlakuan belum dapat dipastikan. |


### 11.10 Kategori Kegagalan Ingest (`JenisKegagalan`)

Field respons/parameter: `failure_type`

| Nilai Enum (Backend) | Label UI Indonesia | Keterangan |
|---|---|---|
| `format_tidak_didukung` | **Format Tidak Didukung** | Berkas rusak, terenkripsi, atau bukan PDF valid. |
| `duplikat` | **Duplikat** | Berkas terdeteksi sebagai duplikat. |
| `ekstraksi_gagal` | **Ekstraksi Gagal** | Gagal mengekstrak teks dari berkas. |
| `ocr_gagal` | **OCR Gagal** | Gagal menjalankan OCR pada berkas hasil pemindaian. |
| `metadata_tidak_lengkap` | **Metadata Tidak Lengkap** | Metadata wajib tidak berhasil diperoleh. |
| `sumber_tidak_dapat_diakses` | **Sumber Tidak Dapat Diakses** | Koneksi timeout, 404, atau 403 saat mengunduh sumber. |
| `kesalahan_internal` | **Kesalahan Internal** | Kesalahan internal lainnya pada sistem. |


### 11.11 Status Tindak Lanjut Kegagalan (`StatusTindakLanjut`)

Field respons/parameter: `follow_up_status`

| Nilai Enum (Backend) | Label UI Indonesia | Keterangan |
|---|---|---|
| `belum_ditangani` | **Belum Ditangani** | Kegagalan baru tercatat dan belum ditangani. |
| `diproses_ulang` | **Diproses Ulang** | Proses retry sedang berjalan. |
| `diabaikan` | **Diabaikan** | Kurator memutuskan untuk mengabaikan kegagalan ini. |


### 11.12 Jenis Tugas Ingest (`JenisJobIngest`)

Field respons/parameter: `job_type`

| Nilai Enum (Backend) | Label UI Indonesia | Keterangan |
|---|---|---|
| `scraping` | **Scraping / Pull** | Penarikan berkas dari pemindaian situs web. |
| `unggah_manual` | **Unggah Manual** | Unggah berkas langsung melalui antarmuka web. |
| `sinkron_folder` | **Sinkronisasi Folder** | Pemindaian folder lokal atau OneDrive. |


### 11.13 Status Tugas Ingest (`StatusJobIngest`)

Field respons/parameter: `job_status`

| Nilai Enum (Backend) | Label UI Indonesia | Keterangan |
|---|---|---|
| `antrian` | **Antrian** | Tugas telah dijadwalkan. |
| `berjalan` | **Berjalan** | Tugas sedang aktif diproses. |
| `selesai` | **Selesai** | Tugas telah selesai dengan sukses. |
| `gagal` | **Gagal** | Tugas berhenti karena kesalahan fatal. |


<!-- /AUTO:enum_tables -->

---

## 12. DAFTAR KODE GALAT HTTP & PENANGANAN DI UI

| Kode HTTP | Makna Teknis | Penyebab Umum | Aksi UI yang Disarankan |
|---|---|---|---|
| **400 Bad Request** | Permintaan tidak valid | URL sumber tidak valid, folder di luar akar yang diizinkan | Tampilkan banner galat dengan pesan dari respons. |
| **403 Forbidden** | Akses ditolak | Mengakses PDF non-publik saat mode proteksi aktif | Tampilkan dialog izin akses atau peringatan login. |
| **404 Not Found** | Data tidak ditemukan | ID dokumen, scan, atau sumber tidak ditemukan | Arahkan pengguna kembali ke halaman daftar. |
| **409 Conflict** | Konflik status | Sesi sedang berjalan atau mencoba retry job aktif | Berikan notifikasi bahwa proses sedang berjalan di latar belakang. |
| **413 Payload Too Large** | Berkas melebihi batas | Ukuran unggah PDF melebihi batas (default 100 MB) | Peringatkan pengguna untuk mengunggah berkas lebih kecil. |
| **422 Unprocessable** | Validasi skema gagal | Komponen format nama salah, field wajib kosong | Sorot field formulir yang bersangkutan dengan pesan spesifik. |
| **503 Service Unavailable** | Layanan database/AI sibuk | Koneksi database terputus atau komponen ML offline | Tampilkan pesan coba lagi beberapa saat. |

---

## 13. CATATAN & PERTANYAAN UNTUK FRONTEND

1. **Komponen Penamaan Berulang:** Backend mengizinkan tombol komponen penamaan yang sama diklik lebih dari sekali (misal: `["tahun", "nama", "tahun"]`). Apakah UI telah mendukung representasi chip/badge yang dapat diurutkan secara drag-and-drop?
2. **Karakter Pemisah Penamaan:** Pemisah default adalah spasi `" "`. Pilihan lain adalah `"_"` dan `"-"`. Jika pengguna tidak memilih pemisah, backend otomatis menggunakan spasi.
3. **Pemberitahuan Status Asinkron:** Disarankan agar frontend menggunakan library seperti React Query / SWR dengan konfigurasi `refetchInterval: 2000` saat sesi berada dalam status `memindai` atau `menarik`.
