# Kontrak API HERO untuk Frontend

Dokumen ini memetakan **setiap layar di desain** ke endpoint backend, beserta
bentuk data yang dikembalikan. Tujuannya satu: frontend dibangun sekali,
langsung terhadap data sungguhan — tidak terhadap mock yang nanti harus
diganti.

- **Base URL (lokal):** `http://127.0.0.1:8000` — jalankan `hero serve`
- **Dokumentasi interaktif:** `http://127.0.0.1:8000/docs` (Swagger UI, bisa dicoba langsung)
- **Skema mesin:** [`docs/openapi.json`](openapi.json) — pakai untuk men-*generate* tipe TypeScript:
  ```bash
  npx openapi-typescript docs/openapi.json -o src/api/hero.d.ts
  ```
- **CORS:** `http://localhost:3000` dan `http://localhost:5173` diizinkan secara default;
  ubah lewat variabel lingkungan `HERO_CORS="https://domain-a,https://domain-b"`.

---

## 0. Konvensi yang berlaku di semua layar

### Badge = `{value, label, tone}`

Setiap badge di desain (status regulasi, status KBS, status proses, sumber,
penyelarasan pasal, urgensi) datang dalam bentuk yang sama:

```json
{ "value": "berlaku", "label": "Aktif", "tone": "success" }
```

Frontend **menampilkan `label` apa adanya** dan memetakan `tone` ke warna
**sekali saja**:

| `tone` | Warna di desain | Contoh |
|---|---|---|
| `success` | hijau | Aktif, Baru, Berhasil, Selesai, Tersimpan di KBS, Terpetakan Lengkap |
| `warning` | kuning/oranye | Diubah, Duplikat, Terpetakan Sebagian, Sedang |
| `danger` | merah | Dicabut, Gagal Terhubung, Tinggi, Belum Terpetakan |
| `info` | biru | Sedang Diproses, Rancangan |
| `neutral` | abu-abu | Sudah Ada, Menunggu, Tidak Diketahui |

Jangan memetakan `value → label` di frontend. Seluruh daftar label ada di
`GET /api/meta/enums`, dan kalau istilah berubah (misalnya "Aktif" menjadi
"Berlaku"), cukup backend yang diubah.

### Isi dropdown filter = `GET /api/kb/facets`

Jangan hardcode kategori, jenis, tahun, topik, status, atau sumber. Endpoint
ini mengembalikan nilai **yang benar-benar ada di data** beserta jumlahnya:

```json
{ "kategori": [{"value": "pasar-modal", "label": "Pasar Modal", "count": 42}, …],
  "topik":    [{"value": "Pelaporan", "label": "Pelaporan", "count": 19}, …], … }
```

### Proses panjang = job + polling

Scan dan ingest berjalan di latar belakang (scan JDIH 50 rekaman ±75 detik).
`POST` langsung menjawab **202** dengan `{id, status_url}`; frontend
mem-*polling* `status_url` setiap ±1 detik sampai `status.value` bukan
`"berjalan"`.

### Galat

Format standar FastAPI: `{"detail": "pesan dalam bahasa Indonesia"}`.

| Kode | Arti | Tampilkan sebagai |
|---|---|---|
| 404 | tidak ditemukan | pesan `detail` |
| 409 | konflik status (mis. memilih item yang bukan "Baru") | pesan `detail` |
| 422 | input tidak valid (mis. URL JDIH tanpa sektor/jenis) | pesan `detail` di bawah field |
| 503 | indeks vektor belum dibangun | sembunyikan opsi pencarian semantik |

---

## 1. Knowledge Base

### 1a. Tabel + kotak cari + filter + paginasi

```
GET /api/kb/documents?q=&kategori=&jenis=&tahun=&topik=&status=&sumber=&akses=&sort=terbaru&page=1&page_size=8
```

- Setiap filter boleh **diulang** untuk multi-pilih: `?status=berlaku&status=diubah`.
- `sort`: `terbaru` (default) · `tahun_desc` · `tahun_asc` · `judul` · `relevansi`
- `mode`: `lexical` (default) · `semantic` · `hybrid` — lihat bagian 6.
  Rekomendasi dari pengukuran (`docs/DB_COMPARISON.md`): pakai `lexical` untuk
  kotak cari biasa, dan **`semantic`** untuk toggle "cari berdasarkan makna"
  (rata-rata MRR 0,84 vs hibrida 0,79 vs BM25 0,68).

```json
{
  "items": [{
    "id": "e7a2aeedd8a34495bc0231c91082ead3",
    "judul": "POJK tentang Prinsip Kehati-hatian dalam Melaksanakan Kegiatan Structured Product bagi Bank Umum",
    "jenis": "POJK",
    "nomor": "7/POJK.03/2016",
    "nomor_singkat": "POJK-7/2016",
    "kategori": {"value": "perbankan", "label": "Perbankan"},
    "topik": "Umum",
    "tahun": 2016,
    "status": {"value": "berlaku", "label": "Aktif", "tone": "success"},
    "sumber": {"value": "web", "label": "Scraping"},
    "cocok": null
  }],
  "total": 93, "page": 1, "page_size": 8, "pages": 12,
  "mode": "lexical", "pencarian": null, "waktu_ms": 0.14
}
```

| Elemen desain | Field |
|---|---|
| "Knowledge Base **128 dokumen**" | `total` pada request tanpa filter |
| Kolom Judul Regulasi | `judul` |
| Kolom Jenis | `jenis` |
| Kolom Nomor (`POJK-11/2024`) | `nomor_singkat` |
| Kolom Kategori / Topik / Tahun | `kategori.label` / `topik` / `tahun` |
| Kolom Status (badge) | `status` |
| Kolom Sumber (ikon + teks) | `sumber.value` untuk ikon, `sumber.label` untuk teks |
| "Menampilkan 1–8 dari 128 regulasi" | hitung dari `page`, `page_size`, `total` |
| Paginasi 1 2 3 … 16 | `pages` |

**Kotak cari punya dua tingkat.** Mula-mula semua kata harus cocok (tepat,
cocok untuk nomor/judul). Bila hasilnya nol, backend otomatis mencari dengan
"kata apa saja" dan mengembalikan `"pencarian": "sebagian_kata"`. Pada kondisi
itu tampilkan keterangan kecil di atas tabel:
*"Tidak ada yang cocok persis — menampilkan hasil yang cocok sebagian."*
Tanpa fallback ini, kueri berbahasa sehari-hari seperti "hak libur tahunan
karyawan" selalu kosong (diukur: 0 dari 12 kueri parafrase terjawab).

### 1b. Laci detail ("drawer")

```
GET /api/kb/documents/{id}
```

| Elemen desain | Field |
|---|---|
| Badge `POJK` · `● Aktif` | `jenis` · `status` |
| Judul besar | `judul` |
| `POJK-11/2024` | `nomor_singkat` |
| KATEGORI SEKTOR | `kategori.label` |
| TOPIK REGULASI | `topik` (seluruhnya: `topik_semua`; alasan: `topik_alasan`) |
| TAHUN & TERBIT "2024 (12 Maret 2024)" | `tahun` + `tanggal_terbit.label` |
| SUMBER PEREKAMAN | `sumber.label` + `sumber_detail` |
| RINGKASAN & POIN KUNCI | `ringkasan` + `poin_kunci[]` (`kategori`, `pasal`, `halaman`, `teks`) |
| Penyelarasan Pasal "✓ Terpetakan Lengkap" | `validasi.penyelarasan_pasal` (badge + `alasan`) |
| Tingkat Urgensi "Tinggi (Sanksi Tertulis)" | `validasi.urgensi_harmonisasi.tampil` (atau `label` + `alasan`) |
| Tombol **Lihat Dokumen PDF Asli** | `pdf.url` |

Setiap penilaian membawa **`alasan`**. Contoh: `"5 pasal terbaca, berurutan
mulai Pasal 1"`, `"Sanksi Tertulis"`. Tampilkan sebagai tooltip. Regulator
harus bisa bertanya "kenapa Tinggi?" dan mendapat jawaban.

Field tambahan yang tidak ada di desain tetapi tersedia: `dasar_hukum[]`
(isi bagian *Mengingat*), `jumlah_pasal`, `jumlah_halaman`, `akses`.

### 1c. Lihat Dokumen PDF Asli

```
GET /api/kb/documents/{id}/pdf      → application/pdf (inline)
```

Buka di tab baru atau `<iframe>`. Header respons:

- `X-HERO-Asal: salinan-lokal` — disajikan dari disk
- `X-HERO-Asal: diambil-ulang-terverifikasi` — salinan lokal sudah dipangkas
  (hemat ruang), diambil ulang dari sumber, dan **SHA-256-nya cocok** dengan
  yang tercatat saat ingest
- `X-HERO-SHA256` — sidik jari dokumen, bisa ditampilkan sebagai bukti keaslian

**409** berarti isi dokumen di sumber berubah sejak dianalisis. Tampilkan
pesan dari body, jangan diam-diam menampilkan versi baru.

### 1d. Relasi hukum (belum ada di desain — disarankan untuk laci detail)

```
GET /api/kb/documents/{id}/relations
```

Mengembalikan `relasi.mencabut`, `dicabut_oleh`, `mengubah`, `diubah_oleh`,
`berdasar_pada`, `menjadi_dasar_bagi`, dan `lineage.berlaku_terkini`. Satu
kalimat yang sangat berguna bagi pengguna: *"Peraturan ini sudah dicabut dan
digantikan oleh POJK 10/2019 (masih berlaku)."*

---

## 2. Ingest Dokumen — tab **Scraping URL**

### 2a. Form parameter

| Elemen desain | Sumber data |
|---|---|
| URL Sumber | input teks |
| "Sumber URL resmi" (ikon centang) | lihat catatan di bagian 7 |
| Dropdown **Kedalaman Scraping** | `GET /api/meta/enums` → `kedalaman_scraping` |
| Dropdown **Kategori Target Knowledge Base** | `GET /api/kb/facets` → `kategori` |

Tombol **Scan Dokumen**:

```
POST /api/ingest/scans
{ "url": "https://jdih.ojk.go.id/Web/ViewPeraturan/Index?sektor=01&jenisPeraturan=06",
  "kedalaman": 2, "kategori": "perbankan", "maks_item": 50 }
→ 202 { "id": "40eb716a7099", "status_url": "/api/ingest/scans/40eb716a7099" }
```

URL JDIH **wajib** memuat `sektor` dan `jenisPeraturan` (atau kirim field
`sektor`/`jenis`). Tanpa keduanya, JDIH akan menelusuri seluruh 120 kombinasi,
jadi backend menolaknya dengan **422** dan pesan yang jelas.

### 2b. Riwayat Scraping Terakhir

```
GET /api/ingest/history?jenis=url&limit=3
```

| Kolom desain | Field |
|---|---|
| SUMBER URL | `sumber.label` (tautan: `sumber.url`) |
| WAKTU | `dibuat` (ISO 8601 — format "Hari ini, 14:30 WIB" di frontend) |
| DOKUMEN DITEMUKAN | `ringkasan.ditemukan` |
| DOKUMEN BARU | `ringkasan.baru` |
| STATUS | `status` (Berhasil / Gagal Terhubung / Gagal / Terputus) |

---

## 3. **Hasil Pemindaian**

```
GET /api/ingest/scans/{scan_id}            (poll sampai status ≠ "berjalan")
GET /api/ingest/scans/{scan_id}?status_kbs=baru     (opsional, filter per tab)
```

```json
{
  "scan_id": "40eb716a7099",
  "status": {"value": "selesai", "label": "Berhasil", "tone": "success"},
  "progres": null,
  "sumber": {"url": "https://jdih.ojk.go.id/…", "label": "jdih.ojk.go.id/Web/ViewPeraturan/Index"},
  "ringkasan": {"ditemukan": 6, "baru": 2, "sudah_ada": 4, "duplikat": 0, "tidak_tersedia": 0},
  "items": [{
    "item_id": "ae5a2a453bd0",
    "judul": "POJK tentang Prinsip Kehati-hatian bagi Bank Umum yang Melakukan Penyerahan …",
    "nomor_tampil": "POJK No. 9/POJK.03/2016",
    "jenis": "POJK", "tahun": 2016,
    "status_regulasi": {"value": "berlaku", "label": "Aktif", "tone": "success"},
    "status_kbs": {"value": "sudah_ada", "label": "Sudah Ada", "tone": "neutral"},
    "dapat_dipilih": false,
    "alasan": "Peraturan ini sudah ada di Knowledge Base",
    "metadata_dari": "sumber"
  }]
}
```

| Elemen desain | Field |
|---|---|
| "Ditemukan 12 dokumen" + chip `5 Baru` `6 Sudah Ada` `1 Duplikat` | `ringkasan` |
| Tab Semua / Baru / Sudah Ada / Duplikat | filter `status_kbs.value` di klien (atau query `?status_kbs=`) |
| Checkbox baris | aktif hanya bila `dapat_dipilih` |
| Judul + nomor abu-abu | `judul` + `nomor_tampil` |
| STATUS REGULASI / STATUS KBS | `status_regulasi` / `status_kbs` |
| Saat scan masih berjalan | `progres` berisi teks, mis. *"Membaca 6 halaman detail…"* |

**Selain tiga status di desain, ada status keempat:
`tidak_tersedia` ("Tidak Tersedia")** — sumber tidak menyediakan PDF (misalnya
rancangan yang hanya terbit sebagai .docx). Sediakan tab atau tampilkan di
"Semua" dengan checkbox nonaktif, lalu tampilkan `alasan` sebagai tooltip.

Arti tiap status:

| `status_kbs` | Arti |
|---|---|
| `baru` | belum ada di KB, bisa diunduh |
| `sudah_ada` | identitas peraturan (jenis+nomor+tahun), URL dokumen, atau berkas yang sama sudah tersimpan |
| `duplikat` | muncul lebih dari sekali **dalam hasil scan ini** (mis. ojk.go.id menampilkan satu peraturan di dua kanal); hanya kemunculan pertama yang ditawarkan |
| `tidak_tersedia` | tidak ada PDF di sumber |

Tombol **Download Dokumen Terpilih (5)**:

```
POST /api/ingest/jobs
{ "scan_id": "40eb716a7099", "item_ids": ["61411929c349", "a1fe659fd7d9"] }
→ 202 { "id": "14af4552e94d", "status_url": "/api/ingest/jobs/14af4552e94d" }
```

Item selain `baru` diabaikan. Bila tidak ada satu pun yang `baru` → **409**.

---

## 4. **Proses Ingest** dan **Dokumen Berhasil Ditambahkan**

Kedua layar memakai endpoint yang sama. Selama `status.value == "berjalan"`,
tampilkan layar Proses; setelah `selesai`, tampilkan layar Berhasil.

```
GET /api/ingest/jobs/{job_id}
```

```json
{
  "status": {"value": "berjalan", "label": "Sedang Berjalan", "tone": "info"},
  "progres": {"selesai": 3, "total": 5, "persen": 60},
  "tersimpan": 3,
  "sumber": {"url": "…", "label": "…"}, "kategori_target": "perbankan",
  "items": [{
    "judul": "POJK tentang …", "nomor_tampil": "POJK No. 8/POJK.03/2016", "jenis": "POJK", "tahun": 2016,
    "status": {"value": "selesai", "label": "Selesai", "tone": "success"},
    "status_kbs": {"value": "tersimpan", "label": "Tersimpan di KBS", "tone": "success"},
    "doc_id": "733f446336c542b3a5f9c6bd6e474857", "alasan": null
  }]
}
```

| Elemen desain | Field |
|---|---|
| Bilah progres + "60%" + "3 DARI 5 DOKUMEN SELESAI" | `progres.persen`, `progres.selesai`, `progres.total` |
| "5 Dokumen Dipilih" · "Sedang Berjalan" | `progres.total` · `status.label` |
| Status per baris (Selesai / Sedang Diproses / Menunggu) | `items[].status` |
| "5 dari 5 berhasil diproses" / "● 5 Dokumen Tersimpan" | `tersimpan` / `progres.total` |
| Kolom STATUS KBS "Tersimpan di KBS" | `items[].status_kbs` (null bila tidak tersimpan) |
| Tautan per dokumen → laci detail | `items[].doc_id` |

Status item yang mungkin: `menunggu` · `diproses` · `selesai` · `duplikat`
(ternyata sudah ada saat diunduh) · `gagal` (lihat `alasan`).

Setelah job selesai, backend otomatis memperbarui **graf** dan **indeks
vektor** di latar belakang. Dokumen baru langsung muncul di tabel KB; untuk
pencarian semantik perlu jeda singkat.

---

## 5. Ingest Dokumen — tab **Sinkronisasi OneDrive / Folder Lokal**

### 5a. Sumber dan status koneksi

```
GET /api/sync/sources
```

```json
[{ "sumber": "onedrive", "nama": "OneDrive mitra — HERO/downloads", "subfolder": "downloads",
   "koneksi": {"value": "terhubung", "label": "Terhubung", "tone": "success", "alasan": null} },
 { "sumber": "folder", "nama": "Dokumen proyek (lokal)", "path": "docs",
   "koneksi": {"value": "terhubung", "label": "Tersedia", "tone": "success", "alasan": null} }]
```

Badge "● Terhubung" di desain = `koneksi`. Hasilnya di-*cache* 5 menit di
backend, jadi aman dipanggil setiap kali tab dibuka.

### 5b. Scan

```
POST /api/sync/scans
{ "sumber": "onedrive", "sumber_nama": "OneDrive mitra — HERO/downloads",
  "klasifikasi_akses": "internal", "kategori": "perbankan" }

POST /api/sync/scans
{ "sumber": "folder", "path": "/srv/hero/inbox", "klasifikasi_akses": "publik" }
```

Hasilnya di-*poll* lewat `GET /api/ingest/scans/{id}` yang **sama** dengan
tab Scraping URL, jadi layar Hasil Pemindaian, Proses, dan Berhasil dipakai
ulang tanpa perubahan.

- **Klasifikasi Akses** (`publik` / `internal` / `rahasia`) tersimpan per
  dokumen dan bisa dipakai sebagai filter KB (`?akses=internal`).
- Pada scan OneDrive/folder, jenis/nomor/tahun **ditebak dari nama berkas**
  (`metadata_dari: "nama_berkas"`) dan `status_regulasi` bernilai "Tidak
  Diketahui". Nilai sebenarnya dibaca dari isi PDF saat ingest. Sebaiknya
  ada keterangan kecil di layar hasil scan sinkronisasi.
- Berkas pendamping (FAQ, Abstrak, Matriks) otomatis dilewati.

Riwayat Sinkronisasi Terakhir: `GET /api/ingest/history?jenis=sinkronisasi`.

---

## 6. Dashboard dan fitur berikutnya

```
GET /api/dashboard/summary     total dokumen, per status/kategori/sumber, urgensi tinggi, 5 terbaru, statistik graf
```

Untuk **Analisa Regulasi** dan **Harmonisasi** (Fase 2–3), endpoint dasarnya
sudah tersedia:

| Endpoint | Kegunaan |
|---|---|
| `GET /api/search?q=&method=hybrid` | cari berdasarkan makna; tiap hasil membawa `cocok` = pasal yang paling cocok (`rujukan`, `halaman`, `cuplikan`) |
| `GET /api/search/compare?q=` | satu kueri, empat metode, berdampingan (untuk demo/validasi) |
| `GET /api/graph/nodes/{JENIS\|nomor\|tahun}/lineage` | sudah diganti? dengan apa? |
| `GET /api/graph/nodes/{key}/impact` | peraturan yang bersandar padanya (berantai) |
| `GET /api/graph/nodes/{key}/basis` | rantai dasar hukum hingga UU |
| `GET /api/graph/findings` | status register yang bertentangan dengan relasi pencabutan |

---

## 7. Selisih antara desain dan data sebenarnya

Bagian ini sengaja dibuat eksplisit. Setiap poin di bawah akan menjadi
pekerjaan ulang bila frontend dibangun mengikuti mock apa adanya.

| Di desain | Kenyataan di data | Saran |
|---|---|---|
| Kategori "Fintech", "Tata Kelola IT & AI", "Asuransi" | Kategori nyata: Perbankan, Pasar Modal, IKNB, Tata Kelola, Kelembagaan, … | Isi dropdown dari `/api/kb/facets` |
| Topik "Ketahanan Siber", "Manajemen Risiko" | Tersedia sebagai kosakata terkendali 16 topik; satu dokumen bisa punya beberapa | Kolom tabel pakai `topik`; laci pakai `topik_semua` |
| 3 status KBS | Ada status keempat **Tidak Tersedia** | Tambahkan tampilan untuknya |
| "Pilih Folder" untuk OneDrive | Tautan berbagi hanya memberi akses ke folder yang dibagikan; backend tidak menjelajah OneDrive pengguna | Ganti dengan pilihan sumber terdaftar + input subfolder |
| "Sumber URL resmi" (centang) | Belum ada daftar domain resmi | Validasi di frontend terhadap daftar domain yang disepakati (`ojk.go.id`, `jdih.ojk.go.id`, …) atau minta endpoint |
| Kedalaman Scraping berlaku untuk semua URL | Untuk ojk.go.id = jumlah halaman pager; untuk JDIH diabaikan (dikendalikan sektor+jenis) | Tampilkan hint sesuai domain |
| Tanggal terbit selalu ada ("12 Maret 2024") | ±10% dokumen tanpa tanggal terbit | Tampilkan "—" bila `tanggal_terbit.label` null |
| Nomor selalu ada | Sebagian kecil dokumen tanpa nomor terbaca | Tampilkan "—" bila `nomor_singkat` null |
| Hasil pencarian = daftar judul | Mode semantik/hybrid membawa `cocok` (pasal + cuplikan) | Tampilkan cuplikan di bawah judul — itu bukti mengapa dokumen muncul |
