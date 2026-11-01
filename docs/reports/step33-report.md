# LAPORAN LANGKAH 33: Ganti Nama Kategori Otomatis Jadi Permanen

Tanggal: 2026-11-01  
Branch: `fix/step33-kunci-kategori`  
Status: SELESAI  

---

## 1. Ringkasan Tujuan & Perubahan

### Latar Belakang & Masalah
Sebelum Langkah 33, kategori otomatis dibentuk dari template `{jenis}/{tahun}` (misal `POJK/2026`). Jika pengguna/admin mengubah nama kategori via antarmuka (misal `"2026"` diubah menjadi `"Tahun 2026"`), placement service pada dokumen baru yang diimpor akan mencari kembali folder bernama `"2026"`. Karena tidak ditemukan (nama sudah berubah), sistem membuat duplikat `"2026"` baru di samping `"Tahun 2026"`.

### Solusi Desain
1. Menambahkan kolom baru `categories.kunci_otomatis` `String(255)`, nullable, dengan dua partial unique index (akar & anak).
2. Menjalankan data migration step di Alembic revision `d6e7f8a9b0c1`:
   ```sql
   UPDATE categories SET kunci_otomatis = name WHERE auto_created = true;
   ```
3. Memperbarui `CategoryService.resolve_or_create_path()`:
   - Prioritas 1: cocokkan `kunci_otomatis == seg` pada level yang sama.
   - Fallback 2: cocokkan `name == seg` (jika ditemukan dan `kunci_otomatis` masih null, isi dengan seg).
   - Buat baru 3: jika tidak ada, buat node baru dengan `name = seg`, `kunci_otomatis = seg`, `auto_created = True`.
4. Memperbarui `CategoryService.update()`:
   - Jika `name` diubah dan `kunci_otomatis` masih null serta `auto_created` True, kunci otomatis diisi nama lama sebelum diubah (`kunci_otomatis = old_name`).
   - Validasi bentrok keunikan `kunci_otomatis` pada induk tujuan saat update/move: jika bentrok, kembalikan HTTP 409 `"Induk tujuan sudah punya kategori otomatis dengan kunci '<kunci>'"`.
   - Audit logging: menyertakan perubahan `kunci_otomatis` dalam field `changes` saat terjadi penetapan kunci.
5. Menambahkan skrip bantu `scripts/backfill_kunci_kategori.py` (default `--dry-run`, flag `--apply` untuk eksekusi) untuk memulihkan kunci kategori otomatis yang pernah diganti nama sebelum Langkah 33 berdasarkan riwayat tertua audit log `UPDATE_CATEGORY`.
6. Memperbarui skema dan respons endpoint:
   - `kunci_otomatis` disertakan pada `CategoryTreeNode` (GET `/api/v1/categories/tree`), `CategoryDetailResponse` (GET `/api/v1/categories/{id}`), POST `/api/v1/categories/`, dan PATCH `/api/v1/categories/{id}`.
   - Regenerasi kontrak OpenAPI dan dokumentasi `docs/api/KONTRAK-API-FASE1.md`.

---

## 2. Pilihan Desain Index Keunikan `kunci_otomatis`

Dalam PostgreSQL dan SQLite, penanganan keunikan dengan nilai NULL dan pembedaan kategori akar (`parent_id IS NULL`) vs anak (`parent_id IS NOT NULL`) dilakukan menggunakan **dua partial unique index**:

1. **Akar (`parent_id IS NULL`)**:
   - Nama index: `ix_categories_kunci_otomatis_root`
   - Kolom: `(kunci_otomatis)`
   - Klausa WHERE: `parent_id IS NULL AND kunci_otomatis IS NOT NULL`
   - Menjamin di level akar tidak ada dua kategori dengan `kunci_otomatis` yang sama.

2. **Anak (`parent_id IS NOT NULL`)**:
   - Nama index: `ix_categories_kunci_otomatis_child`
   - Kolom: `(parent_id, kunci_otomatis)`
   - Klausa WHERE: `parent_id IS NOT NULL AND kunci_otomatis IS NOT NULL`
   - Menjamin di bawah induk yang sama tidak ada dua sub-kategori dengan `kunci_otomatis` yang sama. Kategori di bawah induk berbeda tetap dapat memakai nama tahun/kunci yang sama (misal `POJK/2026` dan `SEOJK/2026`).

**Alasan Pemilihan**:
- Kompatibel 100% baik di PostgreSQL (production/staging) maupun SQLite (lingkungan unit test in-memory).
- Menghindari ketergantungan pada sintaks Postgres 15+ (`NULLS NOT DISTINCT`) yang tidak didukung oleh SQLite.

---

## 3. Hasil Pengujian `tests/test_step33_kunci_kategori.py` (Tabel K01–K12)

| Kode | Kasus Uji | Hasil |
|---|---|---|
| **K01** | `resolve_or_create_path` membuat kategori dengan `kunci_otomatis` terisi sama dengan segmen | **PASS** |
| **K02** | Setelah nama anak diubah, resolve segmen asli memakai kategori yang sudah diganti nama (tidak membuat baru) | **PASS** |
| **K03** | Setelah nama akar diubah, resolve segmen asli memakai akar yang sudah diganti nama | **PASS** |
| **K04** | Kategori manual baru (`POST /api/v1/categories/`) memiliki `kunci_otomatis = None` | **PASS** |
| **K05** | Fallback segmen cocok dengan nama kategori lama (kunci null) dan mengisi `kunci_otomatis` | **PASS** |
| **K06** | Dua cabang berbeda (`POJK/2026` dan `SEOJK/2026`) dapat memakai `kunci_otomatis` yang sama tanpa bentrok | **PASS** |
| **K07** | Dua kategori pada level yang sama tidak boleh memiliki `kunci_otomatis` kembar (cek integritas index) | **PASS** |
| **K08** | Pindah induk via `PATCH /categories/{id}` gagal 409 bila bentrok `kunci_otomatis` dengan sibling di induk baru | **PASS** |
| **K09** | Audit log `UPDATE_CATEGORY` mencatat perubahan nama dan pengisian `kunci_otomatis` | **PASS** |
| **K10** | Konkurensi `resolve_or_create_path` (simulasi race condition) menangani bentrok secara aman | **PASS** |
| **K11** | Skrip `backfill_kunci_kategori.py` `--dry-run` vs `--apply` membaca audit log dan melewati bentrok | **PASS** |
| **K12** | Respons API `/categories/tree`, detail, POST, dan PATCH memuat field `kunci_otomatis` | **PASS** |

### Output pytest:
```text
tests\test_step33_kunci_kategori.py ............                         [100%]
12 passed, 2 warnings in 23.59s
```

---

## 4. Hasil Regresi Penuh `pytest -q`

```text
........................................................................ [ 12%]
.............................................s.......................... [ 24%]
........................................................................ [ 36%]
........................................................................ [ 48%]
........................................................................ [ 60%]
........................................................................ [ 72%]
........................................................................ [ 85%]
........................................................................ [ 97%]
................                                                         [100%]
591 passed, 1 skipped, 195 warnings in 1303.51s (0:21:43)
```

---

## 5. Hasil `ruff check`

```text
$ .\venv\Scripts\python.exe -m ruff check --select E9,F app scripts tests\test_step33_kunci_kategori.py
All checks passed!
```

---

## 6. Hasil Uji Live

### a. Output Migrasi Container Backend (`docker compose logs backend`)
```text
hero_fastapi  | ==> Menjalankan migrasi database Alembic...
hero_fastapi  | INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
hero_fastapi  | INFO  [alembic.runtime.migration] Will assume transactional DDL.
hero_fastapi  | INFO  [alembic.runtime.migration] Running upgrade c5d6e7f8a9b0 -> d6e7f8a9b0c1, step33 kunci_otomatis kategori
hero_fastapi  | ==> Menjalankan server HERO Backend Uvicorn pada port 8000 dengan 1 worker...
hero_fastapi  | INFO:     Started server process [1]
hero_fastapi  | INFO:     Waiting for application startup.
hero_fastapi  | INFO:     Application startup complete.
hero_fastapi  | INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

### b. Output Health Check (`curl.exe -s http://localhost:8000/health`)
```json
{"status":"ok","database":"ok","version":"0.10.0","app_env":"development","alembic_revision":"d6e7f8a9b0c1","alembic_head":"d6e7f8a9b0c1","migrations_up_to_date":true,"storage_writable":true,"crawler_backend":"simple_http","crawler_loaded":true,"auth_enabled":false,"protect_non_public":true}
```

### c. Output Backfill Kunci Kategori (`docker compose exec backend python scripts/backfill_kunci_kategori.py`)
```text
Tidak ada kategori yang perlu di-backfill.
```
*(Catatan: Semua kategori otomatis yang ada di DB lokal telah terisi `kunci_otomatis` otomatis melalui migrasi data step Alembic `d6e7f8a9b0c1`, dan belum ada riwayat rename terdahulu).*

### d. Output Categories Tree Live (`curl.exe -s http://localhost:8000/api/v1/categories/tree`)
*(Kutipan sebagian respon pohon kategori)*:
```json
[
  {
    "id": 1,
    "name": "POJK",
    "kunci_otomatis": null,
    "parent_id": null,
    "auto_created": false,
    "children": [
      {"id": 16, "name": "2026", "kunci_otomatis": "2026", "parent_id": 1, "auto_created": true, "children": []},
      {"id": 10, "name": "2025", "kunci_otomatis": "2025", "parent_id": 1, "auto_created": true, "children": []}
    ]
  },
  {
    "id": 12,
    "name": "PADK",
    "kunci_otomatis": "PADK",
    "parent_id": null,
    "auto_created": true,
    "children": [
      {"id": 13, "name": "2026", "kunci_otomatis": "2026", "parent_id": 12, "auto_created": true, "children": []}
    ]
  }
]
```

### e. Output Smoke Test Fase 2 (`scripts/smoke_fase2.py`)
```text
====================================================================================
       HERO BACKEND SMOKE TEST FASE 2 - http://localhost:8000
       Revisi Alembic Diharapkan: d6e7f8a9b0c1
       Autentikasi: Tidak ada HERO_SMOKE_TOKEN (mode anonim/dev)
====================================================================================
====================================================================================
Kode   | Cek                                      | Status   | Keterangan
------------------------------------------------------------------------------------
S01    | GET /health                              | OK       | rev=d6e7f8a9b0c1
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
S17    | GET /api/v1/dashboard/corong             | OK       | sumber=5, di_kb=92, terbaca=0 (0.0%)
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

## 7. `git diff main --stat`

```text
 app/models/category.py           |  22 ++++++-
 app/routers/categories.py        |   4 +-
 app/schemas/category.py          |   3 +-
 app/services/category_service.py |  68 +++++++++++++++++++---
 docs/api/KONTRAK-API-FASE1.md    |  15 +++++
 docs/api/openapi-fase1.json      | 122 +++++++++++++++++++++------------------
 6 files changed, 169 insertions(+), 65 deletions(-)
```

---

## 8. Log 3 Commit Terakhir (`git log --oneline -3`)

```text
93ce8e5 fix(backend): Langkah 32 - masukan frontend
de4382a fix(step32): response_model harmonisasi longgar & exclude_unset, corong segar di skrip
f9006af fix: masukan frontend — bug corong, skema OpenAPI, ringkasan harmonisasi tersaring, perbaikan kecil kategori/dokumen
```

---

## 9. Catatan untuk FE (Ikhwan)

1. **Field Baru `kunci_otomatis`**:
   - Tersedia di respons `GET /api/v1/categories/tree` (pada setiap node `CategoryTreeNode`), `GET /api/v1/categories/{id}`, `POST /api/v1/categories/`, dan `PATCH /api/v1/categories/{id}`.
   - Nilai bertipe `Optional[str]`: bernilai `null` untuk kategori manual/bawaan, atau string (misal `"2026"`) untuk kategori yang pernah/sedang menjadi target auto-placement.
2. **Perilaku Rename Permanen**:
   - Jika admin mengubah nama kategori otomatis via `PATCH /api/v1/categories/{id}` (contoh: mengubah `"2026"` menjadi `"Tahun 2026"`), backend akan mempertahankan `kunci_otomatis = "2026"`.
   - Dokumen baru yang di-ingest dengan pola tahun 2026 akan **otomatis tetap masuk ke folder yang sudah diganti nama tersebut** tanpa membuat folder `"2026"` duplikat baru.
3. **Penanganan HTTP 409 pada Perpindahan Induk (`parent_id`)**:
   - Backend memvalidasi keunikan `kunci_otomatis` di bawah induk yang sama.
   - Jika pengguna memindahkan kategori otomatis ke induk baru yang sudah memiliki anak dengan `kunci_otomatis` yang sama, backend akan mengembalikan status **HTTP 409 Conflict** dengan pesan:
     `"Induk tujuan sudah punya kategori otomatis dengan kunci '<kunci>'"`
   - Frontend dapat menangkap status 409 dan menampilkan pesan toast/modal kesalahan tersebut kepada pengguna.

---

## 10. Catatan Deploy

1. **Migrasi Otomatis Alembic**:
   - Skrip `entrypoint.sh` container backend secara otomatis menjalankan `alembic upgrade head`, mengeksekusi migrasi `d6e7f8a9b0c1_step33_kunci_otomatis.py` yang menambahkan kolom, mengisi data `kunci_otomatis` untuk kategori auto-created yang ada, dan membuat dua partial unique index.
2. **Backfill Opsional (Production/Staging)**:
   - Jika pada lingkungan produksi sebelumnya ada kategori otomatis yang sudah sempat diubah namanya oleh pengguna sebelum Langkah 33 dideploy, jalankan skrip pemulihan:
     ```bash
     # 1. Cek usulan pemulihan kunci (dry-run):
     docker compose exec backend python scripts/backfill_kunci_kategori.py

     # 2. Terapkan jika usulan sesuai:
     docker compose exec backend python scripts/backfill_kunci_kategori.py --apply
     ```
   - Skrip otomatis membaca nama asli tertua dari `audit_logs` dan melewati kategori jika terjadi bentrok dengan sibling.
