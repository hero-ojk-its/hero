# Data & tools di server — pilihan, biaya, dan cara memindahkannya

> Dokumen **studi keputusan**, bukan perintah kerja. Isinya pilihan beserta
> ongkos dan risikonya, supaya keputusannya bisa diambil sadar. Tidak ada
> satu pun langkah di sini yang sudah dijalankan.
>
> Angka ukuran dan kecepatan di dokumen ini **terukur** pada korpus 118
> dokumen / 3.206 rekaman register (5 Okt 2026), bukan diperkirakan. Yang
> diperkirakan hanya proyeksinya ke korpus penuh, dan selalu disebut
> perhitungannya.

---

## 1. Keadaan sekarang

| Komponen | Di mana sekarang | Konsekuensinya |
|---|---|---|
| Backend + Postgres | kontainer Docker (`backend/docker-compose.yml`) | sudah siap dipindah ke VPS apa adanya |
| PDF asli | `storage/kb/{jenis}/{tahun}/` di host backend | satu-satunya salinan; hilang = bukti rujukan hilang |
| Metadata, pasal, vektor | Postgres backend | ikut `pg_dump` |
| **Lapisan data (`pipeline/`)** | **laptop pengembang** (`../Capstone`) | scraping, OCR, analisa, harmonisasi **hanya jalan saat laptop menyala** |
| Katalog + vektor lapisan data | `data/*.db` di laptop | data turunan — bisa dibangun ulang |
| Model embedding | `data/models/` di laptop, **3,0 GB** terukur | unduh sekali, bisa dipakai offline |

Masalahnya satu: **lapisan data belum ada di server.** Selama worker ekstraksi
dan layar Analisa/Harmonisasi bergantung pada laptop, dokumen yang diunggah
mitra akan menggantung di status `diterima` sampai ada orang yang menyalakan
laptopnya. Jembatan (`hero bridge …`) sudah dibuat untuk bisa jalan di server;
yang belum diputuskan adalah **di mana** dan **bagaimana**.

---

## 2. Apa saja datanya, dan seberapa besar

Terukur pada 118 dokumen ter-ingest, 3.966 pasal, 12.914 potongan vektor:

| Komponen | Terukur | Per dokumen | Proyeksi 3.206 dokumen¹ |
|---|---:|---:|---:|
| PDF asli | 90,8 MB | 769 KB | **≈ 2,5 GB** |
| Katalog: teks dokumen + FTS | 34,2 MB | 290 KB | ≈ 930 MB |
| Katalog: register (seluruh 3.206 rekaman) | 11,8 MB | — | 11,8 MB (sudah penuh) |
| Katalog: pasal | 5,3 MB | 45 KB | ≈ 145 MB |
| Katalog: read model + graf | 2,7 MB | 23 KB | ≈ 75 MB |
| Vektor di SQLite (2 model + cache) | 218,0 MB | 1,85 MB | ≈ 5,9 GB |
| — hanya satu model, tanpa cache | 114,1 MB | 967 KB | ≈ 3,1 GB |
| Vektor pgvector, 1 per pasal @1024 dim² | 5,6 KB/baris | 188 KB | ≈ 605 MB |
| Vektor pgvector, 1 per pasal @1536 dim² | 8,4 KB/baris | 282 KB | ≈ 905 MB |
| Indeks HNSW pgvector² | 8,0 KB/baris | 269 KB | ≈ 865 MB |
| Model embedding (sekali, bukan per dokumen) | 3,0 GB | — | 3,0 GB |

¹ 3.206 = seluruh rekaman yang diterbitkan tiga sumber publik (JDIH 986 +
ojk.go.id regulasi 1.570 + rancangan 650). Proyeksi **linear** terhadap jumlah
dokumen; teks dan pasal memang kira-kira linear, PDF bisa menyimpang jauh
karena dokumen hasil pindai jauh lebih besar dari born-digital.
² Diukur per baris pada 12.914 baris, lalu dikalikan 107.700 pasal (33,6 pasal
per dokumen × 3.206). Satu pasal = satu baris `articles`.

**Kesimpulan ukuran:** korpus penuh butuh **± 5–6 GB** (PDF + Postgres +
indeks), ditambah **3 GB model** bila memakai pencarian semantik, ditambah
**3–6 GB** bila indeks vektor kerja lapisan data juga disimpan di server.
Dengan margin: **VPS 40 GB disk sudah lapang; 20 GB pas-pasan.**

**Yang tidak perlu dicadangkan:** seluruh baris "vektor" dan "read model" dan
"graf" adalah **data turunan** — dibangun ulang dari PDF + katalog dengan satu
perintah. Yang wajib dicadangkan hanya PDF asli dan Postgres.

---

## 3. Pilihan penyimpanan

### Pilihan A — Tetap seperti sekarang: filesystem VPS + rclone ke Nextcloud

PDF di `storage/` milik backend; lapisan data punya `data/` sendiri di
`/opt/hero`; keduanya di disk VPS. Hasil ekspor & knowledge base disinkron ke
Nextcloud lewat WebDAV supaya mitra bisa melihatnya lewat browser.
Sudah terimplementasi: [`../deploy/README.md`](../deploy/README.md).

* **Usaha:** paling kecil — jalurnya sudah ada dan sudah diuji.
* **Biaya:** nol di luar disk VPS.
* **Risiko:** PDF hanya ada di satu disk. Snapshot VPS + `rclone` ke Nextcloud
  adalah cadangannya; keduanya harus benar-benar dinyalakan, bukan diasumsikan.
* **Cocok bila:** target 24 Desember 2026 lebih penting daripada arsitektur
  jangka panjang. **Ini keadaan paling murah untuk menyelesaikan capstone.**

### Pilihan B — Satu sumber kebenaran: semua di Postgres + `storage/` backend

Lapisan data tidak lagi menyimpan korpusnya sendiri; ia mencermin dari
Postgres saat perlu (sudah bisa: `hero bridge sinkron`), dan cermin itu
dianggap cache yang boleh dihapus kapan saja.

* **Usaha:** kecil — hanya kebijakan + cron pembersih cermin.
* **Biaya:** nol tambahan.
* **Keuntungan:** tidak ada dua salinan metadata yang bisa berbeda. Cadangan =
  `pg_dump` + folder `storage/`. Satu izin akses, satu jejak audit.
* **Risiko:** Postgres jadi titik tunggal kegagalan untuk *semua* fitur;
  harmonisasi pada korpus penuh berarti mencermin ± 1,1 GB teks+pasal setiap
  kali cermin dihapus (sekali ± 2–4 menit, terukur 0,1 s untuk 7 dokumen).
* **Cocok bila:** tim ingin satu arsitektur yang mudah dijelaskan ke mitra.
  **Rekomendasi saya untuk setelah demo 8 Oktober** (lihat §9).

### Pilihan C — Object storage (MinIO / S3) untuk PDF

PDF pindah ke bucket; database hanya menyimpan kuncinya. Backend sudah
memusatkan akses berkas di `app/services/storage_service.py`, jadi perubahannya
terkurung di satu kelas.

* **Usaha:** sedang — satu adapter penyimpanan baru di backend (bukan di
  lapisan data), plus kredensial & kebijakan bucket. Perlu koordinasi dengan
  pemilik `backend/`.
* **Biaya:** MinIO di VPS yang sama = nol uang, tambah ±1 GB RAM. S3/OSS
  berbayar per GB + per permintaan.
* **Keuntungan:** PDF tidak lagi terikat ke satu disk; versioning dan
  object-lock (anti-hapus) tersedia; backend bisa diperbanyak tanpa berbagi
  volume.
* **Risiko:** **tautan pra-tanda-tangan (presigned URL) adalah *bearer
  secret*** — persis masalah yang sama dengan tautan berbagi OneDrive. Dokumen
  non-publik tidak boleh diberi presigned URL berumur panjang.
* **Cocok bila:** dokumen DPEA akan disimpan permanen dan jumlahnya tumbuh
  jauh melewati ribuan, atau mitra mewajibkan penyimpanan anti-hapus.

### Pilihan D — Hibrida: PDF di Nextcloud mitra, metadata+vektor di Postgres

Nextcloud DPEA yang sudah ada menjadi penyimpanan dokumen; HERO menyimpan
metadata, pasal, dan vektor, serta merujuk berkasnya lewat WebDAV.

* **Usaha:** sedang–besar: perlu *streaming* berkas lewat WebDAV untuk setiap
  "buka PDF asli", dan penanganan folder yang dipindah manual oleh pengguna.
* **Keuntungan:** satu tempat dokumen bagi mitra, dengan izin akses Nextcloud
  yang sudah mereka pahami.
* **Risiko besar:** HERO kehilangan kendali atas berkas yang jadi **bukti
  rujukan**. Pengguna yang memindahkan folder di Nextcloud akan memutus tautan
  temuan harmonisasi ke halaman PDF-nya — dan validasi sampling DPEA justru
  bergantung pada tautan itu.
* **Cocok bila:** mitra mewajibkan dokumen berada di sistem mereka. Kalau
  tidak diwajibkan, jangan.

### Matriks ringkas

| | A: filesystem | B: Postgres sentral | C: object storage | D: Nextcloud |
|---|---|---|---|---|
| Usaha | **sangat kecil** | kecil | sedang | sedang–besar |
| Biaya uang | nol | nol | nol (MinIO) / per GB (S3) | nol |
| Perubahan di `backend/` | tidak ada | tidak ada | **ada** (storage service) | **ada** |
| Cadangan | snapshot + rclone | `pg_dump` + `storage/` | kebijakan bucket | tanggung jawab mitra |
| Tahan hilang-disk | lemah | lemah | **kuat** | kuat |
| Risiko tautan bukti putus | rendah | rendah | rendah | **tinggi** |
| Siap sebelum 24 Des 2026 | **ya** | ya | mungkin | tidak |

---

## 4. Menjalankan tools-nya di server

Tiga cara, bisa dipilih bertahap. Semuanya memakai perintah yang sudah ada.

### Cara 1 — Timer berkala (paling sederhana)

Satu unit `oneshot` + timer, tiap 30 menit: pindai → ekstraksi → cermin korpus.
Berkasnya sudah disiapkan:
[`../deploy/systemd/hero-bridge-sinkron.service`](../deploy/systemd/hero-bridge-sinkron.service)
dan `.timer`.

```bash
sudo cp /opt/hero/deploy/systemd/hero-bridge-sinkron.* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now hero-bridge-sinkron.timer
systemctl list-timers hero-bridge-sinkron.timer      # kapan jalan berikutnya
journalctl -u hero-bridge-sinkron -n 50 --no-pager   # apa yang terjadi
```

* **Kelebihan:** tidak ada proses yang menyala terus; kegagalan tidak
  mengganggu apa pun; mudah dimatikan.
* **Kekurangan:** dokumen yang baru diunggah menunggu sampai 30 menit.

### Cara 2 — Worker menyala terus + layanan analisa

Tiga unit `simple` dengan `Restart=always`:
[`hero-bridge-ekstraksi.service`](../deploy/systemd/hero-bridge-ekstraksi.service) ·
[`hero-bridge-pindai.service`](../deploy/systemd/hero-bridge-pindai.service) ·
[`hero-ml.service`](../deploy/systemd/hero-ml.service)

```bash
sudo cp /opt/hero/deploy/systemd/hero-bridge-*.service \
        /opt/hero/deploy/systemd/hero-ml.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now hero-bridge-ekstraksi hero-bridge-pindai hero-ml
```

Lalu satu baris di reverse proxy agar layanan analisa berada di asal yang sama
dengan backend (lihat [`INTEGRASI_BACKEND.md`](INTEGRASI_BACKEND.md) §3.3).

* **Kelebihan:** dokumen diproses dalam detik; layar Analisa & Harmonisasi
  hidup. **Ini yang dibutuhkan Fase 2–3.**
* **Kekurangan:** tiga proses yang perlu dipantau. `MemoryMax` sudah dipasang
  di tiap unit agar satu PDF rusak tidak menjatuhkan Nextcloud di VPS yang sama.
* **Catatan keamanan:** `hero-ml.service` mengikat `127.0.0.1` dan **tidak
  punya autentikasi sendiri** — aksesnya harus lewat reverse proxy yang sama
  dengan backend. Jangan buka portnya ke internet.

### Cara 3 — Ikut Docker Compose backend

Tambah dua service di sebelah backend, memakai image berisi `pipeline/` +
Tesseract. Perlu `docker-compose.override.yml` atau perubahan di
`backend/docker-compose.yml` — **milik rekan backend, jadi perlu kesepakatan.**

```yaml
# docker-compose.override.yml (sketsa — belum diuji)
services:
  hero-worker:
    build: { context: ../pipeline, dockerfile: Dockerfile }
    command: hero bridge ekstraksi --loop
    environment:
      - HERO_BACKEND_URL=http://backend:8000
      - HERO_BACKEND_INTERNAL_KEY=${INTERNAL_API_KEY}
      - HERO_PG_DSN=postgresql://hero_user:${POSTGRES_PASSWORD}@db:5432/hero_db
    volumes: [ "hero-data:/work/data", "./config:/work/config:ro" ]
    working_dir: /work
    depends_on: { backend: { condition: service_healthy } }
  hero-ml:
    build: { context: ../pipeline, dockerfile: Dockerfile }
    command: hero bridge serve --host 0.0.0.0 --port 8100
    ports: [ "8100:8100" ]
    volumes: [ "hero-data:/work/data", "./config:/work/config:ro" ]
    working_dir: /work
volumes: { hero-data: }
```

* **Kelebihan:** satu `docker compose up` menyalakan semuanya; lingkungan OCR
  terkunci di image (tidak ada "Tesseract versi berapa di server?").
* **Kekurangan:** image-nya besar (Tesseract + PyMuPDF + model), dan model 3 GB
  harus masuk volume, bukan image. Belum ada `pipeline/Dockerfile` — perlu dibuat.
* **Cocok bila:** infra/QA memang ingin semuanya dalam satu kontainer.

---

## 5. Kebutuhan VPS (terukur, bukan ditebak)

| Kebutuhan | Angka | Dari mana |
|---|---|---|
| RAM, worker ekstraksi | < 500 MB per dokumen; puncak saat OCR halaman 300 dpi | `MemoryMax=2G` di unit sudah lapang |
| RAM, membangun indeks LSA | ± 700 MB pada 7.800 potongan (puncak hitung bigram) | SPIKE #42; pada 80.000 potongan wajib pakai `fit_sample` + `max_features` |
| RAM, model semantik | **e5-large ± 3 GB** saat memuat · **minilm < 1 GB** | `vector.semantic_model` |
| Disk | lihat §2: **40 GB lapang, 20 GB pas-pasan** | terukur + proyeksi |
| CPU | ekstraksi 0,1–2 detik/dokumen born-digital; OCR jauh lebih lambat | terukur: 7 dokumen 4,7 s |
| Jaringan keluar | hanya ke situs sumber saat pindai; **nol** untuk analisa & vektor | semua model lokal |

**Keputusan model.** Pada korpus terukur, e5-large memberi MRR parafrase 0,76
vs minilm 0,45 — selisih besar. Tapi e5-large butuh 3 GB RAM. Di VPS 2 GB,
pilih `minilm` atau matikan pencarian semantik (`bridge.embedder: lsa`);
Mode Deterministik tidak pernah membutuhkannya.

---

## 6. NDA & keamanan — yang tidak boleh dikompromikan

1. **Dokumen non-publik tidak boleh keluar server.** Semua model HERO lokal
   (ONNX), jadi analisa dan vektor tidak pernah mengirim teks ke mana pun.
   Satu-satunya jalur keluar adalah lapisan AI opsional (`analysis.ai_enabled`),
   yang punya saklarnya sendiri dan `ai_allow_internal: false`.
2. **Kunci API internal = akses penuh ke `/api/v1/internal/*`.** Taruh di
   `/opt/hero/.env` dengan mode `600` milik user `hero`, **bukan** di berkas
   unit systemd (berkas unit dapat dibaca semua pengguna sistem).
3. **Tautan berbagi OneDrive dan presigned URL adalah bearer secret.** Jangan
   masuk YAML, log, atau laporan. `redact_ref()` sudah dipakai di ekspor.
4. **"Publik" harus terbukti.** Setelah setiap sinkronisasi folder/OneDrive,
   jalankan `hero akses audit` lalu `--apply`. Audit hanya mengetatkan.
5. **Layanan ML tanpa autentikasi** — wajib di belakang reverse proxy, terikat
   loopback. Kalau suatu saat perlu diakses langsung, tambahkan kunci API
   seperti backend, jangan dibuka apa adanya.
6. **Jangan simpan dokumen mitra di laptop lebih lama dari yang diperlukan.**
   Begitu worker jalan di server, `data/` di laptop boleh dihapus.

---

## 7. Cadangan & pemulihan

**Wajib dicadangkan** (kehilangan = tidak bisa dibangun ulang):

| Apa | Cara |
|---|---|
| Postgres backend | `pg_dump` harian — `backend/deploy/backup.sh` sudah ada |
| PDF asli (`storage/`) | snapshot VPS + rclone ke Nextcloud |
| `config/*.yaml` + `.env` | ada di repo (kecuali `.env` — simpan di pengelola kata sandi) |

**Tidak perlu dicadangkan** (data turunan, dibangun ulang dengan satu perintah):

| Apa | Cara bangun ulang |
|---|---|
| `data/hero_catalog.db` (cermin korpus) | `hero bridge sinkron` |
| `data/hero_vectors.db` | `hero vector build` |
| `data/hero_bridge.db` | terbentuk sendiri — **kecuali** tabel `article_page` & `doc_meta`: halaman pasal dan dasar hukum hanya bisa dipulihkan dengan **mengekstraksi ulang** dokumennya (`requeue` + `hero bridge ekstraksi`). Murah, tapi bukan instan. |
| `data/models/` | terunduh otomatis saat pertama dipakai (3 GB) |

Sebelum penulisan massal apa pun ke katalog:
`sqlite3 data/hero_catalog.db ".backup data/hero_catalog.backup-$(date +%F).db"`

---

## 8. Langkah memindahkan (dan cara mundur)

Urutan yang paling tidak berisiko, tiap langkah bisa dibatalkan sendiri:

```bash
# 1. Kode lapisan data ke VPS (tanpa data, tanpa venv)
rsync -avz --exclude='.venv' --exclude='data' --exclude='__pycache__' \
  pipeline/ USER@VPS:/opt/hero/
ssh USER@VPS 'cd /opt/hero && sudo bash deploy/install.sh'   # python, tesseract, user hero, venv

# 2. Rahasia (mode 600, milik hero) — JANGAN di unit systemd
ssh USER@VPS 'sudo -u hero tee /opt/hero/.env >/dev/null <<ENV
HERO_BACKEND_URL=http://127.0.0.1:8000
HERO_BACKEND_INTERNAL_KEY=<INTERNAL_API_KEY backend>
HERO_PG_DSN=postgresql://hero_user:<sandi>@127.0.0.1:5432/hero_db
ENV
sudo chmod 600 /opt/hero/.env'

# 3. Buktikan tersambung SEBELUM menyalakan apa pun
ssh USER@VPS 'cd /opt/hero && sudo -u hero .venv/bin/hero bridge status'

# 4. Sekali jalan manual, satu dokumen, lihat hasilnya di UI
ssh USER@VPS 'cd /opt/hero && sudo -u hero .venv/bin/hero bridge ekstraksi --limit 1'

# 5. Baru pasang timer (Cara 1) atau worker (Cara 2)
```

**Cara mundur, per langkah:**

| Kalau gagal di | Mundurnya |
|---|---|
| 3 (status merah) | tidak ada yang berubah di backend — perbaiki `.env`/`CRAWLER_BACKEND`, coba lagi |
| 4 (hasil ekstraksi salah) | `POST /api/v1/internal/extraction/requeue/{id}` mengembalikan dokumen ke antrian; metadata yang sudah dikoreksi manual tidak pernah ditimpa |
| 5 (worker bikin beban) | `systemctl disable --now hero-bridge-*` — backend kembali memakai crawler internalnya, aplikasi tetap jalan |
| mana pun | laptop tetap bisa menjalankan perintah yang sama; tidak ada yang terkunci di server |

---

## 9. Rekomendasi & yang saya butuh dari Anda

**Rekomendasi: A + Cara 2 sekarang, pindah ke B setelah demo.**

Alasannya dari angka, bukan selera:

* Pilihan A tidak menyentuh `backend/` sama sekali, jadi tidak ada koordinasi
  yang bisa menunda demo 8 Oktober.
* Cara 2 (worker menyala terus) adalah satu-satunya yang membuat layar Analisa
  dan Harmonisasi Fase 2–3 terasa hidup; selisihnya nyata: detik vs 30 menit.
* Pilihan B berikutnya karena ia **menghapus satu kelas bug** — dua salinan
  metadata yang bisa berbeda — dan ongkos pindahnya kecil (jembatan sudah
  mencermin dari Postgres, tinggal menjadikan cermin itu "boleh dihapus").
* Pilihan C hanya bila mitra mewajibkan penyimpanan anti-hapus; D sebaiknya
  dihindari karena memutus tautan bukti yang justru dipakai validasi DPEA.

**Empat keputusan yang hanya bisa Anda ambil:**

1. **VPS mana, dan berapa RAM-nya?** Ini yang menentukan model embedding:
   ≥ 4 GB → e5-large (MRR parafrase 0,76); 2 GB → minilm (0,45) atau LSA saja.
2. **Cara 1 atau Cara 2?** Berkala (sederhana, lambat) atau menyala terus
   (butuh Fase 2–3, perlu dipantau).
3. **Siapa yang memegang `INTERNAL_API_KEY` produksi?** Saat ini nilai
   contohnya ada di `.env.example` backend — harus diganti sebelum rilis.
4. **Apakah `backend/` boleh diubah?** Kalau ya, empat celah kontrak di
   [`INTEGRASI_BACKEND.md`](INTEGRASI_BACKEND.md) §7 bisa ditutup rapi (kolom
   halaman pasal, idempotensi insert pasal, hierarki ayat, dimensi embedding).
   Kalau tidak, semuanya sudah ada jalan kelilingnya dan tetap jalan.

Apa pun pilihannya, tidak ada yang perlu dikunci sekarang: seluruh perintah
`hero bridge …` jalan sama saja di laptop maupun di server.
