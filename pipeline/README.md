# HERO — Harmonisasi & Analisa Regulasi Otomatis

Baseline implementasi **Fitur 3.2 (Scraping & Pengumpulan Dokumen Peraturan)**
beserta lapisan ekstraksi PDF/OCR yang menjadi fondasi fitur 3.3–3.5, mengacu
pada *HERO User Requirement Document v1.1* dan *Project Charter Mitra OJK*.

Seluruh pemrosesan berjalan pada **Mode Deterministik (non-AI)** — sesuai URD
bagian 3.1, mode ini wajib tersedia dan harus dapat berjalan mandiri tanpa
ketergantungan pada layanan AI. Mode AI-Assisted dirancang sebagai lapisan
*enhancement* di atas keluaran ini, bukan penggantinya.

> Folder ini adalah **lapisan data & AI** HERO (peran Data/ML): ingest, ekstraksi,
> knowledge base, analisa, dan harmonisasi. Antarmuka ada di [`../frontend`](../frontend);
> server API di `hero/server/` adalah implementasi acuan kontrak
> [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md) untuk pengembangan frontend, bukan
> pengganti backend tim.

## 0. Kode di repo, data di workspace

Dokumen peraturan dan katalog **tidak masuk repo** (NDA, `.gitignore` root mengabaikan
`data/`). Kode dijalankan dari sebuah *workspace* yang memegang `config/` dan `data/`:

```
hero/pipeline/          ← kode (repo ini): paket `hero`, tests, config contoh, docs
<workspace>/            ← mis. ../Capstone di mesin pengembang, ~/hero-work di VPS
├── config/sources.yaml     salinan config + rahasia lewat .env
├── config/harmonisasi.yaml
├── config/ground_truth.yaml
├── .env                    HERO_ONEDRIVE_SHARE_URL, ANTHROPIC_API_KEY (opsional)
└── data/                   katalog SQLite, knowledge base PDF, ekspor, log
```

```bash
cd <workspace>
python3 -m venv .venv
.venv/bin/pip install -e "<repo>/pipeline[api,vector,dev]"
cp <repo>/pipeline/config/*.yaml config/      # sekali, lalu sesuaikan
cp <repo>/pipeline/.env.example .env          # isi tautan OneDrive di sini, bukan di YAML
.venv/bin/hero version
```

Tautan berbagi OneDrive adalah *bearer secret* (siapa pun yang memegangnya membaca
seluruh folder DPEA), karena itu `sources.yaml` hanya memuat `${HERO_ONEDRIVE_SHARE_URL}`.

## 0a. Perintah lapisan data (Oktober 2026)

| Perintah | Untuk | Laporan |
|---|---|---|
| `hero scan ukur` | Ukuran berkas tiap rekaman inventaris lewat `HEAD`, **tanpa unduh** (kriteria penerimaan MoM #4) | — |
| `hero scan penerimaan` | Dokumen terindeks (URL + nama + nama berkas + ukuran) vs *ground truth* DPEA (`config/ground_truth.yaml`) | `--out` JSON |
| `hero penamaan bentrok` | Seberapa sering tiap urutan tombol Nama/Tahun/Jenis/Bidang menghasilkan nama kembar | — |
| `hero akses audit [--apply]` | "Publik harus terbukti": dokumen yang tidak ada di register publik diketatkan menjadi `internal` | — |
| `hero snapshot` | Respons API (dokumen publik saja) sebagai JSON statis untuk frontend | `data/export/frontend-snapshot/` |
| `hero harmonisasi jalankan <doc_id\|pdf>` | Draft vs KB: kandidat, rujukan & statusnya, temuan per pasal | `--out` JSON |
| `hero harmonisasi siapkan-uji [--unduh]` | Pasangan peraturan perubahan ↔ induk dari register publik | — |
| `hero harmonisasi evaluasi` | Recall & kalibrasi ambang (TD-07, FR-HRM-12) | `docs/HARMONISASI_EVALUASI.md` |
| `hero bridge …` | Jembatan ke backend tim: pindai (mode push), ekstraksi, cermin korpus, layanan analisa | `docs/INTEGRASI_BACKEND.md` |
| `hero bench-vektor` | SQLite (NumPy/sqlite-vec) vs Postgres pgvector: latensi, recall, ukuran | `docs/VEKTOR_BENCHMARK.md` |

Format nama dari tombol UI (#89/#90): `hero.kb.naming.template_from_components(["jenis",
"nomor", "tahun", "nama"])` → `{jenis} - {nomor_urut} - {tahun} - {judul:90}`.
Laporan lengkap pekerjaan ini: [`docs/LAPORAN_DATA_AI_2026-10-02.md`](docs/LAPORAN_DATA_AI_2026-10-02.md).

---

## 1. Cakupan yang sudah terpenuhi

| URD | Cakupan proses | Status |
|-----|----------------|--------|
| 3.2 | Fetch PDF dari daftar situs yang diinput manual | ✅ `hero scrape` |
| 3.2 | Unggah dokumen manual | ✅ `hero upload` |
| 3.2 | Baca folder lokal & folder OneDrive | ✅ `hero folders`, `hero onedrive` |
| 3.2 | Validasi format file | ✅ magic bytes `%PDF-`, bukan ekstensi |
| 3.2 | Ekstraksi metadata (judul, nomor, tanggal terbit) | ✅ parser deterministik |
| 3.2 | Klasifikasi & penempatan ke folder knowledge base | ✅ rule-based, folder dibuat otomatis |
| 3.3 | Ekstraksi struktur (bab, pasal, ayat) | ✅ parser penomoran baku |
| 3.3 | Identifikasi dasar hukum & status berlaku/dicabut | ✅ |
| 3.3 | Summary & Key Takeaways | ✅ ekstraktif + penambangan klausul normatif |
| 3.3 | Identifikasi topik/klausul relevan | ✅ termasuk penanda relevansi Unit Bisnis IT |
| 4.1 | Antarmuka dasar pencarian & penyajian hasil | ✅ `hero search`, `hero show`, `hero export` |
| 7.1 | Mitigasi risiko "PDF hasil scan / tidak terstruktur" | ✅ OCR otomatis per halaman |
| 7.1 | Mitigasi risiko "folder tidak dapat diakses" | ✅ dilaporkan per folder, tidak menggagalkan run |

**Di luar cakupan baseline ini** (sesuai URD 4.2): auto-crawling terjadwal,
integrasi real-time JDIH, pemrosesan dokumen non-PDF, serta fitur 3.4
(harmonisasi) dan 3.5 (tanggapan PoV) — keduanya memakai keluaran struktur
pasal/ayat dari modul ini sebagai unit pembanding.

---

## 2. Instalasi

```bash
python3 -m venv .venv
.venv/bin/pip install -e .                  # inti: scraping, ingest, OCR, analisa
.venv/bin/pip install -e ".[api,vector]"    # + API frontend, graf, vektor deterministik
.venv/bin/pip install -e ".[api,vector,pg]"  # + jembatan ke backend (pgvector)
.venv/bin/pip install -e ".[all]"           # + pencarian semantik (model lokal 0,2–2,2 GB)

# OCR (wajib untuk dokumen hasil scan) — bahasa Indonesia + Inggris
brew install tesseract tesseract-lang        # macOS
# sudo apt-get install tesseract-ocr tesseract-ocr-ind   # Debian/Ubuntu

.venv/bin/hero version      # verifikasi OCR terdeteksi
```

Butuh Python ≥ 3.11 (diuji pada 3.14). Tanpa Tesseract sistem tetap berjalan:
dokumen born-digital diproses normal, dokumen hasil scan dilaporkan gagal
ekstraksi agar dapat dieskalasi manual.

---

## 3. Penggunaan

```bash
hero sources                       # daftar sumber terdaftar
hero scrape                        # Jalur 1 — scraping semua situs aktif di config

# Situs bisa diinput langsung tanpa mengubah config (bisa lebih dari satu --url):
hero scrape --url https://ojk.go.id/id/regulasi/default.aspx \
            --follow /regulasi/Pages/ --exclude abstrak --limit 5
hero scrape --url "https://jdih.ojk.go.id/Web/ViewPeraturan/Index?sektor=02&jenisPeraturan=06"
hero scrape --sektor 01 --sektor 02 --jenis 06 --limit 20   # JDIH OJK, sektor/jenis dinamis

hero upload berkas.pdf folder/     # Jalur 2 — unggah manual
hero folders --path ~/Regulasi     # Jalur 3 — folder lokal / OneDrive tersinkron
hero onedrive --check              # cek tautan OneDrive dapat dibaca tanpa login (tanpa unduh)
hero onedrive --limit 100          # Jalur 3b — folder OneDrive dari config, 100 PDF BARU per putaran
hero onedrive --share-url <link> --subfolder downloads --limit 30   # ad-hoc
hero ingest-all                    # seluruh jalur sekaligus

hero analyze berkas.pdf            # analisa satu dokumen tanpa menyimpan
hero analyze berkas.pdf --json out.json --tables
hero ocr-check berkas.pdf          # sumber teks per halaman (text-layer / OCR)

hero kb                            # isi knowledge base
hero search "keamanan siber"       # pencarian full-text
hero show <doc_id> --articles      # detail + seluruh pasal
hero stats                         # statistik & indikator URD Fase 1
hero export --out data/export      # ekspor CSV: documents / articles / takeaways
hero export --format jsonl         # varian JSONL (field bersarang dipertahankan)
```

Semua sumber dikonfigurasi di [`config/sources.yaml`](config/sources.yaml) —
tidak ada host yang ditemukan otomatis oleh sistem.

### 3a. Seluruh data: inventaris → unduh → ekspor

Scraping dipecah menjadi dua tahap supaya "semua data" tidak berarti "unduh
3 GB PDF dulu":

```bash
hero discover                    # 1. daftar SEMUA rekaman + SEMUA kolom tiap sumber
hero inventory                   #    ringkasan per sumber & status
hero harvest --limit 50          # 2. unduh dokumennya ke knowledge base (bertahap)
hero harvest --source jdih-ojk --status berlaku --all
hero inventory-export            # 3. satu tabel, semua kolom: CSV, XLSX, JSON, HTML
hero kb-restructure              # rapikan KB ke sumber/kategori/jenis/tahun/status
```

| Sumber | Cara mencapai semua rekaman | Rekaman (15-09-2026) |
|---|---|---|
| JDIH OJK | JSON grid per pasangan sektor × jenis (120 pasangan), lalu halaman detail | 986 |
| OJK · Regulasi | *Postback* ASP.NET pager (157 halaman × 10), lalu halaman detail | 1.570 |
| OJK · Rancangan Regulasi | *Postback* pager (65 halaman × 10); dokumen berupa ZIP | 650 |

`hero discover` aman dihentikan dan dijalankan ulang: daftar digabung, dan
hanya halaman detail yang belum dibaca yang diambil. Status hukum rekaman
ojk.go.id (yang situsnya tidak menuliskannya) disalin dari JDIH OJK bila
jenis|nomor|tahun-nya cocok.

Cakupan pencocokan (15-09-2026): ±1.000 dari 1.570 rekaman ojk.go.id mendapat
status dari JDIH. Sisanya sebagian besar **bukan instrumen OJK** — PBI Bank
Indonesia, Keputusan Bapepam-LK (KEP-…/BL, …/PM), PMK/KMK Kemenkeu, UU/PP —
yang memang tidak diregister JDIH OJK, sehingga statusnya jujur dibiarkan
"tidak diketahui". Pencocokan sengaja **tidak** mengabaikan jenis: SEOJK
5/2020 dan POJK 5/2020 adalah dua peraturan berbeda.

Struktur knowledge base:

```
data/knowledge_base/<sumber>/<kategori>/<jenis>/<tahun>/<status>/<nama>.pdf
   sumber   : jdih-ojk · ojk-regulasi · ojk-rancangan · unggah-manual · folder-lokal
   status   : berlaku · diubah · dicabut · rancangan · status-tidak-diketahui
```

---

## 4. Arsitektur

```
hero/
├── config.py            Pembacaan config/sources.yaml
├── models.py            Struktur data bersama (metadata, halaman, pasal, record)
├── pipeline.py          Orkestrasi: fetch → validasi → ekstraksi → klasifikasi → simpan
├── inventory.py         Discover (daftar + detail + rekonsiliasi status) semua sumber
├── api.py               scrape_urls() — input situs langsung dari Python
├── cli.py               Antarmuka CLI (Typer + Rich)
├── cli_data.py          Perintah lapisan data: scan, akses, snapshot, harmonisasi
├── ingest/
│   ├── web.py           Scraper HTTP: robots.txt, retry, rate limit per host, POST
│   ├── jdih.py          Adapter JDIH OJK (grid JSON, sektor × jenis, halaman detail)
│   ├── sharepoint.py    Adapter ojk.go.id (postback pager, detail, lampiran)
│   ├── probe.py         Ukuran berkas saat scan (HEAD/Range, tanpa unduh) + kriteria penerimaan
│   ├── archive.py       ZIP rancangan → "Batang Tubuh" PDF (aman zip-slip)
│   ├── folders.py       Folder lokal & OneDrive tersinkron
│   └── onedrive.py      Share link OneDrive publik (ditunda)
├── extract/
│   ├── pdf.py           Ekstraksi teks + reflow paragraf + fallback OCR
│   ├── ocr.py           Tesseract (ind+eng), confidence per halaman
│   ├── metadata.py      Parser jenis/nomor/tanggal/dasar hukum/status
│   ├── structure.py     Parser BAB / Bagian / Pasal / ayat / seksi Romawi
│   └── summary.py       Summary ekstraktif + Key Takeaways + profil topik
├── server/            API untuk frontend (FastAPI) — satu router per layar
│   ├── app.py           /api/kb · /api/ingest · /api/sync · /api/search · /api/graph
│   └── schemas.py       Kontrak request/response (→ docs/openapi.json)
├── service/flows.py     Alur layar Ingest: scan → hasil pemindaian → job ingest
├── vector/              Vektor: potong per pasal → embed → sqlite-vec/NumPy → cari
├── graph/               Graf: identitas peraturan, MENCABUT/MENGUBAH/BERDASAR, CTE
├── dq/                  Mutu data: aturan, profil, cakupan, indikator Fase 1, nama kembar
├── harmonisasi/         Draft vs KB per pasal: rujukan, kandidat, label, evaluasi (URD 3.4)
├── bridge/              Jembatan ke backend tim: worker pindai & ekstraksi,
│                        cermin korpus, pgvector, layanan /api/v1/ml/*
├── bench.py             Perbandingan relasional · vektor · graf (terukur)
├── bench_vector.py      SQLite vs pgvector: latensi, recall@k, ukuran indeks
└── kb/
    ├── readmodel.py     Read model tabel & laci Knowledge Base (label UI, FTS5)
    ├── topics.py        Kosakata topik terkendali untuk filter "Topik"
    ├── classify.py      Klasifikasi kategori & penempatan folder
    ├── catalog.py       Katalog SQLite + FTS5 + inventaris + jejak audit ingest
    ├── export.py        Ekspor tabel datar (CSV/JSONL) untuk analisa lanjutan
    ├── inventory_export.py  Inventaris → satu tabel semua kolom (CSV/XLSX/JSON/HTML)
    ├── access.py        Audit klasifikasi akses + redaksi tautan berbagi
    ├── snapshot.py      Snapshot JSON respons API untuk frontend (publik saja)
    ├── restructure.py   Pindahkan KB ke sumber/kategori/jenis/tahun/status
    └── templates/inventory_page.html   Halaman penjelajah data
```

### Alur satu dokumen

```
sumber (web / upload / folder / OneDrive)
   ↓  validasi magic bytes %PDF-
   ↓  SHA-256  →  duplikat?  →  berhenti, catat sebagai duplicate
   ↓  ekstraksi teks per halaman (PyMuPDF)
   ↓  halaman < 120 karakter?  →  render 300 dpi  →  Tesseract (ind+eng)
   ↓  reflow paragraf + buang header/footer/nomor halaman
   ↓  metadata: jenis, nomor, tanggal, penerbit, dasar hukum, status
   ↓  struktur: BAB / Pasal / ayat  (lampiran & penjelasan dipisahkan)
   ↓  summary, Key Takeaways, topik, relevansi IT
   ↓  status: sumber (JDIH / rancangan) → cocokkan ke JDIH → teks dokumen
   ↓  klasifikasi kategori
   └→ data/knowledge_base/<sumber>/<kategori>/<jenis>/<tahun>/<status>/<nama>.pdf
      + baris di katalog SQLite (metadata, teks, struktur, analisa)
```

---

## 5. Keputusan desain

**Validasi berdasarkan magic bytes.** Situs peraturan kerap menyajikan halaman
error HTML dengan `Content-Type: application/pdf`. Yang diperiksa adalah 1024
byte pertama, bukan ekstensi maupun header.

**Deduplikasi dua lapis.** Sebelum mengunduh, URL dicek terhadap katalog;
setelah mengunduh, isi dicek melalui SHA-256. Halaman regulasi per sektor di
ojk.go.id saling merujuk dokumen yang sama, sehingga tanpa lapisan pertama satu
run mengunduh berkas yang sama berulang kali.

**Identitas dokumen diambil dari blok pembuka.** Peraturan Indonesia selalu
dibuka dengan `<JENIS> NOMOR <nomor> TENTANG <perihal>`. Deteksi jenis dan nomor
dibatasi pada blok sebelum kata `TENTANG` — tanpa batasan ini, kutipan pada
bagian *Mengingat* terbaca sebagai identitas dokumen itu sendiri.

**Pasal pada lampiran & penjelasan dipisahkan.** Setelah formula penutup
(`Ditetapkan di …`), setiap `Pasal N` adalah rujukan, bukan judul. Keduanya
tetap disimpan, namun hanya pasal batang tubuh yang menjadi unit pembanding
untuk harmonisasi.

**Ayat dikenali secara berurutan.** Penanda `(n)` hanya membuka ayat baru bila
`n` adalah nomor berikutnya yang diharapkan. Aturan ini yang membedakan judul
ayat sebenarnya dari rujukan silang seperti *"sebagaimana dimaksud pada ayat (1)
dan ayat (2)"*.

**Reflow paragraf.** PDF "SALINAN" OJK memposisikan tiap kata secara terpisah,
sehingga ekstraksi mentah menghasilkan satu kata per baris. Reflow menyatukan
kembali paragraf tanpa merusak penanda struktural.

**Surat Edaran tidak memakai pasal.** SEOJK/SEBI disusun dalam seksi angka
Romawi (`I. KETENTUAN UMUM`), sehingga parser seksi berjalan berdampingan
dengan parser pasal.

**Scraping sopan.** `robots.txt` dipatuhi, jeda antar-permintaan dapat
dikonfigurasi, ukuran unduhan dibatasi, dan satu situs hanya ditelusuri sedalam
satu hop dari halaman yang didaftarkan manual.

**Terjemahan resmi berbahasa Inggris ikut dikenali.** OJK dan BI menerbitkan
versi Inggris berdampingan dengan aslinya (`FINANCIAL SERVICES AUTHORITY
REGULATION NUMBER 26/POJK.04/2014 CONCERNING …`). Parser mengenali bentuk
`NUMBER`/`CONCERNING`/`Article` sehingga dokumen tersebut tidak berakhir tanpa
metadata.

## 5a. Keluaran untuk analisa lanjutan

`hero export` menghasilkan tiga tabel yang dapat digabungkan lewat `doc_id`:

| Berkas | Isi | Kegunaan |
|--------|-----|----------|
| `documents.csv` | Satu baris per peraturan beserta metadatanya | Inventarisasi knowledge base |
| `articles.csv` | Satu baris per pasal (batang tubuh) | Unit pembanding fitur harmonisasi (URD 3.4) |
| `takeaways.csv` | Satu baris per klausul normatif | Bahan checklist tanggapan PoV (URD 3.5) |

CSV ditulis dengan BOM UTF-8 agar teks berbahasa Indonesia terbaca benar di
Excel.

---

## 5b. API frontend, vektor, dan graf

```bash
hero serve                          # API di http://127.0.0.1:8000 — dokumentasi interaktif di /docs
hero readmodel                      # sinkron read model KB (otomatis juga dari API)
hero graph build                    # graf relasi dari Riwayat Peraturan, Landasan Hukum, Mengingat
hero graph findings                 # status register yang bertentangan dengan relasi pencabutan
hero graph export                   # nodes.csv + edges.csv + load.cypher untuk Neo4j
hero vector build [--lsa-only]      # indeks vektor per pasal (LSA deterministik + semantik)
hero vector search "…" -m hybrid    # lexical | lsa | semantic | hybrid
hero bench                          # ukur ulang semuanya → docs/DB_COMPARISON.md

# Fase 2 — Analisa, Summary & Key Takeaways (URD 3.3)
hero analisa --semua                # ringkasan terstruktur & poin kunci berbasis pasal (v2)
hero analisa <doc_id> [--ai]        # tampilkan; --ai: narasi Claude terverifikasi (fallback ke v2)
hero klausul <doc_id> "sanksi …"    # pasal yang relevan dengan kebutuhan pengguna
hero fase2                          # evaluasi v1 vs v2 + indikator → docs/FASE2_EVALUASI.md

# Sprint 3 — US-20a/US-20 (identitas & nama baku), US-24 (kategori), SPIKE #42
hero identitas [PDF] [--ocr]        # nomor/tanggal/judul dari hal. 1 (+ blok penutup); tanpa PDF = survei KB
hero penamaan cek ["templat"]       # validasi + pratinjau nama pada dokumen nyata
hero penamaan set "templat"         # simpan templat aktif (konfigurasi: naming.template)
hero penamaan terapkan [--apply]    # namai ulang seluruh KB (#90); tanpa --apply = dry-run
hero koreksi daftar                 # dokumen yang menunggu koreksi manual
hero koreksi selesaikan <doc_id> --nomor … --tanggal YYYY-MM-DD --judul … --oleh …
hero kategori cek [--belahan uji]   # validasi config/kategori.yaml + akurasi vs sektor JDIH
hero kategori uji "judul"           # coba aturan pada satu judul
hero spike unduh / jalankan         # SPIKE #42 di VPS → docs/SPIKE_42_PENYIMPANAN.md
```

Sprint 3: [docs/SPRINT3_US20_US24.md](docs/SPRINT3_US20_US24.md) ·
[docs/SPIKE_42_PENYIMPANAN.md](docs/SPIKE_42_PENYIMPANAN.md). Aturan kategori
ada di [config/kategori.yaml](config/kategori.yaml) — ubah di sana, bukan di kode.
Dokumen yang identitasnya tidak lengkap disimpan di `data/antrian_koreksi/`
(di luar folder KB) sampai dikoreksi.

Ringkasan Fase 2 (yang dibangun, temuan, langkah berikutnya):
[docs/FASE2_BASELINE.md](docs/FASE2_BASELINE.md).

| Dokumen | Isi |
|---|---|
| [docs/API_CONTRACT.md](docs/API_CONTRACT.md) | Setiap layar desain → endpoint & field, termasuk selisih mockup vs data |
| [docs/openapi.json](docs/openapi.json) | Skema mesin untuk generator tipe TypeScript |
| [docs/DB_COMPARISON.md](docs/DB_COMPARISON.md) | Relasional vs vektor vs graf: latensi, kualitas temu-kembali, penyimpanan |

Ringkasnya: **relasional + read model** untuk tabel dan filter (ratusan kali
lebih cepat dari derivasi per-request), **vektor** untuk pencarian makna
(model e5-large: MRR parafrase 0,77 vs BM25 0,47), **graf** untuk dasar
hukum, pencabutan, dan dampak perubahan. Ketiganya di SQLite, tanpa server
basis data tambahan.

## 5c. Jembatan ke backend tim

Folder ini adalah lapisan data; **backend tim** memegang dokumen, kategori,
sesi pindai, dan jejak audit, dan frontend bicara ke backend. `hero/bridge/`
menyambungkan keduanya lewat kontrak internal backend — tanpa mengubah satu
baris pun di `../backend` untuk dua jalur pertama:

```bash
hero bridge status                 # apa yang tersambung, apa yang belum
hero bridge pindai --loop          # sesi pindai backend dilayani adapter HERO
                                   #   (JDIH grid JSON, postback ojk.go.id, OneDrive)
hero bridge ekstraksi --loop       # antrian ekstraksi: OCR → metadata → pasal → vektor
hero bridge sinkron                # cermin korpus backend → katalog (untuk harmonisasi)
hero bridge vektor-isi --apply     # isi kolom articles.embedding (pgvector) backend
hero bridge serve --port 8100      # layanan /api/v1/ml/* untuk layar Analisa & Harmonisasi
hero bridge sekali                 # satu putaran lengkap — untuk systemd timer
```

| Dokumen | Isi |
|---|---|
| [docs/INTEGRASI_BACKEND.md](docs/INTEGRASI_BACKEND.md) | Arsitektur, peta field tiap kontrak, cara memasang, **celah kontrak** yang perlu diputuskan bersama backend |
| [docs/API_CONTRACT_ML.md](docs/API_CONTRACT_ML.md) | Endpoint `/api/v1/ml/*` untuk layar Analisa & Harmonisasi |
| [docs/VEKTOR_BENCHMARK.md](docs/VEKTOR_BENCHMARK.md) | Vektor di SQLite vs pgvector: latensi, recall@k, ukuran, harga kolom 1536 dimensi |
| [docs/PENYIMPANAN_SERVER.md](docs/PENYIMPANAN_SERVER.md) | Pilihan memindahkan data & tools ke server: ukuran terukur, biaya, risiko, langkah mundur |

Penyimpanan ganda juga berlaku untuk vektor: **satu vektor per pasal** di
`articles.embedding` backend (dipakai pencarian dari frontend) dan **satu
vektor per jendela 80 kata** di basis data vektor lapisan data (dipakai
harmonisasi dan kalibrasi). Model yang sama, jadi hasilnya sebanding;
perbandingan terukurnya ada di `docs/VEKTOR_BENCHMARK.md`.

## 6. Pengujian

```bash
.venv/bin/python -m pytest tests/ -q
```

Suite pengujian (lihat `pytest tests/ -q`) mencakup parser metadata (bentuk Indonesia dan terjemahan
Inggris), pemisahan pasal/ayat/lampiran, pembersihan teks, jalur OCR pada PDF
hasil scan, penemuan tautan PDF, penolakan berkas non-PDF, deduplikasi, dan
ingest ujung-ke-ujung.

Fixture PDF hasil scan dapat dibuat ulang dengan:

```bash
.venv/bin/python tests/make_fixtures.py <sumber.pdf> 4
```

---

## 7. Catatan sumber data

| Situs | Status | Keterangan |
|-------|--------|------------|
| `ojk.go.id` — regulasi + 5 kanal sektor | ✅ aktif | Halaman daftar tidak memuat PDF; HERO menelusuri satu hop ke halaman detail |
| `ojk.go.id` — rancangan regulasi | ✅ aktif | Draft peraturan, bahan uji fitur 3.4 & 3.5 |
| `peraturan.bpk.go.id` | ⚠️ nonaktif | Menjawab HTTP 403 untuk seluruh klien non-browser (proteksi bot) |
| `jdih.kemenkeu.go.id` | ⚠️ nonaktif | Tidak dapat dijangkau saat verifikasi |

Berkas pendamping (`Abstrak`, `FAQ`, `Matriks`) dikecualikan lewat
`exclude_patterns` agar yang tersimpan adalah peraturannya sendiri.

---

## 8. Deployment ke VPS + Integrasi Nextcloud

Seluruh proyek (bukan cuma datanya) bisa dipindah ke VPS Ubuntu 24.04, jalan
otomatis lewat `systemd timer` harian, dengan knowledge base dan hasil export
tersinkron ke Nextcloud lewat WebDAV (`rclone`) — jalan sama saja apapun cara
Nextcloud Anda terpasang (native, Snap, atau Docker/AIO).

Panduan lengkap langkah-demi-langkah: **[deploy/README.md](deploy/README.md)**
