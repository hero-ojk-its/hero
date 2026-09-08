# GLOSSARY & DAFTAR SINGKATAN
**Proyek:** HERO | **Versi:** 1.0 | **Tanggal:** 7 September 2026 | **Penyusun:** Business Analyst

Daftar ini menjaga agar tim pengembang, mitra, dan penguji memakai istilah yang sama artinya.

---

## 1. Istilah Domain Regulasi

| Istilah | Definisi dalam Konteks HERO |
| --- | --- |
| **Peraturan eksisting** | Peraturan yang sudah ditetapkan dan tersimpan di knowledge base sistem, terlepas dari status keberlakuannya |
| **Draft peraturan baru** | Rancangan peraturan yang sedang disusun dan menjadi objek harmonisasi atau tanggapan |
| **Harmonisasi** | Proses membandingkan draft peraturan baru terhadap peraturan eksisting untuk menemukan pertentangan, tumpang tindih, atau celah pengaturan |
| **Dasar hukum** | Peraturan yang menjadi landasan penerbitan suatu peraturan, umumnya tercantum di bagian "Mengingat" |
| **Status keberlakuan** | Kondisi hukum suatu peraturan: `berlaku`, `diubah`, `dicabut`, atau `tidak diketahui` |
| **Struktur pasal** | Penguraian dokumen peraturan menjadi hierarki bab → bagian → paragraf → pasal → ayat → huruf |
| **Rujukan pasal** | Penyebutan pasal peraturan lain di dalam suatu dokumen |
| **Konflik** | Temuan ketika pasal draft bertentangan dengan pasal peraturan eksisting |
| **Duplikasi** | Temuan ketika pasal draft mengatur hal yang sudah diatur peraturan eksisting |
| **Gap (celah pengaturan)** | Temuan ketika suatu hal yang seharusnya diatur belum tercakup, baik oleh draft maupun peraturan eksisting |
| **Point of View (PoV)** | Sudut pandang suatu unit fungsi — tugas, fungsi, dan keilmuannya — yang menjadi dasar penyusunan tanggapan |
| **Draft tanggapan** | Naskah masukan atas draft peraturan baru yang disusun dari sudut pandang unit tertentu; berstatus rekomendasi, bukan keputusan |
| **Ground truth** | Daftar ketidakselarasan yang ditandai manual oleh SME atas dokumen uji; menjadi pembanding untuk mengukur recall sistem |

---

## 2. Istilah Sistem & Teknis

| Istilah | Definisi dalam Konteks HERO |
| --- | --- |
| **Knowledge Base (KB)** | Penyimpanan terstruktur berisi dokumen peraturan beserta metadata, teks, struktur pasal, dan indeks pencariannya |
| **Ingest** | Proses memasukkan dokumen ke sistem, mencakup pengambilan, validasi, ekstraksi, klasifikasi, dan penyimpanan |
| **Scraping** | Pengambilan dokumen PDF dari daftar situs yang diinput manual oleh pengguna |
| **Mode Deterministik (Non-AI)** | Mode default dan wajib; menjalankan seluruh cakupan proses berbasis aturan, pola, dan basis data, tanpa layanan AI |
| **Mode AI-Assisted** | Lapisan opsional di atas hasil Deterministik yang menghaluskan dan menaturalkan bahasa, tanpa mengubah substansi |
| **Fallback** | Perilaku sistem ketika layanan AI tidak tersedia: proses tetap diselesaikan memakai hasil Deterministik |
| **Fallback test** | Pengujian seluruh fitur dengan layanan AI sengaja dimatikan |
| **Mode Orchestrator** | Komponen yang menentukan urutan eksekusi: deterministik dahulu, lalu lapisan AI bila diaktifkan |
| **Summary** | Ringkasan isi peraturan dalam bahasa yang lebih ringkas |
| **Key Takeaways** | Poin-poin penting dokumen; setiap poin wajib menunjuk pasal sumbernya |
| **Metadata dasar** | Judul, nomor peraturan, dan tanggal terbit |
| **OCR** (*Optical Character Recognition*) | Pengubahan citra teks pada PDF hasil pindai menjadi teks yang dapat diproses |
| **Semantic search** | Pencarian berbasis kemiripan makna, bukan sekadar kecocokan kata |
| **Recall** | Rasio temuan yang berhasil dideteksi sistem terhadap seluruh temuan yang seharusnya ada (*ground truth*) |
| **Audit log** | Catatan siapa melakukan aksi apa, kapan, atas entitas mana, pada mode apa |
| **Repeatable** | Sifat sistem yang memungkinkan eksekusi diulang dan menghasilkan output yang sama, karena input, mode, dan versi aturan tersimpan |
| **Traceable** | Sifat hasil yang dapat ditelusuri sampai ke dokumen dan pasal sumbernya |
| **Antrian penanganan manual** | Daftar dokumen gagal proses yang menunggu koreksi atau pemrosesan ulang oleh pengguna |

---

## 3. Istilah Manajemen Proyek

| Istilah | Definisi |
| --- | --- |
| **MVP** (*Minimum Viable Product*) | Versi produk dengan cakupan minimum yang sudah memberi manfaat nyata bagi pengguna |
| **Sprint** | Siklus pengerjaan 2 minggu dengan tujuan (*sprint goal*) yang disepakati |
| **Epic** | Kumpulan user story yang membentuk satu kapabilitas besar |
| **User Story** | Kebutuhan yang ditulis dari sudut pandang pengguna beserta manfaatnya |
| **Acceptance Criteria (AC)** | Syarat terukur yang menentukan sebuah story dinyatakan selesai |
| **Story Point (SP)** | Satuan estimasi relatif tingkat usaha sebuah story |
| **Velocity** | Jumlah story point yang benar-benar diselesaikan tim dalam satu sprint |
| **Definition of Ready (DoR)** | Syarat sebuah story boleh masuk sprint |
| **Definition of Done (DoD)** | Syarat sebuah story dinyatakan selesai |
| **MoSCoW** | Prioritisasi: Must / Should / Could / Won't have |
| **RACI** | Matriks tanggung jawab: Responsible, Accountable, Consulted, Informed |
| **WBS** (*Work Breakdown Structure*) | Penguraian pekerjaan proyek menjadi bagian-bagian yang dapat dikelola |
| **RTM** (*Requirements Traceability Matrix*) | Matriks ketertelusuran kebutuhan dari tujuan bisnis sampai pengujian |
| **UAT** (*User Acceptance Test*) | Pengujian penerimaan oleh pengguna sebelum sistem dinyatakan diterima |
| **Change Request (CR)** | Pengajuan formal perubahan lingkup, jadwal, atau kriteria penerimaan |
| **Milestone** | Titik pencapaian penting dengan tanggal dan indikator keberhasilan tertentu |
| **Jalur kritis** | Rangkaian pekerjaan yang keterlambatannya langsung menggeser tanggal selesai proyek |
| **Baseline** | Angka acuan kondisi awal yang dipakai membandingkan perbaikan |
| **Blocker** | Hambatan yang menghentikan pekerjaan sampai diselesaikan |

---

## 4. Daftar Singkatan

| Singkatan | Kepanjangan |
| --- | --- |
| **AC** | Acceptance Criteria |
| **AI** | Artificial Intelligence |
| **BA** | Business Analyst |
| **BO** | Business Objective |
| **BR** | Business Requirement |
| **BRD** | Business Requirements Document |
| **CR** | Change Request |
| **CSF** | Critical Success Factor |
| **DoD** | Definition of Done |
| **DoR** | Definition of Ready |
| **DPEA** | Departemen Pengembangan Aplikasi |
| **FR** | Functional Requirement |
| **HERO** | Harmonisasi & Analisa Regulasi Otomatis |
| **ITS** | Institut Teknologi Sepuluh Nopember |
| **JDIH** | Jaringan Dokumentasi dan Informasi Hukum |
| **KB** | Knowledge Base |
| **LLM** | Large Language Model |
| **MoM** | Minutes of Meeting |
| **MVP** | Minimum Viable Product |
| **NDA** | Non-Disclosure Agreement |
| **NFR** | Non-Functional Requirement |
| **NLP** | Natural Language Processing |
| **OCR** | Optical Character Recognition |
| **OJK** | Otoritas Jasa Keuangan |
| **PM** | Project Manager |
| **PO** | Product Owner |
| **POJK** | Peraturan Otoritas Jasa Keuangan |
| **PoV** | Point of View |
| **QA** | Quality Assurance |
| **RACI** | Responsible, Accountable, Consulted, Informed |
| **RAG** | Retrieval-Augmented Generation |
| **RTM** | Requirements Traceability Matrix |
| **SEOJK** | Surat Edaran Otoritas Jasa Keuangan |
| **SME** | Subject Matter Expert |
| **SP** | Story Point |
| **SRS** | Software Requirements Specification |
| **UAT** | User Acceptance Test |
| **UI/UX** | User Interface / User Experience |
| **URD** | User Requirement Document |
| **WBS** | Work Breakdown Structure |

---

## Riwayat Revisi

| Versi | Tanggal | Perubahan | Penyusun |
| --- | --- | --- | --- |
| 1.0 | 7 Sep 2026 | Draft awal: istilah domain, sistem, manajemen proyek, dan singkatan | BA |
