# Laporan Langkah 14 HERO Backend (US-30: Nonaktifkan & Pindahkan Dokumen)

**Tanggal:** 10 Oktober 2026  
**Branch:** `feat/step14-nonaktif-dokumen`  
**Base Commit:** `2ef90a1` (Langkah 13: Kontrak Pasal Lapisan Data)  
**Referensi:** US-30, FR-KB-08, TC-15

---

## 1. Ringkasan Eksekutif

Langkah 14 mengimplementasikan kemampuan administratif bagi Admin KB untuk menonaktifkan dan mengaktifkan kembali dokumen regulasi tanpa menghapus berkas fisik PDF (`is_active = false`), serta membuktikan alur pemindahan kategori dokumen yang telah ada lewat `PATCH /api/v1/documents/{id}/metadata`.

Perbedaan konseptual mendasar:
- **Status Keberlakuan Hukum (`status_keberlakuan: berlaku | diubah | dicabut`)**: Dokumen tetap tampil di Knowledge Base dengan penanda keberlakuan hukum.
- **Status Administratif Aktif (`is_active: bool`)**: Dokumen yang salah unggah, bukan regulasi, atau duplikat disembunyikan dari antarmuka Knowledge Base dan metrik statistik, namun berkas fisik tetap tersimpan aman dan dokumen dapat diaktifkan kembali sewaktu-waktu.

---

## 2. Catatan Integrasi

### Catatan untuk frontend
1. **Endpoint Baru Penonaktifan & Pengaktifan:**
   - `PUT /api/v1/documents/{document_id}/active`
   - Request Body:
     ```json
     {
       "is_active": false,
       "reason": "Salah unggah: bukan dokumen regulasi"
     }
     ```
   - Validasi: Saat `is_active: false`, `reason` wajib diisi minimal 5 karakter (setelah trim). Jika kurang, server mengembalikan 422 Unprocessable Entity. Saat `is_active: true`, `reason` bersifat opsional.
   - Respons `200 OK`:
     ```json
     {
       "document_id": 71,
       "is_active": false,
       "changed": true,
       "deactivated_at": "2026-10-10T09:41:49.375689Z",
       "deactivated_reason": "Salah unggah: bukan dokumen regulasi",
       "message": "Dokumen #71 ('POJK 21 Tahun 2023') berhasil dinonaktifkan."
     }
     ```
   - Idempoten: Jika status dokumen sudah sesuai yang diminta, server mengembalikan `changed: false` tanpa membuat entri audit baru.
2. **Field Baru pada Dokumen:**
   - Respons detail dokumen (`GET /documents/{id}`) dan seluruh item daftar dokumen (`GET /documents/`) kini memuat:
     - `is_active: bool`
     - `deactivated_at: string | null`
     - `deactivated_reason: string | null`
3. **Parameter Filter Pencarian Baru:**
   - `GET /api/v1/documents/?include_inactive=true`
   - Default: `include_inactive=false` (hanya menampilkan dokumen aktif). Jika diset `true`, dokumen nonaktif ikut tampil.
4. **Deteksi Duplikat pada Pindai & Unggah:**
   - Skema `CandidateMatchDocument` dan `DuplicateDocumentInfo` kini menyertakan `is_active: bool`. UI dapat menampilkan penanda visual seperti *"Sudah ada (nonaktif)"*.
5. **Metrik Dashboard Baru:**
   - Respons `GET /api/v1/dashboard/summary` pada objek `kb` menambahkan `inactive_documents: int`. Seluruh hitungan `kb.corpus_documents`, `kb.by_status_keberlakuan`, `kb.by_processing_status`, `kb.by_regulation_type`, dan `kb.by_year` kini hanya menghitung dokumen aktif.

### Catatan untuk lapisan data
1. **Antrean Ekstraksi:**
   - Endpoint klaim ekstraksi `POST /api/v1/internal/articles` dan antrean klaim `POST /api/v1/internal/extraction/claim` otomatis **tidak mengklaim dokumen nonaktif** (`documents.is_active = true`). Dokumen nonaktif yang berada dalam antrean akan dilewati.
2. **Cermin Korpus & Harmonisasi:**
   - Pipeline harmonisasi regulasi dan pencarian rujukan silang pasal sebaiknya memfilter `documents.is_active = true` agar dokumen administratif nonaktif tidak dijadikan rujukan rekomendasi atau pembanding hukum.

---

## 3. Skema Database & Migrasi

Migrasi aditif baru: `f6a7b8c9d0e1_step14_deactivate_document.py` (`down_revision = 'e5f6a7b8c9d0'`).

### Kolom Baru pada Tabel `documents`
- `is_active` — `Boolean`, `nullable=False`, `server_default=true`, indexed.
- `deactivated_at` — `DateTime(timezone=True)`, nullable.
- `deactivated_reason` — `Text`, nullable.
- `deactivated_by` — `Integer`, FK `users.id`, nullable, `ondelete='SET NULL'`, indexed.

### Pengujian Migrasi (Upgrade & Downgrade)
Output eksekusi terminal:
```
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running downgrade f6a7b8c9d0e1 -> e5f6a7b8c9d0, step14 deactivate document
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade e5f6a7b8c9d0 -> f6a7b8c9d0e1, step14 deactivate document
```

---

## 4. Evaluasi Query `Document` di Seluruh Kode Sumber (§3)

Hasil audit menyeluruh terhadap `grep -rn "query(Document" app`:

| File & Baris | Operasi / Query | Keputusan | Alasan |
|---|---|---|---|
| `app/services/scan_service.py:325` | Cek hash duplikat kandidat scan | **Tidak disaring** | Mencegah dokumen nonaktif ter-scan ulang sebagai dokumen baru. |
| `app/services/scan_service.py:343` | Cek URL duplikat kandidat scan | **Tidak disaring** | Mencegah URL yang sudah ada masuk kembali. |
| `app/services/scan_service.py:588` | Batch lookup URL kandidat | **Tidak disaring** | Evaluasi perbandingan kandidat scan dengan korpus eksisting. |
| `app/services/scan_service.py:595` | Batch lookup file size kandidat | **Tidak disaring** | Evaluasi perbandingan kandidat scan dengan korpus eksisting. |
| `app/services/placement_service.py:218` | Relokasi kategori berkas dokumen | **Tidak disaring** | Operasi pemindahan fisik kategori tetap berlaku pada berkas dokumen terkait. |
| `app/services/ingest_service.py:242` | Cek hash duplikat saat unggah | **Tidak disaring** | Dokumen nonaktif tetap memicu status duplikat dengan penanda `is_active: false`. |
| `app/services/ingest_service.py:450` | Cek hash kegagalan ingest | **Tidak disaring** | Lookup integritas berkas pada antrean kegagalan. |
| `app/services/failure_service.py:373` | Lookup dokumen kegagalan ingest | **Tidak disaring** | Lookup berdasarkan primary key dokumen. |
| `app/services/category_service.py:150` | Agregasi pohon kategori (`/tree`) | **Disaring (`is_active = True`)** | `document_count` dan `total_document_count` hanya menghitung dokumen aktif. |
| `app/routers/naming.py:96` | Pratinjau penamaan dokumen | **Tidak disaring** | Admin KB dapat melihat pratinjau penamaan dokumen berdasarkan ID. |
| `app/routers/internal.py:315` | Antrean klaim ekstraksi (`/claim`) | **Disaring (`is_active = True`)** | Dokumen nonaktif tidak boleh diklaim untuk pemrosesan ekstraksi pasal. |
| `app/routers/internal.py:359` | Update status ekstraksi selesai | **Tidak disaring** | Callback hasil worker berdasarkan ID dokumen. |
| `app/routers/internal.py:402` | Lapor kegagalan ekstraksi worker | **Tidak disaring** | Callback error worker berdasarkan ID dokumen. |
| `app/routers/internal.py:612` | Reset percobaan ekstraksi | **Tidak disaring** | Operasi perbaikan administratif per ID. |
| `app/routers/ingest.py:738` | Cek duplikat manual upload single | **Tidak disaring** | Menjaga integritas deduplikasi ingest. |
| `app/routers/ingest.py:765` | Cek duplikat manual upload batch | **Tidak disaring** | Menjaga integritas deduplikasi ingest. |
| `app/routers/ingest.py:803` | Hitung total teknis `/ingest/status` | **Tidak disaring** | Endpoint teknis pipeline melaporkan jumlah fisik record dokumen di database. |
| `app/routers/documents.py:214` | Antrean review (`/needs-review`) | **Disaring (`is_active = True`)** | Dokumen nonaktif tidak masuk ke antrean koreksi metadata aktif. |
| `app/routers/documents.py:362` | Detail dokumen (`GET /documents/{id}`) | **Tidak disaring** | Admin KB tetap dapat melihat detail dokumen nonaktif untuk kebutuhan audit. |
| `app/routers/documents.py:389` | Teks dokumen (`GET /documents/{id}/text`)| **Tidak disaring** | Admin KB tetap dapat membaca teks dokumen nonaktif. |
| `app/routers/documents.py:457` | Berkas PDF (`GET /documents/{id}/pdf`) | **Tidak disaring** | Berkas fisik tidak dihapus dan tetap bisa dibuka oleh Admin KB. |
| `app/routers/documents.py:497` | Koreksi metadata (`PATCH /metadata`) | **Tidak disaring** | Perbaikan metadata tetap diizinkan pada dokumen nonaktif. |
| `app/routers/documents.py:630` | Pemicu penempatan (`POST /place`) | **Tidak disaring** | Penataan folder fisik tetap boleh dipicu. |
| `app/routers/documents.py:684` | Status keberlakuan (`PUT /status`) | **Tidak disaring** | Status hukum tetap boleh diperbarui pada dokumen nonaktif. |
| `app/routers/documents.py:691` | Dokumen pencabut status keberlakuan | **Tidak disaring** | Lookup dokumen pencabut berdasarkan ID. |
| `app/routers/documents.py:807` | Update status aktif (`PUT /active`) | **Tidak disaring** | Target utama endpoint aktivasi/penonaktifan. |
| `app/routers/dashboard.py:60` | Statistik status keberlakuan KB | **Disaring (`is_active = True`)** | Hanya menghitung dokumen regulasi aktif. |
| `app/routers/dashboard.py:73` | Statistik status pemrosesan KB | **Disaring (`is_active = True`)** | Hanya menghitung dokumen regulasi aktif. |
| `app/routers/dashboard.py:85` | Statistik jenis regulasi KB | **Disaring (`is_active = True`)** | Hanya menghitung dokumen regulasi aktif. |
| `app/routers/dashboard.py:97` | Statistik per tahun regulasi KB | **Disaring (`is_active = True`)** | Hanya menghitung dokumen regulasi aktif. |
| `app/routers/dashboard.py:139` | Statistik antrean koreksi dashboard | **Disaring (`is_active = True`)** | Hanya menghitung dokumen regulasi aktif. |
| `app/routers/categories.py:62` | Detail kategori (`GET /categories/{id}`)| **Disaring (`is_active = True`)** | `document_count` kategori hanya menghitung dokumen aktif. |
| `app/services/search_service.py:146` | Daftar dokumen (`GET /documents/`) | **Disaring (`is_active = True`)** | Default menyaring dokumen aktif; nonaktif ikut jika `include_inactive=true`. |

---

## 5. Hasil Pengujian Unit & Integrasi (`tests/test_step14_active.py`)

Tabel verifikasi skenario N01 s.d. N11:

| # | Kasus Uji | Ekspektasi | Hasil |
|---|---|---|---|
| **N01** | Nonaktifkan dengan alasan valid (>= 5 kar.) | 200, `changed: true`, kolom terisi, audit `DEACTIVATE_DOCUMENT` memuat alasan | **PASSED** |
| **N02** | Nonaktifkan tanpa alasan / alasan < 5 kar. | 422 Unprocessable Entity, data di DB tidak berubah | **PASSED** |
| **N03** | Nonaktifkan dua kali (idempoten) | Kedua 200, `changed: false`, hanya 1 entri audit yang dibuat | **PASSED** |
| **N04** | `GET /documents/` penyaringan aktif | Nonaktif tidak muncul default; muncul jika `include_inactive=true` | **PASSED** |
| **N05** | `GET /documents/{id}` dan `/pdf` dokumen nonaktif | 200 OK, `is_active: false`, berkas PDF tetap dapat diakses | **PASSED** |
| **N06** | Dashboard dan `/categories/tree` | Angka berkurang 1; `inactive_documents` = 1 | **PASSED** |
| **N07** | Unggah ulang berkas hash sama dari dokumen nonaktif | Terdeteksi duplikat, `duplicate_of_document.is_active == false` | **PASSED** |
| **N08** | Aktifkan kembali dokumen | Kolom dinolkan; kembali tampil di daftar & statistik; audit `ACTIVATE_DOCUMENT` | **PASSED** |
| **N09** | Pindah kategori lewat `PATCH /metadata` `category_id` | Berkas berpindah folder; audit `UPDATE_METADATA` memuat before/after `category_id` (TC-15) | **PASSED** |
| **N10** | Klaim ekstraksi internal | Dokumen nonaktif diabaikan dari antrean klaim | **PASSED** |
| **N11** | Dokumen ID tidak ditemukan | 404 Not Found | **PASSED** |

### Output Pytest Spesifik Step 14
```
tests/test_step14_active.py::test_n01_deactivate_with_reason PASSED      [  9%]
tests/test_step14_active.py::test_n02_deactivate_without_reason_or_too_short PASSED [ 18%]
tests/test_step14_active.py::test_n03_deactivate_idempotent_twice PASSED [ 27%]
tests/test_step14_active.py::test_n04_get_documents_filtering PASSED     [ 36%]
tests/test_step14_active.py::test_n05_get_inactive_document_detail_and_pdf PASSED [ 45%]
tests/test_step14_active.py::test_n06_dashboard_and_category_tree PASSED [ 54%]
tests/test_step14_active.py::test_n07_duplicate_detection_matches_inactive PASSED [ 63%]
tests/test_step14_active.py::test_n08_reactivate_document PASSED         [ 72%]
tests/test_step14_active.py::test_n09_move_category_via_patch_metadata PASSED [ 81%]
tests/test_step14_active.py::test_n10_extraction_claim_ignores_inactive PASSED [ 90%]
tests/test_step14_active.py::test_n11_deactivate_non_existent_document PASSED [100%]
======================= 11 passed, 2 warnings in 14.51s =======================
```

---

## 6. Uji Live pada Dokumen #71 (POJK 21 Tahun 2023)

### 6.1. Build & Health Check
```powershell
docker compose up -d --build backend
Start-Sleep -Seconds 15
curl.exe -s http://localhost:8000/health
```
Output mentah:
```json
{"status":"ok","database":"ok","version":"0.10.0","app_env":"development","alembic_revision":"f6a7b8c9d0e1","alembic_head":"f6a7b8c9d0e1","migrations_up_to_date":true,"storage_writable":true,"crawler_backend":"simple_http","crawler_loaded":true,"auth_enabled":false,"protect_non_public":true}
```

### 6.2. Baseline Awal Sebelum Nonaktif
```powershell
curl.exe -s http://localhost:8000/api/v1/dashboard/summary
```
Output mentah cuplikan:
```json
{"kb":{"corpus_documents":69,"draft_documents":2,"inactive_documents":0,"target_fase1":20,"target_met":true,"by_status_keberlakuan":{"berlaku":10,"diubah":2,"dicabut":2,"tidak_diketahui":57},"placed_documents":57,"inbox_documents":14}}
```

Pencarian POJK 21:
```powershell
curl.exe -s "http://localhost:8000/api/v1/documents/?q=POJK+21"
```
Output mentah:
```json
{"total":1,"items":[{"id":71,"title":"POJK 21 2023 Layanan Digital Bank Umum","regulation_number":"POJK 21 Tahun 2023","regulation_type":"POJK","is_active":true,"deactivated_at":null,"deactivated_reason":null,"rank":2.0}]}
```

### 6.3. Nonaktifkan Dokumen #71
```powershell
curl.exe -s -X PUT http://localhost:8000/api/v1/documents/71/active -H "Content-Type: application/json" --data-raw "{\"is_active\": false, \"reason\": \"Uji Langkah 14\"}"
```
Output mentah:
```json
{"document_id":71,"is_active":false,"changed":true,"deactivated_at":"2026-10-10T09:41:49.375689Z","deactivated_reason":"Uji Langkah 14","message":"Dokumen #71 ('POJK 21 Tahun 2023') berhasil dinonaktifkan."}
```

### 6.4. Verifikasi Tersembunyi dari Pencarian & Dashboard Berkurang 1
Pencarian default (`q=POJK 21`):
```powershell
curl.exe -s "http://localhost:8000/api/v1/documents/?q=POJK+21"
```
Output mentah:
```json
{"total":0,"items":[],"query":{"q":"POJK 21","mode":"phrase"}}
```

Pencarian dengan `include_inactive=true`:
```powershell
curl.exe -s "http://localhost:8000/api/v1/documents/?q=POJK+21&include_inactive=true"
```
Output mentah:
```json
{"total":1,"items":[{"id":71,"title":"POJK 21 2023 Layanan Digital Bank Umum","regulation_number":"POJK 21 Tahun 2023","is_active":false,"deactivated_at":"2026-10-10T09:41:49.375689+00:00","deactivated_reason":"Uji Langkah 14"}]}
```

Dashboard setelah penonaktifan:
```powershell
curl.exe -s http://localhost:8000/api/v1/dashboard/summary
```
Output mentah:
```json
{"kb":{"corpus_documents":68,"draft_documents":2,"inactive_documents":1,"target_fase1":20,"target_met":true,"placed_documents":56,"inbox_documents":14}}
```
*(Catatan: `corpus_documents` turun dari 69 menjadi 68, dan `inactive_documents` bertambah menjadi 1).*

### 6.5. Aktifkan Kembali Dokumen #71
```powershell
curl.exe -s -X PUT http://localhost:8000/api/v1/documents/71/active -H "Content-Type: application/json" --data-raw "{\"is_active\": true}"
```
Output mentah:
```json
{"document_id":71,"is_active":true,"changed":true,"deactivated_at":null,"deactivated_reason":null,"message":"Dokumen #71 ('POJK 21 Tahun 2023') berhasil diaktifkan kembali."}
```

Verifikasi pencarian pulih:
```powershell
curl.exe -s "http://localhost:8000/api/v1/documents/?q=POJK+21"
```
Output mentah:
```json
{"total":1,"items":[{"id":71,"title":"POJK 21 2023 Layanan Digital Bank Umum","regulation_number":"POJK 21 Tahun 2023","is_active":true,"deactivated_at":null,"deactivated_reason":null}]}
```

Verifikasi dashboard pulih:
```powershell
curl.exe -s http://localhost:8000/api/v1/dashboard/summary
```
Output mentah:
```json
{"kb":{"corpus_documents":69,"draft_documents":2,"inactive_documents":0,"target_fase1":20,"target_met":true,"placed_documents":57,"inbox_documents":14}}
```

### 6.6. Entri Audit Log Live
```powershell
curl.exe -s "http://localhost:8000/api/v1/audit-logs/?limit=2"
```
Output mentah:
```json
[
  {
    "id": 230,
    "user_id": null,
    "action": "ACTIVATE_DOCUMENT",
    "target_resource": "document:71",
    "detail": {
      "after": {"is_active": true},
      "before": {"is_active": false},
      "reason": null
    },
    "ip_address": "172.21.0.1",
    "timestamp": "2026-10-10T09:42:27.648198+00:00"
  },
  {
    "id": 229,
    "user_id": null,
    "action": "DEACTIVATE_DOCUMENT",
    "target_resource": "document:71",
    "detail": {
      "after": {"is_active": false},
      "before": {"is_active": true},
      "reason": "Uji Langkah 14"
    },
    "ip_address": "172.21.0.1",
    "timestamp": "2026-10-10T09:41:49.379833+00:00"
  }
]
```

---

## 7. Status Kontrak OpenAPI & Linter

### 7.1. Git Diff Stat Kontrak OpenAPI
```
docs/api/openapi-fase1.json | 172 ++++++++++++++++++++++++++++++++++++++++++++
1 file changed, 172 insertions(+)
```

### 7.2. Hasil Ruff Check
```powershell
.\venv\Scripts\ruff.exe check --select E9,F821,F822,F823 app scripts tests
```
Output:
```
All checks passed!
```

### 7.3. Hasil Seluruh Test Suite
```powershell
.\venv\Scripts\python.exe -m pytest -q
```
Output:
```
262 passed, 1 skipped, 28 warnings in 297.14s (0:04:57)
```
*(Seluruh 262 pengujian lulus 100%, 0 failed, 0 error).*

---

## 8. Ringkasan File & Git Status

### Commit yang Dilakukan
Branch: `feat/step14-nonaktif-dokumen`
Komit memuat:
1. `alembic/versions/f6a7b8c9d0e1_step14_deactivate_document.py`
2. `app/models/document.py`
3. `app/services/audit_service.py`
4. `app/schemas/article.py`
5. `app/schemas/scan.py`
6. `app/schemas/ingest.py`
7. `app/routers/documents.py`
8. `app/routers/dashboard.py`
9. `app/routers/categories.py`
10. `app/services/category_service.py`
11. `app/services/search_service.py`
12. `app/routers/internal.py`
13. `tests/test_step14_active.py`
14. `docs/api/openapi-fase1.json`
15. `docs/api/KONTRAK-API-FASE1.md`
16. `docs/reports/step14-report.md`
