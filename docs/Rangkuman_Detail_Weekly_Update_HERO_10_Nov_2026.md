# Rangkuman Detail Weekly Update Capstone HERO

**Tanggal:** Selasa, 10 November 2026\
**Topik utama:** Evaluasi MVP 2 --- Summary & Key Takeaways, kesiapan
pengujian, dan penyesuaian jadwal\
**Sumber:** Transkrip rapat Weekly Update Capstone Project HERO tanggal
10 November 2026\
**Catatan:** Dokumen ini merupakan rangkuman pembahasan, bukan transkrip
verbatim. Bagian diskusi internal setelah mitra meninggalkan rapat
dipisahkan dari keputusan bersama. Beberapa ucapan pada transkrip
otomatis kurang jelas; informasi yang tidak dapat dipastikan tidak
ditambahkan sebagai fakta.

------------------------------------------------------------------------

## Daftar Isi

-   [1. Konteks dan Tujuan Rapat](#1-konteks-dan-tujuan-rapat)
-   [2. Status Proyek dan Pelaporan](#2-status-proyek-dan-pelaporan)
-   [3. Update Implementasi MVP 2](#3-update-implementasi-mvp-2)
    -   [3.1. Frontend dan Alur
        Pengguna](#31-frontend-dan-alur-pengguna)
    -   [3.2. Backend dan Struktur Hasil
        Summary](#32-backend-dan-struktur-hasil-summary)
    -   [3.3. AI-Assisted dan Pemilihan
        Model](#33-ai-assisted-dan-pemilihan-model)
    -   [3.4. Pengujian dan Kualitas
        Dokumen](#34-pengujian-dan-kualitas-dokumen)
-   [4. Klarifikasi Kebutuhan dari
    DPEA](#4-klarifikasi-kebutuhan-dari-dpea)
-   [5. Rencana Pengujian End-to-End](#5-rencana-pengujian-end-to-end)
-   [6. Timeline dan Dampak terhadap Fase
    Berikutnya](#6-timeline-dan-dampak-terhadap-fase-berikutnya)
-   [7. Arahan dan Ekspektasi Mitra](#7-arahan-dan-ekspektasi-mitra)
-   [8. Diskusi Internal Setelah
    Rapat](#8-diskusi-internal-setelah-rapat)
-   [9. Daftar Tindak Lanjut](#9-daftar-tindak-lanjut)
-   [10. Risiko, Isu, dan Hal yang Belum
    Diputuskan](#10-risiko-isu-dan-hal-yang-belum-diputuskan)
-   [11. Kesimpulan](#11-kesimpulan)

------------------------------------------------------------------------

## 1. Konteks dan Tujuan Rapat

Rapat weekly update dilaksanakan untuk melihat perkembangan pekerjaan
setelah evaluasi sebelumnya, khususnya implementasi **MVP 2 --- Summary
& Key Takeaways**. Pembahasan mencakup demonstrasi aplikasi, penjelasan
alur pemrosesan, hasil pengujian, masukan terhadap UI/UX, serta kesiapan
aplikasi untuk diuji oleh pihak DPEA.

### Peserta yang teridentifikasi dari transkrip

**Pihak DPEA** - Faris Budi --- Product Owner / perwakilan DPEA. -
Andika Prihandoko --- mentor industri; bergabung pada bagian akhir
rapat.

**Tim HERO** - Ahmad Zaky Ash Shidqi --- Project Manager / Business
Analyst. - Muhammad Ikhwan --- Frontend. - Moh. Rafli Gusti Saputra ---
Backend. - Ahmad Izzul Hamdan --- Infrastruktur / QA. - Fathir ---
Data/ML; berhalangan hadir dan progresnya disampaikan oleh Zaky.

> Nama dan peran mengikuti konteks rapat serta informasi tim yang
> tersedia. Transkrip tidak mencatat daftar hadir formal.

------------------------------------------------------------------------

## 2. Status Proyek dan Pelaporan

### 2.1. Laporan kemajuan dari kampus

Zaky menyampaikan bahwa: - Tim telah menyiapkan draft laporan kemajuan
proyek untuk kebutuhan mata kuliah Capstone. - Laporan disusun
berdasarkan perkembangan proyek terbaru hingga pertengahan semester. -
Dokumen masih perlu ditinjau oleh mentor industri. - Laporan juga
berkaitan dengan laporan keuangan/administrasi untuk proses
reimbursement dari pihak kampus. - Zaky menyampaikan bahwa dokumen
kemungkinan memerlukan tanda tangan mentor industri, yaitu Pak Andika.

### 2.2. Kondisi progres proyek

-   Saat rapat, tim masih berada pada MVP/fase kedua dari total lima
    fase.
-   Ketika ditanya mengenai persentase progres keseluruhan, Zaky
    menyampaikan estimasi sekitar **40--45%**, kemudian mengklarifikasi
    kisaran sekitar **40%**. Angka ini merupakan estimasi lisan, bukan
    hasil pengukuran baseline yang ditampilkan secara rinci.
-   Secara jadwal, proyek seharusnya sudah mulai masuk MVP 3, tetapi MVP
    2 belum selesai dan belum diterima oleh Product Owner.
-   Pak Faris meminta status proyek dilaporkan secara apa adanya,
    termasuk keterlambatan, bagian yang sudah selesai, pekerjaan
    tertunda, revisi jadwal, serta rencana mengejar target hingga akhir
    Desember.

### 2.3. Format pelaporan yang diminta mitra

Pak Faris mengarahkan agar laporan progres: - Tidak terlalu teknis dan
mudah dipahami stakeholder. - Menjelaskan posisi proyek terhadap jadwal:
*ahead of schedule*, *on schedule*, atau *behind schedule*. -
Menunjukkan jumlah/proporsi pekerjaan yang selesai, pekerjaan yang masih
tertunda, dan pekerjaan berikutnya. - Menjelaskan dampak keterlambatan
terhadap jadwal akhir serta langkah percepatannya. - Dapat disajikan
dalam ringkasan tabel atau sekitar 1--2 slide untuk weekly meeting
berikutnya.

Pak Faris meminta Zaky mengirimkan laporan melalui WhatsApp agar dapat
ditinjau dan ditandatangani. Laporan harus mencerminkan kondisi aktual,
bukan sekadar status yang terlihat baik.

------------------------------------------------------------------------

## 3. Update Implementasi MVP 2

## 3.1. Frontend dan Alur Pengguna

Ikhwan mendemonstrasikan tampilan aplikasi yang telah diperbarui
berdasarkan masukan sebelumnya.

### Fitur/tampilan yang diperlihatkan

-   Upload dokumen PDF.
-   Riwayat dokumen/regulasi yang pernah diunggah sehingga pengguna
    tidak perlu mengunggah ulang untuk melihat dokumen yang sama.
-   Tampilan Summary dan Key Takeaways.
-   Hasil awal menggunakan mode Deterministik.
-   Opsi untuk mengaktifkan AI pada hasil yang tersedia.
-   Tampilan lanjutan yang mengarah ke analisis/perbandingan dengan
    Knowledge Base.

### Masukan UI/UX dari DPEA

Pak Faris menekankan bahwa pengguna aplikasi nantinya tidak selalu
berasal dari bidang IT. Karena itu, antarmuka harus: - Mudah dipahami
sejak pertama kali dibuka. - Tidak dipenuhi tombol, istilah teknis, atau
isian yang membingungkan. - Menampilkan informasi yang benar-benar
diperlukan untuk menyelesaikan pekerjaan pengguna. - Menggunakan tata
letak yang rapi dan dapat dibaca pada ukuran layar yang berbeda.

Beberapa field yang dinilai belum diperlukan dalam alur yang
didemonstrasikan antara lain alasan approval, status publik/nonpublik,
dan persetujuan publikasi. Tim diminta meninjau kembali kebutuhan field
tersebut, bukan langsung menambah kompleksitas alur.

### Metadata dokumen

Metadata seperti judul, nomor, jenis regulasi, dan sektor diharapkan
dapat diperoleh secara otomatis dari dokumen sejauh memungkinkan,
sehingga pengguna tidak perlu mengisi terlalu banyak informasi secara
manual.

### Penempatan opsi AI

Penempatan toggle AI masih dibahas. Ada dua pertimbangan: - Opsi AI
dapat tersedia pada alur Summary karena prosesnya hanya menganalisis
dokumen yang baru diunggah. - Opsi AI untuk proses Analisa terhadap
Knowledge Base perlu dipisahkan atau dipertimbangkan tersendiri karena
pemrosesan terhadap kumpulan regulasi yang besar berpotensi menggunakan
token jauh lebih banyak.

Pak Faris meminta tim mendiskusikan pengalaman pengguna dan mencoba
penempatan yang paling mudah dipahami. Transkrip tidak menunjukkan
keputusan final mengenai posisi toggle tersebut.

## 3.2. Backend dan Struktur Hasil Summary

Rafli menjelaskan struktur hasil ringkasan eksekutif dan Key Takeaways
yang ditampilkan aplikasi.

### Komponen ringkasan yang dijelaskan

1.  **Identitas dokumen**
    -   Informasi identitas dari dokumen yang diunggah.
2.  **Kerangka atau struktur dokumen**
    -   Susunan dokumen, seperti bab, judul, dan pasal.
3.  **Pihak utama**
    -   Subjek atau pihak yang terkait dengan ketentuan dalam dokumen.
4.  **Kewajiban utama**
    -   Kewajiban yang diatur dalam naskah regulasi.
5.  **Kewajiban pelaporan**
    -   Ketentuan mengenai kewajiban pelaporan.
6.  **Rujukan pasal**
    -   Pasal yang menjadi landasan dari informasi atau temuan yang
        ditampilkan.
7.  **Sanksi**
    -   Sanksi yang tercantum dalam dokumen.
8.  **Pencabutan**
    -   Ketentuan terkait pencabutan aturan atau ketentuan sebelumnya.
9.  **Masa berlaku**
    -   Informasi masa berlaku regulasi.

### Key Takeaways

-   Key Takeaways menampilkan poin-poin penting yang ditemukan dari
    dokumen.
-   Poin dikelompokkan atau diurutkan berdasarkan prioritas.
-   Kategori yang disebut dalam demonstrasi meliputi sanksi, larangan,
    perizinan, dan kategori terkait lainnya.
-   Setiap poin dapat memiliki rujukan pasal dari dokumen yang diunggah.
-   Isi pasal ditampilkan sebagai konteks atau bukti dari poin tersebut.

### Penjelasan alur AI-Assisted

Rafli menjelaskan bahwa AI tidak harus membangun hasil dari nol. Dalam
alur yang dijelaskan: 1. Sistem menjalankan proses Deterministik
terlebih dahulu. 2. Hasil Deterministik menjadi masukan bagi proses AI.
3. AI melakukan analisis atau penyempurnaan terhadap hasil tersebut. 4.
Sistem melakukan pengecekan kembali terhadap dokumen sebagai bentuk
verifikasi tambahan.

Dengan demikian, AI berfungsi membantu memperkaya atau memeriksa hasil
awal, bukan menggantikan seluruh proses dasar.

### Perbandingan dengan Knowledge Base

Dalam demonstrasi bagian analisis, Rafli menjelaskan kategori hasil
perbandingan: - **Baru:** ketentuan terindikasi sebagai ketentuan baru
dalam dokumen. - **Sama:** ketentuan terindikasi sama atau menduplikasi
ketentuan yang telah ada. - **Menggantikan:** ketentuan baru berpotensi
memperbarui atau menggantikan ketentuan sebelumnya. - **Konflik:**
ketentuan terindikasi memiliki pertentangan dengan ketentuan yang sudah
ada.

Rafli menyebut kemiripan teks sekitar 80% sebagai salah satu indikasi
untuk kategori "menggantikan". Angka tersebut disampaikan sebagai
gambaran mekanisme yang sedang digunakan, bukan sebagai standar final
yang telah disepakati mitra.

Bagian perbandingan dengan Knowledge Base merupakan gambaran alur
analisis lanjutan dan belum menjadi fokus penyelesaian MVP 2.

## 3.3. AI-Assisted dan Pemilihan Model

Zaky menyampaikan hasil eksperimen model yang sebelumnya dilakukan
Fathir.

  -----------------------------------------------------------------------
  Model                               Hasil pengamatan yang disampaikan
  ----------------------------------- -----------------------------------
  Gemini 3.1 Pro                      Hasil paling komprehensif, tetapi
                                      waktu proses lebih lama dan biaya
                                      lebih tinggi.

  Gemini 3.6 Flash                    Hasil cukup baik dengan
                                      keseimbangan kualitas, biaya, dan
                                      waktu proses.

  Gemini 3.6 Flash Lite               Paling cepat dan murah, tetapi
                                      hasil ringkasan cenderung terlalu
                                      singkat.
  -----------------------------------------------------------------------

> Nama/versi model di atas mengikuti penyebutan pada transkrip otomatis
> dan perlu diverifikasi kembali terhadap konfigurasi model yang
> benar-benar digunakan.

Pertimbangan teknis yang disampaikan: - Pemilihan model perlu
mempertimbangkan kualitas hasil, durasi pemrosesan, dan biaya. -
Penggunaan model juga dibatasi kuota API, termasuk RPM (*requests per
minute*), TPM (*tokens per minute*), dan TPD (*tokens per day*). - Zaky
menyampaikan kemungkinan mekanisme fallback ke model yang lebih
sederhana dan murah ketika batas tertentu tercapai. - Pak Faris
mengingatkan bahwa model yang digunakan saat pengembangan belum tentu
sama dengan model yang digunakan ketika aplikasi diterapkan ke
lingkungan produksi. - Model yang lebih kuat dapat digunakan untuk
membantu proses pengembangan atau validasi, tetapi penerapan produksi
perlu mempertimbangkan model yang lebih hemat dan proses
*pre-processing* yang memadai. - Tim perlu memiliki alasan yang dapat
dijelaskan mengenai pemilihan model, bukan hanya menyatakan bahwa model
tertentu memberikan hasil terbaik.

Belum ada keputusan final dalam rapat mengenai model produksi yang akan
digunakan.

## 3.4. Pengujian dan Kualitas Dokumen

Izzul menyampaikan hasil pengujian terhadap proses ekstraksi dan
pembuatan ringkasan.

### Hasil pengujian yang disampaikan

-   Pada pengujian awal terhadap dokumen berisi 10 pasal, sekitar 5
    pasal berhasil diberi tag.
-   Izzul menyampaikan hasil tersebut kepada Fathir untuk
    ditindaklanjuti.
-   Setelah revisi yang dilakukan bersama Fathir, hasil pengujian
    membaik.
-   Dokumen dengan struktur pasal dan ayat relatif lebih mudah diproses.
-   Dokumen yang banyak menggunakan tabel masih menjadi kendala utama.

### Variasi dokumen

Izzul menyebut pengujian menggunakan beberapa dokumen dari OneDrive,
termasuk dokumen yang memiliki banyak tabel. Dokumen yang lebih padat
tabel menghasilkan ringkasan dan Key Takeaways yang kurang baik
dibandingkan dokumen dengan struktur pasal/ayat yang lebih jelas.

### Kebutuhan perbaikan

-   Meningkatkan kemampuan sistem membaca konten tabel.
-   Menguji dokumen dengan variasi struktur, bukan hanya dokumen yang
    dominan berisi pasal dan ayat.
-   Memeriksa apakah seluruh ketentuan penting berhasil diekstrak.
-   Memastikan ringkasan tidak kehilangan konteks ketika sumber dokumen
    memiliki struktur yang kompleks.

------------------------------------------------------------------------

## 4. Klarifikasi Kebutuhan dari DPEA

Bagian ini merangkum penjelasan Pak Faris mengenai proses kerja dan
ekspektasi terhadap fitur.

### 4.1. Cara kerja DPEA ketika membaca regulasi

Pak Faris menjelaskan bahwa proses kerja pengguna tidak langsung dimulai
dengan mencari ketentuan IT. Pengguna perlu: 1. Membaca dokumen regulasi
secara keseluruhan. 2. Memahami dokumen tersebut membahas apa. 3.
Memahami latar belakang dan struktur regulasi. 4. Mengidentifikasi
bagian yang berkaitan dengan ruang lingkup pekerjaan DPEA. 5. Menyaring
ketentuan yang relevan. 6. Menyusun ringkasan singkat mengenai ketentuan
yang relevan tersebut.

Contoh hal yang dicari dari sisi IT antara lain: - Pelaporan secara
online. - Pertukaran data. - Penggunaan aplikasi. - Kewajiban
pelaporan. - Ketentuan lain yang berkaitan dengan teknologi informasi.

Dengan demikian, ringkasan yang diharapkan tidak hanya menyalin seluruh
isi regulasi, tetapi membantu pengguna memahami isi dokumen dan
menemukan bagian yang relevan.

### 4.2. Perbedaan Summary dan Analysis

Pembahasan menegaskan perbedaan tujuan kedua fitur:

  -----------------------------------------------------------------------
  Aspek                   Summary                 Analysis
  ----------------------- ----------------------- -----------------------
  Fokus                   Memahami satu dokumen   Membandingkan ketentuan
                          yang diunggah           dokumen dengan regulasi
                                                  dalam Knowledge Base

  Sumber utama            Dokumen yang sedang     Dokumen yang diunggah
                          diunggah                dan referensi dalam
                                                  Knowledge Base

  Tujuan                  Memberi gambaran isi    Mengidentifikasi
                          dokumen dan poin        hubungan ketentuan
                          penting                 dengan regulasi yang
                                                  sudah ada

  Ketergantungan KB       Tidak perlu             Menggunakan KB sebagai
                          membandingkan dengan KB sumber pembanding

  Tahap proyek            MVP 2                   MVP 3 / fase analisis
                                                  lanjutan
  -----------------------------------------------------------------------

Pak Faris menjelaskan bahwa Summary untuk dokumen 50 halaman harus
menghasilkan gambaran dan poin penting dari dokumen tersebut saja.
Proses ini tidak perlu membandingkannya dengan dokumen lain yang juga
memiliki puluhan halaman.

### 4.3. Analisis harus memetakan pasal per pasal

Untuk fitur Analysis, Pak Faris menyampaikan bahwa proses awal yang
penting adalah memetakan setiap pasal dalam dokumen: - Pasal mana yang
merupakan ketentuan baru. - Pasal mana yang sudah pernah diatur dalam
regulasi sebelumnya. - Pasal mana yang ketentuannya sudah tidak
berlaku. - Pasal mana yang digantikan oleh regulasi baru. - Hubungan
antara ketentuan dalam dokumen baru dengan ketentuan dalam Knowledge
Base.

Pemetaan perlu dilakukan sampai tingkat pasal, bukan hanya membandingkan
dokumen secara umum.

### 4.4. Hubungan Input dan Output dari DPEA

-   Contoh **Input** dan **Output** yang diberikan DPEA merupakan
    referensi untuk memahami hasil yang diharapkan.
-   Output bukan daftar seluruh temuan mentah.
-   Pak Faris menjelaskan bahwa Output merupakan *shortlist* yang
    disaring dari *longlist* temuan.
-   Tim perlu memahami proses penyaringan dari daftar temuan awal
    menjadi hasil yang relevan untuk pengguna.

### 4.5. Jumlah Key Takeaways

Rafli menanyakan apakah seluruh temuan sebaiknya ditampilkan atau hanya
10 poin teratas, karena sistem dapat menemukan lebih dari 10 poin.

Pak Faris belum memberikan keputusan. Ia menjelaskan bahwa pengguna
biasanya membaca dokumen terlebih dahulu untuk memahami substansi dan
struktur, kemudian menyaring bagian yang relevan dengan IT, baru membuat
ringkasan yang lebih singkat.

Keputusan mengenai jumlah temuan yang perlu ditampilkan harus menunggu
peninjauan dokumen dan contoh hasil yang lebih konkret.

------------------------------------------------------------------------

## 5. Rencana Pengujian End-to-End

Pak Faris meminta tim menyiapkan tautan aplikasi yang dapat diakses
untuk pengujian mandiri.

### 5.1. Alur pengujian

1.  Tim menyiapkan aplikasi dan tautan pengujian.
2.  Rafli berkoordinasi dengan Fathir untuk memastikan tautan dapat
    diakses.
3.  Izzul melakukan QA internal sebelum tautan diberikan kepada DPEA.
4.  Setelah dinyatakan siap secara internal, tautan disampaikan kepada
    Pak Faris dan Pak Andika.
5.  DPEA melakukan pengujian dari sisi kebutuhan dan penerimaan bisnis
    (*business acceptance*).
6.  Temuan atau pertanyaan dari DPEA dicatat untuk ditindaklanjuti tim.

### 5.2. Skenario pengujian yang disebutkan

  -----------------------------------------------------------------------
  Area                                Hal yang perlu diperiksa
  ----------------------------------- -----------------------------------
  Akses aplikasi                      Tautan dapat dibuka dan digunakan
                                      oleh penguji.

  Upload dokumen                      Berbagai jenis/format dokumen dapat
                                      diunggah dan diproses.

  Summary                             Ringkasan dapat dihasilkan dari
                                      dokumen yang diunggah.

  Key Takeaways                       Poin penting dapat ditampilkan
                                      dengan jelas dan relevan.

  AI action                           Tombol/aksi AI dapat dijalankan dan
                                      prosesnya berjalan dengan lancar.

  Duplicate upload                    Sistem memberikan peringatan ketika
                                      dokumen yang sama diunggah kembali.

  Knowledge Base                      Ada pembedaan antara dokumen yang
                                      dimasukkan (*ingest*) ke KB dan
                                      dokumen yang hanya
                                      diperiksa/dianalisis.

  Stabilitas proses                   Tidak terjadi proses loading tanpa
                                      akhir atau kegagalan yang
                                      menghambat pengguna.

  Pengalaman pengguna                 Alur mudah dipahami oleh pengguna
                                      non-IT.

  Kesesuaian kebutuhan                Hasil dan fungsi aplikasi sesuai
                                      dengan kebutuhan yang telah
                                      disampaikan DPEA.
  -----------------------------------------------------------------------

Pak Faris meminta agar seluruh fungsi tersebut diperiksa terlebih dahulu
oleh tim. Setelah itu, DPEA akan menilai apakah aplikasi sudah berjalan
sesuai kebutuhan bisnis.

### 5.3. Pembagian tanggung jawab pengujian

-   **Rafli:** koordinasi dengan Fathir untuk menyiapkan link pengujian.
-   **Izzul:** memastikan kesiapan QA dan fungsi aplikasi sebelum link
    dibagikan.
-   **Fathir:** membantu kesiapan pipeline/model dan koordinasi teknis
    terkait aplikasi.
-   **Faris dan Andika:** melakukan pengujian dari sisi
    pengguna/stakeholder setelah tim menyatakan aplikasi siap.

------------------------------------------------------------------------

## 6. Timeline dan Dampak terhadap Fase Berikutnya

### Kondisi jadwal

-   Rencana awal mengarah pada dimulainya MVP 3 pada minggu rapat.
-   Namun, MVP 2 masih membutuhkan perbaikan berdasarkan hasil
    demonstrasi dan masukan mitra.
-   Pak Faris menyampaikan kemungkinan jadwal bergeser sekitar satu
    minggu.
-   Minggu berikutnya masih akan digunakan untuk membahas dan memastikan
    penyelesaian MVP 2, terutama Summary, Key Takeaways, dan perbaikan
    UI.
-   Pak Andika meminta tim berupaya agar keterlambatan tidak semakin
    melebar.

### Implikasi terhadap target akhir

-   Zaky diminta mencatat keterlambatan secara transparan pada laporan
    rutin.
-   Tim perlu membuat penyesuaian jadwal dan menjelaskan bagaimana
    pekerjaan akan dikejar hingga akhir Desember.
-   Percepatan perlu dibahas secara konkret, bukan hanya dengan
    memindahkan tanggal target.
-   Mitra membuka ruang komunikasi tambahan apabila diperlukan untuk
    mempercepat penyelesaian.

> **Status:** Pergeseran sekitar satu minggu merupakan perkiraan yang
> disampaikan dalam rapat. Jadwal revisi terperinci dan rencana
> percepatan sampai Desember belum ditetapkan secara rinci.

------------------------------------------------------------------------

## 7. Arahan dan Ekspektasi Mitra

### 7.1. Arahan Pak Faris

-   Laporan progres disampaikan sesuai kondisi aktual.
-   Presentasi weekly meeting sebaiknya diawali dengan posisi proyek
    terhadap jadwal.
-   Informasi yang disampaikan kepada stakeholder harus ringkas dan
    tidak terlalu teknis.
-   Aplikasi harus dirancang untuk pengguna non-IT.
-   Summary harus berfokus pada dokumen yang diunggah, sedangkan
    Analysis membandingkan dokumen dengan Knowledge Base.
-   Pengujian internal harus dilakukan sebelum aplikasi diserahkan
    kepada DPEA.
-   Pertanyaan dan temuan saat pengujian akan diberikan kepada tim untuk
    klarifikasi dan perbaikan.
-   Komunikasi terkait kendala tidak perlu menunggu weekly meeting; tim
    dapat menghubungi mitra melalui WhatsApp.

### 7.2. Arahan Pak Andika

-   Masukan dari mentor bukan untuk memperlambat tim, melainkan
    membangun pemahaman mengenai pelaksanaan proyek di lingkungan kerja
    nyata.
-   Tim diharapkan lebih aktif menyampaikan kendala dan perbedaan
    pendapat.
-   Jika terjadi perbedaan pendapat internal, Zaky sebagai PM diharapkan
    membantu mengarahkan dan mengambil keputusan.
-   Jika membutuhkan klarifikasi, tim dapat mengajukan diskusi atau Zoom
    tambahan tanpa harus menunggu jadwal mingguan.
-   Tim didorong menjaga target penyelesaian dan menghindari
    keterlambatan tambahan.
-   Hasil proyek diharapkan memberikan manfaat bagi stakeholder dan
    menjadi pengalaman yang baik bagi tim.

### 7.3. Kendala pendanaan dan kemungkinan kunjungan

-   Pak Andika menanyakan apakah terdapat kendala lain di luar aspek
    teknis, termasuk anggaran.
-   Zaky menyampaikan bahwa kunjungan tim ke Jakarta memungkinkan dari
    sisi kampus, tetapi pendanaan untuk membawa seluruh anggota tim
    masih terbatas.
-   Pak Andika menyampaikan bahwa pertemuan di Surabaya juga dapat
    dipertimbangkan apabila ada undangan dan koordinasi dengan pihak
    kampus.
-   Ada pembicaraan mengenai kemungkinan mengundang pihak terkait untuk
    bertemu di kampus, tetapi belum ada tanggal atau agenda resmi yang
    diputuskan.

------------------------------------------------------------------------

## 8. Diskusi Internal Setelah Rapat

Bagian ini merupakan pembicaraan tim setelah sesi bersama DPEA berakhir.
Isinya tidak boleh dianggap sebagai keputusan resmi mitra.

### 8.1. Kebutuhan environment testing/staging

Tim membahas kekhawatiran bahwa aplikasi yang digunakan DPEA untuk
pengujian dapat terganggu apabila tim melakukan perubahan kode dan
deployment pada environment yang sama.

Pertimbangan yang muncul: - Tim masih perlu melakukan development, pull
request, dan deployment. - Jika mitra sedang menguji aplikasi pada saat
deployment berlangsung, aplikasi berpotensi mengalami error atau
perubahan perilaku. - Muncul usulan menyediakan web/environment khusus
untuk pengujian mitra. - Environment tersebut diharapkan tetap memiliki
fungsi yang sama dengan aplikasi utama, tetapi tidak terganggu oleh
perubahan development harian.

Belum ada keputusan final mengenai implementasi environment terpisah.

### 8.2. Peninjauan ulang toggle AI

Tim kembali mendiskusikan apakah toggle AI ditempatkan pada tahap upload
atau pada hasil Summary.

Pemahaman yang muncul: - Summary dapat menggunakan AI karena ruang
lingkupnya hanya dokumen yang sedang diproses. - Analysis menggunakan
Knowledge Base yang jauh lebih besar, sehingga penggunaan AI secara
menyeluruh sejak awal dapat meningkatkan konsumsi token. - Perlu
pemisahan yang jelas antara pilihan AI untuk Summary dan kebutuhan
pemrosesan pada Analysis.

Tim menyadari bahwa alur dan posisi toggle masih perlu difinalisasi agar
tidak membingungkan pengguna maupun implementasi teknis.

### 8.3. Kebutuhan memperjelas target fitur

Ikhwan menyampaikan bahwa sebelumnya terdapat perbedaan pemahaman
internal mengenai keluaran yang harus ditampilkan karena blueprint atau
gambaran hasil yang diharapkan belum cukup jelas bagi seluruh anggota.

Setelah penjelasan Pak Faris, tim memperoleh gambaran yang lebih konkret
mengenai prioritas analisis, khususnya identifikasi ketentuan baru,
sama, menggantikan, atau tidak berlaku.

### 8.4. Jumlah poin yang ditampilkan

-   Tim mendiskusikan bahwa sistem dapat menemukan lebih dari 10 poin.
-   Pembatasan 10 poin teratas berpotensi membuat sebagian temuan tidak
    ditampilkan.
-   Di sisi lain, menampilkan seluruh temuan dapat membuat hasil terlalu
    panjang dan sulit dibaca.
-   Belum ada keputusan final mengenai jumlah poin yang ideal.
-   Tim perlu menguji pendekatan penyaringan dan meminta konfirmasi
    mitra berdasarkan contoh dokumen.

### 8.5. Koordinasi lanjutan

Tim membahas perlunya mengadakan sesi tambahan untuk membahas percepatan
dan menyelaraskan pekerjaan. Waktu pastinya belum dapat dipastikan
karena perlu menyesuaikan ketersediaan anggota, khususnya Fathir.

------------------------------------------------------------------------

## 9. Daftar Tindak Lanjut

Daftar berikut merangkum pekerjaan yang diminta atau muncul dari
pembahasan. Status belum dianggap selesai sampai ada konfirmasi dari
PIC.

### 9.1. Project Manager / Business Analyst --- Zaky

-   [ ] Mengirimkan draft laporan kemajuan kepada Pak Faris melalui
    WhatsApp untuk ditinjau.
-   [ ] Mengkoordinasikan kebutuhan review dan tanda tangan laporan
    dengan mentor industri.
-   [ ] Memastikan laporan menunjukkan progres aktual, posisi terhadap
    jadwal, pekerjaan tertunda, dan revisi timeline.
-   [ ] Menyusun rencana percepatan untuk mengejar target hingga akhir
    Desember.
-   [ ] Menyiapkan ringkasan progres yang mudah dibaca stakeholder,
    idealnya 1--2 slide.
-   [ ] Mengawali weekly meeting berikutnya dengan status proyek
    terhadap jadwal.
-   [ ] Mengkoordinasikan perbedaan pendapat dan keputusan lintas peran
    dalam tim.
-   [ ] Mengatur komunikasi lanjutan dengan mitra apabila terdapat
    pertanyaan atau kendala yang membutuhkan arahan.

### 9.2. Frontend --- Ikhwan

-   [ ] Menyederhanakan tampilan agar dapat dipahami pengguna non-IT.
-   [ ] Meninjau field yang tidak diperlukan, termasuk alasan approval,
    status publik/nonpublik, dan persetujuan publikasi.
-   [ ] Merapikan tampilan Summary dan Key Takeaways agar fokus pada
    dokumen dan hasil ringkasan.
-   [ ] Meninjau tata letak agar tetap nyaman digunakan pada ukuran
    layar yang berbeda.
-   [ ] Meninjau cara menampilkan metadata dokumen secara otomatis.
-   [ ] Memfinalisasi pengalaman pengguna untuk toggle AI pada Summary.
-   [ ] Memastikan alur Summary dan Analysis tidak membingungkan atau
    tumpang tindih.
-   [ ] Memperjelas navigasi dari Summary menuju Analysis sesuai
    kebutuhan.

### 9.3. Backend --- Rafli

-   [ ] Meninjau struktur keluaran Summary dan Key Takeaways.
-   [ ] Memastikan rujukan pasal pada hasil ringkasan dapat ditelusuri
    ke dokumen sumber.
-   [ ] Meninjau mekanisme kategori temuan pada Analysis: baru, sama,
    menggantikan, dan konflik.
-   [ ] Memastikan pemetaan regulasi dilakukan pada tingkat pasal,
    termasuk ketentuan yang sudah tidak berlaku atau digantikan.
-   [ ] Mendokumentasikan cara kerja algoritma dan alasan suatu pasal
    atau poin dipilih.
-   [ ] Berkoordinasi dengan Fathir untuk menyiapkan link pengujian
    end-to-end.
-   [ ] Memastikan peringatan dokumen duplikat dan pemisahan proses
    ingest KB dengan analisis dokumen berjalan sesuai kebutuhan.

### 9.4. Data/ML --- Fathir

-   [ ] Menindaklanjuti perbaikan hasil ekstraksi dan ringkasan,
    khususnya pada dokumen yang memiliki banyak tabel.
-   [ ] Memastikan hasil Summary hanya menggunakan dokumen yang
    diunggah, tanpa mencampurkan referensi Knowledge Base.
-   [ ] Melanjutkan evaluasi model berdasarkan kualitas, waktu proses,
    biaya, dan batas kuota API.
-   [ ] Menyiapkan alasan teknis pemilihan model yang dapat dijelaskan
    kepada mitra.
-   [ ] Meninjau mekanisme fallback model apabila batas penggunaan API
    tercapai.
-   [ ] Berkoordinasi dengan Rafli terkait kesiapan pipeline dan link
    pengujian.

### 9.5. Infrastruktur / QA --- Izzul

-   [ ] Melakukan QA internal terhadap alur aplikasi dari upload sampai
    hasil Summary dan Key Takeaways.
-   [ ] Menguji berbagai variasi dokumen, terutama dokumen dengan tabel
    yang kompleks.
-   [ ] Memastikan aksi AI dapat dijalankan dan tidak mengalami loading
    tanpa akhir.
-   [ ] Menguji peringatan ketika dokumen yang sama diunggah kembali.
-   [ ] Memastikan perbedaan dokumen yang di-ingest ke Knowledge Base
    dan dokumen yang hanya dianalisis.
-   [ ] Memastikan aplikasi stabil sebelum tautan diberikan kepada DPEA.
-   [ ] Menyampaikan hasil pengujian dan temuan kepada tim untuk
    diperbaiki.

### 9.6. Seluruh Tim

-   [ ] Menyelaraskan pemahaman mengenai batasan MVP 2 dan MVP 3.
-   [ ] Mengutamakan penyelesaian MVP 2 sebelum memperluas pekerjaan ke
    MVP 3.
-   [ ] Mengadakan koordinasi tambahan jika terdapat isu yang tidak
    dapat diselesaikan melalui diskusi asinkron.
-   [ ] Menyampaikan kendala secara langsung kepada Zaky dan/atau mitra
    tanpa menunggu weekly meeting.
-   [ ] Menjaga agar perubahan aplikasi tidak mengganggu proses
    pengujian stakeholder.

### 9.7. Pihak Mitra

-   [ ] Pak Faris dan Pak Andika melakukan review laporan kemajuan yang
    dikirimkan Zaky.
-   [ ] Pak Faris melakukan pengujian aplikasi setelah tim menyampaikan
    link yang telah lolos QA internal.
-   [ ] Pak Faris memberikan catatan atau pertanyaan berdasarkan hasil
    pengujian.
-   [ ] Pak Faris dan Pak Andika melakukan penilaian dari sisi kebutuhan
    bisnis setelah aplikasi siap diuji.

------------------------------------------------------------------------

## 10. Risiko, Isu, dan Hal yang Belum Diputuskan

  -----------------------------------------------------------------------
  No.               Isu               Dampak/Potensi    Status
                                      Risiko            
  ----------------- ----------------- ----------------- -----------------
  1                 MVP 2 belum       Memengaruhi       Perlu
                    diterima          dimulainya MVP 3  penyelesaian dan
                                      dan timeline      evaluasi ulang
                                      keseluruhan       

  2                 Dokumen berbasis  Summary dan Key   Perlu perbaikan
                    tabel sulit       Takeaways dapat   dan pengujian
                    diproses          tidak lengkap     
                                      atau kurang       
                                      akurat            

  3                 UI masih terlalu  Pengguna non-IT   Perlu
                    kompleks          dapat kesulitan   penyederhanaan
                                      memahami alur     

  4                 Batas Summary dan Berpotensi        Perlu
                    Analysis belum    menyebabkan       penyelarasan
                    sepenuhnya        implementasi dan  internal
                    dipahami semua    UI tidak          
                    anggota           konsisten         

  5                 Posisi toggle AI  Berpengaruh pada  Belum diputuskan
                    belum final       alur pengguna dan 
                                      konsumsi token    

  6                 Pemilihan model   Kualitas, biaya,  Perlu evaluasi
                    AI                kecepatan, dan    lanjutan
                                      kuota API perlu   
                                      diseimbangkan     

  7                 Jumlah Key        Terlalu sedikit   Menunggu evaluasi
                    Takeaways yang    dapat             contoh dokumen
                    ditampilkan       menghilangkan     
                                      temuan; terlalu   
                                      banyak dapat      
                                      menyulitkan       
                                      pembacaan         

  8                 Environment       Deployment        Usulan internal,
                    testing mitra     development dapat belum diputuskan
                                      mengganggu        
                                      pengujian         
                                      stakeholder       

  9                 Keterlambatan     Berpotensi        Perlu revisi
                    jadwal            memengaruhi       timeline dan
                                      target akhir      rencana
                                      Desember          percepatan

  10                Keterbatasan      Dapat membatasi   Belum ada
                    pendanaan         pertemuan tatap   pengaturan final
                    kunjungan         muka di Jakarta   
  -----------------------------------------------------------------------

### Hal yang secara eksplisit belum diputuskan

-   Model AI final untuk penggunaan produksi.
-   Posisi final toggle AI pada antarmuka.
-   Jumlah Key Takeaways yang harus ditampilkan.
-   Implementasi environment staging/testing terpisah.
-   Tanggal dan jam weekly meeting berikutnya.
-   Jadwal kunjungan atau pertemuan tatap muka tim dengan pihak DPEA.
-   Rencana percepatan terperinci untuk mengembalikan proyek ke
    timeline.

------------------------------------------------------------------------

## 11. Kesimpulan

Fokus utama tim setelah rapat adalah menuntaskan dan mematangkan **MVP 2
--- Summary & Key Takeaways** sebelum melanjutkan ke MVP 3. Secara
fungsional, alur upload, Summary, Key Takeaways, dan opsi AI sudah mulai
diperlihatkan, tetapi masih diperlukan perbaikan pada kualitas
pemrosesan dokumen, terutama dokumen yang memiliki banyak tabel, serta
penyederhanaan UI agar mudah digunakan oleh pengguna non-IT.

Dari sisi kebutuhan bisnis, DPEA menegaskan bahwa Summary harus membantu
pengguna memahami satu dokumen secara mandiri, sedangkan Analysis
digunakan untuk memetakan dan membandingkan ketentuan dengan regulasi
yang ada di Knowledge Base. Tim juga diminta menyiapkan aplikasi untuk
pengujian end-to-end setelah QA internal selesai.

Dari sisi manajemen proyek, status keterlambatan harus disampaikan
secara transparan. Perkiraan pergeseran jadwal sekitar satu minggu perlu
ditindaklanjuti dengan revisi timeline dan rencana percepatan yang
realistis hingga akhir Desember. Komunikasi tambahan dengan mitra dapat
dilakukan di luar weekly meeting apabila diperlukan.

------------------------------------------------------------------------

*Disusun sebagai dokumentasi internal tim HERO berdasarkan transkrip
Weekly Update tanggal 10 November 2026. Rangkuman ini tidak menggantikan
keputusan formal atau konfirmasi lanjutan dari Product Owner dan mentor
industri.*
