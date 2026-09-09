# PRODUCT BACKLOG & USER STORIES
**Proyek:** HERO | **Versi:** 1.2 | **Tanggal:** 9 September 2026 | **Penyusun:** PM / Business Analyst

---

## 1. Struktur Epic

| Epic | Nama | Fase | Sprint | Deliverable | Estimasi (SP) |
| --- | --- | --- | --- | --- | --- |
| EP-01 | Scraping & Ingest Dokumen | 1 | S1–S2 | D-01 | 64 |
| EP-02 | Knowledge Base Terstruktur | 1 | S1–S2 | D-02 | 42 |
| EP-03 | Analisa, Summary & Key Takeaways | 2 | S3–S4 | D-03 | 55 |
| EP-04 | Harmonisasi Draft vs Eksisting | 3 | S5–S6 | D-04 | 63 |
| EP-05 | Draft Tanggapan Berbasis PoV | 4 | S6–S7 | D-05 | 47 |
| EP-06 | Platform, Mode & Antarmuka | 0–4 | S0–S7 | lintas | 45 |
| EP-07 | Dokumentasi, Pengujian & UAT | 5 | S7–S8 | D-06 | 26 |
| | **Total** | | | | **342** |

**Skala estimasi:** Fibonacci (1, 2, 3, 5, 8, 13). 1 SP ≈ setengah hari kerja efektif satu orang.

---

## 2. Definition of Ready (DoR)

Sebuah story boleh masuk sprint bila:

1. Memiliki deskripsi *user story* (As a… I want… so that…) yang jelas.
2. Kriteria penerimaan tertulis dan dapat diuji.
3. Tertaut ke minimal satu FR pada [SRS](03-srs-functional-spec.md).
4. Dependensinya sudah selesai atau terjadwal lebih dulu.
5. Sudah diestimasi oleh tim.
6. Tidak ada pertanyaan terbuka yang memblokir dari sisi bisnis.

## 3. Definition of Done (DoD)

Sebuah story dinyatakan selesai bila:

1. Seluruh kriteria penerimaan terpenuhi dan diverifikasi.
2. Kode ter-*review* minimal oleh satu anggota tim lain.
3. Pengujian fungsional terkait lulus.
4. Berjalan pada mode Deterministik tanpa layanan AI (bila story menyentuh alur analisa).
5. Terintegrasi ke lingkungan staging.
6. Audit log tercatat untuk aksi yang relevan.
7. Dokumentasi terkait diperbarui.
8. Tidak menyisakan *defect* severity Kritis/Tinggi yang terbuka.

---

## 4. Product Backlog

Legenda prioritas: **M** = Must, **S** = Should, **C** = Could, **W** = Won't (MVP).

> **Kolom Peran diturunkan dari [Dokumen Arsitektur §4.1](16-arsitektur-sistem.md)**, bukan
> ditetapkan sendiri di dokumen ini. Peran yang tercantum adalah pihak yang bertanggung jawab
> menyatakan story selesai; peran pendukung dicatat di badan issue. Bila kolom ini berbeda
> dengan label issue di GitHub, matriks komponen yang berlaku.

### EP-06 — Platform, Mode & Antarmuka

| ID | **Peran** | User Story | AC Ringkas | FR | Pri | SP | Sprint |
| --- | --- | --- | --- | --- | --- | --- | --- |
| US-01 | Backend | Sebagai **Admin Sistem**, saya ingin mengelola akun pengguna dan perannya, agar akses fitur sesuai tanggung jawab | Peran Analis/Admin KB/Admin Sistem/Pilot User dapat dibuat; akses fitur mengikuti peran | FR-SYS-08 | M | 5 | S1 |
| US-02 | Backend | Sebagai **pengguna**, saya ingin login ke sistem, agar aktivitas saya terekam atas nama saya | Login berhasil/gagal ditangani; tidak ada fitur yang dapat diakses tanpa autentikasi | FR-SYS-08, NFR-06 | M | 3 | S1 |
| US-03 | Frontend | Sebagai **Analis**, saya ingin melihat satu halaman beranda berisi ringkasan KB dan pekerjaan terakhir, agar tahu kondisi sistem | Jumlah dokumen, job terakhir, dan hasil analisa terbaru tampil | FR-SYS-06 | S | 3 | S2 |
| US-04 | Backend | Sebagai **Analis**, saya ingin mengaktifkan/menonaktifkan AI-Assisted lewat *toggle*, agar dapat memilih mode sesuai kebutuhan | Toggle tersimpan; default Deterministik; status mode tampil pada hasil | FR-SYS-02 | M | 5 | S3 |
| US-05 | Backend | Sebagai **Analis**, saya ingin hasil deterministik dan hasil AI disimpan terpisah, agar dapat membandingkan keduanya | Kedua versi dapat ditampilkan berdampingan; substansi hasil dasar tidak berubah | FR-SYS-03 | M | 5 | S3 |
| US-06 | Backend | Sebagai **Analis**, saya ingin proses tetap selesai saat layanan AI mati, agar pekerjaan saya tidak terhenti | Simulasi AI mati: proses selesai dengan hasil deterministik + notifikasi | FR-SYS-04, NFR-04 | M | 5 | S4 |
| US-07 | Frontend | Sebagai **Analis**, saya ingin setiap output diberi label "Draft / Rekomendasi", agar tidak disalahartikan sebagai keputusan final | Label tampil di UI dan pada hasil ekspor | FR-SYS-05 | M | 2 | S3 |
| US-08 | Backend | Sebagai **Admin Sistem**, saya ingin melihat audit log, agar dapat menelusuri siapa melakukan apa | Log memuat pengguna, waktu, aksi, dokumen, mode; dapat difilter | FR-SYS-07, NFR-10 | M | 5 | S2 |
| US-09 | Frontend | Sebagai **Analis**, saya ingin melihat status pekerjaan yang sedang berjalan, agar tidak menebak progres | Status antrian/proses/selesai/gagal tampil dan diperbarui | FR-SYS-09 | S | 3 | S2 |
| US-10 | Backend | Sebagai **Analis**, saya ingin setiap eksekusi analisa tersimpan riwayatnya, agar hasil dapat diulang dan ditelusuri | Riwayat memuat input, mode, versi aturan, output | FR-SYS-10, NFR-11 | M | 5 | S4 |
| US-11 | Infra/QA | Sebagai **tim**, kami ingin lingkungan staging & CI siap, agar setiap perubahan teruji otomatis | Pipeline build & test berjalan pada setiap perubahan | — | M | 4 | S0 |

### EP-01 — Scraping & Ingest Dokumen

| ID | **Peran** | User Story | AC Ringkas | FR | Pri | SP | Sprint |
| --- | --- | --- | --- | --- | --- | --- | --- |
| US-12 | Backend | Sebagai **Admin KB**, saya ingin menambah/mengubah/menonaktifkan daftar URL situs sumber, agar sumber dokumen terkelola | CRUD situs berfungsi; minimal 3 situs dikelola; URL divalidasi & unik | FR-SCR-01 | M | 5 | S1 |
| US-13 | Data/ML | Sebagai **Admin KB**, saya ingin menjalankan scraping atas situs terpilih, agar dokumen PDF tertarik otomatis | Dokumen PDF pada halaman target terunduh & tercatat sumbernya | FR-SCR-02 | M | 8 | S1 |
| US-14 | Backend | Sebagai **Admin KB**, saya ingin melihat ringkasan hasil setiap job scraping, agar tahu apa yang berhasil dan gagal | Jumlah berhasil/duplikat/gagal + alasan gagal tampil & tersimpan | FR-SCR-03 | M | 3 | S1 |
| US-15 | Backend | Sebagai **Analis**, saya ingin mengunggah dokumen PDF secara manual (satu atau banyak), agar dokumen di luar situs sumber tetap bisa masuk | Unggah tunggal & jamak berhasil; notifikasi hasil per berkas | FR-SCR-04 | M | 5 | S1 |
| US-16 | Backend | Sebagai **Admin KB**, saya ingin sistem membaca dokumen dari folder lokal yang dikonfigurasi, agar arsip yang sudah ada dapat dimanfaatkan | Minimal 1 folder lokal terbaca; dokumen baru terdeteksi saat job dijalankan | FR-SCR-05 | M | 5 | S2 |
| US-17 | Backend | Sebagai **Admin KB**, saya ingin sistem membaca dokumen dari folder OneDrive *public*, agar arsip daring ikut terkumpul | Minimal 1 folder OneDrive public terbaca | FR-SCR-06 | M | 8 | S2 |
| US-18 | Backend | Sebagai **sistem**, saya harus menolak berkas non-PDF disertai alasan, agar KB tetap bersih | Berkas non-PDF ditolak, tidak masuk KB, tercatat di log | FR-SCR-07 | M | 3 | S1 |
| US-19 | Backend | Sebagai **sistem**, saya harus mendeteksi dokumen duplikat, agar tidak ada penyimpanan ganda | Dokumen identik (hash/nomor peraturan) tidak tersimpan ganda; ada notifikasi | FR-SCR-08 | S | 5 | S2 |
| US-20 | Data/ML | Sebagai **sistem**, saya harus mengekstraksi judul, nomor peraturan, dan tanggal terbit, agar dokumen dapat diidentifikasi | Ketiga metadata terisi otomatis pada dokumen berstruktur baku | FR-SCR-09 | M | 8 | S1 |
| US-21 | Frontend | Sebagai **Analis**, saya ingin mengoreksi metadata hasil ekstraksi, agar data KB akurat | Perubahan tersimpan & tercatat di audit log | FR-SCR-10 | M | 3 | S2 |
| US-22 | Data/ML | Sebagai **sistem**, saya harus memproses PDF hasil pindai melalui OCR, agar dokumen lama tetap dapat dianalisa | Teks dokumen hasil pindai terekstraksi & terindeks | FR-SCR-11 | S | 8 | S2 |
| US-23 | Backend | Sebagai **Analis**, saya ingin melihat daftar dokumen yang gagal diproses dan memprosesnya ulang, agar tidak ada dokumen hilang diam-diam | Daftar gagal dapat dilihat & di-*retry* | FR-SCR-12 | M | 3 | S2 |

### EP-02 — Knowledge Base Terstruktur

| ID | **Peran** | User Story | AC Ringkas | FR | Pri | SP | Sprint |
| --- | --- | --- | --- | --- | --- | --- | --- |
| US-24 | Data/ML | Sebagai **sistem**, saya harus mengklasifikasikan dokumen ke kategori berdasarkan aturan yang dapat dikonfigurasi | Dokumen uji terklasifikasi sesuai kategori; aturan dapat diubah tanpa ubah kode | FR-KB-01, NFR-15 | M | 8 | S2 |
| US-25 | Backend | Sebagai **sistem**, saya harus menempatkan dokumen ke folder eksisting bila kategori sudah ada, dan membuat folder baru bila belum | Tidak ada duplikasi folder; folder baru mengikuti konvensi penamaan | FR-KB-02, FR-KB-03 | M | 5 | S2 |
| US-26 | Backend | Sebagai **sistem**, saya harus menyimpan dokumen beserta metadata, teks, dan struktur pasal | Seluruh atribut wajib pada Data Dictionary terisi | FR-KB-04 | M | 5 | S1 |
| US-27 | Backend | Sebagai **Analis**, saya ingin mencari dokumen berdasarkan kata kunci, nomor, kategori, tanggal, dan status keberlakuan | Hasil relevan, dapat difilter; respons < 3 detik pada skala MVP | FR-KB-05, NFR-02 | M | 8 | S2 |
| US-28 | Frontend | Sebagai **Analis**, saya ingin melihat detail dokumen beserta struktur bab/pasal/ayat | Struktur tampil hierarkis & dapat dinavigasi | FR-KB-06 | M | 5 | S2 |
| US-29 | Backend | Sebagai **Admin KB**, saya ingin dokumen yang diunggah ulang tersimpan sebagai versi baru, agar riwayat tidak hilang | Versi lama tetap dapat diakses | FR-KB-07 | S | 5 | S3 |
| US-30 | Backend | Sebagai **Admin KB**, saya ingin memindahkan/mengubah kategori/menonaktifkan dokumen | Perubahan tercatat di audit log | FR-KB-08 | S | 3 | S3 |
| US-31 | Backend | Sebagai **Analis**, saya ingin peraturan yang dicabut tetap tersimpan dan ditandai jelas, agar riwayat regulasi utuh | Status "dicabut" terlihat di UI & hasil pencarian; dokumen tidak dihapus | FR-KB-09 | M | 3 | S2 |

### EP-03 — Analisa, Summary & Key Takeaways

| ID | **Peran** | User Story | AC Ringkas | FR | Pri | SP | Sprint |
| --- | --- | --- | --- | --- | --- | --- | --- |
| US-32 | Data/ML | Sebagai **sistem**, saya harus mengekstraksi struktur bab/pasal/ayat berdasarkan pola penomoran baku | Struktur benar pada ≥ 80% dokumen uji berstruktur baku | FR-ANL-01 | M | 13 | S3 |
| US-33 | Data/ML | Sebagai **Analis**, saya ingin melihat dasar hukum yang dirujuk dokumen | Daftar dasar hukum tampil & tertaut ke dokumen KB bila tersedia | FR-ANL-02 | M | 5 | S3 |
| US-34 | Data/ML | Sebagai **Analis**, saya ingin mengetahui status keberlakuan dokumen | Status terisi; sumber penetapan status dapat ditelusuri | FR-ANL-03 | M | 5 | S3 |
| US-35 | Data/ML | Sebagai **Analis**, saya ingin sistem menghasilkan ringkasan isi peraturan | Summary dihasilkan untuk ≥ 10 dokumen uji | FR-ANL-04 | M | 8 | S4 |
| US-36 | Data/ML | Sebagai **Analis**, saya ingin sistem menyusun Key Takeaways | Minimal 3 poin per dokumen, tertaut ke pasal sumbernya | FR-ANL-05 | M | 8 | S4 |
| US-37 | Frontend | Sebagai **Analis**, saya ingin melompat dari poin ringkasan ke teks pasal aslinya, agar dapat memverifikasi | Setiap butir memiliki rujukan pasal yang dapat diklik | FR-ANL-06, NFR-11 | M | 5 | S4 |
| US-38 | Data/ML | Sebagai **Analis**, saya ingin melihat topik/klausul utama dokumen, agar dapat menyaring yang relevan bagi unit saya | Daftar topik dapat difilter | FR-ANL-07 | S | 3 | S4 |
| US-39 | Data/ML | Sebagai **Analis**, saya ingin proses summary selesai di bawah 5 menit per dokumen | Terukur dari timestamp mulai–selesai job | FR-ANL-08, NFR-01 | M | 3 | S4 |
| US-40 | Backend | Sebagai **Analis**, saya ingin mengekspor hasil analisa | Ekspor memuat summary, Key Takeaways, dan rujukan pasal | FR-ANL-09 | S | 5 | S4 |

### EP-04 — Harmonisasi Draft vs Eksisting

| ID | **Peran** | User Story | AC Ringkas | FR | Pri | SP | Sprint |
| --- | --- | --- | --- | --- | --- | --- | --- |
| US-41 | Data/ML | Sebagai **Analis**, saya ingin memilih draft peraturan dan menjalankan harmonisasi terhadap KB | Proses berjalan & menghasilkan laporan | FR-HRM-01 | M | 5 | S5 |
| US-42 | Data/ML | Sebagai **sistem**, saya harus memilih kandidat peraturan eksisting yang relevan untuk dibandingkan | Kandidat relevan; dasar pemilihan dapat dijelaskan ke pengguna | FR-HRM-02 | M | 8 | S5 |
| US-43 | Data/ML | Sebagai **sistem**, saya harus mencocokkan rujukan pasal eksplisit antar dokumen | Rujukan eksplisit terdeteksi & terpetakan | FR-HRM-03 | M | 8 | S5 |
| US-44 | Data/ML | Sebagai **Analis**, saya ingin tahu bila draft merujuk peraturan yang telah dicabut | Rujukan ke peraturan dicabut muncul sebagai temuan | FR-HRM-04 | M | 5 | S5 |
| US-45 | Data/ML | Sebagai **sistem**, saya harus menganalisis kesesuaian makna antar pasal, bukan sekadar kecocokan kata | Pasal beda redaksi tapi bermakna sama terdeteksi | FR-HRM-05 | M | 13 | S5 |
| US-46 | Data/ML | Sebagai **Analis**, saya ingin melihat temuan berlabel konflik / duplikasi / gap | Ketiga jenis temuan dapat dihasilkan & dibedakan | FR-HRM-06..08 | M | 8 | S6 |
| US-47 | Data/ML | Sebagai **Analis**, saya ingin setiap temuan memuat pasal draft, pasal pembanding, jenis, dan tingkat keyakinan | Keempat atribut terisi pada setiap temuan | FR-HRM-09 | M | 3 | S6 |
| US-48 | Data/ML | Sebagai **Analis**, saya ingin membaca ringkasan hasil harmonisasi beserta rekomendasi awal | Laporan memuat ringkasan + daftar temuan + rekomendasi | FR-HRM-10 | M | 5 | S6 |
| US-49 | Frontend | Sebagai **SME/Analis**, saya ingin menandai temuan sebagai valid atau tidak relevan disertai catatan | Penandaan tersimpan sebagai umpan balik & bahan evaluasi recall | FR-HRM-11 | S | 5 | S6 |
| US-50 | Backend | Sebagai **Analis**, saya ingin mengekspor laporan harmonisasi | Laporan dapat diunduh sesuai format yang disepakati | FR-HRM-13 | S | 3 | S6 |

### EP-05 — Draft Tanggapan Berbasis PoV

| ID | **Peran** | User Story | AC Ringkas | FR | Pri | SP | Sprint |
| --- | --- | --- | --- | --- | --- | --- | --- |
| US-51 | Backend | Sebagai **Admin KB**, saya ingin mengelola profil PoV unit fungsi (tugas, fungsi, keilmuan, kata kunci) | Minimal 1 profil (Unit Bisnis IT) tersimpan & dapat dipilih | FR-POV-01 | M | 8 | S6 |
| US-52 | Backend | Sebagai **Admin KB**, saya ingin mengelola template tanggapan baku dan checklist pasal wajib | Template & checklist dapat dikonfigurasi tanpa ubah kode | FR-POV-02, NFR-15 | M | 5 | S6 |
| US-53 | Data/ML | Sebagai **Analis**, saya ingin sistem memeriksa kelengkapan pasal yang wajib ditanggapi | Pasal wajib yang belum ditanggapi ditandai jelas | FR-POV-03 | M | 5 | S7 |
| US-54 | Data/ML | Sebagai **Analis**, saya ingin sistem menyusun narasi draft tanggapan sesuai PoV terpilih | Draft tersusun untuk ≥ 3 draft peraturan uji | FR-POV-04 | M | 13 | S7 |
| US-55 | Data/ML | Sebagai **Analis**, saya ingin melihat pasal yang berdampak pada tugas & fungsi unit beserta alasan relevansinya | Daftar pasal berdampak tampil terpisah dengan alasan | FR-POV-05 | S | 5 | S7 |
| US-56 | Frontend | Sebagai **Analis**, saya ingin menyunting draft tanggapan sebelum diekspor | Perubahan tersimpan sebagai versi baru | FR-POV-06 | M | 5 | S7 |
| US-57 | Backend | Sebagai **Admin Sistem**, saya ingin struktur data PoV mendukung banyak profil meski MVP hanya satu | Penambahan profil kedua tidak memerlukan perubahan skema | FR-POV-07 | M | 3 | S6 |
| US-58 | Backend | Sebagai **Analis**, saya ingin mengekspor draft tanggapan sesuai format template unit | Hasil ekspor sesuai format yang divalidasi pilot user | FR-POV-08 | M | 3 | S7 |

### EP-07 — Dokumentasi, Pengujian & UAT

| ID | **Peran** | User Story | AC Ringkas | FR | Pri | SP | Sprint |
| --- | --- | --- | --- | --- | --- | --- | --- |
| US-59 | Infra/QA | Sebagai **tim**, kami ingin *fallback test* tanpa layanan AI dijalankan pada seluruh fitur | Seluruh fitur lulus tanpa kegagalan proses | NFR-04, FR-SYS-04 | M | 5 | S7 |
| US-60 | Infra/QA | Sebagai **PO**, saya ingin UAT dijalankan dengan minimal 1 pilot user per fitur | 4 fitur lulus UAT; berita acara ditandatangani | CSF-01 | M | 8 | S8 |
| US-61 | PM/BA | Sebagai **pengguna**, saya ingin panduan pengguna berbahasa Indonesia | Panduan mencakup alur unggah → analisa → hasil → ekspor | NFR-18 | M | 5 | S8 |
| US-62 | PM/BA | Sebagai **tim**, kami ingin dokumentasi teknis (arsitektur, API, deployment) lengkap | Dokumentasi selesai 100%, di-*review* PO | NFR-18 | M | 5 | S8 |
| US-63 | PM/BA | Sebagai **PM**, saya ingin evaluasi recall deteksi harmonisasi terdokumentasi | Perhitungan recall ≥ 70% terhadap ground truth SME | FR-HRM-12, M-07 | M | 3 | S7 |

---

## 5. Distribusi Beban per Sprint

| Sprint | Periode | Fokus | SP |
| --- | --- | --- | --- |
| S0 | 31 Agu – 13 Sep | Inception, arsitektur, infra, baseline | 4 + non-story |
| S1 | 14 Sep – 27 Sep | Fondasi platform + scraping inti | 45 |
| S2 | 28 Sep – 11 Okt | Folder eksternal, OCR, KB & pencarian | **72** |
| S3 | 12 Okt – 25 Okt | Mode pemrosesan + parsing struktur | 43 |
| S4 | 26 Okt – 8 Nov | Summary, Key Takeaways, ekspor | 42 |
| S5 | 9 Nov – 22 Nov | Mesin harmonisasi | 39 |
| S6 | 23 Nov – 6 Des | Temuan & laporan harmonisasi + fondasi PoV | 40 |
| S7 | 7 Des – 20 Des | Penyusunan tanggapan PoV + fallback test | 39 |
| S8 | 21 Des – 24 Des | UAT, dokumentasi, penutupan | 18 |
| | | **Total** | **342** |

> **Catatan PM — S2 kelebihan beban dan harus diseimbangkan.** Dengan 72 SP, Sprint 2 memikul
> beban ~58% di atas rata-rata sprint pengembangan (≈46 SP). Penyebabnya US-17 (OneDrive),
> US-22 (OCR), US-24 (klasifikasi), dan US-27 (pencarian) menumpuk di sprint yang sama.
> **Opsi penyeimbangan:**
> 1. Turunkan US-22 (OCR, prioritas *Should*, 8 SP) ke S3 — dampak terkecil karena OCR bukan
>    prasyarat fitur lain.
> 2. Turunkan US-19 (deteksi duplikat, *Should*, 5 SP) ke S3.
> 3. Naikkan US-08/US-09 (audit log & status job, 8 SP) ke S1 bila kapasitas S1 tersisa.
>
> Angka SP di atas adalah **estimasi awal BA/PM, bukan komitmen tim**. Estimasi final ditetapkan
> tim di Sprint Planning, dan distribusi ini direvisi setelah *velocity* S1 diketahui.

---

## 5A. Story Baru & Revisi — Hasil Weekly Update #1 (8 Sep 2026)

Sumber: [MoM Weekly Update #1](14-mom-weekly-update-01.md).

### 5A.1 Story Baru

| ID | **Peran** | User Story | AC Ringkas | FR | Pri | SP | Sprint |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **US-13a** | Data/ML | Sebagai **Admin KB**, saya ingin menentukan kedalaman penelusuran per situs sumber, agar scraper tidak menelusuri terlalu dalam sejak awal | Kedalaman dapat diatur per sumber; nilai awal `1`; kedalaman > 1 menelusuri tautan di dalam halaman | FR-SCR-02 | M | 5 | S1 |
| **US-15a** | Backend | Sebagai **Analis**, saya ingin memilih apakah berkas yang saya unggah adalah **draft peraturan baru** atau **peraturan eksisting**, agar draft yang dikaji tidak mengotori corpus pembanding | Pilihan tampil **sebelum** unggah; draft tidak masuk daftar kandidat pembanding harmonisasi | FR-SCR-04 | M | 3 | S1 |
| **US-20a** | Data/ML | Sebagai **sistem**, saya harus meng-OCR halaman pertama untuk mengambil nomor peraturan, tanggal, dan judul, lalu menerapkannya sebagai penamaan berkas baku sebelum masuk folder | Ketiga unsur terbaca dari halaman 1; nama berkas mengikuti konvensi; gagal baca → antrian koreksi manual | FR-SCR-09 | M | 5 | S2 |
| **US-26a** | Backend | Sebagai **sistem**, saya harus menyimpan **PDF asli** dan **blok terstruktur di basis data** sekaligus, agar dokumen tetap dapat diverifikasi manual sekaligus terindeks | PDF asli dapat dibuka dari detail dokumen; blok pasal tersimpan & terindeks | FR-KB-04 | M | 5 | S3 |
| **US-49a** | Frontend | Sebagai **Validator DPEA**, saya ingin membuka PDF asli peraturan yang dikutip langsung dari sebuah temuan, agar dapat memeriksa apakah pasalnya benar berbunyi demikian | Tautan "Buka PDF Asli" tersedia di setiap temuan & butir Key Takeaway | FR-HRM-09, NFR-11 | M | 2 | S6 |
| **US-64** | PM/BA | Sebagai **BA**, saya ingin merumuskan aturan klasifikasi harmonisasi bersama mitra, agar ambang "menggantikan / memperjelas / pasal baru" terdefinisi sebelum dibangun | Aturan tertulis & disetujui PO; mencakup ambang kemiripan yang belum dijawab di rapat | FR-HRM-06..08 | M | 5 | S3 |
| **US-32a** | Data/ML | Sebagai **tim Data**, kami ingin membuat purwarupa parser struktur pasal atas 20 dokumen nyata, agar asumsi penomoran baku teruji lebih awal | Laporan tingkat keberhasilan parsing per dokumen; pola kegagalan teridentifikasi | FR-ANL-01 | M | 5 | S2 |

### 5A.2 Story yang Kriteria Penerimaannya Direvisi

| ID | Perubahan AC | Alasan |
| --- | --- | --- |
| US-15 | Unggah manual **bukan** jalur utama pengisian corpus, melainkan jalur masuk draft peraturan yang dikaji | Klarifikasi mitra: "upload manual diperlukan jika ada dokumen draft peraturan baru yang ingin dianalisa" |
| US-19 | Metode deduplikasi ditetapkan: **kesamaan hash DAN ukuran berkas**. UI menampilkan alasan duplikat beserta dokumen pembandingnya | KEP-06 |
| US-46 | Klasifikasi temuan berubah menjadi **menggantikan / memperjelas / pasal baru / duplikasi / konflik**, menggantikan `konflik/duplikasi/gap` | Contoh kasus pelaporan bank dari mitra (MoM §5.5) |
| US-47 | Setiap temuan wajib memuat **kutipan pasal beserta tautan ke PDF asli** | Prasyarat metode validasi *sampling* DPEA (KEP-08) |
| US-54 | Keluaran harus menyerupai **surat tanggapan tertulis format baku DPEA**, bukan sekadar naskah bebas | "Gimana caranya aplikasi bisa mengeluarkan output yang sama seperti surat tanggapan tertulis yang sudah biasa kami pakai" |
| US-63 | Evaluasi recall memakai **sampling 2–3 dari 10 dokumen**, bukan *ground truth* menyeluruh | KEP-08 — mengurangi beban SME secara signifikan |
| US-17 | OneDrive tidak lagi wajib di Fase 1 — bergantung pada kesiapan mitra menyediakan folder | "Saya akan beritahu ke teman-teman kalau sudah tersedia di folder OneDrive" |

**Total setelah penambahan:** 342 + 30 = **372 SP**

---

## 5B. Analisis Kapasitas Fase 1 — Temuan Kritis

### 5B.1 Kapasitas Nyata Tim

| Parameter | Nilai | Sumber |
| --- | --- | --- |
| Anggota tim | 5 orang | Charter §D |
| Komitmen per anggota | 15–20 jam/minggu | Charter §C |
| Durasi sprint | 2 minggu | Charter §C |
| Kapasitas kotor per sprint | 5 × 17,5 × 2 = **175 jam** | Perhitungan |
| Konversi 1 SP | ± 4 jam efektif | Asumsi tim |
| **Kapasitas realistis per sprint** | **± 44 SP** | 175 ÷ 4 |
| **Kapasitas Fase 1 (S1 + S2)** | **± 88 SP** | — |

### 5B.2 Kebutuhan vs Kapasitas

| | SP |
| --- | --- |
| Kebutuhan minimum Fase 1 (seluruh story yang menyentuh 4 indikator mitra) | ± 117 |
| Kapasitas tersedia | ± 88 |
| **Defisit** | **± 29 SP (33% di atas kapasitas)** |

> **Ini bukan alasan untuk memundurkan target, melainkan alasan untuk memilih.** Mitra sendiri
> hanya menetapkan **4 indikator** untuk Fase 1 (MoM §7) — jauh lebih sedikit daripada seluruh
> cakupan yang tim rencanakan. Sisanya dapat masuk backlog dan dibawa ke Fase 2 tanpa memblokir,
> sesuai KEP-11.

### 5B.3 Usulan Komitmen Fase 1 (± 90 SP)

**Sprint 1 — 14 s.d. 27 September (45 SP).** Sasaran: *dokumen berhasil ditarik dan tersimpan.*

| ID | Story | SP |
| --- | --- | --- |
| US-02 | Login | 3 |
| US-12 | Kelola daftar situs sumber | 5 |
| US-13 | Mesin scraping & unduh PDF | 8 |
| US-13a | Kontrol kedalaman crawling | 5 |
| US-14 | Ringkasan hasil job | 3 |
| US-15 | Unggah manual | 5 |
| US-15a | Pilih tipe dokumen (draft / eksisting) | 3 |
| US-18 | Tolak berkas non-PDF | 3 |
| US-19 | Deteksi duplikat (hash + ukuran) | 5 |
| US-26 | Simpan dokumen + metadata + teks | 5 |

**Sprint 2 — 28 September s.d. 11 Oktober (45 SP).** Sasaran: *dokumen teridentifikasi, terklasifikasi, dan dapat dicari.*

| ID | Story | SP |
| --- | --- | --- |
| US-20 | Ekstraksi metadata dasar | 8 |
| US-20a | OCR halaman 1 & naming convention | 5 |
| US-21 | Koreksi metadata manual | 3 |
| US-23 | Antrian dokumen gagal | 3 |
| US-16 | Baca folder lokal | 5 |
| US-24 | Klasifikasi kategori (versi sederhana) | 5 |
| US-25 | Folder eksisting / folder baru | 5 |
| US-27 | Pencarian dasar (kata kunci + nomor) | 5 |
| US-28′ | Detail dokumen (teks mentah, belum struktur pasal) | 3 |
| US-32a | **Spike** purwarupa parser atas 20 dokumen nyata | 5 |

**Digeser ke backlog Fase 2** (tercatat, bukan dibatalkan):

| ID | Story | SP | Alasan Digeser |
| --- | --- | --- | --- |
| US-17 | Folder OneDrive | 8 | Folder belum disediakan mitra; menunggu NDA (AI-M2) |
| US-22 | OCR dokumen penuh | 8 | OCR halaman 1 sudah dicakup US-20a; OCR penuh baru dibutuhkan saat analisa isi |
| US-01 | Manajemen peran pengguna | 5 | Fase 1 cukup satu peran |
| US-03 | Beranda / dashboard | 3 | Bukan indikator Fase 1 |
| US-08 | Audit log | 5 | Bukan indikator Fase 1 |
| US-09 | Status pekerjaan berjalan | 3 | Status ringkas sudah ada di US-14 |
| US-26a | Penyimpanan blok terstruktur | 5 | Bergantung pada parser (US-32) |
| US-29, US-30, US-31 | Versioning, kelola dokumen, status dicabut | 11 | Bukan indikator Fase 1 |

### 5B.4 Temuan Dependensi — Parser Struktur Pasal

Rancangan penyimpanan ganda (US-26a) menyimpan **blok pasal** di basis data. Blok itu hanya ada
bila parser struktur (US-32, 13 SP) sudah jalan — padahal US-32 dijadwalkan Sprint 3.

**Dua pilihan, dan keduanya punya konsekuensi:**

| Opsi | Konsekuensi |
| --- | --- |
| **A. Tarik US-32 ke Fase 1** | Menambah 13 SP ke sprint yang sudah defisit 29 SP. Tidak realistis |
| **B. Fase 1 menyimpan teks mentah saja; struktur pasal menyusul di Fase 2** | Indikator mitra tetap tercapai (mereka hanya meminta 20 dokumen masuk KB, tidak meminta struktur pasal). Layar detail dokumen Fase 1 menampilkan teks mentah, bukan hierarki bab/pasal/ayat |

**Rekomendasi: Opsi B**, ditambah *spike* US-32a di Sprint 2 untuk menguji asumsi penomoran baku
pada 20 dokumen nyata. Alasannya: parser menopang tiga fitur sekaligus (summary, harmonisasi,
tanggapan). Menemukan bahwa penomoran dokumen OJK tidak sebaku asumsi pada bulan November akan
jauh lebih mahal daripada menemukannya di akhir September — dan *spike* 5 SP jauh lebih murah
daripada memaksakan 13 SP ke dalam sprint yang sudah kelebihan beban.

---

## 6. Backlog Fase Berikutnya (Tidak Dikerjakan pada MVP)

| ID | Item | Alasan Ditunda | Sumber |
| --- | --- | --- | --- |
| BL-01 | Dukungan multi-PoV / banyak unit fungsi | Di luar lingkup MVP | Charter B.2 |
| BL-02 | *Auto-crawling* berjadwal tanpa input manual | Di luar lingkup MVP | Charter B.2 |
| BL-03 | Integrasi *real-time* dengan JDIH nasional / sistem instansi lain | Perlu kesepakatan lanjutan | Charter B.2 |
| BL-04 | Pemrosesan dokumen non-PDF (Word, Excel) | Fokus MVP pada PDF | Charter B.2 |
| BL-05 | Notifikasi otomatis saat terbit peraturan baru | Belum diminta | Usulan tim |
| BL-06 | Dasbor analitik tren regulasi | Belum diminta | Usulan tim |

---

## Riwayat Revisi

| Versi | Tanggal | Perubahan | Penyusun |
| --- | --- | --- | --- |
| 1.0 | 7 Sep 2026 | Draft awal: 7 epic, 63 user story, DoR/DoD, distribusi sprint | PM/BA |
