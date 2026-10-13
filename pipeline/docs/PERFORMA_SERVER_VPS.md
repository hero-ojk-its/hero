# Performa Server — Latensi & Kapasitas

*Dihasilkan oleh `hero loadtest` pada 2026-10-13 10:44:56. Semua angka diukur ulang setiap perintah dijalankan.*

- **Target:** profil `ml` · server yang sudah berjalan di `http://172.17.0.1:8100`
- **Mesin uji:** 2 inti CPU · linux · Python 3.12.3 — pembangkit beban dan server berbagi mesin yang sama.
- ⚠ **Subset endpoint:** hanya `dokumen`, `analisa`, `analisa-klausul`, `cari-lsa`, `cari-lexical`, `health` — bukan campuran sesi pengguna; jangan dibaca sebagai kapasitas aplikasi utuh.
- **Isi katalog:** 40 dokumen dipakai sebagai contoh akses detail.
- **Batas mutu:** p95 ≤ 3.000 ms (NFR-02) dan galat ≤ 1%.

## Jawaban singkat

- **Pengguna serentak maksimum yang sehat:** **12** koneksi yang menembak tanpa jeda (20,1 permintaan/detik).
- **Perkiraan pengguna nyata:** ± **113** orang bekerja bersamaan, bila tiap orang beraksi sekali per 5 detik *(turunan: throughput × (jeda + waktu layan); bukan hasil ukur langsung)*.
- **Throughput puncak:** 23,4 permintaan/detik pada 1 pengguna.
- **Batas belum ditemukan** — level tertinggi yang diuji pun masih sehat. Naikkan `--level` untuk mencarinya.
- Karena batas belum ditemukan, kedua angka pengguna di atas adalah **batas bawah** (≥), bukan kapasitas sebenarnya.

## 1. Latensi satu pengguna (tanpa persaingan)

| Endpoint | n | p50 ms | p95 ms | p99 ms | maks ms | galat |
|---|---:|---:|---:|---:|---:|---:|
| analisa-klausul | 15 | 107,2 | 325,4 | 325,4 | 325,4 | 0 |
| cari-lsa | 15 | 171,7 | 210,3 | 210,3 | 210,3 | 0 |
| cari-lexical | 15 | 57,7 | 96,2 | 96,2 | 96,2 | 0 |
| analisa | 15 | 11,0 | 45,6 | 45,6 | 45,6 | 0 |
| health | 15 | 12,5 | 16,6 | 16,6 | 16,6 | 0 |
| dokumen | 15 | 2,3 | 2,7 | 2,7 | 2,7 | 0 |

## 2. Beban serentak

Tiap level berjalan 8 detik setelah pemanasan 2 detik; pengguna virtual mengirim permintaan berurutan tanpa jeda dengan campuran endpoint di bagian 4.

| Pengguna | req/s | p50 ms | p95 ms | p99 ms | maks ms | galat | RAM server MB | CPU server % | CPU klien | Sehat |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|:---:|
| 1 | 23,4 | 12,3 | 168,5 | 220,3 | 228,4 | 0,0% | — | — | 1% | ✅ |
| 3 | 14,1 | 90,5 | 816,5 | 845,4 | 882,0 | 0,0% | — | — | 1% | ✅ |
| 6 | 13,9 | 175,8 | 1.284,7 | 1.427,7 | 1.582,4 | 0,0% | — | — | 1% | ✅ |
| 12 | 20,1 | 342,9 | 1.706,4 | 3.215,3 | 4.430,6 | 0,0% | — | — | 1% | ✅ |

## 3. Endpoint paling lambat di bawah beban

Dari level 12 pengguna (level sehat tertinggi, atau terakhir bila tak ada):

| Endpoint | n | p50 ms | p95 ms | galat |
|---|---:|---:|---:|---:|
| cari-lsa | 18 | 1.672,6 | 4.430,6 | 0 |
| analisa-klausul | 26 | 909,8 | 1.706,4 | 0 |
| cari-lexical | 19 | 515,0 | 1.565,2 | 0 |
| health | 13 | 338,0 | 598,8 | 0 |
| dokumen | 36 | 192,0 | 517,1 | 0 |
| analisa | 49 | 199,0 | 494,8 | 0 |

## 4. Campuran beban & endpoint dilewati

Bobot kemunculan per sesi pengguna: `analisa` 29%, `dokumen` 21%, `analisa-klausul` 14%, `cari-lsa` 14%, `cari-lexical` 14%, `health` 7%.

## Cara membaca & batasnya

- **Closed-loop tanpa jeda** adalah skenario terburuk bagi server; ribuan orang yang sesekali mengklik jauh lebih ringan daripada ratusan koneksi yang menembak terus.
- **Pembangkit beban Python** dibatasi satu inti (GIL). Peringatan ⚠ di atas muncul bila itu menjadi penghambat; gunakan mesin terpisah untuk batas atas yang sebenarnya.
- **Pembangkit dan server di satu mesin** saling berebut CPU; hasil di mesin produksi dengan klien terpisah umumnya lebih baik, bukan lebih buruk.
- Data adalah katalog nyata pada saat uji. Setelah korpus membesar, **jalankan ulang** — laporan ini sengaja dapat dieksekusi ulang, bukan dikutip.
- Hanya endpoint **baca (GET)** yang diuji. Unggah, pemindaian, dan harmonisasi (pekerjaan latar yang berat) tidak diukur di sini; waktu proses per dokumen ada di `hero fase2`.
- Ini menguji **API lapisan data** (`hero serve` / `hero bridge layanan`), bukan backend aplikasi tim — itu milik peran Backend dan memiliki infrastruktur (Postgres, proxy) berbeda.
