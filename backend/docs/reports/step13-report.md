# Laporan Langkah 13: Kontrak Pasal untuk Lapisan Data

**Branch:** `feat/step13-kontrak-pasal`  
**Base Commit:** `581c19f`  
**Waktu Eksekusi:** 10 Oktober 2026  

---

## 1. Ringkasan Perubahan

Langkah 13 menyelaraskan kontrak endpoint pasal internal (`POST /api/v1/internal/articles`) antara backend dan lapisan data (ML/Pipeline) sesuai catatan `pipeline/docs/INTEGRASI_BACKEND.md` §7:
1. **Pencegahan Pasal Ganda (§7.2):** Migrasi menambahkan unique index parsial `uq_articles_document_order` pada `(document_id, order_index) WHERE order_index IS NOT NULL`. Endpoint `bulk_insert_articles` kini beroperasi secara upsert (`INSERT ... ON CONFLICT (document_id, order_index) WHERE order_index IS NOT NULL DO UPDATE`). Kolom `level`, `chapter_title`, `article_number`, `content_text`, `page`, `parent_id`, dan `embedding` (coalesce bila tidak null) diperbarui.
2. **Pembersihan Bersih Dokumen (`replace_document_ids`):** Field baru di `BulkArticleIn` yang secara atomik menghapus pasal lama dokumen terkait sebelum upsert jika disediakan.
3. **Penyimpanan & Tampilan Halaman PDF (§7.1):** Kolom baru `articles.page` (`Integer`, nullable, 1-indexed) ditambahkan dan dimuat pada respons detail dokumen `GET /api/v1/documents/{id}`.
4. **Hierarki Pasal dan Ayat (§7.3):** Field baru `parent_order_index` diselesaikan secara otomatis menjadi `parent_id`, baik induk ada pada request sebelumnya maupun berada di dalam batch yang sama (melalui resolusi hierarkis multi-level). Bila induk tidak ditemukan, sistem mengembalikan kode HTTP **422** Unprocessable Entity.
5. **Validasi Eksistensi Dokumen:** Memastikan seluruh `document_id` terdaftar di tabel `documents`, mengembalikan **422** dengan daftar ID yang tidak dikenal jika tidak valid.

---

## 2. Diff Berkas

### `git diff --stat`
```text
 app/models/article.py         |  16 +++-
 app/routers/documents.py      |   1 +
 app/routers/internal.py       | 193 ++++++++++++++++++++++++++++++++++++++----
 app/schemas/article.py        |  24 +++++-
 docs/api/KONTRAK-API-FASE1.md |  12 ++-
 docs/api/openapi-fase1.json   |  70 +++++++++++++--
 6 files changed, 286 insertions(+), 30 deletions(-)
```

### Potongan Diff Skema `ArticleChunkIn` & `BulkArticleIn` (`docs/api/openapi-fase1.json`)
```diff
@@ -3493,6 +3493,38 @@
               4
             ]
           },
+          "page": {
+            "anyOf": [
+              {
+                "type": "integer",
+                "minimum": 1.0
+              },
+              {
+                "type": "null"
+              }
+            ],
+            "title": "Page",
+            "description": "Halaman PDF tempat pasal ini dimulai (1-indexed)",
+            "examples": [
+              1
+            ]
+          },
+          "parent_order_index": {
+            "anyOf": [
+              {
+                "type": "integer",
+                "minimum": 0.0
+              },
+              {
+                "type": "null"
+              }
+            ],
+            "title": "Parent Order Index",
+            "description": "order_index pasal induk dalam dokumen yang sama (0-based)",
+            "examples": [
+              0
+            ]
+          },
           "embedding": {
             "anyOf": [
               {
@@ -3774,6 +3807,21 @@
             "minItems": 1,
             "title": "Articles",
             "description": "Daftar chunk pasal yang akan dimasukkan ke database (min. 1 item)"
+          },
+          "replace_document_ids": {
+            "anyOf": [
+              {
+                "items": {
+                  "type": "integer"
+                },
+                "type": "array"
+              },
+              {
+                "type": "null"
+              }
+            ],
+            "title": "Replace Document Ids",
+            "description": "Daftar ID dokumen yang seluruh pasalnya akan dihapus terlebih dahulu sebelum upsert dalam transaksi yang sama"
           }
```

*Catatan perubahan di luar skema artikel:*
- Perubahan pada `docs/api/KONTRAK-API-FASE1.md` merupakan penambahan field `"page": null` pada contoh respons `GET /api/v1/documents/{id}` yang ditangkap langsung dari eksekusi nyata test builder terhadap database test.

---

## 3. Catatan untuk Lapisan Data

> **Diteruskan kepada Fathir (Data/ML Monorepo `pipeline/`)**

Endpoint `POST /api/v1/internal/articles` kini sepenuhnya mendukung operasi idempoten, pelacakan halaman PDF, dan hierarki ayat.

### Payload Model & Field Baru
```json
{
  "replace_document_ids": [67],
  "articles": [
    {
      "document_id": 67,
      "level": "pasal",
      "chapter_title": "BAB I KETENTUAN UMUM",
      "article_number": "Pasal 1",
      "content_text": "Bank Umum adalah bank yang melaksanakan kegiatan usaha...",
      "order_index": 0,
      "page": 1,
      "parent_order_index": null,
      "embedding": null
    },
    {
      "document_id": 67,
      "level": "ayat",
      "chapter_title": "BAB I KETENTUAN UMUM",
      "article_number": "Ayat (1)",
      "content_text": "Ketentuan mengenai permodalan diatur dalam peraturan ini...",
      "order_index": 1,
      "page": 2,
      "parent_order_index": 0,
      "embedding": null
    }
  ]
}
```

### Panduan Penggunaan
1. **Pengiriman Bertahap & Idempoten (§7.2):**
   - Pengiriman tetap dibagi maksimal 150 pasal per request, urut berdasarkan `order_index` (0, 1, 2, ...).
   - Pengiriman ulang batch yang sama tidak akan menggandakan baris di database. Sistem melakukan upsert berdasarkan `(document_id, order_index)`.
2. **Menggunakan `replace_document_ids`:**
   - Gunakan field opsional `replace_document_ids: [document_id]` **hanya pada request batch pertama** (order_index 0–149) saat melakukan ekstraksi ulang dokumen secara penuh.
   - Semua pasal lama milik dokumen tersebut akan dihapus sebelum pasal baru dimasukkan, membersihkan sisa pasal bila dokumen hasil ekstraksi baru memiliki jumlah pasal lebih sedikit.
   - Pada request batch kedua dan seterusnya, **jangan** sertakan `replace_document_ids` agar hasil request pertama tidak terhapus.
3. **Menggunakan `page` (§7.1):**
   - Isi dengan nomor halaman tempat pasal/ayat dimulai pada berkas PDF (1-indexed, integer >= 1).
   - Nilai ini wajib untuk memudahkan navigasi langsung ke halaman saat verifikasi regulasi.
4. **Menggunakan `parent_order_index` (§7.3):**
   - Untuk level turunan (ayat, huruf, dsb.), isi `parent_order_index` dengan `order_index` pasal/bab induknya dalam dokumen yang sama.
   - Backend menyelesaikan referensi ini menjadi `parent_id` (foreign key) secara otomatis.
   - Referensi induk dapat menunjuk ke pasal pada request sebelumnya maupun pasal pada request yang sama.
   - Jika induk tidak ditemukan, backend merespons **422 Unprocessable Entity**.

---

## 4. Eksekusi Migrasi Database (Alembic)

Migrasi: `alembic/versions/e5f6a7b8c9d0_step13_articles_contract.py` (`down_revision = 'd4e5f6a7b8c9'`).

### Upgrade
```text
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade d4e5f6a7b8c9 -> e5f6a7b8c9d0, step13 articles contract
INFO  [alembic.runtime.migration] Pembersihan duplikat articles: 0 baris dihapus.
```

### Downgrade
```text
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running downgrade e5f6a7b8c9d0 -> d4e5f6a7b8c9, step13 articles contract
```

---

## 5. Hasil Pengujian Unit & Integrasi (P01 – P10)

File: `tests/test_step13_articles.py`

| # | Kasus | Ekspektasi | Hasil |
|---|---|---|:---:|
| **P01** | Kirim 3 pasal (order 0–2) dua kali | Total tetap 3; respons kedua `updated_count = 3` | **PASS** |
| **P02** | Satu dokumen 320 pasal dikirim 3 request (150/150/20) | Total 320; tidak ada yang terhapus antar-request | **PASS** |
| **P03** | Kirim ulang 320 lalu 300 dengan `replace_document_ids=[id]` di request pertama | Total 300; `deleted_count = 320` | **PASS** |
| **P04** | `page` terisi | Tersimpan dan tampil di `GET /documents/{id}` | **PASS** |
| **P05** | Ayat dengan `parent_order_index` pasal di request sebelumnya | `parent_id` menunjuk pasal yang benar | **PASS** |
| **P06** | `parent_order_index` yang tidak ada | 422, tidak ada baris tersimpan | **PASS** |
| **P07** | `document_id` tidak dikenal | 422 berisi daftar id | **PASS** |
| **P08** | Embedding null pada kiriman ulang | Embedding lama tidak tertimpa null | **PASS** |
| **P09** | Migrasi pada DB yang sudah berisi duplikat | Duplikat dibersihkan, index terpasang | **PASS** |
| **P10** | Payload lama persis seperti worker sekarang (tanpa field baru) | Tetap diterima | **PASS** |

### Output Mentah Pytest Suite Step 13
```text
============================= test session starts =============================
platform win32 -- Python 3.13.7, pytest-9.1.1, pluggy-1.6.0 -- C:\Hero\hero-backend\venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Hero\hero-backend
plugins: anyio-4.15.1
collecting ... collected 10 items

tests/test_step13_articles.py::test_p01_duplicate_order_upsert PASSED    [ 10%]
tests/test_step13_articles.py::test_p02_multi_batch_sequential PASSED    [ 20%]
tests/test_step13_articles.py::test_p03_replace_document_ids PASSED      [ 30%]
tests/test_step13_articles.py::test_p04_page_stored_and_displayed PASSED [ 40%]
tests/test_step13_articles.py::test_p05_parent_order_index_previous_request PASSED [ 50%]
tests/test_step13_articles.py::test_p06_nonexistent_parent_order_index PASSED [ 60%]
tests/test_step13_articles.py::test_p07_unknown_document_id PASSED       [ 70%]
tests/test_step13_articles.py::test_p08_null_embedding_on_resend PASSED  [ 80%]
tests/test_step13_articles.py::test_p09_migration_cleans_duplicates_and_creates_index PASSED [ 90%]
tests/test_step13_articles.py::test_p10_legacy_payload_compatibility PASSED [100%]

======================= 10 passed, 9 warnings in 14.78s =======================
```

### Output Mentah Pytest Seluruh Suite
```text
251 passed, 1 skipped, 9 warnings in 331.14s (0:05:31)
```

---

## 6. Output Linter (Ruff)

```powershell
.\venv\Scripts\ruff.exe check --select E9,F821,F822,F823 app scripts tests
```
```text
All checks passed!
```

---

## 7. Uji Live Docker

### Build & Deploy Container
```powershell
docker compose up -d --build backend
```
```text
 hero-backend-backend  Built
 Container hero_postgres  Running
 Container hero_fastapi  Recreate
 Container hero_fastapi  Recreated
 Container hero_postgres  Waiting
 Container hero_postgres  Healthy
 Container hero_fastapi  Starting
 Container hero_fastapi  Started
```

### Healthcheck
```powershell
Start-Sleep -Seconds 15
curl.exe -s http://localhost:8000/health
```
```json
{"status":"ok","database":"ok","version":"0.10.0","app_env":"development","alembic_revision":"e5f6a7b8c9d0","alembic_head":"e5f6a7b8c9d0","migrations_up_to_date":true,"storage_writable":true,"crawler_backend":"simple_http","crawler_loaded":true,"auth_enabled":false,"protect_non_public":true}
```

### Verifikasi Skema Tabel PostgreSQL
```powershell
docker exec hero_postgres psql -U hero_user -d hero_db -c "\d articles"
```
```text
                                         Table "public.articles"
     Column     |           Type           | Collation | Nullable |               Default                
----------------+--------------------------+-----------+----------+--------------------------------------
 id             | integer                  |           | not null | nextval('articles_id_seq'::regclass)
 document_id    | integer                  |           | not null | 
 parent_id      | integer                  |           |          | 
 chapter_title  | character varying(255)   |           |          | 
 article_number | character varying(50)    |           | not null | 
 content_text   | text                     |           | not null | 
 level          | character varying(20)    |           | not null | 
 order_index    | integer                  |           |          | 
 embedding      | vector(1536)             |           |          | 
 created_at     | timestamp with time zone |           |          | now()
 page           | integer                  |           |          | 
Indexes:
    "articles_pkey" PRIMARY KEY, btree (id)
    "ix_articles_document_id" btree (document_id)
    "ix_articles_id" btree (id)
    "ix_articles_parent_id" btree (parent_id)
    "uq_articles_document_order" UNIQUE, btree (document_id, order_index) WHERE order_index IS NOT NULL
Foreign-key constraints:
    "articles_document_id_fkey" FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
    "articles_parent_id_fkey" FOREIGN KEY (parent_id) REFERENCES articles(id) ON DELETE CASCADE
Referenced by:
    TABLE "article_references" CONSTRAINT "article_references_source_article_id_fkey" FOREIGN KEY (source_article_id) REFERENCES articles(id) ON DELETE CASCADE
    TABLE "article_references" CONSTRAINT "article_references_target_article_id_fkey" FOREIGN KEY (target_article_id) REFERENCES articles(id) ON DELETE SET NULL
    TABLE "articles" CONSTRAINT "articles_parent_id_fkey" FOREIGN KEY (parent_id) REFERENCES articles(id) ON DELETE CASCADE
```

### Uji Live Ekstraksi Dokumen #67 (2 Kali Pengiriman)
Header `X-Internal-API-Key` dibaca langsung dari `.env` tanpa ditampilkan.

**Payload Uji:**
```json
{
  "articles": [
    {
      "document_id": 67,
      "level": "pasal",
      "chapter_title": "BAB I KETENTUAN UMUM",
      "article_number": "Pasal 1",
      "content_text": "Pengujian live kontrak pasal untuk dokumen 67",
      "order_index": 0,
      "page": 1
    },
    {
      "document_id": 67,
      "level": "ayat",
      "chapter_title": "BAB I KETENTUAN UMUM",
      "article_number": "Ayat (1)",
      "content_text": "Ayat uji live dengan hierarki parent_order_index",
      "order_index": 1,
      "page": 1,
      "parent_order_index": 0
    }
  ]
}
```

**Output Terminal:**
```text
=== REQUEST 1 ===
HTTP Status: 200
Body: {"status":"ok","inserted_count":2,"updated_count":0,"deleted_count":0,"message":"Berhasil memproses 2 pasal: 2 baru, 0 diperbarui, 0 dihapus."}

=== REQUEST 2 ===
HTTP Status: 200
Body: {"status":"ok","inserted_count":0,"updated_count":2,"deleted_count":0,"message":"Berhasil memproses 2 pasal: 0 baru, 2 diperbarui, 0 dihapus."}
```

**Pengecekan di Database PostgreSQL Pasca Kiriman Kedua:**
```powershell
docker exec hero_postgres psql -U hero_user -d hero_db -c "SELECT id, document_id, order_index, level, article_number, page, parent_id FROM articles WHERE document_id = 67;"
```
```text
 id | document_id | order_index | level | article_number | page | parent_id 
----+-------------+-------------+-------+----------------+------+-----------
  4 |          67 |           0 | pasal | Pasal 1        |    1 |          
  5 |          67 |           1 | ayat  | Ayat (1)       |    1 |         4
(2 rows)
```

**Pembersihan Data Uji:**
```powershell
docker exec hero_postgres psql -U hero_user -d hero_db -c "DELETE FROM articles WHERE document_id = 67;"
```
```text
DELETE 2
```

```powershell
docker exec hero_postgres psql -U hero_user -d hero_db -c "SELECT count(*) FROM articles WHERE document_id = 67;"
```
```text
 count 
-------
     0
(1 row)
```

---

## 8. Status Git

### `git log --oneline -3`
```text
581c19f chore: paksa akhir baris LF untuk skrip shell
c988805 feat(deploy): cadangan DB harian ke Nextcloud + uji pemulihan (#111)
94e653b fix(security): header keamanan (QA I-09) (#110)
```

### `git status --short`
```text
 M app/models/article.py
 M app/routers/documents.py
 M app/routers/internal.py
 M app/schemas/article.py
 M docs/api/KONTRAK-API-FASE1.md
 M docs/api/openapi-fase1.json
?? alembic/versions/e5f6a7b8c9d0_step13_articles_contract.py
?? docs/reports/step13-report.md
?? tests/test_step13_articles.py
```
