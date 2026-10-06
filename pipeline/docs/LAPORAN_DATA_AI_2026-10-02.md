# Laporan Lapisan Data & AI HERO — 2 Oktober 2026

> Ditulis untuk: Data/ML (Fathir) sebagai pemilik pekerjaan, dan tim HERO / PO sebagai pembaca
> keputusan. Semua angka diukur ulang oleh perintah yang disebut di tiap bagian; penyebutnya
> selalu dicantumkan.

## Ringkasan eksekutif

1. **Lapisan data yang ada di `../Capstone` ternyata tidak bisa dijalankan** (paket `hero` tidak
   dapat di-import setelah folder dipindah & di-rename) dan **tidak berada di bawah version
   control**. Sudah dipulihkan, lalu dipindahkan ke repo tim sebagai `pipeline/` dengan CI.
   Data (NDA) tetap di luar repo. Test: **384 lulus** (348 lama + 36 baru).
2. **Kriteria penerimaan scraping MoM #4 terpenuhi tanpa unduh:** JDIH **984/986 (99,8%)**,
   ojk.go.id **1.556/1.570 (99,1%)** terindeks lengkap (URL, nama dokumen, nama berkas,
   **ukuran**). Sebelumnya ukuran diketahui untuk 14 dari 3.206 rekaman.
3. **Angka *ground truth* DPEA perlu didefinisikan ulang:** JDIH punya 986 rekaman, bukan
   400–500. Yang cocok dengan 400–500 adalah **POJK berstatus berlaku (422)**. Tanpa definisi
   yang sama, "jumlah terindeks vs ground truth" tidak bisa dinilai lulus/gagal.
4. **Format nama dari tombol Nama/Tahun/Jenis/Bidang tanpa Nomor menghasilkan nama kembar**
   (0,6–1,5% berkas; "Nama" saja 21–30%). Dengan Nomor: 0% di JDIH, 0,4% di ojk.go.id (dan
   sisa itu duplikasi sumber, bukan kelemahan format). Rekomendasi: tambah tombol **Nomor**.
5. **15 dokumen internal OJK berlabel "publik"** (cuti pegawai, tarif perjalanan dinas,
   `…/PADKINT…`, SEDK) — label inilah yang dipakai pengaman AI. Diketatkan; aturan baru:
   *publik harus terbukti*.
6. **Cacat ekstraksi Fase 1 ditemukan dan diperbaiki di sumbernya:** nomor rujukan hukum
   ("Undang-Undang Nomor **21** Tahun **2011**") terhapus sebagai "nomor halaman" di **43 dari
   118 dokumen (36%)**; dua dokumen salah identitas. Semua diekstraksi ulang → **0 tersisa**.
7. **Prototipe mesin Harmonisasi (Fase 3) selesai, deterministik, terukur:** pada 14 pasangan
   peraturan perubahan ↔ induk, induk menjadi kandidat #1 di **14/14**, **recall 90,1%**
   (target FR-HRM-12 ≥ 70%), AUC 0,895. Ambang TD-07 dikalibrasi dari data: **0,40**.
8. **Frontend bisa langsung membangun di atas data nyata**: snapshot respons API asli,
   103 dokumen publik, 314 berkas JSON, 2,0 MB — tanpa menunggu backend.

---

## 1. Titik awal

| Bagian | Kondisi saat dipelajari |
|---|---|
| `hero/frontend` | React + Vite, 6 halaman. **Seluruh data mock**: 8 baris `regulasiData.ts` dengan kategori yang tidak ada di data ("Fintech", "Asuransi", "Tata Kelola IT & AI"), `id` numerik (data nyata: heksadesimal 32 karakter), Dashboard berangka tetap (128, 96, …), halaman Harmonisasi masih *placeholder* |
| `Capstone/` | Lapisan data matang: 16 rb baris, 348 test, Fase 1–2 (ingest 3 jalur, OCR, struktur pasal, analisa v2, vektor, graf, API acuan). Namun: (a) `.venv` menunjuk `~/Documents/…` lama dan paket ada di `hero-tools/` → **`import hero` gagal**, CLI mati; (b) bukan repo git — salinan tim (`hero-team/backend`) sudah basi |
| Data | 3.206 rekaman inventaris, 91 PDF di KB, katalog SQLite 58 MB, indeks vektor 129 MB |

## 2. Pemulihan & migrasi ke repo tim

| Perubahan | Alasan |
|---|---|
| Kode → `hero/pipeline/` (paket `hero`, test, config contoh, dokumen) | Slot `/pipeline/` sudah disiapkan di CODEOWNERS untuk Data/ML; kode akhirnya ter-*versioning* |
| Model **workspace**: kode di repo, `config/` + `.env` + `data/` di `../Capstone` | `.gitignore` root mengabaikan `data/` dan `*.pdf` (NDA). `Capstone/.venv` kini menjalankan paket dari repo |
| Tautan berbagi OneDrive dipindah ke `.env` (`HERO_ONEDRIVE_SHARE_URL`), YAML memuat `${…}`; variabel yang tak terisi menonaktifkan sumbernya | Tautan "Anyone with the link" adalah *bearer secret* ke folder DPEA |
| `.github/workflows/pipeline-ci.yml` (pytest + Tesseract `ind`), baris CODEOWNERS `/pipeline/` diaktifkan | Setiap PR ke lapisan data teruji otomatis, offline, tanpa kredensial |
| `Capstone/hero-tools/` ditandai arsip (`ARSIP.md`, catatan di README) | Mencegah dua salinan kode yang menyimpang lagi |
| Test yang membaca path literal `hero/pipeline.py` diperbaiki; data pribadi (path OneDrive berbasis surel, potongan token) di test diganti fiktif | Test kebal terhadap rename; repo bersih dari data pribadi |

## 3. Kriteria penerimaan scraping (MoM #4, #87/#88)

**Masalah:** dokumen "berhasil di-scrape" bila saat scan sudah diketahui URL resmi, nama
dokumen, nama berkas, **dan ukuran**. Ukuran hanya diketahui untuk 14 rekaman.

**Yang dibangun:** `hero scan ukur` — satu `HEAD` per berkas, cadangan `Range: bytes=0-0` yang
badannya tidak pernah dibaca (JDIH mengabaikan `Range` dan akan mengirim berkas utuh),
mematuhi robots.txt & jeda per host, satu *thread* per host, bisa dihentikan dan dilanjutkan.
`hero scan penerimaan` membandingkan dengan `config/ground_truth.yaml`.

| Sumber | Rekaman | Terindeks lengkap | Gagal (alasan) | Ground truth | Rasio |
|---|---:|---:|---|---:|---:|
| JDIH OJK | 986 | **984 (99,8%)** | 1 tanpa berkas, 1 HTTP 500 | 400–500 | 2,19× |
| ojk.go.id Regulasi | 1.570 | **1.556 (99,1%)** | 14 tanpa berkas di sumber | ±1.700 | 0,92× |
| ojk.go.id Rancangan | 650 | 636 (97,8%) | 13 HTTP 404, 1 tanpa berkas | — | — |

Total korpus bila diunduh semua: **±2,1 GB** (JDIH 0,74 · regulasi 0,92 · rancangan 0,46 GB;
rata-rata 0,6–0,75 MB, terbesar 94 MB). Ini menjawab pertanyaan kapasitas penyimpanan Hamdan.

**Temuan penyebut (perlu jawaban DPEA, #87):**

| Angka DPEA | Kandidat definisi yang cocok | Nilai |
|---|---|---:|
| JDIH ±400–500 | POJK berstatus berlaku | **422** |
| | SEOJK (semua status) | 393 |
| | seluruh register JDIH | 986 |
| ojk.go.id ±1.700 | rekaman di daftar | 1.570 |
| | peraturan unik (identitas) | 1.358 |
| | berkas (termasuk Abstrak/FAQ) | 2.665 |

Bug yang tertangkap selama pekerjaan ini: versi pertama probe memegang *lock* SQLite selama
25 permintaan HTTP, sehingga ketiga host saling menunggu dan JDIH macet di rekaman ke-29.
Diperbaiki: commit per baris, I/O jaringan di luar *lock*.

## 4. Format nama berkas dinamis (#89 UI, #90 rename)

`hero.kb.naming.template_from_components(["jenis","nomor","tahun","nama"])` →
`{jenis} - {nomor_urut} - {tahun} - {judul:90}`, dan kebalikannya untuk memulihkan tombol di
UI. Tombol boleh diklik ulang; "Bidang" = label kategori ("Pasar Modal"). Logika rename
memakai mesin templat yang sama, jadi UI dan rename tidak bisa berbeda definisi.

Dampak diukur pada inventaris (`hero penamaan bentrok`), persentase = berkas yang berbagi nama
dengan **peraturan lain**:

| Urutan tombol | JDIH (986) | ojk.go.id (1.570) |
|---|---:|---:|
| Nama | 21,3% | 29,5% |
| Jenis → Tahun | 98,9% | 87,9% |
| Nama → Jenis → Tahun | 0,6% | 1,5% |
| Bidang → Tahun → Nama | 3,4% | 3,6% |
| **Jenis → Nomor → Tahun → Nama** | **0,0%** | **0,4%** |

Di ojk.go.id, 82 dari 88 nama kembar pada format bernomor adalah **peraturan yang sama
dicantumkan dua kali** oleh situsnya (URL berbeda) — itu duplikasi sumber, bukan kelemahan
format. **Rekomendasi untuk PO:** tambahkan tombol **Nomor**; tanpa itu folder lokal DPEA akan
berisi "X.pdf" dan "X (2).pdf" untuk dua peraturan berbeda.

## 5. Tata kelola akses data

`documents.access_class` ber-default `publik`, sehingga ke-30 dokumen dari OneDrive mitra
masuk sebagai publik — termasuk *Cuti Pegawai OJK* (PDK 1/2024), *Tarif Perjalanan Dinas
Pegawai* (KDK 36/2013), pedoman `5/PADKINT.01/2025` (PADK **internal**), empat SEDK. Lapisan AI
memakai label ini (`ai_allow_internal: false`) untuk memutuskan apa yang boleh dikirim ke
layanan eksternal.

Aturan baru (`hero akses audit`): **publik hanya bila terbukti** — diambil dari situs regulasi
publik, atau identitasnya terdaftar di JDIH/ojk.go.id. Sisanya `internal` dengan alasan
tertulis. Audit hanya mengetatkan, tidak pernah melonggarkan label pengguna.
Hasil: **15 dari 34 dokumen non-web diketatkan** (19 terbukti publik). Ekspor CSV kini
meredaksi tautan berbagi dan menyertakan kolom `access_class`.

## 6. Data untuk frontend

`hero snapshot` merekam respons **endpoint API asli** (bentuk = `docs/API_CONTRACT.md`) ke
`Capstone/data/export/frontend-snapshot/`: **103 dokumen publik, 314 berkas, 2,0 MB**, path
meniru API (`api/kb/documents/<id>.json`). Dibangun dari salinan katalog yang sudah dibersihkan
dari dokumen non-publik, sehingga *facet*, dashboard, dan daftar konsisten dan tidak
membocorkan hitungan internal (diuji `grep` + test otomatis).

Selisih mock vs data nyata yang perlu diantisipasi UI:

| Di mock | Di data nyata (103 dokumen publik) |
|---|---|
| Kategori Fintech / Asuransi / Tata Kelola IT & AI | Pasar Modal 41, Perbankan 11, IKNB 9, Kelembagaan 5, … — ambil dari `/api/kb/facets` |
| Jenis POJK / SEOJK / PDK / SEDK | POJK 52, PADK 11, SEOJK 7, PADG 2, PBI 2, UU 2 |
| Tanggal selalu ada ("12 Maret 2024") | 7 dokumen tanpa tanggal terbit → tampilkan "—" |
| Judul pendek | 26 judul > 100 karakter, terpanjang 191 |
| `id: number` | `id`: heksadesimal 32 karakter |
| Topik tunggal | `topik_semua` jamak per dokumen |

Snapshot **belum di-commit**: keputusan memasukkannya ke `frontend/public/` ada pada Ikhwan/PO.
Satu perintah membuatnya ulang kapan pun.

## 7. Perbaikan mutu ekstraksi (ditemukan lewat evaluasi harmonisasi)

Evaluasi harmonisasi menghasilkan `konflik` palsu terhadap induk peraturan itu sendiri. Menelusuri
penyebabnya membuka cacat di hulu:

| Cacat | Akar masalah | Dampak | Perbaikan |
|---|---|---|---|
| Nomor rujukan hilang: "Undang-Undang Nomor\nTahun\ntentang" | Pembersih nomor halaman membuang **setiap** baris berisi angka saja; tata letak OJK menaruh "21" dan "2011" di baris sendiri | **43/118 dokumen (36%)** — merusak deteksi rujukan (FR-HRM-03/04) dan perbandingan angka | Angka dalam konteks rujukan/kuantitas dipertahankan dan disambung kembali |
| POJK 14/2023 tersimpan sebagai "POJK 4/2023" | *Text layer* PDF tidak memuat baris "NOMOR 14 TAHUN 2023 TENTANG"; blok identitas melebar sampai *Menimbang* dan mengambil "Undang-Undang Nomor 4 Tahun 2023" | identitas salah → relasi perubahan tak dikenali | Blok identitas berhenti di Menimbang/Mengingat; dokumen tertaut register memakai identitas register (nilai lama disimpan di `metadata_json.identitas_sebelumnya`) |
| "1/POJK.05/20172017" | Dua objek teks bertumpuk di PDF | identitas tidak terbentuk | Tahun ganda dinormalisasi |
| Halaman berisi huruf tercerai ("s\nd\nm\np") lolos OCR | OCR hanya dipicu bila < 120 karakter | 15/6.529 halaman (0,23%) | Deteksi *text layer* rusak → OCR halaman itu |
| "SEBI 31/14/UPPB **2029**" | Penomoran BI seri lama (31 = 1998) dihitung sebagai seri baru | tahun di masa depan di graf | Tahun BI tidak boleh melewati tahun depan; kode unit seri lama (UPPB) dikenali |

`hero ekstrak-ulang --terdampak --apply` memproses ulang dokumen tersimpan dengan jalur kode
yang sama dengan ingest (27 dtk untuk 43 dokumen). Sesudahnya: 0 dokumen dengan rujukan tanpa
nomor; identitas dokumen ↔ register cocok **69/69**; konflik identitas di graf 2 → 1.

Pengukuran ulang Fase 2 (`hero fase2`, kini 118 dokumen): poin berujukan pasal 99,7%, cakupan
pasal normatif 98,3%, 114 dokumen ber-ringkasan. Satu regresi kecil yang perlu ditelusuri:
ringkasan dengan penanda ayat lepas 2,2% → 4,2%.

## 8. Prototipe mesin Harmonisasi (Fase 3, URD 3.4)

Dimulai lebih awal (Fase 3 terjadwal 9 Nov) karena beban Data/ML memuncak di Fase 2–4 dan
TD-07 memblokir lima jenis label.

**Alur (deterministik, offline):** rujukan eksplisit + statusnya dari graf (FR-HRM-03/04) →
rencana perubahan dari teks draft ("Ketentuan Pasal N diubah", "disisipkan Pasal NA") →
TF-IDF 1–2 gram per pasal terhadap seluruh korpus (FR-HRM-05) → kandidat = kemiripan dokumen +
porsi pasal berpadanan + relasi eksplisit (FR-HRM-02) → label + keyakinan + alasan + perbedaan
konkret (FR-HRM-06..09) → rekomendasi bertemplat (FR-HRM-10). Setiap temuan membawa kutipan
pasal draft & pembanding dan tautan `/api/kb/documents/{id}/pdf#page=N`; keluaran berlabel
*Draft / Rekomendasi*.

**Aturan label:** `pasal_baru` (kemiripan < ambang) → `duplikasi` (redaksi ≥ 95% sama dan tidak
diubah eksplisit) → beda angka/Rupiah/modalitas: `menggantikan` bila draft mengubah/mencabut
peraturan itu, **`konflik` bila tidak** (dua aturan berbeda sama-sama berlaku) →
`memperjelas` (isi lama ≥ 80% termuat, draft lebih rinci) → `menggantikan`. Klausul baku
(redaksi serupa di ≥ 3 peraturan, mis. pasal sanksi) tetap dilaporkan dengan keyakinan ×0,6.

**Evaluasi tanpa anotasi manual:** peraturan perubahan menyatakan sendiri pasal mana yang
diubah dan disisipkan. 14 pasangan perubahan ↔ induk (2023–2026) diunduh dari JDIH ke KB
(28 PDF publik, 0 gagal). Hasil (`docs/HARMONISASI_EVALUASI.md`):

| Ukuran | Nilai |
|---|---:|
| Induk menjadi kandidat #1 | **14 / 14** |
| Pasal diubah dipasangkan ke pasal induk yang benar | 197 / 213 |
| **Recall deteksi** (FR-HRM-12, target ≥ 70%) | **90,1%** |
| AUC pemisahan "objek sama" vs "baru" | 0,895 |
| Pasal sisipan tidak tertaut ke induk | 74 / 88 |
| Waktu per draft | 1–2 dtk (korpus pembanding 3.634 pasal dari 90 dokumen) |

**TD-07 — ambang `objek_sama`:**

| Ambang | Recall | Pasal sisipan keliru tertaut ke induk |
|---:|---:|---:|
| 0,30 (awal) | 91,5% | 42,0% |
| **0,40 (dipakai)** | **89,7%** | **15,9%** |
| 0,45 (Youden J) | 88,3% | 12,5% |

Di atas 0,40 tautan keliru hampir tidak turun lagi sementara recall terus turun; karena
FR-HRM-12 mengukur recall, 0,40 dipilih. Angka ini **usulan berbasis data untuk disetujui PO**,
bukan keputusan final.

Kejujuran soal angka: angka recall pertama yang terbaca (95,8%) **terinflasi** oleh nomor pasal
ganda dalam hasil parse; setelah deduplikasi 92,5%, dan setelah ambang dinaikkan 90,1%. Dari 5
label `konflik` pada set amandemen, 4 ternyata palsu akibat cacat identitas (bagian 7) dan
hilang setelah diperbaiki; 1 tersisa (prosedur pemeriksaan BPJS vs PVML — subjek berbeda).

**Demo pada draft nyata** (RPOJK Standar Penyelenggaraan TI oleh BPR & BPRS, PDF dari situs
rancangan, tidak dimasukkan ke KB): draft merujuk **POJK 20/2014 dan POJK 4/2015 yang sudah
dicabut** → sistem menyarankan POJK 7/2024 dan POJK 9/2024; 31 dari 33 pasal `pasal_baru` karena
KB belum memuat peraturan TI perbankan — mesin kini menyarankan mengunduh **POJK
11/POJK.03/2022 (Penyelenggaraan TI oleh Bank Umum)** dari register terlebih dahulu.

**Batas yang harus diketahui pengguna:**
- `konflik` belum pernah divalidasi terhadap label manusia (amandemen tidak memuatnya). Perlu
  contoh dari validasi sampling DPEA.
- Status hukum berasal dari register JDIH, yang tidak mencatat putusan MK. Contoh nyata: graf
  menyatakan UU 25/1992 (Perkoperasian) dicabut UU 17/2012, padahal UU 17/2012 dibatalkan
  seluruhnya oleh MK pada 2014 sehingga UU 25/1992 berlaku kembali.
- Kemiripan TF-IDF bersifat leksikal; parafrase berat bisa terbaca `pasal_baru`. Indeks e5
  (lokal, AI-Assisted) sudah tersedia untuk lapisan berikutnya.
- Kualitas bergantung pada isi KB (118 dokumen dari 3.206 di register).

## 9. Skill yang dibuat

| Skill | Lokasi | Kenapa krusial |
|---|---|---|
| `hero-data-pipeline` | `hero/.claude/skills/` (repo, aktif untuk seluruh tim) | Invarian lapisan data (offline-first, kutip sumber, NDA, publik-harus-terbukti, migrasi aditif, lock SQLite) + perintah rutin |
| `hero-harmonisasi` | `hero/.claude/skills/` | Aturan label, bentuk keluaran untuk layar Harmonisasi, protokol evaluasi & garis dasar angka |
| `document-stated-ground-truth` | `Capstone/skills/` (pustaka metode) | Mengkalibrasi ambang tanpa anotasi dari dokumen yang menyatakan jawabannya sendiri |
| `provenance-access-audit` | `Capstone/skills/` | Mencegah data internal keluar lewat label default "publik" |
| `api-snapshot-fixtures` | `Capstone/skills/` | Fixture frontend dari respons API nyata yang disanitasi |

## 10. Keputusan yang dibutuhkan

| # | Untuk | Pertanyaan | Rekomendasi |
|---|---|---|---|
| 1 | Pak Faris (#87) | Ground truth JDIH 400–500 menghitung apa? | Tetapkan definisi; kandidat terkuat "POJK berlaku" (422) |
| 2 | PO + Ikhwan + Rafli (#89/#90) | Tambah tombol **Nomor**? | Ya — tanpa nomor 0,6–3,6% nama kembar |
| 3 | PO (TD-07) | Ambang `objek_sama` 0,40? | Ya, dengan evaluasi ulang tiap ada set berlabel baru |
| 4 | PO | 15 dokumen OneDrive kini `internal` — benar? | Tinjau daftar `hero akses audit --semua` |
| 5 | Ikhwan | Pakai snapshot di `frontend/public/` sambil menunggu API? | Ya; hanya dokumen publik |
| 6 | DPEA | Contoh konflik nyata untuk validasi sampling | 2–3 draft yang pernah ditanggapi |
| 7 | Sprint 3 (dari laporan sebelumnya) | Tanggal dari blok penutup boleh dipakai untuk penamaan? | Ya (sudah direkomendasikan) |

## 11. Langkah berikutnya

1. **Fase 3:** `konflik` hanya bila subjek yang diatur sama (pakai `subject_of` dari analisa v2);
   lapisan e5 sebagai pencocok kedua untuk parafrase; endpoint `/api/harmonisasi` mengikuti
   bentuk `Report.to_dict()`; set berlabel kedua dari validasi DPEA.
2. **KB:** `hero harvest` bertahap untuk POJK/SEOJK berlaku (±700 berkas, ±0,5 GB) agar
   harmonisasi punya pembanding; prioritaskan sektor yang relevan bagi DPEA (TI).
3. **Mutu:** telusuri regresi "penanda ayat lepas" 2,2% → 4,2%; satu konflik identitas graf
   tersisa; status putusan MK sebagai sumber status tambahan.
4. **Fase 2:** verifikasi AI-Assisted dengan kredensial Claude (satu-satunya indikator Fase 2 yang
   belum tercapai).

## Lampiran A — Cara mengulang

```bash
cd ../Capstone                                  # workspace
.venv/bin/hero scan ukur && .venv/bin/hero scan penerimaan
.venv/bin/hero penamaan bentrok
.venv/bin/hero akses audit
.venv/bin/hero ekstrak-ulang --terdampak        # tanpa --apply: daftar saja
.venv/bin/hero snapshot
.venv/bin/hero harmonisasi siapkan-uji -n 14 --unduh
.venv/bin/hero harmonisasi evaluasi -n 14
.venv/bin/hero harmonisasi jalankan <doc_id | draft.pdf> --out laporan.json
cd ../hero/pipeline && ../../Capstone/.venv/bin/python -m pytest tests -q
```

## Lampiran B — Perubahan data di workspace

Backup sebelum setiap penulisan massal: `data/hero_catalog.backup-2026-10-02-before-probe.db`,
`…-before-reextract.db`. Perubahan: kolom `inventory.file_*` (3.206 baris), 15 dokumen →
`internal`, 27 dokumen baru (14 pasangan evaluasi), 43 dokumen diekstraksi ulang, graf, analisa
v2, indeks LSA & e5 dibangun ulang.

## Lampiran C — Berkas baru/berubah di repo

`pipeline/` (seluruhnya baru; modul baru: `ingest/probe.py`, `kb/access.py`, `kb/snapshot.py`,
`kb/reextract.py`, `dq/naming_collision.py`, `harmonisasi/{refs,engine,evaluate}.py`,
`cli_data.py`; diubah: `config.py`, `kb/catalog.py`, `kb/naming.py`, `kb/export.py`,
`extract/pdf.py`, `extract/metadata.py`, `graph/identity.py`, `cli.py`),
`.github/workflows/pipeline-ci.yml`, `.github/CODEOWNERS`, `.gitignore`,
`.claude/skills/{hero-data-pipeline,hero-harmonisasi}/`. Belum di-commit.
