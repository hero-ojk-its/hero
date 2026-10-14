# LAPORAN LANGKAH 17: Cek Duplikat Identitas (Judul + Nomor Peraturan) & Perbaikan Tes docs/api

**Branch:** `feat/step17-duplikat-identitas`  
**Tanggal:** 14 Oktober 2026  
**Status:** SELESAI  

---

## 1. Ringkasan Perubahan

### Bagian A — Perbaikan Tes docs/api
- Menambahkan parameter `--output-dir` pada `scripts/build_api_contract.py` (dengan bawaan tetap ke `docs/api/` untuk eksekusi manual).
- Memperbarui fixture `test_c01_contract_builder_idempotent` pada `tests/test_naming_step9.py` agar mengarahkan output kedua kali eksekusi builder ke `tmp_path / "api"`, sehingga pengujian tidak lagi memodifikasi `docs/api/KONTRAK-API-FASE1.md`, `openapi-fase1.json`, maupun `hero-fase1.http`.
- Commit terpisah (A): `test: jangan menulis docs/api saat menjalankan tes`.

### Bagian B — Cek Duplikat Identitas Regulasi
1. **Migrasi Database (`a7b8c9d0e1f2_step17_duplicate_identity.py`)**:
   - Menambahkan kolom `identity_key` (`String(120)`, nullable, indexed) pada tabel `documents`.
   - Menambahkan kolom `page_count` (`Integer`, nullable) pada tabel `documents`.
   - Menambahkan kolom `duplicate_of_id` (`Integer`, FK `documents.id` ON DELETE SET NULL, indexed) pada tabel `documents`.
   - Mendukung `upgrade` dan `downgrade` penuh.
2. **Model & Layanan**:
   - `app/models/document.py`: Menambahkan field `identity_key`, `page_count`, `duplicate_of_id`, dan relasi `duplicate_of`.
   - `app/services/identity_service.py`: Menambahkan `fallback_identity_key(regulation_type, regulation_number, regulation_year)` untuk OJK (`POJK`, `SEOJK`, `PADK`, `SEDK`, `PDK`, `KDK`) yang mengekstrak nomor awal dan tahun regulasi kanonik (`JENIS|NOMOR|TAHUN`).
   - `app/services/audit_service.py`: Menambahkan konstanta aksi audit `DUPLICATE_IDENTITY_DETECTED`.
   - `app/services/duplicate_service.py`: Mengimplementasikan `compare_docs` dan `check_identity_duplicate`. Logika penentuan pemenang:
     1. `page_count` lebih besar (bila keduanya diketahui);
     2. `file_size_bytes` lebih besar;
     3. `id` lebih kecil (yang lebih dulu ada).
     Pengecualian: Dokumen yang pernah menjadi duplikat lalu diaktifkan kembali secara manual (`duplicate_of_id is not None and is_active is True`) dilindungi dari penonaktifan otomatis ulang.
     Yang kalah dinonaktifkan (`is_active = false`, `duplicate_of_id = id_pemenang`, `deactivated_reason` diawali `duplikat_identitas`).
3. **Endpoint & Integrasi**:
   - `PATCH /api/v1/internal/documents/{id}/extraction`: Menerima `kunci_identitas` (alias `identity_key`) dan `jumlah_halaman` (alias `page_count`). Jika `kunci_identitas` kosong, otomatis menggunakan `fallback_identity_key`. Menjalankan cek duplikat dalam transaksi tersendiri; jika gagal tidak menggagalkan respons PATCH (tetap 200). Respons 200 menyertakan kolom `"duplikat"`.
   - `PATCH /api/v1/internal/documents/identity`: Endpoint batch isi-ulang maks 500 item `{document_id, kunci_identitas?, jumlah_halaman?}`. Mengembalikan `{updated, not_found, duplicates}`.
   - `GET /api/v1/documents/`: Menerima filter opsional `duplikat=true/false` (bekerja dengan `include_inactive=true`). Respons menyertakan `identity_key`, `page_count`, `duplicate_of_id`.
   - `GET /api/v1/documents/{id}`: Menyertakan `identity_key`, `page_count`, `duplicate_of_id`.
   - `GET /api/v1/dashboard/summary`: Menyertakan `kb.duplicate_documents`.
4. **Skrip Backfill CLI**:
   - `scripts/backfill_identity.py [--dry-run | --apply]`: Mengisi `identity_key` dengan cadangan dan melaporkan/menangani pasangan duplikat. Bawaan adalah `--dry-run`.
5. **Dokumentasi API**:
   - Diperbarui di `docs/api/KONTRAK-API-FASE1.md` (§9.5) dan snapshot `docs/api/openapi-fase1.json` dibangkitkan ulang tanpa memuat path lokal pengembang.

---

## 2. Catatan untuk Lapisan Data (Data/ML)

1. **Pengiriman Kunci Identitas dan Jumlah Halaman**:
   - Saat mengirim hasil ekstraksi ke `PATCH /api/v1/internal/documents/{id}/extraction`, sertakan:
     - `kunci_identitas` (format kanonik `canonical_ref(...).key`, misal `POJK|11|2022`);
     - `jumlah_halaman` (integer total halaman PDF, minimal 1).
   - Kedua field ini opsional; bila `kunci_identitas` tidak dikirim, backend memiliki fallback internal khusus untuk regulasi OJK bernomor awal angka. Namun, kunci kanonik dari lapisan data (`identity.py`) selalu diutamakan.
2. **Backfill Dokumen Lama**:
   - Setelah deployment backend selesai, lakukan pengisian ulang dokumen lama (151+ dokumen) menggunakan endpoint massal:
     `PATCH /api/v1/internal/documents/identity`
     dengan body array JSON (maksimal 500 item per request):
     ```json
     [
       {
         "document_id": 1,
         "kunci_identitas": "POJK|11|2022",
         "jumlah_halaman": 25
       }
     ]
     ```
   - Dokumen duplikat akan otomatis terdeteksi dan dinonaktifkan dengan mencatat pemenang dokumen yang paling lengkap.

---

## 3. Matriks Kasus Uji D01 – D13

| # | Kasus Uji | Ekspektasi | Hasil |
|---|---|---|---|
| D01 | `fallback_identity_key("POJK","11/POJK.03/2022",None)`; `("POJK","36 Tahun 2024",None)`; `("POJK","5",2020)`; `("PBI","7/1/PBI/2005",2005)`; `("POJK",None,2020)` | `POJK\|11\|2022`, `POJK\|36\|2024`, `POJK\|5\|2020`, `None`, `None` | **LULUS** |
| D02 | Dok A (10 hlm) terindeks; PATCH extraction dok B dengan kunci sama, 25 hlm | B tetap aktif; A nonaktif, `duplicate_of_id = B`, alasan memuat `duplikat_identitas`; respons B memuat `duplikat.rule = "page_count"`; audit tercatat | **LULUS** |
| D03 | Sama seperti D02, tetapi B 5 hlm | B nonaktif, A tetap aktif | **LULUS** |
| D04 | Jumlah halaman tidak diketahui, ukuran B > A | A nonaktif, `rule = "file_size"` | **LULUS** |
| D05 | Halaman dan ukuran sama | Yang `id`-nya lebih besar nonaktif, `rule = "older"` | **LULUS** |
| D06 | Kunci berbeda | Tidak ada yang dinonaktifkan, `duplikat = null` | **LULUS** |
| D07 | Pasangan berperan `draft_kajian` | Diabaikan | **LULUS** |
| D08 | A pernah duplikat lalu diaktifkan manual (`PUT /active`); B masuk dengan kunci sama | A **tidak** dinonaktifkan ulang | **LULUS** |
| D09 | `PATCH /internal/documents/identity` dengan 3 item: 1 tidak ada, 2 berkunci sama | `not_found` memuat id yang tidak ada; satu dari dua dinonaktifkan | **LULUS** |
| D10 | Cek duplikat dipaksa melempar galat (monkeypatch) | PATCH extraction tetap 200, hasil ekstraksi tersimpan | **LULUS** |
| D11 | Tanpa `kunci_identitas`, metadata `POJK` / `11/POJK.03/2022` | `identity_key` terisi `POJK\|11\|2022` dari cadangan | **LULUS** |
| D12 | `GET /documents?include_inactive=true&duplikat=true` dan dashboard | Dokumen duplikat tercantum; `kb.duplicate_documents` sesuai | **LULUS** |
| D13 | `backfill_identity.py --dry-run` | Tidak ada perubahan di DB; laporan memuat pasangan | **LULUS** |

---

## 4. Output Mentah Terminal

### 4.1 Ruff Check
```text
PS C:\Hero\hero-backend> .\venv\Scripts\ruff.exe check --select E9,F821,F822,F823 app scripts tests
All checks passed!
```

### 4.2 Pytest Step 17
```text
PS C:\Hero\hero-backend> .\venv\Scripts\python.exe -m pytest tests/test_step17_duplicate_identity.py -q
.............                                                            [100%]
============================== warnings summary ===============================
venv\Lib\site-packages\fastapi\testclient.py:1
  C:\Hero\hero-backend\venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

venv\Lib\site-packages\starlette\testclient.py:53
  C:\Hero\hero-backend\venv\Lib\site-packages\starlette\testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
13 passed, 2 warnings in 13.29s
```

### 4.3 Pytest Full Suite
```text
PS C:\Hero\hero-backend> .\venv\Scripts\python.exe -m pytest -q
........................................................................ [ 23%]
........................................................................ [ 47%]
........................................................................ [ 71%]
........................................................................ [ 95%]
..............s                                                          [100%]
302 passed, 1 skipped, 51 warnings in 248.44s (0:04:08)
```

### 4.4 Uji Live Docker & Health Check
```powershell
PS C:\Hero\hero-backend> docker compose up -d --build backend
#1 [internal] load local bake definitions
#1 reading from stdin 512B done
#1 DONE 0.0s

#2 [internal] load build definition from Dockerfile
#2 transferring dockerfile: 825B 0.0s done
#2 DONE 0.1s

#3 [internal] load metadata for docker.io/library/python:3.11-slim
#3 DONE 4.9s
...
 hero-backend-backend  Built
 Container hero_postgres  Running
 Container hero_fastapi  Recreate
 Container hero_fastapi  Recreated
 Container hero_postgres  Waiting
 Container hero_postgres  Healthy
 Container hero_fastapi  Starting
 Container hero_fastapi  Started

PS C:\Hero\hero-backend> Start-Sleep -Seconds 15; curl.exe -s http://localhost:8000/health
{"status":"ok","database":"ok","version":"0.10.0","app_env":"development","alembic_revision":"a7b8c9d0e1f2","alembic_head":"a7b8c9d0e1f2","migrations_up_to_date":true,"storage_writable":true,"crawler_backend":"simple_http","crawler_loaded":true,"auth_enabled":false,"protect_non_public":true}

PS C:\Hero\hero-backend> docker compose exec backend python scripts/backfill_identity.py --dry-run
=== Menjalankan Backfill Identitas Dokumen [DRY-RUN (bawaan - tanpa perubahan DB)] ===
Total dokumen di database: 71
Identity key terisi (atau kandidat terisi): 29
Kelompok duplikat terdeteksi: 0

=== Ringkasan ===
Mode: DRY-RUN
Dokumen diperiksa: 71
Identity key cadangan diisi: 29
Kelompok duplikat: 0
Dokumen dinonaktifkan: 0
```

### 4.5 Git Log (-4)
```text
PS C:\Hero\hero-backend> git log --oneline -4
b8db64e feat: cek duplikat identitas regulasi judul dan nomor peraturan
a058dcd test: jangan menulis docs/api saat menjalankan tes
3a3d744 chore: sinkron backend dari monorepo (PR #120)
9cf45fe fix(ci): Pipeline CI hijau (tes OCR, tes loadtest rapuh, run 20+ menit) (#120)
```

### 4.6 Git Status Setelah Commit
```text
PS C:\Hero\hero-backend> git status --short
(bersih / kosong)
```

