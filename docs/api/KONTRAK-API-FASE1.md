# KONTRAK API HERO BACKEND — FASE 1 (MVP)

> **Untuk Tim Frontend (Personil_D)**  
> **Status:** Resmi Disepakati (Step 9 / Issue #91 AI-T12 & #90 US-20c)  
> **Basis Implementasi:** FastAPI · PostgreSQL 15.4 · SQLAlchemy 2.x  
> **Artefak Pendamping:**
> - [Koleksi Request Siap Eksekusi (REST Client / VS Code)](file:///docs/api/hero-fase1.http)
> - [Snapshot Skema OpenAPI JSON untuk Type Generator](file:///docs/api/openapi-fase1.json)
> - [Catatan Perubahan Frontend Step 9](file:///docs/api/frontend-changes-step9.md)

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
9. [Alur 8: Kurasi & Koreksi Metadata serta Penanganan Gagal](#9-alur-8-kurasi--koreksi-metadata-serta-penanganan-gagal)
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

1. **Galat Logika Bisnis Aplikasi (400, 403, 404, 409, 503):**
   `detail` berupa **string pesan tunggal**:
<!-- AUTO:error_404_sample -->
```json
{
  "detail": "Dokumen tidak ditemukan"
}
```
<!-- /AUTO:error_404_sample -->

2. **Galat Validasi Input Schema / Pydantic (422 Unprocessable Entity):**
   `detail` berupa **array of objects**:
<!-- AUTO:error_422_sample -->
```json
{
  "detail": "Komponen naming_format tidak valid: 'warna_invalid'. Komponen yang didukung: 'nama', 'nomor', 'tahun', 'jenis', 'bidang'."
}
```
<!-- /AUTO:error_422_sample -->

> **Saran UI:**  
> Buat interceptor response pada Axios / Fetch:  
> `const errorMsg = typeof err.response.data.detail === 'string' ? err.response.data.detail : err.response.data.detail.map(e => e.msg).join(', ');`

### 1.4 Status Autentikasi (Fase 1)
- Pada Fase 1, `AUTH_ENABLED=false`. Frontend **tidak perlu mengirimkan header Authorization/Bearer token**.
- Seluruh endpoint publik dapat diakses langsung.

### 1.5 CORS (Cross-Origin Resource Sharing)
- Backend mengizinkan origin frontend: `http://localhost:3000` dan `http://127.0.0.1:3000`.
- Jika pengujian frontend berjalan di port lain, pastikan menambahkan port tersebut di konfigurasi `.env` (`CORS_ORIGINS`).

### 1.6 Pola Operasi Panjang (Asynchronous Polling)
Operasi berat seperti pemindaian situs web (`POST /scans/`), penarikan dokumen (`POST /scans/{id}/pull`), dan sinkronisasi folder (`POST /scraping-sources/{id}/run`):
1. **Default (`wait=false`):** Backend merespons langsung dengan status **`202 Accepted`** berisi `scan_id` atau `job_id` dan status `"antrian"`.
2. **Polling UI:** Frontend melakukan polling GET (`GET /api/v1/scans/{id}` atau `GET /api/v1/jobs/{id}`) tiap **2 detik**.
3. **Status Final:** Polling berhenti saat status mencapai salah satu nilai final:
   - `selesai` (sukses)
   - `gagal` (terjadi kesalahan, lihat `error_message`)
   - `dibatalkan` (dibatalkan oleh pengguna)

---

## 2. ALUR 1: TAMBAH & KELOLA SUMBER DOKUMEN

### 2.1 Menambah Sumber Situs Web (JDIH OJK)
- **Method & Path:** `POST /api/v1/scraping-sources/`
- **Request Body:**
<!-- AUTO:source_create_web_request -->
```json
{
  "name": "JDIH OJK Pusat",
  "url": "https://jdih.ojk.go.id",
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
  "name": "JDIH OJK Pusat",
  "url": "https://jdih.ojk.go.id",
  "address": "https://jdih.ojk.go.id",
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

### 2.2 Menambah Sumber Folder Lokal
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

### 2.3 Daftar Semua Sumber
- **Method & Path:** `GET /api/v1/scraping-sources/`
- **Query Params:** `is_active` (boolean, opsional), `source_type` (JenisSumber, opsional).
- **Respons (200 OK):**
<!-- AUTO:source_list_response -->
```json
[
  {
    "id": 1,
    "name": "JDIH OJK Pusat",
    "url": "https://jdih.ojk.go.id",
    "address": "https://jdih.ojk.go.id",
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

### 3.1 Memulai Pemindaian Situs
- **Method & Path:** `POST /api/v1/scans/`
- **Query Param:** `wait=false` (default) → 202 Accepted, `wait=true` → 200 OK setelah selesai.
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

### 3.2 Detail Status Sesi Pemindaian
- **Method & Path:** `GET /api/v1/scans/{scan_id}`
- **Respons (200 OK):**
<!-- AUTO:scan_detail_response -->
```json
{
  "id": 1,
  "source_id": 1,
  "start_url": "https://jdih.ojk.go.id",
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

### 3.3 Menampilkan Daftar Kandidat PDF
- **Method & Path:** `GET /api/v1/scans/{scan_id}/candidates`
- **Query Params:** `match_status` (`baru` | `sudah_ada` | `mungkin_ada`), `selected` (boolean), `pull_outcome`, `q` (filter nama berkas), `skip`, `limit`.
- **Respons (200 OK):**
<!-- AUTO:scan_candidates_response -->
```json
{
  "items": [
    {
      "id": 1,
      "scan_id": 1,
      "url": "https://jdih.ojk.go.id/docs/POJK_16_2026.pdf",
      "filename": "POJK_16_2026.pdf",
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
      "url": "https://jdih.ojk.go.id/docs/SEOJK_05_2025.pdf",
      "filename": "SEOJK_05_2025.pdf",
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

### 3.4 Memperbarui Centang Pilihan (Selection)
- **Method & Path:** `PATCH /api/v1/scans/{scan_id}/selection`
- **Aksi Valid:**
  - `select_all_new`: Centang semua kandidat berstatus `baru`.
  - `select_none`: Kosongkan seluruh centang.
  - `set`: Atur centang kandidat tertentu (`candidate_ids: [1, 2]`, `selected: true/false`).
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

### 4.1 Mendapatkan Komponen Penamaan Tersedia
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

### 4.2 Pratinjau Nama Berkas Dinamis (Live Preview)
- **Method & Path:** `POST /api/v1/naming/preview`
- **Contoh 1 (Sample Bawaan Sistem):**
<!-- AUTO:naming_preview_default_response -->
```json
{
  "filename": "Penyelenggaraan Bursa Mineral dan Komoditas Strategis POJK 2026.pdf",
  "missing_components": []
}
```
<!-- /AUTO:naming_preview_default_response -->
- **Contoh 2 (Kustom Sample):**
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

### 5.1 Tarik ke Knowledge Base (KB)
- **Method & Path:** `POST /api/v1/scans/{scan_id}/pull`
- **Body:** `destination: "knowledge_base"`, `naming_format` (array), `naming_separator` (opsional).
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

### 5.2 Tarik ke Folder Ekspor & Unduh ZIP
- **Method & Path:** `POST /api/v1/scans/{scan_id}/pull`
- **Body:** `destination: "unduh_folder"`, `naming_format` (array), `naming_separator` (opsional).
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

- **Unduh Berkas ZIP Setelah Selesai:**
  - `GET /api/v1/scans/{scan_id}/download` → Menghasilkan stream berkas `scan_{id}_export.zip` dengan nama berkas di dalam ZIP mengikuti format penamaan yang dipilih.

---

## 6. ALUR 5: UNGGAH BERKAS MANUAL & SINKRONISASI FOLDER LOKAL

### 6.1 Unggah Manual Banyak Berkas (Multipart/form-data)
- **Method & Path:** `POST /api/v1/ingest/upload-pdf`
- **Header:** `Content-Type: multipart/form-data`
- **Form Fields:**
  - `files`: Berkas-berkas PDF (bisa banyak berkas sekaligus).
  - `access_classification`: `publik` atau `non_publik` (default: `publik`).
  - `document_role`: `corpus_eksisting` atau `referensi_tambahan`.
  - `naming_format`: String dipisah koma (contoh: `"nama,jenis,tahun,bidang"`).
  - `naming_separator`: `" "` | `"_"` | `"-"`.
  - `bidang`: String sektor/bidang regulasi (contoh: `"Perbankan"`).
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
      "file_size_bytes": 485,
      "file_hash": "0f35783570e8a52fd9a66420f561727be83b22daa4d41bb9aae9f3740cbfa6cc",
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

### 6.2 Eksekusi Sinkronisasi Folder Lokal
- **Method & Path:** `POST /api/v1/scraping-sources/{source_id}/run`
- **Body (Opsional):** `naming_format` (array), `naming_separator` (string).
- **Respons (202 Accepted / 200 OK):**
<!-- AUTO:source_run_response -->
```json
{
  "job_id": 4,
  "status": "antrian",
  "message": "Job sinkronisasi folder ID 4 telah dijadwalkan."
}
```
<!-- /AUTO:source_run_response -->

### 6.3 Daftar Berkas Sumber Lokal
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

### 7.1 Daftar & Filter Dokumen KB
- **Method & Path:** `GET /api/v1/documents/`
- **Query Params:**
  - `skip`, `limit`
  - `bidang` (filter sektor, contoh: `Perbankan`, `Pasar Modal`, `BMKS`)
  - `category_id` (filter kategori)
  - `regulation_type` (filter jenis regulasi)
  - `year` (filter tahun)
  - `status_keberlakuan` (`berlaku`, `dicabut`, `diubah`, dll.)
  - `processing_status` (`tersimpan`, `diekstraksi`, `terindeks`, `perlu_koreksi`)
  - `access_classification` (`publik`, `non_publik`)
- **Respons (200 OK):**
<!-- AUTO:documents_list_response -->
```json
{
  "total": 1,
  "items": [
    {
      "id": 1,
      "title": "Penyelenggaraan Usaha Bank Umum",
      "regulation_number": "POJK 10/2026",
      "regulation_type": "Peraturan Otoritas Jasa Keuangan",
      "release_date": "2026-03-15",
      "bidang": "Perbankan",
      "access_classification": "publik",
      "document_role": "corpus_eksisting",
      "category_id": 1,
      "category_path": [
        "POJK"
      ],
      "status_keberlakuan": "berlaku",
      "processing_status": "terindeks",
      "extraction_method": null,
      "file_path_pdf": "pdf/_inbox/POJK 10 Tahun 2026 Bank Umum_NA_NA_Perbankan__0f357835-1.pdf",
      "file_hash": "0f35783570e8a52fd9a66420f561727be83b22daa4d41bb9aae9f3740cbfa6cc",
      "file_size_bytes": 485,
      "standardized_filename": "POJK 10 Tahun 2026 Bank Umum_NA_NA_Perbankan.pdf",
      "source_url": null,
      "is_placed": false,
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

### 7.2 Pencarian Cerdas Regulasi (Full-Text & Semantik)
- **Method & Path:** `GET /api/v1/documents/search`
- **Query Params:**
  - `q`: Kata kunci / frasa hukum (contoh: `modal inti bank umum`).
  - `mode`: `phrase` (pencarian frasa tepat) | `all` (semua kata) | `web` (pencarian berbasis web/boolean).
  - `bidang`: Filter sektor regulasi.
  - `highlight`: `true` untuk menyertakan cuplikan teks dengan tag `<mark>`.
- **Respons (200 OK):**
<!-- AUTO:documents_search_response -->
```json
{
  "detail": [
    {
      "type": "int_parsing",
      "loc": [
        "path",
        "document_id"
      ],
      "msg": "Input should be a valid integer, unable to parse string as an integer",
      "input": "search"
    }
  ]
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
  "regulation_number": "POJK 10/2026",
  "regulation_type": "Peraturan Otoritas Jasa Keuangan",
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
  "file_path_pdf": "pdf/_inbox/POJK 10 Tahun 2026 Bank Umum_NA_NA_Perbankan__0f357835-1.pdf",
  "standardized_filename": "POJK 10 Tahun 2026 Bank Umum_NA_NA_Perbankan.pdf",
  "access_classification": "publik",
  "document_role": "corpus_eksisting",
  "status_keberlakuan": "berlaku",
  "processing_status": "terindeks",
  "extraction_method": null,
  "extraction_engine": null,
  "category_id": 1,
  "category_path": [
    "POJK"
  ],
  "is_placed": false,
  "job_id": 3,
  "pdf_url": "/api/v1/documents/1/pdf",
  "text_url": "/api/v1/documents/1/text",
  "full_text_length": 0,
  "extraction_confidence": null,
  "low_confidence_fields": [],
  "metadata_corrected_at": null,
  "extracted_at": null,
  "created_at": "2026-10-01T10:00:00Z",
  "updated_at": "2026-10-01T10:00:00Z",
  "articles": [
    {
      "id": 1,
      "level": "pasal",
      "chapter_title": "BAB I KETENTUAN UMUM",
      "article_number": "Pasal 1",
      "content_text": "Dalam Peraturan Otoritas Jasa Keuangan ini yang dimaksud dengan Bank Umum adalah...",
      "order_index": 1
    },
    {
      "id": 2,
      "level": "pasal",
      "chapter_title": "BAB II MODAL INTI",
      "article_number": "Pasal 2",
      "content_text": "Modal inti minimum bagi Bank Umum ditetapkan sebesar Rp3.000.000.000.000.",
      "order_index": 2
    }
  ],
  "legal_references": []
}
```
<!-- /AUTO:document_detail_response -->

### 8.2 Membaca Teks Mentah Dokumen
- **Method & Path:** `GET /api/v1/documents/{document_id}/text`
- **Query Params:** `offset` (karakter awal, default 0), `limit` (panjang karakter, default 10000).
- **Respons (200 OK):**
<!-- AUTO:document_text_response -->
```json
{
  "document_id": 1,
  "total_length": 0,
  "offset": 0,
  "limit": 20000,
  "text": "",
  "extraction_method": null,
  "extraction_engine": null,
  "extracted_at": null
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

## 9. ALUR 8: KURASI & KOREKSI METADATA SERTA PENANGANAN GAGAL

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
  "regulation_type": "Peraturan Otoritas Jasa Keuangan",
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
  "file_path_pdf": "kb/POJK/Penyelenggaraan Usaha Bank Umum Terkoreksi_POJK_2026_Perbankan-3.pdf",
  "standardized_filename": "Penyelenggaraan Usaha Bank Umum Terkoreksi_POJK_2026_Perbankan-3.pdf",
  "access_classification": "publik",
  "document_role": "corpus_eksisting",
  "status_keberlakuan": "berlaku",
  "processing_status": "terindeks",
  "extraction_method": null,
  "extraction_engine": null,
  "category_id": 1,
  "category_path": [
    "POJK"
  ],
  "is_placed": true,
  "job_id": 3,
  "pdf_url": "/api/v1/documents/1/pdf",
  "text_url": "/api/v1/documents/1/text",
  "full_text_length": 0,
  "extraction_confidence": null,
  "low_confidence_fields": [],
  "metadata_corrected_at": "2026-10-01T10:00:00Z",
  "extracted_at": null,
  "created_at": "2026-10-01T10:00:00Z",
  "updated_at": "2026-10-01T10:00:00Z",
  "articles": [
    {
      "id": 1,
      "level": "pasal",
      "chapter_title": "BAB I KETENTUAN UMUM",
      "article_number": "Pasal 1",
      "content_text": "Dalam Peraturan Otoritas Jasa Keuangan ini yang dimaksud dengan Bank Umum adalah...",
      "order_index": 1
    },
    {
      "id": 2,
      "level": "pasal",
      "chapter_title": "BAB II MODAL INTI",
      "article_number": "Pasal 2",
      "content_text": "Modal inti minimum bagi Bank Umum ditetapkan sebesar Rp3.000.000.000.000.",
      "order_index": 2
    }
  ],
  "legal_references": [],
  "changed_fields": [
    "title",
    "regulation_number"
  ],
  "placement": {
    "document_id": 1,
    "placed": true,
    "reason": "ditempatkan",
    "old_path": "pdf/_inbox/POJK 10 Tahun 2026 Bank Umum_NA_NA_Perbankan__0f357835-1.pdf",
    "new_path": "kb/POJK/Penyelenggaraan Usaha Bank Umum Terkoreksi_POJK_2026_Perbankan-3.pdf",
    "category_id": 1,
    "category_path": [
      "POJK"
    ]
  }
}
```
<!-- /AUTO:document_patch_metadata_response -->

### 9.2 Daftar Antrian Gagal (Ingest Failures)
- **Method & Path:** `GET /api/v1/failures/`
- **Respons (200 OK):**
<!-- AUTO:failures_list_response -->
```json
{
  "detail": "Not Found"
}
```
<!-- /AUTO:failures_list_response -->

### 9.3 Mencoba Ulang (Retry) Berkas Gagal
- **Method & Path:** `POST /api/v1/failures/{failure_id}/retry`
- **Respons (200 OK):**
<!-- AUTO:failure_retry_response -->
```json
{
  "detail": "Not Found"
}
```
<!-- /AUTO:failure_retry_response -->

### 9.4 Mengabaikan (Ignore) Berkas Gagal
- **Method & Path:** `POST /api/v1/failures/{failure_id}/ignore`
- **Respons (200 OK):**
<!-- AUTO:failure_ignore_response -->
```json
{
  "detail": "Not Found"
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
    "corpus_documents": 1,
    "draft_documents": 0,
    "target_fase1": 20,
    "target_met": false,
    "by_status_keberlakuan": {
      "berlaku": 1,
      "diubah": 0,
      "dicabut": 0,
      "tidak_diketahui": 0
    },
    "by_processing_status": {
      "diterima": 0,
      "diproses": 0,
      "perlu_koreksi": 0,
      "terindeks": 1,
      "gagal": 0,
      "ditolak": 0
    },
    "by_regulation_type": [
      {
        "regulation_type": "Peraturan Otoritas Jasa Keuangan",
        "label": "Peraturan Otoritas Jasa Keuangan",
        "count": 1
      }
    ],
    "by_year": [
      {
        "year": 2026,
        "label": "2026",
        "count": 1
      }
    ],
    "placed_documents": 1,
    "inbox_documents": 0
  },
  "ingest": {
    "open_failures": 1,
    "needs_review": 0,
    "active_scans": 1,
    "recent_jobs": [
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
      },
      {
        "id": 1,
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
| `situs_web` | **Situs Web** | Situs eksternal (misal: JDIH OJK) untuk perayapan berkas. |
| `folder_lokal` | **Folder Lokal** | Direktori penyimpanan lokal di peladen. |
| `onedrive_public` | **OneDrive Publik** | Tautan folder publik Microsoft OneDrive. |


### 11.9 Klasifikasi Akses Dokumen (`KlasifikasiAkses`)

Field respons/parameter: `access_classification`

| Nilai Enum (Backend) | Label UI Indonesia | Keterangan |
|---|---|---|
| `publik` | **Publik** | Dapat diakses oleh publik tanpa batasan login. |
| `non_publik` | **Non-Publik** | Dokumen internal atau rahasia yang memerlukan autentikasi. |


### 11.16 Peran Dokumen (`PeranDokumen`)

Field respons/parameter: `document_role`

| Nilai Enum (Backend) | Label UI Indonesia | Keterangan |
|---|---|---|
| `corpus_eksisting` | **Corpus Eksisting** | Dokumen regulasi induk/utama dalam basis pengetahuan. |
| `draft_kajian` | **Draft Kajian** | Dokumen pendukung atau draft rancangan kajian regulasi. |


### 11.23 Status Sesi Pemindaian (`StatusPindai`)

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


### 11.35 Status Kecocokan Kandidat (`StatusKandidat`)

Field respons/parameter: `match_status`

| Nilai Enum (Backend) | Label UI Indonesia | Keterangan |
|---|---|---|
| `baru` | **Baru** | Berkas belum pernah ada di sistem HERO (default dicentang). |
| `sudah_ada` | **Sudah Ada** | Berkas persis sama sudah ada di Knowledge Base (tidak dapat ditarik ulang). |
| `mungkin_ada` | **Mungkin Ada** | Nama berkas mirip atau hash belum pasti (memerlukan tinjauan). |


### 11.43 Tujuan Penarikan Berkas (`TujuanTarik`)

Field respons/parameter: `destination`

| Nilai Enum (Backend) | Label UI Indonesia | Keterangan |
|---|---|---|
| `knowledge_base` | **Knowledge Base** | Dimasukkan ke basis pengetahuan HERO dan diekstrak metadata/pasal. |
| `unduh_folder` | **Unduh Folder (ZIP)** | Hanya diunduh sebagai berkas terkompresi ZIP tanpa diekstrak ke KB. |


### 11.50 Hasil Penarikan Berkas (`HasilTarik`)

Field respons/parameter: `pull_outcome`

| Nilai Enum (Backend) | Label UI Indonesia | Keterangan |
|---|---|---|
| `berhasil` | **Berhasil** | Berkas berhasil diunduh dan disimpan. |
| `duplikat` | **Duplikat** | Berkas terdeteksi duplikat saat ingest. |
| `gagal` | **Gagal** | Gagal mengunduh atau validasi format gagal. |
| `diunduh` | **Diunduh** | Tersimpan di direktori ekspor untuk ZIP. |


### 11.59 Status Pemrosesan Dokumen KB (`StatusPemrosesan`)

Field respons/parameter: `processing_status`

| Nilai Enum (Backend) | Label UI Indonesia | Keterangan |
|---|---|---|
| `diterima` | **Diterima** | Berkas PDF diterima di sistem, belum diproses. |
| `diproses` | **Diproses** | Teks dan layout sedang diekstrak oleh worker. |
| `perlu_koreksi` | **Perlu Koreksi** | Dokumen membutuhkan verifikasi/koreksi metadata manual oleh kurator. |
| `terindeks` | **Terindeks** | Teks dan metadata telah terindeks untuk pencarian. |
| `gagal` | **Gagal** | Gagal memproses dokumen pada salah satu tahapan pipeline. |
| `ditolak` | **Ditolak** | Dokumen ditolak karena tidak memenuhi kriteria regulasi. |


### 11.70 Status Keberlakuan Regulasi (`StatusKeberlakuan`)

Field respons/parameter: `status_keberlakuan`

| Nilai Enum (Backend) | Label UI Indonesia | Keterangan |
|---|---|---|
| `berlaku` | **Berlaku** | Peraturan sedang berlaku aktif. |
| `diubah` | **Diubah** | Sebagian ketentuan peraturan telah diubah. |
| `dicabut` | **Dicabut** | Peraturan telah dicabut seluruhnya oleh regulasi baru. |
| `tidak_diketahui` | **Tidak Diketahui** | Status keberlakuan belum dapat dipastikan. |


### 11.79 Kategori Kegagalan Ingest (`JenisKegagalan`)

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


### 11.91 Status Tindak Lanjut Kegagalan (`StatusTindakLanjut`)

Field respons/parameter: `follow_up_status`

| Nilai Enum (Backend) | Label UI Indonesia | Keterangan |
|---|---|---|
| `belum_ditangani` | **Belum Ditangani** | Kegagalan baru tercatat dan belum ditangani. |
| `diproses_ulang` | **Diproses Ulang** | Proses retry sedang berjalan. |
| `diabaikan` | **Diabaikan** | Kurator memutuskan untuk mengabaikan kegagalan ini. |


### 11.99 Jenis Tugas Ingest (`JenisJobIngest`)

Field respons/parameter: `job_type`

| Nilai Enum (Backend) | Label UI Indonesia | Keterangan |
|---|---|---|
| `scraping` | **Scraping / Pull** | Penarikan berkas dari pemindaian situs web. |
| `unggah_manual` | **Unggah Manual** | Unggah berkas langsung melalui antarmuka web. |
| `sinkron_folder` | **Sinkronisasi Folder** | Pemindaian folder lokal atau OneDrive. |


### 11.107 Status Tugas Ingest (`StatusJobIngest`)

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
| **413 Payload Too Large** | Berkas melebihi batas | Ukuran unggah PDF melebihi batas (default 50 MB) | Peringatkan pengguna untuk mengunggah berkas lebih kecil. |
| **422 Unprocessable** | Validasi skema gagal | Komponen format nama salah, field wajib kosong | Sorot field formulir yang bersangkutan dengan pesan spesifik. |
| **503 Service Unavailable** | Layanan database/AI sibuk | Koneksi database terputus atau komponen ML offline | Tampilkan pesan coba lagi beberapa saat. |

---

## 13. CATATAN & PERTANYAAN UNTUK FRONTEND

1. **Komponen Penamaan Berulang:** Backend mengizinkan tombol komponen penamaan yang sama diklik lebih dari sekali (misal: `["tahun", "nama", "tahun"]`). Apakah UI telah mendukung representasi chip/badge yang dapat diurutkan secara drag-and-drop?
2. **Karakter Pemisah Penamaan:** Pemisah default adalah spasi `" "`. Pilihan lain adalah `"_"` dan `"-"`. Jika pengguna tidak memilih pemisah, backend otomatis menggunakan spasi.
3. **Pemberitahuan Status Asinkron:** Disarankan agar frontend menggunakan library seperti React Query / SWR dengan konfigurasi `refetchInterval: 2000` saat sesi berada dalam status `memindai` atau `menarik`.
