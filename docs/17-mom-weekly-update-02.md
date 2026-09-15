# MoM — Weekly Update #2 (Minggu 1 Fase 1)

**Tanggal:** Senin, 15 September 2026, 14.19 WIB · ± 32 menit · Zoom
**Hadir DPEA:** Pak Faris Budi (Product Owner + Agile Coach), Pak Andika Prihandoko (Mentor)
**Hadir Tim:** Zaky (PM/BA), Rafli (Backend), Ikhwan (Frontend), Hamdan (Infra/QA), Fathir (Data/ML — menyusul)
**Notulis:** Zaky

---

## 1. Ringkasan singkat

- Minggu pertama Fase 1 (14 Sep – 11 Okt). Semua peran sudah punya progres yang bisa ditunjukkan.
- Mitra puas — Pak Andika bilang kelompok ini "jauh lebih baik dari capstone sebelumnya".
- NDA lengkap 5 orang. Minggu depan mitra mulai taruh dokumen di OneDrive.
- Tiga hal yang harus berubah mulai minggu depan: (1) format laporan PM, (2) mekanisme screening sebelum download di scraper, (3) target tanggal desain Figma.

---

## 2. Laporan progres per orang

### Rafli — Backend
- Sudah ada endpoint login (GET/POST) dan audit log saat login.
- Sudah ada tabel Jobs — status PDF saat masuk / diterima backend.
- Sudah ada tabel Dokumen dengan ID per dokumen, dan status dokumen (dicabut / diupdate / direvisi).
- Sudah ada tabel Articles (pasal).
- Repo sudah di org hero-ojk-its.
- Saat ini scraper langsung download semua begitu di-run — belum ada tahap screening.

### Ikhwan — Frontend
- Mockup Figma sudah 4 halaman: Dashboard, Knowledge Base, Ingest Dokumen, Analisa Regulasi.
- Dashboard: jumlah regulasi, total dokumen masuk, diproses, perlu diharmonisasi, sudah diharmonisasi.
- Knowledge Base: pencarian kata kunci, filter kategori / status / sumber / tahun.
- Ingest: 3 tab — upload PDF manual (dengan pilihan kategori), scraping URL (input link + progress bar), OneDrive.
- Analisa Regulasi: pilih dokumen → struktur pasal → ringkasan. Masih belum yakin sudah mencakup semua.
- Belum ada: Harmonisasi dan Draft Tanggapan (2 halaman).
- Bilang mockup semua bisa ready minggu depan.

### Zaky — PM / BA
- Dokumen sudah ada: use case, product backlog, sprint plan, risk register, papan proyek (tracker Fase 0–1, milestone, referensi, dashboard).
- Belum konfirmasi ke dosen: laporan dalam bentuk Excel atau GitHub Project.

### Fathir — Data/ML
- Scraping sudah jalan. Dibuat UI kecil sendiri untuk mempermudah demo — nanti diintegrasikan ke frontend Ikhwan.
- OCR belum masuk ke alur scraping, tapi sudah dicoba: 41 dokumen dari JDIH, 1 dari ojk.go.id.
- Dedup sudah: yang disimpan adalah yang pertama kali di-scan.
- Struktur knowledge base: Source → Sektor → Jenis/Kategori → Tahun → Status (berlaku/dicabut).
- OneDrive belum dieksplor — belum ada datanya.
- Penyimpanan sekarang PDF; rencana diubah ke bentuk tabular setelah OCR.
- Laptop: MacBook Pro M4, 24 GB — Pak Faris bilang cukup untuk lab sementara.

### Hamdan — Infra/QA
- Coba Vercel (rekomendasi OJK) → Pro trial cuma 14 hari.
- Beralih ke GitHub Pages, auto-deploy. Masih berupa mockup, belum terhubung ke BE/FE.
- Belum cek limit traffic free tier.

---

## 3. Feedback dari mitra — per orang

### Untuk Zaky (PM)

**Dari Pak Andika:**
- Minta satu slide rekap per pertemuan: apa yang dikerjakan tiap orang, apa yang pending, status selesai/belum, persentase milestone. Supaya PM bisa lihat keseluruhan dan mitra bisa cek status tiap minggu.
- Kalau ada kendala, sampaikan di awal. "Kami lebih senang tahu kendala di awal daripada update bagus di depan tapi kendala baru muncul di belakang."

**Dari Pak Faris:**
- Mulai minggu depan, setiap sesi dibuka oleh PM dengan summary 2–3 halaman berisi:
  1. Backlog Fase 0 — apa yang sudah selesai, apa yang carry-over ke Fase 1
  2. Posisi minggu ini
  3. Tiga minggu ke depan mau kerjain apa
- Alasan: mitra perlu hitung kapan harus kasih approval — minggu ke berapa September / Oktober.
- Bentuk bebas — Kanban, Excel, GitHub — yang paling nyaman dipakai.
- Ada 3 pertemuan lagi sebelum 11 Oktober (Pak Andika koreksi: 3, bukan 4).
- Mitra akan bantu review desain, tapi masukan disalurkan lewat PM.

### Untuk Rafli (Backend)

**Dari Pak Faris:**
- Tambahkan mekanisme screening sebelum download. Sekarang scraper langsung tarik semua begitu di-run.
- Cara kerjanya: scan URL dulu tanpa download → hitung ada berapa PDF → cek duplikat (ukuran / nama / hash) → baru tarik yang benar-benar beda.
- Alasan: satu file yang sama bisa ada di banyak URL. Kalau scan 1000 dan 500 sama, cukup tarik 500 — hemat bandwidth.
- Masukkan ini ke mekanisme scraping sebelum diterjemahkan Fathir ke pembacaan dokumen.
- Jawaban soal prioritas sumber: peraturan internal ± 500 (folder) + scraping 3 URL ± 1000 = ± 2000 dokumen ke knowledge base — ini yang utama. Upload manual bukan pengisi KB.

### Untuk Ikhwan (Frontend)

**Dari Pak Faris:**
- Prinsip: desain harus selesai semua di awal — mockup dan flow lengkap — baru di-develop belakangan.
- Prinsip: aplikasi harus bisa dipahami tanpa manual dan tanpa sosialisasi, seperti sosmed. Model/menu bebas, tidak diatur.
- Upload manual sifatnya beda dari 2 jalur lain: itu dokumen yang langsung mau ditanggapi, bisa ditaruh di bawah fitur Analisa, bukan di Ingest.
- Untuk scraping dan folder, yang ditunggu mitra adalah progress bar / animasi yang jelas: proses lagi jalan, lagi di tahap apa, atau stuck.
- Deadline disepakati: 21 September share link Figma → 22 September mitra kasih feedback. Kalau ada revisi, waktunya seminggu.

**Dari Pak Andika:**
- Struktur halaman Analisa Regulasi sudah kelihatan, bagus.

### Untuk Fathir (Data/ML)

**Dari Pak Faris:**
- Dokumen sama di banyak sumber — yang disimpan yang mana? Fathir jawab: yang pertama di-scan. Pak Faris OK.
- Folder per sumber URL atau per tipe dokumen? Pak Faris cenderung per tipe (UU, PP, POJK, SE) karena peraturan punya hierarki. Fathir jelaskan strukturnya: Source → Sektor → Jenis → Tahun → Status. Pak Faris OK, "diskusi saja".
- Pengalaman DPEA soal penyimpanan: dulu simpan PDF dan harus OCR dulu (ada yang protected / hasil scan). Begitu ribuan dokumen, proses melambat karena tiap kali harus buka satu per satu. Solusinya konversi ke vektor — retrieval jauh lebih cepat. Tapi jadi susah saat surat resmi harus melampirkan PDF asli peraturan.
- Minta tim explore dan usulkan cara menjawab dua kebutuhan itu sekaligus.
- Fathir tanya prioritasnya mana. Pak Faris: tahap awal vektor dulu, tapi pastikan yang dikutip memang ada dokumennya — jangan fabrikasi seperti LLM. Fitur simpan lokal tetap dibuat.
- Untuk Fase 1: yang penting jadi dulu. PDF juga boleh sesuai desain tim. Perbandingan kecepatan PDF vs vektor bisa diuji di akhir.
- Fathir usul: simpan PDF asli hanya untuk yang sering dipakai. Pak Faris: bisa.
- Kalau butuh langganan cloud, masukkan ke pengajuan dana.

**Dari Pak Andika:**
- Bikin UI kecil untuk mempermudah penjelasan scraping — itu improvement, yang lain bisa ikuti.

### Untuk Hamdan (Infra/QA)

**Dari Pak Faris:**
- Pengalaman capstone sebelumnya pakai Vercel: limit ± 50 request/hari, dibagi antara tim develop dan mitra menguji → timeline mundur karena harus gantian.
- Minta explore limit free tier GitHub Pages: ada meteran traffic? Cukup untuk MVP dipakai develop dan diuji bersamaan?
- Selama belum berbayar, harus tetap bisa dipakai — pengajuan anggaran butuh proposal dan turunnya lama.

---

## 4. Keputusan

1. Format laporan mingguan berubah: PM buka sesi dengan summary 2–3 halaman (carry-over, posisi sekarang, 3 minggu ke depan).
2. Scraper wajib punya tahap screening sebelum download.
3. Upload manual = jalur dokumen yang langsung ditanggapi, bukan pengisi knowledge base. Di UI ditaruh di bawah Analisa.
4. Deadline desain: 21 Sep share Figma, 22 Sep feedback mitra.
5. Penyimpanan Fase 1: PDF boleh dulu. Vektor dieksplor untuk fase berikutnya. Yang dikutip harus bisa dibuktikan ada dokumennya.
6. NDA lengkap 5 orang. Minggu depan mitra mulai isi folder OneDrive.
7. Bikin grup komunikasi. Zaky bikin grup WhatsApp.

---

## 5. Action item

### Zaky
- [ ] Bikin grup WhatsApp, undang Pak Faris dan Pak Andika — hari ini
- [ ] Siapkan summary 2–3 halaman format Pak Faris untuk sesi minggu depan (22 Sep)
- [ ] Siapkan satu slide rekap per orang (permintaan Pak Andika)
- [ ] Konfirmasi ke dosen: format laporan Excel atau GitHub Project
- [ ] Teruskan link Figma Ikhwan ke mitra — 21 Sep

### Rafli
- [ ] Tambahkan mekanisme screening sebelum download: scan → hitung → cek duplikat → tarik yang beda
- [ ] Koordinasi dengan Fathir supaya screening ada sebelum tahap pembacaan dokumen

### Ikhwan
- [ ] Selesaikan 2 halaman tersisa: Harmonisasi, Draft Tanggapan — target semua ready minggu depan
- [ ] Pindahkan upload manual ke bawah fitur Analisa
- [ ] Progress bar / indikator proses di scraping dan folder harus jelas: lagi jalan / tahap apa / stuck
- [ ] Share link Figma ke Zaky — paling lambat 21 Sep

### Fathir
- [ ] Explore dan usulkan: cara simpan yang retrieval-nya cepat (vektor) tapi PDF asli tetap bisa dilampirkan
- [ ] Untuk Fase 1: lanjutkan PDF dulu, yang penting jadi
- [ ] Integrasikan UI demo ke frontend Ikhwan
- [ ] Mulai baca folder OneDrive begitu mitra isi minggu depan — atau download ke lokal dulu kalau belum bisa langsung

### Hamdan
- [ ] Cek limit free tier GitHub Pages: traffic, request per hari, cukup untuk develop + pengujian bersamaan?
- [ ] Laporkan hasilnya minggu depan

### Mitra (Pak Faris)
- [ ] Mulai taruh dokumen peraturan internal di folder OneDrive — minggu depan
- [ ] Feedback desain Figma — 22 Sep

---

## 6. Catatan dari sisi PM

- Angka penting yang baru muncul: **peraturan internal ± 500, scraping ± 1000, total ± 2000 dokumen** target knowledge base. Sebelumnya indikator Fase 1 cuma "minimal 20". Angka 20 tetap jadi ambang lulus, tapi 2000 itu ukuran sebenarnya.
- Klarifikasi penting yang menguatkan dokumen kita: upload manual memang bukan pengisi KB (sudah ada di ADR-03 dan US-15a). Ikhwan perlu tahu ini karena mockup Ingest-nya masih menaruh upload manual sejajar dengan scraping.
- Soal penyimpanan: yang Pak Faris minta itu persis ADR-01 (PDF asli + blok terstruktur berdampingan). Fathir belum baca dokumennya — tunjukkan.
- Hamdan sudah pindah ke GitHub Pages tanpa lewat keputusan tim. Itu cuma bisa hosting frontend statis, sama seperti Vercel. Backend, DB, OCR tetap butuh server. ADR-11 masih relevan — bahas di checkpoint internal.
- Pak Andika koreksi sisa pertemuan: 3 kali, bukan 4 — 22 Sep, 29 Sep, 6 Okt. Uji coba mitra 8 Okt jatuh setelah pertemuan terakhir.
