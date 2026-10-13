# Performa Server — Latensi & Kapasitas

*Dihasilkan oleh `hero loadtest` pada 2026-10-10 09:09:10. Semua angka diukur ulang setiap perintah dijalankan.*

- **Target:** profil `api` · server diluncurkan sendiri dengan **1 worker**
- **Mesin uji:** 12 inti CPU · darwin · Python 3.14.7 — pembangkit beban dan server berbagi mesin yang sama.
- **Cold start:** 0,5 detik dari proses dimulai sampai `/health` menjawab.
- **Isi katalog:** 40 dokumen dipakai sebagai contoh akses detail.
- **Batas mutu:** p95 ≤ 3.000 ms (NFR-02) dan galat ≤ 1%.

## Jawaban singkat

- **Pengguna serentak maksimum yang sehat:** **800** koneksi yang menembak tanpa jeda (490,2 permintaan/detik).
- **Perkiraan pengguna nyata:** ± **3231** orang bekerja bersamaan, bila tiap orang beraksi sekali per 5 detik *(turunan: throughput × (jeda + waktu layan); bukan hasil ukur langsung)*.
- **Throughput puncak:** 490,2 permintaan/detik pada 800 pengguna.
- **Batas pertama terlampaui di 1600 pengguna:** p95 4529 ms > 3000 ms.

## 1. Latensi satu pengguna (tanpa persaingan)

| Endpoint | n | p50 ms | p95 ms | p99 ms | maks ms | galat |
|---|---:|---:|---:|---:|---:|---:|
| analisa-klausul | 30 | 18,1 | 36,0 | 38,1 | 38,1 | 0 |
| cari-hybrid | 30 | 15,1 | 18,8 | 20,1 | 20,1 | 0 |
| cari-semantik | 30 | 13,4 | 14,0 | 14,0 | 14,0 | 0 |
| cari-lsa | 30 | 10,7 | 11,9 | 13,6 | 13,6 | 0 |
| analisa | 30 | 1,1 | 2,5 | 3,9 | 3,9 | 0 |
| cari-lexical | 30 | 1,5 | 2,1 | 2,2 | 2,2 | 0 |
| dashboard | 30 | 1,7 | 1,8 | 1,8 | 1,8 | 0 |
| kb-cari-leksikal | 30 | 0,8 | 1,7 | 1,8 | 1,8 | 0 |
| graf-statistik | 30 | 1,5 | 1,7 | 1,7 | 1,7 | 0 |
| kb-daftar-filter | 30 | 1,0 | 1,0 | 1,1 | 1,1 | 0 |
| kb-relasi | 30 | 0,8 | 0,9 | 0,9 | 0,9 | 0 |
| kb-facets | 30 | 0,6 | 0,7 | 0,7 | 0,7 | 0 |
| kb-daftar | 30 | 0,6 | 0,6 | 0,7 | 0,7 | 0 |
| kb-detail | 30 | 0,4 | 0,4 | 0,5 | 0,5 | 0 |
| health | 30 | 0,3 | 0,4 | 0,4 | 0,4 | 0 |

## 2. Beban serentak

Tiap level berjalan 10 detik setelah pemanasan 2 detik; pengguna virtual mengirim permintaan berurutan tanpa jeda dengan campuran endpoint di bagian 4.

| Pengguna | req/s | p50 ms | p95 ms | p99 ms | maks ms | galat | RAM server MB | CPU server % | CPU klien | Sehat |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|
| 1 | 322,3 | 1,1 | 14,4 | 16,4 | 56,0 | 0,0% | 2.022,4 | 455 | 3% | ✅ |
| 2 | 426,2 | 1,8 | 20,2 | 29,4 | 61,7 | 0,0% | 2.105,1 | 604 | 4% | ✅ |
| 5 | 475,5 | 5,5 | 36,0 | 50,1 | 78,7 | 0,0% | 2.244,7 | 681 | 5% | ✅ |
| 10 | 483,1 | 15,1 | 51,0 | 68,6 | 107,8 | 0,0% | 2.259,2 | 737 | 6% | ✅ |
| 25 | 478,5 | 48,4 | 95,2 | 129,0 | 185,4 | 0,0% | 2.297,6 | 726 | 6% | ✅ |
| 50 | 467,0 | 102,9 | 164,8 | 208,4 | 268,7 | 0,0% | 2.410,7 | 667 | 6% | ✅ |
| 100 | 464,8 | 214,3 | 309,8 | 342,9 | 399,8 | 0,0% | 2.424,1 | 664 | 6% | ✅ |
| 200 | 466,1 | 447,4 | 602,3 | 632,4 | 654,2 | 0,0% | 2.438,1 | 704 | 6% | ✅ |
| 400 | 477,2 | 929,7 | 1.158,9 | 1.221,9 | 1.262,1 | 0,0% | 2.459,4 | 658 | 7% | ✅ |
| 800 | 490,2 | 1.607,8 | 2.168,3 | 2.193,0 | 2.209,1 | 0,0% | 2.481,0 | 676 | 8% | ✅ |
| 1600 | 451,4 | 2.683,8 | 4.529,3 | 4.623,7 | 4.720,4 | 0,0% | 2.517,2 | 675 | 10% | ❌ |

## 3. Endpoint paling lambat di bawah beban

Dari level 800 pengguna (level sehat tertinggi, atau terakhir bila tak ada):

| Endpoint | n | p50 ms | p95 ms | galat |
|---|---:|---:|---:|---:|
| kb-detail | 546 | 2.103,8 | 2.184,0 | 0 |
| kb-cari-leksikal | 625 | 2.098,9 | 2.183,2 | 0 |
| kb-daftar | 776 | 2.095,8 | 2.182,1 | 0 |
| kb-facets | 253 | 2.094,7 | 2.179,7 | 0 |
| kb-daftar-filter | 403 | 2.098,3 | 2.176,1 | 0 |
| graf-statistik | 128 | 1.078,4 | 1.209,5 | 0 |
| cari-hybrid | 251 | 1.114,6 | 1.207,5 | 0 |
| cari-semantik | 129 | 1.099,7 | 1.205,0 | 0 |

## 4. Campuran beban & endpoint dilewati

Bobot kemunculan per sesi pengguna: `kb-daftar` 16%, `kb-cari-leksikal` 13%, `kb-detail` 11%, `dashboard` 8%, `kb-daftar-filter` 8%, `analisa` 8%, `cari-lexical` 8%, `kb-facets` 5%, `cari-lsa` 5%, `cari-hybrid` 5%, `health` 3%, `kb-relasi` 3%, `analisa-klausul` 3%, `cari-semantik` 3%, `graf-statistik` 3%.

## Cara membaca & batasnya

- **Closed-loop tanpa jeda** adalah skenario terburuk bagi server; ribuan orang yang sesekali mengklik jauh lebih ringan daripada ratusan koneksi yang menembak terus.
- **Pembangkit beban Python** dibatasi satu inti (GIL). Peringatan ⚠ di atas muncul bila itu menjadi penghambat; gunakan mesin terpisah untuk batas atas yang sebenarnya.
- **Pembangkit dan server di satu mesin** saling berebut CPU; hasil di mesin produksi dengan klien terpisah umumnya lebih baik, bukan lebih buruk.
- Data adalah katalog nyata pada saat uji. Setelah korpus membesar, **jalankan ulang** — laporan ini sengaja dapat dieksekusi ulang, bukan dikutip.
- Hanya endpoint **baca (GET)** yang diuji. Unggah, pemindaian, dan harmonisasi (pekerjaan latar yang berat) tidak diukur di sini; waktu proses per dokumen ada di `hero fase2`.
- Ini menguji **API lapisan data** (`hero serve` / `hero bridge layanan`), bukan backend aplikasi tim — itu milik peran Backend dan memiliki infrastruktur (Postgres, proxy) berbeda.
