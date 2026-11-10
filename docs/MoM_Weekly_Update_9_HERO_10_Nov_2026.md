# MoM --- Weekly Update #9 (Tindak Lanjut MVP 2)

## Informasi Rapat

  -----------------------------------------------------------------------
  Keterangan                          Detail
  ----------------------------------- -----------------------------------
  Hari/Tanggal                        Selasa, 10 November 2026

  Durasi                              ±50 menit

  Media                               Zoom Meeting

  Agenda                              Weekly Update dan Evaluasi MVP 2
                                      --- Summary & Key Takeaways

  Mitra                               Faris Budi (DPEA), Andika Wahyu
                                      Prihandoko (bergabung pada
                                      pertengahan rapat)

  Tim HERO                            Zaky (PM/BA), Ikhwan (Frontend),
                                      Rafli (Backend), Izzul (Infra/QA)

  Tidak hadir                         Fathir (Data/ML) --- progres
                                      disampaikan oleh Zaky

  Notulis                             Zaky
  -----------------------------------------------------------------------

## 1. Ringkasan Rapat

Rapat membahas perkembangan MVP 2, yaitu fitur **Summary & Key
Takeaways**, sekaligus mengevaluasi hasil implementasi dan kebutuhan
perbaikan berdasarkan masukan dari pihak DPEA.

Secara umum, fitur utama sudah mulai dapat diuji, tetapi masih
diperlukan penyempurnaan pada hasil ringkasan, perbandingan dengan
knowledge base (KB), dan kemudahan penggunaan antarmuka. Tim juga perlu
menyesuaikan rencana pengerjaan karena evaluasi MVP 2 diperkirakan
membutuhkan tambahan waktu sekitar satu minggu sebelum berlanjut ke MVP
3.

## 2. Laporan Progres Tim

### 2.1. Project Management / Business Analyst --- Zaky

-   Menyampaikan estimasi progres proyek sekitar **40--45%**, dengan
    pengerjaan berada pada fase 2 dari 5 fase.
-   Menjelaskan bahwa laporan progres perlu menunjukkan posisi aktual
    terhadap jadwal, keterlambatan, penyesuaian timeline, serta rencana
    percepatan hingga Desember.
-   Menyampaikan hasil eksperimen model yang dilakukan oleh Fathir:
    -   **Gemini Pro:** hasil paling komprehensif, tetapi lebih lambat
        dan membutuhkan biaya lebih besar.
    -   **Gemini Flash:** keseimbangan antara kualitas dan kecepatan.
    -   **Gemini Flash Lite:** lebih cepat dan murah, tetapi hasil
        cenderung terlalu singkat.
-   Menyampaikan bahwa pemilihan model perlu mempertimbangkan batas
    penggunaan API, termasuk RPM, TPM, dan TPD, serta kemungkinan
    mekanisme fallback.

### 2.2. Frontend --- Ikhwan

-   Mendemonstrasikan antarmuka upload dan riwayat dokumen,
    deterministic summary, AI analysis, serta perbandingan dengan
    knowledge base.
-   Menerima masukan agar tampilan lebih sederhana dan mudah dipahami
    oleh pengguna non-IT.
-   Beberapa field dinilai belum diperlukan, seperti alasan approval,
    status publik/nonpublik, dan persetujuan publikasi.
-   Metadata dokumen seperti judul, nomor, jenis regulasi, dan sektor
    diharapkan dapat diekstrak secara otomatis.
-   Penempatan opsi AI pada fitur Summary masih perlu dipertimbangkan,
    apakah ditampilkan sebelum atau sesudah hasil deterministic summary.

### 2.3. Backend --- Rafli

-   Menjelaskan cakupan ringkasan, meliputi identitas dokumen, struktur,
    pihak terkait, kewajiban, pelaporan, sanksi, pencabutan, dan masa
    berlaku.
-   Poin-poin ringkasan dikelompokkan berdasarkan prioritas.
-   Pada perbandingan dengan KB, kategori temuan mencakup **baru, sama,
    menggantikan, dan konflik**.
-   Indikasi kemiripan sekitar 80% digunakan sebagai salah satu petunjuk
    untuk kategori "menggantikan".
-   Pemetaan perlu dilakukan hingga tingkat pasal/ayat, termasuk
    ketentuan yang sudah tidak berlaku atau telah digantikan.

### 2.4. Data/ML --- Fathir

-   Fathir tidak hadir dalam rapat. Zaky menyampaikan hasil eksperimen
    model yang sebelumnya telah dilakukan.
-   Hasil eksperimen dan pertimbangan pemilihan model dirangkum pada
    bagian laporan Zaky.

### 2.5. Infrastruktur / QA --- Izzul

-   Menyampaikan bahwa hasil ringkasan lebih baik pada dokumen dengan
    struktur pasal dan ayat dibandingkan dokumen yang banyak menggunakan
    tabel.
-   Dokumen berbasis tabel masih menjadi kendala dan perlu ditingkatkan.
-   Pada pengujian sebelumnya terhadap 10 pasal, sekitar 5 pasal
    berhasil diberi tag. Hasil tersebut membaik setelah koordinasi dan
    pengerjaan bersama Fathir.
-   Algoritma masih perlu disempurnakan melalui pengujian dengan variasi
    dokumen.

## 3. Masukan dari Mitra

### 3.1. Faris Budi --- DPEA

-   Alur kerja DPEA dimulai dengan membaca regulasi secara menyeluruh
    untuk memahami latar belakang, substansi, dan strukturnya.
-   Setelah itu, bagian yang relevan dengan bidang TI disaring, misalnya
    kewajiban pelaporan daring, pertukaran data, penggunaan aplikasi,
    dan kewajiban pelaporan.
-   Ringkasan akhir perlu dibuat singkat dan berfokus pada ketentuan
    yang relevan.
-   Perlu dibedakan secara jelas antara:
    -   **Summary:** merangkum dokumen yang diunggah.
    -   **Analysis:** membandingkan dokumen dengan kumpulan regulasi
        dalam knowledge base.
-   Contoh dokumen Input/Output yang telah diberikan DPEA dapat
    digunakan sebagai referensi. Output merupakan shortlist dari
    longlist temuan.
-   Perlu ditinjau apakah hasil temuan sebaiknya menampilkan seluruh
    temuan atau hanya sejumlah temuan teratas. Keputusan belum dapat
    ditentukan sebelum contoh dokumen ditinjau lebih lanjut.
-   Meminta tim mengirimkan tautan untuk pengujian end-to-end setelah
    siap.

### 3.2. Andika Wahyu Prihandoko

-   Mengingatkan tim agar mengupayakan penyelesaian MVP 2 tanpa menambah
    keterlambatan yang tidak diperlukan.
-   Mendorong komunikasi lebih aktif melalui WhatsApp atau sesi Zoom
    tambahan apabila terdapat kendala, tanpa harus menunggu weekly
    meeting.
-   Perbedaan pendapat internal diharapkan dapat diselesaikan terlebih
    dahulu dengan koordinasi bersama Zaky sebagai PM.
-   Tim dipersilakan meminta arahan mentor apabila membutuhkan bantuan.
-   Menegaskan bahwa masukan diberikan untuk membangun pemahaman
    terhadap pelaksanaan proyek di lingkungan kerja nyata.

## 4. Keputusan dan Kesepakatan

1.  Fokus pengerjaan tim masih pada penyempurnaan **MVP 2 --- Summary &
    Key Takeaways**.
2.  Jadwal MVP 3 berpotensi bergeser sekitar satu minggu karena MVP 2
    masih memerlukan evaluasi dan perbaikan.
3.  Antarmuka perlu disederhanakan agar lebih mudah digunakan oleh
    pengguna non-IT.
4.  Fitur Summary dan Analysis harus memiliki fungsi dan keluaran yang
    jelas serta tidak tumpang tindih.
5.  Pengujian internal end-to-end perlu dilakukan sebelum tautan
    aplikasi dibagikan kepada pihak DPEA.
6.  Setelah pengujian internal, Faris dan Andika akan melakukan
    pengujian dari sisi kebutuhan bisnis (*business acceptance*).
7.  Tim perlu meningkatkan komunikasi dan koordinasi di luar weekly
    meeting apabila diperlukan.

## 5. Action Items

  -----------------------------------------------------------------------
  No.                     PIC                     Tindak Lanjut
  ----------------------- ----------------------- -----------------------
  1                       Zaky (PM/BA)            Mengirimkan laporan
                                                  progres kepada Pak
                                                  Faris melalui WhatsApp
                                                  untuk ditinjau dan
                                                  ditandatangani.

  2                       Zaky (PM/BA)            Memperjelas posisi
                                                  progres terhadap
                                                  timeline,
                                                  keterlambatan, revisi
                                                  jadwal, dan rencana
                                                  percepatan hingga
                                                  Desember.

  3                       Ikhwan (Frontend)       Menyederhanakan
                                                  antarmuka dan
                                                  mengevaluasi field yang
                                                  tidak diperlukan.

  4                       Ikhwan (Frontend)       Meninjau alur dan
                                                  penempatan opsi AI pada
                                                  fitur Summary.

  5                       Rafli (Backend)         Berkoordinasi dengan
                                                  Fathir untuk menyiapkan
                                                  tautan aplikasi yang
                                                  dapat digunakan untuk
                                                  pengujian end-to-end.

  6                       Rafli dan Fathir        Menindaklanjuti
                                                  penyempurnaan Summary
                                                  dan Analysis, termasuk
                                                  pemetaan temuan pada
                                                  tingkat pasal/ayat.

  7                       Izzul (QA)              Melakukan pengujian
                                                  internal terhadap
                                                  variasi dokumen, hasil
                                                  Summary dan Key
                                                  Takeaways, aksi AI,
                                                  serta fungsi aplikasi.

  8                       Izzul (QA)              Menguji peringatan
                                                  unggah dokumen duplikat
                                                  dan memastikan
                                                  perbedaan dokumen yang
                                                  di-ingest ke KB dengan
                                                  dokumen yang hanya
                                                  dianalisis.

  9                       Seluruh tim             Melakukan koordinasi
                                                  tambahan apabila
                                                  terdapat kendala atau
                                                  keputusan teknis yang
                                                  menghambat progres.
  -----------------------------------------------------------------------

## 6. Catatan Tambahan

-   Laporan progres untuk weekly meeting berikutnya disarankan dibuat
    ringkas, sekitar 1--2 slide, dengan status progres yang mudah
    dipahami.
-   Pengujian perlu mencakup dokumen dengan struktur berbeda, khususnya
    dokumen yang banyak memuat tabel.
-   Setelah rapat, tim turut membahas kebutuhan lingkungan
    testing/staging terpisah agar pengujian DPEA tidak terganggu oleh
    proses deployment. Hal ini masih berupa pembahasan internal dan
    belum menjadi keputusan final.
-   Keterbatasan pendanaan perjalanan ke Jakarta sempat dibahas. Belum
    ada keputusan atau pengaturan kunjungan lanjutan yang ditetapkan
    dalam rapat.
-   Weekly meeting berikutnya direncanakan pada minggu berikutnya.
    Tanggal dan jam belum ditentukan.

------------------------------------------------------------------------

*Dokumen ini disusun berdasarkan pembahasan dalam weekly meeting pada 10
November 2026.*
