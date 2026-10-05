# Kamus Data HERO

Definisi resmi setiap tabel dan kolom di `data/hero_catalog.db`, beserta
kondisi nyatanya per **20 September 2026**. Dokumen ini adalah rujukan
bersama antara peran data, backend, dan analis: bila ada perbedaan
pemahaman tentang arti sebuah kolom, dokumen ini yang menentukan.

Angka "kosong" diambil dari `hero profile <tabel>` dan akan bergeser seiring
data bertambah. Yang tidak boleh bergeser adalah *arti* kolomnya.

**Konvensi.** NULL dan string kosong/spasi diperlakukan sama — keduanya
berarti "tidak ada nilai". Sistem sumber menulis keduanya untuk maksud yang
identik, sehingga membedakannya hanya membuat angka kelengkapan tampak lebih
baik daripada kenyataannya.

---

## Peta hubungan antar tabel

```
inventory  ──doc_id──▶  documents  ──doc_id──▶  articles
(daftar semua                (berkas yang            (pasal per
 yang terbit)                 benar-benar diunduh)    dokumen)

                             documents ──▶ document_text ──▶ document_fts
                                            (teks penuh)      (indeks cari)
```

Perbedaan yang paling sering tertukar:

- **`inventory`** = *semua yang dipublikasikan sumber*, terunduh atau belum.
  3.206 baris.
- **`documents`** = *berkas yang benar-benar ada di knowledge base*. 63 baris.

Menyebut 3.206 sebagai "jumlah dokumen HERO" adalah keliru. Angka itu adalah
jumlah rekaman katalog; dokumennya baru 63.

---

## Tabel `inventory` — register semua peraturan yang terbit

Satu baris per rekaman yang dipublikasikan sebuah sumber. Diisi oleh
`hero discover`, diperbarui `reconcile_status()`.

| Kolom | Tipe | Kosong | Arti |
|---|---|---:|---|
| `record_key` | TEXT | 0% | **Kunci utama.** URL halaman detail rekaman |
| `source` | TEXT | 0% | Sumber: `jdih-ojk`, `ojk-regulasi`, `ojk-rancangan` |
| `title` | TEXT | 0% | Judul peraturan apa adanya dari sumber |
| `number` | TEXT | 20,3% | Nomor peraturan, mis. `9/POJK.04/2015`. **Kosong pada rancangan adalah normal** — nomor baru terbit saat pengesahan |
| `doc_type` | TEXT | 8,7% | Akronim jenis: `POJK`, `SEOJK`, `PBI`, `UU`, `BL`, `PM`, … (19 nilai) |
| `jenis` | TEXT | 0% | Kode jenis menurut portal sumber |
| `sektor` | TEXT | 0% | Kode sektor menurut portal sumber (28 nilai) |
| `category` | TEXT | 3,9% | Kategori knowledge base hasil klasifikasi (9 nilai) |
| `year` | INTEGER | 0% | Tahun peraturan. Rentang sah 1945–tahun depan; nyatanya 1953–2026 |
| `status` | TEXT | 0% | Status hukum — lihat daftar nilai di bawah |
| `status_label` | TEXT | 17,5% | Teks status apa adanya dari sumber, mis. `Berlaku (Dicabut Sebagian)` |
| `status_source` | TEXT | 17,5% | Dari mana status diperoleh: `jdih` atau kosong. **Wajib kosong bila `status='unknown'`** |
| `reg_key` | TEXT | 28,0% | Kunci penghubung antar sumber: `JENIS\|nomor\|tahun`. Lihat peringatan di bawah |
| `detail_url` | TEXT | 0% | URL halaman detail (sama dengan `record_key`) |
| `document_url` | TEXT | 6,6% | URL berkas dokumen. **Kosong berarti rekaman tidak akan pernah dapat diunduh** |
| `document_name` | TEXT | 6,6% | Nama berkas di sumber |
| `fields_json` | TEXT | 0% | Seluruh field halaman detail, disimpan utuh agar tidak ada informasi yang hilang |
| `attachments_json` | TEXT | 0,2% | Daftar lampiran (Abstrak, FAQ, Matriks) |
| `listed_at` | TEXT | 0% | Waktu rekaman pertama terlihat di halaman daftar |
| `enriched_at` | TEXT | 0,2% | Waktu halaman detail terakhir dibaca. Kosong = baru dari halaman daftar |
| `enrich_error` | TEXT | 99,8% | Alasan pembacaan detail gagal. **Terisi = ada masalah** |
| `doc_id` | TEXT | 98,7% | Terisi bila rekaman sudah diunduh → `documents.doc_id` |
| `file_url` | TEXT | 0,5% | Berkas yang mewakili rekaman (`document_url`, atau lampiran `utama`/`lampiran`/`matriks` bila tidak ada). Diisi `hero scan ukur` |
| `file_name` | TEXT | 0,5% | Nama berkas di sumber (atau dari `Content-Disposition`) |
| `file_role` | TEXT | 0,5% | Asal `file_url`: `document_url` · `utama` · `lampiran` · `matriks` |
| `file_ext` | TEXT | 0,5% | Ekstensi berkas: `pdf` · `docx` · `zip` |
| `file_size` | INTEGER | 1,0% | **Ukuran berkas dalam byte, diukur tanpa mengunduh** (HEAD, cadangan `Range: bytes=0-0`). Kriteria penerimaan scraping MoM #4 |
| `file_type` | TEXT | 1,0% | `Content-Type` dari server |
| `file_method` | TEXT | 0% | `head` · `range` · `none` |
| `file_error` | TEXT | 99,0% | Alasan ukuran tidak diketahui (`HTTP 404`, `tidak ada berkas di sumber`). **Terisi = ada masalah** |
| `file_checked_at` | TEXT | 0% | Waktu pengukuran. Kosong = belum diperiksa (`hero scan ukur` melanjutkan dari sini) |

Rekaman **terindeks** (MoM #4) = `file_url`/`document_url`, `title`, `file_name`/`document_name`
terisi dan `file_size > 0`. Laporan: `hero scan penerimaan`.

### Nilai sah `inventory.status`

| Nilai | Arti | Jumlah |
|---|---|---:|
| `berlaku` | Masih berlaku | 1.469 |
| `dicabut` | Sudah dicabut | 517 |
| `diubah` | Masih berlaku, sebagian diubah | 9 |
| `rancangan` | Draft, belum disahkan | 650 |
| `unknown` | Status tidak diketahui — lihat catatan | 561 |

`unknown` **bukan berarti kegagalan sistem.** Situs `ojk.go.id` tidak pernah
mencantumkan status di halaman manapun; hanya JDIH OJK yang punya field itu.
Dari 561 rekaman `unknown`, **478 berada di luar register JDIH** (PBI, PMK,
KMK, Bapepam-LK) sehingga mustahil dicocokkan, dan hanya **83** yang
benar-benar dapat diperbaiki. Uraian lengkap ada di
[DATA_ANALYST_FASE1.md](DATA_ANALYST_FASE1.md) bagian Temuan 1.

### Peringatan tentang `reg_key`

`reg_key` dibentuk dengan mengambil **angka pertama** dari `number`. Dua pola
penomoran tidak tertangani:

| Pola | Contoh | Akibat |
|---|---|---|
| Bapepam-LK | `KEP-208/BL/2012` | Diawali huruf → kunci tidak terbentuk (187 rekaman) |
| Bank Indonesia | `7/1/PBI/2005` | `7` adalah seri tahun, bukan nomor urut → 42 peraturan berbagi kunci `PBI\|7\|2005` |

Saat ini **belum menimbulkan kesalahan**, karena kedua jenis itu di luar
register JDIH sehingga tak pernah ikut dicocokkan. Akan menjadi masalah nyata
begitu sumber Bank Indonesia diaktifkan.

---

## Tabel `documents` — berkas yang ada di knowledge base

Satu baris per PDF yang benar-benar tersimpan. Diisi `IngestPipeline`.

| Kolom | Tipe | Kosong | Arti |
|---|---|---:|---|
| `doc_id` | TEXT | 0% | **Kunci utama.** UUID heksadesimal |
| `sha256` | TEXT | 0% | Hash isi berkas. **Dasar deduplikasi lintas jalur** |
| `source_type` | TEXT | 0% | Jalur masuk — lihat daftar nilai di bawah |
| `source_name` | TEXT | 0% | Nama sumber/situs asal |
| `source_ref` | TEXT | 0% | URL atau path berkas asal |
| `original_filename` | TEXT | 0% | Nama berkas sebelum ditata ulang |
| `stored_path` | TEXT | 0% | Lokasi berkas di knowledge base |
| `category` | TEXT | 0% | Kategori hasil klasifikasi (8 nilai) |
| `size_bytes` | INTEGER | 0% | Ukuran berkas |
| `page_count` | INTEGER | 0% | Jumlah halaman. **Harus > 0 bila `status='ingested'`** |
| `ocr_pages` | INTEGER | 0% | Berapa halaman melalui OCR |
| `is_scanned` | INTEGER | 0% | 1 bila dokumen hasil pindai |
| `status` | TEXT | 0% | `ingested` · `duplicate` · `rejected` · `failed` |
| `reason` | TEXT | 100% | Alasan ditolak/gagal. **Terisi = ada masalah** |
| `title` | TEXT | 0% | Judul hasil ekstraksi metadata |
| `subject` | TEXT | 3,2% | Perihal — bagian setelah kata "TENTANG" |
| `doc_type` | TEXT | 3,2% | Jenis peraturan hasil ekstraksi |
| `number` | TEXT | 7,9% | Nomor peraturan hasil ekstraksi |
| `year` | INTEGER | 1,6% | Tahun hasil ekstraksi |
| `issued_date` | TEXT | 9,5% | Tanggal penetapan (ISO `YYYY-MM-DD`) |
| `issuing_body` | TEXT | 3,2% | Lembaga penerbit |
| `reg_status` | TEXT | 0% | Status hukum dokumen |
| `confidence` | REAL | 0% | Keyakinan ekstraksi metadata, **rentang 0–1** (jangan tertukar dengan confidence OCR yang berskala 0–100) |
| `metadata_json` | TEXT | 0% | Hasil ekstraksi lengkap: dasar hukum, struktur, summary, key takeaways |
| `ingested_at` | TEXT | 0% | Waktu masuk knowledge base |
| `source_key` | TEXT | 6,3% | Kunci sumber terdaftar di `config/sources.yaml` |
| `status_source` | TEXT | 23,8% | Asal status hukum |
| `access_class` | TEXT | 0% | `publik` · `internal` · `rahasia`. **Publik harus terbukti** (sumber publik atau terdaftar di register); `hero akses audit` mengetatkan sisanya. Menentukan apa yang boleh ke AI eksternal, ekspor, dan snapshot |

`metadata_json["identitas_sebelumnya"]` ada bila jenis/nomor/tahun dikoreksi dari register oleh
`hero ekstrak-ulang` — menyimpan nilai hasil parser yang diganti beserta waktunya.

### Nilai sah `documents.source_type` — empat jalur masuk URD 3.2

| Nilai | Jalur | Perintah |
|---|---|---|
| `web` | Jalur 1 — scraping situs yang diinput manual | `hero scrape`, `hero harvest` |
| `upload` | Jalur 2 — unggah manual | `hero upload` |
| `local_folder` | Jalur 3 — folder lokal / OneDrive tersinkron | `hero folders` |
| `onedrive` | Jalur 3b — share link OneDrive public | `hero onedrive` |

> Nilai-nilai ini harus disalin persis. Menebak nama yang "masuk akal"
> (`folder`, misalnya) menghasilkan hitungan nol yang meyakinkan tanpa galat
> apa pun — kesalahan yang pernah benar-benar terjadi saat modul mutu data
> pertama kali ditulis.

---

## Tabel `articles` — pasal per dokumen

Satu baris per Pasal batang tubuh. **Ini unit pembanding fitur harmonisasi
(URD 3.4)** — mutu tabel inilah yang menentukan apakah fitur berikutnya dapat
bekerja sama sekali.

| Kolom | Tipe | Kosong | Arti |
|---|---|---:|---|
| `id` | INTEGER | 0% | **Kunci utama**, auto-increment |
| `doc_id` | TEXT | 0% | → `documents.doc_id` |
| `number` | TEXT | 0% | Penanda pasal, mis. `Pasal 12` |
| `bab` | TEXT | 2,4% | BAB tempat pasal berada |
| `page` | INTEGER | 0% | Halaman tempat pasal dimulai |
| `text` | TEXT | 0% | Isi pasal. **Tidak boleh kosong** — pasal kosong akan selalu dilaporkan "tidak ada pertentangan" oleh fitur harmonisasi, kesimpulan yang terdengar aman padahal tidak pernah diperiksa |

**Catatan penting.** Surat Edaran (SEOJK, SEBI) **tidak memakai pasal** — ia
disusun dalam seksi angka Romawi (`I. KETENTUAN UMUM`). Nol pasal pada SEOJK
adalah bentuk normalnya, bukan cacat. Untuk POJK, UU, PP, PBI, PADK, dan
PERPRES, nol pasal berarti parser struktur gagal.

---

## Tabel pendukung

| Tabel | Isi |
|---|---|
| `document_text` | Teks penuh per dokumen, per halaman |
| `document_fts` | Indeks pencarian SQLite FTS5 |
| `page_cache` | ETag / Last-Modified untuk conditional GET saat scraping |
| `ingest_log` | Jejak audit setiap upaya ingest, termasuk yang gagal |

`ingest_log` sengaja mencatat kegagalan juga. Tabel yang hanya berisi
keberhasilan tidak dapat dipakai menjawab "mengapa dokumen ini tidak ada".

---

## Aturan mutu yang menjaga kamus ini

21 aturan di `hero/dq/rules.py` menegakkan sebagian besar ketentuan di atas
secara otomatis. Jalankan:

```bash
hero dq                    # ringkas
hero dq --markdown docs/DATA_QUALITY_REPORT.md
hero profile inventory     # profil kolom terkini
```

Bila definisi kolom di dokumen ini berubah, aturan yang bersangkutan harus
ikut berubah — dan sebaliknya.
