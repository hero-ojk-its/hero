# REPORT — Log Perkembangan Proyek HERO

Catatan kronologis setiap sesi pengembangan. Entri terbaru di atas.

---

## 2026-09-28 (sesi 2) · Baseline Fase 2 — Analisa, Summary & Key Takeaways

### Ringkasan

Klarifikasi dari pengguna: mockup adalah acuan **alur backend**, bukan API
yang dipasang langsung ke frontend. Tidak ada perubahan yang diperlukan —
logika alur sudah terpisah di `hero/service/flows.py`.

Fase 2 (URD 3.3) dimulai sebagai Data & AI Engineer, lebih awal dari jadwal
URD (12 Okt). Diawali audit keluaran v1 pada 91 dokumen, lalu v2 dibangun
dan diukur terhadapnya. Laporan: `docs/FASE2_BASELINE.md`,
`docs/FASE2_EVALUASI.md`.

| | v1 | v2 |
|---|---:|---:|
| Poin berujukan pasal / terlacak ke pasal | 81,7% | **99,3%** |
| Cakupan pasal normatif | 29,0% | **97,7%** |
| Median kata ringkasan | 314 | **139** |
| Ringkasan dengan ayat lepas | 67% | **2,2%** |
| Dokumen tanpa poin | 6 | **4** |

Indikator Fase 2: ✅ ≥10 dokumen (87) · ✅ < 5 menit (terburuk 11,5 s) ·
⏳ AI-Assisted — jalur lengkap & teruji dengan klien tiruan, **belum
diverifikasi dengan Claude sungguhan** (tidak ada kredensial).

### Perubahan

| Berkas | Isi |
|---|---|
| `hero/analysis/structured.py` | v2: poin per ayat berkategori & bercitasi, subjek, kerangka, sanksi, pencabutan, deteksi Lampiran, ringkasan bertemplat; cadangan seksi → teks berlabel |
| `hero/analysis/ai.py` | AI-Assisted (`claude-opus-5`, `fallbacks: "default"`, JSON schema, prompt caching); verifikasi ID/angka/pasal; fallback; blokir dokumen internal; cache |
| `hero/analysis/clauses.py` | Klausul relevan: semantik + BM25 + niat (kategori v2, diurutkan kepadatan) |
| `hero/analysis/evaluate.py` | 9 metrik v1 vs v2, indikator Fase 2, templat telaah ahli |
| `hero/kb/readmodel.py` | Laci detail KB memakai v2 |
| `hero/server/app.py`, `hero/cli.py` | `/api/analisa/*`, `hero analisa`, `hero klausul`, `hero fase2` |
| `hero/config.py`, `config/sources.yaml` | `analysis:` (default `ai_enabled: false`, `ai_allow_internal: false`) |
| `pyproject.toml` | extra `ai` (`anthropic>=1.0`) |
| `tests/test_analysis.py` | 19 test; total **312 lulus** |
| `skills/grounded-llm-summarization/` | Skill baru (total 8) |
| `belajar.md` Bagian 11 | Penjelasan Fase 2 |

### Temuan utama

1. Ringkasan ekstraktif tidak cocok untuk teks hukum; struktur pasal/ayat
   adalah ringkasan yang lebih baik.
2. Kategori normatif harus peka huruf besar ("wajib" ≠ "Cuti Wajib").
3. 7 PADK menyimpan substansi di Lampiran — kini dinyatakan eksplisit.
4. **Pasal sanksi tak terjangkau kemiripan teks** (ditulis lewat rujukan
   silang): peringkat 24 (semantik) dan 37 (BM25); sinyal niat membawanya ke
   tiga besar.

### Kesalahan sendiri yang ditemukan dan diperbaiki

Pemecah ayat membaca "Pasal 4 ayat (2)" sebagai ayat baru; v2 sempat membuat
24 dokumen tanpa poin (Surat Edaran tanpa pasal); judul Lampiran menangkap
blok tanda tangan; kerangka menghitung BAB Lampiran; nama peraturan yang
dicabut diawali penyebutan diri; pencari klausul awalnya tidak menemukan
pasal sanksi. Semua dikunci dengan test.

### Operasional

- Katalog dicadangkan: `data/hero_catalog.backup-before-fase2.db`.
- Tabel baru: `analysis_v2`, `analysis_ai`.
- Templat telaah ahli: `data/export/fase2_telaah_ahli.csv` (10 dokumen, 95 baris).

### Butuh dari pengguna / mitra

Kredensial Claude untuk memverifikasi AI-Assisted; ±2 jam analis DPEA untuk
telaah ahli; contoh pertanyaan nyata untuk mengevaluasi pencari klausul.

---

## 2026-09-28 · Backend sesuai desain frontend + perbandingan relasional · vektor · graf

### Ringkasan

Permintaan: sesuaikan backend dengan desain UI (7 layar) agar frontend tidak
kerja dua kali, percepat pengambilan data, dan bangun vector database (serta
graf) untuk dibandingkan dengan basis data relasional. Semua dibangun di
atas SQLite yang sudah ada — tanpa server basis data tambahan.

**Hasil terukur (data produksi, 91 dokumen, `docs/DB_COMPARISON.md`):**

| | Hasil |
|---|---|
| Tabel/filter/detail KB via read model | 0,06–0,14 ms; 20–495× lebih cepat dari derivasi per-request |
| Pencarian makna, e5-large | MRR parafrase **0,78** vs BM25 0,47; kata kunci 0,90 (setara BM25) |
| Rata-rata MRR kedua set | semantik 0,84 · hibrida 0,79 · BM25 0,68 · LSA 0,68 |
| Graf | 1.710 node, 3.333 edge; dampak UU 21/2011 = 946 peraturan dalam 3 level, ±5 ms |
| Pengujian | **293 lulus** (sebelumnya 229) |

### Yang dibangun

| Berkas | Isi |
|---|---|
| `hero/server/app.py`, `schemas.py` | API FastAPI, 23 endpoint, satu kelompok per layar; badge `{value,label,tone}`; `/api/meta/enums`, `/api/kb/facets` |
| `hero/service/flows.py` | Alur scan → hasil pemindaian → job ingest (URL, OneDrive, folder), status persisten di SQLite |
| `hero/kb/readmodel.py`, `topics.py` | Read model KB (CQRS), FTS5 bertingkat (semua kata → sebagian kata), kosakata 16 topik, penyelarasan pasal & urgensi beserta alasannya |
| `hero/vector/` | Potongan per pasal (jendela 80 kata), embedder LSA (deterministik) + semantik (MiniLM/e5-large, dipilih lewat config), penyimpanan sqlite-vec + NumPy, hibrida RRF |
| `hero/graph/` | Identitas peraturan kanonik, edge MENCABUT/MENGUBAH/BERDASAR dari JDIH + Mengingat, lineage/impact/basis via recursive CTE, ekspor Neo4j, temuan status |
| `hero/bench.py`, `config/eval_queries.yaml` | Benchmark: latensi, 24 kueri berlabel (kata kunci + parafrase), graf, penyimpanan; kesimpulan dihitung dari angka |
| `hero/inventory.py`, `pipeline.py`, `config.py` | Kedalaman crawl per *level* (bukan halaman), kategori target saat harvest, `VectorSettings` |
| `deploy/systemd/hero-api.service`, `install.sh`, `run-pipeline.sh` | API sebagai layanan; model semantik opt-in (`HERO_SEMANTIC=1`); graf & vektor diperbarui setiap pipeline harian |
| `docs/API_CONTRACT.md`, `docs/openapi.json` | Kontrak per layar + daftar selisih mockup vs data |
| `docs/DB_COMPARISON.md` | Laporan perbandingan (dihasilkan `hero bench`) |
| `belajar.md` Bagian 10 | Penjelasan relasional/vektor/graf dengan angka proyek |
| `skills/ui-driven-api-contract/`, `skills/retrieval-evaluation/` | Skill baru (total 7) |

### Temuan data baru

1. **33 status "berlaku" kemungkinan basi** — peraturan lain menyatakan
   mencabutnya penuh (`hero graph findings`). Tidak ditimpa otomatis.
2. **230 status "tidak diketahui" dapat disimpulkan "dicabut"** dari graf —
   kelompok yang tak bisa diselesaikan rekonsiliasi `reg_key`.
3. **PADK 45/2025 tersimpan dua kali** di KB (435 hal. dan 2 hal.) — berbeda
   SHA sehingga lolos deduplikasi berkas; tertangkap lewat identitas graf.
   *Menunggu keputusan.*
4. **Salah ketik tahun di ojk.go.id**: "Penerapan Pedoman Tata Kelola
   Perusahaan Terbuka" tercatat 21/POJK.04/2014, seharusnya 2015 — terdeteksi
   sebagai konflik identitas, tidak digabung.
5. JDIH menulis "Dicabut" untuk pencabutan *pasal tertentu*; 227 dari 893
   relasi pencabutan ternyata sebagian (Pasal Terkait terisi).

### Kesalahan sendiri yang ditemukan dan diperbaiki

- Model MiniLM kalah dari BM25 (MRR 0,56 vs 0,90 kata kunci); hipotesis bias
  panjang dokumen diuji — ada, tetapi koreksinya tak membantu, **tidak dipasang**.
  Diganti model retrieval e5-large (butuh prefiks `query:`/`passage:`).
- Narasi benchmark menyimpulkan keunggulan dari selisih yang mengecil padahal
  tetap negatif; tabel kesimpulan sempat di-hardcode; label model tertulis
  "MiniLM" saat e5 dipakai; rekomendasi "hibrida" padahal semantik saja lebih
  baik. Semua kini dihitung dari hasil.
- Identitas: `8/5/PBI/2006` terbaca `PBI|5|2006`; singkatan PADK/PDK/SEDK tak
  dikenali; "Dicabut" dengan Pasal Terkait dianggap pencabutan penuh.
- Nama berkas: decode `_20`→spasi merusak tahun `2026` menjadi `26`.
- Isi Surat Edaran tak terindeks (struktur seksi tanpa teks) — 45 seksi hanya
  menjadi 10 potongan; kini 2.387.
- URL JDIH tanpa sektor/jenis dilaporkan "Gagal Terhubung"; kini 422.
- `sqlite-vec` dijadikan default padahal NumPy 28× lebih cepat di skala ini.
- ONNX Runtime 1.30 menolak model >2 GB lewat symlink cache HF; kini dipindah
  ke folder berkas nyata (tanpa menggandakan 2,2 GB).

### Operasional

- Katalog dicadangkan sebelum tabel baru: `data/hero_catalog.backup-before-indexes.db`.
- Tabel baru di katalog (aditif): `kb_document_view`, `kb_document_topic`,
  `kb_document_search`, `graph_*`, `scan_run`, `scan_item`, `ingest_job*`;
  kolom baru `documents.access_class`.
- Berkas turunan (di `.gitignore`): `data/hero_vectors.db` (132 MB),
  `data/models/` (2,2 GB), `data/vectors/`.
- e5-large: ±3 GB RAM saat mengindeks, ±7 menit untuk 7.830 potongan.
  VPS dengan RAM kecil: `vector.semantic_model: minilm` atau `--lsa-only`.

### Belum dikerjakan

- API belum memiliki autentikasi — batasi di reverse proxy (lihat `deploy/README.md`).
- Layar Analisa Regulasi & Harmonisasi (Fase 2–3) belum dibangun; endpoint
  dasarnya (`/api/search`, `/api/graph/*`) sudah ada.

---

## 2026-09-22 · Bersihkan artefak pengujian dari KB (persetujuan diberikan)

### Ringkasan

Persetujuan diterima untuk menghapus artefak uji, dengan syarat implisit yang
diikuti: **hanya menghapus yang benar-benar bukan peraturan.** Diperiksa dulu
satu per satu — 5 dari 6 baris yang ditandai `DOC-G01` ternyata peraturan
**asli** (17–53 pasal, sumber_ref menunjuk `jdih.ojk.go.id` sungguhan), hanya
label nama sesinya yang menyesatkan ("JDIH test", "api-test"). Menghapusnya
akan membuang data sungguhan. Tindakan yang diambil: **ganti label** untuk
lima itu, **hapus** dua yang benar-benar bukan peraturan.

### Perbaikan bug tersembunyi di `delete_document`

Fungsi ini sudah ada di kode tapi tak pernah dipakai maupun diuji. Sebelum
dipakai untuk penghapusan ini, ditemukan ia hanya menghapus baris `documents`
dan indeks pencarian — meninggalkan `articles`, `document_text` menggantung,
`inventory.doc_id` tetap menunjuk dokumen yang sudah tidak ada, dan **berkas
PDF tidak pernah dihapus**. Diperbaiki sebelum dipakai, dengan 3 test baru.

### Perubahan

| Berkas | Perubahan |
|---|---|
| `hero/kb/catalog.py` | `delete_document()` diperbaiki (hapus tuntas + lepas tautan inventory + kembalikan `stored_path`); `rename_source()` baru |
| `hero/cli.py` | `hero kb-remove <id> --reason "..."` dan `hero kb-rename-source <id> <nama>` |
| `tests/test_kb.py` | +3 test |

Pengujian: **229 lulus** (226 + 3).

### Tindakan pada data produksi

- **Diganti label** (isi tidak disentuh): `728c693a2741…`, `5fc7921a4292…`,
  `cb73530ce550…` ("JDIH test" → "JDIH OJK — Register Peraturan"),
  `4534cd5d488a…`, `f195c416b123…` ("api-test" → nama yang sama).
- **Dihapus** (baris database + berkas PDF):
  - `5ecbca91add3…` — berkas *HERO User Requirement Document*, bukan
    peraturan; ikut terunggah saat uji regresi jalur upload.
  - `a1ea5041bfb2…` — dokumen placeholder tanpa isi ("Dokumen testing ojk"),
    berlabel sumber produksi ("OJK — Regulasi Perbankan") padahal bukan.

`documents`: 93 → **91**. Aturan `DOC-G01` kini **lulus (0%)**, dari
sebelumnya gagal 10,2%.

---

## 2026-09-21 · Backfill OneDrive ke VPS: ingest dapat dilanjutkan + skrip VPS

### Ringkasan

Permintaan: jangan mengunduh seluruh folder OneDrive ke laptop; simpan sementara
di VPS. Solusi: VPS mengunduh langsung dari SharePoint (berkas tidak singgah di
laptop), dengan jalur ingest yang kini **resumable**. Tidak ada data baru masuk
ke KB lokal (tetap 93 dokumen). Belum ada akses ke VPS, jadi **belum dijalankan
di VPS**; disiapkan dan diuji sejauh mungkin secara lokal.

### Perubahan

| Berkas | Perubahan |
|---|---|
| `hero/kb/catalog.py` | `has_source_file(type, name, filename)` |
| `hero/ingest/onedrive.py` | parameter `skip`; diterapkan **sebelum** `max_files`; pesan "N more new PDFs remain" |
| `hero/pipeline.py` | meneruskan `skip` berbasis katalog |
| `hero/cli.py` | `hero onedrive --limit/--subfolder` kini menimpa config (sebelumnya diabaikan diam-diam) |
| `deploy/fetch-onedrive.sh` | BARU — backfill bertahap: cek tautan, flock, batas putaran, cek disk, penjaga kemajuan, log |
| `deploy/README.md` | bagian "Backfill folder OneDrive mitra ke VPS" (B1–B6); path Mac usang diperbaiki |
| `README.md` | perintah OneDrive diperbarui (tidak lagi "ditunda") |
| `skills/resumable-batch-ingest/` | skill baru (total 5) |
| `belajar.md` | Bagian 9.7 (menyimpan di VPS, cara kerja resume) |

Pengujian: **226 lulus** (223 + 3 baru: skip-sebelum-limit, has_source_file, CLI limit).

### Verifikasi

- **Resume dengan SharePoint sungguhan**, folder & DB terpisah: putaran 1 =
  3 berkas (2.296 tersisa); putaran 2 = 3 berkas *berbeda* (2.293 tersisa;
  2.299−6 ✓).
- **Logika `fetch-onedrive.sh`** diuji dengan stub, 5 skenario: selesai
  (100+100+42=242), macet→exit 3, tautan mati→exit 2, batas putaran, disk
  hampir penuh (0 putaran dijalankan).
- **Belum teruji:** skrip di Ubuntu sungguhan (`flock`, `df --output` khas
  GNU; diuji di macOS dengan shim).

### Angka

2.612 berkas di `downloads`; 2.299 PDF peraturan; **±1,3 GB**; terbesar 26 MB.
Disarankan ≥4 GB ruang kosong di VPS.

### Kesalahan sendiri yang ditemukan

1. `--limit` diabaikan untuk tautan dari config → uji "3 berkas" sempat
   mengunduh 100 (ke folder uji, dihentikan). Diperbaiki + test.
2. Variabel lokal `skip` menimpa parameter `skip` → `TypeError`; ditangkap test.
3. README deploy memuat path Mac yang usang; diperbaiki.

### Langkah berikutnya (butuh Anda)

Kirim kode ke VPS dan jalankan B3→B4→B5 di `deploy/README.md`. Saya tidak
memegang kredensial VPS dan tidak meminta Anda menempelkannya.

---

## 2026-09-20 (sesi 3) · OneDrive berhasil: tautan berbagi + SharePoint guest session

### Ringkasan

Tautan berbagi baru (`/:f:/g/...`) dapat dibaca tanpa login. Folder
`HERO/downloads` (2.612 berkas; 2.299 PDF peraturan setelah membuang FAQ/Abstrak/
Matriks) dibaca lewat sesi tamu SharePoint + REST API. **30 dokumen di-ingest
(0 ditolak, 1.625 halaman, 632 pasal).** **Kelima indikator Fase 1 kini
tercapai.**

### Perubahan

| Berkas | Perubahan |
|---|---|
| `hero/ingest/onedrive.py` | Jalur SharePoint: `open_guest_session`, `list_sharepoint_files`, `folder_item_count`, `download_sharepoint_folder`. Perbaikan bug API lama ("User migrated" dibaca sebagai satu file) |
| `hero/config.py` | `OneDriveShareSource` + `subfolder`, `max_files`, `exclude_patterns` |
| `hero/pipeline.py`, `hero/cli.py` | Opsi diteruskan; CLI `--subfolder`, `--limit` |
| `config/sources.yaml` | Tautan baru, `subfolder: downloads`, `enabled: true` |
| `tests/test_onedrive.py` | +6 test; total **223 lulus** |

### Bug yang ditemukan dan diperbaiki

1. **Daftar terpotong diam-diam.** `$top` membuat SharePoint mengembalikan
   persis N baris tanpa tautan halaman berikutnya: 1.000, lalu 500, padahal
   isinya 2.612. Diperbaiki (tanpa `$top`) + pemeriksaan silang ke `ItemCount`
   server yang mencatat `listing incomplete` bila tak cocok. Kesalahan ini
   berasal dari kode saya sendiri, ditemukan karena curiga pada angka bulat.
2. **Badan galat dibaca sebagai data.** API lama menjawab 308 `User migrated`;
   dibaca sebagai satu file bernama "unnamed".

### Temuan data (dari 30 dokumen baru)

- 5 dokumen berjenis pasal tanpa pasal; 4 di antaranya hanya 1–4 halaman.
  Isinya **belum dibuka** — dugaan lembar sampul, belum terbukti.
- Jenis tak dikenal `SE`, `PDK`, `KEPDK`: peraturan internal Dewan Komisioner
  (cuti pegawai, fasilitas perjalanan). Perlu keputusan ruang lingkup.
- 1 berkas bernama UUID tanpa metadata.

### Catatan keamanan

Tautan "Anyone" memberi akses ke seluruh folder `HERO` (termasuk `Data
Internal`, `Administration`). HERO hanya membuka `downloads`; folder lain tidak
diakses. Disarankan pemilik membagikan hanya `downloads`.

### Status indikator Fase 1

Semua 5 tercapai (OneDrive public: 30 dokumen). Total KB: 93 baris `documents`.

---

## 2026-09-20 (sesi 2) · Jalur OneDrive: diagnosis akses + penjelasan arsitektur

### Ringkasan

Permintaan: ambil data dari folder OneDrive mitra. Link yang diberikan
ternyata **alamat browser** (`onedrive.aspx?id=...`), bukan tautan berbagi:
diuji tanpa login, SharePoint mengalihkan ke `Authenticate.aspx` (atau 403).
Tidak ada percobaan melewati autentikasi — Project Charter membatasi akses
pada data publik, dan kredensial tenant organisasi tidak layak dipegang scraper.

**Indikator Fase 1 "folder OneDrive public" tetap belum tercapai; hambatannya
akses dari mitra, bukan kode.**

### Perubahan

| Berkas | Perubahan |
|---|---|
| `hero/ingest/onedrive.py` | `diagnose_link()` + `LinkDiagnosis`: satu probe tanpa mengikuti redirect, membedakan tautan berbagi vs alamat browser, menyebut penyebab & dua cara memperbaiki. `download_onedrive_share` kini berhenti di tembok login (sebelumnya menghasilkan pesan membingungkan "not a PDF") |
| `hero/cli.py` | `hero onedrive --check` — diagnosis tanpa mengunduh; exit code 1 bila butuh login |
| `config/sources.yaml` | Folder mitra didaftarkan dengan `enabled: false` + penjelasan cara mengaktifkan |
| `tests/test_onedrive.py` | +6 test (redirect login, 403, tautan berbagi org-only, tautan terbuka, berhenti tanpa request lanjutan, galat jaringan); 2 test lama disesuaikan karena probe kini request pertama |
| `skills/codebase-walkthrough/`, `skills/access-wall-diagnosis/` | Dua skill baru hasil sesi ini (total 4) |
| `belajar.md` | Bagian 8 (cara kode bekerja, mengapa banyak file, pola desain, arah ketergantungan yang diverifikasi dari import nyata) dan Bagian 9 (langkah mengaktifkan OneDrive) |

Pengujian: **217 lulus** (211 + 6).

### Langkah yang dibutuhkan dari pihak mitra (salah satu)

- **A.** Pemilik folder membuat tautan **"Anyone with the link can view"**
  (bentuk `.../:f:/g/personal/...`). Kebijakan tenant bisa melarang ini.
- **B.** Sinkronkan folder dengan aplikasi OneDrive memakai akun sendiri, lalu
  daftarkan path lokalnya di `folders:` — jalur yang identik dengan yang sudah
  terbukti untuk indikator folder lokal.

### Koreksi atas kesalahan sendiri

- Halaman dokumen jalur folder tertulis "109, 11, 29" di laporan sebelumnya;
  yang benar **35, 11, 29** (109 milik dokumen unggahan). Diperbaiki di
  `DATA_ANALYST_FASE1.md` dan log ini.
- Sempat menulis di `belajar.md` bahwa idempotensi dibuktikan lewat POJK yang
  "sama-sama 109 halaman" — tidak benar, itu berkas berbeda. Diganti dengan
  bukti sungguhan: `hero folders` dijalankan ulang → `0 masuk · 3 duplikat`.

---

## 2026-09-20 · Fase 1 — Lapisan Data Quality & audit metrik (peran: Data Analyst)

### Ringkasan

Membangun kemampuan pengukuran mutu data yang sebelumnya tidak ada,
menemukan bahwa metrik rekonsiliasi utama selama ini salah penyebut, dan
menutup dua indikator Fase 1 yang belum punya bukti produksi.

**Indikator Fase 1: 2 dari 5 → 4 dari 5 tercapai.**

### Yang dibangun

| Berkas | Isi |
|---|---|
| `hero/dq/rules.py` | 21 aturan validasi deklaratif, 6 dimensi DAMA-DMBOK, masing-masing dengan `scope_sql` + `rationale` |
| `hero/dq/profile.py` | Profiling kolom: kekosongan, kardinalitas, sebaran, kandidat kunci |
| `hero/dq/coverage.py` | Analisa penyebut: semesta yang dapat dicocokkan, deduplikasi, corong panen |
| `hero/dq/scorecard.py` | Skor 6 dimensi + pengukuran 5 indikator Fase 1 |
| `hero/dq/report.py` | Penyajian Markdown |
| `hero/cli.py` | Perintah baru `hero dq` dan `hero profile` |
| `tests/test_dq.py` | 26 pengujian baru |

### Temuan

1. **Metrik rekonsiliasi salah penyebut** *(dampak tinggi)* — "561 rekaman
   gagal dicocokkan" keliru. JDIH OJK hanya meregister 5 jenis peraturan
   terbitan OJK; 478 rekaman adalah terbitan lembaga lain (PBI, PMK, KMK,
   Bapepam-LK) yang mustahil dicocokkan. Cakupan sebenarnya **92,4%**
   (1.009/1.092), sisa pekerjaan nyata **83 rekaman**, bukan 561.
2. **Knowledge base tercampur artefak pengujian** *(dampak tinggi)* — 6 dari
   63 baris berasal dari sesi uji, 2 di antaranya bukan peraturan (termasuk
   berkas URD proyek ini sendiri). Indikator "≥20 dokumen" kini dihitung
   dengan 3 syarat; hasilnya 56 dokumen peraturan sungguhan.
3. **Duplikasi rekaman dalam satu sumber** *(sedang)* — 71 peraturan tercatat
   ganda di `ojk-regulasi` (kanal "semua sektor" vs kanal sektor), 144
   rekaman terdampak. 3.206 rekaman sebenarnya = **1.479 peraturan unik**.
4. **`reg_key` tidak mengenali 2 pola penomoran** *(risiko laten)* —
   Bapepam-LK (`KEP-208/BL/2012`, diawali huruf) dan PBI (`7/1/PBI/2005`,
   angka pertama adalah seri tahun → 42 peraturan berbagi satu kunci). Belum
   menimbulkan kesalahan karena keduanya di luar register JDIH; akan menjadi
   masalah masif begitu sumber Bank Indonesia diaktifkan.
5. **Dua jalur masuk belum pernah dipakai produksi** — *sudah ditutup*.
6. **2 dokumen berjenis pasal tanpa pasal terparsing** *(sedang)* — 1 POJK +
   1 PADK tidak dapat dipakai fitur harmonisasi. 4 SEOJK tanpa pasal bukan
   cacat (memakai seksi Romawi).

### Perubahan data

Mengunduh 4 POJK 2026 asli dari JDIH OJK, lalu memasukkannya lewat jalur
produksi yang sesungguhnya:

- `hero folders --path data/inbox` → **3 dokumen** (35, 11, 29 halaman)
- `hero upload data/unggahan` → **1 dokumen** (109 halaman)

Seluruhnya terekstrak penuh beserta struktur pasalnya. `documents` 59 → 63,
`articles` 1.400 → 1.597.

### Koreksi terhadap kesalahan sendiri

Dua kesalahan ditemukan dan diperbaiki dalam sesi ini, dicatat karena
polanya mudah berulang:

- **`NULL NOT IN (...)` bernilai NULL di SQL, bukan benar.** 52 rekaman
  berjenis kosong lolos dari kedua kategori sekaligus sehingga penjumlahan
  tidak kembali ke 561. Ketemu karena penjumlahannya diperiksa. Kini hasil
  pemeriksaan itu ikut dibawa sebagai field `balances`.
- **Menebak nilai enum.** Diasumsikan `source_type='folder'`, nyatanya
  pipeline menulis `'local_folder'` — indikator terbaca nol padahal 3
  dokumen sudah masuk, tanpa galat apa pun. Ditambahkan test yang membaca
  `pipeline.py` untuk mengunci keempat nama jalur.

### Status indikator Fase 1

| # | Indikator | Aktual | Target | Status |
|---|---|---:|---:|:---:|
| 1 | Dokumen dari ≥3 situs sumber | 10 | 3 | ✅ |
| 2 | Unggah manual berfungsi | 1 | 1 | ✅ |
| 3 | Membaca ≥1 folder lokal | 3 | 1 | ✅ |
| 4 | Membaca ≥1 folder OneDrive public | 0 | 1 | ❌ |
| 5 | ≥20 dokumen peraturan di KB | 56 | 20 | ✅ |

Indikator 4 terhalang ketersediaan akses OneDrive public dari mitra — jalur
teknisnya sudah ada, yang kurang aksesnya.

### Pengujian

**211 lulus** (sebelumnya 185, +26 baru). Tidak ada yang gagal.

### Kondisi mutu data

Skor keseluruhan **97,6%** · kesimpulan `perlu-perbaikan`.
Dua aturan gagal, sengaja dibiarkan terlihat alih-alih diturunkan ambangnya:

- `DOC-G01` — 6 artefak pengujian di KB *(menunggu persetujuan penghapusan)*
- `INV-U01` — 5,8% rekaman duplikat terhadap ambang 3%

### Deliverable

| Berkas | Isi |
|---|---|
| `docs/DATA_ANALYST_FASE1.md` | Laporan analisa lengkap, 6 temuan, 6 rekomendasi |
| `docs/DATA_DICTIONARY.md` | Kamus data resmi 3 tabel utama + tabel pendukung |
| `docs/DATA_QUALITY_REPORT.md` | Kartu skor, dihasilkan otomatis `hero dq --markdown` |
| `belajar.md` | Panduan memahami proyek + peta jalan belajar + referensi |
| `skills/data-quality-scorecard/` | Skill: membangun kartu skor mutu data |
| `skills/denominator-audit/` | Skill: mengaudit penyebut metrik |
| `data/export/dq_scorecard.json` | Kartu skor bentuk JSON untuk dasbor/CI |

### Rekomendasi (urut manfaat/usaha)

| # | Tindakan | Catatan |
|---|---|---|
| R1 | Hapus 6 artefak uji dari KB; arahkan sesi uji ke DB terpisah | **butuh persetujuan** |
| R2 | Tutup 83 rekaman rekonsiliasi yang addressable | 36 POJK, 27 SEOJK, 13 UU, 7 PADK |
| R3 | Perbaiki `reg_key` **sebelum** sumber BI diaktifkan | risiko laten |
| R4 | Tetapkan rekaman kanonik untuk duplikat lintas kanal | simpan alias, jangan hapus |
| R5 | Jalankan `hero dq --strict` di CI | jadikan gerbang, bukan laporan |
| R6 | Naikkan capaian panen (baru 1,4%) | utamakan status `berlaku` |

---

## Sebelum 2026-09-20

Riwayat sebelum sesi ini terangkum di [SUMMARY.md](../SUMMARY.md): pembangunan
fitur URD 3.2 (scraping & ingest 3 jalur), lapisan ekstraksi PDF/OCR, parser
metadata & struktur pasal, knowledge base SQLite + FTS5, discovery 3.206
rekaman dari 3 sumber, serta 185 pengujian.
