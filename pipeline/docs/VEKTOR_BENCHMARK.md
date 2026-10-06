# Benchmark penyimpanan vektor — SQLite vs Postgres/pgvector

*Dihasilkan `hero bench vektor` pada 05 October 2026 18:19. Semua angka diukur di mesin yang menjalankannya; jalankan ulang di server sebelum memakainya sebagai dasar keputusan.*

**Korpus:** 12914 potongan dari 118 dokumen · model `intfloat/multilingual-e5-large` (1024 dimensi, mode ai-assisted) · 24 kueri, top-10.

Vektor di kedua penyimpanan **identik** (diambil dari indeks yang sama), jadi yang dibandingkan adalah penyimpanan dan indeksnya — bukan modelnya.

## 1. Latensi & mutu pencarian

`recall@k` = berapa bagian dari k teratas pencarian *exact* yang juga ditemukan. 1,00 berarti tidak ada yang terlewat; di bawah itu adalah ongkos indeks aproksimatif.

| Penyimpanan & indeks | Latensi | recall@k | Catatan |
|---|---:|---:|---|
| SQLite — numpy (matriks di memori) | 0.57 ms (p95 0.74) | 1.00 | exact — jadi ini juga acuan recall |
| SQLite — sqlite-vec (vec0, baca dari disk) | 13.76 ms (p95 20.73) | 1.00 | exact (brute force dalam basis data) |
| Postgres — tanpa indeks (exact) | 16.30 ms (p95 16.73) | 1.00 | seq scan |
| Postgres — IVFFlat lists=113, probes=1 | 0.74 ms (p95 0.86) | 0.26 | indeks dipakai |
| Postgres — IVFFlat lists=113, probes=10 | 1.13 ms (p95 1.50) | 0.65 | indeks dipakai |
| Postgres — IVFFlat lists=113, probes=113 | 9.78 ms (p95 17.05) | 1.00 | seq scan |
| Postgres — HNSW m=16, ef_search=10 | 1.13 ms (p95 1.62) | 0.79 | indeks dipakai |
| Postgres — HNSW m=16, ef_search=40 | 1.30 ms (p95 2.14) | 0.97 | indeks dipakai |
| Postgres — HNSW m=16, ef_search=100 | 1.70 ms (p95 2.60) | 0.99 | indeks dipakai |

Server: PostgreSQL 15.4 (Debian 15.4-1.pgdg120+1) + pgvector 0.5.0 · 12914 baris dimuat dalam 2.44 s lewat `COPY`.

### Waktu & ukuran indeks

| Indeks | Waktu bangun | Ukuran indeks |
|---|---:|---:|
| ivfflat {'lists': 113} | 1.3 s | 106.73 MB |
| hnsw {'m': 16, 'ef_construction': 64} | 9.08 s | 103.87 MB |

### Mutu di tingkat dokumen (pencarian exact, metode semantic)

| Set kueri | n | Hit@1 | MRR@10 |
|---|---:|---:|---:|
| kata_kunci | 12 | 0.75 | 0.81 |
| parafrase | 12 | 0.67 | 0.76 |

Angka ini **sama** untuk SQLite dan pgvector selama keduanya mencari exact — peringkatnya identik. Indeks aproksimatif menurunkannya sebanding dengan recall di tabel pertama.

## 2. Penyimpanan

| Komponen | Ukuran |
|---|---:|
| PDF asli (knowledge base) | 90.8 MB |
| Katalog SQLite (metadata + teks + FTS) | 79.94 MB |
| Vektor di SQLite (BLOB + vec0 + cache) | 217.96 MB |
| Vektor di Postgres (1024 dimensi) | 72.75 MB |
| Vektor di Postgres (zero-pad ke 1536 dimensi) | 108.31 MB |

- SQLite `emb_semantic`: 59.53 MB
- SQLite `emb_cache`: 59.27 MB
- SQLite `vec_semantic_vector_chunks00`: 54.59 MB
- SQLite `emb_lsa`: 17.68 MB
- SQLite `vec_lsa_vector_chunks00`: 13.66 MB
- SQLite `chunk`: 8.28 MB

### Harga kolom 1536 dimensi

Kolom `articles.embedding` backend berdimensi 1536, model ini 1024. Vektor di-zero-pad. Recall terhadap pencarian pada dimensi asli: **1.00** — padding nol tidak mengubah cosine similarity untuk vektor ber-norma 1, jadi 1,00 adalah hasil yang diharapkan dan bukan kebetulan.

Yang terbuang hanya ruang dan waktu: 108.31 MB vs 72.75 MB (**+35.6 MB**, 49% lebih besar) dan latensi exact 18.90 ms (p95 19.02) vs 16.30 ms (p95 16.73).

Pilihannya ada dua, keduanya sah:

1. **Biarkan 1536.** Tidak ada kehilangan mutu, biaya hanya ruang. Pilih ini bila dimensi model masih mungkin berubah.
2. **Samakan kolom dengan model** (1024 dimensi) lewat migrasi aditif: tambah kolom baru `embedding_1024`, isi, pindahkan pembacaan, baru hapus yang lama. Hemat ruang, tetapi mengunci pilihan model.

## 3. Bacaan hasil

- Pada korpus sebesar ini, NumPy di memori 0.57 ms vs pgvector exact 16.30 ms (**28×**). Keduanya exact. Selisih ini adalah ongkos jaringan + parsing SQL, bukan ongkos algoritma.
- Indeks aproksimatif tercepat yang masih menjaga recall ≥ 0,95: **HNSW m=16, ef_search=40** — 1.30 ms (p95 2.14), recall 0.97.
- Keputusannya bukan "SQLite atau Postgres", melainkan **siapa yang bertanya**: pencarian dari frontend lewat backend sebaiknya dijawab pgvector (satu sumber data, satu izin akses, tidak ada salinan yang bisa basi); pekerjaan lapisan data — harmonisasi per pasal, kalibrasi ambang, benchmark — jalan di SQLite karena ia ada di mesin yang sama dengan modelnya dan tidak membebani basis data produksi.
- Angka di atas kecil karena korpusnya kecil. Yang perlu diukur ulang saat korpus tumbuh: latensi exact pgvector (linear terhadap jumlah baris) dan titik di mana HNSW mulai menang.
