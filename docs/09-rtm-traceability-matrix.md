# REQUIREMENTS TRACEABILITY MATRIX (RTM)
**Proyek:** HERO | **Versi:** 1.1 | **Tanggal:** 8 September 2026 | **Penyusun:** Business Analyst

Matriks ini menjaga agar setiap kebutuhan bisnis terbawa sampai ke pengujian, dan sebaliknya
tidak ada fitur yang dibangun tanpa dasar kebutuhan.

**Rantai ketertelusuran:** Tujuan Bisnis (BO) → Kebutuhan Bisnis (BR) → Kebutuhan Fungsional (FR)
→ Use Case (UC) → User Story (US) → Test Case (TC) → Metrik (M).

---

## 1. Matriks Utama

| BR | Kebutuhan Bisnis | BO | FR | UC | US | TC | Metrik | Fase |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| BR-01 | Tarik PDF dari daftar situs manual | BO-01 | FR-SCR-01, 02, 03 | UC-01, UC-02 | US-12, 13, 14 | TC-01, 02, 03 | M-01 | 1 |
| BR-02 | Unggah dokumen manual | BO-01 | FR-SCR-04 | UC-03 | US-15 | TC-04 | M-02 | 1 |
| BR-03 | Baca folder lokal & OneDrive public | BO-01 | FR-SCR-05, 06 | UC-04 | US-16, 17 | TC-05, 06 | M-02 | 1 |
| BR-04 | Validasi format, ekstraksi metadata & penamaan baku | BO-01, BO-05 | FR-SCR-07, 08, 09, 09a, 09b, 10, 12 | UC-02, UC-05 | US-18, 19, 20, 20a, 21, 23 | TC-07, 08, 09, 10 | M-02 | 1 |
| **BR-25** | Sistem memisahkan draft kajian dari corpus pembanding | BO-03 | FR-SCR-04a | UC-03 | US-15a | TC-04 | M-06 | 1 |
| **BR-26** | Sistem menyimpan PDF asli & blok terstruktur sekaligus | BO-05 | FR-KB-04a | UC-07 | US-26a, US-49a | TC-40a | M-07 | 1–3 |
| **BR-27** | Penelusuran situs mendukung kedalaman yang dapat diatur | BO-01 | FR-SCR-02a, 02b | UC-02 | US-13a | TC-02 | M-01 | 1 |
| **BR-28** | Waktu penyusunan satu tanggapan turun dari 2–3 hari ke 2–3 jam | BO-01..04 | seluruh FR | UC-08, 09, 11 | menyeluruh | **UAT-06** | **M-13** | 5 |
| BR-05 | Klasifikasi & penempatan folder KB | BO-05 | FR-KB-01, 02, 03 | UC-06 | US-24, 25 | TC-13, 14 | M-02 | 1 |
| BR-06 | Ekstraksi struktur bab/pasal/ayat | BO-02, BO-03 | FR-ANL-01 | UC-08 | US-32 | TC-21 | M-03 | 2 |
| BR-07 | Ringkasan isi peraturan | BO-02 | FR-ANL-04, 08 | UC-08 | US-35, 39 | TC-24, 28 | M-03, M-04 | 2 |
| BR-08 | Key Takeaways otomatis | BO-02 | FR-ANL-05, 06 | UC-08 | US-36, 37 | TC-25, 26 | M-03 | 2 |
| BR-09 | Identifikasi status keberlakuan & dasar hukum | BO-03 | FR-ANL-02, 03, FR-KB-09 | UC-07, UC-08 | US-33, 34, 31 | TC-22, 23, 20 | M-03 | 2 |
| BR-10 | Pencocokan rujukan pasal eksplisit | BO-03 | FR-HRM-03 | UC-09 | US-43 | TC-32 | M-06 | 3 |
| BR-11 | Analisis kesesuaian substansi antar pasal | BO-03 | FR-HRM-05 | UC-09 | US-45 | TC-34 | M-06, M-07 | 3 |
| BR-12 | Klasifikasi temuan: menggantikan / memperjelas / pasal baru / duplikasi / konflik | BO-03 | FR-HRM-06, 07, 08, 08a, 08b, 09, 12 | UC-09, UC-10 | US-46, 47, 64 | TC-35, 36, 37, 37a, 38 | M-07 | 3 |
| BR-13 | Ringkasan harmonisasi & rekomendasi awal | BO-03 | FR-HRM-10 | UC-09 | US-48 | TC-39 | M-06 | 3 |
| BR-14 | Template tanggapan baku | BO-04 | FR-POV-02 | UC-12 | US-52 | TC-42 | M-09 | 4 |
| BR-15 | Checklist pasal wajib ditanggapi | BO-04 | FR-POV-03 | UC-11 | US-53 | TC-43 | M-08 | 4 |
| BR-16 | Narasi tanggapan sesuai PoV | BO-04 | FR-POV-01, 04 | UC-11, UC-12 | US-51, 54 | TC-41, 44 | M-08 | 4 |
| BR-17 | Sorot pasal berdampak bagi unit | BO-04 | FR-POV-05 | UC-11 | US-55 | TC-45 | M-08 | 4 |
| BR-18 | Seluruh fitur jalan tanpa AI | BO-06 | FR-SYS-01, 04 | UC-13 | US-06, 59 | TC-52, 53 | M-12 | 2–5 |
| BR-19 | Toggle AI-Assisted | BO-06 | FR-SYS-02, 03 | UC-13 | US-04, 05 | TC-50, 51 | M-05 | 2 |
| BR-20 | UI unggah, cari, sajikan hasil | BO-01..04 | FR-SYS-06, FR-KB-05, 06 | UC-03, UC-07 | US-03, 27, 28 | TC-17, 18, 19 | M-10 | 1–4 |
| BR-21 | Output berstatus draft & tertelusur | BO-05 | FR-SYS-05, 07, 10 | UC-08, UC-15 | US-07, 08, 10 | TC-49, 54, 55 | M-10 | 1–5 |
| BR-22 | OCR untuk PDF hasil pindai | BO-01 | FR-SCR-11 | UC-02 | US-22 | TC-11 | M-02 | 1 |
| BR-23 | Multi-PoV | BO-04 | *(struktur data disiapkan)* FR-POV-07 | UC-12 | US-57 | TC-46 | — | Pasca-MVP |
| BR-24 | Auto-crawling berjadwal | BO-01 | — (Won't MVP) | — | BL-02 | — | — | Pasca-MVP |

---

## 2. Ketertelusuran Kebutuhan Non-Fungsional

| NFR | Kategori | Diuji Melalui | TC | Kriteria Lulus |
| --- | --- | --- | --- | --- |
| NFR-01 | Kinerja summary | Pengukuran timestamp job | TC-28 | < 5 menit/dokumen (mode Deterministik) |
| NFR-02 | Kinerja pencarian | Pengujian responsivitas | TC-18 | < 3 detik pada KB skala MVP |
| NFR-03 | Kapasitas KB | Pengujian volume | TC-19 | ≥ 100 dokumen tanpa degradasi berarti |
| NFR-04 | Keandalan tanpa AI | *Fallback test* seluruh fitur | TC-53 | Semua fitur selesai tanpa kegagalan |
| NFR-05 | Ketahanan batch | Uji dokumen rusak dalam batch | TC-12 | Job lain tetap selesai |
| NFR-06 | Autentikasi | Uji akses tanpa login | TC-56 | Seluruh fitur menolak akses anonim |
| NFR-07 | Otorisasi peran | Uji akses lintas peran | TC-57 | Akses di luar peran ditolak |
| NFR-08 | Kepatuhan NDA | Telaah aliran data ke layanan eksternal | TC-58 | Tidak ada pengiriman data non-publik tanpa persetujuan tertulis |
| NFR-10 | Auditabilitas | Telaah audit log | TC-54 | Seluruh aksi relevan tercatat |
| NFR-11 | Ketertelusuran hasil | Uji rujukan pasal pada tiap butir output | TC-26 | 100% butir memiliki rujukan yang dapat dibuka |
| NFR-12 | Usability | Observasi pengguna saat UAT | TC-59 | Alur utama selesai dengan panduan singkat |
| NFR-15 | Maintainability konfigurasi | Uji perubahan aturan tanpa ubah kode | TC-15 | Aturan klasifikasi/PoV/checklist dapat diubah lewat konfigurasi |
| NFR-18 | Dokumentasi | Review kelengkapan | TC-60 | Dokumentasi teknis & panduan pengguna 100% |

---

## 3. Cakupan Terbalik — FR Tanpa Test Case

Pemeriksaan agar tidak ada kebutuhan yang lolos dari pengujian.

| FR | Status Cakupan | Catatan |
| --- | --- | --- |
| FR-SCR-08 (deteksi duplikat) | Tercakup | TC-09 |
| FR-KB-07 (versioning dokumen) | Tercakup | TC-16 |
| FR-KB-08 (kelola dokumen) | Tercakup | TC-15 |
| FR-ANL-07 (identifikasi topik) | Tercakup | TC-27 |
| FR-ANL-09 / FR-HRM-13 / FR-POV-08 (ekspor) | Tercakup | TC-29, TC-40, TC-48 |
| FR-HRM-02 (pemilihan kandidat) | Tercakup | TC-31 |
| FR-HRM-04 (status peraturan dirujuk) | Tercakup | TC-33 |
| FR-HRM-11 (penandaan temuan) | Tercakup | TC-38 |
| FR-POV-06 (penyuntingan draft) | Tercakup | TC-47 |
| FR-SYS-09 (status pekerjaan) | Tercakup | TC-55 |

**Kesimpulan:** seluruh FR berprioritas *Must* dan *Should* memiliki minimal satu test case.
Tidak ditemukan FR yatim (tanpa pengujian) maupun test case tanpa dasar kebutuhan.

---

## 4. Ketertelusuran Metrik → Bukti UAT

| Metrik | Target | Sumber Bukti | Penanggung Jawab Verifikasi |
| --- | --- | --- | --- |
| M-01 | ≥ 3 situs | Log job scraping | QA |
| M-02 | ≥ 20 dokumen di KB | Query knowledge base | QA |
| M-03 | ≥ 10 dokumen bersummary | Laporan hasil analisa | QA |
| M-04 | < 5 menit/dokumen | Timestamp EKSEKUSI_ANALISA | QA |
| M-05 | Toggle berfungsi & narasi lebih natural | Uji fungsional + penilaian pilot user | QA + Pilot User |
| M-06 | ≥ 5 pasang dokumen | Laporan harmonisasi | QA |
| M-07 | Recall ≥ 70% | Validasi sampling 2–3 dari 10 dokumen oleh Faris & Andika | BA + Validator DPEA |
| M-08 | ≥ 3 draft tanggapan | Output sistem | QA |
| M-09 | Template tervalidasi | Review Unit Bisnis IT | Pilot User |
| M-10 | 4 fitur lulus UAT | Berita acara UAT | PO |
| M-11 | Dokumentasi 100% | Checklist review | PO |
| M-12 | Lulus fallback test | Laporan TC-53 | QA |
| **M-13** | **2–3 jam per tanggapan** | **UAT-06** — pengukuran hulu-hilir bersama DPEA | PM + PO |

> **Metode verifikasi M-07 berubah (8 Sep 2026).** Mitra menetapkan **validasi sampling manual**:
> dari 10 dokumen yang di-*run*, diambil 2–3 sampel, lalu diperiksa apakah kutipan pasalnya benar
> (KEP-08). Penyusunan *ground truth* menyeluruh tidak lagi diperlukan.
>
> **Konsekuensi bagi produk:** setiap butir keluaran wajib menyertakan **kutipan pasal apa adanya
> beserta tautan ke PDF asli**. Tanpa keduanya, metode validasi mitra tidak dapat dijalankan sama
> sekali — sehingga M-07 tetap tidak terverifikasi meski fiturnya berfungsi.

---

## Riwayat Revisi

| Versi | Tanggal | Perubahan | Penyusun |
| --- | --- | --- | --- |
| 1.0 | 7 Sep 2026 | Draft awal: 24 BR tertelusur, cakupan NFR, pemeriksaan cakupan terbalik | BA |
| 1.1 | 8 Sep 2026 | Tambah BR-25..BR-28 & M-13; klasifikasi harmonisasi diperbarui; metode verifikasi M-07 menjadi sampling | BA |
