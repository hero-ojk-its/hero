# MoM — Weekly Update #9 (Tindak Lanjut MVP 2)

**Tanggal:** Selasa, 10 November 2026 · ± 45 menit · Zoom
**Hadir DPEA:** Pak Faris Budi (Product Owner), Pak Andika Prihandoko (Mentor — bergabung di tengah rapat, dari Surabaya)
**Hadir Tim:** Zaky (PM/BA), Ikhwan (Frontend), Rafli (Backend), Hamdan (Infra/QA)
**Berhalangan:** Fathir (Data/ML) — progres disampaikan Zaky
**Notulis:** Zaky
**Rekaman:** https://youtu.be/adtN_pEjaXI

> Notulen ini mencakup sesi bersama Pak Faris dan Pak Andika sampai keduanya pamit. Diskusi internal tim setelahnya dicatat di [Rangkuman Detail Weekly #9](26-rangkuman-weekly-update-09.md) §8.

---

## 1. Ringkasan singkat

- Tindak lanjut review MVP 2 (Summary & Key Takeaways) dari Weekly #8. Tim mendemokan alur yang sudah diperbarui: unggah → Summary dan Key Takeaways mode Deterministik → *toggle* AI.
- **Proyek *behind schedule*.** Seharusnya minggu ini sudah masuk MVP 3, tetapi MVP 2 belum diterima. Jadwal diperkirakan mundur sekitar satu minggu; minggu depan masih membahas MVP 2.
- **Laporan progres harus apa adanya.** Mulai rapat berikutnya, PM membuka dengan posisi proyek terhadap jadwal dalam 1–2 halaman.
- **Antarmuka harus untuk pengguna non-IT.** Metadata diekstrak otomatis, dan isian yang tidak perlu dihapus (alasan persetujuan, publik/non-publik, persetujuan publikasi).
- **Summary ≠ Analisa.** Summary hanya mengolah dokumen yang diunggah. Analisa memetakan setiap pasal terhadap Knowledge Base dan menjadi MVP 3.
- **Dokumen bertabel** masih menjadi kelemahan utama ringkasan.
- **Link uji coba** disiapkan Rafli bersama Fathir dan diuji internal oleh Hamdan sebelum diserahkan ke DPEA untuk *business acceptance*.
- **Pak Andika:** jangan sampai mundur lebih jauh. Kendala langsung disampaikan di grup atau lewat Zoom tambahan, tanpa menunggu rapat mingguan.

---

## 2. Laporan progres per orang

### Zaky — PM / BA
- Kampus meminta laporan kemajuan proyek tengah semester. Draft sudah disusun dan perlu direview serta ditandatangani Pak Andika selaku mentor industri. Laporan ini juga memuat laporan keuangan untuk reimburse ke kampus.
- Estimasi progres keseluruhan sekitar **40%** (masih di fase 2 dari 5 fase). Ini estimasi lisan, belum dihitung dari *baseline*.
- Menjawab Pak Andika: dosen membolehkan kunjungan tim ke Jakarta, tetapi dana untuk membawa seluruh anggota terbatas.

### Fathir — Data / ML *(disampaikan Zaky)*
- Sinkronisasi sudah disesuaikan dengan alur Summary Dokumen, sehingga tidak lagi menunggu proses manual seperti saat demo Weekly #8.
- **Benchmark singkat model AI:**
  - **Gemini Pro** — paling komprehensif, paling mahal, dan paling lama.
  - **Gemini Flash** — cukup baik, tidak terlalu mahal dan tidak terlalu lama.
  - **Gemini Flash Lite** — paling cepat dan murah, tetapi hasilnya terlalu singkat.
- **Rencana alur:** model dibatasi oleh batas token dan waktu proses. Kalau melewati batas, sistem beralih (*fallback*) ke model yang lebih sederhana dan murah. Batas API mencakup RPM, TPM, dan token per hari.

### Ikhwan — Frontend
- Tampilan sudah diperbarui sesuai revisi Pak Faris di Weekly #8.
- Menambahkan riwayat regulasi yang pernah diunggah, sehingga dokumen yang sama bisa dilihat lagi tanpa unggah ulang.
- Alur dimulai dari Summary dan Key Takeaways mode Deterministik, lalu ada *toggle* untuk mengaktifkan AI.
- Halaman Analisa (perbandingan dengan Knowledge Base) baru gambaran; belum diputuskan apakah perbandingan Deterministik vs AI akan disediakan.

### Rafli — Backend
- **Struktur ringkasan eksekutif:**
  1. Identitas dokumen
  2. Kerangka dokumen (bab, judul, pasal)
  3. Pihak utama
  4. Kewajiban utama
  5. Kewajiban pelaporan
  6. Rujukan pasal sebagai landasan
  7. Sanksi
  8. Pencabutan
  9. Masa berlaku
- **Poin kata kunci (Key Takeaways):** temuan dari pasal-pasal dokumen, diurutkan berdasarkan prioritas 0 sampai 6, dan dikategorikan (sanksi, larangan, perizinan, dan lainnya). Setiap poin menampilkan rujukan pasal beserta isi pasalnya.
- **Analisa terhadap Knowledge Base:** kategori temuan baru, sama, menggantikan / melengkapi, dan konflik. Kemiripan teks sekitar 80% dipakai sebagai salah satu penanda "menggantikan". Dasar hukum tertaut ke Knowledge Base. Tampilan hasil harmonisasi belum diperbarui.
- **Alur AI:** AI tidak mulai dari nol. AI memakai hasil Deterministik sebagai masukan, lalu memeriksa kembali ke dokumen sebagai verifikasi dua langkah.
- Bertanya ke Pak Faris: dokumen contoh punya sekitar 19 pasal dan sekitar 20 temuan, tetapi rencana Fathir hanya menampilkan 10 poin teratas. Sebaiknya semua temuan ditampilkan?

### Hamdan — Infra / QA
- Hasil analisis sudah bisa diperbesar agar lebih mudah dibaca, sesuai permintaan Pak Faris.
- Uji awal dengan dokumen buatan sendiri berisi 10 pasal: hanya sekitar 5 pasal yang ter-*tag*. Setelah diperbaiki bersama Fathir, hasilnya cukup baik.
- **Kendala utama: dokumen bertabel.** Uji dengan dokumen "1 In" sampai "3 In" dari OneDrive menunjukkan dokumen yang banyak pasal masih aman, tetapi dokumen yang banyak tabel ("3 In") menghasilkan ringkasan dan Key Takeaways yang kurang baik.
- Fathir, Rafli, dan Hamdan akan memperbaiki algoritmanya bersama.
- Bertanya ke Pak Faris: alur link uji disiapkan dengan memosisikan beliau sebagai pengguna awam IT? Pak Faris: benar.

---

## 3. Feedback dari mitra

### Dari Pak Faris

**Untuk Zaky — laporan progres dan peran PM:**
- Kirim laporan kemajuan lewat WhatsApp; DPEA akan mempelajari, mereview, dan menandatanganinya.
- Laporkan kondisi apa adanya. Posisi sekarang: seharusnya sudah masuk MVP 3, tetapi MVP 2 belum diterima. Sampaikan jadwal, revisi jadwal, dan penyesuaiannya sampai akhir Desember.
- **Mulai Selasa depan**, PM lebih percaya diri mempresentasikan. Selalu buka dengan posisi proyek: *behind schedule*, sesuai jadwal, atau lebih cepat. Tampilan papan kanban terlalu teknis bagi DPEA.
- Siapkan **satu dek 1–2 halaman** berisi tabel ringkas: berapa persen selesai, berapa yang tertunda, pekerjaan berikutnya, dan pekerjaan yang sudah ditarik lebih awal — beserta implikasi dan langkah percepatannya.
- **Alasannya:** di proyek nyata yang dihitung per *man-days*, setiap MVP yang mundur membuat klien harus mengeluarkan anggaran tambahan. Karena itu PM harus menyampaikan posisi sejak awal.

**Untuk Ikhwan — antarmuka:**
- **Metadata otomatis.** Judul, nomor, jenis regulasi, dan sektor harus langsung keluar setelah draft diunggah, bukan diisi pengguna. Draft peraturan selalu punya *header*, dan isian bebas berisiko menyesatkan — misalnya peraturan tentang aset kripto malah ditandai "pasar modal". Pilihannya: isi otomatis, atau sederhanakan dengan tidak menampilkannya.
- **Hapus isian yang tidak perlu:**
  - Alasan persetujuan.
  - Publik / non-publik — semua draft peraturan pasti non-publik dan hanya untuk kalangan internal.
  - Persetujuan publikasi.
- **Prinsip UI/UX:** rancang untuk pengguna non-IT. UI yang baik tidak perlu dibaca petunjuknya; pengguna langsung tahu harus berbuat apa. Uji ke orang di luar IT — misalnya ibu kos — apakah mereka paham.
- Halaman Analisa yang sangat detail itu terlalu ramai. Untuk sekarang, fokus MVP 2: Summary.
- **Posisi *toggle* AI** (menjawab Ikhwan): diskusikan di internal. Untuk Summary, *toggle* di depan memungkinkan, karena hanya mengolah satu dokumen lokal — 50 halaman diringkas tanpa dibandingkan dengan dokumen lain. Tetapi untuk Analisa, kalau AI dipakai sejak awal, membandingkan dengan ribuan halaman Knowledge Base akan menghabiskan token. Coba keduanya dan rasakan mana yang lebih masuk dari sisi pengalaman pengguna.
- **Hasil Analisa (MVP 3)** (menjawab Ikhwan): langkah pertama adalah pemetaan pasal per pasal — pasal mana yang baru, mana yang pernah dibahas peraturan sebelumnya di Knowledge Base, dan mana yang sudah tidak berlaku atau digantikan. Tujuan akhirnya seperti dokumen **Out** di data training. Out adalah *shortlist* yang sudah disaring dari *longlist*.

**Untuk Fathir dan Rafli — model AI:**
- Di DPEA, saat menyusun algoritma, dipakai model terbaik yang tersedia. Saat produksi, dipakai model yang lebih rendah dan lebih murah, karena *pre-processing*-nya sudah kuat sehingga tidak boros token.
- Tim boleh memakai model bagus saat pengembangan, tetapi saat di-*deploy* ke VPS harus memakai Gemini. Pertimbangkan hal itu.

**Untuk Rafli — jumlah Key Takeaways:**
- Belum bisa menjawab apakah semua temuan perlu ditampilkan; Pak Faris harus membaca dokumennya dulu.
- **Cara kerja DPEA:** peraturan 50 halaman dibaca sekilas dulu untuk tahu bahasannya, latar belakangnya, dan strukturnya. Lalu dipilih bagian yang terkait TI — pelaporan online, pertukaran data, penggunaan aplikasi, kewajiban pelaporan. Setelah itu baru dibuat ringkasan kecil: "yang terkait teknologi adalah ini, ini, dan ini."

**Untuk Rafli dan Hamdan — link uji coba:**
- Siapkan link pengujian dari awal sampai Summary dan Key Takeaways. Pak Faris akan mencoba sendiri dan mencatat pertanyaannya untuk diklarifikasi.
- **Rafli** berkoordinasi dengan Fathir agar link bisa diakses DPEA.
- **Hamdan** sebagai QA bertanggung jawab atas berjalannya fungsi aplikasi sebelum link diserahkan ke Pak Faris dan Pak Andika. Periksa:
  - Analisis AI bisa dijalankan dengan lancar.
  - Unggah berbagai jenis dokumen, termasuk gambar.
  - Peringatan galat berfungsi.
  - Unggah dokumen yang sudah ada memunculkan peringatan duplikat.
  - Ada pembedaan antara dokumen yang masuk Knowledge Base dan dokumen yang hanya dicek.
- Setelah semua lolos, DPEA menguji dari sisi bisnis: sudah sesuai kebutuhan atau belum.

**Penutup:**
- Ramaikan lagi grup WhatsApp. Kendala langsung didiskusikan, tidak perlu menunggu progres mingguan — selagi *business owner*-nya masih orang IT.

### Dari Pak Andika

- Masukan dari mitra bukan untuk memperlambat, tetapi untuk membangun *sense* kerja di dunia nyata. Tim sudah proaktif.
- Hal teknis yang kurang jelas langsung disampaikan di grup. Kalau perlu Zoom, tidak usah menunggu jadwal mingguan.
- Kalau ada perbedaan pendapat di internal, putuskan cepat lewat Zaky sebagai PM.
- Mencari model yang sempurna sulit karena kebutuhan terus berkembang. Kalau ada yang bisa diuji, segera sampaikan.
- **Kalau bisa, jangan mundur.** Kalau perlu negosiasi percepatan, sampaikan; mitra akan berusaha membantu.
- **Kendala non-teknis:** Pak Andika menawarkan bantuan anggaran. Selain ke Jakarta, pertemuan di Surabaya juga memungkinkan asal ada undangan; anggarannya bisa diusahakan lewat Pak Dwi. Pak Dwi juga pernah ingin proyek Capstone ini ditampilkan di majalah dinding OJK — dikoordinasikan dengan Pak Faiz.
- Menanyakan progres keseluruhan. Dijawab Zaky sekitar 40%. Menurut Pak Andika, di atas 40% masih aman untuk dikejar.
- Minta dikabari kalau aplikasi sudah siap didemokan; beliau akan ikut.

---

## 4. Keputusan

1. Fokus masih menyelesaikan MVP 2 (Summary & Key Takeaways). Jadwal MVP 3 diperkirakan mundur sekitar satu minggu.
2. Laporan progres disampaikan apa adanya. Mulai rapat berikutnya, PM membuka dengan posisi terhadap jadwal dalam dek 1–2 halaman.
3. Metadata dokumen diekstrak otomatis. Isian alasan persetujuan, publik/non-publik, dan persetujuan publikasi dihapus.
4. Summary hanya mengolah dokumen yang diunggah. Analisa memetakan pasal per pasal terhadap Knowledge Base (MVP 3).
5. Posisi *toggle* AI untuk Summary diputuskan tim lewat uji pengalaman pengguna. Untuk Analisa, Deterministik tetap menyaring lebih dulu.
6. Link uji coba diuji internal oleh QA sebelum diserahkan ke DPEA untuk *business acceptance*.
7. Kendala disampaikan langsung lewat WhatsApp atau Zoom tambahan; perbedaan pendapat internal diputuskan PM.
8. Rapat berikutnya: Selasa, 17 November 2026.

---

## 5. Action item

### Zaky
- [ ] Kirim laporan kemajuan ke Pak Faris lewat WhatsApp untuk direview dan ditandatangani
- [ ] Siapkan dek 1–2 halaman untuk 17 Nov: posisi terhadap jadwal, % selesai / tertunda / berikutnya, revisi jadwal, dan rencana percepatan sampai akhir Desember
- [ ] Putuskan perbedaan pendapat internal soal alur Summary dan posisi *toggle* AI
- [ ] Koordinasikan undangan Pak Dwi / Pak Andika ke kampus dan rencana majalah dinding OJK dengan Pak Faiz

### Ikhwan
- [ ] Metadata otomatis setelah unggah; hapus isian alasan persetujuan, publik/non-publik, dan persetujuan publikasi
- [ ] Sederhanakan layar Summary untuk pengguna non-IT; uji ke orang di luar IT
- [ ] Uji dua posisi *toggle* AI di Summary (di depan dan setelah hasil Deterministik)

### Rafli
- [ ] Siapkan link uji coba bersama Fathir
- [ ] Dokumentasikan cara kerja ringkasan dan poin kata kunci untuk menjawab pertanyaan DPEA
- [ ] Siapkan pemetaan pasal per pasal (baru / pernah dibahas / tidak berlaku / digantikan) untuk MVP 3

### Fathir *(tidak hadir — disampaikan lewat Zaky)*
- [ ] Perbaiki ringkasan untuk dokumen bertabel, bersama Rafli dan Hamdan
- [ ] Lanjutkan evaluasi model dan mekanisme *fallback* terhadap batas API
- [ ] Bantu Rafli menyiapkan link uji coba

### Hamdan
- [ ] QA alur dari unggah sampai Summary dan Key Takeaways sebelum link diserahkan: AI, berbagai jenis dokumen termasuk gambar, peringatan galat, peringatan duplikat, pemisahan dokumen KB vs dokumen yang hanya dicek
- [ ] Uji dokumen bertabel ("3 In") setelah perbaikan algoritma

### Mitra
- [ ] Pak Faris / Pak Andika: review dan tanda tangan laporan kemajuan
- [ ] Pak Faris: uji link setelah lolos QA internal; catat pertanyaan untuk diklarifikasi
- [ ] Pak Faris: putuskan jumlah Key Takeaways yang ditampilkan setelah membaca dokumen contoh
- [ ] Pak Faris / Pak Andika: akses OneDrive (#112), angka *ground truth* (#87), tanda tangan PRD (#45) — masih ditunggu

---

## 6. Catatan dari sisi PM

- **Konflik antara "semua draft non-publik" dan mode AI.** Pak Faris menegaskan semua draft peraturan bersifat internal. Lapisan data secara bawaan menolak mengirim dokumen non-publik ke layanan eksternal (`analysis.ai_allow_internal: false`), sedangkan model yang dipakai adalah Gemini milik Google. Artinya, mode AI untuk draft tidak akan pernah jalan kecuali Pak Faris memberi izin tertulis (NFR-08) atau model dijalankan di server sendiri. Ini perlu ditanyakan sebelum tim menghabiskan waktu menyempurnakan alur AI. Bisa jadi ini juga penyebab "alih otomatis ke Deterministik" yang dibahas di Weekly #8.
- **Arahan *toggle* AI melunak dari Weekly #8.** Di Weekly #8 Pak Faris meminta tidak ada pilihan mode di awal. Kali ini untuk Summary beliau membolehkan *toggle* di depan, karena hanya satu dokumen yang diolah. Prinsip "Deterministik dulu" tetap wajib untuk Analisa. Catat sebagai keputusan desain setelah tim mencoba keduanya.
- **Angka 40% perlu dasar.** Estimasi lisan mudah dipertanyakan. Untuk dek 17 Nov, hitung dari papan proyek: story point selesai dibagi total, ditambah posisi tiap MVP terhadap tenggatnya. Papan perlu diperbarui dulu, karena di Weekly #8 statusnya tertinggal dari kondisi nyata.
- **Dokumen bertabel adalah risiko lintas fase.** Dokumen yang gagal diringkas dengan baik ("3 In") berasal dari data training, dan data itu juga dipakai untuk Fase 3–4 serta UAT. Perlu dicek berapa banyak dokumen training yang bertabel. Kalau banyak, ekstraksi tabel perlu story tersendiri, bukan hanya ditambal di algoritma ringkasan.
- **Jumlah Key Takeaways menunggu PO.** Sambil menunggu, opsi yang aman: tampilkan semua temuan dikelompokkan per prioritas, dengan 10 teratas terbuka secara bawaan. Dengan begitu tidak ada temuan yang hilang dan tampilan tetap ringkas.
- **Pemisahan dokumen KB vs dokumen yang hanya dicek sudah ada di backend.** Unggahan Analisa memakai peran `draft_kajian` (US-15a). QA tinggal membuktikannya, dan isian publik/non-publik di layar bisa dihapus tanpa mengubah perilaku itu.
