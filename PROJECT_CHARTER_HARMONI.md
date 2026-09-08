# PROJECT CHARTER MITRA
## MATA KULIAH CAPSTONE PROJECT

**Departemen Teknik Informatika**
**Institut Teknologi Sepuluh Nopember (ITS)**

**Semester Gasal Tahun 2026/2027**

---

## 1. Gambaran Umum Proyek

| Item | Keterangan |
| --- | --- |
| **Nama Proyek** | **HARMONI**: Harmonisasi & Analisa Regulasi Otomatis — *"Menyelaraskan regulasi, mempercepat keputusan."* |
| **Mitra Perusahaan** | Otoritas Jasa Keuangan (OJK) |
| **Mentor Industri** | Nama & kontak mentor industri ditentukan oleh OJK pada awal pelaksanaan proyek (diisi setelah penunjukan resmi) |

### Masalah atau Isu

Proses analisis dan harmonisasi regulasi di OJK — mulai dari menelaah peraturan yang sudah berlaku, meringkas dokumen peraturan yang panjang, mengecek keselarasan draft peraturan baru dengan peraturan eksisting, hingga menyusun tanggapan/masukan atas draft yang sedang disusun — masih dilakukan secara manual oleh tim regulasi.

Proses tersebut memakan waktu lama dan rawan terlewatnya potensi ketidakselarasan atau tumpang tindih antarperaturan.

### Tujuan Proyek

Membangun **HARMONI**, asisten analisis regulasi berbasis AI yang membantu tim regulasi OJK untuk:

1. Menganalisis peraturan eksisting.
2. Meringkas dokumen peraturan yang panjang.
3. Memeriksa keselarasan draft peraturan baru terhadap peraturan yang berlaku.
4. Menyusun draft tanggapan/masukan atas rancangan peraturan.

Sistem ini ditujukan untuk mempercepat proses kajian regulasi dan mengurangi risiko celah atau ketidakselarasan antarperaturan.

### Studi Kasus Bisnis

OJK secara rutin menyusun, mengkaji, dan memperbarui berbagai peraturan sektor jasa keuangan. Proses kajian manual yang melibatkan ratusan hingga ribuan halaman regulasi rawan *human error* dan dapat memperlambat pengambilan keputusan.

HARMONI dirancang sebagai asisten analisis berbasis AI yang mempercepat proses kajian tersebut tanpa menggantikan keputusan akhir pengambil kebijakan.

### Tujuan / Metrik

1. Waktu peringkasan dokumen peraturan panjang, misalnya lebih dari 50 halaman, berkurang dari beberapa jam secara manual menjadi di bawah 15 menit menggunakan sistem.
2. Sistem mampu mendeteksi minimal 80% potensi ketidakselarasan/tumpang tindih antara draft peraturan baru dan peraturan eksisting pada dataset uji yang disiapkan bersama mentor.
3. Draft tanggapan/masukan otomatis atas rancangan peraturan dinilai relevan oleh tim regulasi OJK pada uji coba (pilot).
4. Waktu proses kajian awal regulasi, mulai dari input dokumen hingga draft hasil analisis, berkurang secara signifikan dibandingkan proses manual. Pengukuran dilakukan bersama mentor pada awal proyek sebagai baseline.

### Hasil yang Diharapkan

Aplikasi asisten analisis regulasi berbasis AI yang dapat:

1. Meringkas dokumen peraturan panjang.
2. Mengecek keselarasan draft peraturan baru terhadap basis data peraturan eksisting.
3. Menyusun draft tanggapan/masukan atas rancangan peraturan.
4. Menyediakan antarmuka web bagi pengguna.
5. Dilengkapi dengan dokumentasi teknis.

### Ekspektasi Deliverable & Tingkat Kesulitan

| No. | Deliverable | Tingkat Kesulitan |
| --- | --- | --- |
| 1 | Modul peringkasan dokumen peraturan panjang berbasis AI/LLM (*summarization*) | 3/5 |
| 2 | Modul analisis keselarasan (*cross-check*) antara draft peraturan baru dan basis data peraturan eksisting menggunakan teknik *retrieval*/*semantic search* | 4/5 |
| 3 | Modul penyusunan draft tanggapan/masukan otomatis atas rancangan peraturan | 4/5 |
| 4 | Antarmuka web bagi tim regulasi untuk mengunggah dokumen, meninjau hasil analisis, dan mengekspor laporan | 3/5 |

### Batasan

- Hasil analisis/tanggapan dari sistem bersifat rekomendasi/pendukung keputusan dan tidak menggantikan keputusan akhir pejabat/tim regulasi OJK.
- Dokumen peraturan yang digunakan untuk pengujian dibatasi pada dokumen publik, kecuali dokumen disediakan oleh mentor dengan NDA.
- Keluaran model AI wajib divalidasi secara manual oleh tim regulasi sebelum digunakan dalam proses resmi.

---

## 2. Ruang Lingkup Proyek

### Dalam Lingkup

- Pengembangan modul peringkasan dokumen peraturan.
- Pengembangan modul pengecekan keselarasan draft peraturan baru terhadap peraturan eksisting.
- Pengembangan modul penyusunan draft tanggapan/masukan atas rancangan peraturan.
- Pengembangan antarmuka web bagi tim regulasi.
- Uji coba menggunakan dokumen peraturan sektor jasa keuangan yang bersifat publik.

### Luar Lingkup

- Pengambilan keputusan otomatis/final atas status suatu peraturan. Keputusan tetap berada pada pejabat berwenang OJK.
- Integrasi langsung dengan sistem penerbitan peraturan resmi OJK.
- Analisis regulasi dalam bahasa asing. Cakupan awal difokuskan pada bahasa Indonesia.
- Pemrosesan seluruh regulasi historis OJK secara penuh. Pemrosesan dibatasi pada dataset pilot yang disepakati.

---

## 3. Rancangan Jadwal

| Item | Keterangan |
| --- | --- |
| **Tanggal Mulai** | 1 September 2026 |
| **Tanggal Selesai** | 31 Desember 2026 |
| **Laporan Progress** | Mingguan, setiap hari Jumat melalui tools project management yang disepakati |
| **Komitmen Jam per Minggu** | 15–20 jam per minggu per anggota tim |
| **Metode Pelaksanaan** | Hybrid — luring terjadwal 1×/minggu di kantor OJK, sisanya daring |

---

## 4. Pembagian Tim dan Role

| Peran | Tugas |
| --- | --- |
| **Analis / Product** | Penggalian kebutuhan bersama tim regulasi OJK, pemetaan proses kajian regulasi eksisting, dokumentasi requirement, dan komunikasi rutin dengan mentor/klien. |
| **Backend** | Pengembangan API dan orkestrasi pipeline AI (ringkasan, retrieval, penyusunan draft tanggapan). Bahasa/framework menyesuaikan kesepakatan dengan OJK. |
| **Frontend / UX** | Perancangan antarmuka web untuk unggah dokumen, peninjauan hasil analisis, dan ekspor laporan sesuai kebutuhan tim regulasi. |
| **Data / ML** | Pengembangan pipeline NLP (*summarization*, *semantic search*/RAG, analisis keselarasan regulasi) serta evaluasi akurasi model terhadap dataset uji. |
| **Infra / QA** | Pengaturan lingkungan staging, *continuous integration*, pengujian fungsional, serta keamanan dasar aplikasi dan data dokumen regulasi. |

---

## 5. Fasilitas

| Jenis | Keterangan |
| --- | --- |
| **Tech Stack yang Digunakan (Ketentuan Mitra)** | Belum ditentukan pada saat penyusunan charter — menyesuaikan kesepakatan lebih lanjut dengan OJK, dengan mempertimbangkan kebutuhan pemrosesan bahasa alami/LLM untuk analisis regulasi. |
| **Tools Project Management yang Digunakan** | Menggunakan tools internal OJK atau tools yang disepakati bersama tim. |
| **Repository yang Digunakan** | Menggunakan repository kampus (GitLab/GitHub organisasi Teknik Informatika ITS). Akses ke lingkungan staging OJK, bila ada, disediakan oleh OJK. |
| **Dataset** | Dokumen peraturan sektor jasa keuangan yang bersifat publik sudah tersedia. Dokumen internal/rahasia, bila diperlukan untuk pengujian, disiapkan bersama mentor dengan NDA. |

---

## 6. Manfaat dan Pengguna

### Target Pengguna

Tim/unit kerja yang menangani penyusunan dan kajian regulasi di OJK, misalnya bagian hukum/peraturan.

### Manfaat yang Diharapkan

- Mempercepat proses telaah dan harmonisasi regulasi.
- Mengurangi risiko tumpang tindih atau ketidakselarasan antarperaturan.
- Membantu penyusunan draft tanggapan awal secara lebih efisien.

---

## 7. Risiko, Kendala, dan Asumsi

### Risiko

- Hasil analisis AI berpotensi kurang akurat pada peraturan dengan struktur atau istilah hukum yang kompleks.
- Kualitas hasil analisis sangat bergantung pada kelengkapan basis data peraturan eksisting yang digunakan sebagai referensi.

### Kendala

- Ketersediaan dokumen peraturan dalam format yang dapat diproses, khususnya perbedaan antara PDF hasil pindai/scan dan dokumen dengan teks asli.
- Kebutuhan validasi oleh pakar hukum/regulasi untuk memastikan keluaran sistem relevan dan akurat.

### Asumsi

- OJK menyediakan kumpulan dokumen peraturan publik yang representatif untuk pelatihan/pengujian.
- Tersedia mentor/narasumber dari bagian hukum/regulasi untuk memvalidasi hasil analisis selama proyek berjalan.
