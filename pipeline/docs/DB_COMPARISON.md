# Perbandingan Relasional · Vektor · Graf — HERO

*Dihasilkan oleh `hero bench` pada 02 October 2026 20:10. Semua angka diukur, bukan diperkirakan; jalankan ulang setelah knowledge base bertambah — kesimpulan bisa berubah.*

**Korpus:** 118 dokumen di KB · 3206 rekaman register · 3966 pasal · 12914 potongan terindeks vektor.

## 1. Relasional: read model untuk layar Knowledge Base

Pembanding *naif* = menurunkan setiap baris (ringkasan, topik, urgensi, dll.) dari JSON analisis **pada setiap request**. *Read model* = baris yang sama, dihitung sekali saat ingest, disimpan di kolom berindeks.

| Operasi layar | Naif (p50) | Read model (p50) | Lebih cepat |
|---|---:|---:|---:|
| Daftar KB (halaman 1) | 42.47 ms | 0.07 ms | **566×** |
| Filter status + topik | 43.08 ms | 0.17 ms | **249×** |
| Kotak cari 'karbon' | 2.91 ms | 0.16 ms | **18×** |
| Opsi filter (facets) | 44.74 ms | 0.18 ms | **245×** |
| Laci detail dokumen | 42.87 ms | 0.07 ms | **621×** |

Selisih ini tumbuh linear terhadap jumlah dokumen pada cara naif, sedangkan read model tetap dibatasi indeks dan `LIMIT` — pada ribuan dokumen, cara naif tidak lagi layak dipakai untuk tabel interaktif.

## 2. Temu-kembali: kata kunci vs vektor

Diukur pada `config/eval_queries.yaml`. **Recall@5** = bagian dokumen relevan yang muncul di 5 teratas; **MRR@10** = rata-rata 1/peringkat dokumen relevan pertama (1,0 = selalu di posisi pertama).

### Set `kata_kunci` (12 kueri)

| Metode | Hit@1 | Recall@5 | MRR@10 |
|---|---:|---:|---:|
| **Kotak cari UI (FTS5, semua kata → fallback)** | 1.00 | 0.94 | **1.00** |
| Leksikal BM25 (FTS5, kata apa saja) | 0.83 | 1.00 | 0.90 |
| Vektor LSA (deterministik) | 0.67 | 0.90 | 0.76 |
| Vektor semantik e5-large (AI-Assisted) | 0.75 | 0.98 | 0.81 |
| Hibrida RRF (BM25 + semantik) | 0.75 | 1.00 | 0.84 |

### Set `parafrase` (12 kueri)

| Metode | Hit@1 | Recall@5 | MRR@10 |
|---|---:|---:|---:|
| Kotak cari UI (FTS5, semua kata → fallback) | 0.25 | 0.33 | 0.30 |
| Leksikal BM25 (FTS5, kata apa saja) | 0.33 | 0.50 | 0.46 |
| Vektor LSA (deterministik) | 0.17 | 0.50 | 0.31 |
| **Vektor semantik e5-large (AI-Assisted)** | 0.67 | 0.77 | **0.76** |
| Hibrida RRF (BM25 + semantik) | 0.67 | 0.69 | 0.71 |

**Bacaan hasil:**

- Pada kueri kata kunci, metode terbaik adalah **Kotak cari UI (FTS5, semua kata → fallback)** (MRR 1.00).
- Pada kueri parafrase, metode terbaik adalah **Vektor semantik e5-large (AI-Assisted)** (MRR 0.76); kotak cari UI yang mewajibkan semua kata hanya 0.30 — kueri berbahasa sehari-hari hampir tak pernah memuat semua kata judul.
- Semantik mengungguli BM25 pada parafrase (+0.30 MRR) — manfaat pencarian makna terbukti di tempat kata kunci gagal.
- Hibrida RRF: 0.84 (kata kunci) dan 0.71 (parafrase), selisih +0.25 terhadap BM25 pada parafrase — perbaikan nyata.

### Latensi pencarian (kueri tunggal, sudah hangat)

Kueri: *"kewajiban bank menyampaikan laporan kepada otoritas"*

| Tahap | Latensi |
|---|---:|
| kotak_cari_ui | 0.76 ms (p95 0.81) |
| lexical (FTS5 per potongan) | 3.93 ms (p95 4.24) |
| lsa: embed kueri | 8.46 ms (p95 9.87) |
| lsa: KNN sqlite-vec | 3.73 ms (p95 3.87) |
| lsa: KNN numpy | 0.12 ms (p95 0.15) |
| semantic: embed kueri | 14.60 ms (p95 16.14) |
| semantic: KNN sqlite-vec | 15.65 ms (p95 16.35) |
| semantic: KNN numpy | 0.60 ms (p95 0.68) |
| hybrid (ujung-ke-ujung) | 18.23 ms (p95 26.83) |

Pencarian tetangga terdekat: NumPy pada matriks di memori 0.60 ms vs `sqlite-vec` 15.65 ms (**26×**). Keduanya pencarian *eksak*. Karena matriksnya kecil, HERO memakai NumPy secara default dan beralih ke `sqlite-vec` hanya bila indeks terlalu besar untuk disimpan di memori. Indeks aproksimatif (HNSW) baru relevan di ratusan ribu potongan.

## 3. Graf: pertanyaan yang tidak bisa dijawab dua cara lain

**"Jika UU|21|2011 berubah, peraturan mana yang terdampak?"** — mengikuti relasi BERDASAR (dasar hukum) secara berantai.

- Langsung (1 level): **591** · total sampai 3 level: **953** (per level: {1: 591, 2: 360, 3: 2})

| Cara | Latensi |
|---|---:|
| recursive CTE (SQLite) | 5.95 ms (p95 7.84) |
| BFS Python, graf dimuat per kueri | 0.96 ms (p95 1.79) |
| BFS Python, graf sudah di memori | 0.13 ms (p95 0.13) |
| LIKE teks (tanpa graf, 1 level) | 3.39 ms (p95 4.80) |

Recursive CTE 5.95 ms vs BFS di memori 0.13 ms. Graf di memori lebih cepat, tetapi harus dimuat dan dijaga tetap sinkron di setiap proses; CTE membaca langsung dari tabel yang selalu mutakhir. Pada beberapa milidetik, CTE sudah cukup untuk interaksi pengguna — memori baru layak bila traversal dijalankan ribuan kali per detik.

**Tanpa graf** — mencari teks "21 Tahun 2011" di register dengan `LIKE`: 719 rekaman cocok. Dibanding 1 level graf (587 rekaman register): 583 sama, **136 hanya ditemukan LIKE** (menyebut angka itu tapi bukan sebagai dasar hukum, atau UU lain bernomor sama), dan **4 hanya ditemukan graf** (dirujuk lewat dokumen dan bagian Mengingat). LIKE juga tidak bisa melanjutkan ke level 2 dan 3 sama sekali.

**Lineage** ("sudah diganti dengan apa?") untuk `UU|15|1952`: 0.28 ms (p95 0.29).

Graf: 1712 node, edge {'BERDASAR': 2375, 'MENCABUT': 893, 'MENGUBAH': 99}, konflik identitas 1.

## 4. Penyimpanan

| Komponen | Ukuran |
|---|---:|
| PDF asli di knowledge base | 90.8 MB |
| Katalog SQLite (seluruhnya) | 79.94 MB |
| — teks dokumen (document_text + FTS) | 34.18 MB |
| — register (inventory) | 11.84 MB |
| — pasal (articles) | 5.31 MB |
| — read model (kb_*) | 1.68 MB |
| — graf (graph_*) | 1.03 MB |
| Basis data vektor (terpisah) | 217.96 MB |

Indeks vektor lebih besar dari metadata katalog karena setiap pasal disimpan beberapa kali (BLOB, tabel `vec0`, dan cache embedding). Itu data turunan: boleh dihapus dan dibangun ulang kapan saja dari katalog, jadi tidak perlu ikut dicadangkan.

## 5. Kesimpulan untuk HERO

| Kebutuhan | Pilihan | Dasar dari angka di atas |
|---|---|---|
| Tabel, filter, detail Knowledge Base | **Relasional + read model** | 18–621× lebih cepat dari derivasi per-request |
| Kotak cari saat pengguna mengetik | **FTS5, semua kata → fallback sebagian kata** | Semua kata: MRR 1.00 pada kata kunci; fallback menutup parafrase |
| Cari berdasarkan makna / parafrase (URD 3.4) | **Vektor semantik e5-large (AI-Assisted)** | Rata-rata MRR terbaik 0.78 (kata kunci 0.81, parafrase 0.76) vs BM25 0.68 |
| Dasar hukum, pencabutan, dampak perubahan | **Graf** | Satu-satunya yang menjawab rantai multi-level; LIKE menghasilkan 136 kecocokan palsu pada 1 level saja |

Rata-rata MRR kedua set: Vektor semantik e5-large (AI-Assisted) 0.78 · Hibrida RRF (BM25 + semantik) 0.77 · Leksikal BM25 (FTS5, kata apa saja) 0.68 · Vektor LSA (deterministik) 0.53.

Ketiganya bukan pesaing; masing-masing menjawab jenis pertanyaan berbeda, dan ketiganya hidup di SQLite yang sama — tanpa server basis data tambahan di VPS.

### Keterbatasan pengukuran ini

- Korpus kecil (118 dokumen), didominasi pasar modal. Kualitas temu-kembali perlu diukur ulang saat KB tumbuh.
- Set evaluasi 24 kueri, disusun satu orang. Tambahkan kueri dari pengguna sebenarnya (unit DPEA) untuk hasil yang lebih dapat dipercaya.
- Model semantik: `intfloat/multilingual-e5-large` (1024 dimensi, ±2.24 GB). Potongan dibuat 80 kata agar muat di model terkecil (MiniLM, 128 token); e5 membaca hingga 512 token, jadi jendela yang lebih panjang mungkin lebih baik untuknya — belum diuji.
