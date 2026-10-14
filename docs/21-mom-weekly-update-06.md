# MoM — Weekly Update #6 (Minggu 1 Fase 2)

**Tanggal:** Selasa, 13 Oktober 2026 · ± 27 menit · Zoom
**Hadir DPEA:** Pak Faris Budi (Product Owner)
**Berhalangan DPEA:** Pak Andika Prihandoko (Mentor)
**Hadir Tim:** Zaky (PM/BA), Fathir (Data/ML), Rafli (Backend), Ikhwan (Frontend), Hamdan (Infra/QA)
**Notulis:** Zaky
**Rekaman:** *(menyusul)*

---

## 1. Ringkasan singkat

- Minggu pertama Fase 2 (MVP Analisa & Summary, 12 Okt – 8 Nov), awal Sprint 4. Sprint 3 selesai semua. Sebagian pekerjaan Sprint 5 dan 6 sudah mulai dicicil Backend dan Data/ML.
- **Penyimpanan untuk analisa: vektor.** Dokumen di-OCR dan diubah ke vektor sejak awal, bukan di-OCR saat ada permintaan.
- **Deteksi duplikat ditambah satu lapis:** judul dan nomor peraturan dari halaman pertama. Kalau sama, simpan berkas yang ukuran atau jumlah halamannya paling besar.
- **Prinsip pemakaian AI:** AI dipakai untuk membangun algoritma, dan sistem harus tetap berjalan tanpa AI.
- **Aturan versi dokumen** dijelaskan Pak Faris: perubahan ke-N mengubah sebagian pasal, sedangkan pencabutan mengganti peraturan sepenuhnya.
- **VPS diganti dengan yang lebih besar.** Pak Faris akan menalangi biayanya dulu.
- Pak Faris menantikan layar Analisa karena itu inti aplikasi, dan sudah menyiapkan beberapa test case.

---

## 2. Laporan progres per orang

### Zaky — PM / BA
- Menunjukkan papan GitHub Project:
  - Sprint 3 selesai semua.
  - Sprint 4 sedang berjalan: sebagian *in progress*, sebagian *in review / testing*, dan sebagian terblokir menunggu data dari OJK.
  - Sebagian item Sprint 5 sudah dicicil Backend, dan Sprint 6 sudah mulai dikerjakan Data/ML.
- Fokus Fase 2: analisa dokumen, Summary, dan Key Takeaways.

### Fathir — Data / ML
- Fase 1 seharusnya aman; rinciannya disampaikan Hamdan.
- Fase 2: masih membangun *baseline* analisa dan summary. Fitur yang memakai AI belum dicoba diintegrasikan.
- **VPS:** VPS murah yang dipakai sekarang ternyata berat dan lambat karena kuotanya kecil, jadi tim akan pindah ke VPS yang lebih besar.
- **Belum dikerjakan dari fase sebelumnya:** benchmark waktu proses penyimpanan langsung (PDF + OCR) dibandingkan vektor. Akan dikerjakan bersama Hamdan.
- **Menjawab Pak Faris soal crawler:** dua alamat yang diberikan (situs regulasi OJK dan JDIH) sudah berhasil. Situs lain belum dicoba.
- **Jumlah dokumen:** hasil scan menemukan lebih dari 1.400 dokumen. Yang sudah disimpan di Knowledge Base baru 151, karena penyimpanan VPS hampir penuh.

### Rafli — Backend
- Seluruh pekerjaan backend Fase 1 sudah selesai.
- Fase 2 yang sudah dikerjakan:
  - Pasal hasil ekstraksi tersimpan tanpa duplikasi, lengkap dengan nomor halaman PDF dan hierarkinya.
  - Dokumen yang dihapus di Knowledge Base tidak benar-benar hilang; jejaknya tetap tersimpan.
- **Carry-over:** uji ulang folder data internal dan OneDrive di Knowledge Base. Folder data internal di OneDrive masih kosong.
- **Bisa dipercepat minggu depan:** versioning dokumen.
- **Cara crawler dibangun** (menjawab Pak Faris): Rafli mencoba sendiri, lalu meminta AI agent memeriksa apakah hasilnya benar. Kedua cara jalan.
- **Cek duplikat saat ini:** berkas baru dicek hash-nya dulu, lalu ukuran berkas dan penamaan dokumennya.

### Ikhwan — Frontend
- Fase 1 selesai dan sudah tersambung ke backend sesuai feedback Figma.
- Sedang menyiapkan slicing layar Analisa. Tampilannya ditunjukkan minggu depan untuk diberi feedback, lalu disambungkan ke backend setelah disepakati.

### Hamdan — Infra / QA
- Secara umum aman. Yang tersisa adalah VPS yang masih kecil.
- Sudah membagikan ke Pak Andika halaman web (dibuat dengan Claude) yang menyusun cakupan uji.
- **Hasil uji:** Infra dan Scraping sudah memenuhi, kecuali disk dan memori untuk data scan. Masalah ini akan teratasi setelah VPS yang lebih besar dibeli.
- Sisanya perbaikan kecil, bukan masalah besar.

---

## 3. Feedback dari mitra

### Dari Pak Faris

**Untuk Fathir — crawler dan penyimpanan:**
- **Crawler harus diuji generik.** Pak Faris menanyakan apakah crawler bisa dipakai untuk situs mana pun, misalnya kementerian lain, atau hanya untuk dua alamat yang diberikan. Minta dicoba ke situs lain.
- Mekanisme scan ditegaskan ulang: semua dokumen di-scan dulu sehingga terlihat semua, lalu pengguna memilih mana yang disimpan.
- **Penyimpanan untuk analisa: vektor.** Secara logika mesinnya memang vektor, karena untuk membuat vektor dokumen harus di-OCR dulu. Dokumen yang tidak bisa di-OCR (misalnya hasil pindai *hard copy*) sudah ketahuan sejak awal. Kalau OCR baru dilakukan saat ada permintaan, permintaan itu bisa berhenti begitu bertemu dokumen yang tidak bisa diproses. Jadi kalau dari awal bayangannya vektor, langsung saja pakai vektor.

**Untuk Rafli — duplikat dan versi dokumen:**
- **Tambah satu lapis cek duplikat.** Karena dokumen tetap melewati OCR sebelum jadi vektor, baca halaman pertama bagian atas: judul dan nomor peraturan, yang formatnya pasti unik di setiap dokumen.
- Alasannya, satu situs bisa mengunggah peraturan beserta lampirannya dalam satu berkas, sedangkan situs lain memisahkan lampiran. Ukuran berkas dan jumlah halamannya jadi berbeda, padahal isinya sama.
- **Aturannya:** kalau judul dan nomor peraturan sama, ambil yang ukurannya atau jumlah halamannya paling besar.
- **Kapan dokumen dianggap versi baru** (menjawab pertanyaan Rafli). Ada dua pola:
  1. **Perubahan.** Judulnya berbunyi "Peraturan Nomor … tentang Perubahan Kedua atas Peraturan …". Perubahan tidak otomatis mengganti seluruh peraturan sebelumnya. Di bagian awal disebutkan pasal mana yang diubah. Contoh: peraturan dasar punya 20 pasal, perubahan kedua mengubah 4 di antaranya, dan perubahan ketiga mengubah 7 pasal dari peraturan awal ditambah 2 pasal dari perubahan kedua.
  2. **Pencabutan.** Ada keterangan bahwa setelah peraturan ini berlaku, peraturan sebelumnya otomatis dicabut. Berarti peraturan lama dicabut sepenuhnya.
- Jadi versi dikenali dari "perubahan ke berapa", atau dari kata kunci yang menyatakan mencabut, mencabut sebagian, atau mengganti penuh.
- **Mengapa status berlaku penting:** pengawas di daerah (misalnya pengawas BPR di Yogyakarta) mengeluarkan pernyataan yang diperlakukan seperti fatwa, dan harus didukung peraturan yang masih berlaku. Merujuk peraturan yang ternyata sudah dicabut adalah blunder.

**Untuk semua — prinsip pemakaian AI:**
- Di DPEA, AI dipakai untuk **membangun algoritmanya**. Kalau akses AI hilang atau token habis, sistem tetap berjalan sebagai *fallback*. AI boleh dipakai lagi sesudahnya untuk *enhancement*, tetapi tanpa AI pun sistem harus jalan.
- Terapkan di MVP 2: kalau memakai AI, minta AI membangun algoritmanya, lalu uji manual. Konteks peraturan sering tidak terbaca kalau dibaca kata per kata. Contohnya, peraturan internal tentang SDM dibaca berbeda dengan POJK untuk pihak luar seperti perbankan.

**Untuk Ikhwan — layar Analisa:**
- Struktur halaman: satu halaman dengan frame. Frame kiri berisi daftar (master), frame kanan berisi isi yang berganti, dan URL-nya tetap satu, tidak membuka jendela baru. Ikhwan mengonfirmasi rencananya memang begitu.
- Tambahkan penanda proses sederhana, misalnya *progress bar*, saat pengguna mengklik Analisa, supaya tahu prosesnya jalan. Ikhwan: sudah ada.
- Lanjutkan dulu; mockup-nya akan dilihat minggu depan.

**Untuk Hamdan dan Fathir — VPS:**
- Cari VPS yang **proper** sesuai kebutuhan, sekalian untuk sampai Desember. Kabari Pak Faris detail biayanya; beliau akan menalangi dulu dan mentransfer ke salah satu anggota tim. Segera dibeli supaya pekerjaan tidak tertunda.
- Pengalaman semester lalu: dua kelompok kehabisan waktu uji karena menunggu infrastruktur. Bangun sekalian yang bagus — Pak Faris sendiri memakai crawler untuk penelitian karena menghemat waktu dan biaya mengumpulkan data.

**Umum:**
- Belum ada feedback baru. Pak Faris menantikan layar Analisa karena itu jantung aplikasi, dan akan banyak waktu dihabiskan untuk mengujinya. Beliau sudah menyiapkan beberapa test case.
- Kalau tim punya ide baru untuk algoritma atau SOP, diskusikan langsung dengan beliau di luar rapat, lalu terapkan.

---

## 4. Diskusi di luar proyek — kunjungan ke Jakarta

- Zaky sudah mengajukan undangan Pak Andika ke dosen. Kunjungan diperbolehkan, tetapi dana terbatas: alokasi reimburse Capstone Rp3 juta per tim, dengan bobot maksimal 25% untuk kebutuhan tim, termasuk transportasi.
- Pak Faris: tidak apa-apa, sampaikan ke Pak Andika. Menurut beliau, Pak Andika sudah di level bisnis dan lebih melihat gambaran besar.

---

## 5. Keputusan

1. Penyimpanan untuk analisa memakai vektor. Dokumen di-OCR dan diubah ke vektor saat ingest, bukan saat ada permintaan. Benchmark waktunya tetap dijalankan sebagai pembanding.
2. Cek duplikat ditambah lapis judul + nomor peraturan dari halaman pertama. Kalau sama, simpan yang ukuran atau jumlah halamannya paling besar.
3. Versi dokumen dikenali dari pola "Perubahan ke-N atas …" (mengubah sebagian pasal) dan kata kunci pencabutan (mencabut penuh atau sebagian).
4. AI dipakai untuk membangun algoritma; sistem harus tetap berjalan tanpa AI, dan hasilnya diuji manual.
5. Layar Analisa memakai frame kiri (master) dan kanan (isi) dalam satu URL, dengan penanda proses saat analisa berjalan.
6. VPS diganti dengan yang lebih besar untuk sampai Desember; Pak Faris menalangi biayanya dulu.
7. Crawler diuji ke situs di luar dua alamat yang diberikan.

---

## 6. Action item

### Zaky
- [ ] Koordinasikan pembelian VPS: rangkum pilihan dan biaya dari Hamdan dan Fathir, kirim ke Pak Faris untuk ditalangi
- [ ] Sampaikan keterbatasan dana kunjungan Jakarta ke Pak Andika
- [ ] Perbarui backlog: aturan duplikat judul + nomor, kriteria versioning, keputusan vektor
- [ ] Tagih ke mitra: akses OneDrive (#112), angka *ground truth* (#87), contoh surat tanggapan (#27), tanda tangan PRD (#45)
- [ ] Tanyakan penerimaan resmi MVP Fase 1 ke Pak Faris

### Fathir
- [ ] Uji crawler ke situs di luar OJK dan JDIH, misalnya situs kementerian lain — cukup sampai scan
- [ ] Benchmark waktu proses penyimpanan PDF + OCR vs vektor bersama Hamdan (#42)
- [ ] Lanjutkan *baseline* analisa dan summary; siapkan pemakaian AI sebagai pembangun algoritma dengan *fallback* tanpa AI
- [ ] Pilih VPS yang lebih besar bersama Hamdan

### Rafli
- [ ] Tambahkan cek duplikat judul + nomor peraturan dari halaman pertama; simpan yang ukuran atau halamannya paling besar
- [ ] Kerjakan versioning dokumen (US-29, #37) memakai pola perubahan dan pencabutan dari Pak Faris
- [ ] Uji ulang folder data internal dan OneDrive di Knowledge Base (#30)

### Ikhwan
- [ ] Slicing layar Analisa: frame kiri/kanan, satu URL, *progress bar* — tunjukkan di rapat berikutnya (#116)
- [ ] Sambungkan ke backend setelah tampilan disepakati

### Hamdan
- [ ] Cari VPS yang proper bersama Fathir; kirim detail biaya ke Zaky untuk diteruskan ke Pak Faris
- [ ] Uji ulang disk dan memori untuk data scan setelah VPS baru terpasang
- [ ] Selesaikan perbaikan kecil hasil uji

### Mitra
- [ ] Pak Faris: talangi biaya VPS
- [ ] Pak Faris: siapkan test case untuk layar Analisa
- [ ] Pak Faris / Pak Andika: akses OneDrive (#112), angka *ground truth* (#87), contoh surat tanggapan (#27) — masih ditunggu
- [ ] Pak Andika: tanda tangan PRD (#45)

---

## 7. Catatan dari sisi PM

- **Aturan duplikat Pak Faris menutup celah yang sudah ada.** Saat ini backend hanya menangkap berkas yang identik (hash + ukuran, URL sama, atau nama + ukuran sama). Peraturan yang sama dengan berkas berbeda — misalnya dari situs OJK dan dari JDIH, atau dengan lampiran tergabung vs terpisah — masih masuk dua kali. Lapisan data sudah punya kunci jenis–nomor–tahun untuk pencocokan lintas sumber dan OCR halaman pertama (`pipeline/hero/extract/firstpage.py`), jadi backend tinggal memakainya. Perlu story baru, misalnya US-19a.
- **Versioning bisa memakai mesin yang sudah ada.** `pipeline/hero/harmonisasi/refs.py` sudah membaca judul "Perubahan atas …", penutup "… dicabut dan dinyatakan tidak berlaku", dan instruksi seperti "Ketentuan Pasal 5 diubah". Graf relasinya sudah mencatat 893 relasi mencabut dan 99 mengubah. US-29 (#37) sebaiknya memakai ini, bukan membangun ulang di backend.
- **Spike #42 perlu dibuka lagi.** Issue itu ditutup 9 Okt berdasarkan `pipeline/docs/DB_COMPARISON.md`, yang membandingkan kecepatan pencarian dan ukuran penyimpanan. Pertanyaan aslinya — waktu proses menyimpan ribuan dokumen sebagai PDF + OCR vs vektor — menurut Fathir belum dijawab.
- **Prinsip AI Pak Faris sejalan dengan arsitektur yang ada.** Mode Deterministik sebagai dasar dan AI sebagai lapisan opsional sudah menjadi rancangan (US-04, US-06). Bedanya, Pak Faris menekankan AI sebagai *pembangun* algoritma. Ini perlu tercermin di cara tim menulis dan menguji kode analisa, bukan hanya di saklar mode.
- **VPS dan dana.** Biaya VPS yang lebih besar akan ditalangi Pak Faris. Perlu dipastikan apakah biaya VPS dihitung dalam batas 25% "kebutuhan tim" dari alokasi Rp3 juta, atau di pos lain — kalau masuk 25%, sisanya nyaris tidak cukup untuk transportasi ke Jakarta.
- **Penerimaan M1 masih menggantung.** Pak Faris hanya menanyakan sifat crawler dan jumlah dokumen; belum ada pernyataan menerima MVP Fase 1. Tanyakan secara eksplisit di rapat berikutnya.
- **Layar Analisa: sepakati kontrak API sebelum slicing.** Setelah rapat, Ikhwan menyampaikan bahwa di Fase 1 frontend sempat dikerjakan dua kali karena dibuat sebelum backend jelas. Kontrak layanan analisa sudah tertulis di `pipeline/docs/API_CONTRACT_ML.md`; pakai itu sebagai acuan sejak awal.
- **Knowledge Base staging baru 151 dari lebih dari 1.400 dokumen hasil scan**, karena penyimpanan VPS hampir penuh. VPS baru juga menentukan apakah test case Pak Faris bisa diuji pada korpus yang representatif.
