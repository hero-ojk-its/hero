# Laporan Implementasi HERO Backend — Langkah 23 (US-01 #32)
## Manajemen Pengguna & Otorisasi Berbasis Peran (RBAC)

**Tanggal:** 19 Oktober 2026  
**Branch:** `feat/step23-peran-akses`  
**Commit Target:** `feat: peran pengguna dan otorisasi berbasis peran (US-01)`

---

## 1. Ringkasan Eksekutif

Langkah 23 mengimplementasikan sistem manajemen pengguna dan otorisasi berbasis peran (Role-Based Access Control / RBAC) terpusat untuk memenuhi kriteria penerimaan **US-01 #32**:
1. Empat peran pengguna terdefinisi: `analis`, `admin_kb`, `admin_sistem`, dan `pilot_user`.
2. Matriks perizinan terpusat didefinisikan dalam satu berkas konfigurasi `app/core/permissions.py` via `HAK_AKSES_PERAN`. Router dan endpoint dilarang memeriksa nama peran secara langsung dan hanya memeriksa izin fitur melalui dependensi `perlu_izin(...)`.
3. Pemeriksaan dokumen non-publik yang sebelumnya tersebar di 13 lokasi refaktor sepenuhnya menggunakan helper `boleh_baca_nonpublik(user)` dan `check_non_public_access(doc, user)`.
4. Endpoint manajemen akun pengguna baru (`/api/v1/users`) untuk operasi CRUD pengguna dengan perlindungan terhadap penghapusan/penonaktifan Admin Sistem aktif terakhir (`admin_terakhir`) dan modifikasi peran diri sendiri (`ubah_diri_sendiri`).
5. Endpoint `/api/v1/auth/me` untuk profil pengguna aktif dan daftar izin matriks yang dapat dikonsumsi frontend untuk render navigasi/menu sesuai peran.
6. Skrip administratif mandiri `scripts/create_user.py` yang idempoten untuk seeding Admin Sistem pertama di lingkungan VPS/produksi tanpa mengekspos password.
7. **Prinsip Nol Regresi:** Selama `AUTH_ENABLED=false` (default pengujian dan staging), seluruh endpoint tetap terbuka dan perilaku sistem tidak berubah sedikit pun.

---

## 2. Catatan untuk Frontend

1. **Header Autentikasi:**
   - Ketika `AUTH_ENABLED=true`, seluruh request ke endpoint yang dilindungi wajib menyertakan header:
     ```http
     Authorization: Bearer <access_token>
     ```
2. **Menu Dinamis Sesuai Peran via `/api/v1/auth/me`:**
   - Frontend dapat memanggil `GET /api/v1/auth/me` setelah login:
     - Jika auth mati: mengembalikan `{"auth_enabled": false}`.
     - Jika auth aktif: mengembalikan data profil (`username`, `nama_lengkap`, `unit_kerja`, `role`) serta daftar string `izin` dari matriks (contoh: `["KB_BACA", "KB_BACA_NONPUBLIK", "DOKUMEN_UNGGAH", ...]`).
   - Gunakan array `izin` ini untuk menentukan visibilitas tombol/menu daripada memeriksa nama peran secara langsung.
3. **Penanganan Galat 401 dan 403:**
   - **401 Unauthorized:** Token tidak valid, kedaluwarsa, atau akun dinonaktifkan (`"Akun pengguna tidak aktif"`). Frontend sebaiknya menghapus token lokal dan mengarahkan pengguna ke halaman login.
   - **403 Forbidden (`akses_ditolak`):**
     Payload galat memiliki format terstruktur:
     ```json
     {
       "detail": {
         "code": "akses_ditolak",
         "izin": "AUDIT_BACA",
         "peran": "analis"
       }
     }
     ```
     Frontend dapat menampilkan banner atau dialog izin akses sesuai kode `izin` terkait.

---

## 3. Catatan Deploy

1. **Migrasi Peran & Profil Pengguna (`f2a3b4c5d6e7`):**
   - Jalankan migrasi alembic sebelum aplikasi aktif:
     ```bash
     alembic upgrade head
     ```
   - Migrasi akan otomatis mengonversi role pengguna lama di database: `admin` -> `admin_sistem` dan `user` -> `analis`, menambahkan kolom `nama_lengkap` dan `unit_kerja`, serta memasang check constraint `ck_users_role`.
2. **Pembuatan Admin Sistem Pertama:**
   - **PENTING:** Buat akun Admin Sistem pertama menggunakan skrip sebelum mengaktifkan `AUTH_ENABLED=true`:
     ```bash
     HERO_NEW_USER_PASSWORD="PasswordKuatMinimal12Karakter!" python scripts/create_user.py --username admin_utama --role admin_sistem --nama "Admin Utama HERO" --unit "IT Governance"
     ```
   - Skrip bersifat idempoten: jika username sudah terdaftar, eksekusi selesai tanpa mengubah apa pun. Password tidak pernah dicetak ke terminal atau log.
3. **Aktivasi Autentikasi (`AUTH_ENABLED`):**
   - Mengaktifkan autentikasi adalah keputusan terpisah. Pastikan admin pertama telah dibuat sebelum menyetel `AUTH_ENABLED=true` di lingkungan produksi.

---

## 4. Daftar 13 Lokasi Pemeriksaan Non-Publik yang Diganti

Seluruh logika pengecekan dokumen non-publik kini menggunakan helper `boleh_baca_nonpublik(user)` dan `check_non_public_access(doc, user)`:

| # | Berkas & Lokasi Baris | Fungsi / Endpoint | Deskripsi Penggantian |
|---|---|---|---|
| 1 | `app/services/version_service.py:55` | `is_doc_accessible` | Menggunakan `boleh_baca_nonpublik(user)` untuk relasi dokumen non-publik |
| 2 | `app/services/search_service.py:120` | `SearchService.search` | `is_protect_non_public = not boleh_baca_nonpublik(user)` untuk filter SQL |
| 3 | `app/services/search_service.py:284` | Headline masking | Masking cuplikan headline jika `not boleh_baca_nonpublik(user)` |
| 4 | `app/services/search_service.py:327` | Flag `is_restricted` | Penandaan batasan akses dokumen jika `not boleh_baca_nonpublik(user)` |
| 5 | `app/routers/ml_gateway.py:49` | `allowed_document_ids` | Memfilter id dokumen non-publik jika `not boleh_baca_nonpublik(user)` |
| 6 | `app/routers/ml_gateway.py:71` | `check_document_access` | Memanggil `check_non_public_access(doc, user)` untuk analisa & harmonisasi |
| 7 | `app/routers/ml_gateway.py:1074` | `get_ml_pasal_mirip` | Pemeriksaan klasifikasi non-publik menggunakan `boleh_baca_nonpublik(current_user)` |
| 8 | `app/routers/documents.py:539` | `get_document_pdf` | Memanggil `check_non_public_access(doc, current_user)` |
| 9 | `app/routers/documents.py:607` | `get_document_text` | Memanggil `check_non_public_access(doc, current_user)` |
| 10 | `app/routers/documents.py:1241` | `get_document_version` | Memanggil `check_non_public_access(doc, current_user)` |
| 11 | `app/routers/documents.py:1279` | `get_document_analysis_comparison` | Memanggil `check_non_public_access(doc, current_user)` & `allowed_document_ids(db, user=current_user)` |
| 12 | `app/routers/documents.py:1323` | `get_document_analysis_runs` | Memanggil `check_non_public_access(doc, current_user)` |
| 13 | `app/routers/documents.py:1363` | `get_document_analysis_run_detail` | Memanggil `check_non_public_access(doc, current_user)` & `allowed_document_ids(db, user=current_user)` |
| + | `app/routers/documents.py:1421` | `export_document_analysis` | Memanggil `check_non_public_access(doc, current_user)` & `allowed_document_ids(db, user=current_user)` |

---

## 5. Endpoint yang Tidak Tercantum di Tabel Bagian 4

Semua endpoint bisnis telah terpetakan sesuai matriks hak akses Bagian 4 instruksi:
- `POST /api/v1/auth/login`: Publik (otentikasi).
- `GET /api/v1/auth/me`: Publik saat auth nonaktif, memerlukan token aktif saat auth aktif (tanpa batasan peran tertentu).
- `GET /health`: Publik (health check & readiness probe).
- Seluruh endpoint `/api/v1/internal/*`: Dilindungi oleh kunci API worker (`X-Internal-API-Key`).
Tidak ada endpoint bisnis lain yang tidak terpetakan atau ditebak izinnya.

---

## 6. Tabel Kasus Uji P01–P17 (`tests/test_step23_peran_akses.py`)

| # | Kasus Uji | Ekspektasi | Hasil |
|---|---|---|---|
| P01 | Migrasi: pengguna lama `admin`/`user` | Menjadi `admin_sistem`/`analis` via ORM model validator & alembic upgrade | **PASSED** |
| P02 | Matriks terparametrisasi (11 izin x 4 peran) | 2xx/4xx bila peran punya izin; 403 `akses_ditolak` bila tidak | **PASSED** (11/11 izin) |
| P03 | TC-57: Analis mengakses `GET /audit-logs/` | 403 `akses_ditolak` (izin: `AUDIT_BACA`) | **PASSED** |
| P04 | Tanpa token, auth hidup -> `GET /documents/` | 401 Unauthorized | **PASSED** |
| P05 | Token valid tetapi akun lalu dinonaktifkan di DB | 401 `"Akun pengguna tidak aktif"` | **PASSED** |
| P06 | Peran diubah di DB (`analis` -> `pilot_user`), token lama dipakai lagi | Izin langsung mengikuti peran baru tanpa login ulang | **PASSED** |
| P07 | Dokumen non-publik saat auth hidup | Analis -> 200; Admin Sistem -> 403 `KB_BACA_NONPUBLIK` | **PASSED** |
| P08 | Dokumen non-publik saat auth mati | 403 pesan lama `"Dokumen non-publik hanya dapat dibuka setelah login diaktifkan."` | **PASSED** |
| P09 | Auth mati: `SUMBER_KELOLA`, `AUDIT_BACA`, `PENGGUNA_KELOLA` tanpa token | Tidak 401/403 (perilaku lama dipertahankan) | **PASSED** |
| P10 | `POST /users` oleh Admin Sistem | 201 Created; tanpa hash password; audit `CREATE_USER` tanpa password | **PASSED** |
| P11 | `POST /users` username ganda / password < 12 | 409 `username_terdaftar` / 422 Unprocessable Entity | **PASSED** |
| P12 | Menonaktifkan Admin Sistem aktif terakhir | 409 `admin_terakhir` | **PASSED** |
| P13 | Admin Sistem menurunkan peran akun sendiri | 409 `ubah_diri_sendiri` | **PASSED** |
| P14 | `GET /auth/me` sebagai Analis | `role=analis`, daftar `izin` persis sama dengan matriks hak akses | **PASSED** |
| P15 | `allowed_document_ids` saat auth hidup, Admin KB | Memuat dokumen non-publik (karena punya `KB_BACA_NONPUBLIK`) | **PASSED** |
| P16 | `/internal/*` dengan API key, auth hidup, tanpa token pengguna | 404 (bukan 401 unauthorized auth pengguna) | **PASSED** |
| P17 | `create_user.py` dua kali dengan username sama | Run kedua idempoten; password tidak pernah tercetak di output | **PASSED** |

---

## 7. Bukti Eksekusi Terminal (Raw Output)

### A. Linting Ruff
```
All checks passed!
```

### B. Pytest Berkas Langkah 23 (`tests/test_step23_peran_akses.py`)
```
============================= test session starts =============================
platform win32 -- Python 3.13.7, pytest-9.1.1, pluggy-1.6.0 -- C:\Hero\hero-backend\venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Hero\hero-backend
plugins: anyio-4.15.1
collecting ... collected 27 items

tests/test_step23_peran_akses.py::test_p01_role_mapping_migration PASSED [  3%]
tests/test_step23_peran_akses.py::test_p02_matrix_access_control[KB_BACA-GET-/api/v1/categories/] PASSED [  7%]
tests/test_step23_peran_akses.py::test_p02_matrix_access_control[DOKUMEN_UNGGAH-POST-/api/v1/ingest/upload-pdf] PASSED [ 11%]
tests/test_step23_peran_akses.py::test_p02_matrix_access_control[METADATA_KOREKSI-GET-/api/v1/documents/needs-review] PASSED [ 14%]
tests/test_step23_peran_akses.py::test_p02_matrix_access_control[KEGAGALAN_KELOLA-GET-/api/v1/ingest/failures] PASSED [ 18%]
tests/test_step23_peran_akses.py::test_p02_matrix_access_control[ANALISA_JALANKAN-GET-/api/v1/documents/{doc_id}/analisa/banding] PASSED [ 22%]
tests/test_step23_peran_akses.py::test_p02_matrix_access_control[ANALISA_EKSPOR-GET-/api/v1/documents/{doc_id}/analisa/ekspor] PASSED [ 25%]
tests/test_step23_peran_akses.py::test_p02_matrix_access_control[SUMBER_KELOLA-GET-/api/v1/scraping-sources/] PASSED [ 29%]
tests/test_step23_peran_akses.py::test_p02_matrix_access_control[KB_KELOLA-POST-/api/v1/documents/place-pending] PASSED [ 33%]
tests/test_step23_peran_akses.py::test_p02_matrix_access_control[STATUS_UBAH-PUT-/api/v1/documents/{doc_id}/status] PASSED [ 37%]
tests/test_step23_peran_akses.py::test_p02_matrix_access_control[AUDIT_BACA-GET-/api/v1/audit-logs/] PASSED [ 40%]
tests/test_step23_peran_akses.py::test_p02_matrix_access_control[PENGGUNA_KELOLA-GET-/api/v1/users/] PASSED [ 44%]
tests/test_step23_peran_akses.py::test_p03_tc57_analis_cannot_read_audit_logs PASSED [ 48%]
tests/test_step23_peran_akses.py::test_p04_unauthenticated_request_rejected PASSED [ 51%]
tests/test_step23_peran_akses.py::test_p05_token_valid_but_account_deactivated PASSED [ 55%]
tests/test_step23_peran_akses.py::test_p06_role_change_immediately_effective PASSED [ 59%]
tests/test_step23_peran_akses.py::test_p07_non_public_document_access_auth_enabled PASSED [ 62%]
tests/test_step23_peran_akses.py::test_p08_non_public_document_access_auth_disabled PASSED [ 66%]
tests/test_step23_peran_akses.py::test_p09_auth_disabled_legacy_behavior PASSED [ 70%]
tests/test_step23_peran_akses.py::test_p10_create_user_by_admin PASSED   [ 74%]
tests/test_step23_peran_akses.py::test_p11_create_user_validation_and_duplicate PASSED [ 77%]
tests/test_step23_peran_akses.py::test_p12_cannot_deactivate_last_active_admin PASSED [ 81%]
tests/test_step23_peran_akses.py::test_p13_admin_cannot_demote_self PASSED [ 85%]
tests/test_step23_peran_akses.py::test_p14_get_auth_me_analis PASSED     [ 88%]
tests/test_step23_peran_akses.py::test_p15_allowed_document_ids_includes_non_public PASSED [ 92%]
tests/test_step23_peran_akses.py::test_p16_internal_endpoint_works_with_api_key PASSED [ 96%]
tests/test_step23_peran_akses.py::test_p17_create_user_script_idempotent PASSED [100%]

======================= 27 passed, 2 warnings in 55.63s =======================
```

### C. Seluruh Suite Pytest (Regresi & Kompatibilitas)
```
434 passed, 1 skipped, 162 warnings in 421.85s (0:07:01)
```

### D. Uji Live Docker
```powershell
docker compose up -d --build backend
Start-Sleep -Seconds 20
curl.exe -s http://localhost:8000/health
curl.exe -s http://localhost:8000/api/v1/auth/me
curl.exe -s -o NUL -w "%{http_code}" http://localhost:8000/api/v1/scraping-sources/
```

**Output Terminal:**
```json
{"status":"ok","database":"ok","version":"0.10.0","app_env":"development","alembic_revision":"f2a3b4c5d6e7","alembic_head":"f2a3b4c5d6e7","migrations_up_to_date":true,"storage_writable":true,"crawler_backend":"simple_http","crawler_loaded":true,"auth_enabled":false,"protect_non_public":true}
{"auth_enabled":false}
200
```

### E. Git Diff Main Stat
```
 app/main.py                     |   2 +
 app/models/user.py              |  37 ++-
 app/routers/audit.py            |   4 +-
 app/routers/auth.py             |  48 ++--
 app/routers/categories.py       |  20 +-
 app/routers/dashboard.py        |   7 +-
 app/routers/documents.py        |  88 +++----
 app/routers/ingest.py           |  20 +-
 app/routers/ml_gateway.py       |  59 ++---
 app/routers/naming.py           |   7 +-
 app/routers/scans.py            |   7 +-
 app/routers/scraping_sources.py |   3 +-
 app/services/audit_service.py   |   2 +
 app/services/search_service.py  |   6 +-
 app/services/version_service.py |  12 +-
 docs/api/KONTRAK-API-FASE1.md   | 165 +++++++++++++
 docs/api/openapi-fase1.json     | 506 +++++++++++++++++++++++++++++++++++++++-
 17 files changed, 856 insertions(+), 137 deletions(-)
```

### F. Git Log -3
```
2a01675 feat: Langkah 22 ekspor hasil analisa docx/csv/json (US-40)
080270b fix(step22): rujukan pasal tidak ganda, pengekspor dari pengguna aktif, nama berkas ASCII
576614e feat: ekspor hasil analisa docx/csv/json (US-40)
```

### G. Git Status Short
```
 M app/main.py
 M app/models/user.py
 M app/routers/audit.py
 M app/routers/auth.py
 M app/routers/categories.py
 M app/routers/dashboard.py
 M app/routers/documents.py
 M app/routers/ingest.py
 M app/routers/ml_gateway.py
 M app/routers/naming.py
 M app/routers/scans.py
 M app/routers/scraping_sources.py
 M app/services/audit_service.py
 M app/services/search_service.py
 M app/services/version_service.py
 M docs/api/KONTRAK-API-FASE1.md
 M docs/api/openapi-fase1.json
?? alembic/versions/f2a3b4c5d6e7_step23_user_roles_and_profile.py
?? app/core/
?? app/routers/users.py
?? app/schemas/user.py
?? docs/reports/step23-report.md
?? scripts/create_user.py
?? tests/test_step23_peran_akses.py
```
