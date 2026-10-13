# Integrasi lapisan data ↔ backend tim

> Bagaimana algoritma scraping, OCR, analisa, harmonisasi, dan vektor di
> `pipeline/` tersambung ke backend FastAPI + Postgres milik tim, sehingga
> frontend bisa mengambil data yang diharapkan tiap layarnya.
>
> Status: **siap diuji bersama**. Seluruh kode ada di `pipeline/hero/bridge/`,
> tidak ada satu baris pun yang perlu diubah di `backend/` untuk jalur 1 dan 2.

---

## 1. Siapa memegang apa

```
┌──────────────┐   /api/v1/*            ┌──────────────────────────────┐
│  frontend    │ ─────────────────────▶ │  BACKEND (tim)               │
│  React/Vite  │                        │  FastAPI + Postgres/pgvector │
└──────────────┘ ◀───────────────────── │  dokumen · kategori · sesi   │
       │           /api/v1/ml/*         │  pindai · job · audit · PDF  │
       │                                └──────────────┬───────────────┘
       │                                               │ kontrak internal
       │                                               │ /api/v1/internal/*
       │                                ┌──────────────▼───────────────┐
       └───────────────────────────────▶│  LAPISAN DATA (pipeline/)    │
            layar Analisa & Harmonisasi │  adapter sumber · OCR ·      │
            dijawab layanan ML          │  pasal · analisa ·           │
                                        │  harmonisasi · vektor · graf │
                                        └──────────────────────────────┘
```

**Aturan pembagian yang dipegang:**

| | Backend | Lapisan data |
|---|---|---|
| Sumber kebenaran dokumen, status, PDF | ✅ | — (mencermin, bisa dihapus) |
| Autentikasi, audit, kategori, job | ✅ | — |
| Adapter per sumber (JDIH, postback OJK, OneDrive) | punya versi sendiri (dipilih dari URL) | ✅ alternatif lewat mode *push* |
| OCR, identitas halaman 1, parser pasal/ayat | — | ✅ |
| Analisa, harmonisasi, vektor, graf | — | ✅ |
| Menulis ke basis data backend | ✅ | hanya kolom `articles.embedding` (lihat §6) |

Jembatan **tidak pernah** mengimpor kode backend dan **tidak** menulis ke
tabelnya selain satu kolom yang memang disiapkan untuk lapisan data.

---

## 2. Tiga jalur sambungan

### Jalur 1 — Pemindaian situs (mode *push*)

Backend punya crawler HTML sendiri (`simple_http`). Mode `push` dipakai untuk
sumber yang tidak bisa dipindai crawler HTML biasa:

| Sumber | Kenapa perlu adapter lapisan data |
|---|---|
| `jdih.ojk.go.id` | halaman daftarnya tidak memuat tautan — isinya grid JSON per pasangan sektor × jenis (120 pasangan, 986 rekaman) |
| `ojk.go.id/…/regulasi` | *postback* ASP.NET (`__VIEWSTATE`), 157 halaman × 10 baris; PDF hanya ada di halaman detail |
| `ojk.go.id/…/rancangan` | dokumennya ZIP; "Batang Tubuh" harus dipilih dari dalam arsip |

```
backend                                   worker (hero bridge pindai)
   │ POST /internal/scans/claim  ─────────▶│
   │                             ◀───────── {scan_id, start_url, crawl_depth, …}
   │                                        │ discover_site()   daftar + detail, TANPA unduh
   │                                        │ probe_inventory() ukuran via HEAD (MoM #4)
   │ POST /internal/scans/{id}/candidates ◀─│ batch 200; batch terakhir done=true
   │ (done=true memicu perbandingan KB)     │
```

`CRAWLER_BACKEND` di backend bersifat **global**: nilai `push` membuat *semua*
sesi pindai menunggu worker eksternal, termasuk OneDrive dan folder, yang tidak
ditangani worker ini. Karena itu rekomendasinya:

- **Produksi: `CRAWLER_BACKEND=simple_http`.** Backend memilih adapter sendiri dari
  URL (`detect_adapter_from_url`: JDIH, ojk.go.id, OneDrive) dan pindai dari UI tetap
  jalan. Worker `hero bridge pindai` tidak perlu dinyalakan.
- `push` hanya bila worker pindai ini benar-benar dinyalakan dan sumbernya memang
  salah satu dari adapter HERO. `hero bridge status` menampilkan mode yang aktif.

### Jalur 2 — Ekstraksi dokumen (OCR, metadata, pasal, vektor)

```
backend                                   worker (hero bridge ekstraksi)
   │ POST /internal/extraction/claim ─────▶│  (SELECT … FOR UPDATE SKIP LOCKED)
   │ GET  /internal/documents/{id}/pdf ───▶│  unduh PDF asli
   │                                        │ probe_pdf        %PDF- + perbaikan pikepdf
   │                                        │ extract_pdf      teks/OCR per halaman (ind+eng)
   │                                        │ extract_metadata jenis/nomor/tanggal/dasar hukum
   │                                        │ read_identity    dari mana tiap unsur dibaca
   │                                        │ parse_structure  BAB/Pasal/ayat, lampiran dipisah
   │                                        │ ArticleEmbedder  1 vektor per pasal
   │ PATCH /internal/documents/{id}/extraction ◀─ metadata + full_text + confidence
   │ POST  /internal/articles             ◀─ pasal (+ embedding), batch 150
```

Backend lalu memutuskan sendiri `terindeks` vs `perlu_koreksi` (ambang
`METADATA_CONFIDENCE_THRESHOLD=0.7`) dan menempatkan berkas ke `kb/{jenis}/{tahun}/`.

### Jalur 3 — Layar Analisa & Harmonisasi (Fase 2–3)

Backend belum punya endpoint untuk kedua layar ini (lihat `frontend/src/pages/Harmonisasi.tsx`
— masih "pratinjau desain"). Mesinnya ada di lapisan data, jadi dijalankan
sebagai layanan terpisah dan dipasang di jalur `/api/v1/ml/*`:

```
hero bridge sinkron      cermin korpus backend → katalog SQLite (dokumen + pasal)
hero bridge serve        layanan /api/v1/ml/* (analisa, harmonisasi, pencarian)
```

Kontrak endpoint-nya: [`API_CONTRACT_ML.md`](API_CONTRACT_ML.md).

**Kenapa korpus dicermin, bukan dibaca langsung dari Postgres?** Harmonisasi
membandingkan *setiap pasal draft terhadap setiap pasal korpus*, lalu
menanyakan status hukum tiap pembanding ke graf relasi dan mencari calon
pembanding di register yang belum terunduh. Mesin itu sudah ada, teruji, dan
terkalibrasi (recall 90,1% pada 14 pasangan peraturan perubahan — lihat
[`HARMONISASI_EVALUASI.md`](HARMONISASI_EVALUASI.md)), semuanya di atas katalog
SQLite. Mencerminkan korpus satu kali jauh lebih murah dan lebih aman daripada
menulis ulang mesin harmonisasi, vektor, graf, dan mutu data untuk dua jenis
basis data. Cermin adalah **data turunan**: boleh dihapus, dibangun ulang
dengan satu perintah; sumber kebenaran tetap Postgres.

---

## 3. Memasang & menjalankan

### 3.1 Sekali saja

```bash
cd <workspace>                      # mis. ~/hero-work di VPS, ../Capstone di laptop
.venv/bin/pip install -e "<repo>/pipeline[api,vector,pg]"

# Rahasia di .env, bukan di YAML
cat >> .env <<'ENV'
HERO_BACKEND_URL=http://127.0.0.1:8000
HERO_BACKEND_INTERNAL_KEY=<nilai INTERNAL_API_KEY backend>
HERO_PG_DSN=postgresql://hero_user:...@127.0.0.1:5432/hero_db
ENV

# Blok konfigurasi (sudah ada contohnya di config/sources.yaml)
#   bridge:
#     base_url: http://127.0.0.1:8000
#     embedder: lsa          # lsa (offline) | semantic (model lokal) | none
#     backend_dim: 1536

.venv/bin/hero vector build --lsa-only    # wajib sekali bila embedder: lsa
.venv/bin/hero bridge status              # harus hijau sebelum lanjut
```

`hero bridge status` memeriksa dan melaporkan: `/health` backend, apakah kunci
API internal diterima, apakah `CRAWLER_BACKEND=push`, isi buku besar worker,
jumlah dokumen tercermin, serta versi pgvector + dimensi kolom yang
sebenarnya ada di server.

### 3.2 Perintah harian

| Perintah | Yang dilakukan |
|---|---|
| `hero bridge pindai [--loop]` | melayani sesi pemindaian backend |
| `hero bridge ekstraksi [--loop] [--limit 10]` | mengosongkan antrian ekstraksi |
| `hero bridge sinkron [--vektor] [--analisa]` | mencermin korpus; opsional bangun indeks vektor & analisa Fase 2 |
| `hero bridge vektor-isi --apply` | mengisi `articles.embedding` untuk pasal lama |
| `hero bridge serve --port 8100` | layanan `/api/v1/ml/*` |
| `hero bridge sekali` | satu putaran lengkap — untuk systemd timer |
| `hero bench-vektor` | benchmark penyimpanan vektor (lihat [`VEKTOR_BENCHMARK.md`](VEKTOR_BENCHMARK.md)) |

### 3.3 Reverse proxy (satu asal untuk frontend)

Agar frontend tidak perlu URL kedua dan tidak kena CORS, pasang layanan ML di
bawah asal yang sama. Caddy (backend sudah memakai Caddy — `backend/deploy/Caddyfile`):

```caddy
hero.example.id {
    handle /api/v1/ml/* {
        uri strip_prefix /api/v1/ml
        reverse_proxy 127.0.0.1:8100
    }
    handle { reverse_proxy 127.0.0.1:8000 }
}
```

Nginx:

```nginx
location /api/v1/ml/ { proxy_pass http://127.0.0.1:8100/; }
location /           { proxy_pass http://127.0.0.1:8000; }
```

Untuk pengembangan lokal tanpa proxy, cukup jalankan `hero bridge serve
--cors http://localhost:5173` dan panggil `http://127.0.0.1:8100/...` dari
frontend.

---

## 4. Peta field — kandidat hasil pindai

Sumber: register HERO (`inventory`) → `PdfCandidate` backend
(`crawler-adapter-contract.md` §2.1). Pemetaan ada di `hero/bridge/mapping.py`.

| Field backend | Dari | Catatan |
|---|---|---|
| `url` | `inventory.document_url` | rekaman tanpa tautan berkas **bukan** kandidat |
| `filename` | `document_name`, fallback nama di path URL | |
| `size_bytes` / `size_source` | `file_size` / `file_method` dari `hero scan ukur` | `head` \| `range` \| `listing` \| `unknown` — tanpa mengunduh |
| `found_on_page` / `detail_url` | `detail_url` | |
| `document_title` | `inventory.title` | |
| `regulation_number` / `regulation_type` | `number` / `doc_type` | |
| `bidang` / `sub_bidang` | `sektor` / field "Sub Klasifikasi" | |
| `regulation_year` | `year` | |
| `release_date` | "Tanggal Penetapan (ISO)" → "Tanggal Pengundangan (ISO)" → "Tanggal (ISO)" | |
| `effective_date` | **hanya** "Tanggal Berlaku (ISO)" | tanggal pengundangan ≠ tanggal berlaku, jadi tidak dipaksakan |
| `status_keberlakuan` | `inventory.status` | `rancangan` → `tidak_diketahui` (tidak ada padanannya; perannya dinyatakan lewat `document_role`) |
| `doc_kind` | jenis lampiran | `abstrak`/`faq`/`matriks` **tidak** dikirim kecuali diminta |
| `match_warning` | `file_error` | |

## 5. Peta field — hasil ekstraksi

| Field backend | Dari | |
|---|---|---|
| `title` | `md.subject` (klausul "TENTANG …"), fallback `md.title` | itulah yang dipakai layar sebagai judul |
| `regulation_number` / `regulation_type` / `release_date` | parser metadata | |
| `extraction_method` | `ocr` bila ada halaman di-OCR, selain itu `teks_langsung` | |
| `extraction_engine` | `hero-pipeline/deterministik` | muncul di UI sebagai asal data |
| `full_text` | teks gabungan, dipotong 300.000 karakter | sama dengan batas `left(...)` kolom `search_vector` backend |
| `confidence.*` | tabel di `mapping.CONF_BY_SOURCE` | lihat di bawah |
| `articles[]` | `DocumentStructure.articles` (batang tubuh saja) | pasal di lampiran adalah rujukan, bukan norma |

**Keyakinan per field tidak dikarang.** Angkanya mencerminkan *dari mana*
nilai itu dibaca, dan dikalikan keyakinan OCR bila halamannya hasil pindai:

| Sumber bacaan | Keyakinan |
|---|---|
| blok pembuka halaman 1 (lapisan teks) | 0,95 |
| blok penutup ("Ditetapkan di … pada tanggal …") | 0,85 |
| metadata dokumen utuh / register sumber | 0,75 |
| turunan (jenis dari pola nomor, judul dari metadata PDF) | 0,55 |
| nama berkas saja | 0,35 |
| tidak terbaca | field dikirim `null` → backend menandai `perlu_koreksi` |

Dengan ambang backend 0,7, nilai yang hanya berasal dari nama berkas otomatis
masuk antrian koreksi manual — persis yang diinginkan.

---

## 6. Vektor: dua penyimpanan, satu model

| | Di mana | Isi | Dipakai untuk |
|---|---|---|---|
| **Primer (backend)** | `articles.embedding` (pgvector) | 1 vektor per **pasal** | pencarian dari frontend; satu sumber data, satu izin akses |
| **Kerja (lapisan data)** | `data/hero_vectors.db` (sqlite-vec + NumPy) | 1 vektor per **jendela 80 kata** + cache | harmonisasi, kalibrasi ambang, benchmark, eksperimen model |

Keduanya memakai model yang sama, jadi hasilnya sebanding. Perbedaan unit
disengaja: backend menyimpan satu embedding per baris `articles`, sedangkan
model terkecil hanya membaca 128 token — pasal panjang yang di-embed utuh
akan terwakili paragraf pertamanya saja. Vektor yang dikirim ke backend adalah
**rata-rata vektor jendela pasal itu, dinormalisasi ulang**, sehingga seluruh
isi pasal terwakili dalam satu vektor.

**Dimensi.** Kolom backend `Vector(1536)` (dimensi OpenAI ada-002); model lokal
HERO 256 (LSA) / 384 (MiniLM) / 1024 (e5-large). Vektor di-**zero-pad** ke 1536.
Untuk vektor ber-norma 1 ini **tidak kehilangan apa pun**: nol tidak mengubah
dot product maupun norma, jadi cosine similarity-nya identik — dibuktikan di
`tests/test_bridge.py::test_padding_tidak_mengubah_cosine` dan diukur ulang
sebagai `recall_vs_native` di `hero bench-vektor`. Yang terbuang hanya ruang;
angkanya ada di [`VEKTOR_BENCHMARK.md`](VEKTOR_BENCHMARK.md) §"Harga kolom 1536
dimensi", beserta dua pilihan yang keduanya sah (biarkan 1536, atau samakan
kolom dengan model lewat migrasi aditif).

**Satu-satunya jalur tulis ke Postgres** adalah `hero bridge vektor-isi`
(`UPDATE articles SET embedding`), untuk pasal yang masuk sebelum jembatan ada
atau saat ganti model. Default-nya uji coba; `--apply` baru menulis.
`POST /internal/articles` bisa dipakai untuk ini sejak kontrak Langkah 13 (upsert mempertahankan embedding lama bila yang dikirim `null`), tetapi `vektor-isi` tetap lebih murah: ia menulis kolom vektor saja, tanpa mengirim ulang teks pasal.

**Ganti model = isi ulang semuanya.** Vektor dari ruang yang berbeda tidak
bisa dibandingkan satu sama lain. Pakai `hero bridge vektor-isi --ulang --apply`,
jangan mencampur dua model dalam satu kolom.

---

## 7. Kontrak pasal — status 12 Oktober 2026

**§7.1–7.3 sudah ditutup backend** lewat PR [#115](https://github.com/hero-ojk-its/hero/pull/115) (migrasi
`e5f6a7b8c9d0`, "Langkah 13"). Bagian ini sekarang mencatat apa yang
dipakai lapisan data dan apa yang masih terbuka, bukan lagi daftar
permintaan.

| | Yang diminta | Keadaan |
|---|---|---|
| §7.1 | kolom halaman pada `articles` | ✅ `page` (1-indexed, nullable) |
| §7.2 | `POST /internal/articles` idempoten | ✅ upsert `(document_id, order_index)` + `replace_document_ids` |
| §7.3 | hierarki ayat | ✅ `parent_order_index` → `parent_id` |
| §7.4 | dimensi kolom embedding | ⏳ masih 1536; jembatan jalan di kedua skenario (§6) |

### 7a. Yang dipakai lapisan data

- **`page`** dikirim per pasal **dan** per ayat. Halaman ayat = halaman pasalnya:
  parser mencatat posisi awal pasal, bukan tiap ayat, dan halaman yang ditebak
  akan mengirim pemeriksa ke halaman yang salah.
- **`replace_document_ids`** dikirim **hanya pada batch pertama** satu dokumen.
  Pada batch kedua dan seterusnya ia akan menghapus hasil batch sebelumnya.
  Ini juga yang membersihkan sisa pasal dari worker yang mati di tengah jalan
  dan dari ekstraksi lama yang menghasilkan lebih banyak pasal.
- **`parent_order_index`** diisi untuk setiap ayat (`bridge.push_ayat: true`,
  masih mati secara bawaan — lihat §7c). Induk boleh berada di request
  sebelumnya; diuji sampai **satu baris per request** tanpa 422.
- **`inserted_count` + `updated_count`** dijumlahkan. Menghitung yang pertama
  saja membuat kiriman ulang terlapor "0 pasal" padahal dokumennya lengkap.
- **Cermin korpus** (`hero bridge sinkron`) membaca `articles.page` dari
  backend bila kolomnya ada, dan jatuh ke buku besar lokal bila tidak.

### 7b. Kemampuan dideteksi, tidak diasumsikan

Backend sebelum migrasi ini **mengabaikan field yang tidak dikenalnya tanpa
galat** (Pydantic `extra="ignore"`). Jadi mengirim `replace_document_ids` ke
sana tidak menghapus apa pun — dan kiriman berikutnya menggandakan pasal,
persis kerusakan yang §7.2 ingin dicegah. Karena itu jembatan memastikan dulu:

1. **Pra-terbang** — skema `/openapi.json`. Tepat, tetapi backend produksi
   boleh mematikannya (`EXPOSE_API_DOCS=false`).
2. **Dari jawabannya** — respons kontrak baru membawa `updated_count` dan
   `deleted_count`; yang lama hanya `inserted_count`.

Selama belum pasti, jalur konservatif yang dipakai: tanpa halaman, tanpa ayat,
tanpa ganti-bersih, dan buku besar lokal yang menahan kiriman ulang. Lebih baik
kehilangan fitur daripada menggandakan pasal diam-diam.

Status terbaca di `hero bridge status` baris **"kontrak pasal"**. Bila backend
sudah dimigrasi tetapi dokumentasinya ditutup, setel di `config/sources.yaml`:

```yaml
bridge:
  article_contract: v2      # auto (bawaan) | v2 | v1
```

### 7c. Yang masih perlu keputusan bersama

- **`bridge.push_ayat` masih `false`.** Mesinnya sudah siap dan teruji, tetapi
  menyalakannya mengubah **isi tabel `articles` backend**: satu POJK uji
  menjadi 79 pasal + 169 ayat, dan teks ayat sudah termuat di dalam
  `content_text` pasalnya, jadi ada duplikasi teks di indeks pencarian.
  Keputusan ini milik backend + frontend (tampilan & unit pencarian), bukan
  lapisan data sendiri.
- **`GET /api/v1/documents/{id}` menyaring `parent_id IS NULL`**, jadi ayat
  tersimpan tetapi tidak muncul di respons itu. Bila layar Analisa ingin ayat
  bersarang, backend perlu menambahkan sarangnya atau endpoint terpisah.

### 7d. Hasil uji ujung-ke-ujung (12 Okt 2026)

Lapisan data vs backend sungguhan (`docker compose`, revisi `e5f6a7b8c9d0`,
tiga POJK publik dari JDIH):

| Yang diuji | Hasil |
|---|---|
| Halaman terkirim | 40/40 dan 79/79 pasal punya `page` |
| Dua worker, buku besar terpisah, dokumen sama | tetap 40 pasal (bukan 80) |
| Pasal hantu `order_index=999` disuntik lalu ekstraksi ulang | terhapus |
| Hierarki ayat | 169/169 ayat berinduk pasal yang benar |
| `batch_articles: 1` (induk selalu di request sebelumnya) | 43/43 baris masuk, tanpa 422 |
| Cermin korpus setelah migrasi | halaman terisi 97, kosong 0 (sebelumnya 0 / 97) |

### 7e. Dimensi kolom embedding

Lihat §6. Keputusan: biarkan 1536, atau samakan dengan model. Angkanya ada di
benchmark; jembatan jalan di kedua skenario tanpa perubahan kode
(`hero bridge status` membaca dimensi kolom yang sebenarnya dan menyesuaikan).

---

## 8. Yang didapat frontend

| Layar | Endpoint | Pemilik |
|---|---|---|
| Dashboard, Knowledge Base, Detail Dokumen, Ingest | `/api/v1/*` | backend (sudah ada) |
| Hasil pemindaian situs | `/api/v1/scans/*` | backend — **isinya** dari worker pindai |
| Analisa Regulasi | `GET /api/v1/ml/analisa/{document_id}` | layanan ML |
| "pasal relevan dengan kebutuhan saya" | `GET /api/v1/ml/analisa/{id}/klausul?kebutuhan=…` | layanan ML |
| Harmonisasi | `POST /api/v1/ml/harmonisasi/{document_id}` | layanan ML |
| Pencarian makna | `GET /api/v1/ml/cari?q=…&metode=hybrid` | layanan ML |
| Pembanding cepat per potongan teks | `GET /api/v1/ml/pasal-mirip?teks=…` | layanan ML (pgvector) |

Tipe TypeScript-nya bisa dibangkitkan seperti kontrak backend:

```jsonc
// frontend/package.json
"gen:api:ml": "openapi-typescript http://127.0.0.1:8100/openapi.json -o src/lib/openapi-ml.d.ts"
```

Semua respons layanan ML memakai **`document_id` backend**, bukan `doc_id`
internal katalog, dan setiap pembanding membawa `pdf:
/api/v1/documents/{id}/pdf#page=N`.

---

## 9. Daftar periksa sebelum bilang "tersambung"

- [ ] `hero bridge status` → `/health` ok, kunci internal diterima, mode pindai sesuai rencana
- [ ] `hero bridge ekstraksi --limit 1` pada satu dokumen uji → backend menjadi `terindeks`/`perlu_koreksi`, pasal muncul di `GET /api/v1/documents/{id}`
- [ ] Pasal **tidak** ganda setelah menjalankan perintah yang sama dua kali
- [ ] `hero bridge pindai` pada satu URL JDIH → sesi pindai backend berisi kandidat beserta ukuran berkasnya
- [ ] `hero bridge sinkron` → jumlah dokumen tercermin = jumlah dokumen `terindeks` di backend
- [ ] `GET /api/v1/ml/health` → `status: siap`
- [ ] `POST /api/v1/ml/harmonisasi/{id draft}` → temuan membawa `pembanding.pdf` dan `alasan`
- [ ] `python -m pytest tests -q` di `pipeline/` lulus
