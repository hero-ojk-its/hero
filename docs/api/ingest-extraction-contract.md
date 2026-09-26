# Kontrak Integrasi Ekstraksi Metadata, OCR & Chunking (Data/ML ↔ Backend)

> **Versi Kontrak:** v1.0 (Langkah 5)  
> **Sasaran:** Fathir & Tim Data/ML  
> **Base Path:** `/api/v1/internal`  
> **Header Wajib:** `X-Internal-API-Key: <INTERNAL_API_KEY>`

---

## 1. Ringkasan Alur Ekstraksi

```
[ Worker Data/ML ]                  [ HERO Backend ]
        |                                   |
        |--- 1. POST /extraction/claim ---->|  (Ambil antrean dokumen berstatus 'diterima'
        |<-- 200 OK [daftar task] ----------|   atau timeout klaim > 30 menit)
        |                                   |
        |--- 2. GET /documents/{id}/pdf --->|  (Unduh PDF asli untuk OCR / ekstraksi teks)
        |<-- 200 OK (binary PDF) -----------|
        |                                   |
        | [Proses Ekstraksi / OCR / LLM]    |
        |                                   |
        |--- 3. PATCH .../extraction ------>|  (Kirim metadata, full_text, confidence, atau error)
        |<-- 200 OK (status terindeks/...) -|  (Backend otomatis rename & tempatkan ke kb/...)
```

Jika terjadi kendala sementara pada worker sebelum sempat memproses, worker dapat memanggil:
`POST /api/v1/internal/extraction/requeue/{id}` untuk mengembalikan status dokumen ke `diterima`.

---

## 2. Autentikasi & Header

Setiap request ke endpoint `/api/v1/internal/*` wajib menyertakan header:
```http
X-Internal-API-Key: dev-secret-internal-key-2024
```
Jika header tidak ada atau nilainya salah, backend mengembalikan status **HTTP 401 Unauthorized**:
```json
{
  "detail": "API key internal tidak valid atau tidak disertakan"
}
```

---

## 3. Spesifikasi Endpoint

### 3.1 Klaim Antrean Dokumen (`POST /api/v1/internal/extraction/claim`)

Mengambil sejumlah dokumen untuk diproses oleh worker. Menggunakan transaksi database `SELECT ... FOR UPDATE SKIP LOCKED` sehingga aman dijalankan oleh banyak worker paralel tanpa risiko double-claim.

- **Query Param:**
  - `limit` (integer, default: 10, min: 1, max: 50): Jumlah dokumen maksimal yang ingin diklaim.
- **Kriteria Dokumen yang Diambil:**
  - `processing_status = 'diterima'` ATAU (`processing_status = 'diproses'` DAN `extraction_claimed_at` > 30 menit yang lalu).
  - `extraction_attempts < 3`.
- **Efek di Backend:**
  - Status dokumen berubah menjadi `diproses`.
  - `extraction_claimed_at` diset ke waktu sekarang.
  - `extraction_attempts` bertambah +1.

**Contoh Response `200 OK`:**
```json
[
  {
    "document_id": 42,
    "pdf_url": "/api/v1/internal/documents/42/pdf",
    "original_filename": "Salinan-POJK-11-2022.pdf",
    "file_hash": "a1b2c3d4e5f6...",
    "file_size_bytes": 1048576,
    "document_role": "corpus_eksisting",
    "access_classification": "publik",
    "attempt": 1
  }
]
```

---

### 3.2 Unduh Berkas PDF (`GET /api/v1/internal/documents/{id}/pdf`)

Digunakan oleh worker untuk mengunduh binary PDF dokumen yang sedang diproses.

- **Path Param:** `id` (integer) — ID dokumen.
- **Response `200 OK`:**
  - `Content-Type: application/pdf`
  - Body: Binary stream dari berkas PDF asli.
- **Response `404 Not Found`:** Jika berkas fisik tidak ditemukan di penyimpanan.

---

### 3.3 Kirim Hasil Ekstraksi (`PATCH /api/v1/internal/documents/{id}/extraction`)

Mengirim hasil ekstraksi teks, metadata, dan skor keyakinan (confidence), atau melaporkan kegagalan proses.

- **Path Param:** `id` (integer) — ID dokumen.
- **Query Param:** `force` (boolean, default: `false`) — Jika `true`, memproses request meskipun status dokumen bukan `diproses` (menghindari HTTP 409).
- **Body Schema:** Mendukung penamaan field bahasa **Inggris** maupun alias **Bahasa Indonesia**:

| Field Inggris | Alias Indonesia | Tipe | Wajib | Keterangan |
|---|---|---|---|---|
| `title` | `judul` | string | Opsional | Judul regulasi hasil ekstraksi |
| `regulation_number` | `nomor_peraturan` | string | Opsional | Nomor regulasi (misal `11/POJK.03/2022`) |
| `regulation_type` | `jenis_peraturan` | string | Opsional | Jenis regulasi (misal `POJK`, `SEOJK`, `UU`) |
| `release_date` | `tanggal_terbit` | string (YYYY-MM-DD) | Opsional | Tanggal pengundangan / penetapan |
| `extraction_method` | `metode_ekstraksi` | string | Opsional | Contoh: `surya_ocr`, `pdfplumber`, `llm_v1` |
| `full_text` | `teks_lengkap` | string | Opsional | Teks lengkap dokumen |
| `confidence` | `confidence` | object | Opsional | Skor confidence 0.0 – 1.0 per field metadata |
| `error` | `error` | object | Opsional | `{ "code": "ekstraksi_gagal" | "ocr_gagal", "message": "..." }` |

#### A. Contoh Request Sukses (Bahasa Inggris atau Indonesia):
```json
{
  "title": "Penyelenggaraan Teknologi Informasi oleh Bank Umum",
  "regulation_number": "11/POJK.03/2022",
  "regulation_type": "POJK",
  "release_date": "2022-07-07",
  "extraction_method": "surya_ocr",
  "full_text": "OTORITAS JASA KEUANGAN REPUBLIK INDONESIA SALINAN PERATURAN OTORITAS JASA KEUANGAN...",
  "confidence": {
    "title": 0.95,
    "regulation_number": 0.92,
    "regulation_type": 0.98,
    "release_date": 0.85
  }
}
```

**Response `200 OK` (Sukses Lengkap):**
```json
{
  "status": "terindeks",
  "changed_fields": ["title", "regulation_number", "regulation_type", "release_date", "full_text"],
  "ignored_fields": [],
  "low_confidence_fields": [],
  "placement": {
    "placed": true,
    "standardized_filename": "11-POJK.03-2022 Penyelenggaraan Teknologi Informasi oleh Bank Umum 2022.pdf",
    "category_path": ["POJK", "2022"],
    "destination_path": "kb/POJK/2022/11-POJK.03-2022 Penyelenggaraan Teknologi Informasi oleh Bank Umum 2022.pdf"
  }
}
```

#### B. Logika Penentuan Status Hasil:
1. **`terindeks`**:
   - `title` dan `regulation_number` terisi lengkap.
   - Semua skor keyakinan metadata ≥ threshold (`0.7`).
   - Berkas otomatis ditempatkan ke `kb/{jenis}/{tahun}/` dengan penamaan baku.
2. **`perlu_koreksi`**:
   - Terjadi jika `title` ATAU `regulation_number` kosong, ATAU terdapat field dengan confidence `< 0.7`.
   - Dokumen masuk ke antrian koreksi UI (`/api/v1/documents/needs-review`).
   - **TIDAK membuat log kegagalan** di `ingest_failures`.
3. **Aturan Preservasi Koreksi Manual:**
   - Jika dokumen telah dikoreksi manual oleh pengguna (`metadata_corrected_at` terisi), backend **TIDAK AKAN** menimpa metadata tersebut dari hasil ekstraksi otomatis ML. Field metadata yang ditolak dicatat di `ignored_fields`, sedangkan `full_text` dan metode ekstraksi tetap disimpan.

#### C. Contoh Request Gagal / Error:
```json
{
  "error": {
    "code": "ocr_gagal",
    "message": "Dokumen PDF corrupt atau terproteksi enkripsi DRM password"
  }
}
```
**Response `200 OK`:**
```json
{
  "status": "gagal_dicatat",
  "failure_id": 15
}
```
- Status dokumen berubah menjadi `gagal`.
- Dicatat pada tabel `ingest_failures` dengan `failure_type = "ocr_gagal"` dan `is_retryable = true`.

---

### 3.4 Requeue Dokumen (`POST /api/v1/internal/extraction/requeue/{id}`)

Mengembalikan status dokumen dari `diproses` menjadi `diterima` (misal saat worker mengalami restart mendadak).

- **Path Param:** `id` (integer) — ID dokumen.
- **Efek:** `processing_status = 'diterima'`, `extraction_claimed_at = null`, `extraction_attempts` tidak direset.
- **Response `200 OK`:**
```json
{
  "status": "requeued",
  "document_id": 42
}
```

---

## 4. Retry Kegagalan Ekstraksi (Melalui Backend / Admin UI)

Ketika admin menekan tombol **Retry** pada kegagalan bertipe `ekstraksi_gagal` atau `ocr_gagal` di UI:
1. Backend menjalankan `FailureService.retry(failure_id)`.
2. Dokumen tidak membaca karantina fisik (karena berkas asli tersimpan di `_inbox/` atau staging).
3. Status dokumen dikembalikan ke `diterima` dan kegagalan ditandai `diproses_ulang`.
4. Endpoint mengembalikan `outcome = "requeued"`.
5. Dokumen siap diambil kembali oleh worker pada pemanggilan `POST /extraction/claim` berikutnya.
