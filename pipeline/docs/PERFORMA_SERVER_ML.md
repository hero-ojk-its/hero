# Performa Server — Latensi & Kapasitas

*Dihasilkan oleh `hero loadtest` pada 2026-10-10 09:21:24. Semua angka diukur ulang setiap perintah dijalankan.*

- **Target:** profil `ml` · server diluncurkan sendiri dengan **1 worker**
- **Mesin uji:** 12 inti CPU · darwin · Python 3.14.7 — pembangkit beban dan server berbagi mesin yang sama.
- **Cold start:** 0,3 detik dari proses dimulai sampai `/health` menjawab.
- **Isi katalog:** 40 dokumen dipakai sebagai contoh akses detail.
- **Batas mutu:** p95 ≤ 3.000 ms (NFR-02) dan galat ≤ 1%.

## Jawaban singkat

- **Pengguna serentak maksimum yang sehat:** **200** koneksi yang menembak tanpa jeda (104,5 permintaan/detik).
- **Perkiraan pengguna nyata:** ± **699** orang bekerja bersamaan, bila tiap orang beraksi sekali per 5 detik *(turunan: throughput × (jeda + waktu layan); bukan hasil ukur langsung)*.
- **Throughput puncak:** 159,1 permintaan/detik pada 10 pengguna.
- **Batas belum ditemukan** — level tertinggi yang diuji pun masih sehat. Naikkan `--level` untuk mencarinya.
- Karena batas belum ditemukan, kedua angka pengguna di atas adalah **batas bawah** (≥), bukan kapasitas sebenarnya.

## 1. Latensi satu pengguna (tanpa persaingan)

| Endpoint | n | p50 ms | p95 ms | p99 ms | maks ms | galat |
|---|---:|---:|---:|---:|---:|---:|
| analisa-klausul | 30 | 15,0 | 20,3 | 22,9 | 22,9 | 0 |
| cari | 30 | 14,2 | 16,0 | 16,2 | 16,2 | 0 |
| cari-lsa | 30 | 10,0 | 10,7 | 10,8 | 10,8 | 0 |
| analisa | 30 | 1,3 | 3,0 | 3,0 | 3,0 | 0 |
| cari-lexical | 30 | 1,4 | 2,2 | 2,2 | 2,2 | 0 |
| health | 30 | 1,4 | 1,7 | 1,8 | 1,8 | 0 |
| dokumen | 30 | 1,0 | 1,2 | 1,2 | 1,2 | 0 |

## 2. Beban serentak

Tiap level berjalan 8 detik setelah pemanasan 2 detik; pengguna virtual mengirim permintaan berurutan tanpa jeda dengan campuran endpoint di bagian 4.

| Pengguna | req/s | p50 ms | p95 ms | p99 ms | maks ms | galat | RAM server MB | CPU server % | CPU klien | Sehat |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|
| 1 | 141,8 | 2,1 | 16,0 | 20,5 | 30,9 | 0,0% | 1.949,0 | 547 | 2% | ✅ |
| 10 | 159,1 | 53,0 | 159,3 | 188,3 | 227,6 | 0,0% | 2.101,3 | 872 | 3% | ✅ |
| 50 | 115,1 | 393,2 | 873,6 | 922,2 | 982,7 | 0,0% | 2.223,0 | 780 | 2% | ✅ |
| 200 | 104,5 | 1.515,3 | 2.717,4 | 2.803,9 | 2.839,2 | 0,0% | 2.248,5 | 823 | 2% | ✅ |

## 3. Endpoint paling lambat di bawah beban

Dari level 200 pengguna (level sehat tertinggi, atau terakhir bila tak ada):

| Endpoint | n | p50 ms | p95 ms | galat |
|---|---:|---:|---:|---:|
| cari | 182 | 1.676,6 | 2.803,1 | 0 |
| cari-lexical | 72 | 1.572,4 | 2.697,4 | 0 |
| analisa-klausul | 88 | 1.479,8 | 2.639,1 | 0 |
| cari-lsa | 100 | 1.512,4 | 2.631,8 | 0 |
| dokumen | 162 | 1.500,5 | 2.466,9 | 0 |
| health | 46 | 1.471,0 | 1.919,6 | 0 |
| analisa | 186 | 1.452,3 | 1.766,2 | 0 |

## 4. Campuran beban & endpoint dilewati

Bobot kemunculan per sesi pengguna: `analisa` 22%, `cari` 22%, `dokumen` 17%, `analisa-klausul` 11%, `cari-lsa` 11%, `cari-lexical` 11%, `health` 6%.

## Cara membaca & batasnya

- **Closed-loop tanpa jeda** adalah skenario terburuk bagi server; ribuan orang yang sesekali mengklik jauh lebih ringan daripada ratusan koneksi yang menembak terus.
- **Pembangkit beban Python** dibatasi satu inti (GIL). Peringatan ⚠ di atas muncul bila itu menjadi penghambat; gunakan mesin terpisah untuk batas atas yang sebenarnya.
- **Pembangkit dan server di satu mesin** saling berebut CPU; hasil di mesin produksi dengan klien terpisah umumnya lebih baik, bukan lebih buruk.
- Data adalah katalog nyata pada saat uji. Setelah korpus membesar, **jalankan ulang** — laporan ini sengaja dapat dieksekusi ulang, bukan dikutip.
- Hanya endpoint **baca (GET)** yang diuji. Unggah, pemindaian, dan harmonisasi (pekerjaan latar yang berat) tidak diukur di sini; waktu proses per dokumen ada di `hero fase2`.
- Ini menguji **API lapisan data** (`hero serve` / `hero bridge layanan`), bukan backend aplikasi tim — itu milik peran Backend dan memiliki infrastruktur (Postgres, proxy) berbeda.
