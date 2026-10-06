# MoM — Weekly Update #5 (Minggu 4 Fase 1)

**Tanggal:** Selasa, 6 Oktober 2026 · ± 23 menit · Zoom
**Hadir DPEA:** Pak Andika Prihandoko (Mentor)
**Berhalangan DPEA:** Pak Faris Budi (Product Owner) — training di Jakarta
**Hadir Tim:** Zaky (PM/BA), Ikhwan (Frontend), Rafli (Backend), Hamdan (Infra/QA), Fathir (Data/ML — bergabung di tengah)
**Notulis:** Zaky
**Rekaman:** *(menyusul)*

---

## 1. Ringkasan singkat

- Minggu terakhir Fase 1, lima hari sebelum rilis MVP Fase 1 (11 Okt). Format rapat berbeda dari biasanya: fokus pada **demo target MVP Fase 1** di aplikasi staging (frontend di Vercel).
- Feedback Pak Faris di Weekly #4 dilaporkan sudah dikerjakan: format nama berkas dinamis, halaman detail peraturan untuk verifikasi, dan integrasi frontend–backend sehingga alur berjalan *end-to-end*.
- **Scan situs regulasi OJK dan JDIH berhasil** di lingkungan lokal. Data hasilnya belum ikut ke staging, sehingga dashboard dan Knowledge Base di staging masih nol.
- **Sinkron OneDrive belum bisa jalan.** Akses ke dokumen di dalam folder OneDrive masih tertutup.
- **Temuan QA:** API bisa diakses tanpa login. Berisiko begitu dokumen non-publik masuk Knowledge Base.
- **Backend dipindah ke VPS**, satu tempat dengan worker scraper. Frontend tetap di Vercel.
- Pak Andika: **tidak ada revisi** — aplikasi dinilai cukup baik dan lengkap. Pekan ini tim menutup seluruh error Fase 1 supaya mulai 12 Okt bisa fokus ke Fase 2.

---

## 2. Laporan progres per orang

### Zaky — PM / BA
- Sprint 2 (s.d. 27 Sep) selesai semua. Sisa administrasinya hanya PRD yang belum ditandatangani.
- Sprint 3 sudah berjalan; sebagian story selesai, sebagian masih dikerjakan.
- Mengulang target MVP Fase 1:
  - Menarik dokumen dari tiga situs sumber yang diinput manual.
  - Unggah manual PDF berfungsi.
  - Membaca minimal satu folder lokal dan satu folder OneDrive public.
  - Minimal 20 dokumen peraturan masuk Knowledge Base.
- Hasil scan akan dibandingkan dengan *ground truth* DPEA untuk melihat cakupan scraping. Unduh bukan kriteria utama karena dipengaruhi koneksi dan kapasitas penyimpanan staging.
- Menu aplikasi di staging: Dashboard, Knowledge Base, Ingest Dokumen, Analisa Regulasi, dan Harmonisasi.

### Hamdan — Infra / QA
- Menyusun dokumen **Cakupan Uji HERO**. Areanya: Infra, Scraping, Unggah & Ingest, Knowledge Base, Platform, dan Frontend.
- **Uji Infra 1–7:** hanya satu yang gagal, yaitu **API dapat diakses tanpa login**. Data bisa dibaca dari jendela *incognito* tanpa masuk aplikasi. Saat ini datanya masih kosong, tetapi begitu dokumen non-publik masuk Knowledge Base, isinya ikut terbuka. Perlu dirundingkan tim dan diperbaiki bersama Rafli dan Fathir.
- **Uji Infra 7–14** menyangkut VPS. Hamdan akan memberi akses VPS dan laporan uji ke Fathir dan Rafli supaya ikut mengerjakan dan mengisi laporannya.

### Ikhwan — Frontend
- Demo di staging:
  - **Dashboard** berisi kartu total regulasi, berlaku, dicabut / tidak berlaku, dan diubah. Ada statistik per kategori yang bisa diklik (permintaan Pak Faris), per jenis regulasi, dan per tahun, serta ringkasan aktivitas sistem. Sebagian masih kosong karena belum ada dokumen.
  - **Knowledge Base** berisi pencarian dan filter kategori, jenis, tahun, bidang, dan status.
  - **Ingest Dokumen** punya tiga jalur: scraping URL, sinkron OneDrive / folder lokal, dan unggah manual. Sudah disesuaikan dengan feedback minggu lalu.
- Lingkup Fase 1 berhenti di Ingest: memastikan scraping, unggah manual, dan sinkron folder sudah jalan.

### Rafli — Backend
- Sebelum di-*deploy*, scraping dan sinkronisasi sudah diuji di lokal. Menurut Rafli, ± 98% berjalan lancar.
- Data hasil uji tersimpan di Docker lokal dan tidak ikut terbawa ke staging. Karena itu dashboard, Knowledge Base, dan Ingest di staging masih menunjukkan nol.
- **Scan regulasi OJK dan JDIH berhasil.** Diuji selama satu sampai dua hari, terakhir semalam bersama Hamdan.
- **Kendala OneDrive:** dokumen di dalam folder OneDrive masih tertutup dan tim belum punya aksesnya, jadi sinkron OneDrive belum bisa dijalankan.
- Soal error login yang ditemukan Hamdan: login masih di-*hold* sesuai arahan Pak Faris (Weekly #3). Belum jelas apakah aplikasi butuh halaman login, karena pemakaiannya internal.

### Fathir — Data / ML
- **Kendala deploy:** worker scraper di-*deploy* di VPS, sedangkan backend semula direncanakan di Vercel. Kombinasi itu merepotkan.
- **Solusi sementara:** backend ikut di-*deploy* di VPS. Backend langsung memanggil scraper dan menyimpan hasil secara lokal di VPS.
- **Berikutnya:** berkoordinasi dengan Hamdan soal benchmark penyimpanan — apakah memakai *vector database* atau tidak. Waktu proses *semantic search* belum di-benchmark.

---

## 3. Feedback dari mitra

### Dari Pak Andika

**Umum:**
- **Tidak ada revisi hari ini.** Aplikasi dinilai cukup baik dan cukup lengkap. Pak Andika menghargai usaha tim.
- Feedback Pak Faris minggu lalu yang sudah dikerjakan **diminta disampaikan juga di grup**, karena Pak Faris tidak hadir.
- **Singkatan harus ditulis panjang** di materi dan laporan, supaya tidak menimbulkan persepsi berbeda. Contoh: "KB" di laporan QA perlu ditulis "Knowledge Base".

**Login dan role:**
- Tim tidak perlu login ke ojk.go.id maupun JDIH karena datanya publik. Kalau ternyata ada akses yang dibutuhkan, OJK siap membantu secepatnya.
- Login yang dimaksud adalah login ke aplikasi HERO (klarifikasi Zaky). Role-nya masih menunggu konfirmasi Pak Faris, misalnya admin dan user.
- Saran Pak Andika: **role sesedikit mungkin.** Makin banyak role, makin repot alur di backend. Keputusan akhir tetap di Pak Faris.

**Cara pandang terhadap bug:**
- Setiap aplikasi pasti punya kendala saat dipakai. Pak Andika lebih suka aplikasi segera dipakai, lalu error diperbaiki sambil jalan; Pak Faris lebih suka perencanaan matang di awal.
- Bug adalah bagian dari proses. Aplikasi yang tidak pernah dilaporkan bug-nya hanya ada dua kemungkinan: sangat sempurna, atau tidak pernah dipakai.

**Timeline dan nilai proyek:**
- Pak Andika menanyakan akhir proyek; dijawab Zaky: 24 Desember. Menurut beliau progres tim cepat.
- Zaky: proyek masih di tahap awal. Bagian analisa cukup berat, jadi bagian depan sengaja dipercepat.
- Fase 2 (MVP Analisa & Summary) berjalan 12 Okt – 8 Nov. Makin cepat selesai makin baik: aplikasi ini bisa membantu tim internal OJK maupun lembaga lain. Salah satu penyebab analisa regulasi lama adalah belum adanya *tools* yang mempercepat.

**Lain-lain:** Pak Andika menyinggung undang-undang baru yang ditetapkan hari itu (UU Satu Data). Menurut beliau, ini bisa jadi perhatian untuk pengembangan aplikasi ke depan.

---

## 4. Keputusan

1. Demo MVP Fase 1 diterima Pak Andika tanpa revisi. Penerimaan resmi M1 tetap oleh PO (Pak Faris).
2. Pekan ini fokus memperbaiki seluruh error hasil pengujian supaya Fase 1 ditutup tanpa sisa. MVP Fase 1 rilis 11 Okt, lalu mulai 12 Okt tim fokus ke Fase 2.
3. Backend di-*deploy* di VPS bersama worker scraper (sementara). Frontend tetap di Vercel.
4. Login dan role tetap ditunda. Jenis dan jumlah role dikonfirmasi ke Pak Faris, dengan saran Pak Andika: sesedikit mungkin.
5. Singkatan di materi dan laporan ditulis panjang.

---

## 5. Action item

### Zaky
- [ ] Kirim update ke grup untuk Pak Faris: feedback Weekly #4 yang sudah dikerjakan dan hasil demo — hari ini
- [ ] Minta akses dokumen di folder OneDrive ke Pak Faris / Pak Andika
- [ ] Konfirmasi ke Pak Faris: perlu login atau tidak, dan role apa saja
- [ ] Bawa temuan "API tanpa login" ke Pak Faris (lihat catatan PM)
- [ ] Minta penerimaan M1 dari Pak Faris setelah beliau kembali
- [ ] Tagih tanda tangan PRD ke Pak Andika (#45)
- [ ] Siapkan kickoff Fase 2 (12 Okt)

### Hamdan
- [ ] Berikan akses VPS dan laporan Cakupan Uji ke Fathir dan Rafli
- [ ] Lanjutkan uji Infra 7–14 dan area lain (Scraping, Unggah & Ingest, Knowledge Base, Platform, Frontend) (#92)
- [ ] Tulis singkatan secara lengkap di laporan uji
- [ ] Benchmark penyimpanan bersama Fathir

### Rafli
- [ ] Tutup akses API tanpa login, atau minimal lindungi data non-publik, bersama Fathir
- [ ] Isi ulang data di staging supaya dashboard dan Knowledge Base tidak nol saat diuji
- [ ] Lanjutkan sinkron OneDrive setelah akses dibuka (#30)
- [ ] Perbaiki error dari laporan QA sebelum 11 Okt

### Ikhwan
- [ ] Cek tampilan dashboard, Knowledge Base, dan Ingest dengan data nyata setelah staging terisi
- [ ] Perbaiki error frontend dari laporan QA sebelum 11 Okt

### Fathir
- [ ] Stabilkan deploy backend dan worker scraper di VPS
- [ ] Benchmark *vector database* vs tanpa vektor, termasuk waktu *semantic search* (#42)

### Mitra
- [ ] Pak Faris / Pak Andika: buka akses dokumen di folder OneDrive
- [ ] Pak Faris: arahan kebutuhan login dan role
- [ ] Pak Faris: angka *ground truth* jumlah dokumen per situs (#87) — masih ditunggu
- [ ] Pak Andika: tanda tangan PRD (#45)

---

## 6. Catatan dari sisi PM

- **Status indikator M1, lima hari sebelum rilis:**

  | Indikator | Status |
  | --- | --- |
  | Tarik dokumen dari tiga situs sumber | OJK dan JDIH berhasil di lokal. Belum dibandingkan dengan *ground truth* karena angkanya belum diterima (#87) |
  | Unggah manual PDF | Berjalan |
  | Satu folder lokal dan satu folder OneDrive public | Folder lokal jalan; **OneDrive terblokir akses** |
  | ≥ 20 dokumen di Knowledge Base | Tercapai di lokal, **staging masih nol** |

  Dua hal yang paling menentukan sebelum 11 Okt: akses OneDrive dari mitra, dan isi ulang data di staging. Tanpa yang kedua, mitra yang membuka staging akan melihat aplikasi kosong.

- **Temuan "API tanpa login" bertabrakan dengan keputusan menunda login.** Login ditunda supaya pengujian tidak bolak-balik (Weekly #3). Tetapi staging ada di internet publik, dan begitu dokumen internal DPEA dari OneDrive masuk (ditandai `non_publik` di US-17), isinya bisa dibaca siapa saja. **Usulan:** pasang pengaman minimal di staging — token akses atau *basic auth* di depan API — tanpa membangun fitur login penuh, dan jangan memasukkan dokumen non-publik sebelum pengaman itu ada. Perlu persetujuan Pak Faris karena menyentuh keputusan beliau.
- **Penerimaan M1 belum lengkap.** "Tidak ada revisi" dari Pak Andika belum sama dengan penerimaan PO. Menurut dok. 07, M1 diterima Pak Faris, dan beliau belum melihat demo. Kirim ringkasan dan link staging ke beliau, lalu minta konfirmasi sebelum 11 Okt atau segera setelah kembali.
- **Arsitektur kembali ke ADR-11.** ADR-11 sejak awal mengusulkan frontend di Vercel dan backend di VPS. Percobaan menaruh backend di Vercel adalah penyimpangan yang kini dikoreksi. Status ADR-11 bisa diubah dari *usulan* menjadi *diterima*.
- **Role pengguna menentukan US-01** (#32, Sprint 4). Jawaban Pak Faris soal role dibutuhkan sebelum sprint planning Fase 2, bukan di akhir proyek.
- **Fase 2 lebih pendek dari kelihatannya.** Dengan aturan H-14 (dok. 07 §5.2), pengujian M2 mulai 25 Okt — hanya dua minggu setelah Fase 2 dimulai. Pembagian tugas Fase 2 sudah ada, jadi kickoff 12 Okt bisa langsung masuk pengerjaan.
- **Tanda tangan PRD** sudah ditagih di tiga rapat berturut-turut (Weekly #3, #4, #5).
