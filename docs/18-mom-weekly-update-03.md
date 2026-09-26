# MoM — Weekly Update #3 (Minggu 2 Fase 1)

**Tanggal:** Senin, 22 September 2026 · ± 35 menit · Zoom
**Hadir DPEA:** Pak Faris Budi (Product Owner + Agile Coach), Pak Andika Prihandoko (Mentor — bergabung di akhir)
**Hadir Tim:** Zaky (PM/BA), Ikhwan (Frontend), Fathir (Data/ML), Rafli (Backend)
**Berhalangan:** Hamdan (Infra/QA) — progres disampaikan Zaky
**Notulis:** Zaky
**Rekaman:** https://youtu.be/E0h8hdUm61U

---

## 1. Ringkasan singkat

- Minggu kedua Fase 1. Sesi dibuka dengan pembahasan feedback tertulis Pak Faris atas mockup Figma, lalu progres per peran.
- Backend melaporkan sebagian besar story Sprint 1 selesai: CRUD situs sumber, ringkasan job, unggah manual (tunggal & banyak), tipe dokumen, tolak non-PDF, deteksi duplikat, simpan metadata + teks.
- **Login ditunda ke akhir proyek.** Aplikasi langsung terbuka ke dashboard tanpa login supaya pengujian tidak bolak-balik.
- **Alur scraping ditegaskan ulang:** scan dulu → tampilkan jumlah PDF baru vs sudah ada → pengguna centang yang mau ditarik → pilih tujuan (knowledge base/vektor atau unduh PDF ke folder).
- **Draft Tanggapan tidak lagi berdiri sendiri sebagai menu** — digabung ke dalam Analisa.
- Folder OneDrive sudah bisa diakses Data/ML. Pak Faris akan menyusulkan contoh template tanggapan dan tiga alamat URL sumber.
- Fathir menemukan VPS murah (± US$10/tahun) untuk server — skema reimburse.

---

## 2. Laporan progres per orang

### Zaky — PM / BA
- Menunjukkan papan kanban GitHub Project. Tim baru mendapat pembekalan GitHub Project dari kampus; papan masih disesuaikan dan mulai dipakai sebagai format laporan mingguan.
- PRD sudah disusun dan butuh tanda tangan Pak Andika sebagai mentor industri — dibagikan di grup untuk direview, target selesai pekan ini.

### Ikhwan — Frontend
- Masih menelaah dan menerapkan feedback tertulis Pak Faris atas mockup. Link Figma revisi dikirim minggu depan, atau lebih cepat bila sudah selesai.
- Menambahkan riwayat pengambilan dokumen dan opsi "disimpan sebagai folder lokal" di halaman Ingest.
- Kerangka project frontend sudah dibuat.

### Fathir — Data/ML
- Fokus ke retrieval dokumen dari sumber OneDrive yang baru disediakan mitra.
- Menemukan VPS murah (± US$10/tahun, VPS kosongan) dan sudah mulai dioprek. Pembayaran lewat skema reimburse.
- Scraping dengan paging sudah siap.

### Hamdan — Infra/QA *(disampaikan Zaky)*
- Masih eksplorasi setup infrastruktur yang bisa dipakai berkelanjutan, menyesuaikan dengan GitHub Project.
- Implementasi deployment menunggu sebagian frontend dan backend supaya bisa terintegrasi.

### Rafli — Backend

| Story | Status dilaporkan |
| --- | --- |
| US-02 Login (JWT) | Siap — **ditunda pemakaiannya**, lihat keputusan |
| US-12 CRUD daftar situs sumber | Selesai |
| US-14 Ringkasan hasil job (berhasil / duplikat / gagal) | Selesai |
| US-15 Unggah manual — satu atau banyak berkas | Selesai |
| US-15a Pilih tipe dokumen draft / eksisting | Selesai |
| US-18 Tolak berkas non-PDF beserta alasannya | Selesai |
| US-19 Deteksi duplikat — cek dulu baru unduh | Selesai |
| US-26 Simpan dokumen + metadata + teks | Selesai |
| US-27 Pencarian dasar | Filter nomor / kategori / tanggal / status sudah; kata kunci bebas (judul, nomor) masih berjalan |
| US-16 Baca folder lokal | Belum |
| US-23 Antrian dokumen gagal & proses ulang | Belum |
| US-25 Penempatan folder eksisting / otomatis | Belum |

---

## 3. Feedback dari mitra — per orang

### Untuk Ikhwan (Frontend)

**Dari Pak Faris — Harmonisasi:**
- Satu halaman terlalu penuh informasi. Redesain supaya lebih sederhana.
- Opsi navigasi: sub-menu *tree* di bawah menu utama pada sidebar. Ikhwan mengusulkan alur berurutan dengan tombol *Next* (proses → perbandingan substansi hukum → hasil harmonisasi). Pak Faris: coba keduanya, pilih yang lebih intuitif.
- Sidebar kiri harus bisa di-*minimize*, supaya halaman yang isinya besar tetap lega. Pisahkan ikon-ikonnya.

**Dari Pak Faris — Analisa & Draft Tanggapan:**
- Draft Tanggapan jangan jadi menu tersendiri. Gabungkan ke Analisa: pilih dokumen yang mau dianalisa; kalau mau langsung ditanggapi, klik dokumennya lalu langsung masuk ke draft tanggapan.
- Unggah manual tetap untuk draft yang langsung ditanggapi. Knowledge base diisi dari scraping dan OneDrive.
- Tiga metode analisa — **Deterministik, AI, Custom** — dibuat sebagai *toggle* (misalnya tiga tombol yang berubah warna). Frame-nya sama, isinya mengikuti metode yang dipilih.

**Dari Pak Faris — Ingest (scraping & folder):**
- Masukkan URL beserta kedalaman (kedalaman 1 = satu tingkat *slash*, kedalaman 2 = dua tingkat, dst.).
- **Jangan langsung menarik.** Scan dulu struktur halaman di URL tersebut: ada berapa halaman dan berapa PDF (contoh: 10 halaman × 2 PDF = 20 PDF tersedia).
- Bandingkan dengan isi knowledge base: berapa yang baru, berapa yang sudah ada.
- Pengguna mencentang mana yang mau ditarik (semua yang baru, atau hanya beberapa).
- Setelah itu ada pilihan tujuan: masuk knowledge base dalam bentuk vektor, atau unduh PDF mentah ke folder. Tambahkan tombol untuk alur ini.

**Dari Pak Faris — Dashboard:**
- Statistik berlaku vs dicabut. Contoh: peraturan tahun 2010 yang sudah digantikan peraturan 2020 berstatus dicabut, yang 2020 berlaku. Dari ± 1000 dokumen di KB, tampilkan berapa yang masih berlaku dan berapa yang tidak.
- Dashboard berfungsi memberi insight ringkas untuk manajemen level atas.

**Pengembangan paralel:** Ikhwan boleh mulai develop frontend sambil merevisi mockup.

### Untuk Rafli (Backend)

**Dari Pak Faris:**
- **Login ditunda.** Standar OJK memang memakai user management + captcha, dengan pengguna LDAP dan satu-dua akun lokal cadangan. Untuk sekarang, halaman pertama langsung dashboard tanpa login. Login page dikerjakan di akhir kalau masih ada waktu.
- **Belum ada penamaan baku.** Nama berkas dari tiap sumber berbeda-beda. Setelah deteksi duplikat (hash + ukuran) dan sebelum disimpan ke KB atau folder lokal, berkas di-*rename* ke format baku — misalnya `nomor peraturan␣nama peraturan␣tahun`. Kalau tidak bisa ditentukan, pakai *wildcard*.
- **Pencarian:** Rafli memakai *free text*. Pastikan indeksnya menangani istilah lebih dari satu kata — "sepatu roda" harus dicari sebagai satu frasa, bukan "sepatu" dan "roda" terpisah.
- **Story point:** kalau diterapkan ketat, tiap anggota punya kapasitas per *cycle* (misalnya 5 orang × 5 SP = 25 SP); pekerjaan yang melebihi kapasitas masuk antrian *cycle* berikutnya. Untuk sekarang tidak perlu terlalu kaku — pekerjaan yang bisa ditarik lebih awal, tarik saja.

### Untuk Fathir (Data/ML)

**Dari Pak Faris:**
- VPS ± US$10/tahun tidak masalah.
- Dari pengalaman DPEA, bagian yang biasanya lama di scraping adalah paging (halaman 1, 2, 3, …). Template SharePoint DPEA seragam — tiap halaman hanya beda nomor halaman di bawah. Kalau paging sudah terbaca, berarti aman.
- Masih ditunggu dari diskusi minggu lalu: **komparasi waktu proses penyimpanan folder PDF vs vektor** untuk ribuan dokumen.

### Untuk Zaky (PM)

- Tidak ada feedback khusus. PRD diminta direview dan ditandatangani Pak Andika pekan ini.

---

## 4. Keputusan

1. Login ditunda ke akhir proyek; aplikasi langsung terbuka ke dashboard.
2. Scraping wajib melalui tahap scan → bandingkan dengan KB → centang → pilih tujuan (vektor atau unduh PDF).
3. Draft Tanggapan digabung ke dalam Analisa, bukan menu tersendiri.
4. Metode analisa Deterministik / AI / Custom ditampilkan sebagai toggle dalam satu frame.
5. Berkas di-*rename* ke format baku setelah deteksi duplikat, sebelum disimpan.
6. Story point dipakai sebagai panduan kapasitas, tidak kaku.
7. VPS ± US$10/tahun disetujui, lewat skema reimburse.
8. Frontend boleh dikembangkan paralel dengan revisi mockup.

---

## 5. Action item

### Zaky
- [ ] Bagikan PRD ke grup, minta review dan tanda tangan Pak Andika — pekan ini
- [ ] Rapikan papan kanban GitHub Project sebagai format laporan mingguan
- [ ] Sesuaikan backlog: login ditunda, draft tanggapan masuk Analisa

### Ikhwan
- [ ] Redesain Harmonisasi: lebih sederhana, uji navigasi tree vs tombol Next
- [ ] Sidebar kiri dapat di-minimize
- [ ] Gabungkan Draft Tanggapan ke Analisa; toggle Deterministik / AI / Custom
- [ ] Alur Ingest: scan → hasil baru vs sudah ada → centang → pilih tujuan
- [ ] Dashboard: statistik berlaku vs dicabut
- [ ] Kirim link Figma revisi — paling lambat minggu depan

### Rafli
- [ ] Nonaktifkan login untuk sementara; halaman awal langsung dashboard
- [ ] Tambahkan penamaan baku setelah deteksi duplikat, sebelum simpan
- [ ] Pencarian kata kunci bebas dengan dukungan frasa multi-kata
- [ ] Lanjutkan: baca folder lokal, antrian dokumen gagal, penempatan folder

### Fathir
- [ ] Lanjutkan retrieval dari OneDrive
- [ ] Siapkan VPS; ajukan reimburse lewat Zaky
- [ ] Komparasi waktu proses folder PDF vs vektor untuk ribuan dokumen

### Hamdan
- [ ] Lanjutkan setup infrastruktur; koordinasi dengan Fathir soal VPS untuk backend

### Mitra (Pak Faris)
- [ ] Sediakan contoh template surat tanggapan di folder baru
- [ ] Kirim tiga alamat URL sumber scraping

---

## 6. Catatan dari sisi PM

- **Login yang ditunda** mengubah backlog: US-02 dan US-01 turun prioritas. Pekerjaan login yang sudah jadi tidak dibuang — cukup dimatikan dulu.
- **Penamaan baku** yang diminta Pak Faris sudah ada di backlog sebagai US-20a (OCR halaman 1 + naming convention, Sprint 2). Yang baru adalah urutannya: rename terjadi setelah deteksi duplikat, sebelum simpan. Rafli dan Fathir perlu sepakat siapa yang mengerjakan bagian mana.
- **Alur scan → centang → tarik** memperluas screening dari MoM #2: sekarang pengguna juga memilih dokumen dan tujuan penyimpanannya. Ini menyentuh US-13, US-14, dan US-19 — dan mockup Ingest.
- **Draft Tanggapan masuk Analisa** perlu dicerminkan di UI Spec dan use case sebelum Fase 4.
- **Alamat URL ketiga dan contoh template** dijanjikan lagi. Keduanya blocker lama (#24 dan #27) — tagih di rapat berikutnya kalau belum masuk.
- **VPS** menjawab kebutuhan server yang dicatat di ADR-11 (Vercel/GitHub Pages hanya untuk frontend). Hamdan perlu dilibatkan supaya keputusan infra tidak berjalan sendiri-sendiri.
- Sisa pertemuan sebelum uji coba mitra 8 Okt: **29 Sep dan 6 Okt**.
