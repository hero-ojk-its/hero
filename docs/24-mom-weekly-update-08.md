# MoM — Weekly Update #8 (Review Akhir Fase 2)

**Tanggal:** Senin, 9 November 2026 · ± 50 menit · Zoom
**Sifat rapat:** pengganti Weekly pekan lalu (3 Nov) sekaligus review akhir Fase 2 / Sprint 5
**Hadir DPEA:** Pak Faris Budi (Product Owner)
**Berhalangan DPEA:** Pak Andika Prihandoko (Mentor) — dinas ke Surabaya
**Hadir Tim:** Zaky (PM/BA), Ikhwan (Frontend), Rafli (Backend), Fathir (Data/ML), Hamdan (Infra/QA)
**Notulis:** Zaky
**Rekaman:** https://youtu.be/VBmkQJjq4nY

---

## 1. Ringkasan singkat

- Fase 2 (MVP Analisa & Summary) berakhir 8 November. Pak Faris meminta laporan dua pekan sekaligus dan link untuk uji coba.
- **MVP 2 belum dinyatakan "Go".** Item yang tertunda diselesaikan dulu sebelum masuk Fase 3.
- **Summary dipisah dari Analisa.** Summary (MVP 2) menjadi menu tersendiri: unggah satu dokumen, keluar ringkasan dan Key Takeaways, tanpa melibatkan Knowledge Base. Analisa terhadap Knowledge Base adalah MVP 3.
- **Semua proses mulai dari Deterministik.** AI menjadi *toggle* setelah hasil Deterministik keluar, bukan pilihan di awal. Tanpa AI, sistem tetap jalan.
- **Data training dari DPEA:** folder berisi pasangan **In** (draft yang dimintakan tanggapan) dan **Out** (tanggapan DPEA) tahun 2024, untuk *ground truth* dan pengujian. Data 2025 dan 2026 menyusul.
- **Tim harus bisa menjelaskan algoritmanya sendiri** — misalnya kenapa pasal ini yang dipilih, atau kenapa poin utamanya 10. Pertanyaan yang belum terjawab dicatat di register perbaikan.
- **Rapat lanjutan besok, Selasa 10 November pukul 14.00**, dengan perbaikan dari masing-masing peran.

---

## 2. Laporan progres per orang

### Zaky — PM / BA
- Papan proyek: item Sprint 5 diturunkan ke Sprint 6 supaya tidak *overload*, sehingga Sprint 6 bercampur dengan item Fase 3.
- Item Fase 2 sebagian besar sudah direview dan diuji, dan laporannya ada, tetapi status di papan belum diperbarui.
- Target Fase 2 yang dibacakan:
  - Summary dan Key Takeaways untuk minimal 10 dokumen uji.
  - Waktu proses di bawah 5 menit per dokumen pada mode Deterministik.
  - Mode AI-Assisted bisa diaktifkan atau dinonaktifkan lewat *toggle*, dengan narasi yang lebih natural.
- Berikutnya Fase 3 — MVP Harmonisasi: membandingkan draft dengan peraturan eksisting dan mendeteksi potensi konflik.

### Ikhwan — Frontend
- Total regulasi di Knowledge Base sudah 1.500.
- Layar Analisa masih diuji dengan data dummy, karena belum jelas contoh draft yang nantinya diunggah.
- Dokumen yang pernah dianalisis memunculkan penanda "sudah pernah dianalisis", dan hasil sebelumnya bisa dibuka.
- Hasil yang ditampilkan: ringkasan eksekutif, poin utama dari PDF, informasi tambahan, dan perbandingan Deterministik vs AI. Bagian AI masih kosong karena belum diuji dengan AI.
- Masih bingung soal alur harmonisasi: fitur terpisah atau satu ruang kerja dengan Analisa. Dengan data dummy, semua pasal berstatus "baru" karena tidak ada yang terkait dengan Knowledge Base.

### Fathir — Data / ML
- Knowledge Base seharusnya sudah masuk dan terindeks semua.
- **Cara kerja ringkasan** (menjawab Pak Faris): dari *vector database*, beberapa pasal dirujuk lewat regex dan dicari lewat vektor, lalu ditautkan ke dokumen di Knowledge Base. Pak Faris menanggapi bahwa ringkasan seharusnya hanya dari berkas yang diunggah, tanpa hubungan ke Knowledge Base. Fathir: yang ia maksud adalah bagian rujukan.
- **AI:** memakai model Gemini lewat Google AI Studio, beberapa varian Flash dan Pro. Hasilnya belum bagus, karena alurnya Deterministik dulu lalu hasilnya dimasukkan ke AI.
- **Batas pemakaian:** dokumentasi model menyebut ada batas, tetapi dari sisi aplikasi tidak dibatasi.
- **Alih otomatis ke Deterministik** kadang terjadi tanpa diketahui sebabnya; dugaan Fathir, batas pemakaian API. Akses lewat API juga tidak sebagus memakai model langsung di chat.
- **Unggahan pertama memutar terus (*loading*)** saat demo, karena penjadwal (*cron*) di pipeline belum dibangun dan masih harus dijalankan manual.

### Rafli — Backend
- **Cara menyusun poin utama** (menjawab Pak Faris): per kategori, misalnya kewajiban. Setiap poin mencatat pasalnya dan subjeknya (bank, umum, dan sebagainya), lalu semua yang terdeteksi dijumlahkan. Contoh yang didemokan menghasilkan 10 kategori.
- Belum bisa menjelaskan kenapa sistem memilih pasal tertentu dan bukan pasal lain. Pertanyaan ini dicatat Pak Faris di register untuk diperbaiki.

### Hamdan — Infra / QA
- Membuat halaman web (dengan Claude) untuk pengujian per MVP / sprint, berisi langkah uji, hasil, dan tangkapan layar. Panduannya baru dikirim ke Zaky pagi ini.
- Pengujian sejauh ini bersifat pembuktian bahwa fitur berjalan. Dari yang sudah dibagikan, semuanya aman, tetapi algoritmanya memang masih membingungkan.

---

## 3. Feedback dari mitra

### Dari Pak Faris

**Ekspektasi MVP 2 — Summary:**
- Unggah satu peraturan, lalu keluar ringkasan dan Key Takeaways-nya. Contoh: 35 halaman menjadi satu halaman dalam waktu kurang dari 5 menit.
- Tunjukkan perbedaan hasil Deterministik dan AI: halaman awalnya seperti apa, hasil ringkasannya seperti apa, sudah natural atau masih kaku seperti robot.
- Layar MVP 2 harus pertama-tama menunjukkan seberapa bagus ringkasannya dan seberapa akurat Key Takeaways-nya. Analisa terhadap Knowledge Base baru masuk di MVP 3.

**Data training dan *ground truth*:**
- Pak Faris mengunggah folder "training 2024" berisi contoh tanggapan yang sudah terjadi. Setiap nomor punya pasangan **In** dan **Out**:
  - **In** adalah konsep atau draft peraturan yang dikirimkan ke DPEA untuk ditanggapi, sebelum disampaikan ke departemen lain.
  - **Out** adalah tanggapan DPEA selaku satuan kerja TI atas draft tersebut.
- Setelah tanggapan dikirim, draft itu menjadi peraturan resmi yang dirilis publik, sehingga seharusnya sudah ada di Knowledge Base.
- Data ini terutama untuk fitur terakhir (tanggapan berbasis *Point of View*). Tetapi data yang sama juga bisa dipakai untuk mengukur kemiripan: **Out** adalah hasil analisa manual ahli, sedangkan sistem menghasilkan analisa Deterministik dan AI.
- Berikutnya akan dipakai data 2025, lalu data 2026 yang belum terbit, untuk melihat akurasi sistem secara keseluruhan, bukan per modul.
- Saat rapat, satu dokumen **In** dicoba diunggah ke layar Analisa mode Deterministik.

**Prinsip Deterministik dulu, AI kemudian:**
- Ada dua mekanisme:
  1. **Summary** — objeknya hanya dokumen yang diunggah. Kalau dokumennya 49 halaman, yang diolah 49 halaman itu.
  2. **Analisa** — berhubungan dengan Knowledge Base yang isinya ribuan halaman. Supaya token tidak habis membaca ribuan halaman per permintaan, olah dulu secara Deterministik dari *long list* menjadi *shortlist* (misalnya hanya 20–30 halaman yang terkait), baru AI dikenakan pada *shortlist* itu.
- Kalau semua alur memang mulai dari Deterministik, **pengguna tidak perlu memilih mode di awal.** Jalankan Deterministik, tampilkan hasilnya, lalu sediakan *toggle* untuk mengaktifkan AI.
- Dengan begitu, kalau layanan AI tidak tersedia, pekerjaan tetap jalan. Kalau AI dipakai langsung sejak awal dan layanannya bermasalah, pengguna tidak bisa bekerja sama sekali.
- Intinya: bangun algoritmanya dulu.

**Untuk Zaky — peran PM:**
- PM adalah ujung tombak tim. Klien biasanya hanya mengenal PM, dan kalau dirasa lambat, klien meminta manajemen mengganti PM-nya.
- PM harus aktif bertanya ke anggota tim: modul apa saja, input dan alurnya seperti apa, sehingga saat mendemokan terlihat paham dan klien yakin. Tidak harus paham semua detail, tetapi harus menguasai saat presentasi.
- Anggota tim juga harus aktif memberi tahu PM. Kalau PM tidak menguasai, kerja anggota tim di belakangnya tidak terlihat.

**Untuk Ikhwan — layar Summary dan Analisa:**
- **Pisahkan Summary dan Analisa.** Buat menu baru **Summary** di bawah Ingest Dokumen, lalu Analisa Regulasi di bawahnya.
- Summary hanya: unggah dokumen, lalu keluar ringkasan dan Key Takeaways. Tujuannya seperti abstrak *paper*: pengguna yang baru menerima puluhan halaman langsung tahu peraturan itu membahas apa, tanpa membaca semuanya dulu.
- Di layar Summary, frame kiri (struktur pasal) tidak perlu. Cukup naskah regulasi dan hasil ringkasan / poin utama. Tata letak dibuat dinamis, karena tidak semua pengguna punya layar besar.
- Tidak perlu pilihan mode di awal. Tambahkan *toggle* **AI** di kanan atas hasil.
- Tombol "Lanjutkan Harmonisasi" diganti **"Lanjutkan Analisa"**, yang membawa ke menu Analisa.
- Buat sesederhana mungkin, karena penggunanya orang awam, bukan *engineer*.

**Untuk Rafli — pahami algoritmanya:**
- Rafli dianggap pemegang arsitektur backend. Memakai AI atau model apa pun untuk membangun boleh, tetapi arsitek yang memegang kendali dan harus paham.
- Klien tidak akan bertanya ke AI-nya; klien menganggap tim memahami semuanya.
- Latih dengan pertanyaan-pertanyaan seperti ini dan cek silang manual:
  - Kenapa yang diambil pasal 2, bukan pasal 3?
  - Kenapa dokumen 49 halaman hanya menghasilkan 10 Key Takeaways, bukan 49 (satu per halaman)?
- Siap menjawab pertanyaan teknis di rapat berikutnya.

**Untuk Fathir — model AI:**
- Pak Faris akan banyak bertanya soal analisa, karena terkait *vector database*, token, dan model.
- Bandingkan beberapa model (varian Flash dan Pro). Minta model menyusun skenario, lalu lakukan *post-validation*: biarkan tiap model menjawab dan evaluasi hasilnya. Tujuannya mengetahui apakah Flash sudah cukup atau perlu Pro.
- Siap menjawab pertanyaan "kenapa memakai model ini" dan "bisakah pemahamannya dibuat lebih dalam".

**Untuk Hamdan — kualitas:**
- QA harus memegang kualitas. Unggahan pertama yang terus *loading* saat demo seharusnya tidak terjadi kalau QA sudah dijalankan.
- Posisikan diri sebagai "mandor": periksa unit test, dan posisikan diri sebagai klien — pertanyaan apa yang kira-kira akan diajukan klien.
- UAT oleh DPEA adalah tahap terakhir. Sebelum sampai ke sana, semua error harus sudah dibereskan tim.
- Buat skenario uji lebih bervariasi dan *ground truth* baru sendiri untuk menguji hal yang belum terbaca sistem. Data 2024 (draft In maupun tanggapan Out) bisa dipakai.

**Jadwal:**
- Rapat hari ini dianggap pengganti pekan lalu. **Besok, Selasa 10 November pukul 14.00**, rapat progres pekan ini dengan perbaikan dari masing-masing peran.
- Fokus menyelesaikan item yang tertunda, karena MVP 2 belum "Go", sebelum masuk ke tahap berikutnya.
- Kalau bisa, hadir langsung; yang penting bisa ikut.

---

## 4. Keputusan

1. MVP 2 belum diterima. Item yang tertunda diselesaikan sebelum Fase 3.
2. Summary (MVP 2) dipisah dari Analisa (MVP 3) dan menjadi menu tersendiri di bawah Ingest Dokumen. Summary hanya mengolah dokumen yang diunggah, tanpa Knowledge Base.
3. Semua proses mulai dari Deterministik. AI berupa *toggle* setelah hasil keluar; tidak ada pilihan mode di awal.
4. Untuk Analisa terhadap Knowledge Base: Deterministik menyaring *long list* menjadi *shortlist*, dan AI hanya dikenakan pada *shortlist*.
5. Data training 2024 (pasangan In / Out) dipakai sebagai *ground truth* dan bahan uji; data 2025 dan 2026 menyusul.
6. Tim wajib bisa menjelaskan algoritmanya. Pertanyaan yang belum terjawab masuk register perbaikan.
7. Beberapa model AI dibandingkan dengan skenario dan *post-validation*.
8. Rapat progres berikutnya: Selasa, 10 November 2026, pukul 14.00.

---

## 5. Action item — untuk rapat Selasa 10 Nov, 14.00

### Zaky
- [ ] *Walkthrough* dengan tiap anggota: modul, input, dan alur Summary serta Analisa, supaya bisa mendemokan sendiri
- [ ] Siapkan alur demo dan link uji coba untuk Pak Faris
- [ ] Perbarui status papan proyek sesuai laporan uji yang sudah ada

### Ikhwan
- [ ] Buat menu **Summary** di bawah Ingest Dokumen, terpisah dari Analisa Regulasi
- [ ] Layar Summary: naskah + ringkasan / Key Takeaways, tanpa frame struktur pasal, tata letak dinamis
- [ ] Hapus pilihan mode di awal; tambahkan *toggle* AI setelah hasil Deterministik keluar
- [ ] Ganti tombol "Lanjutkan Harmonisasi" menjadi "Lanjutkan Analisa"

### Rafli
- [ ] Pelajari dan dokumentasikan algoritma ringkasan dan poin utama: kenapa pasal tertentu terpilih, kenapa jumlah poinnya sekian
- [ ] Tindak lanjuti pertanyaan Pak Faris yang masuk register perbaikan

### Fathir
- [ ] Pastikan ringkasan hanya dari dokumen yang diunggah, terpisah dari rujukan Knowledge Base
- [ ] Bangun penjadwal (*cron*) di pipeline supaya unggahan tidak menunggu proses manual
- [ ] Bandingkan model Gemini varian Flash dan Pro dengan skenario + *post-validation*; siapkan alasan pemilihan model
- [ ] Selidiki alih otomatis ke Deterministik (dugaan batas API)

### Hamdan
- [ ] Jalankan QA alur unggah sebelum demo; pastikan tidak ada *loading* tanpa akhir
- [ ] Perluas skenario uji dan susun *ground truth* dari data training 2024
- [ ] Bagikan halaman uji ke tim dan Pak Faris

### Mitra
- [ ] Pak Faris: data training 2025, dan data 2026 yang belum terbit untuk uji akhir
- [ ] Pak Faris / Pak Andika: akses OneDrive (#112), angka *ground truth* (#87), tanda tangan PRD (#45) — masih ditunggu

---

## 6. Catatan dari sisi PM

- **Kebingungan lingkup di Weekly #7 sudah terjawab.** Pak Faris kini memisahkan dengan jelas: MVP 2 adalah Summary per dokumen tanpa Knowledge Base, sedangkan perbandingan per pasal dengan Knowledge Base adalah MVP 3. Backlog Fase 2 (US-35, US-36) tetap berlaku untuk Summary; logika "baru / sama / menggantikan" dari Weekly #7 masuk Fase 3.
- **Status indikator M2:**

  | Indikator | Status |
  | --- | --- |
  | Summary & Key Takeaways ≥ 10 dokumen | Tercapai di lapisan data (114 dokumen) |
  | Waktu proses < 5 menit per dokumen | Tercapai |
  | *Toggle* AI-Assisted | ⚠ belum stabil: hasil AI kosong pada unggahan pertama, dan alih otomatis ke Deterministik belum diketahui sebabnya |

  PO belum menerima M2. Ditambah tata ulang layar Summary, M2 praktis mundur dari tenggat 8 November.

- **Data training In / Out kemungkinan menjawab permintaan lama #27.** Issue itu meminta contoh surat tanggapan tertulis beserta dokumen dasarnya (RSK-19) — persis isi folder training 2024. Perlu dicek isinya, lalu #27 bisa ditutup dan dipakai untuk US-52 (template tanggapan) serta US-63 (evaluasi recall).
- **Draft In bersifat internal, padahal AI memakai layanan Google.** Draft yang belum terbit tidak boleh dikirim ke layanan eksternal tanpa izin tertulis mitra (NFR-08). Lapisan data sudah menolaknya secara bawaan (`analysis.ai_allow_internal: false` di `pipeline/hero/analysis/ai.py`), tetapi ini perlu dikonfirmasi ke Pak Faris sebelum data training dipakai di mode AI.
- **Batas pemakaian API kemungkinan penyebab hasil AI tidak stabil.** Dari sisi aplikasi tidak ada pembatasan, sementara akun Google AI Studio punya kuota. Kalau terbukti, perlu antrean atau pembatasan permintaan, dan keputusan memakai tier berbayar.
- **Masukan untuk PM dicatat sebagai perbaikan proses.** Sebelum setiap rapat mitra, PM perlu sesi singkat dengan tiap peran untuk menyiapkan alur demo. Demo sebaiknya memakai data nyata, bukan dummy — ini juga sudah dicatat di Weekly #7.
- **Penjelasan algoritma perlu menjadi bagian keluaran,** bukan hanya bahan jawaban di rapat. Setiap butir ringkasan dan Key Takeaway sebaiknya membawa alasan pemilihannya (pasal sumber dan kategori). Ini sejalan dengan kebutuhan keterlacakan FR-ANL-06.
- **Papan proyek tertinggal dari kondisi nyata.** Laporan uji sudah ada, tetapi statusnya belum dipindah. Perbarui setelah rapat Selasa, sekalian menandai item Sprint 5 yang diturunkan ke Sprint 6.
