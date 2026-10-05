# Panduan Perubahan API Frontend — Langkah 6: Sumber Folder Lokal

Dokumen ini menjelaskan perubahan kontrak API, penambahan field sumber dokumen, endpoint eksekusi sinkronisasi, dan integrasi progress bar untuk tim Frontend HERO.

---

## 1. Perubahan Model Sumber Dokumen (`/api/v1/scraping-sources`)

Tabel dan endpoint sumber dokumen kini mendukung 3 jenis sumber: `situs_web`, `folder_lokal`, dan `onedrive_public`.

### 1.1 Field Objek `ScrapingSource`

| Field | Tipe | Deskripsi / Nilai |
|---|---|---|
| `id` | `number` | ID unik sumber |
| `name` | `string` | Nama label sumber (contoh: "Direktori Regulasi OJK 2023") |
| `url` | `string` | Alamat URL situs atau jalur folder lokal pada server |
| `address` | `string` | **Alias kompatibel untuk `url`** (selalu bernilai sama dengan `url`) |
| `source_type` | `string` | Enum: `'situs_web'` \| `'folder_lokal'` \| `'onedrive_public'` (default: `'situs_web'`) |
| `crawl_depth` | `number \| null` | Kedalaman crawling (1–5) khusus untuk `'situs_web'` (default: 1); bernilai `null` untuk folder |
| `recursive` | `boolean` | Memindai subdirektori secara rekursif (khusus folder, default: `true`) |
| `default_access_classification` | `string` | Enum: `'publik'` \| `'non_publik'`. Default `'publik'` untuk situs web, `'non_publik'` untuk folder |
| `default_document_role` | `string` | Enum: `'corpus_eksisting'` \| `'draft_kajian'` (default: `'corpus_eksisting'`) |
| `is_active` | `boolean` | Status aktif/non-aktif sumber |
| `last_run_at` | `string (ISO) \| null` | Waktu terakhir eksekusi dijalankan |
| `last_run_status` | `string \| null` | Status eksekusi terakhir: `'selesai'` \| `'gagal'` \| `'berjalan'` |
| `last_run_message` | `string \| null` | Pesan atau ringkasan hasil eksekusi terakhir (contoh: `"Ditemukan: 5, Berhasil: 5, Duplikat: 0, Dilewati: 0, Gagal: 0"`) |
| `last_job_id` | `number \| null` | ID job ingest yang mengeksekusi sumber ini |

### 1.2 Contoh Request Tambah Sumber Baru (`POST /api/v1/scraping-sources/`)

```json
// Mendaftarkan Folder Lokal
{
  "name": "Direktori Regulasi Perbankan OJK",
  "url": "/app/sources/demo_ojk_peraturan",
  "source_type": "folder_lokal",
  "recursive": true,
  "default_access_classification": "publik",
  "default_document_role": "corpus_eksisting"
}
```

---

## 2. Eksekusi Sinkronisasi Sumber (`POST /api/v1/scraping-sources/{id}/run`)

Endpoint untuk memicu pemindaian dan penarikan dokumen dari sumber.

### 2.1 Mode Asinkron (Default untuk UI)
- **Request:** `POST /api/v1/scraping-sources/{id}/run`
- **Response:** `202 Accepted`
```json
{
  "job_id": 45,
  "status": "antrian",
  "message": "Job sinkronisasi folder ID 45 telah dijadwalkan."
}
```

### 2.2 Mode Sinkron (`?wait=true`)
- **Request:** `POST /api/v1/scraping-sources/{id}/run?wait=true`
- **Response:** `200 OK`
```json
{
  "message": "Eksekusi sumber 'Direktori Regulasi Perbankan OJK' selesai dengan status 'selesai'.",
  "job_id": 45,
  "job_status": "selesai",
  "total_found": 5,
  "success_count": 5,
  "duplicate_count": 0,
  "skipped_count": 0,
  "failed_count": 0,
  "last_run_message": "Ditemukan: 5, Berhasil: 5, Duplikat: 0, Dilewati: 0, Gagal: 0"
}
```

### 2.3 Penanganan Error Khusus
- **`409 Conflict` (Situs Web):**
  `"Situs web dijalankan melalui alur pindai (scan) — tersedia pada Langkah 7."`
- **`409 Conflict` (Job Sedang Berjalan):**
  `"Sumber sedang diproses oleh job ID 45."`
- **`409 Conflict` (Sumber Nonaktif):**
  `"Sumber nonaktif."`
- **`422 Unprocessable Content` (OneDrive):**
  `"Konektor OneDrive langsung belum tersedia pada Fase 1. Sinkronkan folder OneDrive ke folder lokal lalu daftarkan sebagai Folder Lokal."`

---

## 3. Polling Progres Job untuk Progress Bar

Saat pengguna menjalankan sinkronisasi sumber di UI, gunakan `job_id` yang diterima dari respons `202` untuk melakukan polling status ke `GET /api/v1/ingest/jobs/{job_id}` setiap 1–2 detik.

### Response `GET /api/v1/ingest/jobs/{job_id}`:
```json
{
  "id": 45,
  "job_type": "sinkron_folder",
  "source_ref": "Direktori Regulasi Perbankan OJK",
  "source_id": 2,
  "source": {
    "id": 2,
    "name": "Direktori Regulasi Perbankan OJK",
    "source_type": "folder_lokal"
  },
  "status": "berjalan",
  "started_at": "2026-09-26T15:02:44.170015Z",
  "finished_at": null,
  "duration_seconds": null,
  "total_found": 100,
  "processed_count": 45,
  "skipped_count": 10,
  "progress_percent": 45.0,
  "success_count": 30,
  "duplicate_count": 5,
  "failed_count": 0,
  "documents": [...],
  "failures": [...]
}
```

**Panduan UI Progress Bar:**
- Gunakan field `progress_percent` (0.0 s/d 100.0) untuk mengisi progress bar.
- Jika `progress_percent === null`, tampilkan animasi spinner / indeterminate bar.
- Hentikan polling saat `status === 'selesai'` atau `status === 'gagal'`.

---

## 4. Daftar Berkas Terindeks per Sumber (`GET /api/v1/scraping-sources/{id}/files`)

Endpoint untuk menampilkan tabel riwayat berkas yang pernah dipindai pada folder/sumber tersebut.

- **Request:** `GET /api/v1/scraping-sources/{id}/files?skip=0&limit=50&last_outcome=success`
- **Response:** `200 OK`
```json
{
  "total": 5,
  "items": [
    {
      "id": 1,
      "source_id": 2,
      "relative_path": "POJK_11_2022_Penyelenggaraan_Teknologi_Informasi.pdf",
      "size_bytes": 1231,
      "mtime": "2026-09-26T15:02:43.010608Z",
      "file_hash": "84dca65548a6ef66af581ef88ff806e0ee8f7847e87e6bb785912f7795b61913",
      "document_id": 17,
      "document_title": "POJK_11_2022_Penyelenggaraan_Teknologi_Informasi",
      "last_outcome": "success",
      "last_seen_job_id": 45,
      "created_at": "2026-09-26T15:02:44.389678Z",
      "updated_at": "2026-09-26T15:02:44.389678Z"
    }
  ]
}
```

**Nilai `last_outcome`:**
- `'success'`: Berkas berhasil di-ingest.
- `'duplicate'`: Berkas duplikat terhadap dokumen yang sudah ada.
- `'skipped_unchanged'`: Berkas tidak berubah sejak run sebelumnya (dilewati tanpa baca isi).
- `'failed'`: Terjadi kesalahan saat membaca atau memvalidasi berkas.

---

## 5. Perubahan Dashboard (`GET /api/v1/dashboard/summary`)

Objek `sources` kini menyertakan rincian `by_type`:
```json
{
  "sources": {
    "total": 3,
    "active": 3,
    "by_type": {
      "situs_web": 1,
      "folder_lokal": 1,
      "onedrive_public": 1
    }
  }
}
```
