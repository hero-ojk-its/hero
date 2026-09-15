# MINUTES OF MEETING — Weekly Update #1 (Fase 0)
**Proyek:** HERO — Harmonisasi & Analisa Regulasi Otomatis
**Tanggal:** 8 September 2026, ± 14.00 WIB *(tanggal tidak disebut eksplisit di transkrip — mohon konfirmasi)*
**Media:** Online | **Durasi:** ± 1 jam
**Notulis:** Ahmad Zaky Ash Shidqi (PM/BA)
**Sumber:** Transkrip rekaman rapat (izin rekam diberikan oleh mitra di menit awal)
**Rekaman:** https://youtu.be/AhZWzkvjnYA

---

## 1. Peserta

| Nama | Peran | Pihak |
| --- | --- | --- |
| **Faris Budi** | Narasumber teknis utama; **Product Owner + Agile Coach** s.d. Fase 1 | OJK – DPEA |
| **Andika** *(Andika Wahyu Prihandoko)* | Mentor Industri | OJK – DPEA |
| **Ahmad Zaky Ash Shidqi** | Analyst + Project Manager | Tim ITS |
| **Moh. Rafli Gusti Saputra** | Backend | Tim ITS |
| **Muhammad Ikhwan** | Frontend / UI-UX | Tim ITS |
| **Mirza Syahrizal Fathir** | Data / ML | Tim ITS |
| **Ahmad Izzul Hamdan** | Platform / Infra & QA | Tim ITS |

---

## 2. Agenda

1. Pemahaman tim atas requirement beserta rancangan arsitektur
2. Usulan tech stack beserta alasannya
3. Struktur knowledge base secara detail
4. Klarifikasi prioritas: Deterministik vs AI-Assisted

---

## 3. Temuan Kunci — Angka Bisnis Sebenarnya

> Ini informasi terpenting dari rapat. **Baseline yang minggu lalu saya tandai belum ada,
> sekarang sudah tersedia.**

| Item | Angka |
| --- | --- |
| Kewajiban DPEA | Menyusun **tanggapan tertulis** atas setiap draft peraturan yang masuk, dari sudut pandang IT |
| Volume tahun lalu | **54 tanggapan** |
| Volume per Agustus tahun ini | **40 tanggapan** (dan terus berjalan) |
| Waktu per tanggapan (manual, saat ini) | **2–3 hari kerja** |
| **Target dengan HERO** | **2–3 jam** |

Faris menegaskan dua motivasi di balik angka ini:

1. **Menghapus ketergantungan pada kontinuitas orang.** "Kalau orangnya bisa nyenuk (fokus)
   diam, bisa. Tapi kalau baru kerja setengah jam terus dipanggil rapat, itu udah nggak
   kepegang. Nanti memulai lagi, nyari lagi dokumennya."
2. **Mempercepat proses berulang.** Pekerjaan setahun bukan hanya menyusun tanggapan.

**Visi jangka panjang:** bila algoritmanya berjalan baik, pola yang sama akan diduplikasi ke
sektor lain — perbankan, IKNB, pasar modal, edukasi & perlindungan konsumen. "Tinggal kita
ganti knowledge base-nya saja." → Implikasi desain: **knowledge base harus dapat ditukar per
sektor tanpa mengubah mesin analisanya.**

---

## 4. Keputusan Rapat

| ID | Keputusan | Dasar | Dampak Dokumen |
| --- | --- | --- | --- |
| **KEP-01** | **Prioritas jalur data: Scraper lebih dulu.** Upload manual dianggap fitur umum yang seharusnya sudah ada; folder OneDrive menyusul setelah Faris menyediakannya | Jawaban langsung atas pertanyaan prioritas tim | Backlog Sprint 1 |
| **KEP-02** | **Prioritas delivery aplikasi: Mode Deterministik lebih dulu.** Aplikasi harus tetap jalan saat offline, tanpa internet, dan tanpa anggaran AI | "Seumpama posisinya offline, tidak ada internet, tidak ada budget untuk beli AI, ini aplikasi masih bisa jalan" | SRS FR-SYS-01/04, Risk RSK-01 |
| **KEP-03** | **Mitra tidak anti-AI.** Tim bebas memakai AI, model lokal (Ollama dsb.), atau model berbayar murah. AI dipakai **untuk membangun algoritma**, bukan menggantikannya | "Bukan 'tolong scrap data dari sana', tapi bikin algoritma scraping-nya dulu" | Arsitektur, SRS §6 TD-03 |
| **KEP-04** | **Bahasa & framework bebas.** Mitra ber-stack .NET/Microsoft, namun menerima Python; bila masuk produksi mereka dapat mengonversi sendiri | Diskusi dengan Fathir | SRS TD-01 — **sebagian terjawab** |
| **KEP-05** | **Format dokumen: PDF saja.** Publikasi selama ini memang satu format | Konfirmasi Faris | BRule-04 tetap |
| **KEP-06** | **Deduplikasi memakai perbandingan *hash* dan *ukuran berkas*** | "Namanya bisa beda, tapi hash-nya sama" | FR-SCR-08 |
| **KEP-07** | **Penamaan berkas diambil dari halaman pertama PDF via OCR**: nomor peraturan, tanggal, dan judul — dipakai sebagai *naming convention* sebelum masuk folder knowledge base | Arahan Faris | FR-SCR-09 (baru: US-20a) |
| **KEP-08** | **Validasi metrik 70% dilakukan DPEA secara manual dengan metode *sampling***, bukan pemeriksaan menyeluruh. Dari 10 dokumen di-*run*, diambil sampel 2–3, lalu dicek apakah kutipan pasalnya benar | "Itu menjadi bagian dari testing kami" | Test Plan — **perubahan metode** |
| **KEP-09** | **Kadens rapat menjadi mingguan**, maksimal 1 jam per sesi | "Nanti rapatnya setiap minggu" | Charter §C, Communication Plan |
| **KEP-10** | **Mockup UI dibuat bertahap per fase**, bukan seluruh modul di awal. Mockup fase berjalan diserahkan **maksimal di minggu pertama fase tersebut** | "Kalau ini sebenarnya ekspektasi kami, nggak perlu langsung jadi semuanya" | UI Spec Fase 1 (dok. 15) |
| **KEP-11** | **Item yang belum selesai di suatu fase masuk backlog dan dibawa ke fase berikutnya**, tidak memblokir fase baru | Penjelasan Agile oleh Faris | Sprint Plan, template rapat |
| **KEP-12** | **Faris + Andika berperan sebagai Product Owner + Agile Coach s.d. 11 Oktober** (akhir Fase 1). Sejak **12 Oktober** mereka murni Product Owner, dan **tim berperan sebagai konsultan** yang memberi rekomendasi teknis | "Memposisikan Anda adalah konsultannya kami" | RACI, Stakeholder Register |
| **KEP-13** | **Komunikasi harian via grup WhatsApp**, mitra ikut bergabung | Usulan Faris | Communication Plan |
| **KEP-14** | **Warna/tema UI bebas**, tidak ada ketentuan brand yang mengikat | Jawaban ke Ikhwan | UI Spec |

---

## 5. Klarifikasi Teknis

### 5.1 Sumber Dokumen — Tiga Jalur dengan Tujuan Berbeda

Ini koreksi penting terhadap pemahaman awal tim. Ketiga jalur **bukan** tiga cara melakukan
hal yang sama; masing-masing punya peran berbeda:

| Jalur | Isi | Tujuan | Catatan |
| --- | --- | --- | --- |
| **1. Scraping** | Peraturan yang **sudah dipublikasikan** | Mengisi *corpus* peraturan eksisting | Target utama: **JDIH** (Jaringan Dokumentasi dan Informasi Hukum) — setiap kementerian/lembaga punya, seluruh peraturan terbit di sana. Juga `ojk.go.id/…/regulasi` |
| **2. Unggah manual** | **Draft peraturan baru yang ingin dianalisa** | Objek analisa, bukan pengisi corpus | "Jika ada dokumen draft dari peraturan baru yang ingin dianalisa, maka mau nggak mau kita harus upload manual" |
| **3. Folder lokal / OneDrive** | **Peraturan internal** yang hanya dipublikasikan di internal | Melengkapi corpus dengan sisi internal | Disediakan Faris di folder OneDrive. **Wajib NDA lebih dulu.** Tim boleh menembak alamatnya langsung atau menyalin ke lokal |

> **Implikasi:** desain flow lama yang menyatukan ketiga jalur ke satu pipeline ingest perlu
> dikoreksi. Draft peraturan baru adalah **objek yang dikaji**, bukan anggota corpus pembanding.

### 5.2 Tantangan Scraping

- Volume: `ojk.go.id/regulasi` dan JDIH masing-masing **lebih dari ribuan dokumen**
- **Kedalaman crawling adalah PR utama.** Pola URL seragam di depan (`/regulasi/…`), berbeda di
  belakang. Tim harus memikirkan cara menelusuri kedalaman 1 → 2 → 3 dan seterusnya.
  **Saran Faris: mulai dari kedalaman 1 dulu**, lalu masuk lebih dalam
- Karakter situs bervariasi: sebagian ber-**anti-bot**, sebagian dapat "ditembak polosan"
- Faris sudah mencoba sendiri di mini-lab rumahnya; kesimpulannya **butuh waktu di awal untuk
  membangun scraper-nya**, tetapi begitu jalan, satu langkah menarik semua PDF

### 5.3 Usulan Stack dari Tim

| Aspek | Usulan | Penanggung Jawab | Status |
| --- | --- | --- | --- |
| Scraping | Python + `requests` + BeautifulSoup4; berpindah ke Playwright/Selenium bila perlu | Fathir | Diterima mitra |
| Alternatif yang disebut mitra | Playwright | Faris | Opsi |
| Stack mitra sendiri | .NET (produk Microsoft) | — | Tidak wajib diikuti |
| Model AI | Model lokal (Ollama dsb.) atau model berbayar murah | Tim | Bebas |
| Hosting | Lokal dulu, lalu publish *version by version* | Tim | Perlu dipastikan sebelum 8 Okt |

### 5.4 Keputusan Penyimpanan yang Diserahkan ke Tim

Faris menawarkan dua opsi dan **meminta tim yang memutuskan serta memberi rekomendasi**:

| Opsi | Deskripsi | Konsekuensi |
| --- | --- | --- |
| **A** | Simpan PDF utuh di folder (boleh di-OCR) | Sederhana; tetapi setiap kali butuh informasi harus dibaca ulang satu per satu |
| **B** | Ekstrak isi dokumen, simpan sebagai **blok** di basis data | Lebih mudah diindeks karena kata per kata sudah terekstraksi |

Idealnya: setelah scraper menemukan misalnya 100 kandidat PDF, **pengguna diberi pilihan** —
langsung masukkan ke basis data, atau unduh PDF-nya.

> **Rekomendasi tim (untuk dibawa ke rapat berikutnya):** jalankan keduanya — simpan PDF asli
> sebagai bukti/rujukan (dibutuhkan agar validator DPEA dapat membuka dokumen aslinya saat
> *sampling*, lihat KEP-08) **dan** simpan hasil ekstraksi sebagai blok terstruktur untuk
> pengindeksan. Menyimpan hanya blok akan mematikan kemampuan verifikasi manual.

### 5.5 Logika Harmonisasi — Penjelasan Konkret dari Mitra

Ini penjabaran paling berharga dari rapat, karena mengubah klasifikasi temuan yang tim rancang
sebelumnya.

**Struktur peraturan yang bisa dimanfaatkan:**
- Judul peraturan relatif jelas menyebut objek dan kausalnya
- Peraturan turunan cenderung punya struktur pasal serupa: "di awal ada pasal terkait
  keanggotaan, pasti peraturan turunannya juga ada keanggotaan. Lalu ada pasal terkait denda,
  judulnya pun juga akan sama"

**Contoh kasus yang diberikan Faris — pelaporan bank ke OJK:**

| | Peraturan Eksisting | Peraturan Baru (7 tahun kemudian) |
| --- | --- | --- |
| Objek | Kewajiban bank melaporkan ke OJK | Sama |
| Batas waktu | Laporan bulanan paling lambat tanggal sekian | Mungkin berubah (mis. 15 hari → 10 hari) |
| Denda keterlambatan | Terlambat 1 hari atau 10 hari → sama, 1% dari aset | Mungkin menjadi per hari |

**Logika klasifikasi yang diminta:**

| Kondisi | Klasifikasi | Contoh dari Faris |
| --- | --- | --- |
| Objek sudah pernah diatur, ketentuannya berubah | **Menggantikan** (menggugurkan yang sebelumnya) | "Kalau sebelumnya 1–10 hari sama, dan ini per hari, berarti kita pakai yang baru" |
| Objek sudah diatur, ketentuan pada dasarnya sama tetapi diperinci | **Memperjelas** | "Sifatnya sama dengan ini, tapi itu sifatnya memperjelas" |
| Objek belum pernah diatur sama sekali di peraturan eksisting | **Pasal baru / tambahan** — tidak me-*replace* | "Peraturan eksisting kalau terlambat tidak ada denda. Sekarang ada denda, berarti ini pasal tambahan" |

> **Perubahan terhadap rancangan sebelumnya:** klasifikasi `konflik / duplikasi / gap` yang tim
> pakai di URD **belum cukup**. Kosakata bisnis DPEA yang sebenarnya adalah **menggantikan /
> memperjelas / pasal baru**. Klasifikasi ini harus masuk ke SRS dan model data.

Faris menutup dengan: *"Untuk menemukan pola ini, itu yang perlu diskusi bersama."* → Perlu
sesi khusus perumusan aturan harmonisasi.

### 5.6 Pertanyaan yang Belum Terjawab

| No. | Pertanyaan | Penanya | Status |
| --- | --- | --- | --- |
| 1 | **Berapa persen kesamaan** yang membuat sebuah pasal dianggap "pengembangan" versus "duplikat" versus "pasal baru"? | Fathir | **BELUM DIJAWAB.** Faris menjelaskan logikanya secara kualitatif (berdasarkan objek/kausal), bukan ambang angka. Perlu dirumuskan bersama |

---

## 6. Action Item

### 6.1 Tanggung Jawab Mitra (DPEA)

| ID | Tindakan | PIC | Target |
| --- | --- | --- | --- |
| AI-M1 | Menyediakan **3 alamat situs sumber** yang akan di-*scrape* (2 sudah ditunjukkan saat rapat: `ojk.go.id/…/regulasi` dan JDIH) | Faris | Sebelum 14 Sep |
| AI-M2 | Menyediakan **folder OneDrive berisi peraturan internal** — setelah NDA | Faris | Menyusul, akan dikabari |
| AI-M3 | Menyediakan **contoh dokumen tanggapan** yang pernah diminta | Faris | Fase 0–1 |
| AI-M4 | Menyediakan **contoh surat tanggapan tertulis final** yang sudah dirilis DPEA (mis. tanggapan atas juklak pertukaran data OJK–LPS) | Faris | Fase 0–1 |
| AI-M5 | Menyediakan **seluruh dokumen dasar** yang dirujuk di dalam surat tanggapan contoh tersebut ("kalau menyebut Peraturan 1 sampai 7, kami provide ketujuhnya") | Faris | Fase 0–1 |
| AI-M6 | Menyediakan **template/model output** yang diharapkan | Faris | Fase 0–1 |

> **Catatan PM:** AI-M3 s.d. AI-M6 adalah **prasyarat mutlak Fase 4** (Modul Tanggapan PoV,
> deliverable tersulit dengan bobot 5/5). Tanpa contoh output final dan dokumen dasarnya, tim
> tidak punya target bentuk yang harus dicapai. Faris sudah mencatatnya sebagai *pending item*
> di sisi mitra — PM wajib menagihnya di rapat mingguan, bukan menunggu sampai November.

### 6.2 Tanggung Jawab Tim

| ID | Tindakan | PIC | Target |
| --- | --- | --- | --- |
| AI-T1 | Menyelesaikan seluruh persiapan Fase 0 | Semua | **13 Sep 2026** |
| AI-T2 | Menandatangani **NDA** seluruh anggota tim | Semua | Sebelum menerima dokumen internal |
| AI-T3 | Membuat **mockup Figma Fase 1** (input/pencarian link + unggah PDF), lalu membagikan tautannya | Ikhwan | Maks. minggu pertama Fase 1 (± 20 Sep) |
| AI-T4 | Menyusun **user story** sebagai bahan mockup Ikhwan | Zaky | Sebelum Ikhwan mulai — **lihat dok. 06 & 15** |
| AI-T5 | Membangun **algoritma scraper** — mulai dari kedalaman 1 | Fathir | Fase 1 |
| AI-T6 | Memutuskan & merekomendasikan **strategi penyimpanan** (PDF utuh vs blok DB) | Fathir + Rafli | Rapat berikutnya |
| AI-T7 | Memastikan **infrastruktur/hosting** siap untuk uji coba user | Hamdan | **8 Okt 2026** |
| AI-T8 | Membuat **grup WhatsApp** dan mengundang mitra | Zaky | Segera |
| AI-T9 | Mengajukan **pendanaan** bila diperlukan (skema sama dengan semester lalu, masih tersedia) | Zaky | Sesuai kebutuhan |
| AI-T10 | Menyiapkan **format laporan rapat mingguan** sesuai template yang diminta Faris | Zaky | Sebelum 14 Sep |

### 6.3 Format Rapat Mingguan yang Diminta Mitra

Faris menetapkan template pelaporan berikut, dibawakan oleh PM:

1. Dari fase sebelumnya ada **N item** — berapa yang **terealisasi**
2. Mana saja yang **sudah disetujui user** (Faris & Andika)
3. Yang belum — **mengapa belum**
4. Item yang belum selesai **masuk antrian fase berikutnya**

---

## 7. Target Fase 1 yang Ditegaskan Ulang

Periode **14 September – 11 Oktober 2026**. Indikator dari mitra:

| No. | Indikator | Angka |
| --- | --- | --- |
| 1 | Berhasil menarik dokumen dari situs sumber yang diinput manual | ≥ **3 situs** |
| 2 | Fitur unggah manual berfungsi untuk PDF | Berfungsi |
| 3 | Berhasil membaca folder lokal | ≥ **1 folder** |
| 4 | Dokumen peraturan masuk knowledge base | ≥ **20 dokumen** |
| 5 | **Siap diuji coba oleh user (Faris & Andika)** | **8 Okt 2026** (idealnya), paling lambat 11 Okt |

> Bila indikator belum tercapai, item masuk backlog dan dibawa ke Fase 2 — bukan menahan
> dimulainya Fase 2 (KEP-11).

---

## 8. Catatan Non-Teknis

- Andika menegaskan OJK adalah **lembaga negara yang produknya regulasi**, bukan organisasi
  pencari profit — sehingga pekerjaan ini berdampak langsung pada pijakan bersama.
- Terdapat **± 51 alumni ITS** di OJK. Pimpinan saat ini, **Pak Dwi Kurniawan** (Eselon 1,
  alumni TC ITS angkatan 2), bersedia memberikan rekomendasi bagi peserta yang memintanya.
- Mitra menekankan agar proyek dijalani sebagai **belajar bersama**, bukan beban.
- Faris mencatat bahwa karena proyek dimulai tepat waktu, tiap fase punya ruang **± 3 minggu**
  sehingga diskusi bisa lebih panjang.

---

## 9. Dampak terhadap Dokumen Proyek

| Dokumen | Perubahan yang Diperlukan | Status |
| --- | --- | --- |
| [02 BRD](02-brd-business-requirements.md) | Isi baseline: 54/40 tanggapan, 2–3 hari → 2–3 jam. Tambah BO visi multi-sektor | ✅ Diperbarui |
| [03 SRS](03-srs-functional-spec.md) | Klasifikasi harmonisasi baru; dedup hash+ukuran; naming convention OCR halaman 1; kedalaman crawling; pemisahan draft vs corpus | ✅ Diperbarui |
| [04 Process Flow](04-process-flow-asis-tobe.md) | Flow TO-BE v2 — pemisahan jalur dokumen | ✅ Diperbarui |
| [13 DFD](13-dfd-data-flow-diagram.md) | Dokumen baru | ✅ Dibuat |
| [06 Backlog](06-product-backlog-user-stories.md) | Story baru & revisi AC | ✅ Diperbarui |
| [15 UI Spec Fase 1](15-ui-spec-fase-1.md) | Dokumen baru untuk Ikhwan | ✅ Dibuat |
| [11 Test Plan](11-test-plan-uat.md) | Metode validasi berubah menjadi *sampling* oleh DPEA | ✅ Diperbarui |
| [10 Risk Register](10-risk-register.md) | ISU-01/02/03/04 tertutup sebagian; risiko baru | ✅ Diperbarui |
| [01 Stakeholder](01-stakeholder-register-raci.md) | Nama riil; peran PO/Agile Coach; kadens mingguan | ✅ Diperbarui |
| [07 Sprint Plan](07-wbs-sprint-plan.md) | Kadens mingguan; tanggal uji coba user 8 Okt | ✅ Diperbarui |

---

## 10. Rapat Berikutnya

**Agenda:** masuk pembahasan Fase 1 — status kesesuaian Fase 0, pekerjaan Fase 1, item sisa
Fase 0, dan pembahasan tech stack.
**Format:** sesuai §6.3. **Durasi maksimal:** 1 jam.
