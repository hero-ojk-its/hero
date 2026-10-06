# Laporan Data Analyst — Fase 1 (MVP Scraping & Ingest)

**Proyek:** HERO — Harmonisasi & Analisa Regulasi Otomatis
**Mitra:** Otoritas Jasa Keuangan · Departemen Pengembangan Aplikasi (DPEA)
**Peran:** Data / ML (Project Charter bagian D) — pipeline data, analitik
**Fase:** 1 — MVP Scraping & Ingest (14 September – 11 Oktober 2026)
**Tanggal laporan:** 20 September 2026

---

## Ringkasan eksekutif

Fase 1 memiliki lima indikator keberhasilan menurut URD bagian 5. Pada awal
sesi ini, dua di antaranya belum memiliki bukti apa pun di dalam katalog, dan
satu indikator lain terpenuhi hanya karena berkas sisa pengujian ikut
terhitung. Kini **empat dari lima indikator tercapai dengan bukti yang dapat
diperiksa**, dan satu sisanya terhalang akses yang berada di luar kendali tim
teknis.

Temuan terpenting laporan ini bukan tentang data yang rusak, melainkan
tentang **cara data itu diukur**. Angka yang selama ini dibaca sebagai
kelemahan sistem — "36% rekaman gagal dicocokkan statusnya" — ternyata hasil
dari penyebut yang keliru. Diukur dengan benar, cakupan rekonsiliasi adalah
**92,4%**, dan sisa pekerjaan yang nyata tinggal **83 rekaman**, bukan 561.

| | Sebelum | Sesudah |
|---|---|---|
| Indikator Fase 1 tercapai | 2 dari 5 | **4 dari 5** |
| Kemampuan ukur mutu data | tidak ada | 21 aturan · 6 dimensi |
| Cakupan rekonsiliasi terlapor | 64,3% (menyesatkan) | **92,4%** (terhadap semesta yang benar) |
| Sisa pekerjaan rekonsiliasi | "561 rekaman" | **83 rekaman** |
| Pengujian otomatis | 185 | **217** |

---

## 1. Yang dibangun

### 1.1 Modul `hero/dq/` — lapisan pengukuran mutu data

| Berkas | Isi |
|---|---|
| `rules.py` | 21 aturan validasi deklaratif, masing-masing dengan ruang lingkup dan alasan ambangnya |
| `profile.py` | Profiling kolom: kekosongan, kardinalitas, sebaran nilai, kandidat kunci |
| `coverage.py` | Analisa cakupan: semesta yang dapat dicocokkan, deduplikasi, corong panen |
| `scorecard.py` | Skor enam dimensi + pengukuran indikator Fase 1 |
| `report.py` | Penyajian sebagai Markdown |

### 1.2 Dua perintah baru

```bash
hero dq                                  # kartu skor di terminal
hero dq --markdown docs/LAPORAN.md       # laporan lengkap
hero dq --json data/export/dq.json       # untuk dasbor / pembandingan
hero dq --strict                         # gerbang CI: keluar kode 1 bila gagal

hero profile inventory                   # profil kolom sebuah tabel
hero profile documents --top 10
```

### 1.3 Pengujian

26 pengujian baru (`tests/test_dq.py`), seluruh suite **217 lulus** (termasuk 6 test OneDrive). Setiap
pengujian menegakkan satu keputusan analitik yang mudah tergerus saat kode
dirapikan kemudian — misalnya bahwa rancangan tanpa nomor bukan pelanggaran,
dan bahwa Surat Edaran tanpa pasal adalah bentuk normalnya.

---

## 2. Temuan

### Temuan 1 — Metrik rekonsiliasi status salah penyebut *(dampak: tinggi)*

**Yang dilaporkan sebelumnya:** 561 dari 1.570 rekaman `ojk.go.id` (36%)
berstatus "tidak diketahui".

**Yang sebenarnya terjadi.** JDIH OJK adalah register milik OJK sendiri,
bukan basis data hukum nasional. Kueri terhadap data membuktikan ia hanya
memuat lima jenis peraturan:

```
UU · PADK · POJK · SEOJK · PERPRES
```

Sementara 478 dari 1.570 rekaman `ojk.go.id` adalah terbitan lembaga lain —
174 PBI (Bank Indonesia), 187 Keputusan Bapepam-LK, 31 PMK dan 19 KMK
(Kementerian Keuangan), serta 52 rekaman yang jenisnya tidak terbaca.
Rekaman-rekaman itu tidak akan pernah ditemukan di JDIH OJK, sebaik apa pun
algoritma pencocokannya.

**Setelah penyebut diperbaiki:**

| Golongan | Jumlah | Tindakan |
|---|---:|---|
| Dapat dicocokkan, sudah berstatus | 1.009 | — |
| Dapat dicocokkan, belum berstatus | **83** | **inilah pekerjaan yang nyata** |
| Di luar register JDIH | 478 | batas struktural, laporkan apa adanya |
| **Total** | **1.570** | penjumlahan terbukti seimbang |

Cakupan sebenarnya: **1.009 / 1.092 = 92,4%**.

**Mengapa ini penting.** Angka lama mengarahkan tim memperbaiki algoritma
pencocokan untuk mengejar 561 rekaman, yang 85% di antaranya mustahil
ditutup. Angka baru menunjuk 83 rekaman yang seluruhnya nyata dan dapat
dikerjakan.

Sisa 83 itu terdiri atas: 36 POJK, 27 SEOJK, 13 UU, dan 7 PADK.

### Temuan 2 — Knowledge base tercampur artefak pengujian *(dampak: tinggi)*

Enam dari 63 baris `documents` berasal dari sesi pengujian
(`JDIH test`, `api-test`, `test-upload-regression`), dan dua di antaranya
bukan dokumen peraturan sama sekali — salah satunya adalah berkas *User
Requirement Document* proyek ini sendiri.

Akibatnya indikator "≥20 dokumen peraturan di knowledge base" terpenuhi
sebagian karena baris yang tidak seharusnya dihitung. Indikator kini diukur
dengan tiga syarat: berstatus `ingested`, bukan artefak pengujian, dan
identitas hukumnya (jenis + tahun) terbaca. Hasilnya **56 dokumen peraturan
sungguhan** — masih jauh melampaui target 20, tetapi kini angkanya dapat
dipertanggungjawabkan.

Aturan `DOC-G01` menjaga agar hal ini tidak terulang.

> **Tindakan menunggu persetujuan.** Enam baris artefak tersebut belum saya
> hapus, karena penghapusan data bersifat merusak dan sebaiknya diputuskan
> pemilik data. Rekomendasi ada di bagian 4.

### Temuan 3 — Duplikasi rekaman di dalam satu sumber *(dampak: sedang)*

71 peraturan tercatat lebih dari sekali di sumber `ojk-regulasi`, dengan URL
detail berbeda — satu dari kanal "semua sektor", satu lagi dari kanal
sektornya sendiri. Total 144 rekaman terdampak, dengan kelebihan 73 baris.

Dampaknya: setiap hitungan populasi melebih-lebihkan jumlah peraturan.
Setelah deduplikasi lintas sumber, **3.206 rekaman sebenarnya mewakili 1.479
peraturan unik** yang dapat diidentifikasi, ditambah 702 rekaman yang belum
dapat diidentifikasi (650 di antaranya rancangan yang memang belum bernomor).

Aturan `INV-U01` saat ini **gagal** (5,8% terhadap ambang 3%) — sengaja
dibiarkan gagal agar terlihat, bukan diturunkan ambangnya.

### Temuan 4 — Pembentuk `reg_key` tidak mengenali dua pola penomoran *(dampak: rendah sekarang, tinggi kelak)*

`reg_key` dibentuk dengan mengambil angka pertama dari nomor peraturan. Dua
pola gagal ditangani:

1. **Keputusan Bapepam-LK** — `KEP-208/BL/2012` diawali huruf, sehingga kunci
   tidak terbentuk sama sekali. 187 rekaman.
2. **Peraturan Bank Indonesia** — `7/1/PBI/2005` menghasilkan `PBI|7|2005`,
   padahal angka pertama adalah seri tahun, bukan nomor urut. Akibatnya 42
   peraturan berbeda berbagi satu kunci yang sama.

**Saat ini belum menimbulkan kesalahan**, karena kedua jenis itu berada di
luar register JDIH sehingga tidak pernah ikut dicocokkan. Saya memeriksa
secara khusus apakah salah-cocok sudah terjadi: tidak — sisi JDIH tidak
memiliki satu pun `reg_key` kembar, sehingga setiap pencocokan bersifat
tunggal.

Ini **risiko laten**: begitu Bank Indonesia ditambahkan sebagai sumber — dan
`config/sources.yaml` sudah memuatnya — pencocokan akan salah secara masif
dan diam-diam.

### Temuan 5 — Dua jalur masuk belum pernah dipakai di produksi *(sudah ditutup)*

Indikator Fase 1 menuntut bukti bahwa jalur unggah manual dan jalur folder
berfungsi. Keduanya sudah berkode dan lulus pengujian, tetapi katalog tidak
memuat satu pun dokumen dari jalur tersebut — satu-satunya unggahan berasal
dari sesi regresi.

**Ditutup dalam sesi ini** dengan empat POJK 2026 asli yang diunduh dari
JDIH OJK, lalu dimasukkan lewat jalur sungguhan:

- `hero folders --path data/inbox` → 3 dokumen (35, 11, dan 29 halaman)
- `hero upload data/unggahan` → 1 dokumen (109 halaman)

Seluruhnya terekstrak penuh beserta struktur pasalnya.

### Temuan 6 — Dua dokumen berjenis pasal tidak menghasilkan pasal *(dampak: sedang)*

Satu POJK dan satu PADK masuk knowledge base tanpa satu pun pasal terparsing.
Karena pasal adalah unit pembanding fitur harmonisasi (URD 3.4), kedua
dokumen itu tidak dapat dipakai sama sekali oleh fitur berikutnya.

Empat SEOJK lain yang juga tanpa pasal **bukan** cacat: Surat Edaran disusun
dalam seksi angka Romawi. Aturan `DOC-S01` sengaja mengecualikannya.

---

## 3. Status indikator Fase 1

| # | Indikator (URD bagian 5) | Aktual | Target | Status |
|---|---|---:|---:|:---:|
| 1 | Dokumen tertarik dari ≥3 situs sumber yang diinput manual | 10 | 3 | ✅ |
| 2 | Fitur unggah manual berfungsi untuk dokumen PDF | 1 | 1 | ✅ |
| 3 | Sistem membaca minimal 1 folder lokal | 3 | 1 | ✅ |
| 4 | Sistem membaca minimal 1 folder OneDrive public | 0 | 1 | ❌ |
| 5 | ≥20 dokumen peraturan di knowledge base (Deterministik) | 56 | 20 | ✅ |

**Indikator 4** memerlukan tautan atau folder OneDrive public yang sungguhan
dari pihak mitra. Jalur teknisnya sudah tersedia dua-duanya — folder OneDrive
yang tersinkron ke disk berjalan lewat jalur yang sama dengan folder lokal
(sudah terbukti), sedangkan jalur share-link publik masih ditunda sesuai
keputusan sebelumnya. Yang kurang adalah aksesnya, bukan kodenya.

---

## 4. Rekomendasi

Diurutkan menurut manfaat dibanding usaha.

**R1 · Bersihkan enam artefak pengujian dari knowledge base.** *(butuh
persetujuan)* Memulihkan aturan `DOC-G01` ke lulus dan membuat indikator
Fase 1 sepenuhnya bersih. Mulai sekarang, arahkan sesi pengujian ke database
terpisah lewat `--config`, jangan ke katalog produksi.

**R2 · Tutup 83 rekaman rekonsiliasi yang dapat diperbaiki.** Pekerjaan yang
sesungguhnya, dan ukurannya kini diketahui pasti. Sebagian besar kemungkinan
karena perbedaan penulisan nomor; sisanya memang belum terdaftar di JDIH dan
dapat dilabeli demikian secara eksplisit.

**R3 · Perbaiki `reg_key` untuk pola Bapepam-LK dan PBI *sebelum* sumber Bank
Indonesia diaktifkan.** Selama BI belum aktif, ini tidak mendesak. Begitu
diaktifkan tanpa perbaikan, hasilnya adalah salah-cocok masif yang tidak
menimbulkan galat apa pun. Tambahkan pula aturan mutu yang mendeteksi
`reg_key` kembar di sisi sumber kebenaran.

**R4 · Tetapkan rekaman kanonik untuk peraturan yang muncul di beberapa
kanal.** Usulan aturan: utamakan rekaman yang punya tautan dokumen; bila
seri, ambil yang halaman detailnya paling lengkap. Simpan rekaman lain
sebagai alias, jangan dihapus — riwayat URL tetap berguna.

**R5 · Jalankan `hero dq --strict` di CI.** Menjadikan mutu data sebagai
gerbang, bukan laporan yang dibaca setelah masalahnya terlanjur menyebar.

**R6 · Naikkan capaian panen.** Baru 42 dari 2.994 rekaman yang dapat diunduh
(1,4%) sudah menjadi berkas. Fitur 3.3 dan 3.4 membutuhkan isi dokumen, bukan
sekadar daftarnya. Sarankan panen bertahap per status `berlaku` lebih dulu,
karena itu yang relevan untuk harmonisasi.

---

## 5. Catatan metodologis

Tiga keputusan yang membentuk seluruh laporan ini, dicatat agar dapat
diperdebatkan:

**Ruang lingkup dipisahkan dari aturan.** Setiap aturan menyatakan bukan
hanya apa yang salah, tetapi di mana harapan itu berlaku. Tanpa itu, sifat
bawaan data — rancangan tanpa nomor, Surat Edaran tanpa pasal — akan terbaca
sebagai kerusakan, dan tim akan memperbaiki yang sudah benar.

**Batas struktural dilaporkan sebagai batas.** Ketika sesuatu mustahil
dikerjakan, ia dihitung terpisah dan dijelaskan, bukan disembunyikan di dalam
persentase kegagalan. Ini membedakan laporan yang menunjukkan pekerjaan dari
laporan yang hanya menimbulkan kecemasan.

**Angka lama tidak diganti diam-diam.** Cakupan 64,3% tetap ditampilkan
bersebelahan dengan 92,4%, dengan penjelasan selisihnya. Mengganti angka
buruk dengan angka bagus tanpa menunjukkan sebabnya akan terlihat seperti
memoles, dan sepantasnya memang tidak dipercaya.

---

*Metode di balik laporan ini disuling menjadi dua skill yang dapat dipakai
ulang di proyek lain: [`skills/data-quality-scorecard`](../skills/data-quality-scorecard/SKILL.md)
dan [`skills/denominator-audit`](../skills/denominator-audit/SKILL.md).*
