# MoM — Weekly Update #10 (Sprint 6 · Fase 3 Harmonisasi)

**Tanggal:** Selasa, 17 November 2026 · 14.00–14.40 · Zoom
**Hadir DPEA:** Pak Faris Budi (Product Owner), Pak Andika Prihandoko (Mentor)
**Hadir Tim:** Zaky (PM/BA), Ikhwan (Frontend), Rafli (Backend), Fathir (Data/ML), Hamdan (Infra/QA)
**Notulis:** Zaky
**Slide:** https://canva.link/4gvw3nvpo8yk5ae
**Rekaman:** https://youtu.be/6Rf5g08dQ7w

> Notulen ini mencakup rapat sampai penutupan oleh Zaky (± 14.40). Percakapan setelahnya tidak dicatat.

---

## 1. Ringkasan singkat

- Pertama kalinya rapat dibuka dengan slide posisi proyek, sesuai permintaan Pak Faris di Weekly #9.
- **Posisi:** Sprint 6, Fase 3 (Harmonisasi). Progres **39% selesai**, atau **67% bila termasuk pekerjaan yang masih *In Review***. Fase 2 masih dievaluasi dan diperbaiki; Harmonisasi sudah masuk tahap review.
- **Masukan Weekly #9 sudah dikerjakan:**
  - Metadata draft terisi otomatis.
  - Key Takeaways tidak lagi dibatasi 10 poin.
  - Layar Summary lebih ringkas.
  - Dokumen bertabel sudah terbaca, termasuk pasal dan ayatnya.
- **Link uji MVP 2 dibagikan besok (18 Nov).** DPEA mulai menguji sesuai skenario, dan temuannya disampaikan lewat grup WhatsApp.
- **Cara menentukan relasi peraturan (Fase 3):** cari dulu kata kunci seperti "perubahan atas", "mencabut", atau "dinyatakan tidak berlaku". Kalau ada, bandingkan langsung dengan peraturan yang dirujuk. Kalau tidak ada, anggap peraturan baru dan analisa pasal per pasal.
- **Ambang kemiripan diserahkan ke tim**, asal ditentukan lewat simulasi dan bisa dijelaskan — bukan *magic number*.
- **Kop catatan dinas sudah dijawab:** Kepada Kepala Departemen, Dari Analis Eksekutif, Perihal "Tanggapan atas …", Tanggal diisi manual.
- **Laporan kemajuan** ditambah timeline dan ilustrasi teknis; Pak Faris memaraf lebih dulu.

---

## 2. Laporan progres per orang

### Zaky — PM / BA
- Membuka dengan slide posisi proyek:
  - Sprint 6, Fase 3 (Harmonisasi).
  - Progres 39% selesai; 67% bila termasuk pekerjaan *In Review* (sudah selesai, tetapi masih direview).
  - Fase 2 masih dievaluasi dan diperbaiki sesuai masukan pekan lalu.
  - Pengerjaan Harmonisasi sudah masuk review, supaya pergeseran jadwal MVP 3 bisa ditekan.
- **Ringkasan per peran di slide:**
  - **Frontend:** halaman Summary selesai; ringkasan AI dan Deterministik ditampilkan terpisah dari Key Takeaways; Key Takeaways yang semula dibatasi 10 poin kini tampil semua.
  - **Backend:** isian otomatis draft diperbaiki — nomor, tahun, dan judul draft (termasuk draft perubahan) kini terisi sendiri.
  - **Data/ML:** skema ingest berhasil; Summary berjalan baik.
  - **Infra/QA:** formulir UAT untuk *business acceptance* sudah dibuat, dan lingkungan *staging* untuk UAT dipisahkan dari *deployment* harian.
- **Kendala tampilan:** pekan lalu tampilan dinilai terlalu menumpuk, tetapi tim tidak tahu data mana yang seharusnya ditampilkan karena semuanya terasa penting dan tidak ada *blueprint*. Butuh arahan Pak Faris.

### Hamdan — Infra / QA
- **Dokumen bertabel sudah teratasi.** Dua hari lalu, Key Takeaways dari dokumen bertabel belum bisa menampilkan pasal dan ayat. Sejak semalam sudah bisa.
- Diuji dengan dokumen "Agustus 3 In" dan "April 1 In" (dokumen 2025). Saat ditanya Pak Faris, Hamdan juga menyebut "Agustus 2" dan "April 4" sudah berhasil.
- Minta maaf karena tautan spreadsheet UAT yang dikirim sebelumnya tidak menyertakan link aplikasi (Vercel) untuk diuji.

### Ikhwan — Frontend
- **Unggah di Analisa Regulasi:** metadata kini terisi otomatis, sesuai pilihan "isi otomatis atau sembunyikan" dari pekan lalu. Penamaan berhasil; nomor sebagian besar terbaca, beberapa belum.
- **Summary mode Deterministik (tanpa AI):** menampilkan kerangka dokumen, pihak yang diatur, kewajiban utama, dan seterusnya.
- **Key Takeaways:** bisa difilter per kategori (kewajiban, pelaporan, larangan, sanksi), dan semua poin tampil tanpa batas 10.
- **Summary mode AI:** isinya kurang lebih sama, tetapi lebih ringkas.
- **Hasil Analisa:** disederhanakan, fokus pada mana yang baru, menggantikan, melengkapi, atau konflik terhadap Knowledge Base, dengan akses langsung ke PDF.
- Belum final: beberapa font belum sesuai dan warnanya terlalu banyak; akan didiskusikan dengan tim.

### Rafli — Backend
- Saat draft diunggah, isian di setiap kolom terisi otomatis dari hasil analisa, tanpa input manual.
- Temuan pada draft yang semula dikunci 10 kini dibuka semua; total temuan terlihat dan bisa dicek per bagian (sanksi, tugas, kewajiban, dan lainnya).
- Masih dikerjakan: ekspor ke PDF, Excel, dan Word. Format akhirnya belum ditentukan.

### Fathir — Data / ML
- Perbaikan pemrosesan tabel setelah masukan Hamdan. Semula diasumsikan dokumen masukan tidak berformat tabel, ternyata ada. Sudah diperbaiki dan lolos QA Hamdan.
- Ekstraksi memakai algoritma buatan sendiri, belum memakai AI.
- Alur AI: setelah Summary diklik, *toggle* AI diaktifkan dan AI mengolah ulang hasil Summary Deterministik agar bahasanya lebih natural.
- **Pertanyaan:** apa peran Knowledge Base dalam Analisa? Apakah hanya untuk mengubah status (misalnya dari rancangan menjadi dicabut), atau Knowledge Base yang menentukan apakah suatu peraturan dicabut? Hamdan menambahkan: di dokumen In, paragraf penutupnya menyebut "mengganti", dan di Out muncul sebagai "menggantikan", sehingga tim bingung soal definisi peran Knowledge Base.

---

## 3. Feedback dari mitra

### Dari Pak Andika

- Progres pekan ini cukup banyak di tengah padatnya kuliah.
- Mengutip Pak Faris: menghadapi tantangan, jangan berhenti, tetap maju. Tujuannya menyelesaikan proyek tepat waktu.
- Pertanyaan seperti prioritas tampilan atau kebingungan definisi Knowledge Base langsung disampaikan di grup, supaya tidak menjadi penghambat.
- **Hitungan progres:** Pak Andika menanyakan proyek ada berapa sprint; dijawab Zaky "sepertinya 13". Dengan dasar itu, menurut beliau Sprint 6 dari 13 dengan progres 67% masih optimis selesai tepat waktu (lihat catatan PM).
- Berharap bisa dipercepat, karena demo ke pimpinan kemungkinan menambah masukan, dan tim perlu waktu untuk menindaklanjutinya.

### Dari Pak Faris

**Untuk Hamdan — link uji:**
- Sebelum link dibagikan, pastikan semua jalan.
- **Besok (18 Nov) link dibagikan**, supaya DPEA bisa mulai menguji sesuai skenario. Hasilnya akan langsung di-*mention* di grup WhatsApp untuk diperbaiki.
- Perketat pengujian dengan skenario In/Out yang sudah diberikan. Formatnya beragam: teks, Word, dan tabel.

**Untuk Ikhwan — tampilan:**
- Masukan sudah diakomodasi. UI lebih simpel dan rapi, satu halaman tanpa perlu digeser.
- **Buka PDF di jendela baru.** Saat ini klik PDF masih mengarahkan ke halaman berikutnya. Padahal PDF dibuka untuk mencocokkan pernyataan sistem dengan redaksi aslinya, jadi harus bisa dilihat berdampingan.
- Masukan lebih detail menyusul setelah DPEA mencoba link-nya.

**Untuk Fathir dan Rafli — ekstraksi:**
- Masukan DPEA beragam: PDF hasil pindai yang belum di-OCR, dokumen bertabel, dokumen teks saja, dan lainnya.
- Alur yang diharapkan:
  1. Pastikan dokumen terbaca; kalau hasil pindai, di-OCR dulu.
  2. Uraikan penanda strukturnya — angka Romawi, huruf, pasal, dan sebagainya.
  3. *Pre-processing*.
  4. Baca satu per satu.
- Kalau ada kesulitan, Pak Faris siap membantu.
- Untuk Summary dan Key Takeaways mode AI: DPEA akan mencoba dulu, lalu memberi masukan apakah hasilnya terasa berbeda.

**Untuk Fathir — relasi peraturan dan peran Knowledge Base (Fase 3):**
- Cara DPEA mengidentifikasi relasi: lihat dulu peraturan itu tentang apa — benar-benar baru, atau sejak awal sudah memuat kata seperti "mengubah".
- **Cari kata kunci lebih dulu:** mengubah, mencabut, mencabut sebagian, menggantikan; di judul "Perubahan atas …"; "dicabut", "dinyatakan tidak berlaku".
  - **Kata kunci ditemukan** → ada relasi dengan peraturan sebelumnya nomor sekian. Bandingkan langsung dengan peraturan itu, lalu pasal per pasal.
  - **Tidak ditemukan** → anggap peraturan baru, lalu analisa pasal per pasal.
- **Alasannya efisiensi:** kalau Knowledge Base berisi ribuan peraturan dan draft menyebut "perubahan atas POJK sekian", langsung bandingkan dengan peraturan itu. Tanpa pengecekan kata kunci, sistem dipaksa membandingkan dengan seluruh Knowledge Base, dan itu tidak sanggup secara sumber daya.
- **Dampak pada status:**
  - **Perubahan** — hanya pasal yang disebut yang berubah. Kalau 10 dari 100 pasal diubah, 10 pasal lama otomatis tidak berlaku.
  - **Pencabutan** — biasanya berbunyi "mencabut dan dinyatakan tidak berlaku". Seluruh peraturan sebelumnya tidak berlaku.
- Menemukan relasi ini memang butuh banyak membaca; DPEA sendiri bisa butuh berhari-hari.
- **Kelengkapan daftar kata kunci** (Fathir menanyakan apakah ada selain mencabut, menggantikan, dan mencabut sebagian): Pak Faris akan mengikuti skenario uji Hamdan dulu, lalu memberi tahu apakah sudah mencakup semuanya.

**Untuk Hamdan dan Fathir — kop catatan dinas (template Out untuk tanggapan):**

| Bagian | Isi |
| --- | --- |
| Kepada | Selalu Kepala Departemen |
| Dari | Selalu Analis Eksekutif |
| Perihal | Jenis tanggapannya, yaitu "Tanggapan atas [peraturan]" |
| Tanggal | Diisi manual |

**Untuk Hamdan dan Fathir — ambang kemiripan "regulasi atau pasal serupa":**
- Tentukan sendiri ambangnya, misalnya 50 atau berapa pun. Yang penting informasinya tidak terlalu banyak tetapi tetap relevan.
- Simulasikan dulu, dan angkanya harus bisa dijelaskan — jangan *magic number* yang tidak jelas asalnya.
- Contoh: 75% ke atas boleh ditampilkan; di bawah 50% tidak layak dikutip. DPEA akan mengecek hasilnya.

**Untuk Zaky — laporan kemajuan:**
- Tambahkan dua hal: timeline dan ilustrasi teknis. Selebihnya sudah cukup.
- Pak Faris memaraf lebih dulu, lalu Pak Andika menandatangani.
- Menjawab Pak Andika: laporan mingguan dan dua mingguan bisa dikumpulkan tim sendiri. Yang butuh mitra hanya laporan kemajuan, yang menurut Zaky ada dua (tengah dan akhir semester) dan ikut dinilai untuk UTS/UAS. Pak Andika: kalau dinilai, akan dikondisikan sebaik mungkin.

**Rencana pertemuan:**
- Pak Andika minta dikabari kapan bisa berkunjung ke kampus bersama Pak Dwi untuk diagendakan. Tim juga dipersilakan berkunjung ke kantor OJK (Wisma Mulia 2).
- Zaky akan berkoordinasi dengan Pak Alfian selaku koordinator.

---

## 4. Keputusan

1. Link uji MVP 2 dibagikan 18 November. DPEA menguji sesuai skenario dan menyampaikan temuan lewat grup WhatsApp.
2. PDF sumber dibuka di jendela baru agar redaksinya bisa dicocokkan.
3. Relasi peraturan ditentukan lewat kata kunci lebih dulu. Ada kata kunci → bandingkan langsung dengan peraturan yang dirujuk; tidak ada → peraturan baru, dianalisa pasal per pasal.
4. Perubahan hanya membatalkan pasal yang disebut; pencabutan membatalkan seluruh peraturan sebelumnya.
5. Ambang kemiripan ditentukan tim lewat simulasi dan harus bisa dijelaskan; acuan awal: ≥ 75% layak ditampilkan, < 50% tidak layak dikutip.
6. Kop catatan dinas: Kepada Kepala Departemen; Dari Analis Eksekutif; Perihal "Tanggapan atas [peraturan]"; Tanggal diisi manual.
7. Laporan kemajuan ditambah timeline dan ilustrasi teknis; Pak Faris memaraf, lalu Pak Andika menandatangani.

---

## 5. Action item

### Zaky
- [ ] Luruskan hitungan sprint ke Pak Andika lewat grup: proyek punya 8 sprint, bukan 13 (lihat catatan PM)
- [ ] Tambahkan timeline dan ilustrasi teknis ke laporan kemajuan; kirim untuk diparaf Pak Faris dan ditandatangani Pak Andika
- [ ] Koordinasikan jadwal kunjungan Pak Andika dan Pak Dwi dengan Pak Alfian (koordinator)
- [ ] Rangkum masukan DPEA dari grup WhatsApp selama masa uji

### Hamdan
- [ ] Bagikan link uji (Vercel) beserta formulir UAT ke DPEA — 18 Nov
- [ ] Pastikan semua fungsi jalan sebelum link dibagikan
- [ ] Perketat uji skenario In/Out, termasuk dokumen bertabel, Word, dan hasil pindai

### Ikhwan
- [ ] PDF sumber dibuka di jendela baru
- [ ] Finalisasi font dan warna halaman hasil Analisa
- [ ] Tindak lanjuti masukan tampilan dari hasil uji DPEA

### Rafli
- [ ] Selesaikan ekspor PDF, Excel, dan Word; pertimbangkan format Out sebagai acuan
- [ ] Tangani nomor draft yang belum terbaca otomatis

### Fathir
- [ ] Deteksi relasi lewat kata kunci lebih dulu, lalu bandingkan dengan peraturan yang dirujuk saja
- [ ] Terapkan status: perubahan membatalkan pasal yang disebut; pencabutan membatalkan seluruh peraturan
- [ ] Simulasikan ambang kemiripan dan dokumentasikan alasannya
- [ ] Siapkan template catatan dinas sesuai kop yang disepakati, bersama Hamdan

### Mitra
- [ ] Pak Faris / Pak Andika: uji link MVP 2 dan sampaikan temuan di grup WhatsApp
- [ ] Pak Faris: cek kelengkapan daftar kata kunci relasi berdasarkan skenario uji Hamdan
- [ ] Pak Faris / Pak Andika: paraf dan tanda tangan laporan kemajuan
- [ ] Pak Faris / Pak Andika: akses OneDrive (#112), angka *ground truth* (#87), tanda tangan PRD (#45) — masih ditunggu

---

## 6. Catatan dari sisi PM

- **Hitungan sprint ke Pak Andika keliru dan perlu diluruskan.** Menurut PRD, proyek punya **8 sprint**, bukan 13. Sprint 6 (9–29 Nov) adalah sprint ketiga dari belakang. Per 17 Nov, 78 dari 115 hari proyek (± 68%) sudah berjalan, sedangkan pekerjaan yang benar-benar selesai baru 39%. Angka 67% masih memuat pekerjaan *In Review* dan MVP 2 yang belum diterima PO. Kesimpulan "masih optimis tepat waktu" di rapat bertumpu pada pembagi yang salah. Kirim koreksinya di grup sebelum dipakai di laporan kemajuan.
- **Laporkan 39% sebagai angka utama.** Angka 67% berguna sebagai *pipeline*, tetapi pekerjaan *In Review* baru bisa dihitung selesai setelah lolos UAT DPEA. Uji link besok adalah kesempatan pertama mengubah sebagian *In Review* menjadi *Done*.
- **Kebingungan peran Knowledge Base sudah terjawab, dan mesinnya sudah ada.** Pendekatan "kata kunci dulu" dari Pak Faris sama dengan yang dikerjakan `pipeline/hero/harmonisasi/refs.py`: membaca "Perubahan atas …", "… dicabut dan dinyatakan tidak berlaku", dan instruksi seperti "Ketentuan Pasal 5 diubah". Graf relasinya juga sudah mencatat ratusan relasi mencabut dan mengubah. Fathir sebaiknya memakai modul ini, bukan membangun ulang.
- **Ambang kemiripan sebagian menjawab isu lama #28 (ISU-06).** PO menyerahkan ambangnya ke tim, asal bisa dijelaskan lewat simulasi. Catat hasil simulasinya di issue itu, lalu #28 bisa ditutup atau diubah menjadi tugas internal.
- **Kop catatan dinas mengisi kebutuhan US-52 (template tanggapan, #76).** Jawaban Pak Faris sebaiknya dicatat di issue tersebut, supaya tidak hilang sampai Fase 4.
- **Izin mode AI untuk draft internal masih belum eksplisit.** Fathir menyebut *toggle* AI sudah jalan di Summary, padahal semua draft bersifat internal (Weekly #9) dan secara bawaan tidak boleh dikirim ke layanan eksternal. Pastikan apakah dokumen uji diunggah sebagai publik, atau izin sudah diubah — dan minta persetujuan tertulis Pak Faris (NFR-08) sebelum DPEA menguji mode AI dengan draft sungguhan.
- **"Tidak ada *blueprint*" muncul lagi untuk kedua kalinya** (Weekly #9 dan #10). Pak Faris belum menjawab langsung soal data apa yang harus ditampilkan; jawabannya akan datang dari hasil uji link. Rekam setiap masukan uji sebagai acuan tampilan, supaya tim tidak menebak lagi di Fase 3 dan 4.
