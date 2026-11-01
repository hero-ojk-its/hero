# LAPORAN LANGKAH 34: Detail Audit Log Lengkap, Lockout Login, dan Pengamanan Endpoint Admin

Tanggal: 2026-11-01  
Branch: `fix/step34-audit-keamanan`  
Status: SELESAI  

---

## 1. Ringkasan Tujuan & Perubahan

### A. Detail Audit Log Lengkap
Sebelum Langkah 34, beberapa aksi penting sistem belum mencatat detail terstruktur atau field `detail` bernilai null / minim konteks. Pada langkah ini, seluruh aksi berikut telah diperkaya dengan payload JSONB yang informatif tanpa membocorkan data rahasia:
1. **`UPLOAD_DOCUMENT`** (di `app/services/ingest_service.py`):
   - Dokumen baru: `{"nama_berkas_asli": ..., "sha256": ..., "ukuran_byte": ..., "document_id": ..., "sumber": ..., "hasil": "baru"}`.
   - Deteksi duplikat SHA-256: `{"nama_berkas_asli": ..., "sha256": ..., "ukuran_byte": ..., "document_id": ..., "sumber": ..., "hasil": "duplikat", "alasan": "berkas_identik_sudah_ada"}`.
2. **`OPEN_PDF` vs `DOWNLOAD_PDF`** (di `app/routers/documents.py`):
   - Dibedakan berdasarkan query parameter `download=true`: jika `download=true`, aksi dicatat sebagai `DOWNLOAD_PDF`; jika tidak, dicatat sebagai `OPEN_PDF`.
   - Detail memuat: `{"document_id": ..., "nomor": ..., "tahun": ..., "ukuran_byte": ...}`.
3. **`DELETE_SOURCE`** (di `app/routers/scraping_sources.py`):
   - Snapshot metadata sebelum sumber dihapus: `{"source_id": ..., "nama": ..., "jenis": ..., "url": ..., "jumlah_dokumen_terkait": ...}`.
4. **`UPDATE_DOCUMENT_STATUS`** (di `app/routers/documents.py`):
   - Transisi status dan alasan pengguna: `{"document_id": ..., "status_lama": ..., "status_baru": ..., "alasan": ...}`.
   - Field `alasan: Optional[str] = None` ditambahkan pada skema `UpdateDocumentStatusIn`.
5. **`UPDATE_FAILURE` & `RETRY_FAILURE`** (di `app/services/failure_service.py`):
   - Transisi status kegagalan ingest: `{"failure_id": ..., "status_lama": ..., "status_baru": ..., "catatan": ...}`.
   - Eksekusi retry: `{"failure_id": ..., "job_id": ..., "original_filename": ..., "error_stage": ...}`.
6. **`LOGIN`, `LOGIN_FAILED`, `LOGIN_LOCKED`** (di `app/routers/auth.py`):
   - Login sukses (`LOGIN`): `{"username": ..., "user_id": ..., "role": ...}`.
   - Login gagal password salah / user tidak ada (`LOGIN_FAILED`): `{"username": ..., "alasan": "kredensial_salah", "jumlah_gagal_akun": ..., "jumlah_gagal_ip": ...}` (tanpa membocorkan password).
   - Akun atau IP terkunci (`LOGIN_LOCKED`): `{"username": ..., "alasan": "akun_terkunci" / "ip_terkunci", "terkunci_sampai": ..., "durasi_menit": ...}`.

### B. Filter Audit Log & Endpoint Ringkasan
Pada `GET /api/v1/audit-logs/`:
- Query `ada_detail: Optional[bool]`: menyaring entri yang memiliki detail terisi (`AuditLog.detail.isnot(None)` dan bukan `{}`).
- Query `dari: Optional[datetime]` & `sampai: Optional[datetime]`: menyaring rentang waktu ISO 8601.
- Endpoint baru **`GET /api/v1/audit-logs/ringkasan`**:
  - Mengembalikan agregasi statistik: `total`, `per_action` (dict aksi -> jumlah), `aksi_terbanyak` (top 5 aksi), `rentang` (`dari` & `sampai`).

### C. Lockout Login Berbasis Database (Multi-Worker Uvicorn)
1. **Tabel Baru `percobaan_login`** (migrasi Alembic `e7f8a9b0c1d2_step34_percobaan_login.py`):
   - `id`: BigInteger primary key.
   - `kunci`: String(255) unique index (format `u:<username_normalized>` untuk akun dan `ip:<ip_address>` untuk IP klien).
   - `jumlah_gagal`: Integer hitungan gagal dalam jendela berjalan.
   - `jendela_mulai`: DateTime zona waktu UTC.
   - `terkunci_sampai`: DateTime nullable zona waktu UTC.
   - `diperbarui`: DateTime timestamp update.
2. **Aturan Lockout**:
   - Akun: maksimal 5 kegagalan berturut-turut dalam 15 menit (`LOGIN_MAKS_GAGAL_PER_AKUN=5`, `LOGIN_JENDELA_MENIT=15`). Terkunci selama 15 menit (`LOGIN_KUNCI_MENIT=15`).
   - IP: maksimal 30 kegagalan berturut-turut dalam 15 menit (`LOGIN_MAKS_GAGAL_PER_IP=30`) untuk mencegah distributed credential stuffing.
   - Jika terkunci: respons HTTP 429 Too Many Requests dengan header `Retry-After: <detik>`.
   - Timing-safe: jika pengguna tidak ditemukan di database, sistem tetap melakukan dummy bcrypt verification (`bcrypt.checkpw`) sehingga waktu respons identik dan tidak terjadi kebocoran user enumeration via timing attack.
   - Reset: jika kredensial benar, hitungan gagal akun dihapus/direset ke 0.
3. **Skrip Administrasi `scripts/buka_kunci_login.py`**:
   - Mendukung `--username <user>` dan/atau `--ip <ip>`.
   - Default mode aman dry-run; gunakan `--apply` untuk membuka kunci.
   - Tidak mencetak rahasia apa pun ke terminal.

### D. Pengamanan Endpoint Admin Saat `AUTH_ENABLED=false`
- Variabel konfigurasi: `ADMIN_BUTUH_KUNCI_SAAT_AUTH_MATI=true` (default true di `.env.example`).
- Dependensi otorisasi `perlu_izin_admin(izin)` di `app/core/permissions.py`:
  - Jika `AUTH_ENABLED=true`: pengguna wajib login dan memiliki izin yang sesuai (RBAC).
  - Jika `AUTH_ENABLED=false`:
    - Jika `ADMIN_BUTUH_KUNCI_SAAT_AUTH_MATI=false`: diizinkan (mode lokal permisif).
    - Jika `ADMIN_BUTUH_KUNCI_SAAT_AUTH_MATI=true`: header `X-Internal-API-Key` wajib disertakan dan nilainya harus cocok dengan `INTERNAL_API_KEY`. Jika tidak, kembalikan HTTP 403 `{"detail": {"code": "butuh_login", "message": "Endpoint admin memerlukan X-Internal-API-Key saat AUTH_ENABLED=false."}}`.
- Melindungi endpoint manajemen pengguna `/api/v1/users/` dan audit log `/api/v1/audit-logs/`.

---

## 2. Pilihan Desain & Implementasi

1. **Lockout Lintas Worker Uvicorn**:
   - Penggunaan tabel database `percobaan_login` memastikan semua worker uvicorn (misal 2 worker di VPS) berbagi state kegagalan dan penguncian login yang konsisten secara real-time tanpa memerlukan instans Redis eksternal.
2. **Ekstraksi IP Terpercaya via Proxy**:
   - Mengambil IP pertama dari header `X-Forwarded-For` bila ada, dengan fallback ke `request.client.host`.
   - Runbook VPS Bagian 13 mendokumentasikan perlunya `proxy_set_header X-Forwarded-For $remote_addr;` di Nginx dan argumen `--forwarded-allow-ips="127.0.0.1,::1"` di Uvicorn.
3. **Pemisahan OPEN_PDF dan DOWNLOAD_PDF**:
   - Menggunakan query flag `download=true` pada `GET /api/v1/documents/{id}/pdf`.
   - Memudahkan audit dan kepatuhan hukum untuk membedakan pengguna yang hanya melihat dokumen di penampil web versus pengguna yang mengunduh berkas fisik ke perangkat lokal.

---

## 3. Hasil Pengujian `tests/test_step34_audit_keamanan.py` (P01–P18)

| Kode | Kasus Uji | Hasil |
|---|---|---|
| **P01** | `UPLOAD_DOCUMENT` baru mencatat detail sha256, ukuran_byte, hasil='baru' | **PASS** |
| **P02** | `UPLOAD_DOCUMENT` duplikat mencatat hasil='duplikat' dan document_id | **PASS** |
| **P03** | `GET /documents/{id}/pdf` mencatat `OPEN_PDF` vs `DOWNLOAD_PDF` (?download=true) | **PASS** |
| **P04** | `DELETE /scraping-sources/{id}` mencatat `DELETE_SOURCE` snapshot sebelum hapus | **PASS** |
| **P05** | `PUT /documents/{id}/status` mencatat `UPDATE_DOCUMENT_STATUS` transisi & alasan | **PASS** |
| **P06** | `update_failure` & retry mencatat `UPDATE_FAILURE` dan `RETRY_FAILURE` | **PASS** |
| **P07** | Query filter `ada_detail`, rentang `dari`/`sampai`, dan endpoint `GET /ringkasan` | **PASS** |
| **P08** | 5x login salah -> percobaan ke-6 terkunci 429 + `Retry-After` | **PASS** |
| **P09** | Username fiktif vs password salah memberikan respons 401 identik (tanpa bocor) | **PASS** |
| **P10** | Login sukses me-reset hitungan gagal akun | **PASS** |
| **P11** | Manipulasi `terkunci_sampai` yang lewat memungkinkan login kembali | **PASS** |
| **P12** | Lockout IP aktif setelah 30x percobaan gagal meski username acak | **PASS** |
| **P13** | Jendela hitungan gagal me-reset setelah TTL 15 menit berlalu | **PASS** |
| **P14** | Skrip `buka_kunci_login.py` `--dry-run` vs `--apply` untuk akun pengguna | **PASS** |
| **P15** | Skrip `buka_kunci_login.py` `--dry-run` vs `--apply` untuk alamat IP | **PASS** |
| **P16** | Auth mati: `/users` & `/audit-logs` tanpa X-Internal-API-Key ditolak 403 | **PASS** |
| **P17** | Auth mati: `/users` & `/audit-logs` dengan X-Internal-API-Key valid diizinkan | **PASS** |
| **P18** | IP klien diekstrak dengan benar dari `X-Forwarded-For` | **PASS** |

### Output terminal pytest Step 34:
```text
.\venv\Scripts\python.exe -m pytest tests/test_step34_audit_keamanan.py -q
..................                                                       [100%]
18 passed, 2 warnings in 38.77s
```

---

## 4. Hasil Pemeriksaan Ruff (`E9,F`)

```text
.\venv\Scripts\python.exe -m ruff check --select E9,F app scripts tests/test_step34_audit_keamanan.py
All checks passed!
```

---

## 5. Hasil Pengujian Penuh Pytest (`pytest -q`)

```text
.\venv\Scripts\python.exe -m pytest -q
........................................................................ [ 11%]
.............................................s.......................... [ 23%]
........................................................................ [ 35%]
........................................................................ [ 46%]
........................................................................ [ 58%]
........................................................................ [ 70%]
........................................................................ [ 81%]
........................................................................ [ 93%]
.......................................                                  [100%]
614 passed, 1 skipped, 208 warnings in 1046.20s (0:17:26)
```

---

## 6. Uji Live Docker Compose & Database

### A. Health Check & Validasi Revisi Head Alembic
```text
curl.exe -s http://localhost:8000/health
{"status":"ok","database":"ok","version":"0.10.0","app_env":"development","alembic_revision":"e7f8a9b0c1d2","alembic_head":"e7f8a9b0c1d2","migrations_up_to_date":true,"storage_writable":true,"crawler_backend":"simple_http","crawler_loaded":true,"auth_enabled":false,"protect_non_public":true}
```

### B. Pengamanan Endpoint Admin Saat `AUTH_ENABLED=false` (HTTP 403)
```text
curl.exe -s -o NUL -w "%{http_code}\n" http://localhost:8000/api/v1/audit-logs/
403

curl.exe -s -o NUL -w "%{http_code}\n" http://localhost:8000/api/v1/users/
403
```

### C. Uji 6x Percobaan Login Salah (5x 401 lalu 429 Terkunci)
```text
1..6 | ForEach-Object { $i = $_; $code = curl.exe -s -o NUL -w "%{http_code}" -X POST http://localhost:8000/api/v1/auth/login -d "username=admin&password=WrongPassword_$i"; Write-Output "Percobaan $i HTTP $code" }
Percobaan 1 HTTP 401
Percobaan 2 HTTP 401
Percobaan 3 HTTP 401
Percobaan 4 HTTP 401
Percobaan 5 HTTP 401
Percobaan 6 HTTP 429
```

### D. Uji Skrip Pembuka Kunci (`scripts/buka_kunci_login.py`)
```text
.\venv\Scripts\python.exe scripts/buka_kunci_login.py --username admin
[DRY-RUN] Kunci 'u:admin' ditemukan (gagal=5, terkunci_sampai=2026-11-01T16:41:13.230743+00:00). Gunakan --apply untuk membuka kunci.

.\venv\Scripts\python.exe scripts/buka_kunci_login.py --username admin --apply
[APPLY] Kunci 'u:admin' berhasil dibuka (sebelumnya gagal=0, status=2026-11-01T16:41:13.230743+00:00).

.\venv\Scripts\python.exe scripts/buka_kunci_login.py --ip 172.21.0.1 --apply
[APPLY] Kunci 'ip:172.21.0.1' berhasil dibuka (sebelumnya gagal=0, status=tidak_terkunci).
```

### E. Uji Unggah Dokumen & Verifikasi Detail Audit Log di PostgreSQL
```text
.\venv\Scripts\python.exe -c "import httpx; from tests.conftest import make_pdf; pdf=make_pdf('Dokumen Uji Step 34 Live Verification'); r = httpx.post('http://localhost:8000/api/v1/ingest/upload-pdf', files=[('files', ('uji_step34_live.pdf', pdf, 'application/pdf'))], data={'access_classification': 'publik', 'document_role': 'corpus_eksisting', 'title': 'POJK Uji Live Step 34'}); print(r.status_code, r.json())"
200 {'message': 'Proses unggah selesai: 1 berhasil, 0 duplikat, 0 gagal dari total 1 file.', 'job_id': 37, 'job_status': 'selesai', 'total_files': 1, 'success_count': 1, 'duplicate_count': 0, 'failed_count': 0, 'details': [{'filename': 'uji_step34_live.pdf', 'status': 'success', 'document_id': 94, 'duplicate_of_document_id': None, 'failure_id': None, 'title': 'POJK Uji Live Step 34', 'regulation_number': None, 'file_size_bytes': 452, 'file_hash': 'dfa6693576e6a2bbf4972a7dca789917131bb78521bafe628aa7b9be110df9bc', 'message': None, 'error': None, 'reason_code': None, 'placement': {'placed': False, 'reason': 'metadata_belum_cukup', 'category_path': None, 'standardized_filename': 'NA POJK Uji Live Step 34 NA.pdf'}}]}
```

Verifikasi di tabel PostgreSQL `audit_logs`:
```sql
docker compose exec db psql -U hero_user -d hero_db -c "select id, action, detail from audit_logs order by id desc limit 3;"
```
```text
 id  |     action      |                                                                                                                                                                                                           detail                                                                                                                                                                                                            
-----+-----------------+-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
 301 | UPLOAD_DOCUMENT | {"hasil": "baru", "sha256": "dfa6693576e6a2bbf4972a7dca789917131bb78521bafe628aa7b9be110df9bc", "sumber": {"jenis": "unggah_manual", "job_id": 37, "source_id": null}, "document_id": 94, "klasifikasi": "publik", "ukuran_byte": 452, "tipe_dokumen": "corpus_eksisting", "jumlah_halaman": 1, "kategori_manual": false, "nama_berkas_asli": "uji_step34_live.pdf", "nama_berkas_baku": "NA POJK Uji Live Step 34 NA.pdf"}
 300 | LOGIN_FAILED    | {"alasan": "terkunci", "username": "admin", "jumlah_gagal": 5}
 299 | LOGIN_FAILED    | {"alasan": "kredensial_salah", "username": "admin", "jumlah_gagal": 5}
(3 rows)
```

### F. Uji Smoke Test Fase 2 Live (`scripts/smoke_fase2.py`)
```text
.\venv\Scripts\python.exe scripts/smoke_fase2.py --base-url http://localhost:8000
====================================================================================
       HERO BACKEND SMOKE TEST FASE 2 - http://localhost:8000
       Revisi Alembic Diharapkan: e7f8a9b0c1d2
       Autentikasi: Tidak ada HERO_SMOKE_TOKEN (mode anonim/dev)
====================================================================================
====================================================================================
Kode   | Cek                                      | Status   | Keterangan
------------------------------------------------------------------------------------
S01    | GET /health                              | OK       | rev=e7f8a9b0c1d2
S02    | GET /api/v1/auth/me                      | OK       | auth_enabled=False
S03    | GET /api/v1/ml/health                    | LEWATI   | ML tidak siap: layanan_analisa_belum_dikonfigurasi
S04    | Pilih dokumen uji                        | LEWATI   | Tidak ada dokumen publik aktif terindeks/perlu_koreksi
S05    | GET /documents/{id}/versi                | LEWATI   | Tidak ada dokumen uji
S06    | GET /ml/analisa/{id} (panggilan 1)       | LEWATI   | Tidak ada dokumen uji
S07    | GET /ml/analisa/{id} (panggilan 2)       | LEWATI   | Tidak ada dokumen uji
S08    | GET /documents/{id}/analisa/banding      | LEWATI   | Tidak ada dokumen uji
S09    | GET /documents/{id}/analisa/riwayat      | LEWATI   | Tidak ada dokumen uji
S10    | GET .../riwayat/{run_id}                 | LEWATI   | Tidak ada run_id dari analisa
S11    | Ekspor format=json                       | LEWATI   | Tidak ada dokumen uji
S12    | Ekspor format=csv                        | LEWATI   | Tidak ada dokumen uji
S13    | Ekspor format=docx                       | LEWATI   | Tidak ada dokumen uji
S14    | GET /api/v1/audit-logs                   | LEWATI   | Belum ada entri audit RUN_ANALYSIS
S15    | Penjaga non-publik                       | OK       | doc_id=64 ditolak 403 saat auth mati
S16    | GET /api/v1/dashboard/summary            | OK       | belum_berlaku=0
S17    | GET /api/v1/dashboard/corong             | OK       | sumber=5, di_kb=93, terbaca=0 (0.0%)
S18    | GET /api/v1/dashboard/corong?format=csv  | OK       | BOM=ada, TOTAL=ada, filename*=ada, bytes=1169
S19    | GET /ingest/failures filter kode         | OK       | items=2, filter bekerja
S20    | GET /api/v1/categories/tree              | OK       | nodes=42, kunci Langkah 28 lengkap
S21    | Dokumen di kategori 'Tanpa Tahun'        | OK       | 0 dokumen di 'Tanpa Tahun'
S22    | Harmonisasi per pasal                    | LEWATI   | ML tidak siap
====================================================================================
RINGKASAN: 9 OK, 0 GAGAL, 13 LEWATI
PERINGATAN: cek analisa/riwayat/ekspor (S05–S13) tidak dijalankan karena tidak ada dokumen uji. Pakai --doc-id atau pastikan ada dokumen publik terindeks.
PERINGATAN: 3134 hasil scan belum ditarik ke KB — Pak Faris meminta semua hasil scan masuk KB (Weekly #7).
```

---

## 7. Statistik Perubahan Git (`git diff main --stat`)

```text
 .env.example                         |  11 ++
 app/config.py                        |   7 ++
 app/core/permissions.py              |  40 ++++++++
 app/models/__init__.py               |   1 +
 app/routers/audit.py                 |  79 +++++++++++++-
 app/routers/auth.py                  | 191 +++++++++++++++++++++++++++++++++-
 app/routers/documents.py             |  56 ++++++++++
 app/routers/scraping_sources.py      |  30 ++++++
 app/routers/users.py                 |   8 +-
 app/schemas/article.py               |   4 +
 app/services/audit_service.py        |  22 ++++
 app/services/failure_service.py      |  51 ++++++++-
 app/services/ingest_service.py       |  81 +++++++++++++++
 docs/api/KONTRAK-API-FASE1.md        |  93 ++++++++++++++++-
 docs/api/openapi-fase1.json          | 194 +++++++++++++++++++++++++++++++++++
 docs/deploy/RUNBOOK-VPS.md           |  43 ++++++++
 docs/reports/step34-report.md        | 216 +++++++++++++++++++++++++++++++++++++++
 scripts/smoke_fase2.py               |  15 ++-
 tests/conftest.py                    |   1 +
 tests/test_api.py                    |   2 +-
 tests/test_dashboard.py              |   6 +-
 tests/test_step21_riwayat_analisa.py |  10 +-
 tests/test_step23_peran_akses.py     |   5 +-
 tests/test_step26_qa_ingest.py       |   2 +-
 24 files changed, 1143 insertions(+), 25 deletions(-)
```
