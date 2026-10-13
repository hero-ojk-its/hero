# Yang harus dilakukan di VPS — Fase 2 (kontrak pasal Langkah 13)

**Untuk:** Fathir (operator VPS) · **Peran penulis:** Data / ML
**Tanggal:** 12 Oktober 2026 · **Prasyarat:** backend sudah di `main` pasca PR #115

Lapisan data sekarang memakai kontrak pasal baru: **halaman PDF per pasal**,
**hierarki ayat**, dan **ganti-bersih idempoten**. Semuanya hanya aktif bila
backend di VPS sudah dimigrasi. Urutan di bawah ini penting — langkah 1 dan 2
harus selesai sebelum langkah 4, kalau tidak jembatan tetap memakai jalur lama
(dan itu memang perilaku yang benar, bukan kegagalan).

> Semua perintah **Anda jalankan sendiri** lewat SSH. Sesi ini tidak punya
> akses ke VPS Anda.

---

## 1. Migrasi backend (wajib lebih dulu)

Revisi yang dituju: **`e5f6a7b8c9d0`**.

```bash
cd /opt/hero-backend          # sesuaikan dengan lokasi backend di VPS Anda
git pull
docker compose up -d --build backend
```

Periksa — ini satu-satunya bukti yang dipakai lapisan data:

```bash
curl -s http://127.0.0.1:8000/health | python3 -m json.tool
```

Yang harus terlihat:

```jsonc
"alembic_revision": "e5f6a7b8c9d0",
"alembic_head":     "e5f6a7b8c9d0",
"migrations_up_to_date": true
```

Kalau `alembic_revision` masih revisi lama, **berhenti di sini** dan jalankan
migrasinya. Melanjutkan tidak merusak apa pun, tetapi halaman dan ayat tidak
akan tersimpan.

---

## 2. Perbarui lapisan data

### 2a. Periksa dulu tata letak VPS Anda

Ada perangkap di sini. Workspace `Capstone/` masih memuat salinan kode lama di
`hero-tools/`, dan `deploy/README.md` dulu menyuruh rsync dari sana. Salinan
itu **jauh tertinggal**: per 12 Okt 2026 ia tidak punya paket `bridge/`
(seluruh jembatan ke backend), `harmonisasi/`, maupun `loadtest.py`. Kalau VPS
Anda pernah di-rsync dari `Capstone/`, `hero bridge …` bisa saja tidak ada di
sana sama sekali.

```bash
ssh "$VPS" 'ls /opt/hero/hero-tools >/dev/null 2>&1   && echo "TATA LETAK LAMA (hero-tools)" || echo "tata letak repo"'
ssh "$VPS" 'sudo -u hero /opt/hero/.venv/bin/hero bridge status >/dev/null 2>&1   && echo "jembatan ADA" || echo "jembatan TIDAK ADA"'
```

### 2b. Kirim kode dari repo (bukan dari Capstone)

Sumber kebenaran kode adalah `hero/pipeline/`.

```bash
# Dari Mac:
export VPS="USER@IP_VPS"
rsync -avz --delete --exclude='__pycache__' --exclude='.pytest_cache'   "/Users/mirzafathirr/Cool Yeah/TC/hero/pipeline/hero/" "$VPS:/opt/hero/hero/"
rsync -avz   "/Users/mirzafathirr/Cool Yeah/TC/hero/pipeline/pyproject.toml"   "/Users/mirzafathirr/Cool Yeah/TC/hero/pipeline/deploy/"   "$VPS:/opt/hero/"
```

Bila hasil pemeriksaan 2a adalah **tata letak lama**, hapus sisanya — dua
salinan paket `hero` tidak boleh ada bersamaan (`pyproject.toml` repo memakai
`packages.find` pada `hero/`, yang lama memakai
`package-dir = {"hero" = "hero-tools"}`):

```bash
ssh "$VPS" 'sudo rm -rf /opt/hero/hero-tools /opt/hero/hero.egg-info'
```

### 2c. Pasang ulang (wajib, bukan opsional)

`openpyxl` kini dideklarasikan sebagai dependensi inti — sebelumnya dipakai
jalur bawaan `hero inventory` tanpa pernah dideklarasikan, jadi ia jalan di
laptop pengembang dan gagal di mesin yang bersih. Pemasangan ulang yang
mengambilnya **tidak bisa dilewati**.

```bash
# Di VPS:
sudo -u hero /opt/hero/.venv/bin/pip install -q -e "/opt/hero[api,vector]"
sudo -u hero /opt/hero/.venv/bin/hero version
sudo -u hero /opt/hero/.venv/bin/python -c "import openpyxl; print('openpyxl ok')"
```

---

## 3. Pastikan kontrak terdeteksi

```bash
cd /opt/hero && sudo -u hero /opt/hero/.venv/bin/hero bridge status
```

Baris **"kontrak pasal"** harus berbunyi:

```
kontrak pasal   Langkah 13 — halaman, hierarki ayat, ganti-bersih (sumber: openapi)
```

Kemungkinan lain dan artinya:

| Yang tampil | Arti | Tindakan |
|---|---|---|
| `Langkah 13 … (sumber: openapi)` | siap | lanjut |
| `belum terdeteksi` | `/openapi.json` ditutup (`EXPOSE_API_DOCS=false` di produksi) | lihat kotak di bawah |
| `lama` | backend belum dimigrasi | ulangi langkah 1 |

> **Bila "belum terdeteksi" padahal langkah 1 sudah selesai**, tambahkan ke
> `/opt/hero/config/sources.yaml` lalu jalankan `hero bridge status` lagi:
>
> ```yaml
> bridge:
>   article_contract: v2
> ```
>
> Jangan menyetel ini sebelum `/health` menunjukkan revisi `e5f6a7b8c9d0`:
> backend lama **mengabaikan field yang tidak dikenalnya tanpa galat**, jadi
> memaksanya akan membuat pasal ganda — bukan pesan kesalahan.

---

## 4. Perbaiki batas memori layanan analisa (penting)

`deploy/systemd/hero-ml.service` sebelumnya membatasi `MemoryMax=600M`.
Terukur dengan `hero loadtest --profil ml`:

| Skenario | RAM terpakai | CPU |
|---|---|---|
| Deterministik saja (lexical + LSA) | **347–530 MB** | ±1–4 inti |
| + pencarian semantik e5-large | **1.950–2.250 MB** | ±5–9 inti |

**Masalahnya:** `GET /api/v1/ml/cari` default-nya `metode=hybrid`, dan hybrid
memuat model semantik. Jadi satu permintaan pencarian tanpa `metode` eksplisit
akan menembus 600 MB dan systemd mematikan layanan — gejalanya "layanan
analisa mati sendiri setiap kali ada yang mencari".

> **Terukur setelah indeks dibangun (13 Okt) — dan satu koreksi atas angka saya sebelumnya.**
> Kondisi tunak `hero-ml` adalah **anon ≈ 180 MB + cache berkas ≈ 570 MB**. Cache halaman indeks
> (`hero_vectors.db`, 705 MB) **dihitung ke cgroup layanan**. Dengan `MemoryHigh=550M`, kernel terus
> membuang cache itu dan menukar memori anonim ke swap sehingga **setiap kueri membaca disk: 2,2 s**
> (`memory.events` `high` = 838). Tanpa `MemoryHigh`: **0,23 s**. Angka "210–248 MB" yang sempat tercatat
> adalah pengukuran saat cache belum terisi — **jangan dipakai**.
>
> Unit di repo sekarang: **tanpa `MemoryHigh`, `MemoryMax=900M`, `CPUQuota=100%`**. Di VPS ini model
> semantik **tidak ada**, jadi `GET /api/v1/ml/cari` **tanpa** `metode` (bawaannya `hybrid`) menjawab
> **503**, bukan mematikan layanan. Frontend wajib mengirim `metode=lsa` atau `metode=lexical`.

> **Peringatan kapasitas host:** di bawah 12 koneksi, anon `hero-ml` naik ke **±540 MB** (idle ±180 MB).
> VPS 1,9 GB sudah memakai ±950 MB untuk Nextcloud/backend/database dan swap host ±0,9 GB. Layanan
> analisa tetap berjalan (0% galat pada 12 koneksi), tetapi **tidak ada ruang tambahan**. Bila pengguna
> nyata bertambah, naikkan RAM server (≥ 4 GB) alih-alih menaikkan batas.

Berkas unit di repo sudah diperbarui (skenario Deterministik). **Pilih satu** sebelum memasangnya:

- **Tetap Deterministik** (hemat RAM, tanpa pencarian makna):
  pasang unit apa adanya, dan pastikan frontend selalu mengirim
  `metode=lsa` atau `metode=lexical` ke `/api/v1/ml/cari`.
- **Aktifkan pencarian semantik** (butuh RAM): sunting unit menjadi
  `MemoryMax=2800M` (tetap tanpa `MemoryHigh`), `CPUQuota=400%`. Pastikan VPS punya
  sisa RAM sebanyak itu — `free -h` sebelum memutuskan.

```bash
sudo cp /opt/hero/deploy/systemd/hero-ml.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart hero-ml
sudo systemctl status hero-ml --no-pager | head -20
curl -s http://172.17.0.1:8100/health | python3 -m json.tool | head -20
```

Kalau layanan pernah di-OOM, jejaknya ada di sini:

```bash
sudo journalctl -u hero-ml --since '1 day ago' | grep -i -E 'killed|oom|memory'
```

---

## 5. Indeks pencarian di VPS 1,9 GB (sudah dikerjakan 13 Okt — catatan untuk mengulang)

Korpus VPS: **207.530 potongan** dari 2.109 dokumen. Build LSA bawaan **dimatikan OOM-killer**
di ±1,0 GB (`anon-rss 1010660kB`), jadi tiga pembatas dipasang di `/opt/hero/config/sources.yaml`:

```yaml
vector:
  lsa_dim: 256
  lsa_fit_sample: 5000       # kosakata dilatih dari sampel; SEMUA potongan tetap diindeks
  lsa_max_features: 50000
  numpy_max_rows: 50000      # >50 ribu potongan → cari dari disk (sqlite-vec)
```

Menjalankan ulang (aman: batas cgroup membuat hanya prosesnya yang mati bila memori habis):

```bash
cd /opt/hero
nohup sudo systemd-run --scope -q -p MemoryMax=900M -p MemorySwapMax=512M -p CPUQuota=100% \
  nice -n 15 sudo -u hero -H /opt/hero/.venv/bin/hero vector build --lsa-only \
  > ~/vector-build.log 2>&1 < /dev/null &
tail -f ~/vector-build.log
sudo systemctl restart hero-ml
```

Hasil terukur: build **43 detik**, 705 MB di disk, `hero-ml` anon ≈ 180 MB + cache ≈ 570 MB, kueri ±**0,23 s**
(pertama setelah restart 1,2–1,6 s; sebelum pemanasan: 2,9 s). Kualitas LSA pada sampel diuji di Mac
(kueri berlabel `config/eval_queries.yaml`): tidak terlihat penurunan, tetapi hanya 12 kueri per set,
jadi bukti lemah — belum diukur pada korpus VPS.

> Log build **harus** ditulis ke folder milik `ubuntu` (`~/`). Menulis ke `/tmp/…` milik `hero`
> membuat pengalihan gagal sebelum build dimulai, tanpa pesan yang jelas.

Lalu cermin korpus:

```bash
sudo -u hero /opt/hero/.venv/bin/hero bridge sinkron
```

---

## 6. Mengisi halaman dokumen yang sudah ada

**Terukur 13 Okt:** dari 735 pasal di backend, **0 yang punya `page`**. Pasal itu dikirim sebelum
kontrak Langkah 13 aktif, dan penjaga kiriman-ulang (sengaja) menahannya. Hanya **25 dokumen** yang
punya pasal; 123 dokumen terindeks lainnya tidak berpasal — 75 SEOJK (wajar) dan 48 POJK/PADK yang
**pendek** (rata-rata ±5.000 karakter vs 84.000–164.000), kemungkinan sampul/abstrak.

Untuk 25 dokumen berpasal itu, ekstraksi ulang mengisi halaman. Dua hambatan:

1. **Buku besar lokal menahan kiriman ulang** untuk berkas yang sama (memang gunanya). Hapus catatannya:

   ```bash
   sudo -u hero /opt/hero/.venv/bin/python - <<'PY'
   import sqlite3
   c = sqlite3.connect("/opt/hero/data/hero_bridge.db")
   ids = (1, 2, 3)            # <- ganti dengan id dokumen berpasal
   c.execute(f"DELETE FROM extraction WHERE document_id IN ({','.join('?'*len(ids))})", ids)
   c.commit()
   PY
   ```
   (VPS tidak punya CLI `sqlite3`; cadangan sudah ada di `data/cadangan-fase2-*`.)

2. **Backend membatasi 3 percobaan** dan `requeue` tidak mereset hitungannya:

   ```bash
   docker exec hero_db sh -c 'psql -U $POSTGRES_USER -d $POSTGRES_DB -c \
     "UPDATE documents SET extraction_attempts = 0, processing_status = '"'"'diterima'"'"' WHERE id IN (1,2,3);"'
   ```

Lakukan bertahap (±10 dokumen), lalu `hero bridge sinkron` dan periksa:

```sql
select count(*) pasal, count(page) berhalaman from articles;   -- keduanya harus sama
```

**Ini mengubah data produksi** (pasal diganti dalam satu transaksi). Cadangkan dulu:
`docker exec hero_db sh -c 'pg_dump -U $POSTGRES_USER $POSTGRES_DB' | gzip > ~/hero_db-$(date +%F).sql.gz`

### 6a. Dokumen yang menggantung di `diproses`

Insiden 13 Okt: dokumen 93/94/137 (lembar ringkasan SEOJK satu halaman) tidak pernah keluar dari
`diproses`. Penyebab berantai: judul terbaca **298 karakter** (potongan butir isi) dan nomor terbaca
nomor peraturan **lain** yang disebut sebagai dicabut → PATCH menjawab 200, lalu commit penempatan di
backend gagal (`varchar(255)`) dan di-*rollback* → diklaim ulang tiap 30 menit. Diperbaiki di lapisan
data: semua kolom string dipotong ke batas backend, dan kop yang jelas gagal dibaca menurunkan
keyakinan ke 0,4 sehingga dokumen masuk **antrean koreksi** (`perlu_koreksi`) alih-alih lolos dengan
nomor salah. **Catatan untuk tim Backend:** PATCH mengembalikan 200 dengan status tidak berubah saat
penempatan gagal — sebaiknya mengembalikan galat.

---

## 7. Ayat: jangan dinyalakan sendiri

`bridge.push_ayat` **masih `false`** dan sebaiknya tetap begitu sampai ada
kesepakatan. Mesinnya sudah siap dan teruji (169/169 ayat tertaut ke pasal
induk yang benar), tetapi menyalakannya **mengubah isi tabel `articles`
backend**: satu POJK uji berubah dari 79 baris menjadi 79 pasal + 169 ayat,
dan teks ayat sudah termuat di dalam `content_text` pasalnya — jadi ada
duplikasi teks di indeks pencarian.

Itu keputusan Backend + Frontend (tampilan dan unit pencarian), bukan lapisan
data sendiri. Catatan untuk mereka ada di
[`INTEGRASI_BACKEND.md`](INTEGRASI_BACKEND.md) §7c, termasuk bahwa
`GET /api/v1/documents/{id}` menyaring `parent_id IS NULL` sehingga ayat
tersimpan tetapi tidak muncul di respons itu.

---

## 8. Daftar periksa

- [ ] `/health` → `alembic_revision: e5f6a7b8c9d0`, `migrations_up_to_date: true`
- [ ] `hero bridge status` jalan di VPS (bukan tata letak `hero-tools/` yang tertinggal)
- [ ] `pip install -e "/opt/hero[api,vector]"` dijalankan ulang (karena `openpyxl`)
- [ ] `hero bridge status` → kontrak pasal **Langkah 13**
- [ ] `hero-ml.service` memakai batas memori yang sesuai skenario, layanan tidak di-OOM
- [ ] `hero bridge sinkron` → `dokumen_terpeta_ke_backend` > 0 dan layanan analisa `siap` (lexical + lsa)
- [ ] `select count(*), count(page) from articles` → kedua angka sama (setelah ekstraksi ulang §6)
- [ ] Tidak ada pasal ganda: `SELECT document_id, order_index, COUNT(*) FROM articles
      GROUP BY 1,2 HAVING COUNT(*) > 1;` → kosong
- [ ] `bridge.push_ayat` masih `false` kecuali sudah disepakati tim

---

## Rujukan

- Kontrak pasal & hasil uji ujung-ke-ujung: [`INTEGRASI_BACKEND.md`](INTEGRASI_BACKEND.md) §7
- Angka RAM/CPU/latensi: [`PERFORMA_SERVER_ANALISIS.md`](PERFORMA_SERVER_ANALISIS.md)
- Prosedur deploy & update: [`../deploy/README.md`](../deploy/README.md) §Update kode
- Laporan backend Langkah 13: `backend/docs/reports/step13-report.md`

---

## Yang TIDAK perlu Anda lakukan

- **Tidak perlu menghapus `article_page`** di buku besar lokal. Tabel itu tetap
  dipakai untuk dokumen yang diekstraksi sebelum kolom halaman ada di backend;
  cermin korpus membaca backend lebih dulu, lalu jatuh ke tabel ini.
- **Tidak perlu mengubah dimensi kolom embedding.** Masih 1536 dan jembatan
  jalan di kedua skenario (`INTEGRASI_BACKEND.md` §6, §7e).
- **Tidak perlu menjalankan ulang `hero vector build`** karena kontrak pasal.
  Vektor lapisan data tidak terpengaruh perubahan ini.
