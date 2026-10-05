# Kontrak API — Layanan Analisa & Harmonisasi (`/api/v1/ml/*`)

Layanan lapisan data untuk layar **Analisa Regulasi** dan **Harmonisasi**.
Dijalankan dengan `hero bridge serve`, dipasang di `/api/v1/ml/*` lewat reverse
proxy (lihat [`INTEGRASI_BACKEND.md`](INTEGRASI_BACKEND.md) §3.3). Skema mesin:
`/api/v1/ml/openapi.json` · dokumentasi interaktif: `/api/v1/ml/docs`.

**Dua aturan yang berlaku di seluruh endpoint:**

1. Setiap `document_id` yang masuk dan keluar adalah **id dokumen backend**.
   Frontend tidak perlu tahu lapisan data punya penomoran sendiri.
2. Setiap keluaran membawa sumbernya (pasal + halaman + tautan PDF asli) dan
   `catatan` berlabel *Draft / Rekomendasi*. Sistem tidak mengambil keputusan.

Semua respons `application/json`. Galat memakai bentuk FastAPI: `{"detail": "…"}`.

| Kode | Arti | Yang harus dilakukan frontend |
|---|---|---|
| 404 | dokumen belum tercermin / belum punya pasal terbaca | tampilkan "belum siap dianalisa"; pesannya memuat perintah yang perlu dijalankan |
| 503 | indeks vektor atau Postgres belum siap | sembunyikan fitur pencarian makna, bukan menggagalkan layar |

---

## `GET /api/v1/ml/health`

Kesiapan layanan. Dipakai untuk memutuskan apakah menu Analisa/Harmonisasi
boleh aktif.

```json
{
  "status": "siap",
  "korpus": {"dokumen": 7, "pasal": 227, "pasal_berhalaman": 227,
             "dokumen_terpeta_ke_backend": 7},
  "vektor": {"lexical": true, "lsa": true, "semantic": false, "hybrid": false},
  "mode_ai": false,
  "langkah_berikutnya": [],
  "catatan": "Draft / Rekomendasi — …"
}
```

`status`: `siap` | `belum-siap`. Saat `belum-siap`, `langkah_berikutnya` berisi
perintah yang perlu dijalankan operator — tampilkan apa adanya, jangan ditebak.

## `GET /api/v1/ml/dokumen`

Dokumen backend yang sudah siap dianalisa. Dipakai pemilih draft di layar
Harmonisasi.

| Parameter | | |
|---|---|---|
| `peran` | opsional | `corpus_eksisting` \| `draft_kajian` |
| `limit` | opsional | 1–500, bawaan 50 |

```json
{"total": 1, "items": [{
  "document_id": 7, "judul": "PERUBAHAN ATAS PERATURAN …", "jenis": "POJK",
  "nomor": "36 Tahun 2024", "tahun": 2024, "status": "rancangan",
  "peran": "draft_kajian"}]}
```

## `GET /api/v1/ml/analisa/{document_id}`

Ringkasan terstruktur & poin kunci berbasis pasal (URD 3.3). Setiap poin
menyebut pasal dan halamannya.

| Parameter | | |
|---|---|---|
| `mode` | opsional | `deterministik` (bawaan) \| `ai` |

Respons (bagian penting):

| Field | Isi |
|---|---|
| `document_id`, `pdf` | id backend + tautan PDF asli |
| `identitas` | jenis, nomor, tahun, tanggal, penerbit |
| `ringkasan` | daftar `{kalimat, rujukan[], fakta[]}` — tiap kalimat menunjuk pasal asalnya |
| `ringkasan_teks` | ringkasan sebagai satu paragraf |
| `kerangka` | struktur BAB → pasal |
| `poin_utama` | 10 poin terpenting: `{id, kategori, teks, ref, halaman, urgensi}` |
| `jumlah_poin` | total poin yang ditemukan (bisa ratusan) |
| `subjek_diatur`, `sanksi`, `dasar_hukum`, `lampiran` | daftar terstruktur |
| `metrik` | jumlah pasal, ayat, kewajiban, larangan, dst. |
| `mode_diminta` / `mode_dipakai` | `ai` yang gagal otomatis kembali ke `deterministik` |
| `ai` | `null` pada mode deterministik; berisi narasi terverifikasi bila mode `ai` berhasil |

`kategori` poin: `Kewajiban` · `Larangan` · `Sanksi` · `Pelaporan` ·
`Perizinan` · `Batas Waktu` · `Definisi` · `Lain-lain`.

## `GET /api/v1/ml/analisa/{document_id}/klausul`

Pasal yang relevan dengan kebutuhan pengguna — bahan checklist tanggapan.

| Parameter | | |
|---|---|---|
| `kebutuhan` | wajib | ≥ 3 karakter, bahasa sehari-hari |
| `k` | opsional | 1–20, bawaan 5 |

## `POST /api/v1/ml/harmonisasi/{document_id}`

Draft vs korpus, **per pasal** (URD 3.4, FR-HRM-01..13). Body opsional: daftar
`document_id` backend untuk membatasi korpus pembanding (`null` = seluruh korpus).

```jsonc
{
  "versi": "…",
  "draft": {"judul": "…", "key": "POJK|36|2024", "document_id": 7, "pasal": 37},
  "kandidat": [                      // peraturan pembanding, terurut skor
    {"document_id": 2, "doc_id": "be-2", "judul": "…", "skor": 1.765,
     "pasal_mirip": ["1", "4", "5"], "relasi": "diubah"}
  ],
  "rujukan": [                       // peraturan yang DIRUJUK draft + statusnya
    {"key": "POJK|69|2016", "teks": "PERATURAN … NOMOR 69/POJK.05/2016",
     "relasi": "diubah", "status": "berlaku", "document_id": 2, "diganti_oleh": null}
  ],
  "temuan": [
    {"pasal_draft": "Pasal 4",
     "jenis": "menggantikan",
     "badge": {"value": "menggantikan", "label": "Menggantikan", "tone": "amber"},
     "keyakinan": 0.84, "tingkat": "tinggi",
     "alasan": "objek sama dengan 4, redaksi ketentuan diganti (isi lama termuat 86%); draft mengubah/mencabut peraturan tersebut",
     "kutipan_draft": "…",
     "perbedaan": ["batas waktu 30 hari → 14 hari"],
     "pembanding": {"document_id": 2, "judul": "…", "pasal": "4", "halaman": 10,
                    "kutipan": "…", "pdf": "/api/v1/documents/2/pdf#page=10"},
     "alternatif": [], "klausul_baku": false}
  ],
  "ringkasan": {"pasal_draft": 37, "pasal_korpus": 190, "dokumen_korpus": 4,
                "per_jenis": {"menggantikan": 7, "memperjelas": 12, "pasal_baru": 18,
                              "duplikasi": 0, "konflik": 0},
                "rujukan": 6, "rujukan_dicabut": 0,
                "rencana_perubahan": {"diubah": ["1","4","5"], "disisipkan": ["3A","3B"],
                                      "dihapus": []}},
  "rekomendasi": ["18 pasal mengatur objek yang belum ada di korpus — …"],
  "kandidat_register": [],           // peraturan di register yang belum diunduh
  "catatan": "Draft / Rekomendasi — …",
  "waktu_detik": 1.2
}
```

**Label temuan** (`jenis`) dan artinya:

| Label | Arti | Warna `tone` |
|---|---|---|
| `menggantikan` | objek sama, redaksi diganti — draft menyatakan mengubah peraturan itu | amber |
| `memperjelas` | isi lama masih termuat, draft menambah rincian | blue |
| `pasal_baru` | tidak ada pasal korpus yang mengatur objek ini | green |
| `duplikasi` | redaksi hampir identik dengan pasal yang sudah ada | slate |
| `konflik` | dua aturan berbeda yang **keduanya tetap berlaku** | red |

`konflik` dibedakan dari `menggantikan` oleh **hubungan eksplisit**, bukan oleh
angka kemiripan. Peraturan perubahan tidak pernah memuat `konflik` — kalau
muncul, biasanya identitas induknya salah terbaca.

`klausul_baku: true` menandai pasal yang redaksinya serupa di banyak peraturan
(pasal sanksi, "OJK dapat memberikan kebijakan yang berbeda…"); keyakinannya
sudah diturunkan dan sebaiknya ditampilkan lebih redup.

`tingkat`: `tinggi` (≥ 0,75) · `sedang` (≥ 0,50) · `rendah`. Ambangnya ada di
`config/harmonisasi.yaml`, bukan di kode.

## `GET /api/v1/ml/cari`

| Parameter | | |
|---|---|---|
| `q` | wajib | ≥ 2 karakter |
| `metode` | opsional | `lexical` \| `lsa` \| `semantic` \| `hybrid` (bawaan) \| `pgvector` |
| `k` | opsional | 1–50, bawaan 10 |

```json
{"kueri": "…", "metode": "lsa", "total": 3, "items": [
  {"document_id": 3, "doc_id": "be-3", "skor": 0.709, "pasal": "12", "level": "pasal",
   "halaman": 7, "kutipan": "…", "pdf": "/api/v1/documents/3/pdf#page=7"}]}
```

`metode=pgvector` mencari langsung di kolom `articles.embedding` backend
(satu sumber data, tanpa salinan); metode lain memakai indeks lapisan data yang
memotong pasal menjadi jendela 80 kata sehingga kutipannya lebih presisi.
Perbandingan terukur keduanya: [`VEKTOR_BENCHMARK.md`](VEKTOR_BENCHMARK.md).

## `GET /api/v1/ml/pasal-mirip`

Pasal termirip di korpus backend untuk sepotong teks — pembanding cepat saat
pengguna menyalin satu pasal draft.

| Parameter | | |
|---|---|---|
| `teks` | wajib | ≥ 20 karakter |
| `k` | opsional | 1–50, bawaan 10 |
| `kecuali_dokumen` | opsional | `document_id` yang dikecualikan (draft itu sendiri) |
| `hanya_publik` | opsional | `true` = hanya dokumen `access_classification = publik` |

```json
{"total": 3, "embedder": "lsa", "mode": "deterministik", "items": [
  {"article_id": 51, "document_id": 3, "pasal": "Pasal 37", "bab": "BAB VII",
   "kutipan": "…", "judul": "…", "nomor": "61/POJK.07/2020", "jenis": "POJK",
   "status": "berlaku", "skor": 0.4722, "pdf": "/api/v1/documents/3/pdf"}],
 "catatan": "Draft / Rekomendasi — …"}
```

`hanya_publik=true` menyaring di SQL, bukan setelahnya — tidak ada dokumen
ber-NDA yang sempat ikut terbaca. Pakai ini untuk apa pun yang akan keluar dari
server (snapshot, ekspor, layanan AI eksternal).

---

## Kesiapan data per endpoint

| Endpoint | Perlu |
|---|---|
| `/health`, `/dokumen` | `hero bridge sinkron` |
| `/analisa/*` | `hero bridge sinkron` (dokumen harus punya pasal terbaca) |
| `/harmonisasi/*` | `hero bridge sinkron` (graf relasi dibangun otomatis di akhir sinkron) |
| `/cari` (`lexical`/`lsa`/`semantic`/`hybrid`) | `hero vector build` |
| `/cari?metode=pgvector`, `/pasal-mirip` | `hero bridge vektor-isi --apply` + `HERO_PG_DSN` |
