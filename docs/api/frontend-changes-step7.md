# Panduan Integrasi Frontend — Alur Pindai Situs (Langkah 7)

Dokumen ini menjelaskan alur antarmuka pengguna (UI/UX) dan kontrak API untuk fitur **Alur Pindai Situs Web** (*Scan → Compare → Select → Pull*).

---

## 1. Alur Interaksi Pengguna

Alur kerja pada menu **Ingest → Pindai Situs Web**:

```
[1. Pilih Sumber & Kedalaman] 
           │
           ▼
[2. Mulai Pemindaian: POST /api/v1/scans/]
           │
           ▼ (Polling GET /api/v1/scans/{id})
[3. Status 'siap_dipilih': Tampilkan Ringkasan & Tabel Kandidat]
           │
           ├─ Checkbox 'Baru' (Default: Checked)
           ├─ Checkbox 'Mungkin Ada' (Default: Unchecked, Peringatan)
           └─ Checkbox 'Sudah Ada' (Disabled: Selalu Unchecked)
           │
           ▼
[4. Pilih Aksi: Tarik ke KB  ATAU  Unduh PDF ZIP]
           │
           ▼ (Polling GET /api/v1/scans/{id})
[5. Status 'selesai': Tampilkan Hasil & Tautan Unduh/Kegagalan]
```

---

## 2. Rincian Langkah & Endpoint API

### Langkah 1: Memulai Pemindaian

Pengguna memilih sumber tipe `situs_web`, menentukan kedalaman (`crawl_depth`, 1–5), serta batas halaman maksimal (`max_pages`).

**Request:**
`POST /api/v1/scans/`

```json
{
  "source_id": 6,
  "crawl_depth": 1,
  "max_pages": 50
}
```

*Query param opsional:* `?wait=true` untuk menunggu proses pemindaian selesai secara sinkron (berguna untuk pengujian atau preview cepat).

**Response (202 Accepted / 200 OK):**
```json
{
  "id": 1,
  "source_id": 6,
  "start_url": "https://jdih.esdm.go.id",
  "crawl_depth": 1,
  "mode": "simple_http",
  "crawler_name": null,
  "status": "memindai",
  "cancel_requested": false,
  "pages_visited": 1,
  "candidates_summary": {
    "total": 0,
    "baru": 0,
    "sudah_ada": 0,
    "mungkin_ada": 0,
    "terpilih": 0
  },
  "truncated": false,
  "errors": [],
  "error_message": null,
  "destination": null,
  "pull_job_id": null,
  "pull_progress": null,
  "download_url": null,
  "claimed_at": null,
  "started_at": "2026-09-26T16:12:52.204415Z",
  "scanned_at": null,
  "finished_at": null,
  "created_at": "2026-09-26T16:12:52.122412Z",
  "updated_at": "2026-09-26T16:12:52.122412Z"
}
```

**Error responses:**
- `409 Conflict`: Sesi pemindaian/penarikan aktif sedang berjalan untuk sumber ini.
  ```json
  {
    "detail": {
      "message": "Sesi pindai aktif sedang berjalan untuk sumber ini.",
      "active_scan_id": 1
    }
  }
  ```
- `422 Unprocessable Content`: Sumber bukan `situs_web` atau URL melanggar aturan SSRF (IP lokal/privat).
  ```json
  {
    "detail": "Akses ke host/IP privat '127.0.0.1' diblokir untuk keamanan SSRF."
  }
  ```

---

### Langkah 2: Polling Status Sesi Pemindaian

Lakukan polling berkala (misal tiap 2-3 detik) ke endpoint detail sesi:

**Request:**
`GET /api/v1/scans/{scan_id}`

**Response saat selesai memindai (`status: "siap_dipilih"`):**
```json
{
  "id": 1,
  "source_id": 6,
  "start_url": "https://jdih.esdm.go.id",
  "crawl_depth": 1,
  "mode": "simple_http",
  "crawler_name": null,
  "status": "siap_dipilih",
  "cancel_requested": false,
  "pages_visited": 1,
  "candidates_summary": {
    "total": 12,
    "baru": 10,
    "sudah_ada": 1,
    "mungkin_ada": 1,
    "terpilih": 10
  },
  "truncated": false,
  "errors": [],
  "error_message": null,
  "destination": null,
  "pull_job_id": null,
  "pull_progress": null,
  "download_url": null,
  "claimed_at": null,
  "started_at": "2026-09-26T16:12:52.204415Z",
  "scanned_at": "2026-09-26T16:12:58.986377Z",
  "finished_at": null,
  "created_at": "2026-09-26T16:12:52.122412Z",
  "updated_at": "2026-09-26T16:12:58.986377Z"
}
```

---

### Langkah 3: Mengambil Daftar Kandidat PDF

Tampilkan tabel kandidat dengan pagination dan filter:

**Request:**
`GET /api/v1/scans/{scan_id}/candidates?match_status=baru&page=1&limit=50`

Query parameters yang didukung:
- `match_status`: `baru` | `sudah_ada` | `mungkin_ada`
- `selected`: `true` | `false`
- `pull_outcome`: `success` | `duplicate` | `failed` | `downloaded`
- `q`: Pencarian nama berkas (case-insensitive ILIKE)
- `page`: Nomor halaman (default: 1)
- `limit`: Jumlah per halaman (default: 50, maks 200)

**Response:**
```json
{
  "items": [
    {
      "id": 1,
      "scan_id": 1,
      "url": "https://jdih.esdm.go.id/storage/document/2026kmesdm365k.pdf",
      "filename": "2026kmesdm365k.pdf",
      "size_bytes": 879298,
      "found_on_page": "https://jdih.esdm.go.id",
      "depth": 1,
      "match_status": "baru",
      "match_reason": null,
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
      "url": "https://jdih.esdm.go.id/storage/document/POJK_03_2022.pdf",
      "filename": "POJK_03_2022.pdf",
      "size_bytes": 1048576,
      "found_on_page": "https://jdih.esdm.go.id",
      "depth": 1,
      "match_status": "sudah_ada",
      "match_reason": "url_sama",
      "match_document": {
        "id": 12,
        "title": "Peraturan Otoritas Jasa Keuangan Nomor 11/POJK.03/2022",
        "regulation_number": "11/POJK.03/2022"
      },
      "selected": false,
      "pull_outcome": null,
      "document_id": null,
      "failure_id": null,
      "export_path": null,
      "message": null
    }
  ],
  "total": 2,
  "page": 1,
  "limit": 50,
  "total_pages": 1
}
```

---

### Langkah 4: Memperbarui Pilihan / Centang

Pengguna dapat memilih/membatalkan kandidat:

**Request:**
`PATCH /api/v1/scans/{scan_id}/selection`

Tiga jenis `action`:
1. `set`: Mengubah status pilihan kandidat tertentu berdasarkan `candidate_ids`.
   ```json
   {
     "action": "set",
     "candidate_ids": [1, 3, 5],
     "selected": true
   }
   ```
2. `select_all_new`: Memilih seluruh kandidat berstatus `baru`.
   ```json
   {
     "action": "select_all_new"
   }
   ```
3. `select_none`: Mengosongkan seluruh centang pilihan.
   ```json
   {
     "action": "select_none"
   }
   ```

**Response:**
```json
{
  "scan_id": 1,
  "summary": {
    "total": 12,
    "baru": 10,
    "sudah_ada": 1,
    "mungkin_ada": 1,
    "terpilih": 3
  },
  "rejected_ids": [
    {
      "id": 2,
      "reason": "Kandidat dengan status 'sudah_ada' tidak dapat dipilih."
    }
  ]
}
```

---

### Langkah 5: Memulai Penarikan (*Pull*)

Pengguna menekan tombol:
- **"Masukkan ke Knowledge Base"** (`destination: "knowledge_base"`)
- **"Unduh PDF (ZIP)"** (`destination: "unduh_folder"`)

**Request:**
`POST /api/v1/scans/{scan_id}/pull`

```json
{
  "destination": "knowledge_base"
}
```

*Query param opsional:* `?wait=true` untuk menunggu proses selesai.

**Response (202 Accepted / 200 OK):**
```json
{
  "id": 1,
  "status": "menarik",
  "destination": "knowledge_base",
  "pull_job_id": 61,
  "pull_progress": {
    "job_id": 61,
    "status": "memproses",
    "processed_count": 1,
    "total_found": 3,
    "progress_percent": 33.3
  }
}
```

---

### Langkah 6: Mengunduh Berkas ZIP (Jika Tujuan `unduh_folder`)

Jika penarikan selesai dengan tujuan `unduh_folder`, endpoint `GET /api/v1/scans/{scan_id}/download` akan mengalirkan berkas ZIP:

**Request:**
`GET /api/v1/scans/{scan_id}/download`

**Response:**
- Header `Content-Type: application/zip`
- Header `Content-Disposition: attachment; filename="hero-scan-1.zip"`
- Streaming zip stream.

---

### Langkah 7: Pembatalan Sesi

Pengguna dapat membatalkan pemindaian atau penarikan yang sedang berjalan:

**Request:**
`POST /api/v1/scans/{scan_id}/cancel`

**Response (200 OK):**
```json
{
  "message": "Permintaan pembatalan sesi pindai telah dicatat.",
  "status": "dibatalkan"
}
```
