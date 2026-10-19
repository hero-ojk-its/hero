# Laporan Lapisan Data — Fase 1 & Fase 2

**Proyek:** HERO — Harmonisasi & Analisa Regulasi Otomatis · **Mitra:** OJK, DPEA
**Peran penulis:** Data / ML (Data Analyst) · **Posisi:** 13 Oktober 2026 · **Status:** Draft untuk pembahasan
**Rujukan:** URD v1.1 · SRS ([`docs/03`](../../docs/03-srs-functional-spec.md)) · WBS ([`docs/07`](../../docs/07-wbs-sprint-plan.md)) §5 · Backlog ([`docs/06`](../../docs/06-product-backlog-user-stories.md)) §5D

> Semua angka di bawah dihasilkan oleh perintah yang dapat dijalankan ulang (kolom *Cara membuktikan*),
> bukan diketik tangan. Dokumen ini hanya menyatakan bagian **lapisan data**; bagian Backend,
> Frontend, dan Infrastruktur dirujuk dari dokumen tim dan ditandai demikian.
> Keluaran sistem berlabel **Draft / Rekomendasi** — keputusan final tetap kewenangan Pengawas.

---

## 1. Ringkasan satu paragraf

Mesin analisa Fase 2 (D-03) **sudah memenuhi dua dari tiga indikator M2 dengan margin besar**, dan yang
ketiga (mode AI-Assisted) terpenuhi sebagai *mekanisme* tetapi **belum dibuktikan dengan model sungguhan**.
Ringkasan dan Key Takeaways dihasilkan untuk **114 dokumen** (target 10) dalam **≤ 11,5 detik per dokumen**
(batas 5 menit), dan **99,7%** poin kunci menyebut pasal asalnya. Per 13 Okt, **server (VPS) sudah menjalankan
mesin ini**: backend termigrasi ke kontrak pasal terbaru, **149 dokumen terindeks** (2 menunggu koreksi manusia, 0 menggantung) dan layanan analisa
berstatus **siap** dengan pencarian kata kunci + LSA atas **207 ribu potongan teks**. Per 19 Okt, **layar Analisa sudah dibangun tim Frontend** dan alur ujung-ke-ujung terbukti di lingkungan uji
(unggah → ekstraksi → cermin → analisa → cache → riwayat → ekspor DOCX/CSV/JSON). Yang masih kurang adalah
**penyambungan di server**: backend VPS belum dimigrasi ke versi terbaru dan `ML_SERVICE_URL` belum diisi,
serta **halaman PDF per pasal belum terisi di backend** untuk dokumen yang diekstraksi sebelum kontrak baru aktif.

---

## 2. Fase 1 — MVP Scraping & Ingest (D-01, D-02) · batas 11 Okt

Indikator M1 (WBS §5):

| Indikator M1 | Status | Bukti | Pemilik |
|---|---|---|---|
| Scan 3 sumber mengindeks dokumen tanpa unduh, mendekati *ground truth* | ✅ dengan catatan | situs regulasi OJK 1.556 dari ±1.700 (**0,92×**); JDIH 984 dari ±400–500 (**2,19×**) — `hero scan penerimaan` | Backend + Data |
| Unggah manual berfungsi | ✅ | PR #99 | Backend/Frontend |
| ≥ 1 folder lokal terbaca | ✅ | 3 folder terbaca (PR #107) | Backend + Data |
| ≥ 1 folder OneDrive *public* terbaca | ⚠ terblokir sebagian | tautan **terbaca** tanpa login (`hero onedrive --check`: *anonymous-share*), 30 dokumen tercatat di katalog; **isi dokumen tertutup** — issue #112, menunggu mitra | Mitra |
| ≥ 20 dokumen di KB (mode Deterministik) | ✅ | **116** dokumen peraturan sungguhan (target 20) — `hero dq` | Data |
| Penerimaan PO | ⏳ | Pak Faris belum melihat demo | PM |

**Kontribusi lapisan data pada Fase 1:** parser metadata (judul, nomor, tanggal), klasifikasi kategori
berbasis konfigurasi, struktur bab/pasal/ayat, OCR halaman pindai (38 halaman), deteksi duplikat hash + ukuran,
dan pengukuran mutu data (**21 aturan, 6 dimensi**, skor keseluruhan **98,2%**).

**Dua catatan yang harus dinyatakan terbuka kepada klien:**

1. **JDIH 2,19× ground truth.** Hasil scan jauh di atas estimasi mitra. Dugaan: estimasi hanya mencakup
   sebagian jenis peraturan (JDIH OJK memuat lima jenis: UU, PADK, POJK, SEOJK, PERPRES). **Angka resmi
   mitra belum ada** (issue #87), jadi rasio ini belum bisa disebut "lulus" maupun "gagal".
2. **Dua aturan mutu data berstatus gagal, dan itu cerminan data, bukan bug.**
   `INV-U01`: 144 peraturan tercatat lebih dari sekali — **daftar situs OJK sendiri** menampilkannya
   berulang. `DOC-S01`: 7 dokumen hanya 1–4 halaman (sampul atau draf pendek) sehingga tidak berpasal.
   Memaksanya lulus berarti mengarang data; kami memilih melaporkannya.

---

## 3. Fase 2 — MVP Analisa & Summary (D-03) · 12 Okt – 8 Nov

### 3.1 Tiga indikator M2 (WBS §5)

| Indikator M2 | Aktual | Target | Status |
|---|---|---|:---:|
| Summary & Key Takeaways untuk ≥ 10 dokumen uji | **114** | 10 | ✅ |
| Waktu proses per dokumen < 5 menit (Deterministik) | **11,5 s** (terburuk) | 300 s | ✅ |
| Toggle AI-Assisted berfungsi | mekanisme ada, **belum diuji model nyata** | berfungsi | ⚠ |

*Cara membuktikan:* `hero fase2` (menulis [`FASE2_EVALUASI.md`](FASE2_EVALUASI.md)).

**Soal indikator ketiga, jelas apa yang sudah dan belum dibuktikan.** Sudah: saklar
`analysis.ai_enabled`, penolakan otomatis bila keluaran AI mengubah angka atau mengarang fakta, penolakan
mengirim dokumen berklasifikasi internal ke layanan eksternal, dan kembali ke hasil Deterministik tanpa galat
bila layanan AI tidak ada — semuanya diuji offline. **Belum**: panggilan nyata ke model, karena tidak ada
kunci API di lingkungan ini dan pengiriman teks ke layanan pihak ketiga menyangkut NFR-08 / TD-03 yang
memerlukan persetujuan tertulis mitra. Mode Deterministik tetap penuh dan berjalan offline.

### 3.2 Kebutuhan fungsional Fitur 3.3 (SRS)

| FR | Kebutuhan | Hasil terukur | Status |
|---|---|---|:---:|
| FR-ANL-01 | Struktur bab/pasal/ayat, ≥ 80% dokumen berstruktur baku | **92,9%** dokumen berpasal terparsing (92 dari 99); 3.966 pasal | ✅ |
| FR-ANL-02 | Dasar hukum yang dirujuk | **98,2%** rujukan terbaca (4.096 dari 4.172); 2.375 relasi *berdasar* | ✅ |
| FR-ANL-03 | Status keberlakuan + sumber penetapan | cakupan rekonsiliasi dengan JDIH **92,4%**; 893 relasi *mencabut*, 99 *mengubah* | ✅ |
| FR-ANL-04 | Ringkasan isi peraturan | ringkasan terstruktur, median **152 kata** (v1: 318) | ✅ |
| FR-ANL-05 | Key Takeaways ≥ 3 poin per dokumen | median **16,5 poin** per dokumen; 5.231 poin total | ✅ |
| FR-ANL-06 | Setiap butir menyebut pasal asal | **99,7%** berujukan pasal; **98,3%** terlacak ke teks pasalnya | ✅ |
| FR-ANL-07 | Topik/klausul relevan, dapat difilter | kosakata topik terkendali + pencarian klausul per kebutuhan | ✅ |
| FR-ANL-08 | Waktu < 5 menit/dokumen | 11,5 s terburuk (26× lebih cepat dari batas) | ✅ |
| FR-ANL-09 | Ekspor hasil analisa | CSV `documents` / `articles` / `takeaways` via `hero export` | ✅ CLI · layar ekspor: Frontend |

Peningkatan v1 → v2 (ekstraktif → terstruktur per pasal): cakupan pasal normatif **23,9% → 98,3%**, poin
terpotong **12,6% → 2,8%**, kalimat ringkasan bercitasi pasal **0% → 66,1%**.

**Batas yang perlu dipahami:** metrik di atas memeriksa sifat yang bisa diuji mesin (rujukan, keterlacakan,
cakupan). Ringkasan yang lolos semuanya **masih bisa melewatkan hal penting**. Belum ada ringkasan acuan buatan
manusia; templat telaah ahli sudah disiapkan (`fase2_telaah_ahli.csv`) dan hasil telaah SME menjadi set evaluasi
berlabel pertama — itu syarat penerimaan **PO + SME**, bukan sesuatu yang bisa diklaim mesin.

### 3.3 Yang ditambahkan pada sesi Fase 2 ini

1. **Kontrak pasal Langkah 13 dipakai penuh** (backend PR #115): nomor halaman PDF per pasal, hierarki
   ayat, dan penggantian bersih yang idempoten. Kemampuan backend **dideteksi, tidak diasumsikan** — backend
   lama mengabaikan field baru tanpa galat sehingga pengiriman buta justru menggandakan pasal. Diuji
   terhadap backend sungguhan: **79 dari 79 pasal berhalaman**, dua worker pada dokumen yang sama tetap 40 pasal
   (bukan 80), 169 dari 169 ayat berinduk benar.
2. **Cacat nyata ditemukan dan diperbaiki** — dua galat konkurensi (HTTP 500 di bawah beban), penjaga
   kiriman-ulang yang membandingkan hash dengan dirinya sendiri sehingga berkas yang diganti tidak pernah
   diekstraksi ulang, mode Deterministik yang tanpa disadari menuntut SDK AI, **judul dokumen yang melampaui
   batas kolom backend** (membuat dokumen menggantung di status `diproses` dan, pada lembar ringkasan satu
   halaman, nomor peraturan lain terbaca sebagai nomor dokumen — kini masuk antrean koreksi), **byte NUL (0x00) di teks hasil OCR** (PostgreSQL menolaknya sehingga satu dokumen gagal diselesaikan
   backend), dan **build
   indeks yang dimatikan OOM-killer** pada korpus server (kini 650 MB, bukan 950 MB, dan dapat dibatasi lewat
   konfigurasi).
3. **Pengujian latensi & kapasitas** (`hero loadtest`), untuk NFR-01..03 — lihat §4.
4. **CI diperbaiki:** pipeline sebelumnya **merah di mesin bersih** (tiga dependensi tak dideklarasikan atau
   salah ekstra). Kini diuji pada Python 3.11 dan 3.12 plus satu pekerjaan khusus "pemasangan inti tanpa ekstra".

---

## 4. Performa server (NFR-01, NFR-02, NFR-03)

Diukur pada katalog nyata (118 dokumen, 12.914 potongan teks) di laptop 12 inti. Rinci:
[`PERFORMA_SERVER_ANALISIS.md`](PERFORMA_SERVER_ANALISIS.md).

| Pertanyaan | Hasil |
|---|---|
| Waktu satu permintaan (NFR-02 < 3 detik) | semua endpoint **p95 ≤ 36 ms** (margin > 80×) |
| Permintaan per detik | ±490 req/s per proses |
| Pengguna serentak | sehat sampai **800 koneksi** menembak tanpa jeda; ±3.200 pengguna nyata *(perkiraan turunan, jeda 5 detik)* |
| Kapasitas dokumen (NFR-03 ≥ 100) | 118 dokumen terlayani tanpa degradasi |

**Di server produksi (VPS 1,9 GB RAM, 2 inti, berbagi dengan Nextcloud), diukur 13 Okt**
([`PERFORMA_SERVER_VPS.md`](PERFORMA_SERVER_VPS.md)): layanan analisa, jalur Deterministik, korpus 207 ribu potongan.

| | Laptop (12 inti) | **VPS (2 inti)** |
|---|---|---|
| Pencarian LSA, satu pengguna (p95) | ±12 ms | **±200–250 ms** |
| Kueri pencarian LSA, kondisi tunak | — | **±0,23 s** (kueri pertama setelah restart 1,2–1,6 s) |
| Throughput puncak (campuran endpoint yang sama) | ±230 req/s | **±24 req/s** |
| Pengguna serentak diuji | 10 (layanan analisa) | 12 (p95 2,0 s, **0% galat**); batas belum ditemukan |
| Memori layanan | 350–530 MB (matriks di RAM) | anon **≈180 MB** saat diam, **≈540 MB** di bawah 12 koneksi, ditambah cache berkas 250–570 MB (batas 900 MB) |

**Ekstraksi dokumen besar di VPS lambat:** satu PDF hasil OCR (345 halaman) memakan **±280 detik** di
server — mendekati batas 5 menit NFR-01 untuk satu dokumen, walau ukurannya jauh di atas dokumen biasa.
Pada laptop, ekstraksi terburuk 11,4 detik. Dokumen biasa belum diukur di VPS.

**Kapasitas RAM server nyaris habis.** Layanan analisa saja bisa memakai ±0,8 GB di bawah beban, dari 1,9 GB
yang juga dipakai Nextcloud, backend, dan database (swap host sudah terpakai ±0,9 GB). Pencarian tetap berjalan,
tetapi tidak ada ruang untuk fitur memori besar (pencarian makna, harmonisasi massal). Menambah RAM server
menjadi ≥ 4 GB adalah langkah paling berdampak bila beban pengguna nyata naik.

Angka laptop **tidak berlaku** di server. Perkiraan ±110 pengguna nyata di VPS adalah *turunan* dari
level yang diuji (12 koneksi), bukan batas terukur. Pencarian makna (e5-large, ±2,2 GB) **tidak muat**
di VPS dan modelnya memang tidak ada di sana; yang tersedia kata kunci + LSA.

---

## 5. Pengujian

| Lapisan | Hasil | Cara menjalankan |
|---|---|---|
| Lapisan data (Python 3.14) | **466 lulus** | `python -m pytest tests -q` di `pipeline/` |
| Lapisan data (Python 3.11, dependensi persis CI) | **465 lulus, 1 dilewati** | idem, venv bersih |
| Backend (Postgres + pgvector, seperti CI) | **252 lulus** | `python -m pytest -q` di `backend/` |
| Frontend | lint lulus (1 peringatan), build berhasil | `npm run lint && npm run build` |
| Lint nama tak terdefinisi | lulus (data dan backend) | `ruff check --select E9,F821,F822,F823` |

Catatan: tes backend sempat gagal 12 kasus **hanya** di mesin pengembang karena berkas `.env` lokal
(`CRAWLER_BACKEND=push`) yang tidak dimiliki CI; dengan lingkungan CI semuanya lulus.

---

## 6. Yang BELUM selesai — dan siapa yang menyelesaikannya

| Hal | Dampak ke klien | Pemilik |
|---|---|---|
| **Penyambungan di server (VPS):** backend baru belum di-deploy (6+ migrasi) dan `ML_SERVICE_URL` belum diisi | Layar Analisa di staging belum mendapat jawaban dari mesin; di lingkungan uji sudah terbukti | Backend + Infra |
| Layar Harmonisasi masih placeholder | Fitur 3.4 memang jadwal Fase 3 | Frontend |
| **Halaman PDF belum tersimpan** untuk 735 pasal yang sudah ada di backend (0 yang punya `page`) | Rujukan "pasal + halaman" belum lengkap untuk dokumen lama; perlu ekstraksi ulang bertahap (25 dokumen berpasal) | Data + Backend |
| **Backend VPS baru memuat 151 dari ±2.100 dokumen katalog** (149 terindeks, 2 `perlu_koreksi`). Cara sisanya masuk (pindai backend, unggah massal) belum diputuskan | Knowledge Base staging belum mencerminkan seluruh korpus | Backend + PO |
| 48 POJK/PADK terindeks tanpa pasal (rata-rata ±5.000 karakter vs 84–164 ribu) | Kemungkinan sampul/abstrak yang ikut tertarik; perlu disaring di sumber | Backend + Data |
| Backend menjawab 200 saat penempatan gagal (status tetap `diproses`) | Dokumen bisa menggantung diam-diam; di sisi data sudah dilaporkan, perbaikan akar ada di backend | Backend |
| Isi dokumen OneDrive tertutup (#112) | Indikator M1 OneDrive | Mitra |
| Angka *ground truth* resmi (#87) | Rasio scan belum bisa ditetapkan lulus/gagal | Mitra |
| API tanpa login (#113) | Perlu ditutup sebelum dokumen non-publik masuk staging | Backend + PO |
| Uji mode AI-Assisted dengan model nyata | Indikator M2 ketiga | PO (persetujuan NFR-08) + Data |
| Telaah SME atas kualitas ringkasan | Syarat penerimaan M2 | PO + SME |
| Hierarki ayat (`push_ayat`) sengaja **belum dinyalakan** | Mengubah isi tabel `articles` (79 baris → 79 pasal + 169 ayat) dan menduplikasi teks di indeks | Backend + Frontend |

---

## 7. Jawaban singkat untuk pertanyaan yang mungkin muncul

- **"Apakah sudah bisa dipakai?"** Mesin analisa ya (lewat API, 114 dokumen, berujukan pasal). Aplikasi utuh belum:
  layar Analisa sudah ada dan terbukti bekerja di lingkungan uji, tetapi belum disambungkan di server staging.
- **"Apakah hasilnya benar?"** Terlacak dan terukur, tetapi kebenaran substansi ringkasan baru bisa dinyatakan
  setelah telaah SME. Sistem memberi rekomendasi, bukan keputusan.
- **"Apakah data kami keluar dari server?"** Tidak. Mode Deterministik berjalan offline; AI hanya opsional,
  dimatikan, dan menolak dokumen berklasifikasi internal.
- **"Seberapa cepat dan berapa pengguna?"** Terukur di §4, dengan peringatan bahwa server produksi jauh lebih kecil.
- **"Apa risiko terbesar?"** Bukan kode, melainkan: layar Analisa belum tersambung, isi OneDrive tertutup, penyambungan layar Analisa di server, dan hanya ±151 dari ±2.100 dokumen yang sudah masuk ke backend server.
