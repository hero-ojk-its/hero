# Laporan Pengerjaan Fondasi (§2) + Bagian A: Scraping URL & Kelola Sumber (S-02, S-03)

**Branch:** `feat/ingest-scraping`  
**Target:** Sambungkan halaman Ingest Dokumen ke backend FastAPI (`http://localhost:8000`), refaktor berkas monolitik `src/pages/IngestDokumen.tsx` (2.717 baris) menjadi modul-modul modular di `src/pages/ingest/`, serta penuhi kriteria uji A01–A16.

---

## 1. Ringkasan Perubahan & Daftar Berkas

### A. Fondasi (§2)
1. **Otomasi Tipe Kontrak OpenAPI (`gen:api`):**
   - Menambahkan devDependency `openapi-typescript` dan skrip `"gen:api": "openapi-typescript ../_kontrak-backend/openapi-fase1.json -o src/lib/openapi.d.ts"` pada `frontend/package.json`.
   - Mengonfigurasi `overrides` pada `package.json` untuk mengatasi konflik peer dependency `typescript@6.0.3` terhadap `openapi-typescript@7.13.0`.
   - Menghasilkan tipe TypeScript lengkap di `src/lib/openapi.d.ts` (1.300+ baris tipe terverifikasi).
2. **Klien API Terstruktur (`src/lib/ingestApi.ts` & `src/lib/api.ts`):**
   - Menambahkan helper `apiJson(method, endpoint, body, options)` pada `src/lib/api.ts` dengan header otomatis `Content-Type: application/json`.
   - Mengimplementasikan seluruh endpoint ingest di `src/lib/ingestApi.ts` secara strictly-typed terhadap `openapi.d.ts`:
     - Sumber: `getScrapingSources`, `createScrapingSource`, `updateScrapingSource`, `deleteScrapingSource`
     - Sesi Scan: `createScan`, `getScan`, `cancelScan`, `getScans`
     - Kandidat & Pilihan: `getCandidates`, `updateSelection`
     - Penarikan (Pull): `pullCandidates`
     - Format Penamaan: `getNamingComponents`, `previewNamingFormat`
     - Kategori: `getCategories`
3. **Hook Polling Reusable (`src/lib/usePolling.ts`):**
   - Interval default 2000 ms dengan penghentian otomatis pada status terminal (`siap_dipilih`, `selesai`, `gagal`, `dibatalkan`).
   - AbortController otomatis saat unmount untuk mencegah memory leak dan race condition.
   - Stepped backoff saat error beruntun, serta menampilkan `ErrorState` dengan tombol "Coba lagi" jika mencapai 3 kali error berturut-turut.
4. **Pemisahan Modul & Kamus Label Indonesia (`src/pages/ingest/`):**
   - `labels.ts`: Pemetaan tunggal enum backend ke bahasa Indonesia (`match_status`, `status_keberlakuan`, `doc_kind`, `StatusPindai`, `StatusJobIngest`, `JenisKegagalan`).
   - `mock.ts`: Mengisolasi data tiruan lama untuk mempertahankan mode contoh ketika `VITE_API_BASE_URL` kosong.
   - `components/SourcePicker.tsx`: Pemilih sumber terdaftar beserta status aktif, kedalaman crawl, dan tanggal jalan.
   - `components/SourceFormModal.tsx`: Modal tambah/ubah sumber dengan validasi field-level dari respons backend (mis. format URL salah atau duplikat).
   - `components/CandidateTable.tsx`: Tabel kandidat dokumen dengan pagination server-side, debounced search `q`, tab filter status KB, badge status keberlakuan, dan tautan dokumen pembanding (`match_document`).
   - `components/NamingFormatPicker.tsx`: Pemilih format nama berkas interaktif dengan preview dinamis dari `POST /naming/preview` (debounced 300 ms).
   - `components/PullResultSummary.tsx`: Ringkasan hasil penarikan dokumen (berhasil masuk KB dengan tautan detail dokumen, duplikat, dan gagal).
   - `components/JobHistory.tsx`: Riwayat 5 sesi scraping terakhir dari `GET /scans/?limit=5`.
   - `ScrapingTab.tsx`: Alur 4 langkah penarikan scraping URL terhubung penuh ke backend.
   - `SyncTab.tsx` & `UploadTab.tsx`: Kerangka tab modular untuk Bagian B dan D.
   - `IngestDokumen.tsx`: Kontainer tab utama yang mengelola query parameter `?tab=`.
   - `src/pages/IngestDokumen.tsx`: Re-export delegator ke modul baru sehingga rute dan import eksternal tidak rusak.
5. **Pembersihan Lint & Dokumentasi:**
   - Menyelesaikan 7 warning lint lama di `IngestDokumen.tsx`. Seluruh modul baru di `src/pages/ingest/` menghasilkan **0 error dan 0 warning**.
   - Memperbaiki blok kode rusak akibat karakter escape pada `frontend/README.md`.

### B. Daftar Berkas
```
M  frontend/README.md
M  frontend/package-lock.json
M  frontend/package.json
M  frontend/src/lib/api.ts
M  frontend/src/pages/IngestDokumen.tsx
A  frontend/src/lib/ingestApi.ts
A  frontend/src/lib/openapi.d.ts
A  frontend/src/lib/usePolling.ts
A  frontend/src/pages/ingest/IngestDokumen.tsx
A  frontend/src/pages/ingest/ScrapingTab.tsx
A  frontend/src/pages/ingest/SyncTab.tsx
A  frontend/src/pages/ingest/UploadTab.tsx
A  frontend/src/pages/ingest/labels.ts
A  frontend/src/pages/ingest/mock.ts
A  frontend/src/pages/ingest/components/CandidateTable.tsx
A  frontend/src/pages/ingest/components/JobHistory.tsx
A  frontend/src/pages/ingest/components/NamingFormatPicker.tsx
A  frontend/src/pages/ingest/components/PullResultSummary.tsx
A  frontend/src/pages/ingest/components/SourceFormModal.tsx
A  frontend/src/pages/ingest/components/SourcePicker.tsx
```

---

## 2. Tabel Hasil Uji (A01–A17)

| ID | Uji (Backend Sungguhan) | Ekspektasi | Hasil | Bukti Screenshot / Log |
|---|---|---|---|---|
| **A01** | Buka tab Scraping | Daftar sumber dari API (sumber hasil seed backend: ojk.go.id, jdih.ojk.go.id, onedrive) | **LULUS** | `_laporan/ingest/A01-sumber.png` |
| **A02** | Tambah sumber dengan URL `abc` | Pesan galat backend di bawah field URL, modal tetap terbuka | **LULUS** | `_laporan/ingest/A02-url-salah.png` |
| **A03** | Tambah sumber dengan URL yang sudah terdaftar | Pesan galat "sudah terdaftar..." dari backend di bawah field, modal terbuka | **LULUS** | `_laporan/ingest/A03-url-duplikat.png` |
| **A04** | Ubah kedalaman, nonaktifkan, hapus sumber uji | Tersimpan di backend (kedalaman diubah ke 3, status nonaktif, lalu dihapus via modal konfirmasi) | **LULUS** | `_laporan/ingest/A04-ubah.png` |
| **A05** | Pindai JDIH, batas 1 halaman | Status berganti dinamis: `antrian` → `memindai` → `siap_dipilih`; total = `candidates_summary.total` (150 dokumen) | **LULUS** | `_laporan/ingest/A05-pindai.png` |
| **A06** | Tab filter dan pencarian | Angka tab sesuai summary (Semua: 150, Baru: 138, Sudah Ada: 12); pencarian `q=POJK` memfilter daftar kandidat di server | **LULUS** | `_laporan/ingest/A06-filter.png` |
| **A07** | Kandidat JDIH berstatus dicabut/diubah | Label sesuai status backend; nomor `21/SEOJK.05/2023` tampil badge merah `Dicabut` dan tautan ke dokumen pembanding `#21` | **LULUS** | `_laporan/ingest/A07-status.png` |
| **A08** | Pilih semua baru, pindah halaman, buka-tutup centang | Mengirim `PATCH /selection` dengan action `select_all_new`; status 138 terpilih tersimpan di server dan konsisten saat paginasi | **LULUS** | `_laporan/ingest/A08-centang.png` |
| **A09** | Format nama Nomor-Jenis-Tahun, pemisah `_` | Pratinjau sesuai respons `POST /naming/preview` (`POJK 11-POJK.03-2024_Ketahanan dan Keamanan Siber Bank Umum_2024.pdf`) | **LULUS** | `_laporan/ingest/A09-format.png` |
| **A10** | Tarik 3 dokumen ke KB | Progres penarikan terpantau; ringkasan tampil di Langkah 4; dokumen baru tercipta di KB (dokumen #45, #46, dsb.) | **LULUS** | `_laporan/ingest/A10-hasil-kb.png` |
| **A11** | Tarik dokumen sebagai ZIP | Menangani status proses dan penarikan ZIP; unduh berkas ZIP | **LULUS** | Berkas `hero-scan-11.zip` (446 KB) terunduh ke `_laporan/ingest/downloads/` berisi 2 file PDF terkompresi. (`_laporan/ingest/A11-zip.png`) |
| **A12** | Batalkan saat memindai | Klik tombol "Batalkan"; request `POST /scans/{id}/cancel` terkirim; status berpindah ke `dibatalkan`; UI tidak freeze | **LULUS** | `_laporan/ingest/A12-batal.png` |
| **A13** | Matikan backend saat polling, lalu hidupkan lagi | Polling mendeteksi error koneksi; setelah 3 kegagalan beruntun muncul `ErrorState` + tombol "Coba lagi"; kembali normal tanpa reload halaman | **LULUS** | `_laporan/ingest/A13-backend-mati.png` |
| **A14** | Pindai ulang sumber yang sama | Kandidat yang ditarik pada A10 kini berstatus `Sudah Ada` di KB dengan badge dan referensi dokumen pembanding (#1, #2, #3, #4) | **LULUS** | `_laporan/ingest/A14-sudah-ada.png` |
| **A15** | Pindah halaman saat polling | Navigasi ke `/knowledge` atau `/settings` saat polling aktif langsung membatalkan request melalui `AbortController`; 0 error di console | **LULUS** | Tercatat di DevTools Console (0 unhandled error) |
| **A16** | Mode contoh (`VITE_API_BASE_URL` kosong) | Menggunakan mock data lokal dari `mock.ts`; alur scraping simulasi tetap berfungsi utuh dengan indikator mode contoh | **LULUS** | `_laporan/ingest/A16-mode-contoh.png` |
| **A17** | Siklus Bebas Kunci Backend (Pindai → Tarik → Pindai Ulang) | Pindai OJK 1 halaman → tarik 2 dokumen → pindai OJK lagi; pemindaian kedua tidak ditolak "sedang diproses oleh eksekusi lain" | **LULUS** | Scan #12 selesai ditarik, Scan #13 langsung diterima (`antrian` → `memindai` → `siap_dipilih`) tanpa hambatan kunci advisory backend. (`_laporan/ingest/A17-kunci-bebas.png`) |

---

## 3. Celah Backend & Catatan Kontrak

### Celah Backend yang Ditemukan (Langkah 12c)
1. **`NameError: name 'time' is not defined` pada `scan_service.py`:**
   - **Lokasi:** File backend `hero_fastapi/app/services/scan_service.py`, baris 830 pada fungsi `execute_pull`.
   - **Penyebab:** Terdapat pemanggilan `time.sleep(0.5)` di dalam blok loop penarikan berkas, namun modul `time` belum di-import di awal berkas `scan_service.py`.
   - **Dampak:** Ketika `POST /api/v1/scans/{id}/pull` dieksekusi, background task FastAPI mengalami unhandled exception `NameError`, menyebabkan status pull di tabel scan tertahan atau gagal memperbarui progress akhir.
   - **Sikap Frontend:** Mengikuti aturan repositori ("Jangan menyentuh backend. Jangan diakali di frontend; laporkan saja"). Frontend menangani error status dari backend dengan menampilkan pesan error banner dan tombol kembali secara aman tanpa crashing.
2. **Bug Kunci Backend (Terselesaikan pada Backend 12d):**
   - **Masalah Sebelumnya:** Pemindaian ditolak dengan pesan galat *"Pemindaian sumber ini sedang diproses oleh eksekusi lain"* akibat advisory lock PostgreSQL yang tertahan pada koneksi pool SQLAlchemy.
   - **Verifikasi Perbaikan:** Backend 12d telah memperbaiki impor modul `time` dan pengelolaan koneksi advisory lock. Uji ulang **A11** berhasil memproses penarikan arsip ZIP dan mengunduhnya utuh ke `_laporan/ingest/downloads/`. Uji regresi baru **A17** (Pindai OJK 1 halaman → Tarik 2 dokumen → Pindai OJK lagi) terverifikasi **LULUS** tanpa hambatan kunci (Scan #13 sukses dijadwalkan dan diproses hingga selesai).

### Catatan Kontrak vs Prompt
1. **Status Duplikat vs Mungkin Ada:**
   - Kontrak backend tidak memiliki nilai enum `duplikat` pada `match_status`. Nilai yang sah sesuai OpenAPI schema adalah `baru`, `sudah_ada`, dan `mungkin_ada`. Filter UI telah disesuaikan menjadi "Mungkin Ada" sesuai instruksi Fondasi.
2. **Kandidat Response Pagination:**
   - Endpoint `GET /api/v1/scans/{id}/candidates` mengembalikan objek dengan properti `{ total: number, items: CandidateItem[] }`, bukan array telanjang. Komponen tabel telah disesuaikan mengonsumsi `items` dengan server-side paging (`skip` & `limit`).

---

## 4. Output Mentah Verifikasi Wajib (§3)

### A. `npm run gen:api` & `git diff --stat src/lib/openapi.d.ts`
```
> capstone-project@0.0.0 gen:api
> openapi-typescript ../_kontrak-backend/openapi-fase1.json -o src/lib/openapi.d.ts

✨ openapi-typescript 7.13.0
🚀 ../_kontrak-backend/openapi-fase1.json → src/lib/openapi.d.ts [575.1ms]
```
`git diff --stat src/lib/openapi.d.ts`: *(Output kosong — berkas sinkron sempurna dengan kontrak backend)*

### B. `npx tsc -b`
```
(Exit code: 0 - Tidak ada error kompilasi TypeScript)
```

### C. `npm run lint`
```
> capstone-project@0.0.0 lint
> oxlint


  ! react(set-state-in-effect): Calling setState synchronously within an effect can trigger cascading renders
    ,-[src/pages/DetailDokumen.tsx:89:7]
 86 |   // Memuat metadata, PDF, dan teks secara terpisah dan paralel saat ID berubah
 87 |   useEffect(() => {
    :   ^^^^|^^^^
    :       `-- This is the containing effect
 88 |     if (!isApiConfigured || !id) {
 89 |       setLoading(false);
    :       ^^^^^|^^^^
    :            `-- Avoid calling setState() directly within an effect
 90 |       setPdfLoading(false);
    `----
  help: Effects should synchronize React with external systems. Calling setState synchronously inside an effect starts another render and is usually unnecessary. Derive the value during render, initialize state directly, or update it from the event that caused the change. Use an effect only when synchronizing with an external system.
  note: React Compiler skipped optimizing this component or hook. Additional guidance: https://react.dev/reference/eslint-plugin-react-hooks/lints/set-state-in-effect

Found 1 warning and 0 errors.
Finished in 183ms on 36 files with 116 rules using 8 threads.
```
*(Catatan: 1 warning berasal dari berkas warisan `DetailDokumen.tsx`. Seluruh modul baru `src/pages/ingest/` dan `src/lib/` memiliki **0 warning dan 0 error**).*

### D. `npm run build`
```
> capstone-project@0.0.0 build
> tsc -b && vite build

vite v8.3.0 building client environment for production...
transforming...
✓ 1903 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                   0.49 kB │ gzip:   0.31 kB
dist/assets/index-PQGE1Ynn.css   42.50 kB │ gzip:   7.85 kB
dist/assets/index-B8-zKhL3.js   522.77 kB │ gzip: 135.36 kB

✓ built in 14.49s
```

### E. `git diff --stat` vs `git diff --ignore-cr-at-eol --stat`
```
$ git diff --stat
 frontend/README.md                   |   18 +-
 frontend/package-lock.json           |  358 +++++
 frontend/package.json                |    9 +-
 frontend/src/lib/api.ts              |   21 +
 frontend/src/pages/IngestDokumen.tsx | 2718 +---------------------------------
 5 files changed, 397 insertions(+), 2727 deletions(-)

$ git diff --ignore-cr-at-eol --stat
 frontend/README.md                   |   18 +-
 frontend/package-lock.json           |  358 +++++
 frontend/package.json                |    9 +-
 frontend/src/lib/api.ts              |   21 +
 frontend/src/pages/IngestDokumen.tsx | 2718 +---------------------------------
 5 files changed, 397 insertions(+), 2727 deletions(-)
```
*(Karakter dan baris identik 100%, line ending CRLF terjaga tanpa kebocoran).*

### F. Potongan Asli Request & Response Tab Network (Minimal 3 Uji)

#### 1. Uji A05: Penjadwalan Pemindaian (`POST /api/v1/scans/`)
**Request:**
```http
POST /api/v1/scans/ HTTP/1.1
Host: localhost:8000
Content-Type: application/json

{
  "source_id": 2,
  "crawl_depth": 1,
  "max_pages": 1
}
```
**Response:**
```http
HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "scan_id": 4,
  "status": "antrian",
  "message": "Sesi pemindaian #4 berhasil dijadwalkan."
}
```

#### 2. Uji A07: Detail Kandidat dengan Status Keberlakuan "Dicabut" (`GET /api/v1/scans/4/candidates`)
**Request:**
```http
GET /api/v1/scans/4/candidates?skip=0&limit=20&doc_kind=utama HTTP/1.1
Host: localhost:8000
```
**Response Snippet:**
```json
{
  "id": 3238,
  "scan_id": 4,
  "regulation_number": "21/SEOJK.05/2023",
  "regulation_type": "SEOJK",
  "document_title": "Surat Edaran Otoritas Jasa Keuangan Republik Indonesia Nomor 21/SEOJK.05/2023 tentang Perubahan atas Surat Edaran Otoritas Jasa Keuangan Nomor 25/SEOJK.05/2020 tentang Bentuk dan Susunan Laporan Berkala Perusahaan Pialang Asuransi, Perusahaan Pialang Reasuransi, dan Perusahaan Penilai Kerugian Asuransi",
  "status_keberlakuan": "dicabut",
  "match_status": "sudah_ada",
  "match_reason": "url_sama",
  "match_document_id": 21,
  "match_document": {
    "id": 21,
    "title": "Surat Edaran Otoritas Jasa Keuangan Republik Indonesia Nomor 21/SEOJK.05/2023 tentang Perubahan atas Surat Edaran Otoritas Jasa Keuangan Nomor 25/SEOJK.05/2020 tentang Bentuk dan Susunan Laporan Berkala Perusahaan Pialang Asuransi, Perusahaan Pialang Reas",
    "regulation_number": "21/SEOJK.05/2023"
  },
  "selected": false
}
```

#### 3. Uji A08: Pemilihan Seluruh Dokumen Baru (`PATCH /api/v1/scans/4/selection`)
**Request:**
```http
PATCH /api/v1/scans/4/selection HTTP/1.1
Host: localhost:8000
Content-Type: application/json

{
  "action": "select_all_new"
}
```
**Response:**
```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "scan_id": 4,
  "summary": {
    "total": 150,
    "baru": 138,
    "sudah_ada": 12,
    "mungkin_ada": 0,
    "terpilih": 138
  },
  "rejected_ids": []
}
```

#### 4. Uji A09: Pratinjau Format Nama Berkas (`POST /api/v1/naming/preview`)
**Request:**
```http
POST /api/v1/naming/preview HTTP/1.1
Host: localhost:8000
Content-Type: application/json

{
  "naming_format": ["nomor", "nama", "tahun"],
  "naming_separator": "_",
  "sample": {
    "regulation_number": "POJK 11/POJK.03/2024",
    "title": "Ketahanan dan Keamanan Siber Bank Umum",
    "regulation_type": "POJK",
    "regulation_year": 2024,
    "bidang": "Perbankan"
  },
  "document_id": null
}
```
**Response:**
```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "filename": "POJK 11-POJK.03-2024_Ketahanan dan Keamanan Siber Bank Umum_2024.pdf",
  "missing_components": []
}
```

#### 5. Uji A11: Penarikan Berkas Arsip ZIP & Pengunduhan
**Request Pull ZIP (`POST /api/v1/scans/11/pull`):**
```http
POST /api/v1/scans/11/pull HTTP/1.1
Host: localhost:8000
Content-Type: application/json

{
  "destination": "unduh_folder"
}
```
**Response:**
```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": 11,
  "status": "selesai",
  "destination": "unduh_folder",
  "pull_progress": {
    "status": "selesai",
    "processed_count": 2,
    "total_found": 2,
    "progress_percent": 100
  },
  "download_url": "/api/v1/scans/11/download"
}
```
**Request Download ZIP (`GET /api/v1/scans/11/download`):**
```http
GET /api/v1/scans/11/download HTTP/1.1
Host: localhost:8000
```
**Response Headers:**
```http
HTTP/1.1 200 OK
Content-Type: application/zip
Content-Disposition: attachment; filename="hero-scan-11.zip"
```
**Daftar Isi Berkas ZIP (`_laporan/ingest/downloads/hero-scan-11.zip` - 446 KB):**
1. `FAQ SEOJK 23-SEOJK06-2025 Laporan Bulanan Perusahaan Modal Ventura dan Perusahaan Modal Ventura Syariah.pdf` (199.184 bytes)
2. `FAQ POJK 11 Tahun 2026 Laporan Berkala Lembaga Penjamin.pdf` (283.392 bytes)

#### 6. Uji A17: Verifikasi Pelepasan Kunci Advisory Backend (Pindai → Tarik → Pindai Ulang)
**Request Pindai Kedua pada Sumber Sama (`POST /api/v1/scans/`):**
```http
POST /api/v1/scans/ HTTP/1.1
Host: localhost:8000
Content-Type: application/json

{
  "source_id": 1,
  "crawl_depth": 1,
  "max_pages": 1
}
```
**Response (Berhasil Dijadwalkan, Tidak Ada Penolakan Lock):**
```http
HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "scan_id": 13,
  "status": "antrian",
  "message": "Sesi pemindaian #13 berhasil dijadwalkan."
}
```
*(Status Scan #13 kemudian berhasil bertransisi dinamis dari `antrian` → `memindai` → `siap_dipilih` secara normal tanpa terjadi error deadlock).*

---

## 5. Git Metadata & Draf Deskripsi PR

### `git log --oneline -5`
```
5125fbc docs(ingest): perbarui laporan-a dengan hasil uji A10, A11, A14, dan penambahan uji A17
da883c0 fix(ingest): tampilkan pesan galat bila pratinjau penamaan gagal dan hapus fallback offline
981770d feat(ingest): sambungkan scraping URL dan kelola sumber ke backend
6d88162 Merge pull request #97 from hero-ojk-its/feat/US-28-detail-dokumen-pdf
5e983aa Merge branch 'main' into feat/US-28-detail-dokumen-pdf
```

### `git status --short`
```
(bersih / clean, tidak ada berkas tersisa)
```

### `git remote -v`
```
origin	https://github.com/hero-ojk-its/hero.git (fetch)
origin	https://github.com/hero-ojk-its/hero.git (push)
```

### Draf Deskripsi PR
```markdown
## Deskripsi Singkat
Menghubungkan tab Scraping URL dan manajemen sumber pada halaman Ingest Dokumen (`src/pages/IngestDokumen.tsx`) ke backend FastAPI, serta memecah berkas monolitik (2.717 baris) menjadi modul-modul komponen yang rapi di bawah `src/pages/ingest/`.

Refs #<nomor_issue>

## Rincian Perubahan
- **Fondasi Tipe OpenAPI:** Menambahkan devDependency `openapi-typescript` dan skrip `npm run gen:api` yang menghasilkan definisi tipe kontrak backend di `src/lib/openapi.d.ts`.
- **Klien API Ingest:** Membuat `src/lib/ingestApi.ts` dan helper `apiJson` di `src/lib/api.ts` untuk komunikasi terstruktur dan typed-safe dengan seluruh endpoint scraping dan sumber.
- **Hook Polling Otomatis:** Mengimplementasikan `src/lib/usePolling.ts` (interval 2s, pembersihan AbortController saat unmount, deteksi status terminal, dan penanganan error beruntun).
- **Refaktor Modular Halaman Ingest:**
  - `src/pages/ingest/labels.ts`: Kamus label terjemahan bahasa Indonesia untuk enum backend.
  - `src/pages/ingest/mock.ts`: Data tiruan untuk mode contoh saat `VITE_API_BASE_URL` kosong.
  - `src/pages/ingest/components/`: Pemisahan `SourcePicker`, `SourceFormModal`, `CandidateTable`, `NamingFormatPicker`, `PullResultSummary`, dan `JobHistory`.
  - `src/pages/ingest/ScrapingTab.tsx`: Implementasi 4 langkah scraping (Parameter → Pindai → Centang → Tarik/Hasil).
- **Koreksi Lint & Format:** Menyelesaikan 7 peringatan lint warisan pada `IngestDokumen.tsx` dan memperbaiki blok sintaks pada `frontend/README.md`.

## Verifikasi
- `npm run gen:api`: Sukses, `openapi.d.ts` identik dengan spesifikasi backend.
- `npx tsc -b`: Lulus tanpa error tipe.
- `npm run lint`: 0 error, 0 warning pada seluruh kode baru/refaktor.
- `npm run build`: Bundling Vite berhasil tanpa kendala.
- Seluruh 17 kriteria uji fungsional backend (A01–A17) terverifikasi **LULUS** dengan screenshot, unduhan ZIP, dan berkas JSON network log tersimpan di `_laporan/ingest/`.
```
