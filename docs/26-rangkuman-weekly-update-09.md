# Rangkuman Detail — Weekly Update #9

**Tanggal:** Selasa, 10 November 2026 · Zoom
**Topik utama:** evaluasi MVP 2 (Summary & Key Takeaways), kesiapan pengujian, dan penyesuaian jadwal
**Rekaman:** https://youtu.be/adtN_pEjaXI
**Notulen resmi:** [MoM Weekly Update #9](25-mom-weekly-update-09.md)

> Dokumen ini merangkum seluruh pembahasan per topik, bukan per peran, dan bukan transkrip verbatim. Diskusi internal tim setelah mitra pamit dipisahkan di §8 dan bukan keputusan bersama mitra. Beberapa bagian transkrip otomatis kurang jelas; informasi yang tidak bisa dipastikan tidak dicatat sebagai fakta.

---

## Daftar Isi

1. [Konteks dan Peserta](#1-konteks-dan-peserta)
2. [Status Proyek dan Pelaporan](#2-status-proyek-dan-pelaporan)
3. [Update Implementasi MVP 2](#3-update-implementasi-mvp-2)
4. [Klarifikasi Kebutuhan dari DPEA](#4-klarifikasi-kebutuhan-dari-dpea)
5. [Rencana Pengujian End-to-End](#5-rencana-pengujian-end-to-end)
6. [Timeline dan Dampak ke Fase Berikutnya](#6-timeline-dan-dampak-ke-fase-berikutnya)
7. [Arahan dan Ekspektasi Mitra](#7-arahan-dan-ekspektasi-mitra)
8. [Diskusi Internal Setelah Rapat](#8-diskusi-internal-setelah-rapat)
9. [Daftar Tindak Lanjut](#9-daftar-tindak-lanjut)
10. [Risiko, Isu, dan Hal yang Belum Diputuskan](#10-risiko-isu-dan-hal-yang-belum-diputuskan)
11. [Kesimpulan](#11-kesimpulan)

---

## 1. Konteks dan Peserta

Rapat ini menindaklanjuti review MVP 2 di Weekly #8 (9 Nov). Pembahasannya mencakup demo aplikasi, penjelasan alur pemrosesan, hasil pengujian, masukan UI/UX, dan kesiapan aplikasi untuk diuji DPEA. Pak Faris membatasi sesi sampai pukul 14.30 karena ada agenda lain.

| Pihak | Peserta |
| --- | --- |
| DPEA | Pak Faris Budi — Product Owner |
| DPEA | Pak Andika Prihandoko — Mentor industri; sedang dinas di Surabaya, bergabung di tengah rapat |
| Tim HERO | Zaky (PM/BA), Ikhwan (Frontend), Rafli (Backend), Hamdan (Infra/QA) |
| Berhalangan | Fathir (Data/ML) — progresnya disampaikan Zaky |

---

## 2. Status Proyek dan Pelaporan

### 2.1. Laporan kemajuan untuk kampus

- Kampus meminta laporan kemajuan proyek Capstone tengah semester.
- Draft sudah disusun dari perkembangan terbaru dan perlu direview mentor industri.
- Laporan ini juga memuat laporan keuangan untuk reimburse ke kampus.
- Dokumennya membutuhkan tanda tangan Pak Andika selaku mentor industri.

### 2.2. Kondisi progres

- Tim masih di MVP / fase 2 dari total 5 fase.
- Ditanya Pak Andika soal persentase progres, Zaky menyebut sekitar 40–45%, lalu mengoreksi menjadi sekitar **40%**. Angka ini estimasi lisan, bukan hasil hitungan *baseline*.
- Secara jadwal, minggu ini seharusnya sudah masuk MVP 3, tetapi MVP 2 belum selesai dan belum diterima Product Owner.
- Menurut Pak Andika, kalau progres di atas 40% masih aman untuk dikejar.

### 2.3. Format pelaporan yang diminta Pak Faris

- Tidak terlalu teknis dan mudah dipahami stakeholder. Tampilan papan kanban dinilai terlalu teknis.
- Selalu dibuka dengan posisi proyek: *behind schedule*, sesuai jadwal, atau lebih cepat.
- Memuat persentase pekerjaan yang selesai, yang tertunda, dan yang berikutnya, termasuk pekerjaan yang sudah ditarik lebih awal.
- Menjelaskan dampak keterlambatan terhadap jadwal akhir dan langkah percepatannya sampai akhir Desember.
- Disajikan sebagai tabel ringkas atau dek 1–2 halaman, mulai rapat Selasa berikutnya.

**Alasannya:** di proyek nyata yang dihitung per *man-days*, setiap MVP yang mundur membuat klien harus mengeluarkan anggaran tambahan. Karena itu PM harus menyampaikan posisi proyek sejak awal, apa adanya.

Laporan kemajuan dikirim Zaky lewat WhatsApp; DPEA akan mempelajari, mereview, dan menandatanganinya.

---

## 3. Update Implementasi MVP 2

### 3.1. Data/ML — sinkronisasi dan model AI *(disampaikan Zaky)*

- Sinkronisasi sudah disesuaikan dengan alur Summary Dokumen, sehingga tidak lagi menunggu proses manual seperti saat demo Weekly #8.
- Benchmark singkat model yang dilakukan Fathir:

  | Model | Hasil pengamatan |
  | --- | --- |
  | Gemini Pro | Paling komprehensif, tetapi paling mahal dan paling lama |
  | Gemini Flash | Cukup baik; tidak terlalu mahal dan tidak terlalu lama |
  | Gemini Flash Lite | Paling cepat dan murah, tetapi hasilnya terlalu singkat |

  > Nomor versi model di transkrip tidak jelas, sehingga tidak dicantumkan. Perlu dicek ke konfigurasi yang benar-benar dipakai.

- Rencana alur: pemakaian model dibatasi batas token dan waktu proses. Kalau melewati batas, sistem beralih ke model yang lebih sederhana dan murah.
- Batas API mencakup RPM (*requests per minute*), TPM (*tokens per minute*), dan batas token per hari.

### 3.2. Frontend dan alur pengguna

Ikhwan mendemokan tampilan yang sudah diperbarui sesuai revisi Weekly #8:

- Unggah dokumen PDF.
- Riwayat regulasi yang pernah diunggah, sehingga dokumen yang sama bisa dilihat lagi tanpa unggah ulang.
- Summary dan Key Takeaways mode Deterministik sebagai hasil awal.
- *Toggle* untuk mengaktifkan AI pada hasil.
- Halaman lanjutan ke Analisa (perbandingan dengan Knowledge Base) sebagai gambaran; belum diputuskan apakah perbandingan Deterministik vs AI akan disediakan.

Hamdan juga menambahkan: hasil analisis sekarang bisa diperbesar agar lebih mudah dibaca, sesuai permintaan Pak Faris.

### 3.3. Backend — struktur hasil Summary

Rafli menjelaskan struktur ringkasan eksekutif, yang mengikuti templat dari sisi Data/ML:

1. **Identitas dokumen** yang diunggah
2. **Kerangka dokumen** — bab, judul, dan pasal
3. **Pihak utama** — subjek yang terkait ketentuan
4. **Kewajiban utama** dari naskah regulasi
5. **Kewajiban pelaporan**
6. **Rujukan pasal** sebagai landasan setiap temuan
7. **Sanksi**
8. **Pencabutan**
9. **Masa berlaku**

**Key Takeaways (poin kata kunci):**

- Temuan dari pasal-pasal dokumen, diurutkan berdasarkan prioritas 0 sampai 6.
- Dikategorikan, misalnya sanksi, larangan, perizinan, dan lainnya.
- Setiap poin menampilkan rujukan pasal beserta isi pasalnya sebagai bukti.

**Alur AI-Assisted:**

1. Sistem menjalankan proses Deterministik lebih dulu.
2. Hasil Deterministik menjadi masukan bagi AI.
3. AI menganalisis dan memperkaya hasil tersebut.
4. Sistem memeriksa kembali ke dokumen sebagai verifikasi dua langkah.

Jadi AI tidak membangun hasil dari nol, melainkan memperkaya dan memeriksa hasil awal.

### 3.4. Backend — perbandingan dengan Knowledge Base

Kategori hasil perbandingan yang didemokan:

| Kategori | Arti |
| --- | --- |
| Baru | Pasal terdeteksi sebagai ketentuan baru |
| Sama | Pasal sudah ada atau menduplikasi pasal di Knowledge Base |
| Menggantikan / melengkapi | Pasal memperbarui pasal yang sudah ada |
| Konflik | Pasal bertentangan dengan ketentuan yang sudah ada |

- Kemiripan teks sekitar **80%** dipakai sebagai salah satu penanda "menggantikan". Angka ini gambaran mekanisme yang sedang dipakai, bukan standar yang disepakati mitra.
- Dasar hukum tertaut ke Knowledge Base.
- Tampilan hasil harmonisasi belum diperbarui. Bagian ini gambaran MVP 3, bukan fokus MVP 2.

### 3.5. Pengujian dan kualitas dokumen

Hamdan menyampaikan hasil pengujian ekstraksi dan ringkasan:

- Uji awal dengan dokumen buatan sendiri berisi 10 pasal: hanya sekitar 5 pasal yang ter-*tag*. Temuan ini diteruskan ke Fathir, dan setelah diperbaiki hasilnya cukup baik.
- Dokumen yang berbasis pasal dan ayat relatif mudah diproses.
- **Dokumen bertabel masih menjadi kendala utama.** Uji memakai dokumen "1 In" sampai "3 In" dari OneDrive. "1 In" yang banyak pasal masih aman, tetapi "3 In" yang banyak tabel menghasilkan ringkasan dan Key Takeaways yang kurang baik.
- Fathir, Rafli, dan Hamdan akan memperbaiki algoritmanya bersama.

**Perbaikan yang dibutuhkan:**

- Kemampuan membaca isi tabel.
- Pengujian dengan variasi struktur dokumen, bukan hanya dokumen yang dominan pasal dan ayat.
- Pemeriksaan apakah semua ketentuan penting berhasil diekstrak.
- Ringkasan tidak kehilangan konteks pada dokumen yang strukturnya kompleks.

---

## 4. Klarifikasi Kebutuhan dari DPEA

### 4.1. Cara kerja DPEA membaca regulasi

Menurut Pak Faris, pengguna tidak langsung mencari ketentuan TI. Urutannya:

1. Membaca sekilas seluruh regulasi, misalnya 50 halaman.
2. Memahami bahasannya, latar belakangnya, dan strukturnya.
3. Menandai bagian yang terkait lingkup kerja DPEA.
4. Menyaring ketentuan yang relevan.
5. Menyusun ringkasan kecil: "yang terkait teknologi adalah ini, ini, dan ini."

Contoh hal yang dicari dari sisi TI: pelaporan online, pertukaran data, penggunaan aplikasi, dan kewajiban pelaporan.

Jadi ringkasan yang diharapkan bukan salinan isi regulasi, tetapi membantu pengguna memahami dokumen dan menemukan bagian yang relevan.

### 4.2. Perbedaan Summary dan Analisa

| Aspek | Summary | Analisa |
| --- | --- | --- |
| Fokus | Memahami satu dokumen yang diunggah | Membandingkan ketentuan dokumen dengan regulasi di Knowledge Base |
| Sumber | Dokumen yang diunggah saja | Dokumen yang diunggah dan Knowledge Base |
| Tujuan | Gambaran isi dan poin penting | Hubungan setiap pasal dengan regulasi yang ada |
| Kebutuhan Knowledge Base | Tidak perlu | Knowledge Base sebagai pembanding |
| Tahap proyek | MVP 2 | MVP 3 |

Summary dokumen 50 halaman cukup mengolah 50 halaman itu, tanpa membandingkan dengan dokumen lain.

### 4.3. Analisa harus memetakan pasal per pasal

Untuk Analisa (MVP 3), langkah pertama adalah memetakan setiap pasal — misalnya satu halaman berisi 10 pasal:

- Pasal mana yang baru.
- Pasal mana yang sudah pernah dibahas peraturan sebelumnya di Knowledge Base.
- Pasal mana yang sudah tidak berlaku atau digantikan.

Pemetaan dilakukan sampai tingkat pasal, bukan perbandingan dokumen secara umum.

### 4.4. Hubungan In dan Out dari DPEA

- Tujuan akhir Analisa: draft diunggah, dan hasilnya mendekati dokumen **Out** di data training — tanggapan yang biasa dituangkan DPEA dalam catatan dinas.
- Out bukan daftar seluruh temuan mentah, melainkan *shortlist* yang sudah disaring dari *longlist*.
- Tim perlu memahami proses penyaringan dari daftar temuan awal menjadi hasil yang relevan bagi pengguna.

### 4.5. Jumlah Key Takeaways

- Rafli bertanya: dokumen contoh punya sekitar 19 pasal dan sekitar 20 temuan, tetapi rencana Fathir hanya menampilkan 10 poin teratas. Sebaiknya semua ditampilkan?
- Pak Faris belum bisa memutuskan, karena harus membaca dokumennya dulu.
- Keputusan menunggu peninjauan dokumen dan contoh hasil yang lebih konkret.

### 4.6. Metadata dan isian di layar unggah

- Judul, nomor, jenis regulasi, dan sektor harus langsung keluar setelah draft diunggah, bukan diisi pengguna. Draft peraturan selalu punya *header*.
- Isian bebas dari pengguna berisiko menyesatkan, misalnya peraturan tentang aset kripto malah ditandai "pasar modal".
- Pilihannya: isi otomatis, atau sederhanakan dengan tidak menampilkannya.
- Isian yang tidak diperlukan:
  - **Alasan persetujuan.**
  - **Publik / non-publik** — semua draft peraturan pasti non-publik dan hanya untuk kalangan internal.
  - **Persetujuan publikasi.**

---

## 5. Rencana Pengujian End-to-End

### 5.1. Alur pengujian

1. Rafli berkoordinasi dengan Fathir menyiapkan link aplikasi yang bisa diakses DPEA.
2. Hamdan menjalankan QA internal sebelum link diserahkan.
3. Setelah siap, link diserahkan ke Pak Faris dan Pak Andika.
4. DPEA menguji dari sisi kebutuhan bisnis (*business acceptance*).
5. Pertanyaan dan temuan DPEA dicatat untuk diklarifikasi dan diperbaiki tim.

Alur uji disiapkan dengan memosisikan Pak Faris sebagai pengguna awam IT (dikonfirmasi beliau saat menjawab Hamdan).

### 5.2. Hal yang harus diperiksa QA sebelum link diserahkan

| Area | Yang diperiksa |
| --- | --- |
| Akses | Link bisa dibuka dan dipakai penguji |
| Unggah dokumen | Berbagai jenis dokumen bisa diunggah dan diproses, termasuk gambar |
| Summary | Ringkasan dihasilkan dari dokumen yang diunggah |
| Key Takeaways | Poin penting tampil jelas dan relevan |
| Aksi AI | Analisis AI berjalan lancar |
| Peringatan galat | Pesan galat muncul dengan benar |
| Unggah duplikat | Ada peringatan saat dokumen yang sama diunggah lagi |
| Knowledge Base | Dokumen yang masuk Knowledge Base dibedakan dari dokumen yang hanya dicek |
| Stabilitas | Tidak ada *loading* tanpa akhir atau kegagalan yang menghambat pengguna |
| Pengalaman pengguna | Alur mudah dipahami pengguna non-IT |

### 5.3. Pembagian tanggung jawab

- **Rafli:** koordinasi dengan Fathir untuk menyiapkan link pengujian.
- **Fathir:** kesiapan pipeline dan model.
- **Hamdan:** QA dan berjalannya fungsi aplikasi sebelum link diserahkan.
- **Pak Faris dan Pak Andika:** pengujian dari sisi pengguna dan bisnis setelah tim menyatakan siap.

---

## 6. Timeline dan Dampak ke Fase Berikutnya

- Rencana awal: minggu ini mulai MVP 3.
- MVP 2 masih membutuhkan perbaikan berdasarkan demo dan masukan mitra.
- Pak Faris memperkirakan jadwal mundur sekitar **satu minggu**; minggu depan masih membahas MVP 2 — ringkasan, Key Takeaways, dan perbaikan UI.
- Pak Andika meminta tim berusaha agar keterlambatan tidak melebar. Kalau perlu negosiasi percepatan, mitra akan membantu.

**Implikasi:**

- Zaky mencatat keterlambatan secara transparan di laporan rutin.
- Tim menyusun revisi jadwal dan menjelaskan cara mengejar target sampai akhir Desember.
- Percepatan harus konkret, bukan sekadar memindahkan tanggal target.

> **Status:** pergeseran sekitar satu minggu adalah perkiraan dalam rapat. Revisi jadwal terperinci dan rencana percepatan belum ditetapkan.

---

## 7. Arahan dan Ekspektasi Mitra

### 7.1. Arahan Pak Faris

- Laporan progres disampaikan sesuai kondisi aktual, dan setiap rapat dibuka dengan posisi proyek terhadap jadwal.
- Informasi untuk stakeholder ringkas dan tidak terlalu teknis.
- **Prinsip UI/UX:** aplikasi dirancang untuk pengguna non-IT. UI yang baik tidak perlu dibaca petunjuknya — pengguna langsung tahu harus berbuat apa. Uji ke orang di luar IT, misalnya ibu kos.
- Halaman Analisa yang sangat detail terlalu ramai; untuk sekarang fokus MVP 2: Summary.
- **Posisi *toggle* AI:** diskusikan di internal. Untuk Summary, *toggle* di depan memungkinkan karena hanya satu dokumen lokal yang diolah. Untuk Analisa, AI sejak awal akan menghabiskan token saat membandingkan dengan ribuan halaman Knowledge Base, jadi Deterministik menyaring lebih dulu. Coba keduanya dan rasakan mana yang lebih masuk.
- **Pemilihan model:** di DPEA, model terbaik dipakai saat menyusun algoritma. Saat produksi dipakai model yang lebih murah, karena *pre-processing*-nya sudah kuat. Saat di-*deploy* ke VPS, tim harus memakai Gemini.
- Pengujian internal dilakukan sebelum aplikasi diserahkan ke DPEA. Pertanyaan dari pengujian DPEA akan disampaikan ke tim untuk diklarifikasi.
- Kendala tidak perlu menunggu rapat mingguan; langsung diskusikan di grup WhatsApp, selagi *business owner*-nya masih orang IT.

### 7.2. Arahan Pak Andika

- Masukan mentor bukan untuk memperlambat, tetapi untuk membangun *sense* kerja di dunia nyata. Tim sudah proaktif.
- Kendala dan hal teknis yang kurang jelas langsung disampaikan di grup; Zoom tambahan bisa diadakan kapan saja.
- Perbedaan pendapat internal diputuskan cepat lewat Zaky sebagai PM.
- Model yang sempurna sulit dicari karena kebutuhan terus berkembang. Kalau ada yang bisa diuji, segera sampaikan.
- Kalau bisa, jangan mundur. Kalau perlu negosiasi percepatan, sampaikan.
- Minta dikabari kalau aplikasi sudah siap didemokan; beliau akan ikut.

### 7.3. Pendanaan dan rencana pertemuan

- Pak Andika menanyakan kendala non-teknis, termasuk anggaran.
- Zaky: pendanaan proyek sudah beres, tetapi undangan ke Jakarta dari Pak Andika terkendala dana untuk membawa seluruh anggota tim, meski dosen membolehkan.
- Pak Andika: pertemuan di Surabaya juga memungkinkan asal ada undangan; anggarannya bisa diusahakan lewat Pak Dwi, yang juga bisa diundang ke kampus.
- Pak Dwi pernah ingin proyek Capstone ini ditampilkan di majalah dinding OJK; akan dikoordinasikan dengan Pak Faiz.
- Belum ada tanggal atau agenda resmi yang diputuskan.

---

## 8. Diskusi Internal Setelah Rapat

> Bagian ini adalah pembicaraan tim setelah mitra pamit. Isinya bukan keputusan resmi bersama mitra.

### 8.1. Lingkungan uji terpisah untuk mitra

- Tim khawatir aplikasi yang sedang diuji DPEA terganggu ketika tim melakukan *pull request* dan *deployment* di lingkungan yang sama.
- Ikhwan mengusulkan web khusus untuk pengujian mitra, dengan fungsi yang sama tetapi tidak terkena perubahan harian. Contohnya: kalau Pak Faris menguji hari Kamis saat ada pembaruan, aplikasi bisa error.
- Zaky menyebut aplikasi di Vercel sejak awal memang dimaksudkan sebagai *staging*.
- Belum ada keputusan.

### 8.2. Posisi *toggle* AI

- Summary boleh memakai AI sejak awal karena lingkupnya hanya dokumen yang diproses.
- Analisa memakai Knowledge Base yang jauh lebih besar, sehingga AI sejak awal akan menghabiskan token. *Toggle* untuk Analisa perlu dipisahkan.
- Tim sepakat posisi *toggle* perlu difinalisasi agar tidak membingungkan pengguna maupun implementasi.

### 8.3. Target fitur yang kurang jelas

- Ikhwan menyampaikan bahwa sebelumnya tim berbeda pemahaman soal keluaran yang harus ditampilkan, karena belum ada *blueprint* atau gambaran hasil yang jelas.
- Setelah penjelasan Pak Faris, gambarannya lebih konkret: prioritas Analisa adalah mengidentifikasi pasal yang baru, sama, menggantikan, atau tidak berlaku.
- Ikhwan akan menghapus elemen visual yang terlalu "bernuansa AI" (misalnya ikon bintang) dari tampilan.

### 8.4. Jumlah poin yang ditampilkan

- Sistem bisa menemukan lebih dari 10 poin, tetapi rencana Fathir mengunci 10 poin teratas.
- Membatasi 10 poin berisiko menyembunyikan temuan; menampilkan semua berisiko terlalu panjang.
- Belum ada keputusan; tim perlu menguji pendekatan penyaringan dan meminta konfirmasi mitra.

### 8.5. Kualitas dokumen uji

- Tabel di dokumen "3 In" ternyata berbentuk gambar, sehingga algoritma gagal membacanya.
- Rafli mencatat bahwa sejauh ini tim kebanyakan menguji dokumen publik; dokumen internal belum banyak diuji.

### 8.6. Koordinasi lanjutan

- Tim ingin mengadakan sesi tambahan (Rabu atau Kamis) untuk membahas percepatan.
- Waktunya menyesuaikan ketersediaan anggota, terutama Fathir yang sambil bekerja.

---

## 9. Daftar Tindak Lanjut

Status belum dianggap selesai sampai ada konfirmasi dari PIC.

### Zaky — PM / BA
- [ ] Kirim draft laporan kemajuan ke Pak Faris lewat WhatsApp untuk direview dan ditandatangani
- [ ] Siapkan dek 1–2 halaman untuk rapat Selasa berikutnya: posisi terhadap jadwal, progres, pekerjaan tertunda, revisi jadwal, dan rencana percepatan sampai akhir Desember
- [ ] Putuskan perbedaan pendapat internal soal alur Summary dan posisi *toggle* AI
- [ ] Atur sesi koordinasi tambahan untuk membahas percepatan
- [ ] Koordinasikan rencana pertemuan dengan Pak Dwi / Pak Andika dan majalah dinding OJK dengan Pak Faiz

### Ikhwan — Frontend
- [ ] Ekstraksi metadata otomatis setelah unggah, atau sembunyikan isian metadata
- [ ] Hapus isian alasan persetujuan, publik/non-publik, dan persetujuan publikasi
- [ ] Sederhanakan layar Summary untuk pengguna non-IT dan uji ke orang di luar IT
- [ ] Uji dua posisi *toggle* AI di Summary
- [ ] Hapus elemen visual yang terlalu "bernuansa AI"

### Rafli — Backend
- [ ] Siapkan link uji coba bersama Fathir
- [ ] Dokumentasikan cara kerja ringkasan dan poin kata kunci, termasuk alasan suatu pasal dipilih
- [ ] Siapkan pemetaan pasal per pasal untuk MVP 3
- [ ] Pastikan peringatan duplikat dan pemisahan dokumen KB vs dokumen yang hanya dicek berjalan

### Fathir — Data / ML
- [ ] Perbaiki ringkasan untuk dokumen bertabel, termasuk tabel berbentuk gambar
- [ ] Lanjutkan evaluasi model dari sisi kualitas, waktu, biaya, dan batas API; siapkan alasan pemilihan model
- [ ] Tinjau mekanisme *fallback* ketika batas API tercapai
- [ ] Bantu Rafli menyiapkan link uji coba

### Hamdan — Infra / QA
- [ ] QA alur dari unggah sampai Summary dan Key Takeaways, mengikuti daftar di §5.2
- [ ] Uji variasi dokumen, terutama dokumen bertabel dan dokumen internal
- [ ] Laporkan temuan uji ke tim sebelum link diserahkan ke DPEA

### Mitra
- [ ] Pak Faris / Pak Andika: review dan tanda tangan laporan kemajuan
- [ ] Pak Faris: uji link setelah lolos QA internal, lalu catat pertanyaannya
- [ ] Pak Faris: putuskan jumlah Key Takeaways setelah membaca dokumen contoh

---

## 10. Risiko, Isu, dan Hal yang Belum Diputuskan

| No. | Isu | Dampak | Status |
| --- | --- | --- | --- |
| 1 | MVP 2 belum diterima | Memundurkan MVP 3 dan jadwal keseluruhan | Perlu diselesaikan dan dievaluasi ulang |
| 2 | Dokumen bertabel sulit diproses, termasuk tabel berbentuk gambar | Summary dan Key Takeaways tidak lengkap atau kurang akurat | Perlu perbaikan dan pengujian |
| 3 | UI masih terlalu kompleks | Pengguna non-IT kesulitan memahami alur | Perlu disederhanakan |
| 4 | Batas Summary dan Analisa belum dipahami semua anggota | Implementasi dan UI tidak konsisten | Perlu penyelarasan internal |
| 5 | Posisi *toggle* AI belum final | Memengaruhi alur pengguna dan konsumsi token | Belum diputuskan |
| 6 | Pemilihan model AI | Kualitas, biaya, kecepatan, dan batas API harus diseimbangkan | Perlu evaluasi lanjutan |
| 7 | Jumlah Key Takeaways yang ditampilkan | Terlalu sedikit menyembunyikan temuan; terlalu banyak sulit dibaca | Menunggu keputusan PO |
| 8 | Lingkungan uji mitra | *Deployment* bisa mengganggu pengujian DPEA | Usulan internal, belum diputuskan |
| 9 | Keterlambatan jadwal | Mengancam target akhir Desember | Perlu revisi jadwal dan rencana percepatan |
| 10 | Dana kunjungan tatap muka | Membatasi pertemuan di Jakarta | Alternatif Surabaya / kampus belum dijadwalkan |

**Hal yang secara eksplisit belum diputuskan:**

- Model AI final untuk produksi.
- Posisi final *toggle* AI.
- Jumlah Key Takeaways yang ditampilkan.
- Lingkungan uji terpisah untuk mitra.
- Jadwal pertemuan tatap muka dengan DPEA.
- Rencana percepatan terperinci.

Rapat mingguan berikutnya: Selasa, 17 November 2026 (Pak Faris: "mulai minggu depan, hari Selasa"). Jamnya belum disebutkan.

---

## 11. Kesimpulan

Fokus tim setelah rapat adalah menuntaskan **MVP 2 — Summary & Key Takeaways** sebelum melanjutkan ke MVP 3. Alur unggah, Summary, Key Takeaways, dan opsi AI sudah bisa didemokan, tetapi kualitas pemrosesan dokumen bertabel dan kesederhanaan UI untuk pengguna non-IT masih perlu diperbaiki.

Dari sisi kebutuhan bisnis, DPEA menegaskan bahwa Summary membantu pengguna memahami satu dokumen secara mandiri, sedangkan Analisa memetakan setiap pasal terhadap regulasi di Knowledge Base. Tim diminta menyiapkan link pengujian end-to-end setelah QA internal selesai.

Dari sisi manajemen proyek, keterlambatan harus dilaporkan secara transparan. Perkiraan pergeseran sekitar satu minggu perlu ditindaklanjuti dengan revisi jadwal dan rencana percepatan yang realistis sampai akhir Desember, dan komunikasi dengan mitra tidak perlu menunggu rapat mingguan.
