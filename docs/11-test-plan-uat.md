# TEST PLAN & UAT SCENARIO
**Proyek:** HERO | **Versi:** 1.1 | **Tanggal:** 8 September 2026 | **Penyusun:** PM/BA bersama QA

---

## 1. Strategi Pengujian

| Level | Cakupan | Pelaksana | Waktu |
| --- | --- | --- | --- |
| **Unit Test** | Fungsi & komponen individual | Developer | Setiap perubahan kode |
| **Integration Test** | Antar modul (ingest → KB → analisa) | Developer + QA | Setiap sprint |
| **System Test** | Alur end-to-end pada staging | QA | Akhir setiap sprint |
| **Fallback Test** | Seluruh fitur tanpa layanan AI | QA | Akhir Fase 2, 3, 4, dan 5 |
| **Performance Test** | NFR-01, NFR-02, NFR-03 | QA | Akhir Fase 2 & Fase 5 |
| **Security Test** | Autentikasi, otorisasi, aliran data (NDA) | Infra/QA | Akhir Fase 1 & Fase 5 |
| **Validasi Sampling DPEA** | Kebenaran kutipan pasal pada hasil analisa & harmonisasi | **Faris & Andika (DPEA)** | Akhir tiap fase, mulai Fase 2 |
| **User Acceptance Test (UAT)** | Penerimaan pengguna atas 4 fitur utama | Pilot User + PO | Fase 5 |

### 1.1 Kriteria Masuk (Entry Criteria) UAT

1. Seluruh test case System Test untuk fitur terkait lulus.
2. Tidak ada *defect* severity Kritis atau Tinggi yang terbuka.
3. Lingkungan UAT tersedia dengan dataset uji yang disepakati.
4. Panduan pengguna versi draft sudah tersedia.
5. Pilot user telah ditunjuk dan dijadwalkan.

### 1.2 Kriteria Keluar (Exit Criteria) UAT

1. Seluruh skenario UAT berstatus **Lulus** atau **Lulus dengan Catatan**.
2. Tidak tersisa *defect* Kritis/Tinggi.
3. Metrik M-01 s.d. M-12 terverifikasi atau tercatat alasannya bila tidak tercapai.
4. Berita acara UAT ditandatangani PO dan pilot user.

### 1.2a Metode Validasi Sampling DPEA

Metode ini ditetapkan mitra pada Weekly Update #1 (KEP-08) dan **menggantikan** rencana awal
berupa penyusunan *ground truth* menyeluruh oleh SME.

| Langkah | Ketentuan |
| --- | --- |
| 1 | Sistem menjalankan analisa/harmonisasi atas **10 dokumen** |
| 2 | Validator DPEA mengambil **2–3 dokumen** sebagai sampel |
| 3 | Untuk setiap kutipan pada hasil, validator **membuka peraturan yang disebut** |
| 4 | Validator memeriksa: apakah pasal tersebut benar-benar berbunyi seperti yang dikutip sistem |
| 5 | Hasil penilaian dicatat sebagai umpan balik per temuan |

**Konsekuensi bagi produk — bukan sekadar bagi pengujian:**

1. **Setiap butir keluaran wajib menyebut pasal sumbernya secara eksplisit.** Tanpa kutipan,
   metode validasi ini tidak dapat dijalankan sama sekali.
2. **PDF asli wajib dapat dibuka langsung dari temuan** (FR-KB-04a, US-49a). Validator tidak
   akan mencari dokumennya secara manual di luar sistem.
3. Kutipan harus menampilkan **teks pasal apa adanya**, bukan parafrase — parafrase membuat
   validator tidak dapat menilai benar atau salah.

> **Catatan PM — beban validasi turun drastis.** Rencana awal mensyaratkan SME menandai seluruh
> ketidakselarasan pada 5 pasang dokumen sebagai penyebut recall; itu pekerjaan berhari-hari.
> Metode sampling menurunkannya menjadi pemeriksaan 2–3 dokumen per putaran. RSK-06 turun dari
> Kritis ke Sedang karenanya.

### 1.3 Klasifikasi Severity Defect

| Severity | Definisi | SLA Perbaikan |
| --- | --- | --- |
| **Kritis** | Fitur utama tidak dapat digunakan; data hilang/rusak; kebocoran data | 1 hari kerja |
| **Tinggi** | Fitur utama berjalan salah; hasil analisa keliru secara substansial | 2 hari kerja |
| **Sedang** | Fitur berjalan tapi tidak sesuai spesifikasi; ada jalan pintas (*workaround*) | Sprint berjalan |
| **Rendah** | Kosmetik, penulisan, ketidaknyamanan minor | Backlog |

---

## 2. Test Case

Format: **ID · Deskripsi · Prakondisi · Langkah · Hasil Diharapkan · FR**

### 2.1 Scraping & Ingest (TC-01 … TC-12)

| ID | Deskripsi | Langkah Ringkas | Hasil Diharapkan | FR |
| --- | --- | --- | --- | --- |
| TC-01 | Kelola daftar situs sumber | Tambah, ubah, nonaktifkan, hapus URL | Data tersimpan; URL tidak valid & duplikat ditolak | FR-SCR-01 |
| TC-02 | Scraping dari 3 situs sumber | Pilih 3 situs → jalankan job | Dokumen PDF terunduh & tercatat sumbernya; **M-01 terpenuhi** | FR-SCR-02 |
| TC-03 | Ringkasan hasil job scraping | Jalankan job dengan 1 situs sengaja tidak dapat diakses | Ringkasan menampilkan berhasil/duplikat/gagal + alasan; job tetap selesai | FR-SCR-03 |
| TC-04 | Unggah manual banyak berkas | Unggah 5 PDF sekaligus | Semua masuk antrian; notifikasi hasil per berkas | FR-SCR-04 |
| TC-05 | Baca folder lokal | Konfigurasi 1 folder lokal berisi PDF → jalankan sinkron | Dokumen terbaca & masuk KB | FR-SCR-05 |
| TC-06 | Baca folder OneDrive public | Konfigurasi 1 folder OneDrive public → jalankan sinkron | Dokumen terbaca & masuk KB | FR-SCR-06 |
| TC-07 | Tolak berkas non-PDF | Unggah berkas Word/Excel | Ditolak dengan alasan jelas; tidak masuk KB; tercatat di log kegagalan | FR-SCR-07 |
| TC-08 | Ekstraksi metadata dasar | Ingest dokumen berstruktur baku | Judul, nomor peraturan, tanggal terbit terisi otomatis | FR-SCR-09 |
| TC-09 | Deteksi duplikat | Unggah dokumen yang sama dua kali | Unggahan kedua ditandai duplikat; tidak tersimpan ganda | FR-SCR-08 |
| TC-10 | Koreksi metadata manual | Ubah nomor peraturan hasil ekstraksi yang salah | Perubahan tersimpan & tercatat di audit log | FR-SCR-10 |
| TC-11 | OCR pada PDF hasil pindai | Ingest PDF hasil scan | Teks terekstraksi & dapat dicari | FR-SCR-11 |
| TC-12 | Ketahanan batch | Ingest batch berisi 1 berkas rusak di antara berkas normal | Berkas rusak masuk antrian penanganan; berkas lain tetap selesai | FR-SCR-12, NFR-05 |

### 2.2 Knowledge Base (TC-13 … TC-20)

| ID | Deskripsi | Langkah Ringkas | Hasil Diharapkan | FR |
| --- | --- | --- | --- | --- |
| TC-13 | Klasifikasi otomatis | Ingest dokumen dari kategori yang sudah ada | Ditempatkan ke folder eksisting, tanpa folder ganda | FR-KB-01, 02 |
| TC-14 | Pembuatan folder baru | Ingest dokumen dari kategori yang belum ada | Folder baru dibuat sesuai konvensi penamaan | FR-KB-03 |
| TC-15 | Ubah aturan klasifikasi & kelola dokumen | Ubah aturan lewat konfigurasi; pindahkan dokumen antar kategori | Perubahan berlaku tanpa mengubah kode; tercatat di audit log | FR-KB-08, NFR-15 |
| TC-16 | Versioning dokumen | Unggah ulang dokumen dengan identitas sama | Tersimpan sebagai versi baru; versi lama tetap dapat diakses | FR-KB-07 |
| TC-17 | Pencarian multi-kriteria | Cari berdasarkan kata kunci, nomor, kategori, tanggal, status | Hasil relevan & dapat difilter | FR-KB-05 |
| TC-18 | Kinerja pencarian | Jalankan 10 pencarian pada KB skala MVP | Setiap respons < 3 detik | NFR-02 |
| TC-19 | Kapasitas KB | Isi KB dengan ≥ 100 dokumen lalu jalankan pencarian & analisa | Tidak ada degradasi berarti | NFR-03 |
| TC-20 | Penandaan peraturan dicabut | Tandai satu dokumen sebagai dicabut | Status terlihat di UI & hasil pencarian; dokumen tidak hilang | FR-KB-09 |

### 2.3 Analisa, Summary & Key Takeaways (TC-21 … TC-29)

| ID | Deskripsi | Langkah Ringkas | Hasil Diharapkan | FR |
| --- | --- | --- | --- | --- |
| TC-21 | Parsing struktur bab/pasal/ayat | Analisa 10 dokumen berstruktur baku | Struktur benar pada ≥ 8 dari 10 dokumen | FR-ANL-01 |
| TC-22 | Identifikasi dasar hukum | Analisa dokumen yang memuat daftar dasar hukum | Daftar tampil & tertaut ke dokumen KB bila tersedia | FR-ANL-02 |
| TC-23 | Identifikasi status keberlakuan | Analisa dokumen yang telah dicabut | Status "dicabut" terisi; sumber penetapan dapat ditelusuri | FR-ANL-03 |
| TC-24 | Pembuatan summary | Analisa 10 dokumen uji | Summary dihasilkan untuk seluruhnya; **M-03 terpenuhi** | FR-ANL-04 |
| TC-25 | Key Takeaways | Analisa 1 dokumen | Minimal 3 poin dihasilkan | FR-ANL-05 |
| TC-26 | Ketertelusuran ke pasal | Buka setiap butir Key Takeaway | Seluruh butir memiliki rujukan pasal yang dapat dibuka | FR-ANL-06, NFR-11 |
| TC-27 | Identifikasi topik utama | Analisa dokumen lalu filter topik | Daftar topik tampil & dapat difilter | FR-ANL-07 |
| TC-28 | Kinerja summary | Ukur waktu proses 10 dokumen (mode Deterministik) | Setiap dokumen selesai < 5 menit; **M-04 terpenuhi** | FR-ANL-08, NFR-01 |
| TC-29 | Ekspor hasil analisa | Ekspor hasil 1 dokumen | Berkas memuat summary, Key Takeaways, rujukan pasal, label "Draft / Rekomendasi" | FR-ANL-09 |

### 2.4 Harmonisasi (TC-30 … TC-40)

| ID | Deskripsi | Langkah Ringkas | Hasil Diharapkan | FR |
| --- | --- | --- | --- | --- |
| TC-30 | Jalankan harmonisasi | Pilih draft → jalankan proses | Laporan harmonisasi dihasilkan | FR-HRM-01 |
| TC-31 | Pemilihan kandidat pembanding | Jalankan harmonisasi pada draft bertopik spesifik | Kandidat relevan terpilih; dasar pemilihan dapat dilihat pengguna | FR-HRM-02 |
| TC-32 | Pencocokan rujukan eksplisit | Gunakan draft yang menyebut pasal peraturan lain | Rujukan terdeteksi & terpetakan | FR-HRM-03 |
| TC-33 | Rujukan ke peraturan dicabut | Gunakan draft yang merujuk peraturan berstatus dicabut | Muncul temuan `rujukan_dicabut` | FR-HRM-04 |
| TC-34 | Analisis kesesuaian substansi | Siapkan pasal berbeda redaksi namun bermakna sama | Terdeteksi sebagai terkait, bukan terlewat | FR-HRM-05 |
| TC-35 | Klasifikasi **MENGGANTIKAN** | Siapkan pasal draft yang mengatur objek sama dengan ketentuan berbeda (contoh mitra: denda keterlambatan 1% flat → per hari) | Muncul temuan `menggantikan` beserta pasal yang digugurkan | FR-HRM-06 |
| TC-36 | Klasifikasi **MEMPERJELAS** dan **DUPLIKASI** | Siapkan pasal dengan substansi sama namun diperinci, serta pasal identik | Terbedakan sebagai `memperjelas` dan `duplikasi` | FR-HRM-07, 08a |
| TC-37 | Klasifikasi **PASAL BARU** | Siapkan pengaturan yang belum ada di corpus (contoh mitra: denda yang sebelumnya tidak diatur) | Muncul temuan `pasal_baru`; **tidak** ditandai sebagai penggantian | FR-HRM-08 |
| **TC-37a** | Klasifikasi **KONFLIK** | Siapkan dua pasal bertentangan yang sama-sama berlaku | Muncul temuan `konflik` | FR-HRM-08b |
| TC-38 | Kelengkapan atribut & penandaan temuan | Periksa 1 temuan lalu tandai valid/tidak relevan | Pasal draft, pasal pembanding, jenis, tingkat keyakinan terisi; penandaan tersimpan | FR-HRM-09, 11 |
| TC-39 | Ringkasan & rekomendasi | Buka laporan hasil | Memuat ringkasan, daftar temuan, rekomendasi awal, label "Draft / Rekomendasi" | FR-HRM-10 |
| TC-40 | Evaluasi recall & ekspor laporan | Jalankan 10 dokumen; validator DPEA ambil 2–3 sampel, buka peraturan yang dikutip, periksa kebenaran bunyi pasal; ekspor laporan | Recall ≥ 70% pada sampel; **M-06 & M-07 terpenuhi**; laporan dapat diunduh | FR-HRM-12, 13 |
| **TC-40a** | Kesiapan validasi sampling | Buka satu temuan → klik tautan PDF asli peraturan yang dikutip | PDF asli terbuka; kutipan pasal ditampilkan apa adanya, bukan parafrase | FR-KB-04a, FR-HRM-09 |

### 2.5 Draft Tanggapan PoV (TC-41 … TC-48)

| ID | Deskripsi | Langkah Ringkas | Hasil Diharapkan | FR |
| --- | --- | --- | --- | --- |
| TC-41 | Kelola profil PoV | Buat profil Unit Bisnis IT | Profil tersimpan & dapat dipilih saat penyusunan | FR-POV-01 |
| TC-42 | Penerapan template baku | Susun tanggapan memakai template unit | Struktur output sesuai template | FR-POV-02 |
| TC-43 | Pemeriksaan checklist pasal wajib | Susun tanggapan atas draft yang sengaja melewatkan 1 pasal wajib | Pasal tersebut ditandai "belum ditanggapi" | FR-POV-03 |
| TC-44 | Penyusunan narasi PoV | Susun tanggapan untuk 3 draft peraturan uji | Draft tersusun untuk ketiganya; **M-08 terpenuhi** | FR-POV-04 |
| TC-45 | Penyorotan pasal berdampak | Buka hasil penyusunan | Daftar pasal berdampak tampil terpisah dengan alasan relevansi | FR-POV-05 |
| TC-46 | Dukungan struktur multi-PoV | Tambahkan profil PoV kedua | Berhasil tanpa perubahan skema | FR-POV-07 |
| TC-47 | Penyuntingan draft | Sunting narasi lalu simpan | Tersimpan sebagai versi baru; versi sebelumnya tetap ada | FR-POV-06 |
| TC-48 | Ekspor tanggapan | Ekspor draft tanggapan | Format sesuai template unit; label "Draft / Rekomendasi" melekat | FR-POV-08 |

### 2.6 Platform, Mode & Non-Fungsional (TC-49 … TC-60)

| ID | Deskripsi | Langkah Ringkas | Hasil Diharapkan | FR/NFR |
| --- | --- | --- | --- | --- |
| TC-49 | Label status output | Buka hasil analisa, harmonisasi, dan tanggapan | Ketiganya berlabel "Draft / Rekomendasi", termasuk pada hasil ekspor | FR-SYS-05 |
| TC-50 | Toggle mode AI-Assisted | Aktifkan lalu nonaktifkan toggle | Mode tersimpan; default Deterministik; status mode tampil pada hasil | FR-SYS-02 |
| TC-51 | Pemisahan hasil deterministik vs AI | Jalankan 1 dokumen pada kedua mode | Kedua hasil tersimpan terpisah & dapat dibandingkan; substansi hasil dasar tidak berubah | FR-SYS-03 |
| TC-52 | Default deterministik | Jalankan analisa tanpa mengubah pengaturan apa pun | Proses berjalan pada mode Deterministik | FR-SYS-01 |
| TC-53 | **Fallback test tanpa AI** | Matikan layanan AI → jalankan keempat fitur utama | Seluruh proses selesai dengan hasil deterministik + notifikasi; tidak ada kegagalan; **M-12 terpenuhi** | FR-SYS-04, NFR-04 |
| TC-54 | Audit log | Lakukan ingest, analisa, ubah metadata, ekspor → buka audit log | Seluruh aksi tercatat: pengguna, waktu, aksi, entitas, mode | FR-SYS-07, NFR-10 |
| TC-55 | Status pekerjaan & riwayat eksekusi | Jalankan job panjang → pantau status; buka riwayat eksekusi | Status berubah antrian → berjalan → selesai; riwayat memuat input, mode, versi aturan | FR-SYS-09, 10 |
| TC-56 | Autentikasi | Akses fitur tanpa login | Seluruh akses ditolak | FR-SYS-08, NFR-06 |
| TC-57 | Otorisasi peran | Login sebagai Analis → coba akses fitur Admin Sistem | Akses ditolak | FR-SYS-08, NFR-07 |
| TC-58 | Kepatuhan aliran data (NDA) | Telaah aliran data saat AI-Assisted aktif | Tidak ada pengiriman dokumen berklasifikasi non-publik ke pihak ketiga tanpa persetujuan tertulis | NFR-08 |
| TC-59 | Usability alur utama | Pengguna baru menjalankan unggah → analisa → lihat hasil → ekspor | Selesai dengan panduan singkat, tanpa bantuan teknis | NFR-12 |
| TC-60 | Kelengkapan dokumentasi | Review dokumentasi teknis & panduan pengguna | Lengkap 100%; **M-11 terpenuhi** | NFR-18 |

---

## 3. Skenario UAT

Setiap skenario dijalankan oleh minimal 1 pilot user per fitur, didampingi QA.

### UAT-01 — Mengumpulkan Dokumen Peraturan ke Knowledge Base

> **Sebagai** analis regulasi, saya ingin mengumpulkan dokumen peraturan dari berbagai sumber
> sehingga tersimpan rapi dan dapat dicari kembali.

| No. | Langkah | Hasil yang Diharapkan | Lulus/Gagal | Catatan |
| --- | --- | --- | --- | --- |
| 1 | Masuk ke sistem sebagai Analis | Berhasil masuk; menu sesuai peran | | |
| 2 | Tambahkan 3 situs sumber peraturan | Tersimpan di daftar sumber | | |
| 3 | Jalankan scraping | Dokumen PDF tertarik; ringkasan job tampil | | |
| 4 | Unggah 3 dokumen manual | Ketiganya masuk antrian & terproses | | |
| 5 | Jalankan sinkron folder lokal & OneDrive | Dokumen dari kedua folder masuk KB | | |
| 6 | Buka knowledge base | Total ≥ 20 dokumen tersimpan terstruktur | | |
| 7 | Cari dokumen berdasarkan nomor peraturan | Dokumen ditemukan dalam < 3 detik | | |
| 8 | Buka detail satu dokumen | Metadata & struktur bab/pasal/ayat tampil | | |

**Metrik terkait:** M-01, M-02 · **Fitur:** 3.2

---

### UAT-02 — Meringkas Dokumen Peraturan

> **Sebagai** analis regulasi, saya ingin memahami inti sebuah peraturan tanpa harus membaca
> seluruh isinya.

| No. | Langkah | Hasil yang Diharapkan | Lulus/Gagal | Catatan |
| --- | --- | --- | --- | --- |
| 1 | Pilih satu dokumen peraturan panjang dari KB | Detail dokumen tampil | | |
| 2 | Jalankan analisa pada mode Deterministik (default) | Proses selesai < 5 menit | | |
| 3 | Baca ringkasan yang dihasilkan | Isi ringkasan mencerminkan substansi peraturan | | |
| 4 | Periksa Key Takeaways | Minimal 3 poin, masing-masing berujuk pasal | | |
| 5 | Klik salah satu rujukan pasal | Teks pasal asli terbuka | | |
| 6 | Aktifkan AI-Assisted lalu jalankan ulang | Narasi lebih mengalir; substansi tetap sama | | |
| 7 | Bandingkan hasil kedua mode | Keduanya dapat dilihat berdampingan | | |
| 8 | Ekspor hasil analisa | Berkas memuat ringkasan, poin, rujukan, dan label "Draft / Rekomendasi" | | |

**Metrik terkait:** M-03, M-04, M-05 · **Fitur:** 3.3

---

### UAT-03 — Memeriksa Harmonisasi Draft Peraturan

> **Sebagai** analis regulasi, saya ingin mengetahui apakah draft peraturan baru bertentangan,
> tumpang tindih, atau meninggalkan celah terhadap peraturan yang sudah berlaku.

| No. | Langkah | Hasil yang Diharapkan | Lulus/Gagal | Catatan |
| --- | --- | --- | --- | --- |
| 1 | Unggah draft peraturan baru | Draft ter-*parsing*; struktur pasal tampil | | |
| 2 | Jalankan harmonisasi terhadap knowledge base | Proses selesai & laporan dihasilkan | | |
| 3 | Periksa daftar peraturan pembanding | Kandidat relevan; dasar pemilihan dapat dilihat | | |
| 4 | Telaah temuan berjenis `menggantikan` | Pasal draft & pasal yang digugurkan jelas; penjelasan masuk akal | | |
| 5 | Telaah temuan `memperjelas`, `pasal_baru`, `duplikasi`, `konflik` | Kelima jenis temuan dapat dibedakan | | |
| 5a | Buka PDF asli dari salah satu temuan | PDF terbuka; bunyi pasal sesuai dengan yang dikutip sistem | | |
| 6 | Periksa apakah ada rujukan ke peraturan yang telah dicabut | Muncul sebagai temuan tersendiri | | |
| 7 | Tandai satu temuan sebagai "tidak relevan" disertai catatan | Penandaan tersimpan | | |
| 8 | Baca ringkasan & rekomendasi awal | Ringkasan mencerminkan seluruh temuan | | |
| 9 | Ekspor laporan harmonisasi | Laporan dapat diunduh | | |

**Metrik terkait:** M-06, M-07 · **Fitur:** 3.4
**Catatan:** verifikasi recall ≥ 70% dilakukan melalui **validasi sampling DPEA** (§1.2a) —
2–3 sampel dari 10 dokumen, diperiksa langsung oleh Faris & Andika.

---

### UAT-04 — Menyusun Draft Tanggapan Berbasis PoV

> **Sebagai** perwakilan Unit Bisnis IT, saya ingin memperoleh draft tanggapan awal atas
> rancangan peraturan dari sudut pandang tugas dan fungsi unit saya.

| No. | Langkah | Hasil yang Diharapkan | Lulus/Gagal | Catatan |
| --- | --- | --- | --- | --- |
| 1 | Pilih draft peraturan & profil PoV Unit Bisnis IT | Profil termuat | | |
| 2 | Jalankan penyusunan tanggapan | Draft tersusun mengikuti template unit | | |
| 3 | Periksa kelengkapan terhadap checklist pasal wajib | Pasal wajib yang belum ditanggapi ditandai | | |
| 4 | Telaah daftar pasal berdampak bagi unit | Alasan relevansi tercantum dan masuk akal | | |
| 5 | Nilai kesesuaian gaya bahasa dengan kaidah unit | Sesuai atau dapat diperbaiki dengan penyuntingan wajar | | |
| 6 | Sunting satu butir tanggapan lalu simpan | Tersimpan sebagai versi baru | | |
| 7 | Ekspor draft tanggapan | Format sesuai standar unit | | |
| 8 | Pastikan label status | Tertulis "Draft / Rekomendasi", bukan dokumen final | | |

**Metrik terkait:** M-08, M-09 · **Fitur:** 3.5

---

### UAT-05 — Sistem Berjalan Tanpa Layanan AI

> **Sebagai** pemilik proses, saya ingin memastikan sistem tetap dapat dipakai ketika layanan
> AI tidak tersedia.

| No. | Langkah | Hasil yang Diharapkan | Lulus/Gagal | Catatan |
| --- | --- | --- | --- | --- |
| 1 | Nonaktifkan layanan AI pada lingkungan uji | Sistem tetap dapat diakses | | |
| 2 | Jalankan ingest dokumen | Selesai normal | | |
| 3 | Jalankan analisa & summary | Selesai dengan hasil deterministik | | |
| 4 | Jalankan harmonisasi | Selesai dengan hasil deterministik | | |
| 5 | Jalankan penyusunan tanggapan | Selesai dengan hasil deterministik | | |
| 6 | Aktifkan toggle AI-Assisted saat layanan mati | Muncul notifikasi; proses tetap selesai, tidak gagal | | |
| 7 | Periksa seluruh output | Lengkap dan berlabel "Draft / Rekomendasi" | | |

**Metrik terkait:** M-12 · **Kriteria Sukses Proyek:** CSF-02

---

### UAT-06 — Verifikasi Metrik Utama: 2–3 Hari menjadi 2–3 Jam

> **Sebagai** pemilik proses DPEA, saya ingin membuktikan bahwa penyusunan satu tanggapan
> tertulis benar-benar menjadi jauh lebih cepat dibanding cara manual.

| No. | Langkah | Hasil yang Diharapkan | Lulus/Gagal | Catatan |
| --- | --- | --- | --- | --- |
| 1 | Pilih satu draft peraturan nyata yang pernah ditanggapi secara manual | Dokumen tersedia beserta surat tanggapan aslinya sebagai pembanding | | |
| 2 | Catat waktu mulai | Timestamp tercatat | | |
| 3 | Unggah draft, jalankan analisa, harmonisasi, dan penyusunan tanggapan | Seluruh proses selesai | | |
| 4 | Sunting draft tanggapan sampai layak dikirim ke atasan | Naskah siap | | |
| 5 | Catat waktu selesai | **Total < 3 jam** | | |
| 6 | Bandingkan isi dengan surat tanggapan manual yang asli | Pasal yang ditanggapi sebanding; tidak ada pasal penting yang terlewat | | |

**Metrik terkait:** **M-13 (metrik utama proyek)** · **Fitur:** 3.2–3.5 menyeluruh

> **Catatan PM.** Inilah pengujian yang paling berarti bagi mitra. Empat UAT sebelumnya
> membuktikan fitur berfungsi; UAT-06 membuktikan **proyeknya berhasil**. Siapkan draft
> peraturan pembandingnya sejak Fase 4, jangan menjelang UAT.

---

## 4. Jadwal Pengujian

| Kegiatan | Periode | Penanggung Jawab |
| --- | --- | --- |
| Penyusunan test case per fitur | Mengikuti sprint fitur | QA + BA |
| System test Fase 1 | 8 – 11 Okt 2026 | QA |
| System test Fase 2 + performance test | 5 – 8 Nov 2026 | QA |
| Penyiapan berkas uji harmonisasi & sesi validasi sampling DPEA | 9 – 22 Nov 2026 | BA + Validator DPEA |
| System test Fase 3 + evaluasi recall | 26 – 29 Nov 2026 | QA + BA |
| System test Fase 4 | 10 – 13 Des 2026 | QA |
| Fallback test menyeluruh & perbaikan defect | 14 – 20 Des 2026 | QA + Tim |
| **UAT (UAT-01 s.d. UAT-06)** | 21 – 23 Des 2026 | Pilot User + PO + QA |
| Berita acara & penutupan | 24 Des 2026 | PM |

> **Catatan PM — jendela UAT hanya 3 hari.** UAT-01 sampai UAT-05 dijadwalkan pada 21–23
> Desember, tanpa ruang untuk perbaikan *defect* yang ditemukan di dalamnya. **Mitigasi:**
> jalankan "UAT kering" (*dry run*) per fitur pada akhir fasenya masing-masing — Fase 1, 2, 3,
> dan 4 — sehingga sesi UAT resmi menjadi konfirmasi, bukan penemuan masalah pertama kali.

---

## Riwayat Revisi

| Versi | Tanggal | Perubahan | Penyusun |
| --- | --- | --- | --- |
| 1.0 | 7 Sep 2026 | Draft awal: strategi, 60 test case, 5 skenario UAT, jadwal | PM/BA |
| 1.1 | 8 Sep 2026 | Metode validasi sampling DPEA (§1.2a) menggantikan ground truth SME; TC-35..37 diselaraskan dengan klasifikasi baru; TC-37a & TC-40a ditambahkan; UAT-06 verifikasi metrik utama ditambahkan | PM/BA |
