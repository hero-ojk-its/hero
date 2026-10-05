# Fase 2 — Baseline Analisa, Summary & Key Takeaways

**Proyek:** HERO · **Fitur:** URD 3.3 · **Jadwal URD:** 12 Oktober – 8 November 2026
**Peran:** Data & AI Engineer · **Tanggal:** 28 September 2026 (dimulai lebih awal dari jadwal)

Angka terukur ulang di [`docs/FASE2_EVALUASI.md`](FASE2_EVALUASI.md) (`hero fase2`).

---

## Ringkasan satu paragraf

Fase 2 dimulai dengan mengukur keluaran yang sudah ada (v1), bukan langsung
membangun. Pengukuran menunjukkan ringkasan v1 berupa tumpukan kalimat
tanpa jangkar (67% memuat "(1) … (2) …" tanpa pasal) dan hanya mewakili 29%
pasal normatif. Baseline baru (v2) menyusun ringkasan dan poin kunci **dari
struktur pasal/ayat**, sehingga 99,3% poin menunjuk pasal yang benar dan
terlacak ke teksnya, dan 97,7% pasal normatif terwakili. Mode AI-Assisted
dibangun sebagai lapisan narasi yang **hanya boleh memakai fakta v2** dan
diverifikasi otomatis. Mode ini sudah teruji dengan klien tiruan, tetapi
**belum dijalankan terhadap Claude sungguhan** karena kredensial belum
tersedia. Dua dari tiga indikator Fase 2 tercapai.

---

## 1. Yang sudah dibangun

| Komponen | Isi | Mode |
|---|---|---|
| `hero/analysis/structured.py` | **Analisa v2**: poin kunci per ayat (daftar tetap utuh), kategori (Sanksi, Larangan, Pelaporan, Perizinan, Kewajiban, Batas Waktu, Pencabutan, Masa Berlaku), subjek yang diatur, kerangka BAB→pasal, jenis sanksi, nama peraturan yang dicabut, deteksi "substansi di Lampiran", ringkasan bertemplat yang setiap kalimatnya bercitasi | Deterministik |
| — cadangan bertingkat | Pasal (dari parser struktur) → seksi & butir bernomor (Surat Edaran) → kalimat teks berlabel jujur "pasal tidak terbaca" | Deterministik |
| `hero/analysis/ai.py` | **AI-Assisted**: Claude (`claude-opus-5`) menarasikan ulang fakta v2 ber-ID; keluaran JSON schema; verifikasi ID/angka/pasal; kembali ke v2 bila gagal, ditolak, galat, atau dinonaktifkan; dokumen `internal` tidak pernah dikirim; hasil di-cache | AI-Assisted (opsional, default mati) |
| `hero/analysis/clauses.py` | **Klausul relevan dengan kebutuhan pengguna**: pasal dalam satu dokumen diurutkan dari gabungan semantik (e5) + BM25 + **niat** (kategori poin v2) | Deterministik + vektor |
| `hero/analysis/evaluate.py` | Evaluasi v1 vs v2 (9 metrik), indikator Fase 2, **templat telaah ahli** (CSV) | — |
| Integrasi | Laci detail Knowledge Base kini memakai v2; API `/api/analisa/{id}`, `/api/analisa/{id}/klausul`, `/api/analisa-status`; CLI `hero analisa`, `hero klausul`, `hero fase2` | — |
| Konfigurasi | `analysis:` di `config/sources.yaml` (`ai_enabled`, `ai_model`, `ai_effort`, `ai_allow_internal`) | — |
| Pengujian | 19 test baru; total **312 lulus** | — |

### Contoh keluaran v2 (POJK 1/2026, Tenaga Kerja Asing)

> POJK Nomor 1 Tahun 2026 tentang Penggunaan Tenaga Kerja Asing dan Program Alih Pengetahuan oleh Bank Umum masih berlaku. …
> **Kewajiban pelaporan:** Bank yang akan menggunakan TKA wajib menyampaikan rencana penggunaan TKA kepada Otoritas Jasa Keuangan dalam rencana bisnis Bank. *[Pasal 12 ayat (1)]*
> **Larangan:** KCBLN dilarang menggunakan TKA selain untuk jabatan: a. Pimpinan KCBLN; dan/atau b. Tenaga Ahli atau Konsultan. *[Pasal 7 ayat (1)]*
> **Peraturan ini mencabut:** Peraturan Otoritas Jasa Keuangan Nomor 37/POJK.03/2017 tentang Pemanfaatan Tenaga Kerja Asing … *[Pasal 37]*

Di v1, larangan yang sama terpotong tepat sebelum daftarnya ("…selain untuk
jabatan: a.") dan tanpa rujukan pasal.

---

## 2. Hasil terukur (91 dokumen produksi)

| Metrik | v1 | **v2** |
|---|---:|---:|
| Poin kunci berujukan pasal | 81,7% | **99,3%** |
| Poin kunci terlacak ke teks pasalnya | 81,7% | **99,3%** |
| Cakupan pasal normatif | 29,0% | **97,7%** |
| Poin terpotong di awal daftar | 14,4% | **3,5%** |
| Definisi terbaca sebagai kewajiban | 2,9% | **0,2%** |
| Dokumen tanpa poin kunci | 6 | **4** |
| Median kata ringkasan | 314 | **139** |
| Ringkasan dengan penanda ayat lepas | 67,0% | **2,2%** |
| Kalimat ringkasan bercitasi pasal | 0% | **64,8%** |
| Waktu analisa | — | **0,4 s untuk 91 dokumen** |

Kalimat v2 tanpa citasi (35%) adalah kalimat identitas, kerangka, dan
subjek. Isinya berasal dari metadata, bukan dari satu pasal.

### Indikator Fase 2 (URD bagian 5)

| Indikator | Status |
|---|---|
| Summary & Key Takeaways untuk ≥10 dokumen uji | ✅ **87 dokumen** |
| Waktu proses per dokumen < 5 menit (Deterministik) | ✅ terburuk **11,5 s** (termasuk ekstraksi PDF) |
| Mode AI-Assisted dapat di-toggle, narasi lebih natural | ⏳ **toggle & jalur lengkap tersedia dan teruji dengan klien tiruan; belum diverifikasi dengan Claude sungguhan** (kredensial belum ada) |

---

## 3. Temuan

**T1 — Ringkasan ekstraktif tidak cocok untuk teks hukum.** Memilih
kalimat berdasarkan frekuensi kata menghasilkan potongan ayat tanpa konteks.
Teks hukum sudah punya struktur (BAB → pasal → ayat), dan struktur itu
adalah ringkasan yang lebih baik daripada skor statistik mana pun.

**T2 — Kategori normatif harus peka huruf besar.** Legal drafting menulis
kewajiban dengan huruf kecil ("wajib menyampaikan") dan istilah dengan huruf
kapital ("Cuti Wajib", "Wajib Pajak"). Pencocokan tanpa membedakan huruf
membuat definisi terbaca sebagai kewajiban.

**T3 — 7 PADK menyimpan substansinya di Lampiran.** Batang tubuhnya hanya 2–4
pasal yang menunjuk ke Lampiran. v2 menyatakannya terang-terangan dan
menampilkan judul bagian Lampiran, alih-alih memberi ringkasan yang tampak
lengkap padahal kosong.

**T4 — Pasal sanksi tidak bisa ditemukan lewat kemiripan teks.** Sanksi
ditulis lewat rujukan silang ("yang melanggar ketentuan sebagaimana dimaksud
dalam Pasal 4, Pasal 5 … dikenai sanksi"). Untuk kueri "sanksi jika melanggar
penggunaan TKA", pasal sanksi utama berada di peringkat **24 (semantik)** dan
**37 (BM25)**. Menggabungkan kategori hasil ekstraksi (niat) membawanya ke
tiga besar. Pelajarannya: vektor dan kata kunci perlu dilengkapi pengetahuan
struktur hukum.

**T5 — Parser struktur meninggalkan judul sub-bagian di akhir ayat**
("… Paragraf 2 Bidang Tugas yang…"). Dibersihkan di v2; sumbernya sebaiknya
diperbaiki di parser Fase 1.

**T6 — 4 dokumen masih tanpa poin kunci** (terjemahan Inggris dan berkas
yang teksnya hampir kosong). v2 tidak mengarang poin untuk dokumen ini.

**Kesalahan sendiri yang tertangkap selama pengerjaan** (dicatat karena
polanya berulang): pemecah ayat membaca "Pasal 4 **ayat (2)**" sebagai ayat
baru; v2 sempat membuat **24** dokumen tanpa poin (regresi vs v1, karena
Surat Edaran tidak punya pasal); heuristik judul Lampiran menangkap blok
tanda tangan; kerangka menghitung BAB milik Lampiran; nama peraturan yang
dicabut diawali penyebutan diri sendiri ("Peraturan OJK *ini* …").
Semuanya diperbaiki dan dikunci dengan test.

---

## 4. Yang dibangun selanjutnya

Diurutkan menurut dampak terhadap indikator dan kebutuhan pengguna.

| # | Pekerjaan | Mengapa | Butuh dari Anda / mitra |
|---|---|---|---|
| 1 | **Verifikasi AI-Assisted sungguhan**: aktifkan, jalankan pada ±20 dokumen publik, ukur tingkat lolos verifikasi & biaya per dokumen | Satu-satunya indikator Fase 2 yang belum tercapai | Kredensial Claude (`ant auth login` atau `ANTHROPIC_API_KEY`) |
| 2 | **Telaah ahli** atas `data/export/fase2_telaah_ahli.csv` (10 dokumen, 95 baris) | Mengubah metrik "sifat" menjadi metrik "benar menurut ahli"; menjadi set evaluasi berlabel pertama | ±2 jam dari 1–2 analis DPEA |
| 3 | **Ringkasan isi Lampiran** untuk dokumen berat-Lampiran (T3) | 7 PADK saat ini hanya punya judul bagian | — |
| 4 | **Evaluasi pencari klausul** dengan set kueri berlabel (seperti `eval_queries.yaml`), terpisah kata kunci/parafrase/niat | T4 diperbaiki dari beberapa contoh; perlu diukur luas | Contoh pertanyaan nyata dari pengguna |
| 5 | Perbaikan parser struktur di sumbernya (T5, pasal tidak terbaca T6) | Membersihkan akar masalah, bukan gejalanya | — |
| 6 | **Persiapan Fase 3 (Harmonisasi)**: pasangkan poin v2 draft ↔ eksisting per kategori & subjek, gunakan graf (lineage, dasar hukum) + vektor e5 untuk kandidat konflik | Poin kunci v2 yang berkategori & berujuk pasal adalah unit pembanding yang dibutuhkan fitur 3.4 | Draft peraturan uji (rancangan dari ojk.go.id sudah ada 650) |

---

## 5. Cara menjalankan

```bash
hero analisa --semua                       # analisa v2 semua dokumen (±0,5 s), laci KB ikut diperbarui
hero analisa <doc_id>                      # tampilkan ringkasan & poin kunci
hero analisa <doc_id> --ai                 # coba AI-Assisted (butuh kredensial; kembali ke v2 bila gagal)
hero klausul <doc_id> "sanksi jika …"      # pasal yang relevan dengan kebutuhan
hero fase2                                 # evaluasi → docs/FASE2_EVALUASI.md + templat telaah ahli
```

Mengaktifkan AI-Assisted: `pip install -e ".[ai]"`, siapkan kredensial,
lalu set `analysis.ai_enabled: true` di `config/sources.yaml`.
