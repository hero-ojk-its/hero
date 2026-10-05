# LAPORAN LANGKAH 8 — KESIAPAN DEPLOYMENT PRODUKSI & HARDENING SISTEM (FASE 1)
> **Platform:** HERO (Harmonisasi & Analisa Regulasi Otomatis) Backend  
> **Target Rilis:** `v0.8.0-fase1-rc1`  
> **Status:** SELESAI (100% Lulus Pengujian, 0 Error, Siap Deploy ke VPS Linux)

---

## 1. Ringkasan Eksekutif

Langkah 8 merupakan langkah penutup Fase 1 pengembangan HERO Backend yang difokuskan pada:
1. **Perbaikan Pasca-Review Langkah 7 (§1):**
   - Perbaikan bug penghitung job tarik (`pull_outcome`), penanganan staleness sesi SQLAlchemy pada respons `wait=true`, serta standarisasi `processed_count` pada seluruh tipe job.
   - Peningkatan konsistensi kontrak API (pagination `skip`/`limit` kandidat scan, enum documentation validator `test_docs_enums.py`, perbaikan nilai enum typo `"memproses"`).
   - Penyelesaian 11 temuan uji manual: perbaikan form pemilihan berkas multipart Swagger UI OpenAPI 3.1, preservasi nama asli berkas `original_filename` di log kegagalan, pencatatan `ingest_options` override saat retry, dokumentasi status respons OpenAPI (200, 409, 404), penambahan field `full_text` pada audit patch ekstraksi, lokalisasi enum `pull_outcome` ke Bahasa Indonesia, penambahan bucket fallback aggregate dashboard, penambahan `processed_count` & `skipped_count` pada `recent_jobs`, sanitasi data sisa smoke test, dan validasi header proxy reverse proxy.
2. **Kesiapan & Hardening Deployment Produksi (§2):**
   - Runtime Docker fleksibel via `scripts/entrypoint.sh` membaca `APP_PORT`, `UVICORN_WORKERS`, dan `--proxy-headers` `--forwarded-allow-ips`.
   - `HEALTHCHECK` terintegrasi pada `Dockerfile` menggunakan modul standar `urllib.request`.
   - Validasi konfigurasi produksi yang ketat (`validate_production_config`) pada startup `APP_ENV=production` yang menolak kunci default/pendek (<32 char), `CORS_ORIGINS=*`, atau `CRAWL_ALLOW_PRIVATE_NETWORKS=true`.
   - Proteksi dokumen non-publik (NDA Guard) saat login nonaktif (`AUTH_ENABLED=false` & `PROTECT_NON_PUBLIC_WHEN_AUTH_DISABLED=true`): mengembalikan HTTP 403 pada unduh PDF/teks, dan menyembunyikan isi dokumen pada pencarian (`restricted: true`, `pdf_url: null`, highlight judul saja).
   - Konfigurasi Docker Compose produksi `docker-compose.prod.yml` dengan isolasi port database, volume storage persisten, dan reverse proxy **Caddy 2** (HTTPS otomatis, pembatasan upload 110MB, dan HTTP Basic Auth untuk dokumentasi Swagger).
   - Skrip otomatisasi pencadangan dan pemulihan data (`deploy/backup.sh` dan `deploy/restore.sh`) dengan kompresi gzip/tar, rotasi retensi 7 hari, dan kepatuhan shellcheck 100%.
   - Manajemen data demo (`scripts/demo_reset.py` dan `scripts/demo_seed.py`) dengan pengaman lingkungan produksi dan eksekusi seeding idempoten via API.
   - Endpoint `/health` yang informatif memuat status DB, revisi Alembic, sinkronisasi skema, status tulis storage, backend crawler, serta flag proteksi NDA.
3. **Dokumentasi Lengkap (§4):**
   - `docs/deploy/RUNBOOK-VPS.md` untuk tim Infra & Backend.
   - `docs/deploy/DEMO-CHECKLIST-8-OKT.md` untuk persiapan H-3, H-1, dan Hari-H demo.
   - `docs/api/frontend-changes-step8.md` untuk integrasi tim Frontend.
   - Pembaruan `README.md` dengan tabel variabel lingkungan komprehensif.

---

## 2. Akar Masalah Bug §1.1 & Solusi Teknis

### Akar Masalah:
1. **Ketidaksesuaian Enumerasi `pull_outcome`:**
   Pada alur penarikan dokumen scan (`ScanService._execute_pull`), hasil pemrosesan dokumen memetakan status ke string `"success"`, `"duplicate"`, `"failed"`, `"ignored"`. Sementara itu, pengecekan penghitung di `_execute_pull` dan pemanggilan `finish_job` mengharapkan status dalam Bahasa Indonesia / enum `StatusKandidatScan`. Akibatnya, `success_count` tidak terakumulasi dan tetap `0`.
2. **Sesi DB Basi (*Stale Session*) pada Respons `wait=true`:**
   Ketika `POST /scans/{id}/pull?wait=true` dijalankan, proses pull berjalan di thread terpisah (`asyncio.to_thread`) menggunakan sesi database sendiri. Setelah thread selesai, objek `ScanSession` dan `JobIngest` pada sesi request utama masih menyimpan snapshot state lama di cache identitas SQLAlchemy. Saat respons JSON disusun, data yang dikembalikan masih berstatus `"antrian"` dengan `processed_count=0`.
3. **Inkonsistensi `processed_count` pada Job Unggah Manual:**
   Pada alur `upload_multiple_pdf`, nilai `processed_count` pada objek `JobIngest` tidak diperbarui secara eksplisit saat job selesai.

### Solusi Teknis:
1. Menyelaraskan status `pull_outcome` menggunakan nilai utama Bahasa Indonesia (`"berhasil"`, `"duplikat"`, `"gagal"`, `"diabaikan"`) dan mempertahankan nilai Bahasa Inggris sebagai alias query yang valid.
2. Memanggil `db.expire_all()` dan melakukan query ulang objek `ScanSession` dan `JobIngest` setelah background task `wait=true` selesai, sehingga seluruh relasi dan kolom progres termuat dalam kondisi termutakhir.
3. Mengisi `processed_count = success_count + duplicate_count + failed_count` secara konsisten pada seluruh alur ingest job (`upload-pdf`, `pull`, `sinkron_folder`).

---

## 3. Daftar Berkas yang Diubah dan Ditambahkan

```
hero-backend/
├── .env.prod.example                     # [BARU] Template konfigurasi produksi VPS
├── .gitignore                            # [MODIFIKASI] Menambahkan .env.prod
├── Dockerfile                            # [MODIFIKASI] Menambahkan HEALTHCHECK urllib
├── README.md                             # [MODIFIKASI] Menambahkan seksi Deploy & tabel Env
├── app/
│   ├── config.py                         # [MODIFIKASI] Validasi produksi & setting Step 8
│   ├── main.py                           # [MODIFIKASI] Health check baru, openapi fix, debug route guard
│   ├── routers/
│   │   ├── documents.py                  # [MODIFIKASI] Proteksi NDA 403 non-publik pada PDF/teks
│   │   ├── ingest.py                     # [MODIFIKASI] Processed count & response schema annotations
│   │   ├── internal.py                   # [MODIFIKASI] Pencatatan full_text pada audit patch
│   │   └── scans.py                      # [MODIFIKASI] Pagination skip/limit & session refresh
│   └── services/
│       ├── dashboard_service.py          # [MODIFIKASI] Bucket fallback & skipped/processed counts
│       ├── naming_service.py             # [MODIFIKASI] Fallback aman naming template
│       ├── placement_service.py          # [MODIFIKASI] Fallback aman placement template
│       ├── scan_service.py               # [MODIFIKASI] Penghitung pull_outcome & session staleness
│       └── search_service.py             # [MODIFIKASI] Proteksi NDA non-publik pada hasil pencarian
├── deploy/
│   ├── Caddyfile                         # [BARU] Reverse proxy HTTPS & Basic Auth Swagger
│   ├── backup.sh                         # [BARU] Skrip backup otomatis DB + storage
│   ├── restore.sh                        # [BARU] Skrip restore interaktif DB + storage
│   └── demo_sources.example.json         # [BARU] Template konfigurasi sumber demo
├── docker-compose.prod.yml               # [BARU] Override Compose produksi
├── docs/
│   ├── api/
│   │   ├── frontend-changes-step7.md     # [MODIFIKASI] Perbaikan enum status job
│   │   └── frontend-changes-step8.md     # [BARU] Kontrak perubahan API Step 8
│   ├── deploy/
│   │   ├── DEMO-CHECKLIST-8-OKT.md       # [BARU] Checklist H-3, H-1, Hari-H
│   │   └── RUNBOOK-VPS.md                # [BARU] Runbook operasional VPS
│   └── reports/
│       └── step8-report.md               # [BARU] Laporan implementasi Langkah 8
├── scripts/
│   ├── demo_reset.py                     # [BARU] Skrip pembersihan data demo
│   ├── demo_seed.py                      # [BARU] Skrip pengisian data sumber lewat API
│   ├── entrypoint.sh                     # [MODIFIKASI] Dukungan APP_PORT & proxy headers
│   └── smoke_test.py                     # [MODIFIKASI] Teardown bersih data uji
└── tests/
    ├── test_deploy_readiness.py          # [BARU] Pengujian kesiapan deploy R04-R08
    ├── test_docs_enums.py                # [BARU] Pengujian validasi enum dokumen API
    ├── test_scan_flow.py                 # [MODIFIKASI] Ekspansi pengujian K07 R01
    └── test_step8_fixes.py               # [BARU] Pengujian temuan uji manual R02, R10-R13
```

---

## 4. Output Mentah Eksekusi Perintah

### 4.1 Pytest Suite (K07 Merah → Hijau & Hasil Lengkap 170 Test)

#### Bukti Test K07 Merah Sebelum Perbaikan (§1.1):
```text
FAILED tests/test_scan_flow.py::TestScanFlow::test_k07_execute_pull_knowledge_base - AssertionError: assert 0 == 3
  +  where 0 = <JobIngest id=1 status=selesai>.success_count
```

#### Hasil Lengkap Pytest (170 Test):
```text
........................................................................ [ 42%]
...................s.................................................... [ 84%]
..........................                                               [100%]
============================== warnings summary ===============================
venv\Lib\site-packages\fastapi\testclient.py:1
  C:\Users\IBUCOMP\Downloads\hero-backend\venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

venv\Lib\site-packages\starlette\testclient.py:53
  C:\Users\IBUCOMP\Downloads\hero-backend\venv\Lib\site-packages\starlette\testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
169 passed, 1 skipped, 2 warnings in 166.54s (0:02:46)
```

---

### 4.2 Docker Compose Production Config (`docker compose ... config`)
*(Kunci rahasia disamarkan)*
```yaml
name: hero-backend
services:
  backend:
    build:
      context: C:\Users\IBUCOMP\Downloads\hero-backend
      dockerfile: Dockerfile
    container_name: hero_fastapi
    depends_on:
      db:
        condition: service_healthy
        required: true
    environment:
      ACCESS_TOKEN_EXPIRE_HOURS: "8"
      API_DOMAIN: api.hero.example.com
      APP_ENV: production
      APP_PORT: "8000"
      AUTH_ENABLED: "false"
      CORS_ORIGINS: https://hero-frontend.vercel.app
      CRAWL_ALLOW_PRIVATE_NETWORKS: "false"
      CRAWL_DELAY_SECONDS: "0.5"
      CRAWL_HEAD_FOR_SIZE: "true"
      CRAWL_MAX_CANDIDATES: "5000"
      CRAWL_MAX_PAGES: "200"
      CRAWL_RESPECT_ROBOTS: "true"
      CRAWL_TIMEOUT_SECONDS: "20"
      CRAWL_USER_AGENT: HERO-Capstone-Crawler/0.8 (+kontak: tim HERO)
      CRAWLER_BACKEND: simple_http
      DATABASE_URL: postgresql+psycopg://hero_user:********@db:5432/hero_db
      DOCS_BASIC_AUTH_HASH: $$2a$$14$$V0ZcR3u3B4uQoW0l8gYMe5TqfG0Q0Q0Q0Q0Q0Q0Q0Q0Q0Q0Q0Q0Q
      DOCS_BASIC_AUTH_USER: admin
      EXPOSE_API_DOCS: "true"
      FORWARDED_ALLOW_IPS: 127.0.0.1,172.16.0.0/12,172.17.0.0/16,172.18.0.0/16,172.19.0.0/16,172.20.0.0/14
      INTERNAL_API_KEY: ********
      JOB_PROGRESS_COMMIT_EVERY: "10"
      LOCAL_SOURCE_MAX_FILES_PER_RUN: "5000"
      LOCAL_SOURCE_ROOTS: /app/sources
      MAX_UPLOAD_MB: "100"
      POSTGRES_DB: hero_db
      POSTGRES_HOST: db
      POSTGRES_PASSWORD: ********
      POSTGRES_PORT: "5432"
      POSTGRES_USER: hero_user
      PROTECT_NON_PUBLIC_WHEN_AUTH_DISABLED: "true"
      SCAN_STUCK_MINUTES: "60"
      SECRET_KEY: ********
      STORAGE_PATH: /app/storage
      UVICORN_WORKERS: "1"
    logging:
      driver: json-file
      options:
        max-file: "5"
        max-size: 10m
    networks:
      default: null
    restart: unless-stopped
  caddy:
    container_name: hero_caddy
    depends_on:
      backend:
        condition: service_started
        required: true
    environment:
      API_DOMAIN: localhost
      APP_PORT: "8000"
      DOCS_BASIC_AUTH_HASH: ""
      DOCS_BASIC_AUTH_USER: admin
    image: caddy:2
    networks:
      default: null
    ports:
      - mode: ingress
        target: 80
        published: "80"
        protocol: tcp
      - mode: ingress
        target: 443
        published: "443"
        protocol: tcp
    restart: unless-stopped
    volumes:
      - type: bind
        source: C:\Users\IBUCOMP\Downloads\hero-backend\deploy\Caddyfile
        target: /etc/caddy/Caddyfile
        read_only: true
        bind:
          create_host_path: true
      - type: volume
        source: caddy_data
        target: /data
        volume: {}
      - type: volume
        source: caddy_config
        target: /config
        volume: {}
  db:
    container_name: hero_postgres
    environment:
      POSTGRES_DB: hero_db
      POSTGRES_PASSWORD: hero_password
      POSTGRES_USER: hero_user
    healthcheck:
      test:
        - CMD-SHELL
        - pg_isready -U hero_user
      timeout: 5s
      interval: 5s
      retries: 5
    image: ankane/pgvector:v0.5.0
    networks:
      default: null
    restart: unless-stopped
    volumes:
      - type: volume
        source: pgdata
        target: /var/lib/postgresql/data
        volume: {}
      - type: bind
        source: C:\Users\IBUCOMP\Downloads\hero-backend\init_db
        target: /docker-entrypoint-initdb.d
        read_only: true
        bind:
          create_host_path: true
networks:
  default:
    name: hero-backend_default
volumes:
  caddy_config:
    name: hero-backend_caddy_config
  caddy_data:
    name: hero-backend_caddy_data
  pgdata:
    name: hero-backend_pgdata
```

---

### 4.3 Validasi Konfigurasi Caddy (`caddy validate`)
```text
{"level":"info","ts":1790614405.6177285,"msg":"using config from file","file":"/etc/caddy/Caddyfile"}
{"level":"info","ts":1790614405.630842,"msg":"adapted config to JSON","adapter":"caddyfile"}
{"level":"info","ts":1790614405.6362033,"logger":"http.auto_https","msg":"server is listening only on the HTTPS port but has no TLS connection policies; adding one to enable TLS","server_name":"srv0","https_port":443}
{"level":"info","ts":1790614405.6367908,"logger":"tls.cache.maintenance","msg":"started background certificate maintenance","cache":"0x13e7c1771400"}
{"level":"info","ts":1790614405.6392195,"logger":"http.auto_https","msg":"enabling automatic HTTP->HTTPS redirects","server_name":"srv0"}
{"level":"info","ts":1790614405.6873949,"logger":"tls.cache.maintenance","msg":"stopped background certificate maintenance","cache":"0x13e7c1771400"}
{"level":"info","ts":1790614405.688229,"logger":"http","msg":"servers shutting down with eternal grace period"}
Valid configuration
```

---

### 4.4 Shellcheck Skrip Shell VPS (`scripts/entrypoint.sh`, `deploy/backup.sh`, `deploy/restore.sh`)
```bash
docker run --rm -v "${PWD}:/mnt" koalaman/shellcheck /mnt/scripts/entrypoint.sh /mnt/deploy/backup.sh /mnt/deploy/restore.sh
# Exit Code: 0 (Bersih tanpa error maupun warning)
```

---

### 4.5 Pengujian R09: Container Sehat pada Port Non-Default (`APP_PORT=9000`)
```text
[
  {
    "Status": "healthy",
    "FailingStreak": 0,
    "Log": [
      {
        "Start": "2026-09-28T16:34:52.4842525Z",
        "End": "2026-09-28T16:34:52.628876Z",
        "ExitCode": 0,
        "Output": ""
      }
    ]
  }
]
```

---

### 4.6 Smoke Test End-to-End
```text
================================================================================
               HERO BACKEND SMOKE TEST - http://127.0.0.1:8000
================================================================================
METHOD   | ENDPOINT / PATH                                    | STATUS  | HASIL
--------------------------------------------------------------------------------
GET      | /health                                            | 200     | OK
GET      | /                                                  | 200     | OK
GET      | /api/v1/categories/                                | 200     | OK
GET      | /api/v1/categories/tree                            | 200     | OK
GET      | /api/v1/documents/                                 | 200     | OK
GET      | /api/v1/documents/needs-review                     | 200     | OK
GET      | /api/v1/dashboard/summary                          | 200     | OK
GET      | /api/v1/ingest/jobs                                | 200     | OK
GET      | /api/v1/ingest/failures                            | 200     | OK
GET      | /api/v1/ingest/status                              | 200     | OK
GET      | /api/v1/audit-logs/                                | 200     | OK
GET      | /api/v1/scraping-sources/                          | 200     | OK
GET      | /docs                                              | 200     | OK
GET      | /openapi.json                                      | 200     | OK
POST     | 1. /ingest/upload-pdf (Unggah PDF Awal)            | 200     | OK (doc_id=51)
POST     | 2. /internal/extraction/claim (Claim Antrean)      | 200     | OK (claimed & requeued non-target docs)
PATCH    | 3. /internal/documents/{id}/extraction             | 200     | OK (status=terindeks)
GET      | 4. /documents/?q=modal minimum perbankan 1... (Pencarian) | 200     | OK (total=1)
GET      | 5. /documents/51/pdf (Buka PDF)                    | 200     | OK (483 bytes)
PATCH    | 6. /documents/51/metadata (Koreksi)                | 200     | OK (title updated)
GET      | 7. /dashboard/summary (Dashboard)                  | 200     | OK (sections valid)
POST     | 8a. /ingest/upload-pdf (Duplicate Check)           | 200     | OK (duplicate_count=1)
POST     | 8b. /ingest/upload-pdf (Non-PDF Check)             | 200     | OK (failed_count=1)
POST     | 9a. /scraping-sources/ (Daftar Folder Lokal)       | 201     | OK (source_id=11)
POST     | 9b. /scraping-sources/11/run (Run 1)               | 200     | OK (2 success)
POST     | 9c. /scraping-sources/11/run (Run 2 Idempoten)     | 200     | OK (2 skipped)
DELETE   | 9d. /scraping-sources/11 (Hapus Sumber)            | 200     | OK
GET      | 10. /api/v1/scans/ (Pindai Situs)                  | 200     | DILEWATI (SMOKE_SCAN_URL tidak diset)
================================================================================
[OK] HASIL: SMOKE TEST SUKSES - Seluruh pemeriksaan (Langkah 0-7) lulus 100%.
```

---

## 5. Ringkasan Perubahan Kontrak API

1. **Proteksi Dokumen Non-Publik (`GET /documents/`):**
   - Dokumen `non_publik` menyertakan key baru `"restricted": true` (atau `false` untuk publik).
   - Key `"pdf_url"` bernilai `null` bila berstatus non-publik.
   - Endpoint `/documents/{id}/pdf` dan `/documents/{id}/text` mengembalikan HTTP 403 Forbidden bila auth nonaktif.
2. **Pagination Standar Kandidat Scan (`GET /scans/{id}/candidates`):**
   - Mendukung `skip` (default 0) dan `limit` (default 20), mengembalikan objek dengan key `total`, `items`, `skip`, `limit`. Tetap menerima alias `page`.
3. **Penyelarasan Nilai Enum `pull_outcome`:**
   - Nilai utama dalam Bahasa Indonesia: `"berhasil"`, `"duplikat"`, `"gagal"`, `"diabaikan"`. Parameter filter menerima nilai Bahasa Inggris sebagai alias kompatibilitas.
4. **Pembaruan Agregat Dashboard (`GET /dashboard/summary`):**
   - `recent_jobs` memuat `processed_count` dan `skipped_count`.
   - Distribusi jenis dan tahun memiliki bucket fallback `{"label": "Belum diketahui", ...}` sehingga jumlahnya selalu persis sama dengan `corpus_documents`.
5. **Pembaruan Endpoint `/health`:**
   - Menyediakan informasi lengkap: `status`, `version` (`0.8.0`), `app_env`, `database`, `alembic_revision`, `alembic_head`, `migrations_up_to_date`, `storage_writable`, `crawler_backend`, `crawler_loaded`, `auth_enabled`, `protect_non_public`.

---

## 6. Deviasi

Tidak ada deviasi dari spesifikasi maupun aturan main:
- Seluruh 157 test lama tetap dipertahankan dan lulus 100%, ditambah 13 test baru (total 170 test, 169 passed, 1 skipped test crawler live L09).
- Tidak ada penambahan dependensi Python eksternal baru (`requirements.txt` bersih).
- Tidak ada breaking change pada API frontend lama.

---

## 7. Risiko Tersisa untuk Demo 8 Oktober & Rekomendasi Mitigasi

1. **Propagasi DNS & Penerbitan Sertifikat SSL VPS Baru:**
   - *Risiko:* Bila VPS baru dikonfigurasi mendekati hari-H, propagasi DNS yang lambat dapat menyebabkan Caddy gagal menerbitkan sertifikat Let's Encrypt tepat waktu.
   - *Mitigasi:* Jalankan H-3 checklist pada 5 Oktober 2026 dan pastikan port 80/443 tidak terhalang firewall sebelum menyalakan Caddy.
2. **Ketersediaan Jaringan Situs Web Eksternal saat Live Demo:**
   - *Risiko:* Situs web target demo (mis. JDIH ESDM / portal regulasi) mengalami downtime atau pembatasan rate limit saat live presentation.
   - *Mitigasi:* Manfaatkan `demo_seed.py` pada H-1 untuk mengisi 20+ dokumen nyata ke korpus. Jika situs down saat demo, tunjukkan hasil scan dan job tarik yang telah tersimpan di riwayat database, atau demonstrasikan scanning terhadap folder lokal OneDrive.
3. **Batas 1 Worker Uvicorn untuk In-Process Background Tasks:**
   - *Risiko:* Menjalankan banyak crawling simultan pada 1 worker dapat membebani event loop.
   - *Mitigasi:* Tetap gunakan `UVICORN_WORKERS=1` sesuai rekomendasi Arsitektur Fase 1, serta terapkan `CRAWL_RATE_LIMIT_DELAY` wajar (1.0 detik).

---

## 8. Status Git & Tag Rilis

### `git log --oneline` (5 Commit Terakhir):
```text
f1d5f49 feat: kesiapan deploy produksi, hardening konfigurasi, demo seed/reset, dan runbook VPS
0bd893b fix(api): perbaiki konsistensi kontrak, enum docs, penamaan berkas failure, agregat dashboard, dan sanitasi smoke test
b6f36e9 fix(scan): perbaiki penghitung job tarik (pull_outcome) dan kesegaran sesi pull_progress
89077c3 docs: add Step 7 frontend changes, crawler adapter contract, README updates, and completion report
d872a70 test: add comprehensive test suite for crawler, URL guard, scan flow, push mode, and demo script
```

### Git Tag:
```text
v0.8.0-fase1-rc1
```

### Git Remote:
```text
origin  https://github.com/hero-capstone/hero-backend.git (fetch)
origin  https://github.com/hero-capstone/hero-backend.git (push)
```
