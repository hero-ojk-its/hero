# MoM — Weekly Update #7 (Minggu 3 Fase 2)

**Tanggal:** Selasa, 27 Oktober 2026 · ± 37 menit (sampai pukul 15.00) · Zoom
**Hadir DPEA:** Pak Faris Budi (Product Owner)
**Berhalangan DPEA:** Pak Andika Prihandoko (Mentor)
**Hadir Tim:** Ikhwan (Frontend), Rafli (Backend), Zaky (PM/BA — bergabung terlambat, menjelang akhir)
**Berhalangan:** Fathir (Data/ML) — ada urusan; Hamdan (Infra/QA) — mengurus proposal tugas akhir
**Notulis:** Zaky
**Rekaman:** *(menyusul)*

> Notulen ini mencakup sesi bersama Pak Faris sampai pukul 15.00. Diskusi internal tim setelahnya tidak dicatat di sini.

---

## 1. Ringkasan singkat

- Minggu ketiga Fase 2 (12 Okt – 8 Nov). Ikhwan membuka rapat mewakili PM dan mendemokan layar **Analisa Regulasi** yang sudah tersambung ke layanan analisa (ML), memakai data dummy.
- **Pak Faris meluruskan apa yang dimaksud "hasil analisa":** keluarannya harus dibandingkan dengan Knowledge Base, per pasal. Apakah pasal ini baru, sudah ada, menggantikan, atau melengkapi.
- **Knowledge Base hasil scraping adalah *ground truth*.** Tugas pertama modul ini: scraping sukses, lalu semua dokumen terbaca dan terpecah menjadi vektor.
- **Perlu statistik corong:** jumlah hasil scan → berhasil diunduh → tersimpan lokal → terbaca OCR. Termasuk PDF yang diproteksi dan hasil pindai *hard copy*.
- **Draft untuk analisa tidak boleh terkunci sebagai duplikat** saat diunggah berulang-ulang. Perlu *threshold* duplikat berdasarkan persentase teks.
- **Setiap temuan analisa wajib punya *hyperlink*** ke PDF sumbernya, untuk verifikasi manual.
- **AI wajib diberi guardrail:** hanya boleh berpendapat dari fakta di Knowledge Base internal.
- **8 November adalah batas rilis MVP Fase 2, termasuk UAT.** Pak Faris memberi skenario uji 1.480 + 20 dokumen.
- **VPS dibeli hari ini.** Kalau dana kurang, Pak Faris menalangi dulu.

---

## 2. Laporan progres per orang

### Ikhwan — Frontend *(membuka rapat mewakili PM)*
- Menyampaikan bahwa Zaky, Fathir, dan Hamdan berhalangan.
- **Backlog:** Sprint 4 sudah diperbarui. Sebagian besar item *In Review / Testing* dan tinggal direview, terutama bagian Summary; sebagian masih *In Progress*.
- **Demo layar Analisa Regulasi** (data dummy buatan AI, belum dari Knowledge Base):
  - Unggah draft berjalan dan layanan ML sudah tersambung.
  - Mode Deterministik; kolom regulasi dan tanggal opsional.
  - Hasil: ringkasan, poin utama, dasar hukum (kosong karena data dummy), dan informasi dokumen.
  - Ekspor ke Word, Excel, dan JSON.
  - PDF asli bisa dibuka.
- Fokus Ikhwan di Fase 2; beberapa bagian sudah dijahit ke backend.
- Belum mencoba dengan dokumen peraturan nyata, karena masih menguji fungsionalitasnya.

### Rafli — Backend
- Sebagian besar masukan Pak Faris berada di ranah backend: diproses di backend dulu, lalu frontend tinggal meminta hasilnya.
- Progres backend sejalan dengan yang didemokan Ikhwan di layar Analisa.
- Uji backend dari OneDrive dan tautan situs: hampir semua dokumen terbaca dan terunduh.
- Masih menunggu bagian Fathir (Data/ML), dan belum bisa menangkap keseluruhan karena personelnya tidak hadir.

### Zaky — PM / BA
- Bergabung menjelang akhir rapat.
- Menjawab Pak Faris soal timeline: Fase 2 berjalan 12 Okt – 8 Nov, jadi berakhir minggu depan. Revisi terakhir minggu depan, dan 8 November Fase 2 selesai.
- Menegaskan fokus Fase 2: *go through* Knowledge Base — apa pun yang sudah masuk harus bisa dicek, benar-benar masuk atau terhalang.

---

## 3. Feedback dari mitra

### Dari Pak Faris

**Untuk Ikhwan dan Rafli — apa yang dimaksud "hasil analisa":**
- **Saat unggah, dokumen hanya dipecah** menjadi judul, nomor, pasal, dan seterusnya. Itu belum analisa.
- **Analisa baru terjadi saat dibandingkan dengan Knowledge Base.** Dalam mode Deterministik, sistem memeriksa apakah pasal atau judul ini pernah disebut di Knowledge Base. Keluarannya:
  1. **Baru** — belum ada di Knowledge Base.
  2. **Sama** — dokumen yang sama sudah pernah masuk. Contoh: pukul 07.00 dokumen diunggah, pukul 07.10 dokumen yang sama diunggah lagi, maka hasilnya "pasal yang sama".
  3. Mode Deterministik membandingkan secara *letterlijk*, kata per kata.
- **Frame kiri (struktur dokumen) dan tengah (naskah)** bisa ditampilkan tanpa analisa. **Frame kanan (hasil analisa)** harus membandingkan dengan Knowledge Base yang ada. Tanpa Knowledge Base sebagai *ground truth*, sistem tidak punya dasar menganalisa.
- **Kebutuhan bisnis DPEA**, untuk draft dengan misalnya 100 pasal:
  1. Untuk setiap pasal: sudah pernah ada di peraturan lain, atau benar-benar baru?
  2. Kalau sudah ada: draft ini **melengkapi**, **menggantikan**, atau **menghapus berlakunya** pasal lama? Kalau menggantikan, pasal lama otomatis tidak berlaku.
- **Contoh perubahan peraturan:** POJK 1/2026 tentang *Rule Making Rule* punya 100 pasal. Enam bulan kemudian terbit POJK 2/2026 tentang Perubahan atas POJK 1/2026, yang hanya memuat 10 pasal yang diganti. Sembilan puluh pasal lainnya tetap mengikuti peraturan sebelumnya. Karena itu struktur dokumen per bab dan pasal harus terbaca.
- **Hyperlink untuk verifikasi manusia.** Kalau sistem menyatakan "Pasal 1 ini sudah pernah muncul di POJK Nomor 7 Tahun 2024 Pasal 1", pengguna harus bisa mengklik dan membuka PDF sumbernya untuk memastikan bunyinya sama. Klik membawa ke sumber yang dikutip, bukan kembali ke draft.

**Untuk Ikhwan — duplikat pada unggahan analisa:**
- **Cek duplikat berlaku untuk semua jalur**, baik hasil scraping maupun unggahan. Ikhwan mengonfirmasi keduanya sudah tercakup, dan menunjukkan riwayat: unggahan pertama berhasil, unggahan kedua ditandai duplikat.
- **Analogi Turnitin:** kalau unggahan dicentang "masuk database", mengunggah naskah yang sama lagi lima menit kemudian akan menghasilkan kemiripan 100%.
- **Draft dikerjakan berulang:** unggah draft pertama, cek, unggah draft kedua, cek, dan seterusnya, sebelum jawaban tertulis final dikirim. Kalau draft kedua dianggap duplikat, hasilnya akan sama persis, padahal yang diharapkan adalah masukan baru atas draft kedua.
- **Tetapkan *threshold* duplikat** dalam persentase dari seluruh teks yang diunggah. Ikhwan akan memisahkan "unggah manual untuk analisa" dari unggah manual di Ingest Dokumen.

**Untuk Ikhwan dan Rafli — kerjakan bertahap:**
1. Pastikan PDF yang masuk ter-OCR.
2. Pasal per pasal, judul, dan nomor terbaca, lalu semua masuk ke penyimpanan vektor.
3. Baru setelah itu analisa. Boleh membandingkan pasal secara *letterlijk*, boleh diawali cek "dokumen sama pernah diunggah", boleh juga model lain.
- **Skenario sulit yang harus diuji:** PDF yang tidak bisa di-OCR dan PDF yang diproteksi (tidak bisa disalin).
- **Guardrail AI:** kalau memakai AI, jangan izinkan memberi pendapat di luar fakta yang diberikan. Dari percobaan DPEA, AI yang boleh mengambil data di luar Knowledge Base cenderung mengarang hal yang tidak ada di peraturan internal mana pun.

**Untuk Rafli — Knowledge Base sebagai *ground truth*:**
- Pada prinsipnya, semua dokumen yang terdeteksi saat scraping ditarik, diunduh ke lokal, dipecah (*chunking*), dan masuk vektor.
- Tiga sumber (dua situs dan satu folder OneDrive) berisi dokumen final yang sudah dirilis, sehingga menjadi *ground truth*. Analisa draft baru dibandingkan dengan kondisi peraturan yang ada.
- **Tugas pertama modul ini:** scraping sukses dulu, lalu dokumen diubah menjadi potongan vektor agar bisa dibaca.
- **Buat statistik corongnya:** jumlah hasil scan pertama → berhasil diunduh → pindah ke lokal → terbaca OCR. Contoh: 500 berkas di OneDrive plus 2 × 500 dari dua situs = 1.500 dokumen; dari 1.500 itu, berapa yang berhasil terbaca?
- **Tiga jenis PDF:**
  1. Hasil konversi Word — bisa langsung dibaca.
  2. PDF diproteksi (tidak bisa disalin) — belum tentu terbaca.
  3. Hasil pindai *hard copy* — kadang tidak bisa di-OCR. Peraturan lama yang masih berlaku banyak yang berbentuk ini, dan kadang hanya terbaca sebagian.
- Jenis 2 dan 3 belum dicek. Dokumen yang gagal harus ketahuan supaya bisa dibuka manual.
- Setelah semua masuk Knowledge Base, Ikhwan tinggal menjahit tampilannya.

**Timeline dan pengujian:**
- **8 November** (hari Minggu minggu depan) adalah batas rilis MVP Fase 2, **sudah termasuk UAT**, karena tim memakai Agile.
- Pekerjaan analisa (Fase 3, 4, 5) akan berat. Fase 2 harus selesai dulu: tanpa kepastian semua dokumen terbaca dan bisa ditautkan, fase berikutnya tidak bisa jalan.
- **Beda Fase 2 dan harmonisasi:**
  - Fase 2 mencari apakah pasal sudah ada, menggantikan, atau benar-benar baru.
  - Harmonisasi (Fase 3) memeriksa apakah peraturan baru bertabrakan dengan peraturan yang ada. Contoh: peraturan pasar modal mengatur penawaran saham oleh perusahaan terbuka; lalu ada peraturan perbankan baru yang membolehkan BPR menerbitkan surat utang atau saham. Hubungannya bisa sehat (saling melengkapi) atau tidak sehat (bertolak belakang).
- **Skenario uji dari Pak Faris:** dari 1.500 dokumen, masukkan 1.480 ke Knowledge Base dan sisihkan 20. Setelah Knowledge Base terisi, masukkan 20 dokumen itu sebagai test case — terbaca atau tidak? Lalu masukkan lagi 20 dokumen yang sudah masuk — seharusnya dikenali karena sudah ada di Knowledge Base.

**VPS dan pendanaan:**
- Beli VPS hari ini. Kalau dana kurang, japri Pak Faris; beliau menalangi dulu, supaya tidak terlewat batas 2 November. Proyek masih berjalan sampai Desember.
- Kirim detailnya ke Pak Faris. Beliau bisa mentransfer, atau tim membeli dulu lalu di-reimburse.

**Lain-lain:** Pak Faris menyinggung pemakaian langganan Claude / GPT oleh Fathir untuk pekerjaan ini (transkrip bagian ini kurang jelas).

---

## 4. Keputusan

1. Hasil analisa (frame kanan) adalah perbandingan dengan Knowledge Base, per pasal: baru / sudah ada; bila sudah ada — melengkapi, menggantikan, atau menghapus berlakunya.
2. Knowledge Base hasil scraping tiga sumber adalah *ground truth* pembanding.
3. Urutan kerja Fase 2: scraping sukses → OCR → pasal, judul, nomor terbaca → vektor → baru analisa.
4. Setiap temuan analisa memuat *hyperlink* ke PDF sumber yang dikutip.
5. AI hanya boleh berpendapat dari fakta di Knowledge Base internal (guardrail).
6. Unggahan draft untuk analisa dipisahkan dari unggahan ke Knowledge Base, dan memakai *threshold* duplikat berbasis persentase teks.
7. 8 November adalah batas rilis MVP Fase 2, termasuk UAT.
8. VPS dibeli hari ini; Pak Faris menalangi bila dana kurang.

---

## 5. Action item

### Zaky
- [ ] Pastikan VPS dibeli hari ini; kirim detail biaya ke Pak Faris dan kumpulkan nota sebelum 2 November
- [ ] Bahas hasil rapat dengan tim (Fathir dan Hamdan tidak hadir)
- [ ] Selaraskan backlog Fase 2 dengan definisi "hasil analisa" dari Pak Faris (lihat catatan PM)
- [ ] Masukkan skenario uji 1.480 + 20 dokumen ke Test Plan
- [ ] Tagih ke mitra: akses OneDrive (#112), angka *ground truth* (#87), contoh surat tanggapan (#27), tanda tangan PRD (#45)

### Ikhwan
- [ ] Frame kanan menampilkan hasil perbandingan dengan Knowledge Base, bukan hanya ringkasan dokumen
- [ ] *Hyperlink* dari setiap temuan ke PDF sumber yang dikutip
- [ ] Pisahkan "unggah untuk analisa" dari unggah manual Ingest Dokumen
- [ ] Usulkan *threshold* duplikat untuk draft yang diunggah berulang
- [ ] Uji dengan dokumen peraturan nyata dari Knowledge Base, bukan data dummy
- [ ] Presentasikan perbaikannya di rapat berikutnya

### Rafli
- [ ] Statistik corong per sumber: hasil scan → terunduh → tersimpan lokal → terbaca OCR
- [ ] Uji PDF yang diproteksi dan PDF hasil pindai *hard copy*; catat dokumen yang gagal supaya bisa dibuka manual
- [ ] Logika perbandingan per pasal dengan Knowledge Base di backend (baru / sama / menggantikan / melengkapi)
- [ ] Pastikan seluruh dokumen hasil scraping masuk Knowledge Base dan vektor (*ground truth*)

### Fathir *(tidak hadir — disampaikan lewat Zaky)*
- [ ] Guardrail AI: keluaran hanya dari fakta Knowledge Base internal
- [ ] Dukung logika perbandingan per pasal dari lapisan data

### Hamdan *(tidak hadir — disampaikan lewat Zaky)*
- [ ] Siapkan VPS baru bersama Fathir begitu dibeli
- [ ] Siapkan skenario uji 1.480 + 20 dokumen untuk UAT Fase 2

### Mitra
- [ ] Pak Faris: talangi biaya VPS bila dana tim kurang
- [ ] Pak Faris / Pak Andika: akses OneDrive (#112), angka *ground truth* (#87), contoh surat tanggapan (#27) — masih ditunggu
- [ ] Pak Andika: tanda tangan PRD (#45)

---

## 6. Catatan dari sisi PM

- **Definisi "analisa" Pak Faris berbeda dari isi backlog Fase 2.** Backlog Fase 2 (US-35, US-36) berfokus pada ringkasan dan Key Takeaways per dokumen. Yang diminta Pak Faris adalah status setiap pasal terhadap Knowledge Base — baru, sama, menggantikan, atau melengkapi. Ini lebih dekat ke pencocokan rujukan dan klasifikasi temuan (US-43, US-46) yang dijadwalkan di Fase 3. Kabar baiknya, mesin harmonisasi di lapisan data sudah memberi label `menggantikan`, `memperjelas`, `duplikasi`, dan `pasal_baru` per pasal dengan recall 90,1%, sehingga bisa dipakai untuk layar Analisa. Lingkup ini perlu dikonfirmasi ke Pak Faris dan dicatat di backlog, karena menggeser pekerjaan Fase 3 ke Fase 2.
- **Aturan duplikat Weekly #6 tidak boleh berlaku untuk draft.** Unggahan di layar Analisa sudah memakai peran `draft_kajian`, sehingga draft tidak masuk korpus pembanding (US-15a). Tetapi aturan Weekly #6 — judul + nomor peraturan sama berarti duplikat — akan menolak draft kedua yang judul dan nomornya sama dengan draft pertama. Aturan itu sebaiknya hanya berlaku untuk dokumen eksisting di Knowledge Base, sedangkan draft memakai *threshold* kemiripan teks seperti yang diminta Pak Faris.
- **Statistik corong sudah dimulai di lapisan data.** `pipeline/docs/DATA_QUALITY_REPORT.md` punya tabel "Corong panen dokumen" (terdaftar → dapat diunduh → sudah di KB). Yang belum ada adalah tahap "terbaca OCR" dan pemisahan jenis PDF (diproteksi, hasil pindai). Rafli bisa melanjutkan tabel itu alih-alih membuat dari nol.
- **Guardrail AI sudah ada di lapisan data.** `pipeline/hero/analysis/ai.py` menolak keluaran AI yang mengubah angka atau mengarang fakta, dan menolak mengirim dokumen berklasifikasi internal ke layanan luar. Pastikan layar Analisa memakai jalur itu.
- ***Hyperlink* ke sumber sudah ada di backlog.** Ini US-37 (#59, lompat ke teks pasal) dan US-49a (#72, buka PDF asli dari temuan). Viewer PDF dari US-28 bisa dipakai ulang.
- **Jadwal sangat sempit.** Rilis 8 Nov sudah termasuk UAT. Menurut aturan H-14, pengujian M2 seharusnya mulai 25 Okt, tetapi layar Analisa masih memakai data dummy, Knowledge Base staging belum terisi penuh, dan VPS baru belum dibeli sejak Weekly #6 (13 Okt).
- **Kehadiran.** Tiga dari lima anggota berhalangan saat topik utamanya adalah analisa, termasuk Fathir sebagai pemilik mesin analisa. Ikhwan tidak bisa menjawab pertanyaan logika bisnis dari Pak Faris. Untuk rapat berikutnya, demo analisa sebaiknya dibawakan Fathir atau Rafli dengan data Knowledge Base nyata.
- **Penomoran.** Tidak ada catatan rapat 20 Oktober di repo, sehingga notulen ini diberi nomor #7.
