# PERUBAHAN KONTRAK API — LANGKAH 8 (Kesiapan Deploy & Hardening)
> **Untuk Tim Frontend (Hero UI) & Integrator**  
> **Versi API:** `0.8.0`  
> **Kompatibilitas:** Seluruh endpoint dan key lama tetap dipertahankan (*non-breaking changes* / penambahan fungsionalitas).

---

## 1. Proteksi Dokumen Non-Publik saat Login Nonaktif (NDA Guard)

Ketika `AUTH_ENABLED=false` dan proteksi aktif (`PROTECT_NON_PUBLIC_WHEN_AUTH_DISABLED=true`):

### 1.1 Pencarian Dokumen (`GET /documents/`)
Untuk dokumen dengan `access_classification = "non_publik"`:
- Item hasil pencarian memuat flag baru: `"restricted": true` (untuk dokumen publik nilainya `false`).
- Key `"pdf_url"` bernilai `null` (untuk dokumen publik mengembalikan URL unduh).
- Key `"highlight"` tidak mengekstraksi potongan isi teks dokumen sensitif, melainkan hanya menampilkan judul dokumen.
- Frontend dapat menampilkan label gembok / *"Akses Terbatas (NDA)"* dan menonaktifkan tombol buka PDF bila `restricted === true`.

### 1.2 Unduh PDF & Teks Penuh (`GET /documents/{id}/pdf` dan `GET /documents/{id}/text`)
- Mengembalikan **HTTP 403 Forbidden**:
  ```json
  {
    "detail": "Dokumen non-publik hanya dapat dibuka setelah login diaktifkan."
  }
  ```

---

## 2. Standardisasi Pagination Kandidat Scan (`GET /scans/{id}/candidates`)

Parameter query telah distandarkan konsisten dengan seluruh API HERO:
- **`skip` (int, default `0`):** Jumlah data yang dilewati.
- **`limit` (int, default `20`, max `100`):** Jumlah data per halaman.
- **`page` (int, opsional):** Tetap didukung sebagai alias kompatibilitas mundur (`skip = (page - 1) * limit`).
- **Respons format:**
  ```json
  {
    "items": [...],
    "total": 45,
    "skip": 0,
    "limit": 20
  }
  ```

---

## 3. Hasil Tarik Scan Berbahasa Indonesia (`pull_outcome`)

Nilai status hasil penarikan kandidat scan (`pull_outcome`) kini menggunakan bahasa Indonesia:
- **Nilai Utama Baru:** `"berhasil"`, `"duplikat"`, `"gagal"`, `"diabaikan"`, `"dalam_proses"`, `"antrian"`.
- **Kompatibilitas Filter Query:** Filter `GET /scans/{id}/candidates?pull_outcome=...` tetap menerima nilai lama berbahasa Inggris (`success`, `duplicate`, `failed`, `ignored`, `processing`, `queued`) sebagai alias.

---

## 4. Penghitung Tambahan pada Riwayat Job Dashboard (`GET /dashboard/summary`)

Objek job pada `recent_jobs` kini menyertakan `processed_count` dan `skipped_count`:
```json
{
  "id": 87,
  "job_type": "sinkron_folder",
  "status": "selesai",
  "success_count": 0,
  "duplicate_count": 0,
  "failed_count": 0,
  "skipped_count": 2,
  "processed_count": 2,
  "progress_percent": 100,
  "created_at": "2026-09-28T10:00:00Z"
}
```
*Frontend dapat menampilkan ringkasan seperti "2 berkas diproses (2 dilewati karena tidak berubah)" tanpa membingungkan pengguna.*

---

## 5. Konsistensi Agregat Dashboard (`by_regulation_type` & `by_year`)

Untuk menjamin total pada grafik/diagram frontend selalu sama dengan `corpus_documents`, dokumen yang belum memiliki jenis regulasi atau tahun penetapan dikelompokkan ke bucket khusus:
```json
{
  "by_regulation_type": [
    { "regulation_type": "POJK", "label": "POJK", "count": 25 },
    { "regulation_type": "SEOJK", "label": "SEOJK", "count": 15 },
    { "regulation_type": null, "label": "Belum diketahui", "count": 7 }
  ],
  "by_year": [
    { "year": 2024, "label": "2024", "count": 30 },
    { "year": 2023, "label": "2023", "count": 10 },
    { "year": null, "label": "Belum diketahui", "count": 7 }
  ]
}
```

---

## 6. Pembaruan Endpoint Pemantauan Sistem (`GET /health`)

Endpoint `/health` kini menyajikan status operasional komprehensif:
```json
{
  "status": "ok",
  "version": "0.8.0",
  "app_env": "production",
  "database": "connected",
  "alembic_revision": "4f9b2d8e1a3c",
  "alembic_head": "4f9b2d8e1a3c",
  "migrations_up_to_date": true,
  "storage_writable": true,
  "crawler_backend": "simple_http",
  "crawler_loaded": true,
  "auth_enabled": false,
  "protect_non_public": true
}
```
- Status HTTP 200 dengan `"status": "degraded"` dikembalikan bila database aktif namun migrasi skema belum up to date.
- Status HTTP 503 Service Unavailable dikembalikan bila database tidak dapat dihubungi.

---

## 7. Unggah Banyak Berkas di Swagger UI (`POST /ingest/upload-pdf`)

Skema OpenAPI untuk unggah berkas multi-part telah diperbaiki sehingga Swagger UI `/docs` menampilkan form pemilihan berkas native (file selector) yang mendukung pemilihan beberapa berkas PDF sekaligus.
