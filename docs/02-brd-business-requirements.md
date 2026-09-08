# BUSINESS REQUIREMENTS DOCUMENT (BRD)
**Proyek:** HERO — Harmonisasi & Analisa Regulasi Otomatis
**Versi:** 1.1 (Draft) | **Tanggal:** 8 September 2026 | **Penyusun:** Business Analyst

---

## 1. Latar Belakang Bisnis

Departemen Pengembangan Aplikasi (DPEA) OJK menjalankan analisa ketentuan dan kebijakan dalam
rangka penyelarasan dengan pengembangan aplikasi. Analisa ini menuntut DPEA membaca peraturan
yang terus bertambah volumenya, memastikan draft peraturan baru selaras dengan peraturan
eksisting, dan menyusun tanggapan dari sudut pandang unit fungsinya.

Seluruh rangkaian tersebut hari ini dikerjakan manual. Konsekuensinya bukan sekadar lambat —
kualitas hasil menjadi bergantung pada ingatan dan pengalaman individu penyusun, sehingga sulit
dijamin konsisten dan sulit ditelusuri ulang.

## 1A. Baseline Proses Berjalan

Angka berikut disampaikan langsung oleh mitra pada Weekly Update #1
([MoM §3](14-mom-weekly-update-01.md)) dan menjadi dasar seluruh metrik proyek.

| Item | Angka |
| --- | --- |
| Kewajiban DPEA | Menyusun **tanggapan tertulis** atas setiap draft peraturan yang masuk, dari sudut pandang IT |
| Volume 2025 | **54 tanggapan** |
| Volume 2026 per Agustus | **40 tanggapan**, masih berjalan |
| Waktu per tanggapan (manual) | **2–3 hari kerja** |
| **Target dengan HERO** | **2–3 jam** |
| Rasio percepatan yang dituju | ± 8–12 kali lebih cepat |

**Penyebab lamanya proses menurut mitra** bukan semata volume bacaan, melainkan **terputusnya
konsentrasi**: *"Kalau orangnya bisa fokus, bisa. Tapi kalau baru kerja setengah jam terus
dipanggil rapat, itu sudah nggak kepegang. Nanti memulai lagi, nyari lagi dokumennya."*

> **Implikasi desain yang mudah terlewat.** Nilai utama HERO bukan hanya "membaca lebih cepat",
> melainkan **membuat pekerjaan dapat ditinggalkan lalu dilanjutkan tanpa kehilangan konteks**.
> Karena itu penyimpanan status pekerjaan, riwayat eksekusi, dan kemampuan mengulang proses
> (FR-SYS-09, FR-SYS-10) bukan fitur pelengkap — keduanya menyerang penyebab masalah secara
> langsung.

### Visi Jangka Panjang Mitra

Bila algoritmanya terbukti bekerja, pola yang sama akan **diduplikasi ke sektor lain** —
perbankan, IKNB, pasar modal, serta edukasi & perlindungan konsumen. *"Tinggal kita ganti
knowledge base-nya saja."*

> **Implikasi arsitektur:** knowledge base harus **dapat ditukar per sektor tanpa mengubah mesin
> analisanya**. Aturan klasifikasi, profil PoV, template, dan checklist wajib berupa konfigurasi,
> bukan logika yang tertanam di kode — ini menguatkan NFR-15 dari sekadar kenyamanan pemeliharaan
> menjadi prasyarat visi mitra.

---

## 2. Pernyataan Masalah

| ID | Masalah | Dampak Bisnis | Bukti/Indikasi |
| --- | --- | --- | --- |
| PB-01 | Pengumpulan dokumen peraturan dilakukan manual satu per satu | Waktu analis habis di pekerjaan administratif, bukan analisa | Volume peraturan terus bertambah |
| PB-02 | Pembacaan & pemahaman dokumen peraturan panjang berbahasa hukum memakan waktu lama | Keterlambatan respons atas draft peraturan | Dokumen dapat mencapai ratusan halaman |
| PB-03 | Harmonisasi manual rawan luput mendeteksi pertentangan, duplikasi, atau *gap* antar pasal | Risiko ketidakselarasan regulasi lolos ke tahap penetapan | Bergantung ingatan/pengalaman individu |
| PB-04 | Penyusunan tanggapan berbasis PoV unit tidak konsisten antar penyusun | Kualitas tanggapan bervariasi, perlu banyak revisi | Belum ada template & checklist baku terotomasi |
| PB-05 | Belum ada sistem terpusat yang konsisten, *traceable*, dan *repeatable* | Pengetahuan tidak terakumulasi; sulit audit ulang | Tidak ada knowledge base peraturan |

## 3. Peluang dan Justifikasi

Empat proses (pengumpulan, peringkasan, harmonisasi, penyusunan tanggapan) memiliki pola kerja
berulang yang dapat dibakukan menjadi aturan. Sebagian besar nilainya dapat dicapai dengan
pendekatan **deterministik berbasis aturan** — tanpa ketergantungan pada layanan AI. AI
ditempatkan sebagai lapisan penyempurna bahasa, bukan sebagai penentu substansi.

Pendekatan ini menjawab dua kebutuhan sekaligus: sistem tetap andal ketika layanan AI tidak
tersedia, dan hasil analisa tetap dapat ditelusuri asal-usulnya (*traceable*) karena berbasis
aturan yang eksplisit.

## 4. Tujuan Bisnis (Business Objectives)

| ID | Tujuan Bisnis | Terkait Masalah |
| --- | --- | --- |
| BO-01 | Mempercepat dan menstrukturkan pengumpulan dokumen peraturan yang telah dipublikasikan | PB-01 |
| BO-02 | Mempercepat pemahaman isi peraturan melalui ringkasan dan Key Takeaways yang konsisten | PB-02 |
| BO-03 | Meningkatkan cakupan dan kecepatan deteksi ketidakselarasan draft terhadap peraturan eksisting | PB-03 |
| BO-04 | Menyeragamkan kualitas dan mempercepat penyusunan draft tanggapan berbasis PoV unit | PB-04 |
| BO-05 | Membangun knowledge base peraturan terpusat yang konsisten, tertelusur, dan dapat diulang | PB-05 |
| BO-06 | Menjamin sistem tetap beroperasi penuh tanpa ketergantungan pada layanan AI | PB-05 |
| BO-07 | Menyiapkan sistem agar dapat dipakai ulang sektor lain dengan mengganti knowledge base-nya | Visi mitra (§1A) |

## 5. Kebutuhan Bisnis (Business Requirements)

| ID | Kebutuhan Bisnis | Tujuan | Prioritas (MoSCoW) |
| --- | --- | --- | --- |
| BR-01 | Sistem dapat menarik dokumen peraturan berformat PDF dari daftar situs yang diinput manual | BO-01 | Must |
| BR-02 | Sistem menyediakan unggah dokumen manual oleh pengguna | BO-01 | Must |
| BR-03 | Sistem dapat membaca dokumen dari folder lokal dan folder OneDrive *public* yang dikonfigurasi | BO-01 | Must |
| BR-04 | Sistem memvalidasi format dan mengekstraksi metadata dasar dokumen | BO-01, BO-05 | Must |
| BR-05 | Sistem mengklasifikasikan dan menempatkan dokumen ke folder knowledge base yang sesuai | BO-05 | Must |
| BR-06 | Sistem mengekstraksi struktur dokumen (bab, pasal, ayat) | BO-02, BO-03 | Must |
| BR-07 | Sistem menghasilkan ringkasan isi peraturan yang lebih ringkas dan mudah dipahami | BO-02 | Must |
| BR-08 | Sistem menyusun Key Takeaways secara otomatis | BO-02 | Must |
| BR-09 | Sistem mengidentifikasi status keberlakuan peraturan (berlaku/dicabut) dan dasar hukumnya | BO-03 | Must |
| BR-10 | Sistem mencocokkan rujukan pasal secara eksplisit antar dokumen | BO-03 | Must |
| BR-11 | Sistem menganalisis kesesuaian makna/substansi antar pasal, bukan sekadar kecocokan kata | BO-03 | Must |
| BR-12 | Sistem mendeteksi potensi konflik, duplikasi, atau celah pengaturan | BO-03 | Must |
| BR-13 | Sistem menyusun ringkasan hasil harmonisasi beserta rekomendasi awal | BO-03 | Must |
| BR-14 | Sistem menerapkan template/format tanggapan baku sesuai standar unit | BO-04 | Must |
| BR-15 | Sistem memeriksa kelengkapan pasal yang wajib ditanggapi berdasarkan checklist | BO-04 | Must |
| BR-16 | Sistem menyusun narasi draft tanggapan sesuai profil PoV yang dipilih | BO-04 | Must |
| BR-17 | Sistem menyoroti pasal yang relevan/berdampak pada tugas & fungsi unit terkait | BO-04 | Should |
| BR-18 | Seluruh fitur dapat dijalankan pada mode Deterministik tanpa layanan AI | BO-06 | Must |
| BR-19 | Pengguna dapat mengaktifkan/menonaktifkan mode AI-Assisted per proses | BO-06 | Must |
| BR-20 | Sistem menyediakan UI untuk unggah, pencarian, dan penyajian hasil | BO-01..BO-04 | Must |
| BR-21 | Seluruh output sistem berstatus draft/rekomendasi dan menyimpan jejak untuk direview manusia | BO-05 | Must |
| BR-22 | Sistem menangani dokumen PDF hasil pindai melalui OCR | BO-01 | Should |
| BR-23 | Sistem mendukung lebih dari satu profil PoV | BO-04 | Won't (MVP) — roadmap fase berikutnya |
| BR-24 | Sistem melakukan *auto-crawling* berjadwal | BO-01 | Won't (MVP) |

## 6. Aturan Bisnis (Business Rules)

| ID | Aturan Bisnis | Implikasi Sistem |
| --- | --- | --- |
| BRule-01 | Keputusan final atas hasil harmonisasi maupun tanggapan adalah kewenangan Pengawas/unit terkait | Sistem tidak boleh menandai hasil sebagai "final"; label wajib "Draft/Rekomendasi" |
| BRule-02 | Mode Deterministik wajib tersedia dan menjadi default di seluruh fitur | AI tidak boleh menjadi jalur tunggal proses apa pun |
| BRule-03 | AI-Assisted hanya boleh menghaluskan bahasa, tidak mengubah substansi hasil deterministik | Hasil deterministik wajib disimpan terpisah & dapat dibandingkan |
| BRule-04 | Hanya dokumen berformat PDF yang diproses pada fitur pengumpulan | Dokumen non-PDF ditolak dengan pesan jelas + dicatat di log |
| BRule-05 | Dokumen yang diproses harus bersifat publik/legal untuk diproses | Perlu penandaan klasifikasi dokumen saat ingest |
| BRule-06 | Seluruh data yang berhubungan dengan DPEA tunduk pada NDA | Larangan distribusi/ekspor ke luar lingkungan yang disepakati |
| BRule-07 | Pada MVP, PoV dibatasi 1 profil unit fungsi | Struktur data PoV tetap dirancang jamak agar tidak perlu *rework* |
| BRule-08 | Peraturan yang berstatus dicabut tetap disimpan, tidak dihapus | Status keberlakuan sebagai atribut, bukan penghapusan data |

## 7. Metrik Keberhasilan Bisnis

| ID | Metrik | Baseline (Saat Ini) | Target | Cara Ukur | Fase |
| --- | --- | --- | --- | --- | --- |
| M-01 | Jumlah situs sumber yang berhasil ditarik dokumennya | 0 (manual) | ≥ 3 situs | Log scraping | 1 |
| M-02 | Jumlah dokumen masuk knowledge base | 0 | ≥ 20 dokumen | Query KB | 1 |
| M-03 | Dokumen berhasil dihasilkan Summary & Key Takeaways | 0 | ≥ 10 dokumen uji | Laporan hasil | 2 |
| M-04 | Waktu proses summary per dokumen (mode Deterministik) | Bagian dari 2–3 hari kerja per tanggapan | < 5 menit | Timestamp sistem | 2 |
| M-05 | Mode AI-Assisted dapat di-*toggle* & narasi lebih natural | — | Berfungsi, divalidasi user | Uji fungsional + penilaian user | 2 |
| M-06 | Pasang dokumen berhasil dibandingkan (draft vs eksisting) | 0 | ≥ 5 pasang | Laporan harmonisasi | 3 |
| M-07 | Recall deteksi potensi konflik/duplikasi | Tidak terukur (bergantung ingatan individu) | ≥ 70% | **Validasi sampling manual DPEA**: 2–3 sampel dari 10 dokumen | 3 |
| **M-13** | **Waktu penyusunan satu tanggapan tertulis, hulu ke hilir** | **2–3 hari kerja** | **2–3 jam** | Pengukuran bersama DPEA saat UAT | 5 |
| **M-14** | Volume tanggapan yang dapat ditangani per tahun | 54 (2025) / 40 per Agustus (2026) | Kapasitas naik tanpa penambahan orang | Perbandingan bersama DPEA | Pasca-MVP |
| M-08 | Draft tanggapan berhasil disusun | 0 | ≥ 3 draft peraturan uji | Output sistem | 4 |
| M-09 | Kesesuaian template tanggapan dengan standar unit | — | Tervalidasi pilot user | Review Unit Bisnis IT | 4 |
| M-10 | Fitur utama lulus UAT | — | 4/4 fitur, ≥ 1 pilot user/fitur | Berita acara UAT | 5 |
| M-11 | Kelengkapan dokumentasi teknis & panduan | 0% | 100% | Checklist review PO | 5 |
| M-12 | Sistem berjalan penuh tanpa AI | — | Lulus *fallback test* | Uji dengan layanan AI dimatikan | 5 |

> **Baseline sudah tersedia (diperbarui 8 Sep 2026).** Pada Weekly Update #1, mitra menyampaikan
> angka nyata proses berjalan — lihat §1A. **M-13 adalah metrik utama proyek ini**; M-04 kini
> menjadi metrik pendukung di dalamnya, bukan klaim yang berdiri sendiri.
>
> Metode verifikasi M-07 juga berubah: mitra melakukan **validasi sampling manual**, bukan
> menyusun *ground truth* menyeluruh. Ini memangkas beban SME secara signifikan dan menutup
> ISU-03 pada [Risk Register](10-risk-register.md).

## 8. Analisis Manfaat

| Aspek | Kondisi Saat Ini | Kondisi Setelah HERO | Manfaat |
| --- | --- | --- | --- |
| Pengumpulan dokumen | Manual, satu per satu, tersebar | Tiga jalur ingest terpusat ke KB terstruktur | Waktu administratif berkurang; dokumen terkonsolidasi |
| Pemahaman dokumen | Baca penuh, manual | Summary + Key Takeaways otomatis | Analis langsung ke inti pengaturan |
| Harmonisasi | Bergantung ingatan individu | Pencocokan rujukan + analisis substansi sistematis | Cakupan deteksi lebih luas, konsisten |
| Penyusunan tanggapan | Bervariasi antar penyusun | Template baku + checklist + narasi PoV | Kualitas seragam, revisi berkurang |
| Akumulasi pengetahuan | Tidak terakumulasi | Knowledge base tertelusur & dapat diulang | Aset jangka panjang DPEA |

## 9. Asumsi dan Kendala Bisnis

**Asumsi**

| ID | Asumsi | Bila Tidak Terpenuhi |
| --- | --- | --- |
| AS-01 | Dokumen sumber berformat PDF dan bersifat publik/legal untuk diproses | Scope ingest berubah; perlu Change Request |
| AS-02 | Infrastruktur (server, storage, komputasi AI) memadai selama pengembangan | Fitur AI-Assisted mundur; mode Deterministik jadi satu-satunya |
| AS-03 | Tersedia SME dari unit terkait untuk validasi tiap akhir fase | M-07 dan M-09 tidak dapat diverifikasi |
| AS-04 | PoV MVP dibatasi 1 profil unit fungsi | Beban Fase 4 bertambah signifikan |
| AS-05 | Mode Deterministik dapat memenuhi seluruh cakupan proses secara mandiri | Ketergantungan AI naik; BRule-02 gugur |

**Kendala**

| ID | Kendala | Mitigasi |
| --- | --- | --- |
| KD-01 | Daftar situs sumber peraturan belum dikonsolidasikan | Workshop konsolidasi di Fase 0; mulai dari 3 situs prioritas |
| KD-02 | Ketersediaan data historis digital untuk pengujian | Gunakan dokumen publik; siapkan dataset uji minimum lebih awal |
| KD-03 | Validasi unit terkait untuk kaidah & gaya bahasa tanggapan | Jadwalkan sesi validasi berkala, bukan hanya di akhir |
| KD-04 | Akses tim di luar sistem DPEA (akses publik) | Rancang sistem tidak bergantung pada integrasi internal DPEA |
| KD-05 | Timeline ± 17 minggu untuk 4 fitur utama | Prioritisasi MVP ketat; scope per sprint dikunci di sprint planning |

## 10. Ketertelusuran

Pemetaan BR → FR → User Story → Use Case → Test Case terdapat pada
[Requirements Traceability Matrix](09-rtm-traceability-matrix.md).

---

## Riwayat Revisi

| Versi | Tanggal | Perubahan | Penyusun |
| --- | --- | --- | --- |
| 1.0 | 7 Sep 2026 | Draft awal dari Project Charter & URD v1.1 | BA |
| 1.1 | 8 Sep 2026 | Tambah §1A baseline nyata (54/40 tanggapan, 2–3 hari → 2–3 jam); tambah BO-07 serta metrik M-13 & M-14; ubah metode verifikasi M-07 menjadi sampling | BA |
