# PROJECT CHARTER
## HERO — Harmonisasi & Analisa Regulasi Otomatis

| Atribut | Keterangan |
| --- | --- |
| **Nama Proyek** | HERO (Harmonisasi & Analisa Regulasi Otomatis) |
| **Mitra Perusahaan** | Otoritas Jasa Keuangan (OJK) |
| **Unit Pemilik Proses** | Departemen Pengembangan Aplikasi (DPEA) |
| **Mentor Industri** | Andika Wahyu Prihandoko |
| **Mata Kuliah** | Capstone Project — Departemen Teknik Informatika, ITS |
| **Semester** | Gasal 2026/2027 |
| **Versi Dokumen** | 1.0 (Draft) |
| **Tanggal** | 7 September 2026 |
| **Metode Delivery** | Agile, pendekatan MVP, sprint 2 mingguan |
| **Periode** | 31 Agustus 2026 – 24 Desember 2026 (± 17 minggu) |

---

## A. Gambaran Umum Proyek

### A.1 Masalah atau Isu

Proses analisa regulasi di lingkungan regulator/otoritas saat ini masih banyak dilakukan
secara manual, mulai dari pengumpulan dokumen peraturan, pembacaan dan pemahaman isi
peraturan, pengecekan keselarasan (harmonisasi) draft peraturan baru terhadap peraturan yang
sudah berlaku, hingga penyusunan tanggapan atas draft peraturan dari sudut pandang unit
tertentu.

### A.2 Tujuan Proyek

1. Mengumpulkan dokumen peraturan yang telah dipublikasikan secara lebih cepat dan terstruktur.
2. Melakukan analisa, ringkasan (*summary*), dan penyusunan *Key Takeaways*.
3. Melakukan pengecekan harmonisasi antara draft peraturan baru dengan peraturan eksisting.
4. Menyusun draft tanggapan atas draft peraturan baru berdasarkan sudut pandang (*Point of
   View*/PoV) unit fungsi tertentu.

### A.3 Studi Kasus Bisnis

Proses bisnis Departemen Pengembangan Aplikasi (DPEA) dalam menjalankan analisa ketentuan dan
kebijakan dalam rangka penyelarasan dengan pengembangan aplikasi.

### A.4 Tujuan / Metrik

Proyek dapat di-*deliver* sesuai indikator keberhasilan dan *timeline* per fase sebagaimana
dirinci pada [WBS & Sprint Plan](07-wbs-sprint-plan.md) §5 dan
[BRD](02-brd-business-requirements.md) §7.

### A.5 Hasil yang Diharapkan (Deliverable)

| No. | Deliverable | Tingkat Kesulitan (1–5) | Fase Target |
| --- | --- | --- | --- |
| D-01 | Modul Scraping & Ingest Dokumen | 3 | Fase 1 |
| D-02 | Knowledge Base Peraturan Terstruktur | 4 | Fase 1 |
| D-03 | Modul Analisa, Summary & Key Takeaways | 4 | Fase 2 |
| D-04 | Modul Harmonisasi Draft vs Eksisting | 4 | Fase 3 |
| D-05 | Modul Draft Tanggapan Berbasis PoV | 5 | Fase 4 |
| D-06 | Dokumentasi & Hasil UAT | 2 | Fase 5 |

### A.6 Batasan

1. Semua peserta proyek diharuskan mengisi **Non-Disclosure Agreement (NDA)** sesuai format
   yang disepakati.
2. Selama proyek berlangsung, peserta melakukan akses sistem **di luar sistem DPEA** (akses
   publik).
3. Peserta proyek wajib menjaga kerahasiaan semua data yang berhubungan dengan pelaksanaan
   proyek dan dilarang mendistribusikan data yang berhubungan dengan DPEA tanpa izin tertulis
   dari DPEA.

---

## B. Ruang Lingkup Proyek

### B.1 Dalam Lingkup (In-Scope)

1. Pengumpulan dokumen peraturan berformat PDF melalui tiga jalur: (1) *scraping* dari daftar
   situs yang diinput manual, (2) unggah manual oleh pengguna, dan (3) pembacaan dokumen dari
   folder lokal atau folder OneDrive *public* yang dikonfigurasi.
2. Analisa, *summary*, dan penyusunan *Key Takeaways* untuk dokumen peraturan yang sudah
   tersedia di sistem.
3. Harmonisasi draft peraturan baru terhadap peraturan eksisting di *knowledge base*.
4. Penyusunan draft tanggapan berdasarkan minimal 1 (satu) profil PoV unit fungsi pada tahap
   MVP (misal: PoV Unit Bisnis IT).
5. Penyimpanan dan pengelolaan dokumen peraturan dalam *knowledge base* terstruktur.
6. Mode pemrosesan **Deterministik** (default, wajib tersedia di seluruh fitur) dan
   **AI-Assisted** (opsional, dapat diaktifkan/nonaktifkan pengguna).
7. Antarmuka pengguna (UI) dasar untuk unggah dokumen, pencarian, dan penyajian hasil.

### B.2 Luar Lingkup (Out-of-Scope)

1. *Scraping* otomatis berjadwal (*auto-crawling*) tanpa input manual daftar situs.
2. Keputusan final atas hasil harmonisasi maupun tanggapan — tetap kewenangan Pengawas/unit
   terkait.
3. Integrasi langsung (*real-time*) dengan sistem/basis data peraturan resmi instansi lain
   (misal JDIH nasional).
4. Dukungan multi-PoV/multi-unit fungsi secara penuh pada tahap MVP.
5. Pemrosesan dokumen non-PDF (Word, Excel, video) pada fitur *scraping*.

---

## C. Rancangan Jadwal

| Item | Keterangan |
| --- | --- |
| **Tanggal Mulai** | 31 Agustus 2026 |
| **Tanggal Selesai** | 24 Desember 2026 |
| **Laporan Progress** | Setiap 1 atau 2 minggu sekali sesuai perjanjian |
| **Pelaksanaan** | Online |
| **Siklus Sprint** | 2 mingguan (± 8 sprint) |

Rincian fase: lihat [WBS & Sprint Plan](07-wbs-sprint-plan.md).

---

## D. Pembagian Tim dan Role

| Peran | Tugas | PIC |
| --- | --- | --- |
| **Project Manager / Business Analyst** | Perencanaan & pengendalian proyek, penggalian kebutuhan, pemetaan proses, dokumentasi, komunikasi klien | *(diisi)* |
| **Backend** | API, basis data, logika bisnis, integrasi | *(diisi)* |
| **Frontend / UX** | Antarmuka, alur pengguna, purwarupa | *(diisi)* |
| **Data / ML** | Pipeline data, analitik, permodelan NLP/LLM | *(diisi)* |
| **Infra / QA** | Deployment, CI, pengujian, keamanan dasar | *(diisi)* |

Matriks tanggung jawab terperinci: lihat [RACI](01-stakeholder-register-raci.md) §3.

---

## E. Fasilitas

| Jenis | Keterangan | Status |
| --- | --- | --- |
| Tools Project Management | Menggunakan tools kampus | Perlu konfirmasi tool spesifik |
| Repository | Menggunakan mitra & kampus | Perlu penyiapan akses |
| Dataset | Harus dikumpulkan | **Blocker Sprint 1** |
| Tech Stack | Belum ditentukan | **Blocker keputusan arsitektur** |
| Infrastruktur (server, storage, komputasi AI) | Diasumsikan tersedia | Perlu konfirmasi kapasitas & biaya |

---

## F. Manfaat dan Pengguna

| Item | Keterangan |
| --- | --- |
| **Target Pengguna** | DPEA sebagai *business owner*, unit bisnis lain sebagai *user* |
| **Pilot PoV (MVP)** | Unit Bisnis IT |
| **Manfaat** | HERO berperan sebagai asisten analisa dalam penyelesaian tugas DPEA |

---

## G. Risiko, Kendala, dan Asumsi

Ringkasan; register lengkap ada di [Risk Register](10-risk-register.md).

**Risiko utama:** akurasi mode AI-Assisted, variasi format dokumen sumber (PDF hasil scan),
kendala akses folder lokal/OneDrive, dan *timeline* yang relatif ketat (± 17 minggu untuk 4
fitur utama).

**Kendala utama:** konsolidasi daftar situs sumber, ketersediaan data historis untuk pengujian,
dan kebutuhan validasi dari unit terkait.

**Asumsi utama:** dokumen sumber berformat PDF & bersifat publik/legal untuk diproses;
infrastruktur memadai; tersedia SME untuk validasi tiap akhir fase; PoV MVP dibatasi 1 profil;
mode Deterministik mandiri tanpa AI.

---

## H. Kriteria Keberhasilan Proyek

Proyek dinyatakan **berhasil** apabila seluruh kondisi berikut terpenuhi pada 24 Desember 2026:

| Kode | Kriteria | Cara Verifikasi |
| --- | --- | --- |
| CSF-01 | Keempat fitur utama (3.2–3.5) lulus UAT dengan minimal 1 pilot user per fitur | Berita acara UAT |
| CSF-02 | Sistem berjalan penuh pada mode Deterministik tanpa layanan AI aktif | *Fallback test* terdokumentasi |
| CSF-03 | Minimal 20 dokumen peraturan tersimpan di knowledge base terstruktur | Query knowledge base |
| CSF-04 | Minimal 70% potensi konflik/duplikasi pada dokumen uji terdeteksi | Validasi manual SME |
| CSF-05 | Dokumentasi teknis & panduan pengguna selesai 100% | Review PO |
| CSF-06 | Tidak ada pelanggaran NDA / kebocoran data DPEA | Audit internal tim |

---

## I. Persetujuan

| Peran | Nama | Tanda Tangan | Tanggal |
| --- | --- | --- | --- |
| Mentor Industri | Andika Wahyu Prihandoko | | |
| Product Owner (DPEA) | *(diisi)* | | |
| Dosen Pembimbing | *(diisi)* | | |
| Project Manager | *(diisi)* | | |

---

## Riwayat Revisi

| Versi | Tanggal | Perubahan | Penyusun |
| --- | --- | --- | --- |
| 1.0 | 7 Sep 2026 | Draft awal, penataan ulang charter mitra + penambahan §H Kriteria Keberhasilan | PM/BA |
