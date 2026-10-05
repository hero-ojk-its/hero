# Panduan Perubahan API untuk Frontend — Langkah 12 (Dukungan Halaman Ingest)

Dokumen ini ditujukan untuk tim frontend yang menyambungkan halaman **Ingest Dokumen** (S-02 hingga S-05) ke Backend HERO.

---

## 1. Perbaikan Bug Serialisasi Kandidat (`GET /api/v1/scans/{id}/candidates`)
- **Masalah Sebelumnya:** Status keberlakuan kandidat di API selalu mengembalikan nilai default (`tidak_diketahui`), dan field `effective_date` serta `match_warning` hilang.
- **Perubahan:** Seluruh kolom database model `ScanCandidate` kini diserialisasikan secara utuh menggunakan `CandidateResponse.model_validate(c)`.
- **Field yang Kini Mengembalikan Nilai Riil:**
  - `status_keberlakuan`: mengembalikan nilai riil dari sumber (misal JDIH: `"berlaku"`, `"dicabut"`, `"diubah"`).
  - `effective_date`: format string ISO `YYYY-MM-DD` atau `null` jika tidak ada.
  - `match_warning`: string penjelasan jika ada ketidaksesuaian nomor/tahun antara nama berkas dan metadata web, atau `null` jika cocok.
  - `release_date`: tanggal rilis/penetapan regulasi yang valid.

---

## 2. Pemindaian Sumber Folder Lokal (`folder_lokal`)
Kini tab **"Sinkronisasi Folder"** dapat menggunakan alur interaktif **Pindai → Centang → Tarik**, identik dengan sumber scraping web:
1. **Pindai (`POST /api/v1/scans/`):**
   - Menerima `source_id` milik sumber bertipe `folder_lokal`.
   - Mengambil daftar berkas `.pdf` di direktori lokal sumber secara rekursif (jika `recursive: true`).
   - Ukuran byte dibaca langsung dari filesystem (`size_source: "local"`).
   - Deduplikasi kandidat:
     - `sudah_ada`: jika hash SHA-256 dan ukuran byte identik dengan dokumen yang sudah ada di Knowledge Base.
     - `mungkin_ada`: jika nomor/nama dan ukuran serupa.
     - `baru`: berkas belum pernah di-ingest.
2. **Tarik (`POST /api/v1/scans/{id}/pull`):**
   - Penarikan berkas folder lokal langsung membaca konten berkas dari filesystem tanpa HTTP download overhead.
   - Mendukung `naming_format` dinamis (misal `['nama', 'jenis', 'tahun']`).
   - **Tolak `unduh_folder`:** Jika `destination: "unduh_folder"` dikirim untuk sumber folder lokal, backend mengembalikan **HTTP 422** dengan pesan penolakan jelas: *"Tujuan unduh_folder tidak diizinkan untuk sumber folder lokal karena berkas sudah berada di filesystem lokal."*

---

## 3. Endpoint Opsi Folder Lokal (`GET /api/v1/scraping-sources/folder-options`)
Frontend tidak perlu lagi melakukan hardcode path folder sumber palsu. Endpoint ini memindai direktori yang diizinkan (`local_source_roots`) hingga kedalaman 2:
- **URL:** `GET /api/v1/scraping-sources/folder-options`
- **Respons (HTTP 200):**
```json
{
  "items": [
    {
      "path": "/app/sources/demo_ojk_peraturan",
      "name": "demo_ojk_peraturan",
      "pdf_count": 5,
      "already_registered_source_id": null
    },
    {
      "path": "/app/sources/uji_folder",
      "name": "uji_folder",
      "pdf_count": 2,
      "already_registered_source_id": 1
    }
  ]
}
```
- **Keamanan:** Path di luar direktori root dan tautan symlink yang mengarah keluar root difilter secara ketat dan tidak akan bocor ke daftar opsi.

---

## 4. Dukungan Kategori Target Knowledge Base (`category_id`)
Pada UI modal penarikan dan registrasi scraping, pengguna dapat memilih kategori target penempatan dokumen:
1. **`POST /api/v1/scans/{id}/pull`:**
   ```json
   {
     "destination": "knowledge_base",
     "category_id": 5,
     "naming_format": ["nama", "jenis", "tahun"],
     "naming_separator": "_"
   }
   ```
   - `category_id` bersifat opsional (integer).
   - Jika `category_id` diberikan tetapi ID tersebut tidak ditemukan pada database, API segera mengembalikan **HTTP 422**: *"Kategori target dengan ID {id} tidak ditemukan."*
   - Dokumen yang berhasil ditarik otomatis ditempatkan ke kategori tersebut di Knowledge Base.
2. **`POST /api/v1/scraping-sources/{id}/run`:**
   - Menerima field opsional `category_id: Optional[int]`. Validasi 422 yang sama berlaku.
3. **`POST /api/v1/ingest/upload-pdf`:**
   - Menerima field form `category_id: Optional[str]`. Validasi bilangan bulat diterapkan.

---

## 5. Peningkatan Kualitas Nomor Regulasi OneDrive (`regulation_number`)
- Nomor regulasi dari tautan OneDrive kini diformat mengikuti standar penamaan OJK/JDIH:
  - Format standar: `{Jenis} {Nomor} Tahun {Tahun}` (Contoh: `POJK 3 Tahun 2015`, `PADK 19 Tahun 2015`, `SEOJK 6 Tahun 2016`, `PBI 7 Tahun 1992`, `UU 17 Tahun 2012`).
  - Format Keputusan Direksi Bank Indonesia: `27-164-KEP-DIR-1995`, `26-68-KEP-DIR-1993`.
  - Berkas tanpa informasi jenis/nomor/tahun yang meyakinkan (misal nama acak UUID `708a41f0-9685-...pdf`) dikosongkan (`null`), bukan angka parsial fiktif.

---

## 6. Tahun Regulasi Riil (`regulation_year`) & Perbaikan `release_date`
Pada Langkah 12b, dilakukan koreksi penting terkait tanggal regulasi untuk mencegah "mengarang tanggal" (seperti pengisian 1 Januari semu):
1. **`release_date` Bersih & Murni:**
   - `release_date` hanya diisi bila tanggal **penetapan/pengundangan resmi** benar-benar tercantum di sumber dokumen.
   - Bila tidak tercantum, `release_date` bernilai `null` (bukan fallback semu ke 1 Januari atau tanggal berlaku). Tanggal berlaku tetap disimpan di `effective_date`.
2. **Kolom & Field Baru `regulation_year`:**
   - Ditambahkan pada objek respons:
     - `CandidateResponse` (`GET /api/v1/scans/{id}/candidates`)
     - `DocumentResponse` (`GET /api/v1/documents/{id}`, `GET /api/v1/documents/`)
     - `NamingSampleInput` (`POST /api/v1/naming/preview`)
   - Tipe data: `integer` (nullable, e.g. `2015`, `2024`, `2026`).
   - Urutan penentuan tahun:
     1. Tahun dari nomor regulasi resmi (misal `POJK 3 Tahun 2015` -> `2015`).
     2. Tahun dari judul/perihal dokumen.
     3. Tahun dari nama berkas (misal berkas OneDrive `Peraturan_OJK_3_2015.pdf` -> `2015`).
     4. Tahun dari `release_date` (jika tanggal penetapan ada).
3. **Penyelarasan Komponen Sistem:**
   - **Filter Tahun (`GET /api/v1/documents/?year={year}`):** Menyaring dokumen berdasarkan `regulation_year` (dengan fallback ke tahun `release_date`), sehingga dokumen OneDrive atau dokumen tanpa tanggal penetapan tetap dapat difilter sesuai tahun aslinya.
   - **Statistik Dashboard (`GET /api/v1/dashboard/summary`):** Agregasi `by_year` kini menggunakan `regulation_year`, sehingga tidak ada dokumen regulasi yang hilang dari distribusi tahun.
   - **Pratinjau & Standarisasi Nama Dokumen:** Komponen `tahun` menggunakan `regulation_year` jika `release_date` kosong, sehingga tidak menghasilkan placeholder `NA` untuk dokumen resmi yang memiliki tahun pada nomor atau nama berkasnya.
