# PROCESS FLOW — AS-IS & TO-BE
**Proyek:** HERO | **Versi:** 2.0 | **Tanggal:** 8 September 2026 | **Penyusun:** Business Analyst

---

## 1. Proses AS-IS (Kondisi Saat Ini)

Seluruh rangkaian dikerjakan manual oleh analis. Perhatikan tiga titik yang menjadi sumber
masalah: pengumpulan satu per satu, pembacaan penuh dokumen, dan harmonisasi yang bergantung
pada ingatan individu.

```mermaid
flowchart TD
    A(["Ada draft peraturan baru /<br/>kebutuhan analisa ketentuan"]) --> B["Analis mencari dokumen peraturan<br/>di berbagai situs, satu per satu"]
    B --> C["Unduh & simpan manual<br/>ke folder pribadi / bersama"]
    C --> D["Baca dokumen secara penuh<br/>bahasa hukum, bisa ratusan halaman"]
    D --> E["Catat poin penting<br/>di dokumen kerja pribadi"]
    E --> F["Cari peraturan eksisting yang terkait<br/>berdasarkan ingatan & pengalaman"]
    F --> G{"Ada pertentangan /<br/>duplikasi / celah?"}
    G -- "Terdeteksi" --> H["Catat temuan"]
    G -- "Luput" --> I["Risiko: ketidakselarasan<br/>tidak terdeteksi"]
    H --> J["Susun tanggapan dari sudut pandang unit<br/>format & gaya bahasa bervariasi"]
    I --> J
    J --> K["Review internal unit"]
    K --> L{"Sesuai?"}
    L -- "Tidak" --> J
    L -- "Ya" --> M(["Tanggapan dikirim ke<br/>pengambil keputusan"])

    classDef pain fill:#fdeaea,stroke:#c0392b,stroke-width:2px,color:#5c1a13
    class B,D,F,I,J pain
```

### 1.1 Titik Nyeri (Pain Point) pada AS-IS

| Langkah | Pain Point | Kode BRD |
| --- | --- | --- |
| Mencari & mengunduh dokumen | Manual satu per satu, tersebar, tidak terkonsolidasi | PB-01 |
| Membaca dokumen penuh | Lama; bahasa hukum; dokumen panjang | PB-02 |
| Mencari peraturan terkait | Bergantung ingatan; cakupan tidak terjamin | PB-03 |
| Deteksi konflik | Rawan luput; tidak ada jejak audit | PB-03 |
| Menyusun tanggapan | Format & kualitas bervariasi antar penyusun | PB-04 |
| Seluruh proses | Tidak tersimpan terpusat; tidak dapat diulang | PB-05 |

---

## 2. Proses TO-BE v2 (Setelah HERO)

> **Versi 2** — direvisi 8 September 2026 berdasarkan [MoM Weekly Update #1](14-mom-weekly-update-01.md).
> Diagram lengkap beserta ringkasan 10 perubahan dari v1 ada di [HERO_FLOW.md](../HERO_FLOW.md).

Perbedaan paling mendasar dari v1: **tiga sumber dokumen tidak lagi disatukan ke satu pipeline
dengan tujuan yang sama.** Scraping dan folder internal mengisi *corpus* peraturan eksisting,
sedangkan unggah manual memasukkan **draft peraturan baru yang menjadi objek kajian**. Keduanya
melewati validasi yang sama, tetapi berakhir dengan peran yang berbeda.

```mermaid
flowchart TD
    START(["Mulai"]) --> TUJUAN{"Apa tujuan pengguna?"}

    subgraph JA["JALUR A - Membangun Corpus Peraturan Eksisting"]
        direction TB
        A1["Scraping situs publik<br/>JDIH / ojk.go.id-regulasi"]
        A3["Folder lokal / OneDrive DPEA<br/>peraturan INTERNAL - wajib NDA"]
        A1D{"Kedalaman crawling"}
        A1D1["Kedalaman 1 - prioritas awal"]
        A1D2["Kedalaman 2 dan seterusnya"]
    end

    subgraph JB["JALUR B - Objek Kajian"]
        B0["Unggah manual<br/>DRAFT PERATURAN BARU"]
    end

    TUJUAN -- "Isi corpus publik" --> A1
    TUJUAN -- "Isi corpus internal" --> A3
    TUJUAN -- "Kaji draft baru" --> B0
    A1 --> A1D --> A1D1
    A1D --> A1D2

    subgraph ING["Ingest, Validasi & Identitas"]
        direction TB
        C1{"Format PDF?"}
        C2["Tolak - log kegagalan"]
        C3{"Duplikat?<br/>HASH + UKURAN BERKAS"}
        C5["OCR halaman pertama"]
        C6["Ambil nomor, tanggal, judul"]
        C7["Terapkan naming convention"]
        C11["Ekstraksi teks & parsing struktur"]
    end

    A1D1 --> C1
    A1D2 --> C1
    A3 --> C1
    B0 --> C1
    C1 -- "Tidak" --> C2 --> ESK["Antrian penanganan manual"]
    C1 -- "Ya" --> C3
    C3 -- "Ya" --> ESK
    C3 -- "Tidak" --> C5 --> C6 --> C7 --> C11

    subgraph KB["Penyimpanan Ganda"]
        D5[("PDF ASLI<br/>bukti untuk validasi sampling")]
        D6[("BLOK TERSTRUKTUR di DB<br/>pasal + metadata + index")]
    end

    C11 --> D5 & D6

    D6 --> E0{"Pilih layanan"}
    C11 -.->|"khusus draft Jalur B"| E0
    E0 --> E1["Summary & Key Takeaways"]
    E0 --> E2["Harmonisasi"]
    E0 --> E3["Draft Surat Tanggapan - PoV"]

    E1 & E2 & E3 --> F1["MODE DETERMINISTIK<br/>default, wajib jalan offline"]
    F1 --> F2{"AI-Assisted aktif?"}
    F2 -- "Ya" --> F3["Naturalkan narasi"]
    F2 -- "Tidak" --> F4["Pakai hasil deterministik"]

    F3 & F4 --> G0{"Objek pasal sudah<br/>diatur di corpus?"}
    G0 -- "Tidak" --> G4["PASAL BARU / TAMBAHAN"]
    G0 -- "Ya" --> G1{"Ketentuannya?"}
    G1 -- "Berbeda" --> G2["MENGGANTIKAN"]
    G1 -- "Sama, diperinci" --> G3["MEMPERJELAS"]
    G1 -- "Identik" --> G5["DUPLIKASI"]
    G1 -- "Bertentangan" --> G6["KONFLIK"]

    G2 & G3 & G4 & G5 & G6 --> H1["Hasil di UI<br/>tiap butir MENGUTIP pasal sumber"]
    E1 --> H1
    H1 --> H2["VALIDASI SAMPLING DPEA<br/>2-3 dari 10 dokumen"]
    H2 --> H3{"Kutipan akurat?"}
    H3 -- "Tidak" --> H4["Perbaiki algoritma"] --> E0
    H3 -- "Ya" --> H5["Ekspor SURAT TANGGAPAN TERTULIS"]
    H5 --> Z(["Keputusan final oleh unit terkait<br/>DI LUAR SISTEM"])

    classDef store fill:#e8f0fe,stroke:#3b6ea5,stroke-width:2px,color:#12314f
    classDef det fill:#e9f7ef,stroke:#2e8b57,stroke-width:2px,color:#14432a
    classDef ai fill:#fdf3e3,stroke:#c98a1d,stroke-width:2px,color:#5c3d05
    classDef human fill:#fdeaea,stroke:#c0392b,stroke-width:2px,color:#5c1a13
    class D5,D6 store
    class F1,F4 det
    class F3 ai
    class H2,Z,ESK human
```

### 2.1 Perbandingan AS-IS vs TO-BE

| Aspek | AS-IS | TO-BE | Requirement Terkait |
| --- | --- | --- | --- |
| Pengumpulan dokumen | Manual, satu per satu | 3 jalur ingest terpusat | FR-SCR-01..07 |
| Penyimpanan | Folder pribadi/bersama, tidak baku | Knowledge base terstruktur & terindeks | FR-KB-01..09 |
| Pemahaman dokumen | Baca penuh | Summary + Key Takeaways dengan rujukan pasal | FR-ANL-04..06 |
| Pencarian peraturan terkait | Ingatan individu | Pemilihan kandidat sistematis + pencarian semantik | FR-HRM-02, FR-HRM-05 |
| Deteksi ketidakselarasan | Rawan luput | Temuan berlabel menggantikan/memperjelas/pasal baru/duplikasi/konflik, tertelusur ke pasal | FR-HRM-06..09 |
| Penyusunan tanggapan | Format bervariasi, 2–3 hari per tanggapan | Surat tanggapan format baku DPEA, target 2–3 jam | FR-POV-02..05 |
| Jejak audit | Tidak ada | Audit log & riwayat eksekusi — pekerjaan dapat ditinggalkan lalu dilanjutkan | FR-SYS-07, FR-SYS-10 |
| Keputusan final | Manusia | **Tetap manusia** (tidak berubah) | BRule-01 |

---

## 3. Flow Detail per Modul

### 3.1 Scraping & Ingest (Fitur 3.2)

```mermaid
flowchart TD
    A(["Admin KB membuka menu Sumber"]) --> B["Input / pilih daftar URL situs"]
    B --> C["Jalankan job scraping"]
    C --> D["Telusuri halaman target"]
    D --> E{"Ditemukan tautan PDF?"}
    E -- "Tidak" --> F["Catat: tidak ada dokumen<br/>pada sumber ini"]
    E -- "Ya" --> G["Unduh berkas"]
    G --> H{"Berkas valid PDF?"}
    H -- "Tidak" --> I["Tolak + catat alasan"]
    H -- "Ya" --> J{"Duplikat?<br/>cek hash / nomor peraturan"}
    J -- "Ya" --> K["Lewati, tandai duplikat"]
    J -- "Tidak" --> L["Simpan berkas mentah"]
    L --> M["Ekstraksi teks<br/>OCR bila hasil pindai"]
    M --> N["Ekstraksi metadata"]
    N --> O{"Metadata wajib lengkap?"}
    O -- "Tidak" --> P["Masuk antrian koreksi manual"]
    P --> Q["Analis melengkapi metadata"]
    Q --> R["Parsing struktur bab/pasal/ayat"]
    O -- "Ya" --> R
    R --> S["Klasifikasi & penempatan folder"]
    S --> T[("Tersimpan di Knowledge Base")]
    F --> U(["Ringkasan job ditampilkan"])
    I --> U
    K --> U
    T --> U
```

### 3.2 Analisa, Summary & Key Takeaways (Fitur 3.3)

```mermaid
flowchart TD
    A(["Analis memilih dokumen dari KB"]) --> B{"Mode AI-Assisted<br/>diaktifkan?"}
    B --> C["Jalankan mode Deterministik"]
    C --> D["Ambil struktur bab/pasal/ayat"]
    D --> E["Identifikasi dasar hukum<br/>& status keberlakuan"]
    E --> F["Seleksi pasal inti<br/>berbasis aturan & pola"]
    F --> G["Susun ringkasan terstruktur"]
    G --> H["Susun Key Takeaways<br/>+ rujukan pasal asal"]
    H --> I[("Simpan hasil deterministik")]
    I --> J{"AI-Assisted aktif?"}
    J -- "Tidak" --> M
    J -- "Ya" --> K{"Layanan AI tersedia?"}
    K -- "Tidak" --> L["Notifikasi: AI tidak tersedia,<br/>tampilkan hasil deterministik"]
    K -- "Ya" --> N["Naturalkan narasi<br/>tanpa mengubah substansi"]
    N --> O[("Simpan hasil AI-Assisted<br/>terpisah dari hasil dasar")]
    L --> M["Tampilkan hasil + label<br/>Draft / Rekomendasi"]
    O --> M
    M --> P["Analis dapat membandingkan<br/>versi deterministik vs AI"]
    P --> Q(["Ekspor / lanjut ke harmonisasi"])
```

### 3.3 Harmonisasi Draft vs Eksisting (Fitur 3.4)

```mermaid
flowchart TD
    A(["Analis mengunggah / memilih<br/>draft peraturan baru"]) --> B["Parsing struktur draft"]
    B --> C["Pilih kandidat peraturan eksisting<br/>dari KB berdasarkan topik & rujukan"]
    C --> D["Cocokkan rujukan pasal eksplisit"]
    D --> E["Cek status peraturan yang dirujuk"]
    E --> F{"Merujuk peraturan<br/>yang telah dicabut?"}
    F -- "Ya" --> G["Catat temuan:<br/>rujukan tidak berlaku"]
    F -- "Tidak" --> H["Analisis kesesuaian substansi<br/>antar pasal"]
    G --> H
    H --> I{"Klasifikasi temuan"}
    I -- "Bertentangan" --> J["Temuan: KONFLIK"]
    I -- "Mengatur hal sama" --> K["Temuan: DUPLIKASI"]
    I -- "Belum diatur" --> L["Temuan: GAP"]
    I -- "Selaras" --> M["Tidak dicatat sebagai temuan"]
    J --> N["Lengkapi atribut temuan:<br/>pasal draft, pasal pembanding,<br/>jenis, tingkat keyakinan"]
    K --> N
    L --> N
    N --> O["Susun ringkasan hasil<br/>+ rekomendasi awal"]
    O --> P["Tampilkan laporan harmonisasi"]
    P --> Q["Analis / SME menandai tiap temuan:<br/>valid atau tidak relevan"]
    Q --> R[("Umpan balik disimpan<br/>bahan evaluasi recall")]
    R --> S(["Ekspor laporan"])
```

### 3.4 Draft Tanggapan Berbasis PoV (Fitur 3.5)

```mermaid
flowchart TD
    A(["Analis memilih draft peraturan<br/>+ profil PoV unit"]) --> B["Muat profil PoV:<br/>tugas, fungsi, keilmuan, kata kunci"]
    B --> C["Muat template tanggapan baku unit"]
    C --> D["Muat checklist pasal wajib ditanggapi"]
    D --> E["Identifikasi pasal relevan / berdampak<br/>terhadap tugas & fungsi unit"]
    E --> F["Cek kelengkapan terhadap checklist"]
    F --> G{"Ada pasal wajib<br/>yang belum tertangani?"}
    G -- "Ya" --> H["Tandai sebagai<br/>butir belum lengkap"]
    G -- "Tidak" --> I["Susun narasi tanggapan per pasal<br/>sesuai sudut pandang unit"]
    H --> I
    I --> J["Isi ke template baku"]
    J --> K{"AI-Assisted aktif?"}
    K -- "Ya" --> L["Haluskan gaya bahasa<br/>sesuai kaidah unit"]
    K -- "Tidak" --> M["Gunakan narasi deterministik"]
    L --> N["Tampilkan draft tanggapan<br/>label: Draft / Rekomendasi"]
    M --> N
    N --> O["Analis menyunting bila perlu"]
    O --> P["Simpan sebagai versi baru"]
    P --> Q(["Ekspor sesuai format unit"])
    Q --> R(["Review & keputusan final<br/>oleh unit terkait - DI LUAR SISTEM"])
```

---

## 4. Sequence Diagram — Alur Utama Analisa

```mermaid
sequenceDiagram
    actor A as Analis
    participant UI as Web UI
    participant OR as Mode Orchestrator
    participant DE as Deterministic Engine
    participant KB as Knowledge Base
    participant AI as Layanan AI (opsional)
    participant LG as Audit Log

    A->>UI: Pilih dokumen + tentukan mode
    UI->>OR: Minta proses analisa
    OR->>LG: Catat mulai eksekusi (input, mode, versi aturan)
    OR->>DE: Jalankan proses deterministik
    DE->>KB: Ambil struktur, metadata, pasal
    KB-->>DE: Data dokumen
    DE-->>OR: Hasil dasar (summary, key takeaways)
    OR->>KB: Simpan hasil deterministik

    alt AI-Assisted diaktifkan
        OR->>AI: Kirim hasil dasar untuk penghalusan bahasa
        alt Layanan AI tersedia
            AI-->>OR: Narasi hasil penghalusan
            OR->>KB: Simpan hasil AI terpisah
        else Layanan AI tidak tersedia
            AI--xOR: Gagal / timeout
            OR->>UI: Notifikasi fallback ke hasil deterministik
        end
    end

    OR->>LG: Catat selesai eksekusi + status mode
    OR-->>UI: Kirim hasil + label "Draft / Rekomendasi"
    UI-->>A: Tampilkan hasil (dapat dibandingkan)
```

---

## 5. State Dokumen dalam Sistem

```mermaid
stateDiagram-v2
    [*] --> Diterima: berhasil di-ingest
    Diterima --> Ditolak: format bukan PDF / duplikat
    Diterima --> Diproses: ekstraksi teks & metadata
    Diproses --> PerluKoreksi: metadata wajib tidak lengkap
    PerluKoreksi --> Diproses: analis melengkapi
    Diproses --> Gagal: ekstraksi / OCR gagal
    Gagal --> Diproses: proses ulang manual
    Diproses --> Terindeks: struktur & index terbentuk
    Terindeks --> Aktif: status keberlakuan = berlaku
    Terindeks --> Dicabut: status keberlakuan = dicabut
    Aktif --> Diubah: terbit peraturan pengubah
    Diubah --> Dicabut
    Aktif --> Dicabut
    Ditolak --> [*]
    Dicabut --> [*]: tetap tersimpan, tidak dihapus
```

---

## Riwayat Revisi

| Versi | Tanggal | Perubahan | Penyusun |
| --- | --- | --- | --- |
| 1.0 | 7 Sep 2026 | Draft awal: AS-IS, TO-BE, 4 flow modul, sequence & state diagram | BA |
| 2.0 | 8 Sep 2026 | TO-BE v2 hasil Weekly Update #1: pemisahan Jalur A/B, dedup hash+ukuran, OCR halaman 1, penyimpanan ganda, klasifikasi temuan baru, validasi sampling | BA |
