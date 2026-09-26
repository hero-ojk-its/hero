# Panduan Integrasi API Frontend — Langkah 4 & 5

> **Sasaran:** Personil_D & Tim Frontend  
> **Ruang Lingkup:** Pencarian KB, Buka PDF & Teks, Koreksi Metadata, Antrian Perlu Koreksi, Dashboard Ringkasan, dan Outcome Retry.

---

## 1. Pencarian Knowledge Base (`GET /api/v1/documents/`)

Endpoint `GET /api/v1/documents/` telah diperluas dengan kemampuan full-text search PostgreSQL TSVector, pencocokan nomor regulasi berbasis trigram (`pg_trgm`), filter kategori hierarkis (CTE), dan snippet highlight.

### 1.1 Parameter Query Baru & Kompatibilitas

| Parameter | Tipe | Default | Keterangan |
|---|---|---|---|
| `q` | string | `None` | Kata kunci pencarian (maksimal 200 karakter). Jika kosong/hanya spasi, mengembalikan dokumen tanpa filter teks |
| `mode` | string enum | `phrase` | Mode pencocokan teks:<br>• `phrase`: Kata harus bersebelahan & berurutan (contoh: "sepatu roda")<br>• `all`: Semua kata harus ada, urutan bebas<br>• `web`: Sintaks ala Google (`"kutip"`, `OR`, `-kecuali`) |
| `regulation_number` | string | `None` | Pencocokan nomor regulasi (toleran terhadap variasi `/`, `-`, titik) |
| `regulation_type` | string | `None` | Jenis regulasi (misal: `POJK`, `SEOJK`, `UU`, `PP`) |
| `category_id` | integer | `None` | ID kategori folder KB |
| `include_subcategories` | boolean | `true` | Jika `true`, otomatis mencakup seluruh dokumen di subfolder turunannya |
| `status_keberlakuan` | list[string] | `None` | Filter status regulasi. **Mendukung multi-select** dengan mengulang parameter: `?status_keberlakuan=berlaku&status_keberlakuan=diubah`. Bila tidak dikirim, **dokumen dicabut tetap ikut muncul** |
| `document_role` | string | `None` | `corpus_eksisting` atau `draft_kajian` |
| `access_classification`| string | `None` | `publik` atau `rahasia` |
| `processing_status` | string | `None` | `diterima`, `diproses`, `perlu_koreksi`, `terindeks`, `gagal`, `ditolak` |
| `date_from` | YYYY-MM-DD | `None` | Batas awal `release_date` (inklusif) |
| `date_to` | YYYY-MM-DD | `None` | Batas akhir `release_date` (inklusif) |
| `year` | integer | `None` | Tahun terbit dokumen |
| `sort` | string enum | `relevance` | Pilihan urutan:<br>• `relevance` (default bila `q` terisi)<br>• `release_date_desc` (default bila `q` kosong)<br>• `release_date_asc`<br>• `created_desc`<br>• `title_asc` |
| `skip` | integer | `0` | Offset pagination |
| `limit` | integer | `20` | Ukuran halaman (maksimal 100, jika > 100 otomatis dibatasi ke 100) |

### 1.2 Struktur Respons
Respons tetap mempertahankan key `total` dan `items`, dengan penambahan objek `query` (echo filter aktif) serta field baru pada tiap item:

```json
{
  "total": 1,
  "query": {
    "q": "modal minimum",
    "mode": "phrase",
    "sort": "relevance",
    "regulation_number": null,
    "regulation_type": null,
    "category_id": null,
    "status_keberlakuan": null,
    "year": null,
    "skip": 0,
    "limit": 20
  },
  "items": [
    {
      "id": 10,
      "title": "Kesehatan Bank dan Permodalan",
      "regulation_number": "11/POJK.03/2022",
      "regulation_type": "POJK",
      "release_date": "2022-07-07",
      "category_id": 3,
      "category_path": ["POJK", "2022"],
      "status_keberlakuan": "berlaku",
      "document_role": "corpus_eksisting",
      "access_classification": "publik",
      "processing_status": "terindeks",
      "standardized_filename": "11-POJK.03-2022 Kesehatan Bank dan Permodalan 2022.pdf",
      "file_size_bytes": 524288,
      "source_url": null,
      "is_placed": true,
      "rank": 0.0892,
      "highlight": "...kepatuhan rasio kecukupan <mark>modal</mark> <mark>minimum</mark> bagi bank umum...",
      "pdf_url": "/api/v1/documents/10/pdf",
      "created_at": "2026-09-26T12:00:00Z"
    }
  ]
}
```

---

## 2. Buka PDF Asli & Ekstraksi Teks (US-28′ / S-07)

### 2.1 Buka PDF Asli (`GET /api/v1/documents/{id}/pdf`)
Digunakan untuk tombol **"Buka PDF Asli"** di UI atau iframe/embed preview.
- **Header Response:**
  - `Content-Type: application/pdf`
  - `Content-Disposition: inline; filename="..."; filename*=UTF-8''...`
  - `Cache-Control: private, max-age=300`
- **Opsi Unduh:** Tambahkan `?download=true` untuk memicu unduh file (`Content-Disposition: attachment`).
- **Pengecekan Error:** Jika file fisik tidak ada di disk penyimpanan, mengembalikan status **HTTP 404** dengan pesan:
  `{"detail": "Berkas PDF asli tidak ditemukan di penyimpanan."}`

### 2.2 Baca Potongan Teks (`GET /api/v1/documents/{id}/text`)
Digunakan untuk melihat teks hasil OCR/ekstraksi secara paginated.
- **Query Param:** `offset` (default: 0), `limit` (default: 20000, maks: 100000) karakter.
- **Response `200 OK`:**
```json
{
  "document_id": 10,
  "total_length": 45000,
  "offset": 0,
  "limit": 20000,
  "text": "OTORITAS JASA KEUANGAN...",
  "extraction_method": "surya_ocr",
  "extracted_at": "2026-09-26T12:05:00Z"
}
```

### 2.3 Detail Dokumen Lengkap (`GET /api/v1/documents/{id}`)
Menambahkan metadata ekstraksi:
```json
{
  "id": 10,
  "title": "Kesehatan Bank dan Permodalan",
  "full_text_length": 45000,
  "pdf_url": "/api/v1/documents/10/pdf",
  "text_url": "/api/v1/documents/10/text",
  "extraction_confidence": {
    "title": 0.95,
    "regulation_number": 0.65
  },
  "low_confidence_fields": ["regulation_number"],
  "metadata_corrected_at": null,
  "extracted_at": "2026-09-26T12:05:00Z"
}
```

---

## 3. Koreksi Metadata (US-21 / S-08) (`PATCH /api/v1/documents/{id}/metadata`)

Memungkinkan reviewer/admin memperbaiki metadata regulasi. Jika dokumen belum terindeks atau belum rapi di KB, koreksi ini otomatis memperbarui penamaan baku dan memindahkannya ke folder KB (`kb/{jenis}/{tahun}/`).

- **Body (Semua opsional, minimal 1 field):**
```json
{
  "title": "Peraturan Otoritas Jasa Keuangan Nomor 11 Tahun 2022",
  "regulation_number": "11/POJK.03/2022",
  "regulation_type": "POJK",
  "release_date": "2022-07-07",
  "category_id": 3,
  "access_classification": "publik",
  "document_role": "corpus_eksisting"
}
```
- **Aturan Input:**
  - `title` tidak boleh string kosong atau `null` (HTTP 422).
  - `release_date` tidak boleh melebihi hari ini (HTTP 422).
  - Mengirim `null` secara eksplisit pada `regulation_number`, `regulation_type`, `release_date`, atau `category_id` akan **mengosongkan** field tersebut.
  - Mengirim body `{}` kosong akan mengembalikan HTTP 422.
- **Audit:** Aktivitas ini dicatat di audit log (`UPDATE_METADATA`) dengan diff lengkap field sebelum vs sesudah.

---

## 4. Antrian Dokumen Perlu Koreksi (`GET /api/v1/documents/needs-review`)

Menampilkan daftar dokumen yang membutuhkan intervensi reviewer:
- Dokumen berstatus `processing_status = 'perlu_koreksi'`.
- Dokumen berstatus `terindeks` yang memiliki field keyakinan rendah (`low_confidence_fields` tidak kosong) dan belum pernah dikoreksi manual.

- **Query Param:** `skip` (default: 0), `limit` (default: 20).
- **Response `200 OK`:**
```json
{
  "total": 3,
  "items": [
    {
      "id": 14,
      "title": "Regulasi Draft Ekstraksi OCR",
      "regulation_number": null,
      "regulation_type": "POJK",
      "release_date": "2023-01-10",
      "processing_status": "perlu_koreksi",
      "low_confidence_fields": ["regulation_number"],
      "extraction_confidence": {"title": 0.88, "regulation_number": 0.45},
      "pdf_url": "/api/v1/documents/14/pdf",
      "created_at": "2026-09-26T12:10:00Z"
    }
  ]
}
```

---

## 5. Dashboard Ringkasan (`GET /api/v1/dashboard/summary`)

Menyajikan statistik agregat performa KB, ingest, dan kepatuhan target Fase 1 (≥ 20 dokumen corpus di KB).

- **Response `200 OK`:**
```json
{
  "kb": {
    "corpus_documents": 21,
    "draft_documents": 2,
    "target_fase1": 20,
    "target_met": true,
    "by_status_keberlakuan": {
      "berlaku": 18,
      "diubah": 1,
      "dicabut": 2,
      "tidak_diketahui": 0
    },
    "by_processing_status": {
      "diterima": 0,
      "diproses": 1,
      "perlu_koreksi": 1,
      "terindeks": 21,
      "gagal": 0,
      "ditolak": 0
    },
    "by_regulation_type": [
      {"regulation_type": "POJK", "count": 14},
      {"regulation_type": "SEOJK", "count": 7}
    ],
    "by_year": [
      {"year": 2023, "count": 12},
      {"year": 2022, "count": 9}
    ],
    "placed_documents": 21,
    "inbox_documents": 2
  },
  "ingest": {
    "open_failures": 0,
    "needs_review": 1,
    "recent_jobs": [
      {
        "id": 8,
        "job_type": "unggah_manual",
        "status": "selesai",
        "started_at": "2026-09-26T12:00:00Z",
        "finished_at": "2026-09-26T12:00:05Z",
        "success_count": 5,
        "duplicate_count": 0,
        "failed_count": 0
      }
    ]
  },
  "sources": {
    "total": 3,
    "active": 2
  },
  "generated_at": "2026-09-26T12:30:00Z"
}
```

---

## 6. Penanganan Outcome Baru Retry Kegagalan (`POST /api/v1/ingest/failures/{id}/retry`)

Pada endpoint retry kegagalan:
- Jika kegagalan bertipe pasca-ingest (`ekstraksi_gagal` atau `ocr_gagal`), dokumen tidak di-ingest ulang dari karantina fisik, melainkan langsung di-requeue ke antrean ekstraksi.
- Response mengembalikan `outcome = "requeued"`:
```json
{
  "message": "Dokumen berhasil dimasukkan kembali ke antrean ekstraksi.",
  "outcome": "requeued",
  "failure_id": 5,
  "document_id": 10
}
```
Frontend dapat menampilkan notifikasi bahwa dokumen telah dikembalikan ke antrean pemrosesan worker.
