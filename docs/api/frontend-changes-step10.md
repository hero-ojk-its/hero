# Panduan Perubahan Frontend — Langkah 10 (Web Scanning & OneDrive)

**Target Pembaca:** Frontend Engineer (Personil_D) & Tim UI  
**Versi Backend:** `0.10.0` (Step 10)  
**Terkait Issue:** #88 (US-13c) & #30 (US-17)

---

## 1. Ringkasan Perubahan Penting

Pada Langkah 10, backend memperkaya kemampuan pemindaian situs web regulasi (OJK, JDIH) dan folder OneDrive publik, serta menyediakan metadata regulasi kaya langsung di tabel kandidat hasil pindai (`ScanCandidate`).

---

## 2. Perubahan Model Kandidat (`ScanCandidate` / `CandidateResponse`)

Endpoint `GET /api/v1/scans/{scan_id}/candidates` kini mengembalikan field metadata tambahan pada setiap item kandidat:

```json
{
  "id": 101,
  "scan_id": 12,
  "url": "https://ojk.go.id/id/regulasi/Documents/Pages/POJK-17-2023/POJK%2017%20Tahun%202023.pdf",
  "filename": "POJK 17 Tahun 2023.pdf",
  "size_bytes": 1048576,
  "size_source": "head",
  "found_on_page": "https://ojk.go.id/id/regulasi/Pages/POJK-17-2023.aspx",
  "document_title": "Penerapan Tata Kelola Bagi Bank Umum",
  "detail_url": "https://ojk.go.id/id/regulasi/Pages/POJK-17-2023.aspx",
  "final_url": "https://ojk.go.id/id/regulasi/Documents/Pages/POJK-17-2023/POJK%2017%20Tahun%202023.pdf",
  "doc_kind": "utama",
  "regulation_number": "POJK 17/POJK.03/2023",
  "regulation_type": "POJK",
  "bidang": "Perbankan",
  "sub_bidang": "Bank Umum",
  "release_date": "2023-09-14",
  "source_path": null,
  "match_status": "baru",
  "selected": true,
  "pull_outcome": null,
  "created_at": "2026-10-01T20:00:00Z"
}
```

### Rekomendasi Tampilan UI:
1. **Badge Peran Dokumen (`doc_kind`)**:
   - `utama` -> Badge Biru / Primer (Dokumen Peraturan Inti)
   - `abstrak` -> Badge Hijau / Sekunder (Ringkasan / Abstrak)
   - `faq` -> Badge Kuning / Info (Tanya Jawab Regulasi)
   - `lampiran` -> Badge Abu-abu (Lampiran Matriks / Tabel)
2. **Kolom Informasi Tambahan**:
   - Tampilkan kolom **Judul Regulasi** (`document_title`), **Nomor Regulasi** (`regulation_number`), dan **Bidang/Sektor** (`bidang`).
   - Tautan klik pada judul dapat membuka `detail_url` di tab baru.

---

## 3. Parameter Filter Baru pada Daftar Kandidat

Endpoint `GET /api/v1/scans/{scan_id}/candidates` kini mendukung query filter tambahan:

| Parameter | Tipe | Contoh | Keterangan |
|---|---|---|---|
| `doc_kind` | string | `?doc_kind=utama` | Menyaring berdasarkan peran dokumen (`utama`, `abstrak`, `faq`, dll.) |
| `bidang` | string | `?bidang=Perbankan` | Menyaring berdasarkan nama sektor/bidang regulasi |
| `q` | string | `?q=tata+kelola` | Pencarian cepat pada nama berkas, judul regulasi, atau URL |

---

## 4. Informasi Status Sesi Pemindaian (`ScanSessionResponse`)

Objek sesi pemindaian (`GET /api/v1/scans/{scan_id}`) kini memuat informasi status proteksi dan adapter:

```json
{
  "id": 12,
  "status": "selesai",
  "blocked": false,
  "crawler_adapter": "sharepoint_postback",
  "stats": {
    "regulations_found": 20,
    "pdfs_found": 60,
    "by_doc_kind": {
      "utama": 20,
      "abstrak": 20,
      "faq": 20
    },
    "pages_visited": 2,
    "requests_made": 64,
    "duration_seconds": 37.34
  },
  "summary": {
    "total": 60,
    "baru": 55,
    "sudah_ada": 5,
    "mungkin_ada": 0,
    "terpilih": 55
  }
}
```

### Rekomendasi Tampilan UI:
- Bila `blocked: true`, tampilkan banner peringatan: *"Pemindaian dihentikan karena proteksi Captcha/WAF pada situs target."*
- Widget ringkasan dapat menampilkan jumlah per kelompok `by_doc_kind` (misal: "20 Dokumen Utama, 20 Abstrak, 20 FAQ").

---

## 5. Dukungan Sumber OneDrive Publik

Saat mendaftarkan atau memicu pemindaian sumber, frontend dapat menyuplai:
- `source_type`: `"onedrive_public"`
- `url`: Tautan berbagi folder OneDrive (misal: `https://oneojk-my.sharepoint.com/:f:/g/personal/...`)
- Metadata jalur folder asli otomatis tersedia di field `source_path` setiap kandidat.
