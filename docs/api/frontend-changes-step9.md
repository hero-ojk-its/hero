# Ringkasan Perubahan API HERO Backend (Langkah 9)

> **Untuk:** Personil_D (Frontend Engineer)  
> **Tujuan:** Penjelasan fitur penamaan berkas dinamis (#90 US-20c), penambahan field `bidang`, dan artefak Kontrak API Fase 1 (#91 AI-T12).

---

## 1. Ringkasan Fitur Utama

1. **Penamaan Berkas Dinamis (#90 US-20c):**  
   Pengguna dapat menyusun urutan komponen penamaan berkas melalui tombol-tombol UI (`nama`, `tahun`, `jenis`, `bidang`, `nomor`).
2. **Metadata Sektor / Bidang (`bidang`):**  
   Kolom baru untuk menyimpan sektor regulasi OJK (misal: `Perbankan`, `Pasar Modal`, `IKNB`, `BMKS`).
3. **Kontrak API Fase 1 Lengkap (#91 AI-T12):**  
   Dokumen resmi di [`KONTRAK-API-FASE1.md`](KONTRAK-API-FASE1.md) yang memuat seluruh alur UI, contoh request/respons JSON nyata, tabel enum lengkap, dan kode galat.
4. **Snapshot OpenAPI & REST Client:**  
   - [`openapi-fase1.json`](openapi-fase1.json) untuk type generator TypeScript (`openapi-typescript` / `orval`).
   - [`hero-fase1.http`](hero-fase1.http) untuk pengetesan langsung di VS Code.

---

## 2. Endpoint Baru: Penamaan Dinamis

### 2.1 `GET /api/v1/naming/components`
Mengembalikan daftar komponen penamaan yang tersedia, karakter pemisah, nilai wildcard default, dan urutan default.

**Contoh Respons (200 OK):**
```json
{
  "components": [
    {"key": "nama", "label": "Nama"},
    {"key": "tahun", "label": "Tahun"},
    {"key": "jenis", "label": "Jenis"},
    {"key": "bidang", "label": "Bidang"},
    {"key": "nomor", "label": "Nomor"}
  ],
  "separators": [" ", "_", "-"],
  "wildcard": "NA",
  "default_format": ["nomor", "nama", "tahun"],
  "max_components": 8
}
```

### 2.2 `POST /api/v1/naming/preview`
Menghasilkan pratinjau live nama berkas standar berdasarkan format yang sedang dipilih pengguna di UI.

**Body Request:**
```json
{
  "naming_format": ["nama", "jenis", "tahun", "bidang"],
  "naming_separator": " ",
  "sample": {
    "title": "Kesehatan Bank Umum",
    "regulation_number": "POJK 10/2026",
    "regulation_type": "POJK",
    "release_date": "2026-03-15",
    "bidang": "Perbankan"
  }
}
```
*Catatan: Jika `sample` dan `document_id` tidak dikirim, backend otomatis menggunakan contoh bawaan sistem.*

**Contoh Respons (200 OK):**
```json
{
  "filename": "Kesehatan Bank Umum POJK 2026 Perbankan.pdf",
  "missing_components": []
}
```

---

## 3. Penambahan Field pada Endpoint Eksisting

### 3.1 `POST /api/v1/ingest/upload-pdf` (Multipart)
Dapat mengirimkan field formulir tambahan:
- `naming_format` (string dipisah koma, misal: `"nama,jenis,tahun,bidang"`)
- `naming_separator` (string: `" "`, `"_"` atau `"-"`)
- `bidang` (string, misal: `"Perbankan"`)

### 3.2 `POST /api/v1/scans/{id}/pull`
Body request kini menerima opsi format penamaan:
```json
{
  "destination": "knowledge_base",
  "naming_format": ["nama", "tahun", "bidang"],
  "naming_separator": "_"
}
```

### 3.3 `POST /api/v1/scraping-sources/{id}/run`
Body request (opsional) untuk override format penamaan:
```json
{
  "naming_format": ["nama", "tahun", "bidang"],
  "naming_separator": "-"
}
```

### 3.4 `GET /api/v1/documents/` (Daftar & Pencarian Full-Text)
- Parameter filter baru: `bidang` (contoh: `GET /api/v1/documents/?bidang=Perbankan`).
- Parameter pencarian teks: `q`, `mode` (`phrase` | `all` | `web`), dan `highlight=true`.
- Parameter pencarian nomor regulasi: `regulation_number` (pencarian trigram cepat).
- Setiap objek dokumen di respons daftar dan detail kini memuat properti `bidang`, `naming_format`, dan `naming_separator`.

### 3.5 `PATCH /api/v1/documents/{id}/metadata`
Body request mendukung update field `bidang` bersamaan dengan metadata lainnya.

---

## 4. Panduan Penanganan Error di Frontend

Backend HERO merespons galat dalam 2 bentuk:
1. **Galat Bisnis / HTTP 4xx / 5xx:** `{ "detail": "Pesan galat dalam bahasa Indonesia" }`
2. **Galat Validasi Schema (422):** `{ "detail": [ { "loc": [...], "msg": "...", "type": "..." } ] }`

Rekomendasi helper error handler:
```typescript
export function extractErrorMessage(error: any): string {
  const detail = error?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((d: any) => d.msg).join(', ');
  return 'Terjadi kesalahan pada sistem.';
}
```
