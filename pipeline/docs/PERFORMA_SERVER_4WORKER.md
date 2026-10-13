# Performa Server — Latensi & Kapasitas

*Dihasilkan oleh `hero loadtest` pada 2026-10-10 09:13:22. Semua angka diukur ulang setiap perintah dijalankan.*

- **Target:** profil `api` · server diluncurkan sendiri dengan **4 worker**
- **Mesin uji:** 12 inti CPU · darwin · Python 3.14.7 — pembangkit beban dan server berbagi mesin yang sama.
- **Cold start:** 0,5 detik dari proses dimulai sampai `/health` menjawab.
- **Isi katalog:** 40 dokumen dipakai sebagai contoh akses detail.
- **Batas mutu:** p95 ≤ 3.000 ms (NFR-02) dan galat ≤ 1%.

## Jawaban singkat

- **Pengguna serentak maksimum yang sehat:** **400** koneksi yang menembak tanpa jeda (450,2 permintaan/detik).
- **Perkiraan pengguna nyata:** ± **2640** orang bekerja bersamaan, bila tiap orang beraksi sekali per 5 detik *(turunan: throughput × (jeda + waktu layan); bukan hasil ukur langsung)*.
- **Throughput puncak:** 626,6 permintaan/detik pada 100 pengguna.
- **Batas pertama terlampaui di 800 pengguna:** p95 5722 ms > 3000 ms.

## 1. Latensi satu pengguna (tanpa persaingan)

| Endpoint | n | p50 ms | p95 ms | p99 ms | maks ms | galat |
|---|---:|---:|---:|---:|---:|---:|
| analisa-klausul | 30 | 17,9 | 37,5 | 39,2 | 39,2 | 0 |
| cari-hybrid | 30 | 15,6 | 21,8 | 22,7 | 22,7 | 0 |
| cari-semantik | 30 | 13,7 | 14,2 | 14,3 | 14,3 | 0 |
| cari-lsa | 30 | 10,9 | 12,2 | 13,3 | 13,3 | 0 |
| analisa | 30 | 1,2 | 2,9 | 3,8 | 3,8 | 0 |
| cari-lexical | 30 | 1,6 | 2,6 | 2,9 | 2,9 | 0 |
| graf-statistik | 30 | 1,6 | 2,0 | 2,7 | 2,7 | 0 |
| dashboard | 30 | 1,8 | 2,0 | 2,1 | 2,1 | 0 |
| kb-cari-leksikal | 30 | 0,8 | 1,8 | 1,9 | 1,9 | 0 |
| kb-daftar-filter | 30 | 1,0 | 1,0 | 1,1 | 1,1 | 0 |
| kb-relasi | 30 | 0,8 | 0,9 | 0,9 | 0,9 | 0 |
| kb-daftar | 30 | 0,6 | 0,7 | 0,7 | 0,7 | 0 |
| kb-facets | 30 | 0,6 | 0,7 | 0,7 | 0,7 | 0 |
| health | 30 | 0,4 | 0,6 | 0,6 | 0,6 | 0 |
| kb-detail | 30 | 0,4 | 0,4 | 0,5 | 0,5 | 0 |

## 2. Beban serentak

Tiap level berjalan 10 detik setelah pemanasan 2 detik; pengguna virtual mengirim permintaan berurutan tanpa jeda dengan campuran endpoint di bagian 4.

| Pengguna | req/s | p50 ms | p95 ms | p99 ms | maks ms | galat | RAM server MB | CPU server % | CPU klien | Sehat |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|
| 1 | 317,0 | 1,1 | 14,7 | 16,9 | 59,3 | 0,0% | 6.077,5 | 461 | 3% | ✅ |
| 2 | 453,4 | 1,5 | 20,1 | 31,2 | 64,2 | 0,0% | 6.430,7 | 818 | 5% | ✅ |
| 5 | 465,2 | 4,5 | 43,8 | 78,2 | 250,7 | 0,0% | 6.745,5 | 1.088 | 9% | ✅ |
| 10 | 393,3 | 9,8 | 99,1 | 206,8 | 1.394,9 | 0,0% | 6.206,8 | 1.110 | 9% | ✅ |
| 25 | 497,2 | 26,4 | 168,1 | 370,9 | 778,7 | 0,0% | 6.461,9 | 1.161 | 12% | ✅ |
| 50 | 551,1 | 55,7 | 295,5 | 418,9 | 743,2 | 0,0% | 6.603,5 | 1.124 | 13% | ✅ |
| 100 | 626,6 | 138,1 | 344,7 | 542,4 | 852,1 | 0,0% | 7.106,1 | 1.148 | 15% | ✅ |
| 200 | 463,8 | 383,0 | 1.133,1 | 1.572,9 | 1.828,3 | 0,0% | 7.246,9 | 1.135 | 12% | ✅ |
| 400 | 450,2 | 650,7 | 2.422,7 | 3.426,0 | 3.727,4 | 0,0% | 6.833,2 | 1.048 | 13% | ✅ |
| 800 | 376,1 | 1.316,4 | 5.721,9 | 6.701,7 | 6.854,7 | 0,0% | 7.165,0 | 1.039 | 14% | ❌ |

## 3. Endpoint paling lambat di bawah beban

Dari level 400 pengguna (level sehat tertinggi, atau terakhir bila tak ada):

| Endpoint | n | p50 ms | p95 ms | galat |
|---|---:|---:|---:|---:|
| kb-facets | 236 | 779,6 | 3.154,7 | 0 |
| kb-daftar | 728 | 771,1 | 3.151,0 | 0 |
| kb-daftar-filter | 363 | 813,1 | 3.095,9 | 0 |
| kb-detail | 490 | 775,3 | 2.984,8 | 0 |
| kb-cari-leksikal | 577 | 799,4 | 2.513,4 | 0 |
| cari-semantik | 104 | 654,3 | 2.080,8 | 0 |
| cari-lsa | 254 | 622,2 | 2.005,6 | 0 |
| analisa | 359 | 525,3 | 1.929,4 | 0 |

## 4. Campuran beban & endpoint dilewati

Bobot kemunculan per sesi pengguna: `kb-daftar` 16%, `kb-cari-leksikal` 13%, `kb-detail` 11%, `dashboard` 8%, `kb-daftar-filter` 8%, `analisa` 8%, `cari-lexical` 8%, `kb-facets` 5%, `cari-lsa` 5%, `cari-hybrid` 5%, `health` 3%, `kb-relasi` 3%, `analisa-klausul` 3%, `cari-semantik` 3%, `graf-statistik` 3%.

## Cara membaca & batasnya

- **Closed-loop tanpa jeda** adalah skenario terburuk bagi server; ribuan orang yang sesekali mengklik jauh lebih ringan daripada ratusan koneksi yang menembak terus.
- **Pembangkit beban Python** dibatasi satu inti (GIL). Peringatan ⚠ di atas muncul bila itu menjadi penghambat; gunakan mesin terpisah untuk batas atas yang sebenarnya.
- **Pembangkit dan server di satu mesin** saling berebut CPU; hasil di mesin produksi dengan klien terpisah umumnya lebih baik, bukan lebih buruk.
- Data adalah katalog nyata pada saat uji. Setelah korpus membesar, **jalankan ulang** — laporan ini sengaja dapat dieksekusi ulang, bukan dikutip.
- Hanya endpoint **baca (GET)** yang diuji. Unggah, pemindaian, dan harmonisasi (pekerjaan latar yang berat) tidak diukur di sini; waktu proses per dokumen ada di `hero fase2`.
- Ini menguji **API lapisan data** (`hero serve` / `hero bridge layanan`), bukan backend aplikasi tim — itu milik peran Backend dan memiliki infrastruktur (Postgres, proxy) berbeda.
