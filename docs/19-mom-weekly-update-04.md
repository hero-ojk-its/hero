# MoM — Weekly Update #4 (Minggu 3 Fase 1)

**Tanggal:** Selasa, 29 September 2026 · ± 46 menit · Zoom
**Hadir DPEA:** Pak Faris Budi (Product Owner + Agile Coach), Pak Andika Prihandoko (Mentor — bergabung di akhir)
**Hadir Tim:** Zaky (PM/BA), Ikhwan (Frontend), Rafli (Backend), Hamdan (Infra/QA)
**Berhalangan:** Fathir (Data/ML) — progres disampaikan Zaky
**Notulis:** Zaky
**Rekaman:** https://youtu.be/Ht6GgmVjPdA

---

## 1. Ringkasan singkat

- Minggu ketiga Fase 1, awal Sprint 3. Tim mulai mencicil task Sprint 3; sebagian task Sprint 2 masih finalisasi dan *in review*.
- **Pengujian MVP Fase 1 harus mulai pekan ini.** MVP dirilis 11 Okt. Pak Faris memberi aturan untuk setiap MVP: pengujian mulai H-14, batas perbaikan H-7.
- **Kriteria penerimaan scraping ditetapkan:** dokumen dianggap berhasil kalau sudah terindeks saat scan (URL, nama dokumen, nama berkas, ukuran), tanpa harus diunduh. Jumlahnya dibandingkan dengan *ground truth* DPEA: ± 1.700 dokumen di situs regulasi OJK dan ± 400–500 di JDIH.
- **Tiga sumber uji MVP:** situs regulasi OJK, JDIH OJK, dan folder OneDrive public.
- **Format nama berkas dibuat dinamis.** Di halaman Scraping ada tombol Nama / Tahun / Jenis / Bidang. Urutan klik menentukan format nama berkas.
- **Halaman detail peraturan menampilkan isi dokumen**, supaya hasil analisa bisa dicek langsung ke dokumen aslinya.
- Project Charter sudah ditandatangani. PRD masih menunggu tanda tangan Pak Andika.
- Dokumen sprint review diselesaikan pekan ini dan tidak perlu tanda tangan mentor.

---

## 2. Laporan progres per orang

### Zaky — PM / BA
- Papan GitHub Project (template kampus) sudah dipakai: backlog, board, current iteration, roadmap, dan item per peran. Sprint 1 selesai; sebagian Sprint 2 masih *in progress* dan *in review*, beberapa belum diperbarui statusnya di papan.
- Project Charter sudah ditandatangani. PRD sudah dikirim ke grup, masih direview dan belum ditandatangani Pak Andika. Tanda tangan dibutuhkan untuk administrasi kampus.
- Figma masih diperbarui, feedback sudah mulai bolak-balik.
- Pencarian dokumen sudah *in progress*. Contoh surat tanggapan tertulis masih ditunggu dari Pak Faris. Folder OneDrive sudah bisa diakses.

### Fathir — Data/ML *(disampaikan Zaky)*
- Mulai mengerjakan metadata dasar, OCR halaman pertama, dan penamaan berkas baku (US-20, US-20a).
- Rencana memakai model Claude untuk bagian ini.

### Ikhwan — Frontend
- **Dashboard:** redundansi yang dicatat Pak Faris diakui dan akan direvisi. Usulan Ikhwan: angka kategori (misalnya "Penerbangan 42") bisa diklik dan langsung membuka Knowledge Base yang sudah terfilter ke kategori itu.
- **Knowledge Base:** mockup selesai.
- **Ingest dokumen:** mockup selesai. Hasil scraping sudah bisa dipilih sesuai feedback minggu lalu. Halaman OneDrive serupa, hanya sumbernya OneDrive.
- **Analisa Regulasi:** baru tampilan Deterministik. Tampilan AI dan Custom belum dibuat karena arahnya belum jelas.
- **Harmonisasi:** unggah draft → pilih dokumen pembanding → proses → hasil per pasal. Setiap pasal bisa diklik untuk melihat statusnya (konflik, duplikasi, atau selaras), lalu hasil harmonisasi disimpan.
- **Slicing:** sudah mulai untuk halaman yang sudah fix (dijalankan di lokal). Dashboard belum memuat feedback Pak Faris. Knowledge Base sudah punya filter kategori, jenis, tahun, dan topik.
- **Pertanyaan:** kalau judul peraturan di Knowledge Base diklik, apakah cukup menampilkan detail informasi, atau juga membuka PDF aslinya?

### Rafli — Backend
- Menindaklanjuti MoM #3:
  - Login dikunci sementara.
  - Pencarian frasa multi-kata sudah diperbaiki.
  - Penamaan baku sudah jalan: berkas disimpan dengan format `nomor judul tahun`.
- Unggah dokumen yang sebelumnya lewat Swagger sekarang sudah memakai dialog *choose file*. Dialog masih menerima TXT maupun PDF, tetapi sistem hanya membaca PDF.
- Scraping: dokumen duplikat atau berjudul sama otomatis di-*skip* (sudah diuji ulang).
- Scan sudah membaca nama berkas, ukuran, dan jumlah halaman.
- Sumber yang didukung saat ini: folder OneDrive dan link. Link yang diuji semalam masih link ke satu dokumen, belum ke kumpulan dokumen. Paging belum dicek.
- Sebagian besar pekerjaan minggu ini berupa revisi dari masukan Sprint 2.

### Hamdan — Infra/QA
- Minta maaf karena absen minggu lalu (listrik padam satu desa).
- QA: menelaah berapa pengguna yang bisa dilayani. Jumlahnya bergantung pada ukuran aplikasi dan berkas yang diunggah; makin besar ukurannya, makin sedikit pengguna maksimalnya.
- Mulai mencari dokumen untuk pengujian internal, begitu frontend dan backend siap, sebelum diuji mitra.
- Menjawab Pak Faris soal hosting: layanan gratis yang dipakai tidak punya limit harian. Batasnya ada pada ukuran berkas (per MB), jadi makin banyak dokumen hasil scraping, kapasitasnya makin berkurang.

---

## 3. Feedback dari mitra — per orang

### Untuk Ikhwan (Frontend)

**Dari Pak Faris — Detail peraturan:**
- Mockup pertama sudah punya halaman detail peraturan satu layar penuh yang berisi isi dokumennya, seperti membaca PDF. Pakai bentuk itu.
- Alasannya adalah verifikasi. Misalnya sistem menyimpulkan "Pasal 27 dokumen yang baru diunggah bertentangan dengan Pasal 23 undang-undang tahun '97". Pengguna harus bisa mengklik dan memastikan ringkasan sistem memang sesuai dokumen aslinya, bukan halusinasi.
- PDF sebaiknya bisa langsung dilihat di browser (*view only*) kalau tidak memberatkan. Kalau rumit, untuk tahap pertama cukup unduh ke lokal. Konsekuensinya, uji manual harus mengunduh dulu.
- Tata letaknya diserahkan ke Ikhwan: kembali ke frame lama atau versi yang lebih detail.

**Dari Pak Faris — Format nama berkas di halaman Scraping:**
- Belum ada di mockup. Di halaman Scraping perlu ada pilihan format nama untuk berkas yang ditarik.
- Bentuknya: ada tombol **Nama, Tahun, Jenis, Bidang**, dan sebuah kotak format di atasnya. Setiap tombol yang diklik ditambahkan ke format secara berurutan (misalnya Nama → Jenis → Tahun). Tombol yang sama boleh diklik lagi, dan ada tombol *clear*.
- Alasannya, cara orang mengelompokkan dokumen berbeda-beda. Ada yang berdasarkan nama atau jenis peraturan, ada yang berdasarkan tahun (Pak Faris sendiri biasanya per tahun). Di dalam sistem dokumen bisa difilter dan diurutkan, tetapi di folder lokal urutannya mengikuti nama berkas.
- Logika penamaan yang sudah dibuat Rafli disambungkan ke UI ini.

**Dari Pak Faris — Prioritas dan cara update:**
- Kejar Sprint 2 dan 3 dulu. Analisa baru berat nanti di belakang.
- Mockup tidak wajib direvisi dulu. Update boleh langsung di aplikasi selama sprint dan MVP-nya masih terbuka. Setelah MVP dirilis, tidak diutak-atik lagi; perubahan masuk ke sprint berikutnya.

### Untuk Rafli (Backend)

**Dari Pak Faris — Penamaan berkas:**
- OJK tidak punya format baku untuk nama berkas; format bakunya hanya ada di isi dokumen. Karena itu penamaannya dibuat dinamis: algoritma me-*rename* otomatis mengikuti urutan komponen yang dipilih pengguna.

**Dari Pak Faris — Scraper harus tahan terhadap variasi situs:**
- Ada tiga tipe situs:
  1. URL sumber sama dengan lokasi PDF.
  2. URL target membuka alamat lain (*redirect*).
  3. Harus melewati captcha sebelum bisa masuk atau mengunduh.
- Paging juga punya beberapa format, misalnya `1 2 3 … terakhir` dan `1 2 … 7 8 terakhir`. Posisi scraper sekarang perlu jelas: generik atau disesuaikan per situs.
- Tiga sumber uji MVP:
  - **Situs regulasi OJK** (`ojk.go.id/id/regulasi/…`) berbasis SharePoint. Dengan Selenium, paging bisa dibaca. Estimasi ± 1.700 dokumen.
  - **JDIH OJK**: cari halaman peraturannya (ada kategori perbankan dan seterusnya). Estimasi ± 400–500 dokumen.
  - **OneDrive public.**
- Untuk menguji ketangguhan algoritma, Rafli boleh mencoba situs apa pun. Cukup sampai scan, tidak perlu unduh.
- **Pendekatan:** menurut pengalaman Pak Faris, Gemini lebih pintar untuk crawling lintas situs, sedangkan Claude bagus kalau instruksinya jelas dan guardrail-nya ketat. Tetapi kalau crawling diserahkan penuh ke model, tokennya boros. Lebih baik bangun algoritma dengan banyak pengecekan (apa yang dilakukan saat bertemu paging, redirect, Cloudflare, dan seterusnya), lalu model cukup dipanggil sekali.

### Untuk Hamdan (Infra/QA) dan seluruh tim — kriteria penerimaan scraping

**Dari Pak Faris:**
- Pastikan dulu jumlah dokumen yang ter-*scan*. Untuk situs regulasi OJK targetnya sekitar 1.700.
- Scraping dianggap **berhasil** kalau saat scan sistem sudah mengetahui URL resmi, nama dokumen, nama berkas, dan ukuran setiap dokumen, artinya dokumen sudah terindeks. Proses unduh bergantung pada internet dan penyimpanan lokal, jadi tidak termasuk kriteria.
- Kalau jumlah hasil scan masih jauh dari angka *ground truth*, algoritmanya perlu dikulik lagi.
- DPEA sudah memegang angka *ground truth* per website (per bulan lalu) sebagai acuan.
- Hasil tidak harus langsung besar. Yang penting algoritmanya jalan. Skenario ini bisa langsung dipakai Hamdan untuk pengujian.

### Untuk Zaky (PM)

**Dari Pak Faris — Jadwal pengujian MVP:**
- Rumus untuk setiap MVP: tentukan tanggal rilis, lalu tarik mundur. **H-14 mulai pengujian, H-7 batas perbaikan.** Dengan begitu kalau pengujian menghasilkan feedback, masih ada seminggu untuk memperbaiki.
- MVP Fase 1 dirilis **11 Okt**, jadi pengujian mulai **pekan ini**. Siklus uji dan perbaikan berjalan sampai sekitar 9 Okt.
- Rumus yang sama berlaku untuk MVP berikutnya (± sebulan sekali).

**Dari Pak Faris — Dokumen sprint review:**
- Tidak perlu tanda tangan mentor. Informasi dari kampus (Pak Faizin): laporan dua mingguan sudah tidak memerlukan tanda tangan mentor. Cukup direview.
- Isinya tiga bagian:
  1. Progres yang sudah dilaporkan tiap minggu.
  2. Timeline minimal satu sprint ke depan beserta sprint backlog-nya.
  3. Masukan dari DPEA, termasuk yang lewat WhatsApp (contoh: "desain ini diganti"), beserta status sudah atau belum dikerjakan.

**Dari Pak Andika:**
- Laporan Zaky di grup sudah cukup lengkap. Figma juga dinilai lengkap; Pak Andika akan meneruskan update ke Pak Dwi.
- **Pendanaan:** skema reimburse, dikumpulkan dan diganti di akhir. Pastikan tidak mengganggu kas tim. Kalau ada kendala, lapor ke Pak Andika supaya dibantu pimpinan.
- **Kunjungan offline ke kampus:** Pak Dwi berkenan datang, asal tidak minggu depan karena Pak Faris training seminggu di Jakarta.
- **Surat rekomendasi:** di akhir proyek, Zaky selaku ketua tim meminta surat rekomendasi dari DPEA (Pak Dwi) sebagai tambahan CV anggota tim.

---

## 4. Diskusi — kesiapan uji MVP Fase 1

- Pak Faris menanyakan kapan tim siap diuji.
- **Ikhwan:** penyesuaian frontend Fase 1 bisa selesai pekan ini. Penyambungan ke backend bergantung pada API, jadi Ikhwan akan berkoordinasi dengan Rafli soal kontraknya.
- **Zaky:** pekan ini semua bagian diintegrasikan dan diuji internal, supaya pada rapat berikutnya DPEA sudah bisa mencoba.

---

## 5. Keputusan

1. Pengujian MVP Fase 1 dimulai pekan ini; rilis 11 Okt. Untuk setiap MVP berlaku H-14 mulai uji dan H-7 batas perbaikan.
2. Scraping diterima kalau dokumen terindeks saat scan (URL, nama dokumen, nama berkas, ukuran). Jumlahnya dibandingkan dengan *ground truth* DPEA; unduh tidak termasuk kriteria.
3. Tiga sumber uji MVP Fase 1: situs regulasi OJK, JDIH OJK, dan OneDrive public.
4. Scraper dibangun sebagai algoritma dengan pengecekan paging, redirect, dan captcha/Cloudflare. Crawling tidak diserahkan penuh ke LLM.
5. Format nama berkas dinamis, disusun pengguna dari komponen Nama / Tahun / Jenis / Bidang di halaman Scraping.
6. Halaman detail peraturan menampilkan isi dokumen untuk verifikasi. PDF dilihat langsung di browser bila memungkinkan; unduh ke lokal jadi cadangan tahap pertama.
7. Selama sprint dan MVP masih terbuka, perubahan UI boleh langsung di aplikasi tanpa revisi mockup dulu.
8. Prioritas saat ini Sprint 2 dan 3 (ingest dan knowledge base). Analisa menyusul.
9. Dokumen sprint review tidak perlu tanda tangan mentor dan memuat tiga bagian: progres, timeline + sprint backlog, serta masukan DPEA beserta statusnya.

---

## 6. Action item

### Zaky
- [ ] Selesaikan dokumen sprint review Sprint 2 (tiga bagian) dan kirim untuk direview — pekan ini
- [ ] Rekap masukan DPEA dari rapat dan WhatsApp beserta statusnya, untuk dokumen sprint review
- [ ] Koordinasikan integrasi frontend–backend dan pengujian internal; siapkan akses uji untuk DPEA sebelum rapat 6 Okt
- [ ] Tagih tanda tangan PRD ke Pak Andika (#45)
- [ ] Perbarui backlog: format nama dinamis, kriteria penerimaan scraping, OneDrive masuk uji MVP Fase 1
- [ ] Sampaikan hasil rapat ke Fathir
- [ ] Atur jadwal kunjungan offline ke kampus (bukan minggu depan)
- [ ] Akhir proyek: minta surat rekomendasi DPEA (Pak Dwi)

### Ikhwan
- [ ] Revisi redundansi dashboard; angka kategori bisa diklik ke Knowledge Base yang terfilter
- [ ] Halaman detail peraturan berisi isi dokumen; PDF dilihat langsung di browser (unduh lokal sebagai cadangan)
- [ ] UI format nama berkas di halaman Scraping: tombol Nama / Tahun / Jenis / Bidang, kotak format, tombol clear
- [ ] Selesaikan penyesuaian frontend Fase 1 pekan ini
- [ ] Sepakati kontrak API dengan Rafli dan sambungkan frontend ke backend

### Rafli
- [ ] Uji scan ke tiga sumber (regulasi OJK, JDIH, OneDrive); laporkan jumlah terindeks dibandingkan *ground truth*
- [ ] Tangani paging (dua format), redirect, dan captcha
- [ ] Ubah rename dari format tetap `nomor judul tahun` menjadi dinamis mengikuti urutan komponen dari UI
- [ ] Uji ketangguhan scan ke situs lain (cukup scan, tanpa unduh)
- [ ] Sediakan kontrak API untuk Ikhwan

### Fathir
- [ ] Lanjutkan metadata dasar, OCR halaman pertama, dan penamaan baku (US-20, US-20a); selaraskan dengan rename dinamis Rafli
- [ ] Bantu Rafli menguji scan ke tiga sumber
- [ ] Masih terbuka dari MoM #3: komparasi waktu proses folder PDF vs vektor (#42)

### Hamdan
- [ ] Susun skenario uji scraping berdasarkan kriteria penerimaan (jumlah terindeks vs *ground truth*)
- [ ] Siapkan dokumen uji untuk pengujian internal pekan ini
- [ ] Estimasi kapasitas pengguna dan penyimpanan dokumen di server backend

### Mitra
- [ ] Pak Faris: bagikan angka *ground truth* jumlah dokumen per situs sebagai pembanding
- [ ] Pak Faris: contoh surat tanggapan tertulis (#27) — masih ditunggu
- [ ] Pak Andika: tanda tangan PRD

---

## 7. Catatan dari sisi PM

- **Kriteria M1 berubah.** Dokumen 07 menulis M1 sebagai "≥ 3 situs sumber tertarik; ≥ 20 dokumen di KB". Sekarang ukurannya jumlah dokumen terindeks dibandingkan *ground truth* (± 1.700 OJK, ± 400–500 JDIH), tanpa unduh. Dokumen 07, Test Plan (11), dan kriteria penerimaan US-13 / US-13b (#44) perlu disesuaikan.
- **OneDrive maju ke Fase 1.** Di backlog, US-17 (#30) ada di Sprint 5 karena dulu foldernya belum tersedia. Sekarang foldernya sudah ada (#26 ditutup), backend Rafli sudah bisa membacanya, dan Pak Faris memasukkannya ke tiga sumber uji MVP. US-17 sebaiknya ditarik ke Sprint 3.
- **Penamaan berkas kini melibatkan tiga orang.** Ikhwan membuat UI format, Rafli logika rename, Fathir OCR halaman pertama yang menyediakan metadatanya. US-20a (#12) perlu dipecah atau diberi sub-task supaya ketiganya tidak jalan sendiri-sendiri.
- **Detail peraturan adalah fondasi verifikasi.** Permintaan Pak Faris terkait US-28 (#19) di Fase 1 dan US-49a (#72, buka PDF asli dari temuan) di Fase 3. Kalau viewer PDF dibangun sekarang, Fase 3 tinggal memakainya.
- **Integrasi frontend–backend belum dimulai** per rapat ini, dan ini jalur kritis minggu ini. Kontrak API perlu disepakati secepatnya supaya pengujian bisa jalan sesuai H-14.
- **Risiko jadwal:** Pak Faris training seminggu di Jakarta "minggu depan", yang bisa bertabrakan dengan rapat 6 Okt dan uji coba mitra 8 Okt. Konfirmasi ketersediaan beliau dan pastikan akses uji bisa dipakai dari jarak jauh.
- **Carry-over Sprint 2.** Sprint 2 (14–27 Sep) sudah lewat, tetapi beberapa story masih *in review*. Catat sebagai carry-over di dokumen sprint review, jangan disembunyikan.
- **Hosting.** Pertanyaan kapasitas Hamdan menyangkut layanan hosting gratis. Menurut ADR-11, frontend ada di Vercel, sedangkan backend dan penyimpanan PDF di VPS, jadi kapasitas dokumen hasil scraping bergantung pada disk VPS. Konfirmasi ke Hamdan dan Fathir layanan mana yang dimaksud.
- **Pilihan model LLM** (Claude untuk metadata, saran Gemini untuk crawling) sebaiknya dicatat sebagai ADR supaya biaya token terukur sejak awal.
- **Tanda tangan PRD** sudah diminta di dua rapat berturut-turut (MoM #3 dan hari ini).
