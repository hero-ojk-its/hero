# Laporan Implementasi HERO Backend — Langkah 28
**Kategori: Relokasi Otomatis, Kelola Kategori, dan Audit Penempatan**

---

## 1. Ringkasan Singkat

Langkah 28 menyelesaikan isu klasifikasi kategori dokumen di Knowledge Base HERO, khususnya temuan QA Hamdan (#168 di mana dokumen `POJK-77-2026.pdf` masuk ke kategori `POJK / Tanpa Tahun` karena `NamingInput` tidak menyertakan `regulation_year` dan `original_filename`), serta menyempurnakan manajemen hierarki kategori dan audit penempatan berkas:
1. **Penanda `kategori_manual`**: Menambahkan kolom `documents.kategori_manual` (Boolean, default `False`) melalui migrasi Alembic `c5d6e7f8a9b0`. Kolom bernilai `true` saat pengguna memilih kategori manual pada unggah berkas atau mengubah `category_id` via `PATCH /documents/{id}/metadata`. Mengosongkan `category_id` (`null`) mereset `kategori_manual = false` dan memicu evaluasi relokasi otomatis.
2. **Perbaikan `NamingInput` & Logika Penempatan (`PlacementService`)**:
   - Menambahkan `regulation_year` dan `original_filename` pada konstruksi `NamingInput` di `CategoryService` dan `PlacementService`.
   - Mengubah `placement_service.place()` agar tidak lagi mengunci `doc.category_id` lama kecuali `keep_category=True` atau `doc.kategori_manual=True`.
   - Menghasilkan audit log `PLACE_DOCUMENT` dengan detail lengkap (`alasan`, `old_path`, `new_path`, `kategori_lama`, `kategori_baru`, `kategori_manual`).
3. **Skrip Relokasi Dokumen (`scripts/relokasi_kategori.py`)**:
   - Mendukung mode `--dry-run` (bawaan) dan `--apply`, serta parameter `--limit N`.
   - Mengevaluasi seluruh dokumen berkategori otomatis dan memindahkan file storage serta memperbarui kategori dokumen ke segmen terbaru.
4. **Kelola Kategori Lengkap (`CategoryService` & `app/routers/categories.py`)**:
   - `PATCH /api/v1/categories/{id}`: Ubah nama, ubah induk (`parent_id`), dan perbarui aturan klasifikasi (`classification_rule`). Memvalidasi siklus hierarki (422), nama unik per induk (409), dan JSON dict <= 4000 karakter (422). Memindahkan seluruh dokumen pada subhierarki secara otomatis dan mengubah `auto_created` menjadi `false`.
   - `DELETE /api/v1/categories/{id}`: Menolak 409 bila kategori memiliki subkategori atau dokumen aktif. Mengizinkan hapus jika kosong (204).
   - `GET /api/v1/categories/{id}` & `/tree`: Menampilkan `jumlah_dokumen` (dokumen langsung pada kategori) dan `classification_rule`.
   - `POST /api/v1/categories/`: Menerima dan memvalidasi `classification_rule` serta menyetel `auto_created=False`.
   - Audit trail `UPDATE_CATEGORY` dan `DELETE_CATEGORY`.

---

## 2. Daftar Lokasi `NamingInput(...)` yang Diubah

Berikut adalah berkas dan baris sebelum/sesudah perbaikan yang memastikan `regulation_year` dan `original_filename` tersedia saat penentuan kategori dan penempatan:

### a. `app/services/category_service.py` (fungsi `category_segments_for`)
**Sebelum:**
```python
        naming_input = NamingInput(
            document_type=str(document_type),
            regulation_number=doc.regulation_number,
        )
```
**Sesudah:**
```python
        naming_input = NamingInput(
            document_type=str(document_type),
            regulation_number=doc.regulation_number,
            regulation_year=doc.regulation_year,
            original_filename=doc.original_filename,
        )
```

### b. `app/services/placement_service.py` (fungsi `place`)
**Sebelum:**
```python
        naming_input = NamingInput(
            document_type=doc.document_type.value if hasattr(doc.document_type, "value") else str(doc.document_type),
            regulation_number=doc.regulation_number,
            original_filename=doc.original_filename,
        )
```
**Sesudah:**
```python
        naming_input = NamingInput(
            document_type=doc.document_type.value if hasattr(doc.document_type, "value") else str(doc.document_type),
            regulation_number=doc.regulation_number,
            regulation_year=doc.regulation_year,
            original_filename=doc.original_filename,
        )
```

### c. `app/routers/documents.py` (fungsi `update_document_metadata`)
**Sebelum:**
```python
        placement_fields = {"document_type", "regulation_number", "original_filename"}
```
**Sesudah:**
```python
        placement_fields = {"document_type", "regulation_number", "regulation_year", "original_filename"}
```

---

## 3. Output Terminal `scripts/relokasi_kategori.py`

### Dry-run (bawaan)
```
=== Menjalankan Relokasi Kategori [DRY-RUN (bawaan - tanpa perubahan DB)] ===
Kandidat dokumen perlu relokasi: 5
Dokumen 67 | POJK -> POJK/2022
Dokumen 68 | POJK -> POJK/2023
Dokumen 69 | POJK -> POJK/2023
Dokumen 70 | POJK -> POJK/2023
Dokumen 71 | POJK -> POJK/2023
=== Ringkasan Hasil Relokasi ===
Mode                : DRY-RUN (bawaan - tanpa perubahan DB)
Kandidat ditemukan  : 5
Dipindah            : 0
Gagal               : 0
Dilewati            : 66
```

### Apply
```
=== Menjalankan Relokasi Kategori [APPLY] ===
Kandidat dokumen perlu relokasi: 5
Dokumen 67 | POJK -> POJK/2022 | DIPINDAH
Dokumen 68 | POJK -> POJK/2023 | DIPINDAH
Dokumen 69 | POJK -> POJK/2023 | DIPINDAH
Dokumen 70 | POJK -> POJK/2023 | DIPINDAH
Dokumen 71 | POJK -> POJK/2023 | DIPINDAH
=== Ringkasan Hasil Relokasi ===
Mode                : APPLY
Kandidat ditemukan  : 5
Dipindah            : 5
Gagal               : 0
Dilewati            : 66
```

---

## 4. Tabel Hasil Pengujian Langkah 28 (K01 s.d. K16)

| Kode | Skenario Uji | Status |
|---|---|:---:|
| **K01** | `CategoryService.category_segments_for` menggunakan `regulation_year` dan tidak lagi jatuh ke "Tanpa Tahun" | **PASS** |
| **K02** | Koreksi metadata (nomor/tahun) memicu relokasi otomatis dokumen non-manual ke segmen kategori dan path baru | **PASS** |
| **K03** | Dokumen dengan `kategori_manual=true` mempertahankan kategori lamanya saat metadata (nomor/tahun) dikoreksi | **PASS** |
| **K04** | Koreksi `category_id: null` mereset `kategori_manual` menjadi `false` dan menempatkan ulang ke kategori otomatis | **PASS** |
| **K05** | Unggah dokumen dengan `category_id` tersetel menghasilkan dokumen dengan `kategori_manual=true` | **PASS** |
| **K06** | `PATCH /categories/{id}` ubah nama merelokasi berkas fisik seluruh dokumen di subhierarkinya | **PASS** |
| **K07** | `PATCH /categories/{id}` nama bentrok dengan saudara satu induk mengembalikan HTTP 409 Conflict | **PASS** |
| **K08** | `PATCH /categories/{id}` memindahkan kategori menjadi turunan dari dirinya sendiri mengembalikan 422 (siklus) | **PASS** |
| **K09** | `PATCH /categories/{id}` pemindahan induk valid memindahkan seluruh dokumen pada subhierarki ke direktori baru | **PASS** |
| **K10** | Validasi `classification_rule` pada POST dan PATCH (dict JSON valid, maks 4000 char, tipe bukan dict -> 422) | **PASS** |
| **K11** | `DELETE /categories/{id}` menolak 409 bila ada subkategori/dokumen aktif, dan berhasil 204 bila kosong | **PASS** |
| **K12** | `POST /categories/` membuat kategori manual dengan `auto_created=false` | **PASS** |
| **K13** | `GET /categories/{id}` dan `GET /categories/tree` mengembalikan `jumlah_dokumen` dan `classification_rule` | **PASS** |
| **K14** | Skrip CLI `scripts/relokasi_kategori.py` dry-run tidak mengubah DB, opsi `--apply` memperbarui DB dan memindahkan berkas | **PASS** |
| **K15** | Otorisasi role: pengguna tanpa hak akses `kb_kelola` ditolak HTTP 403 Forbidden | **PASS** |
| **K16** | Kegagalan penempatan 1 dokumen saat rename/move kategori tidak membatalkan perubahan kategori | **PASS** |

---

## 5. Output Terminal Pytest

### a. `pytest tests/test_step28_kategori.py -q`
```
................                                                         [100%]
============================== warnings summary ===============================
venv\Lib\site-packages\fastapi\testclient.py:1
  C:\Hero\hero-backend\venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

venv\Lib\site-packages\starlette\testclient.py:53
  C:\Hero\hero-backend\venv\Lib\site-packages\starlette\testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
16 passed, 2 warnings in 30.71s
```

### b. `pytest -q` (seluruh suite)
```
........................................................................ [ 13%]
.............................................s.......................... [ 27%]
........................................................................ [ 41%]
........................................................................ [ 55%]
........................................................................ [ 69%]
........................................................................ [ 83%]
........................................................................ [ 97%]
...............                                                          [100%]
518 passed, 1 skipped, 184 warnings in 879.30s (0:14:39)
```

---

## 6. Output Terminal Ruff
Perintah: `.\venv\Scripts\python.exe -m ruff check --select E9,F app scripts tests/test_step28_kategori.py`
```
All checks passed!
```

---

## 7. Output Terminal Uji Live (Docker)

### a. `curl http://localhost:8000/health`
```json
{"status":"ok","database":"ok","version":"0.10.0","app_env":"development","alembic_revision":"c5d6e7f8a9b0","alembic_head":"c5d6e7f8a9b0","migrations_up_to_date":true,"storage_writable":true,"crawler_backend":"simple_http","crawler_loaded":true,"auth_enabled":false,"protect_non_public":true}
```

### b. `curl http://localhost:8000/api/v1/categories/tree` (cuplikan)
```json
[
  {"id":7,"name":"Draft Kajian","parent_id":null,"auto_created":false,"document_count":0,"total_document_count":0,"jumlah_dokumen":0,"classification_rule":null,"children":[]},
  {"id":23,"name":"KEPDIR","parent_id":null,"auto_created":true,"document_count":0,"total_document_count":2,"jumlah_dokumen":0,"classification_rule":null,"children":[
    {"id":25,"name":"1993","parent_id":23,"auto_created":true,"document_count":1,"total_document_count":1,"jumlah_dokumen":1,"classification_rule":null,"children":[]},
    {"id":24,"name":"1995","parent_id":23,"auto_created":true,"document_count":1,"total_document_count":1,"jumlah_dokumen":1,"classification_rule":null,"children":[]}
  ]},
  {"id":1,"name":"POJK","parent_id":null,"auto_created":false,"document_count":2,"total_document_count":26,"jumlah_dokumen":2,"classification_rule":null,"children":[
    {"id":37,"name":"2014","parent_id":1,"auto_created":true,"document_count":1,"total_document_count":1,"jumlah_dokumen":1,"classification_rule":null,"children":[]},
    {"id":8,"name":"2023","parent_id":1,"auto_created":true,"document_count":4,"total_document_count":4,"jumlah_dokumen":4,"classification_rule":null,"children":[]},
    {"id":16,"name":"2026","parent_id":1,"auto_created":true,"document_count":11,"total_document_count":11,"jumlah_dokumen":11,"classification_rule":null,"children":[]}
  ]}
]
```

### c. `python scripts/smoke_fase2.py --base-url http://localhost:8000`
```
================================================================================
       HERO BACKEND SMOKE TEST FASE 2 (READ-ONLY) - http://localhost:8000
       Revisi Alembic Diharapkan: c5d6e7f8a9b0
       Autentikasi: Tidak ada HERO_SMOKE_TOKEN (mode anonim/dev)
================================================================================
================================================================================
Kode   | Cek                                  | Status   | Keterangan
--------------------------------------------------------------------------------
S01    | GET /health                          | OK       | rev=c5d6e7f8a9b0
S02    | GET /api/v1/auth/me                  | OK       | auth_enabled=False
S03    | GET /api/v1/ml/health                | LEWATI   | ML tidak siap: layanan_analisa_belum_dikonfigurasi
S04    | Pilih dokumen uji                    | LEWATI   | Tidak ada dokumen publik aktif terindeks/perlu_koreksi
S05    | GET /documents/{id}/versi            | LEWATI   | Tidak ada dokumen uji
S06    | GET /ml/analisa/{id} (panggilan 1)   | LEWATI   | Tidak ada dokumen uji
S07    | GET /ml/analisa/{id} (panggilan 2)   | LEWATI   | Tidak ada dokumen uji
S08    | GET /documents/{id}/analisa/banding  | LEWATI   | Tidak ada dokumen uji
S09    | GET /documents/{id}/analisa/riwayat  | LEWATI   | Tidak ada dokumen uji
S10    | GET .../riwayat/{run_id}             | LEWATI   | Tidak ada run_id dari analisa
S11    | Ekspor format=json                   | LEWATI   | Tidak ada dokumen uji
S12    | Ekspor format=csv                    | LEWATI   | Tidak ada dokumen uji
S13    | Ekspor format=docx                   | LEWATI   | Tidak ada dokumen uji
S14    | GET /api/v1/audit-logs               | LEWATI   | Belum ada entri audit RUN_ANALYSIS
S15    | Penjaga non-publik                   | OK       | doc_id=64 ditolak 403 saat auth mati
================================================================================
RINGKASAN: 3 OK, 0 GAGAL, 12 LEWATI
PERINGATAN: cek analisa/riwayat/ekspor (S05–S13) tidak dijalankan karena tidak ada dokumen uji. Pakai --doc-id atau pastikan ada dokumen publik terindeks.
```

---

## 8. Catatan untuk Frontend (Ikhwan)

1. **Ubah Nama / Pindah Induk Kategori (`PATCH /api/v1/categories/{id}`)**:
   - Payload parsial didukung:
     - `name`: string (1-100 karakter).
     - `parent_id`: integer id kategori induk baru, atau `null` untuk memindahkan ke tingkat akar (root).
     - `classification_rule`: objek JSON (dictionary) atau `null`.
   - Respons sukses (HTTP 200) mengembalikan:
     ```json
     {
       "kategori": { ...CategoryDetailResponse... },
       "dokumen_dipindah": 5,
       "dokumen_gagal": []
     }
     ```
     Jika ada dokumen fisik yang gagal dipindahkan saat penamaan/pemindahan folder, detail kegagalan tercatat dalam array `dokumen_gagal: [{"document_id": 12, "error": "..."}]` tanpa membatalkan pembaharuan kategori di database.
   - Penanganan Error:
     - **HTTP 409 Conflict**: Nama kategori sudah digunakan oleh kategori lain di bawah induk yang sama (`detail: "Kategori dengan nama '...' sudah ada di bawah induk yang sama"`).
     - **HTTP 422 Unprocessable Entity**:
       - Siklus hierarki (`detail: "Kategori tidak dapat dipindahkan ke dirinya sendiri atau turunannya"`).
       - Aturan klasifikasi tidak valid (bukan JSON object atau ukuran serialisasi melebihi 4000 karakter).

2. **Hapus Kategori (`DELETE /api/v1/categories/{id}`)**:
   - Kategori hanya dapat dihapus bila tidak lagi memiliki subkategori dan tidak memiliki dokumen aktif.
   - Bila masih memiliki referensi, backend mengembalikan **HTTP 409 Conflict** dengan payload detail:
     ```json
     {
       "detail": "Kategori tidak dapat dihapus karena masih memiliki subkategori atau dokumen terkait",
       "subkategori": 2,
       "dokumen": 15
     }
     ```
     Frontend dapat menampilkan modal peringatan berisi jumlah subkategori dan dokumen yang perlu dipindahkan/dibersihkan terlebih dahulu sebelum kategori dapat dihapus.
   - Bila kosong, mengembalikan **HTTP 204 No Content**.

3. **Field `jumlah_dokumen` pada Tree & Detail**:
   - Endpoint `GET /api/v1/categories/tree` dan `GET /api/v1/categories/{id}` kini menyertakan `jumlah_dokumen` yang menghitung dokumen langsung yang berada pada kategori tersebut (di samping `total_document_count` yang mencakup subtree).

4. **Kategori Manual vs Otomatis pada Dokumen**:
   - Jika pengguna memilih kategori manual saat unggah (`category_id` terisi), dokumen diberi tanda `kategori_manual = true`. Koreksi metadata (nomor, tahun) di masa depan tidak akan memindahkan dokumen dari kategori pilihan pengguna.
   - Bila ingin mengembalikan dokumen ke penempatan otomatis berbasis jenis/tahun, kirimkan `{"category_id": null}` pada `PATCH /api/v1/documents/{id}/metadata`. Dokumen akan dihitung ulang kategorinya secara otomatis.

---

## 9. Catatan Deploy Staging

1. **Migrasi Database**:
   - Jalankan Alembic migration:
     ```bash
     alembic upgrade head
     ```
   - Revisi target: `c5d6e7f8a9b0` (menambahkan kolom `documents.kategori_manual BOOLEAN NOT NULL DEFAULT FALSE`).

2. **Relokasi Dokumen Eksisting**:
   - Setelah migrasi DB dan service backend aktif, jalankan skrip relokasi dokumen untuk merapikan dokumen historis (seperti POJK tahun 2022/2023 yang sebelumnya berada di root POJK):
     ```bash
     # Dry-run untuk memastikan kandidat dokumen yang akan dipindah
     docker compose exec backend python scripts/relokasi_kategori.py

     # Eksekusi relokasi dan perbarui path berkas
     docker compose exec backend python scripts/relokasi_kategori.py --apply
     ```

