# Laporan Mutu Data HERO

*Dihasilkan otomatis oleh `hero dq --markdown` pada 20 September 2026 21:08.*

**Kesimpulan:** ⚠️ `perlu-perbaikan` — skor mutu keseluruhan **97.6%**

## Skor per dimensi

| Dimensi | Skor | Hasil | Aturan | Lulus | Perhatian | Gagal |
|---|---:|:---:|---:|---:|---:|---:|
| completeness | 98.9% | ⚠️ | 7 | 6 | 1 | 0 |
| validity | 100.0% | ✅ | 5 | 5 | 0 | 0 |
| uniqueness | 98.1% | ❌ | 2 | 1 | 0 | 1 |
| consistency | 97.5% | ⚠️ | 4 | 2 | 2 | 0 |
| timeliness | 99.8% | ✅ | 1 | 1 | 0 | 0 |
| accuracy | 91.4% | ❌ | 2 | 0 | 1 | 1 |

## Rincian aturan

| ID | Dataset | Dimensi | Keparahan | Pelanggar | Lingkup | Rasio | Ambang | Hasil |
|---|---|---|---|---:|---:|---:|---:|:---:|
| ART-C01 | articles | completeness | major | 0 | 1597 | 0.0% | 0.0% | ✅ |
| DOC-C01 | documents | completeness | blocker | 0 | 63 | 0.0% | 0.0% | ✅ |
| DOC-C02 | documents | completeness | major | 5 | 63 | 7.9% | 15.0% | ⚠️ |
| DOC-G01 | documents | accuracy | major | 6 | 63 | 9.5% | 0.0% | ❌ |
| DOC-S01 | documents | consistency | major | 2 | 55 | 3.6% | 5.0% | ⚠️ |
| DOC-S02 | documents | consistency | minor | 0 | 1 | 0.0% | 0.0% | ✅ |
| DOC-U01 | documents | uniqueness | blocker | 0 | 63 | 0.0% | 0.0% | ✅ |
| DOC-V01 | documents | validity | major | 0 | 63 | 0.0% | 0.0% | ✅ |
| DOC-V02 | documents | validity | blocker | 0 | 63 | 0.0% | 0.0% | ✅ |
| INV-A01 | inventory | accuracy | major | 83 | 1092 | 7.6% | 10.0% | ⚠️ |
| INV-C01 | inventory | completeness | blocker | 0 | 3206 | 0.0% | 0.0% | ✅ |
| INV-C02 | inventory | completeness | major | 0 | 2556 | 0.0% | 2.0% | ✅ |
| INV-C03 | inventory | completeness | major | 15 | 2556 | 0.6% | 2.0% | ✅ |
| INV-C04 | inventory | completeness | minor | 52 | 2556 | 2.0% | 5.0% | ✅ |
| INV-S01 | inventory | consistency | major | 0 | 561 | 0.0% | 0.0% | ✅ |
| INV-S02 | inventory | consistency | minor | 197 | 2504 | 7.9% | 10.0% | ⚠️ |
| INV-T01 | inventory | timeliness | minor | 7 | 3206 | 0.2% | 2.0% | ✅ |
| INV-U01 | inventory | uniqueness | major | 144 | 2504 | 5.8% | 3.0% | ❌ |
| INV-V01 | inventory | validity | major | 0 | 3206 | 0.0% | 0.0% | ✅ |
| INV-V02 | inventory | validity | blocker | 0 | 3206 | 0.0% | 0.0% | ✅ |
| INV-V03 | inventory | validity | major | 0 | 2307 | 0.0% | 0.0% | ✅ |

### Aturan yang perlu ditindaklanjuti

#### INV-U01 — Satu peraturan tercatat sekali per sumber

- **Hasil:** ❌ `gagal` · 144/2504 (5.8%) · ambang 3.0%
- **Dasar ambang:** Satu peraturan dapat muncul di kanal 'semua sektor' sekaligus di kanal sektornya sendiri, dengan URL detail berbeda. Duplikat membuat setiap hitungan populasi melebih-lebihkan jumlah peraturan yang sebenarnya ada.

  | record_key |
  |---|
  | https://ojk.go.id/id/regulasi/Pages/--Laporan-Bulanan-Perusa |
  | https://ojk.go.id/id/regulasi/Pages/Ahli-Syariah-Pasar-Modal |
  | https://ojk.go.id/id/regulasi/Pages/Akad-Yang-Digunakan-dala |
  | https://ojk.go.id/id/regulasi/Pages/BAPEPAM-II-K1-tentang-Kr |
  | https://ojk.go.id/id/regulasi/Pages/BAPEPAM-XI1-tentang-Peme |

#### INV-S02 — reg_key terbentuk bila jenis, nomor, dan tahun lengkap

- **Hasil:** ⚠️ `perhatian` · 197/2504 (7.9%) · ambang 10.0%
- **Dasar ambang:** Bila ketiga bahan tersedia namun kunci tidak terbentuk, pembentuk kunci tidak mengenali pola penomorannya. Penyebab terbesar adalah Keputusan Bapepam-LK (KEP-208/BL/2012) yang diawali huruf, bukan angka. Ambang 10% adalah pengakuan bahwa peraturan pra-OJK memang bercorak lain.

  | record_key |
  |---|
  | https://ojk.go.id/id/regulasi/Pages/Akad-akad-yang-Digunakan |
  | https://ojk.go.id/id/regulasi/Pages/BAPEPAM-II-A1-tentang-Do |
  | https://ojk.go.id/id/regulasi/Pages/BAPEPAM-II-A2-tentang-Pr |
  | https://ojk.go.id/id/regulasi/Pages/BAPEPAM-II-A3-tentang-Su |
  | https://ojk.go.id/id/regulasi/Pages/BAPEPAM-II-K1-tentang-Kr |

#### INV-A01 — Rekaman yang seharusnya dapat dicocokkan ke JDIH benar-benar memperoleh status

- **Hasil:** ⚠️ `perhatian` · 83/1092 (7.6%) · ambang 10.0%
- **Dasar ambang:** Inilah ukuran rekonsiliasi yang jujur. Menghitung seluruh 1.570 rekaman ojk.go.id sebagai penyebut adalah keliru: PBI, PMK, KMK, dan Keputusan Bapepam-LK memang tidak pernah diregister JDIH OJK, karena JDIH OJK adalah register milik OJK sendiri, bukan basis data hukum nasional. Hanya jenis yang benar-benar ada di JDIH yang boleh dituntut cocok.

  | record_key |
  |---|
  | https://ojk.go.id/id/regulasi/Pages/28-Tahun-2024-Pengelolaa |
  | https://ojk.go.id/id/regulasi/Pages/Asosiasi-Penyelenggara-I |
  | https://ojk.go.id/id/regulasi/Pages/Kesehatan-Keuangan-Perus |
  | https://ojk.go.id/id/regulasi/Pages/Lalu-Lintas-Devisa-Dan-S |
  | https://ojk.go.id/id/regulasi/Pages/Laporan-Bulanan-Pengelol |

#### DOC-C02 — Identitas peraturan lengkap (jenis, nomor, tahun)

- **Hasil:** ⚠️ `perhatian` · 5/63 (7.9%) · ambang 15.0%
- **Dasar ambang:** Ketiga field ini membentuk identitas yang dipakai fitur harmonisasi untuk merujuk peraturan secara eksplisit (URD 3.4). Ambang longgar karena knowledge base saat ini masih memuat berkas non-peraturan dari sesi pengujian.

  | doc_id | title |
  |---|---|
  | 55743ebebbe5478497be3a39a12e4891 | Peraturan Otoritas Jasa Keuangan tentang DERIVATIF KEUANGAN  |
  | 5ecbca91add3451cad465e5eb0087140 | HERO User Requirement Document |
  | a1ea5041bfb24b92bcd8839edf249e09 | 9f616d1f178e Dokumen testing ojk |
  | b6ab29b590d245a3ab7c7fc3093d0e58 | Peraturan Otoritas Jasa Keuangan tentang PENERAPAN TATA KELO |
  | cab13d02876243aa971559299c9c3829 | Peraturan Anggota Dewan Komisioner OJK tentang BENTUK DAN SU |

#### DOC-S01 — Peraturan berbentuk pasal menghasilkan pasal terparsing

- **Hasil:** ⚠️ `perhatian` · 2/55 (3.6%) · ambang 5.0%
- **Dasar ambang:** Surat Edaran sengaja tidak termasuk: ia disusun dalam seksi angka Romawi, sehingga nol pasal adalah bentuk normalnya. Untuk POJK atau UU, nol pasal berarti parser struktur gagal — dan pasal adalah unit pembanding fitur harmonisasi, sehingga dokumen itu tidak dapat dipakai sama sekali.

  | doc_id | doc_type | title |
  |---|---|---|
  | b6ab29b590d245a3ab7c7fc3093d0e58 | POJK | Peraturan Otoritas Jasa Keuangan tentang PENERAPAN TATA KELO |
  | bc74014b0c264ff891c5f8af87e45e82 | PADK | Peraturan Anggota Dewan Komisioner OJK Nomor 45/PADK.06/2025 |

#### DOC-G01 — Knowledge base bebas dari artefak pengujian

- **Hasil:** ❌ `gagal` · 6/63 (9.5%) · ambang 0.0%
- **Dasar ambang:** Berkas dari sesi pengujian yang mengendap di knowledge base membuat indikator Fase 1 ('minimal 20 dokumen') terpenuhi di atas kertas tanpa ada peraturan sungguhan yang bertambah. Pemisahan basis data uji dan produksi adalah syarat agar angka penerimaan dapat dipertanggungjawabkan.

  | doc_id | source_name | title |
  |---|---|---|
  | 4534cd5d488a49f4852c3abf81436cec | api-test | Peraturan Otoritas Jasa Keuangan Nomor 76/POJK.07/2016 tenta |
  | 5ecbca91add3451cad465e5eb0087140 | test-upload-regression | HERO User Requirement Document |
  | 5fc7921a42924e9182b7cd0e8a6fed84 | JDIH test | Peraturan Otoritas Jasa Keuangan Nomor 9/POJK.04/2017 tentan |
  | 728c693a27414ab1809ff50c9bc23de1 | JDIH test | Peraturan Otoritas Jasa Keuangan Nomor 9/POJK.04/2015 tentan |
  | cb73530ce550473b8706d6e7d00526d8 | JDIH test | Peraturan Otoritas Jasa Keuangan Nomor 9/POJK.04/2018 tentan |

## Cakupan rekonsiliasi status

Persentase hanya bermakna bila penyebutnya benar. JDIH OJK adalah register milik OJK sendiri, sehingga hanya jenis yang memang diregister di sana yang dapat dituntut cocok.

- Jenis yang diregister JDIH: `POJK, SEOJK, PADK, UU, PERPRES`
- Rekaman ojk.go.id seluruhnya: **1570**
- Di dalam semesta JDIH (dapat dicocokkan): **1092**
- Di luar semesta JDIH (mustahil dicocokkan): **478**

| Ukuran | Nilai | Arti |
|---|---:|---|
| Cakupan naif | 64.3% | terhadap seluruh rekaman — **menyesatkan** |
| Cakupan sebenarnya | 92.4% | terhadap rekaman yang dapat dicocokkan |

Sisa yang benar-benar layak diperbaiki: **83 rekaman**. Sisanya, 478 rekaman, berada di luar register JDIH — batas struktural, bukan cacat.

| Jenis | Belum berstatus | Di antaranya tanpa reg_key |
|---|---:|---:|
| POJK | 36 | 2 |
| SEOJK | 27 | 2 |
| UU | 13 | 1 |
| PADK | 7 | 3 |

## Populasi sebenarnya

- Rekaman inventaris: **3206**
- Peraturan unik (setelah deduplikasi lintas sumber): **1479**
- Terdaftar di lebih dari satu sumber: 952
- Duplikat di dalam satu sumber (kelebihan baris): ojk-regulasi: 73
- Tidak dapat diidentifikasi (tanpa jenis/nomor): ojk-rancangan: 650, ojk-regulasi: 52 — hampir seluruhnya rancangan yang memang belum bernomor

## Corong panen dokumen

| Sumber | Terdaftar | Dapat diunduh | Sudah di KB | Tanpa tautan | Capaian |
|---|---:|---:|---:|---:|---:|
| ojk-regulasi | 1570 | 1556 | 0 | 14 | 0.0% |
| jdih-ojk | 986 | 985 | 41 | 1 | 4.2% |
| ojk-rancangan | 650 | 453 | 1 | 197 | 0.2% |
| **Total** | **3206** | **2994** | **42** | **212** | **1.4%** |

Capaian dihitung terhadap rekaman yang *dapat* diunduh, bukan seluruh rekaman: rekaman tanpa tautan dokumen tidak akan pernah menjadi berkas, sehingga memasukkannya ke penyebut hanya membuat angka terlihat lebih buruk tanpa menunjuk pekerjaan.

## Indikator keberhasilan Fase 1 (URD bagian 5)

| Indikator | Aktual | Target | Status |
|---|---:|---:|:---:|
| Dokumen tertarik dari ≥3 situs sumber yang diinput manual | 10 | 3 | ✅ |
| Fitur unggah manual berfungsi untuk dokumen PDF | 1 | 1 | ✅ |
| Sistem membaca minimal 1 folder lokal | 3 | 1 | ✅ |
| Sistem membaca minimal 1 folder OneDrive public | 0 | 1 | ❌ |
| ≥20 dokumen peraturan di knowledge base (mode Deterministik) | 56 | 20 | ✅ |

**Cara hitung tiap indikator:**

- *Dokumen tertarik dari ≥3 situs sumber yang diinput manual* — COUNT(DISTINCT source_name) pada documents dengan source_type='web', tidak termasuk nama bernuansa pengujian
- *Fitur unggah manual berfungsi untuk dokumen PDF* — COUNT(*) pada documents dengan source_type='upload'
- *Sistem membaca minimal 1 folder lokal* — COUNT(*) pada documents dengan source_type='local_folder'
- *Sistem membaca minimal 1 folder OneDrive public* — COUNT(*) pada documents dengan source_type='onedrive'
- *≥20 dokumen peraturan di knowledge base (mode Deterministik)* — documents berstatus 'ingested', bukan artefak pengujian, dan identitas hukumnya (jenis + tahun) terbaca

> Catatan penting: tabel `documents` memuat **63** baris berstatus ingested, tetapi hanya **56** yang merupakan dokumen peraturan sungguhan. Selisihnya adalah artefak sesi pengujian dan berkas non-peraturan. Indikator dihitung memakai angka yang kedua.
