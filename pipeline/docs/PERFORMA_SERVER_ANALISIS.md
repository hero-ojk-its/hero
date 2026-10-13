# Analisis Performa Server — Latensi & Kapasitas (Data Analyst, Fase 2)

**Proyek:** HERO · **Peran:** Data / ML (Data Analyst) · **Tanggal:** 10 Oktober 2026
**Alat:** `hero loadtest` (`pipeline/hero/loadtest.py`) · **Tes:** `tests/test_loadtest.py` (25 tes)
**Laporan mentah (dihasilkan perintah, bukan diketik tangan):**
[`PERFORMA_SERVER.md`](PERFORMA_SERVER.md) (1 worker) ·
[`PERFORMA_SERVER_4WORKER.md`](PERFORMA_SERVER_4WORKER.md) ·
[`PERFORMA_SERVER_ML.md`](PERFORMA_SERVER_ML.md) (layanan analisa/harmonisasi, laptop) ·
[`PERFORMA_SERVER_VPS.md`](PERFORMA_SERVER_VPS.md) (**layanan analisa di VPS 1,9 GB, 13 Okt** — angka laptop tidak berlaku di sana)

> Dokumen ini adalah **tafsiran** atas laporan mentah itu. Angkanya diambil dari
> pengukuran 10 Okt 2026 pada katalog nyata (118 dokumen, 12.914 potongan teks, model
> semantik e5-large) di satu laptop 12 inti yang juga menjalankan pembangkit beban.
> Jalankan ulang `hero loadtest` setelah korpus atau mesin berubah; jangan mengutip
> angka di sini sebagai janji kapasitas produksi.

## 1. Jawaban untuk tiga pertanyaan

| Pertanyaan | Jawaban terukur |
|---|---|
| **Berapa lama satu permintaan?** (satu pengguna) | Semua endpoint **p95 ≤ 36 ms**. Terlambat: klausul relevan 36 ms, pencarian hybrid 19 ms, semantik 14 ms. Halaman Knowledge Base/Dashboard < 2 ms. Batas NFR-02 adalah 3.000 ms → margin **> 80×**. Cold start server **0,5 detik**. |
| **Berapa permintaan per detik?** | Puncak **± 490 req/s** per worker untuk campuran sesi pengguna. Per jenis: halaman KB ± 1.400 req/s · pencarian leksikal ± 1.000 req/s · **pencarian semantik/hybrid hanya ± 120–145 req/s**. |
| **Berapa pengguna maksimum?** | Tanpa jeda berpikir: sehat hingga **800 koneksi** yang menembak terus (p95 2,2 s, galat 0%); **1.600 koneksi melewati batas** (p95 4,5 s). Dengan jeda berpikir 5 detik per aksi: **± 3.200 pengguna nyata** *(perkiraan turunan, bukan ukuran langsung)*. |

**Cara membaca "pengguna".** 800 koneksi yang menembak tanpa henti jauh lebih berat daripada
800 orang yang sesekali mengklik. Angka 3.200 berasal dari throughput × (jeda 5 s + waktu
layan) — hukum Little. Pemakai internal DPEA kemungkinan puluhan, jadi **kapasitas bukan
kendala Fase 2**; yang perlu dijaga adalah tidak turun ketika korpus membesar (bagian 4).

## 2. Dua cacat nyata yang ditemukan alat ini — dan sudah diperbaiki

Pengukuran awal menampilkan galat 0,1–0,4% (HTTP 500, 503, koneksi terputus) mulai dari 5
pengguna serentak. Itu bukan derau:

| | Gejala | Akar masalah | Perbaikan |
|---|---|---|---|
| 1 | `GET /api/search` → 500 `sqlite3.InterfaceError` dan `TypeError` | `VectorStore` memakai **satu koneksi SQLite untuk semua utas** (`check_same_thread=False`), dan endpoint ini memanggilnya tanpa kunci | koneksi **per utas** + pemuatan matriks cache dijaga kunci (`vector/store.py`) |
| 2 | `GET /cari` (layanan analisa) → 500, sama | `BridgeState` memakai pola yang sama | koneksi per utas + `timeout=30` agar menunggu penulis (`bridge/state.py`) |

Sesudah perbaikan: **0 galat** di semua level pada seluruh pengukuran final (± 4.900
permintaan per level pada puncak). Tes regresi (`test_vector_store_survives_concurrent_readers`,
`test_bridge_state_survives_concurrent_readers…`) **terbukti gagal tanpa perbaikan**.

Satu kejadian belum terjelaskan sepenuhnya: pada percobaan layanan `ml` *sebelum* perbaikan
#2, 10 pengguna menghasilkan **nol permintaan selesai** (macet). Tidak terulang setelah
perbaikan. Dugaan saya akar masalahnya sama, tetapi **tidak saya buktikan terpisah**.
Alatnya kini menghitung koneksi macet sebagai galat (sebelumnya tampak "0 req/s, galat 0%").

## 3. Apa yang membatasi throughput

Pengukuran subset endpoint (`--endpoint`), 1 worker, 50 pengguna:

| Kelompok | req/s | CPU server | Arti |
|---|---:|---:|---|
| `/api/health` (langit-langit kerangka) | ± 3.300 | ~2 inti | batas atas FastAPI di mesin ini |
| Halaman KB: daftar, detail, dashboard, facets | ± 1.400 | **~1 inti** | terikat GIL satu proses Python; murah |
| Pencarian leksikal | ± 1.000 | ~2 inti | murah |
| **Pencarian hybrid** (embedding e5-large + matriks 12.914×1.024) | **± 145** | **~11 inti** | **sepuluh kali lebih mahal**; menghabiskan hampir seluruh CPU |

Akibatnya kapasitas campuran **sangat bergantung pada porsi pencarian semantik**. Dalam
campuran uji ini pencarian lsa/hybrid/semantik/klausul ≈ 16% permintaan; bila pengguna
lebih banyak menelusuri tabel daripada mencari makna, kapasitas nyata lebih tinggi dari
490 req/s; bila hampir semuanya pencarian semantik, mendekati 145 req/s.

Latensi satu pengguna tetap baik (14–36 ms) karena satu kueri boleh memakai semua inti.
Di bawah beban, inti yang sama diperebutkan semua kueri — latensi naik hampir linear
dengan jumlah koneksi (p95 ≈ 2,7–3 ms per koneksi), pola antrean klasik di titik jenuh.

## 4. Temuan untuk perencanaan (bukan perubahan yang saya buat)

1. **Menambah worker tidak menambah kapasitas pada satu mesin.** 4 worker: puncak 627 req/s
   (vs 490), batas sehat turun ke 400 koneksi (vs 800), RAM **7,2 GB** (vs 2,5 GB), dan hasil
   lebih bergejolak. Penyebab: tiap worker memuat model dan matriks vektor sendiri (± 1,8–2,5 GB) dan semuanya
   memperebutkan inti yang sama. Untuk VPS: **mulai dengan 1 worker**; tambah worker hanya
   bila ada inti cadangan *dan* RAM ≥ 2,5 GB × jumlah worker.
2. **RAM adalah biaya tetap ± 2–2,5 GB per worker** (e5-large + matriks vektor). Ini yang
   harus dicek terhadap spesifikasi VPS, bukan CPU.
3. **Membatasi thread BLAS/OpenMP (`OMP_NUM_THREADS=1`) tidak membantu** (diuji: 490 → 501 req/s,
   dalam derau). Hipotesis itu saya coba dan gugur.
4. **Korpus membesar → pencarian semantik membesar linear** (matriks dikalikan penuh per kueri).
   Pada 12.914 potongan 13 ms; tolok ukur `hero bench-vektor` sudah membandingkan SQLite vs
   pgvector untuk saat itu tiba. Jalankan ulang `hero loadtest` setiap korpus naik ≥ 2×.
5. **`server/app.py` memegang satu `RLock` global** untuk semua endpoint KB, jadi halaman KB
   berjalan serial dalam satu proses. Itu aman dan cukup cepat (1.400 req/s), tetapi bila
   kelak halaman KB menjadi penghambat, kuncinya yang pertama ditinjau. Tidak saya ubah:
   tidak ada bukti ia membatasi pada beban yang realistis.
6. **Batas memori `hero-ml.service` terlalu kecil untuk pencarian semantik.**
   Terukur pada profil `ml`: jalur Deterministik (lexical + LSA) memakai
   **347–530 MB**, tetapi begitu model e5-large dimuat RSS menjadi
   **1.950–2.250 MB**. Unit systemd sebelumnya membatasi `MemoryMax=600M`.
   Yang membuatnya berbahaya: `GET /api/v1/ml/cari` **default-nya
   `metode=hybrid`**, dan hybrid memuat model semantik — jadi satu permintaan
   tanpa `metode` eksplisit sudah cukup untuk menembus batas dan membuat
   systemd mematikan layanan. Unit sudah disesuaikan untuk skenario Deterministik
   (kini `MemoryMax=900M` tanpa `MemoryHigh` — lihat butir 8), dengan skenario semantik dicatat di komentarnya.
   Langkah di VPS: [`VPS_FASE2_LANGKAH.md`](VPS_FASE2_LANGKAH.md) §4.
7. **Layanan analisa (`/api/v1/ml/*`)** lebih lambat daripada server acuan: puncak ± 160 req/s,
   dan **turun** menjadi ± 105 req/s pada 200 koneksi (p95 2,7 s, nyaris di batas). Menurun
   di bawah beban berarti ada perebutan sumber daya, bukan sekadar antrean. Layak diselidiki
   sebelum Fase 3 membebaninya dengan harmonisasi. Catatan: pengukuran memakai peta dokumen
   salinan uji (60 dokumen) dan tidak mencakup `POST /harmonisasi` maupun `/pasal-mirip`
   (butuh Postgres backend).
8. **Skala korpus mengubah profil memori — diukur di VPS, 13 Okt.** Korpus server berisi **207–212 ribu
   potongan** (laptop: 12.914). Pada skala itu: build LSA bawaan dimatikan OOM-killer di ±1,0 GB;
   `index()` lama memuncak di **952 MB** walau pelatihan sudah bersampel; dan memuat matriks pencarian
   NumPy menahan 217 MB tetap di proses layanan. Perbaikan (semuanya terukur pada korpus sintetis seukuran
   server): `index()` kini memuncak di **651 MB**, pelatihan LSA bersampel (`vector.lsa_fit_sample`), dan
   pencarian dari disk di atas `vector.numpy_max_rows` (anon layanan ≈ **180 MB**). **Koreksi atas klaim saya
   sendiri:** cache halaman indeks (≈570 MB) ikut dihitung ke cgroup, dan `MemoryHigh=550M` yang saya pasang
   membuat kernel terus membuangnya hingga tiap kueri membaca disk (**2,2 s**, `memory.events high`=838).
   Tanpa `MemoryHigh`: **±0,23 s**. Angka 210–248 MB yang sempat tercatat diambil sebelum cache terisi.

## 5. Batas pengukuran ini (jangan dilewatkan)

- **Satu mesin untuk server dan pembangkit beban.** Laporan menampilkan CPU klien; pada semua
  pengukuran final ≤ 17% — pembangkit bukan penghambat. Mesin terpisah bisa memberi angka lebih
  tinggi, bukan lebih rendah.
- **Laptop 12 inti bukan VPS.** Pola (semantik mahal, RAM per worker, antrean linear) berlaku
  umum; angka absolut tidak. Jalankan ulang di VPS: `hero loadtest --url https://…` mengukur
  server yang sudah berjalan, termasuk lewat reverse proxy.
- **Hanya GET.** Unggah, pemindaian, ekstraksi, dan harmonisasi (pekerjaan latar yang berat)
  tidak diukur di sini. Waktu proses per dokumen: `hero fase2` (11,5 s terburuk vs target 300 s).
- **Server acuan, bukan backend tim.** Backend aplikasi (Postgres, proxy, autentikasi) milik
  peran Backend; alat ini dapat diarahkan ke sana dengan `--url` bila endpoint-nya ditambahkan
  ke profil, tetapi itu di luar lingkup saya.
- **Hasil 4-worker bergejolak** (dua pengukuran berbeda ± 10% pada puncak). Perlakukan sebagai arah, bukan angka.
- **Perkiraan "pengguna nyata"** bergantung pada jeda berpikir yang saya asumsikan 5 detik.
  Ubah dengan `--think-time` setelah ada data perilaku pengguna dari UAT.

## 6. Cara menjalankan

```bash
cd <workspace>                                   # mis. ../Capstone
hero loadtest --berat                            # luncurkan server sendiri, 1 worker, cari batas
hero loadtest --workers 2 --berat                # bandingkan jumlah worker
hero loadtest --profil ml                        # layanan analisa/harmonisasi
hero loadtest --url https://staging.example/ --level 1,5,20,50   # server yang sudah berjalan
hero loadtest --endpoint cari-hybrid --level 1,10,50             # satu endpoint saja
hero loadtest --strict                           # gerbang: keluar kode 1 bila p95 satu pengguna > 3 s
```

Hanya permintaan GET; tidak mengubah data. Server yang diluncurkan sendiri membaca katalog
yang sama dengan `hero serve` — arahkan ke salinan workspace bila tidak ingin menyentuh yang asli.
