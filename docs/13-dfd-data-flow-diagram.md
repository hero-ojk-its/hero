# DATA FLOW DIAGRAM (DFD)
**Proyek:** HERO | **Versi:** 1.0 | **Tanggal:** 8 September 2026 | **Penyusun:** Business Analyst
**Dasar:** [SRS](03-srs-functional-spec.md), [MoM Weekly Update #1](14-mom-weekly-update-01.md)

---

## 0. Notasi

| Bentuk | Arti |
| --- | --- |
| Persegi bergaris tebal | **Entitas eksternal** — pihak/sistem di luar batas HERO |
| Persegi membulat | **Proses** — transformasi data |
| Silinder | **Data store** — tempat data mengendap |
| Panah berlabel | **Aliran data** — nama data, bukan nama aksi |

Penomoran: proses induk `1.0`, dekomposisinya `1.1`, `1.2`, dan seterusnya.

---

## 1. Context Diagram (DFD Level 0)

Menunjukkan batas sistem: siapa memberi data apa ke HERO, dan HERO mengembalikan apa.

```mermaid
flowchart LR
    ANL["ANALIS REGULASI DPEA"]
    ADM["ADMIN KNOWLEDGE BASE"]
    PO["PRODUCT OWNER / VALIDATOR DPEA<br/>Faris - Andika"]
    SITUS["SITUS SUMBER PERATURAN<br/>JDIH / ojk.go.id"]
    DRIVE["FOLDER ONEDRIVE / LOKAL DPEA<br/>peraturan internal"]
    AI["LAYANAN AI / LLM<br/>opsional"]

    HERO(("0<br/>SISTEM HERO<br/>Harmonisasi & Analisa<br/>Regulasi Otomatis"))

    ADM -- "daftar URL situs sumber,<br/>konfigurasi folder,<br/>aturan klasifikasi" --> HERO
    HERO -- "ringkasan job ingest,<br/>daftar dokumen gagal" --> ADM

    ANL -- "berkas draft peraturan baru,<br/>permintaan analisa,<br/>pilihan mode pemrosesan,<br/>suntingan draft tanggapan" --> HERO
    HERO -- "summary & key takeaways,<br/>laporan harmonisasi,<br/>draft surat tanggapan,<br/>hasil pencarian" --> ANL

    SITUS -- "berkas PDF peraturan<br/>terpublikasi" --> HERO
    HERO -- "permintaan HTTP<br/>penelusuran per kedalaman" --> SITUS

    DRIVE -- "berkas PDF peraturan internal" --> HERO
    HERO -- "permintaan baca folder" --> DRIVE

    HERO -- "teks hasil deterministik<br/>untuk dinaturalkan" --> AI
    AI -- "narasi hasil penghalusan" --> HERO

    HERO -- "hasil analisa + kutipan pasal<br/>untuk validasi sampling" --> PO
    PO -- "hasil validasi sampling,<br/>penandaan temuan,<br/>persetujuan fase" --> HERO

    classDef ext fill:#eef2f7,stroke:#33475b,stroke-width:2.5px,color:#12314f
    classDef proc fill:#e9f7ef,stroke:#2e8b57,stroke-width:2.5px,color:#14432a
    class ANL,ADM,PO,SITUS,DRIVE,AI ext
    class HERO proc
```

### 1.1 Kamus Aliran Data — Level 0

| Aliran | Dari → Ke | Isi Data |
| --- | --- | --- |
| Daftar URL situs sumber | Admin KB → HERO | Nama sumber, URL, jenis sumber, kedalaman crawling, status aktif |
| Berkas PDF peraturan terpublikasi | Situs Sumber → HERO | Berkas PDF mentah + URL asal |
| Berkas PDF peraturan internal | OneDrive/Lokal → HERO | Berkas PDF mentah + jalur folder |
| Berkas draft peraturan baru | Analis → HERO | Berkas PDF draft yang akan dikaji |
| Permintaan analisa | Analis → HERO | ID dokumen, jenis layanan, profil PoV, mode pemrosesan |
| Teks hasil deterministik | HERO → Layanan AI | Narasi dasar yang akan dinaturalkan (**hanya dokumen berklasifikasi publik**) |
| Laporan harmonisasi | HERO → Analis | Ringkasan, daftar temuan berklasifikasi, kutipan pasal, rekomendasi awal |
| Draft surat tanggapan | HERO → Analis | Naskah sesuai template baku DPEA + daftar pasal berdampak |
| Hasil validasi sampling | Validator DPEA → HERO | Penilaian benar/salah atas kutipan pasal pada dokumen sampel |

---

## 2. DFD Level 1 — Dekomposisi Sistem HERO

```mermaid
flowchart TB
    ANL["ANALIS REGULASI"]
    ADM["ADMIN KB"]
    PO["VALIDATOR DPEA"]
    SITUS["SITUS SUMBER"]
    DRIVE["ONEDRIVE / LOKAL"]
    AI["LAYANAN AI"]

    P1(("1.0<br/>Pengumpulan &<br/>Ingest Dokumen"))
    P2(("2.0<br/>Pengelolaan<br/>Knowledge Base"))
    P3(("3.0<br/>Analisa &<br/>Peringkasan"))
    P4(("4.0<br/>Harmonisasi<br/>Draft vs Corpus"))
    P5(("5.0<br/>Penyusunan Draft<br/>Surat Tanggapan"))
    P6(("6.0<br/>Orkestrasi Mode<br/>Deterministik / AI"))
    P7(("7.0<br/>Audit &<br/>Riwayat Eksekusi"))

    D1[("D1 - Berkas PDF Asli")]
    D2[("D2 - Dokumen & Metadata")]
    D3[("D3 - Struktur Pasal - blok")]
    D4[("D4 - Index Pencarian")]
    D5[("D5 - Hasil Analisa")]
    D6[("D6 - Temuan Harmonisasi")]
    D7[("D7 - Profil PoV & Template")]
    D8[("D8 - Draft Tanggapan")]
    D9[("D9 - Audit & Job Log")]

    ADM -- "daftar sumber & konfigurasi" --> P1
    SITUS -- "PDF terpublikasi" --> P1
    DRIVE -- "PDF internal" --> P1
    ANL -- "unggah draft peraturan baru" --> P1

    P1 -- "berkas PDF tervalidasi" --> D1
    P1 -- "metadata hasil OCR halaman 1" --> P2
    P1 -- "ringkasan job & daftar gagal" --> ADM
    P1 -- "catatan job" --> D9

    P2 -- "dokumen + metadata" --> D2
    P2 -- "blok pasal hasil parsing" --> D3
    P2 -- "term index" --> D4
    ANL -- "kata kunci pencarian" --> P2
    P2 -- "hasil pencarian" --> ANL

    ANL -- "permintaan analisa" --> P6
    ANL -- "permintaan harmonisasi" --> P6
    ANL -- "permintaan penyusunan tanggapan" --> P6
    ANL -- "pilihan mode" --> P6

    P6 -- "instruksi jalankan deterministik" --> P3
    P6 -- "instruksi jalankan deterministik" --> P4
    P6 -- "instruksi jalankan deterministik" --> P5
    P6 -- "teks dasar untuk dinaturalkan" --> AI
    AI -- "narasi hasil penghalusan" --> P6
    P6 -- "jejak mode & status layanan AI" --> P7

    D3 -- "blok pasal" --> P3
    D2 -- "metadata & status keberlakuan" --> P3
    P3 -- "summary, key takeaways, kutipan pasal" --> D5
    P3 -- "hasil analisa" --> ANL

    D3 -- "pasal draft & pasal corpus" --> P4
    D4 -- "kandidat pembanding" --> P4
    D2 -- "status keberlakuan peraturan dirujuk" --> P4
    P4 -- "temuan terklasifikasi + kutipan" --> D6
    P4 -- "laporan harmonisasi" --> ANL

    D7 -- "profil PoV, template, checklist" --> P5
    D6 -- "temuan sebagai bahan tanggapan" --> P5
    D3 -- "pasal draft" --> P5
    P5 -- "draft tanggapan berversi" --> D8
    P5 -- "draft surat tanggapan" --> ANL
    ANL -- "suntingan draft" --> P5

    ADM -- "profil PoV & template" --> P5

    D5 -- "hasil + kutipan" --> PO
    D6 -- "temuan + kutipan" --> PO
    D1 -- "PDF asli untuk diperiksa" --> PO
    PO -- "hasil validasi sampling" --> P7
    P7 -- "catatan audit" --> D9

    classDef ext fill:#eef2f7,stroke:#33475b,stroke-width:2px,color:#12314f
    classDef proc fill:#e9f7ef,stroke:#2e8b57,stroke-width:2px,color:#14432a
    classDef store fill:#e8f0fe,stroke:#3b6ea5,stroke-width:2px,color:#12314f
    class ANL,ADM,PO,SITUS,DRIVE,AI ext
    class P1,P2,P3,P4,P5,P6,P7 proc
    class D1,D2,D3,D4,D5,D6,D7,D8,D9 store
```

### 2.1 Daftar Proses Level 1

| No. | Proses | Masukan Utama | Keluaran Utama | FR Terkait |
| --- | --- | --- | --- | --- |
| 1.0 | Pengumpulan & Ingest Dokumen | Daftar sumber, PDF dari situs/folder/unggahan | Berkas tervalidasi, metadata dasar, log job | FR-SCR-01…12 |
| 2.0 | Pengelolaan Knowledge Base | Metadata, teks, struktur | Dokumen terklasifikasi, index pencarian | FR-KB-01…09 |
| 3.0 | Analisa & Peringkasan | Blok pasal, metadata | Summary, Key Takeaways + kutipan pasal | FR-ANL-01…09 |
| 4.0 | Harmonisasi Draft vs Corpus | Pasal draft, kandidat pembanding | Temuan terklasifikasi, laporan | FR-HRM-01…13 |
| 5.0 | Penyusunan Draft Surat Tanggapan | Profil PoV, template, checklist, temuan | Draft surat tanggapan berversi | FR-POV-01…08 |
| 6.0 | Orkestrasi Mode | Permintaan analisa, pilihan mode | Instruksi eksekusi, penanganan *fallback* | FR-SYS-01…04 |
| 7.0 | Audit & Riwayat Eksekusi | Kejadian proses, validasi DPEA | Audit log, riwayat yang dapat diulang | FR-SYS-07, 10 |

### 2.2 Daftar Data Store

| ID | Data Store | Isi | Mengapa Terpisah |
| --- | --- | --- | --- |
| D1 | Berkas PDF Asli | Berkas mentah + hash + ukuran | Dibutuhkan validator DPEA untuk membuka dokumen aslinya saat *sampling* |
| D2 | Dokumen & Metadata | Judul, nomor, tanggal, status keberlakuan, klasifikasi akses | Sumber identitas & penyaringan NDA |
| D3 | Struktur Pasal (blok) | Bab/pasal/ayat hasil parsing | Unit terkecil ketertelusuran; dasar semua analisa |
| D4 | Index Pencarian | Term & representasi kemiripan | Memisahkan kebutuhan retrieval dari penyimpanan kanonis |
| D5 | Hasil Analisa | Summary & Key Takeaways, versi deterministik dan AI terpisah | Menegakkan BRule-03 |
| D6 | Temuan Harmonisasi | Temuan + klasifikasi + tingkat keyakinan | Objek yang divalidasi DPEA |
| D7 | Profil PoV & Template | Profil unit, template baku, checklist pasal | Konfigurasi, bukan kode (NFR-15) |
| D8 | Draft Tanggapan | Naskah berversi + butir per pasal | Riwayat penyuntingan |
| D9 | Audit & Job Log | Siapa, kapan, aksi, mode, versi aturan | Syarat *repeatable* & *traceable* |

---

## 3. DFD Level 2 — Proses 1.0 Pengumpulan & Ingest Dokumen

```mermaid
flowchart TB
    ADM["ADMIN KB"]
    ANL["ANALIS"]
    SITUS["SITUS SUMBER"]
    DRIVE["ONEDRIVE / LOKAL"]

    P11(("1.1<br/>Kelola Daftar<br/>Sumber"))
    P12(("1.2<br/>Telusuri Situs<br/>per Kedalaman"))
    P13(("1.3<br/>Unduh & Validasi<br/>Format PDF"))
    P14(("1.4<br/>Periksa Duplikat<br/>hash + ukuran"))
    P15(("1.5<br/>OCR Halaman 1 &<br/>Ambil Identitas"))
    P16(("1.6<br/>Terapkan Naming<br/>Convention"))
    P17(("1.7<br/>Ekstraksi Teks<br/>langsung / OCR penuh"))
    P18(("1.8<br/>Parsing Struktur<br/>Bab-Pasal-Ayat"))
    P19(("1.9<br/>Kelola Antrian<br/>Kegagalan"))

    DS1[("D1 - Berkas PDF Asli")]
    DS2[("D2 - Dokumen & Metadata")]
    DS3[("D3 - Struktur Pasal")]
    DSL[("D10 - Sumber & Job Log")]

    ADM -- "URL, jenis sumber, kedalaman" --> P11
    P11 -- "daftar sumber aktif" --> DSL
    DSL -- "sumber yang akan dijalankan" --> P12
    P12 -- "permintaan HTTP per level" --> SITUS
    SITUS -- "halaman & tautan PDF" --> P12
    P12 -- "daftar kandidat URL PDF" --> P13
    DRIVE -- "berkas dari folder" --> P13
    ANL -- "unggahan draft peraturan" --> P13

    P13 -- "berkas non-PDF + alasan" --> P19
    P13 -- "berkas PDF valid" --> P14
    P14 -- "berkas duplikat + alasan" --> P19
    P14 -- "berkas unik" --> DS1
    P14 -- "berkas unik" --> P15

    P15 -- "nomor peraturan, tanggal, judul" --> P16
    P15 -- "identitas tidak terbaca" --> P19
    P16 -- "nama berkas baku + metadata" --> DS2
    P16 -- "berkas siap diekstraksi" --> P17
    P17 -- "teks lengkap" --> P18
    P17 -- "ekstraksi/OCR gagal" --> P19
    P18 -- "blok bab/pasal/ayat" --> DS3
    P18 -- "struktur tidak terbaca" --> P19

    P19 -- "daftar dokumen gagal" --> ADM
    ADM -- "perintah proses ulang / koreksi manual" --> P19
    P19 -- "berkas diproses ulang" --> P13
    P19 -- "catatan kegagalan" --> DSL

    classDef ext fill:#eef2f7,stroke:#33475b,stroke-width:2px,color:#12314f
    classDef proc fill:#e9f7ef,stroke:#2e8b57,stroke-width:2px,color:#14432a
    classDef store fill:#e8f0fe,stroke:#3b6ea5,stroke-width:2px,color:#12314f
    class ADM,ANL,SITUS,DRIVE ext
    class P11,P12,P13,P14,P15,P16,P17,P18,P19 proc
    class DS1,DS2,DS3,DSL store
```

### 3.1 Catatan Proses 1.0

| Proses | Aturan yang Berlaku |
| --- | --- |
| 1.2 | Mulai dari kedalaman 1; kedalaman lebih dalam menyusul. Situs ber-anti-bot memakai jalur *browser automation*, bukan permintaan polos |
| 1.3 | Hanya PDF yang diterima (BRule-04); berkas lain ditolak dengan alasan tercatat |
| 1.4 | Duplikat ditentukan dari **kesamaan hash DAN ukuran berkas** (KEP-06) |
| 1.5 | Identitas diambil dari **halaman pertama** — di situlah nomor, tanggal, dan judul berada (KEP-07) |
| 1.6 | Penamaan baku diterapkan **sebelum** berkas masuk folder knowledge base |
| 1.9 | Tidak ada dokumen yang dibuang diam-diam; semua kegagalan masuk antrian yang dapat ditindaklanjuti (FR-SCR-12) |

---

## 4. DFD Level 2 — Proses 4.0 Harmonisasi Draft vs Corpus

```mermaid
flowchart TB
    ANL["ANALIS"]
    PO["VALIDATOR DPEA"]

    P41(("4.1<br/>Pilih Kandidat<br/>Peraturan Pembanding"))
    P42(("4.2<br/>Cocokkan Rujukan<br/>Pasal Eksplisit"))
    P43(("4.3<br/>Cek Status Keberlakuan<br/>Peraturan Dirujuk"))
    P44(("4.4<br/>Bandingkan Objek &<br/>Substansi Antar Pasal"))
    P45(("4.5<br/>Klasifikasikan Temuan"))
    P46(("4.6<br/>Susun Laporan &<br/>Rekomendasi Awal"))
    P47(("4.7<br/>Terima Penandaan &<br/>Hasil Validasi"))

    DS3[("D3 - Struktur Pasal")]
    DS4[("D4 - Index Pencarian")]
    DS2[("D2 - Dokumen & Metadata")]
    DS6[("D6 - Temuan Harmonisasi")]
    DS9[("D9 - Audit Log")]

    ANL -- "ID draft peraturan" --> P41
    DS4 -- "peraturan bertopik serupa" --> P41
    DS2 -- "judul, objek, kausal peraturan" --> P41
    P41 -- "daftar kandidat + dasar pemilihan" --> P42

    DS3 -- "pasal draft" --> P42
    DS3 -- "pasal kandidat" --> P42
    P42 -- "pasangan pasal terpetakan" --> P43
    DS2 -- "status berlaku / dicabut" --> P43
    P43 -- "temuan rujukan dicabut" --> P45
    P43 -- "pasangan pasal aktif" --> P44

    P44 -- "kesamaan objek & perbedaan ketentuan" --> P45

    P45 -- "temuan berlabel MENGGANTIKAN" --> DS6
    P45 -- "temuan berlabel MEMPERJELAS" --> DS6
    P45 -- "temuan berlabel PASAL BARU" --> DS6
    P45 -- "temuan berlabel DUPLIKASI" --> DS6
    P45 -- "temuan berlabel KONFLIK" --> DS6

    DS6 -- "temuan + kutipan pasal" --> P46
    P46 -- "laporan harmonisasi" --> ANL
    P46 -- "hasil + kutipan untuk sampling" --> PO

    PO -- "penilaian benar/salah kutipan" --> P47
    ANL -- "penandaan valid / tidak relevan" --> P47
    P47 -- "umpan balik temuan" --> DS6
    P47 -- "catatan validasi" --> DS9

    classDef ext fill:#eef2f7,stroke:#33475b,stroke-width:2px,color:#12314f
    classDef proc fill:#e9f7ef,stroke:#2e8b57,stroke-width:2px,color:#14432a
    classDef store fill:#e8f0fe,stroke:#3b6ea5,stroke-width:2px,color:#12314f
    class ANL,PO ext
    class P41,P42,P43,P44,P45,P46,P47 proc
    class DS2,DS3,DS4,DS6,DS9 store
```

### 4.1 Aturan Klasifikasi pada Proses 4.5

Diturunkan langsung dari contoh kasus pelaporan bank yang dijelaskan mitra
([MoM §5.5](14-mom-weekly-update-01.md)).

| Kondisi Objek Pasal Draft | Kondisi Ketentuan | Klasifikasi |
| --- | --- | --- |
| Sudah diatur di corpus | Ketentuannya berbeda dari yang lama | **MENGGANTIKAN** — pasal lama gugur |
| Sudah diatur di corpus | Substansi sama, hanya diperinci/dipertegas | **MEMPERJELAS** |
| Sudah diatur di corpus | Identik, tidak menambah apa pun | **DUPLIKASI** |
| Sudah diatur di corpus | Bertentangan dan keduanya sama-sama berlaku | **KONFLIK** |
| **Belum** diatur di corpus | — | **PASAL BARU / TAMBAHAN** — tidak me-*replace* apa pun |
| Merujuk peraturan berstatus dicabut | — | **RUJUKAN DICABUT** |

> **Ambang kemiripan belum ditetapkan.** Fathir menanyakannya di rapat; mitra menjawab dengan
> logika kualitatif (kesamaan objek dan kausal), bukan angka persentase. Perumusan ambang ini
> menjadi agenda diskusi bersama — lihat [Risk Register](10-risk-register.md) RSK-17.

---

## 5. DFD Level 2 — Proses 5.0 Penyusunan Draft Surat Tanggapan

```mermaid
flowchart TB
    ANL["ANALIS"]
    ADM["ADMIN KB"]

    P51(("5.1<br/>Muat Profil PoV,<br/>Template & Checklist"))
    P52(("5.2<br/>Identifikasi Pasal<br/>Berdampak bagi Unit"))
    P53(("5.3<br/>Periksa Kelengkapan<br/>terhadap Checklist"))
    P54(("5.4<br/>Susun Narasi<br/>per Pasal"))
    P55(("5.5<br/>Isikan ke Template<br/>Baku DPEA"))
    P56(("5.6<br/>Kelola Penyuntingan<br/>& Versi"))
    P57(("5.7<br/>Ekspor Surat<br/>Tanggapan"))

    DS7[("D7 - Profil PoV & Template")]
    DS3[("D3 - Struktur Pasal")]
    DS6[("D6 - Temuan Harmonisasi")]
    DS8[("D8 - Draft Tanggapan")]

    ADM -- "profil unit, template, checklist" --> DS7
    ANL -- "ID draft + pilihan profil PoV" --> P51
    DS7 -- "konfigurasi PoV" --> P51
    P51 -- "kata kunci relevansi" --> P52
    DS3 -- "pasal draft" --> P52
    DS6 -- "temuan terkait pasal" --> P52
    P52 -- "daftar pasal berdampak + alasan" --> P53
    P53 -- "pasal wajib belum ditanggapi" --> P55
    P53 -- "pasal siap ditanggapi" --> P54
    P54 -- "narasi per pasal + kutipan dasar hukum" --> P55
    P55 -- "naskah sesuai template" --> DS8
    P55 -- "draft tanggapan" --> ANL
    ANL -- "suntingan naskah" --> P56
    P56 -- "versi baru" --> DS8
    DS8 -- "naskah final draft" --> P57
    P57 -- "berkas surat tanggapan" --> ANL

    classDef ext fill:#eef2f7,stroke:#33475b,stroke-width:2px,color:#12314f
    classDef proc fill:#e9f7ef,stroke:#2e8b57,stroke-width:2px,color:#14432a
    classDef store fill:#e8f0fe,stroke:#3b6ea5,stroke-width:2px,color:#12314f
    class ANL,ADM ext
    class P51,P52,P53,P54,P55,P56,P57 proc
    class DS3,DS6,DS7,DS8 store
```

> **Prasyarat proses 5.0 belum tersedia.** Isi D7 (profil PoV, template baku, checklist pasal
> wajib) sepenuhnya bergantung pada contoh surat tanggapan dan dokumen dasarnya yang akan
> disediakan mitra — action item AI-M3 s.d. AI-M6. Selama D7 kosong, seluruh proses 5.1–5.7
> tidak dapat dibangun maupun diuji.

---

## 6. Pemeriksaan Keseimbangan DFD

Setiap aliran yang masuk/keluar proses induk harus muncul kembali di dekomposisinya.

| Proses Induk | Aliran Masuk Level 1 | Muncul di Level 2 | Aliran Keluar Level 1 | Muncul di Level 2 |
| --- | --- | --- | --- | --- |
| 1.0 | Daftar sumber, PDF situs, PDF internal, unggahan draft | ✅ P1.1, P1.2, P1.3 | Berkas ke D1, metadata ke 2.0, ringkasan job, log | ✅ P1.4, P1.6, P1.9 |
| 4.0 | Pasal draft & corpus (D3), kandidat (D4), status (D2) | ✅ P4.1, P4.2, P4.3 | Temuan ke D6, laporan ke Analis | ✅ P4.5, P4.6 |
| 5.0 | Profil PoV (D7), temuan (D6), pasal draft (D3) | ✅ P5.1, P5.2 | Draft ke D8, naskah ke Analis | ✅ P5.5, P5.7 |

**Data store tanpa penulis atau tanpa pembaca:** tidak ditemukan. Setiap store memiliki
minimal satu proses yang menulis dan satu yang membaca.

---

## Riwayat Revisi

| Versi | Tanggal | Perubahan | Penyusun |
| --- | --- | --- | --- |
| 1.0 | 8 Sep 2026 | Dokumen baru: Context, Level 1, dan tiga Level 2 (ingest, harmonisasi, tanggapan) | BA |
