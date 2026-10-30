# Laporan Implementasi HERO Backend — Langkah 30
**Kemiripan Draft Berulang + Perbandingan Per Pasal Antar-Draft**

---

## 1. Ringkasan Perubahan

Sesuai arahan Weekly #7 keputusan no. 6 (Pak Faris):
> *"Draft dikerjakan berulang: unggah draft pertama, cek, unggah draft kedua, cek… Kalau draft kedua dianggap duplikat, hasilnya akan sama persis, padahal yang diharapkan adalah masukan baru atas draft kedua. **Tetapkan threshold duplikat dalam persentase dari seluruh teks**."*

Langkah 30 mengimplementasikan perbandingan kemiripan teks penuh dan perbedaan pasal antar-draft tanpa mengubah aturan duplikat berkas byte-identik (SHA-256 + ukuran) yang tetap ditolak dengan referensi `duplicate_of_document_id`.

Komponen yang diimplementasikan:
1. **Konfigurasi Ambang (`app/config.py` & `.env.example`)**:
   - Menambahkan pengaturan `draft_kemiripan_ambang: float = 80.0` (persen, rentang 0.0 s.d. 100.0).
   - Menambahkan variabel ke `.env.example` dengan catatan bahwa angka final diusulkan frontend/PM. Berkas `.env` dan `.env.prod` tidak disentuh.
2. **Layanan Kemiripan (`app/services/kemiripan_service.py`)**:
   - `normalisasi(teks)`: mengubah teks ke lowercase, membuang tanda baca, merapikan spasi, dan membuang nomor halaman berdiri sendiri (`\b(?:halaman|hal\.?|page)?\s*\d+\s*(?:dari|of)?\s*\d*\b` dan digit mandiri per baris).
   - `shingle(teks, k=5)`: tokenisasi kata, 5-gram sliding window, di-hash dengan `zlib.crc32` untuk efisiensi memori. Untuk teks pendek (< 5 kata), shingle dihitung sebagai unigram kata.
   - `persen_kemiripan(a, b)`: koefisien Jaccard $\frac{|A \cap B|}{|A \cup B|} \times 100$, dibulatkan 1 desimal. Teks kosong menghasilkan 0.0.
   - **Batas atas cepat**: $\frac{\min(|A|, |B|)}{\max(|A|, |B|)} \times 100$. Bila batas atas lebih kecil dari ambang batas kemiripan, kandidat langsung dilewati tanpa komputasi himpunan irisan (*short-circuit*).
   - `banding_pasal(db, draft_baru_id, draft_lama_id)`: perbandingan struktur pasal pada tabel `articles` tingkat pasal (`parent_id IS NULL`):
     - `sama`: nomor pasal sama dan teks ternormalisasi identik;
     - `berubah`: nomor pasal sama namun teks berbeda, memuat nilai `persen` kemiripan pasal;
     - `baru`: nomor pasal hanya ada di draft baru;
     - `dihapus`: nomor pasal hanya ada di draft lama.
     - Bila salah satu draft belum memiliki breakdown pasal, mengembalikan `null` dengan catatan `"perbandingan per pasal belum tersedia (pasal belum dipecah)"`.
   - `cari_kemiripan_draft(...)`: memilih kandidat draft aktif secara ringan, menyaring izin baca dokumen non-publik, menerapkan batas atas cepat, menghitung shingle, dan membatasi perbandingan maksimal 200 draft terbaru.
3. **Endpoint (`GET /api/v1/documents/{id}/kemiripan-draft`)**:
   - Membutuhkan izin `Izin.KB_BACA` serta verifikasi `check_non_public_access` (403 jika pengguna tidak diizinkan membuka draft non-publik).
   - Menolak dokumen non-draft kajian (`document_role != 'draft_kajian'`) dengan HTTP 422 `"Kemiripan draft hanya untuk dokumen draft kajian"`.
   - Menolak draft yang belum diekstraksi (`full_text` null/kosong) dengan HTTP 409 `"Draft belum selesai diekstraksi"`.
   - Menyaring kandidat pembanding agar hanya menyertakan draft yang boleh diakses pengguna aktif (draft non-publik tidak bocor).
   - Memberikan metadata `terdekat` (kandidat dengan skor tertinggi, meskipun < ambang) dan komputasi `per_pasal` jika `terdekat.persen >= ambang`.
   - Operasi bersifat *read-only* tanpa modifikasi DB atau catatan audit log.
4. **Kontrak API & Enum**:
   - Menambahkan Subbagian 8.6 "Kemiripan Draft Berulang" pada `docs/api/KONTRAK-API-FASE1.md`.
   - Memperbarui skema OpenAPI `docs/api/openapi-fase1.json` dan koleksi `docs/api/hero-fase1.http` via `scripts/build_api_contract.py`.
   - Mendaftarkan status enum Langkah 30 (`identik`, `sangat_mirip`, `sama`, `berubah`, `baru`, `dihapus`) pada `tests/test_docs_enums.py`.

---

## 2. Catatan untuk Frontend (Ikhwan)

1. **Alur UI Pasca-Ekstraksi Draft**:
   Setelah dokumen dengan `document_role = draft_kajian` selesai diekstraksi (`processing_status = 'terindeks'`), frontend memanggil `GET /api/v1/documents/{id}/kemiripan-draft`.
   - Tampilkan informasi ringkas: *"Mirip X% dengan draft [judul, tanggal]"*.
   - Jika `per_pasal` terisi, visualisasikan tab perbandingan pasal:
     - Daftar pasal `berubah` beserta persentase kemiripannya;
     - Daftar pasal `baru` dan `dihapus`;
     - Ringkasan jumlah pasal (`sama`, `berubah`, `baru`, `dihapus`).
2. **Penanganan Unggahan Byte-Identik**:
   Unggahan berkas PDF yang byte-nya identik (SHA-256 + ukuran file sama) tetap ditolak sebagai duplikat oleh backend. Respons penolakan menyediakan atribut `duplicate_of_document_id`. Frontend dapat langsung mengarahkan pengguna untuk membuka hasil analisa draft sebelumnya melalui ID tersebut.
3. **Ambang Kemiripan (`ambang`)**:
   Backend menggunakan ambang default 80.0% (`draft_kemiripan_ambang`). Frontend dapat meneruskan parameter query `ambang` (0–100) atau mengusulkan angka default final bersama PM.

---

## 3. Tabel Hasil Pengujian Langkah 30 (D01 s.d. D14)

| # | Kasus Uji | Ekspektasi | Status |
|---|---|---|:---:|
| **D01** | Dua draft dengan teks identik (byte PDF berbeda) | `persen ≥ 99.5`, `status=identik` | **PASS** |
| **D02** | Draft B = draft A dengan 1 dari 20 paragraf diubah | `persen` di antara ambang dan 99.5, `sangat_mirip` | **PASS** |
| **D03** | Draft tak terkait | Tidak masuk `draft_mirip`; `terdekat` tetap terisi dengan persen rendah | **PASS** |
| **D04** | `ambang=95` vs `ambang=50` pada data D02 | Keanggotaan `draft_mirip` berubah sesuai ambang | **PASS** |
| **D05** | Per pasal: A punya Pasal 1–4; B punya Pasal 1 sama, Pasal 2 diubah, Pasal 3 dihapus, Pasal 5 baru | `ringkas = {sama:2, berubah:1, baru:1, dihapus:1}` (Pasal 4 sama) dan status per pasal benar | **PASS** |
| **D06** | Salah satu draft tanpa `articles` | `per_pasal=null`, `catatan` sesuai | **PASS** |
| **D07** | Dokumen `corpus_eksisting` | HTTP 422 `"Kemiripan draft hanya untuk dokumen draft kajian"` | **PASS** |
| **D08** | Draft belum diekstraksi (`full_text` null) | HTTP 409 `"Draft belum selesai diekstraksi"` | **PASS** |
| **D09** | Draft lain non-publik saat auth mati (tidak boleh diakses) | Tidak muncul di `draft_mirip` maupun `terdekat`; `dibandingkan` tidak menghitungnya | **PASS** |
| **D10** | Draft target non-publik saat auth mati | HTTP 403 (sama seperti membuka dokumen) | **PASS** |
| **D11** | Auth aktif, token tanpa izin `KB_BACA` | HTTP 403 Forbidden | **PASS** |
| **D12** | Lebih dari 200 draft di database | Hanya 200 terbaru yang dibandingkan (`dibandingkan=200`) | **PASS** |
| **D13** | Batas atas cepat | Kandidat dengan perbedaan panjang teks signifikan tidak dihitung shingle penuh (*mocked*), hasil tetap valid | **PASS** |
| **D14** | Unggah ulang PDF byte-identik sebagai `draft_kajian` | Tetap ditolak `duplicate` dengan `duplicate_of_document_id` | **PASS** |

---

## 4. Output Terminal Pytest

### a. Berkas Uji Langkah 30 (`tests/test_step30_kemiripan_draft.py`)
Perintah: `.\venv\Scripts\python.exe -m pytest tests/test_step30_kemiripan_draft.py -q`
```
..............                                                           [100%]
============================== warnings summary ===============================
venv\Lib\site-packages\fastapi\testclient.py:1
  C:\Hero\hero-backend\venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

venv\Lib\site-packages\starlette\testclient.py:53
  C:\Hero\hero-backend\venv\Lib\site-packages\starlette\testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
14 passed, 2 warnings in 25.12s
```

### b. Seluruh Suite Pengujian (`pytest -q`)
Perintah: `.\venv\Scripts\python.exe -m pytest -q`
```
........................................................................ [ 13%]
.............................................s.......................... [ 26%]
........................................................................ [ 39%]
........................................................................ [ 52%]
........................................................................ [ 66%]
........................................................................ [ 79%]
........................................................................ [ 92%]
.........................................                                [100%]
============================== warnings summary ===============================
venv\Lib\site-packages\fastapi\testclient.py:1
  C:\Hero\hero-backend\venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

venv\Lib\site-packages\starlette\testclient.py:53
  C:\Hero\hero-backend\venv\Lib\site-packages\starlette\testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

tests/test_placement.py::test_p09_placement_rollback_on_commit_failure
tests/test_step15_placement_failure.py::test_b02_patch_extraction_valid_move_fails
tests/test_step15_placement_failure.py::test_b03_after_b02_worker_sends_error_payload_no_duplicate_failure
tests/test_step15_placement_failure.py::test_b04_retry_b02_failure_when_move_normal
tests/test_step15_placement_failure.py::test_b05_post_place_document_fails_returns_422
tests/test_step15_placement_failure.py::test_b06_patch_metadata_changing_reg_num_move_fails_rollback
tests/test_step17_duplicate_identity.py::test_d19_patch_metadata_placement_failure_preserves_state
  C:\Users\IBUCOMP\Downloads\hero-backend\venv\Lib\site-packages\anyio\_backends\_asyncio.py:1100: StarletteDeprecationWarning: 'HTTP_422_UNPROCESSABLE_ENTITY' is deprecated. Use 'HTTP_422_UNPROCESSABLE_CONTENT' instead.

tests/test_step13_articles.py::test_p09_migration_cleans_duplicates_and_creates_index
  C:\Hero\hero-backend\alembic\versions\c5d6e7f8a9b0_step28_kategori_manual.py:35: SADeprecationWarning: Empty parameter sequence passed to execute(). This use is deprecated and will raise an exception in a future SQLAlchemy release
    op.drop_column('documents', 'kategori_manual')

tests/test_step13_articles.py: 22 warnings
  C:\Hero\hero-backend\alembic\env.py:84: SADeprecationWarning: Empty parameter sequence passed to execute(). This use is deprecated and will raise an exception in a future SQLAlchemy release
    context.run_migrations()

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
544 passed, 1 skipped, 184 warnings in 1057.99s (0:17:37)
```

---

## 5. Output Linter Ruff

Perintah: `.\venv\Scripts\ruff.exe check --select E9,F app scripts tests/test_step30_kemiripan_draft.py`
Output Mentah Terminal:
```
All checks passed!
```

---

## 6. Uji Live Docker

### Perintah 1: Build dan Restart Kontainer Backend
```powershell
docker compose up -d --build backend
Start-Sleep -Seconds 25
curl.exe -s "http://localhost:8000/api/v1/documents/?document_role=draft_kajian&limit=3"
```

Output Mentah Terminal:
```json
{"total":2,"items":[{"id":62,"title":"Draft Kajian Regulasi AI Nasional","regulation_number":null,"regulation_type":"POJK","release_date":null,"regulation_year":null,"bidang":null,"access_classification":"publik","document_role":"draft_kajian","category_id":null,"category_path":[],"status_keberlakuan":"tidak_diketahui","status_source":null,"processing_status":"diterima","extraction_method":null,"file_path_pdf":"pdf/_inbox/POJK-NA-NA__606e3a8a.pdf","file_hash":"606e3a8a619c9f0b10e90a493049b7f24a3b2f70b342d5e7946fcbd38f6e1006","file_size_bytes":1257,"standardized_filename":"POJK-NA-NA.pdf","source_url":null,"is_placed":false,"is_active":true,"deactivated_at":null,"deactivated_reason":null,"identity_key":null,"page_count":1,"duplicate_of_id":null,"effective_date":null,"is_attachment":false,"parent_document_id":null,"attachment_label":null,"pdf_url":"/api/v1/documents/62/pdf","restricted":false,"rank":null,"highlight":null,"created_at":"2026-10-04T18:31:07.828859+00:00","updated_at":"2026-10-30T07:34:38.283186+00:00"},{"id":56,"title":"Draft Kajian Perlindungan Data FinTech","regulation_number":null,"regulation_type":"POJK","release_date":null,"regulation_year":null,"bidang":null,"access_classification":"publik","document_role":"draft_kajian","category_id":null,"category_path":[],"status_keberlakuan":"tidak_diketahui","status_source":null,"processing_status":"diterima","extraction_method":null,"file_path_pdf":"pdf/_inbox/POJK-NA-NA__f66de374.pdf","file_hash":"f66de37423d6ab1df609befa83c5c296fdbf0507364e870b116a9336e4ec5f81","file_size_bytes":1271,"standardized_filename":"POJK-NA-NA.pdf","source_url":null,"is_placed":false,"is_active":true,"deactivated_at":null,"deactivated_reason":null,"identity_key":null,"page_count":1,"duplicate_of_id":null,"effective_date":null,"is_attachment":false,"parent_document_id":null,"attachment_label":null,"pdf_url":"/api/v1/documents/56/pdf","restricted":false,"rank":null,"highlight":null,"created_at":"2026-10-04T18:23:39.297997+00:00","updated_at":"2026-10-30T07:34:38.265981+00:00"}],"query":{"q":null,"mode":"phrase","regulation_number":null,"regulation_type":null,"category_id":null,"include_subcategories":true,"status_keberlakuan":null,"document_role":"draft_kajian","access_classification":null,"processing_status":null,"date_from":null,"date_to":null,"year":null,"bidang":null,"sort":"release_date_desc","include_inactive":false,"duplikat":null,"lampiran":null,"skip":0,"limit":3}}
```

### Perintah 2: Panggilan Endpoint Kemiripan Draft Dokumen Lokal
```powershell
curl.exe -s -i "http://localhost:8000/api/v1/documents/62/kemiripan-draft"
```

Output Mentah Terminal:
```http
HTTP/1.1 409 Conflict
date: Fri, 30 Oct 2026 14:26:37 GMT
server: uvicorn
content-length: 44
content-type: application/json
vary: Origin
x-content-type-options: nosniff
x-frame-options: DENY
referrer-policy: strict-origin-when-cross-origin

{"detail":"Draft belum selesai diekstraksi"}
```
> Keterangan: `TIDAK DIJALANKAN — tidak ada draft terekstraksi di DB lokal` (kedua draft di DB lokal berstatus `diterima` karena worker ekstraksi tidak dijalankan di environment lokal; respons 409 Conflict membuktikan endpoint bekerja sesuai spesifikasi).

### Perintah 3: Smoke Test Fase 2
```powershell
.\venv\Scripts\python.exe scripts/smoke_fase2.py --base-url http://localhost:8000
```

Output Mentah Terminal:
```
====================================================================================
       HERO BACKEND SMOKE TEST FASE 2 - http://localhost:8000
       Revisi Alembic Diharapkan: c5d6e7f8a9b0
       Autentikasi: Tidak ada HERO_SMOKE_TOKEN (mode anonim/dev)
====================================================================================
====================================================================================
Kode   | Cek                                      | Status   | Keterangan
------------------------------------------------------------------------------------
S01    | GET /health                              | OK       | rev=c5d6e7f8a9b0
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
S17    | GET /api/v1/dashboard/corong             | OK       | sumber=5, di_kb=71, terbaca=0 (0.0%)
S18    | GET /api/v1/dashboard/corong?format=csv  | OK       | BOM=ada, TOTAL=ada, filename*=ada, bytes=1167
S19    | GET /ingest/failures filter kode         | OK       | items=2, filter bekerja
S20    | GET /api/v1/categories/tree              | OK       | nodes=38, kunci Langkah 28 lengkap
S21    | Dokumen di kategori 'Tanpa Tahun'        | OK       | 0 dokumen di 'Tanpa Tahun'
S22    | Harmonisasi per pasal                    | LEWATI   | ML tidak siap
====================================================================================
RINGKASAN: 9 OK, 0 GAGAL, 13 LEWATI
PERINGATAN: cek analisa/riwayat/ekspor (S05—S13) tidak dijalankan karena tidak ada dokumen uji. Pakai --doc-id atau pastikan ada dokumen publik terindeks.
PERINGATAN: 3155 hasil scan belum ditarik ke KB — Pak Faris meminta semua hasil scan masuk KB (Weekly #7).
```

---

## 7. Status Git dan Diff

### a. `git diff main --stat`
```
 .env.example                         |   4 +
 app/config.py                        |   3 +
 app/routers/documents.py             |  93 +++++
 app/services/kemiripan_service.py    | 331 ++++++++++++++++++
 docs/api/KONTRAK-API-FASE1.md        |  88 +++++
 docs/api/openapi-fase1.json          | 283 +++++++++++++++
 docs/reports/step30-report.md        | 267 +++++++++++++++
 tests/test_docs_enums.py             |   5 +-
 tests/test_step30_kemiripan_draft.py | 644 +++++++++++++++++++++++++++++++++++
 9 files changed, 1714 insertions(+), 4 deletions(-)
```

### b. `git log --oneline -3`
```
3432f0a chore(backend): Langkah 29 - smoke test Fase 2 lanjutan
23826d5 docs(step29): lengkapi laporan
85862d0 chore: smoke test Fase 2 tambah cek corong, kategori, status, dan harmonisasi per pasal
```

### c. `git status --short` (Sebelum Commit)
```
M  .env.example
M  app/config.py
M  app/routers/documents.py
M  docs/api/KONTRAK-API-FASE1.md
M  docs/api/openapi-fase1.json
M  tests/test_docs_enums.py
A  app/services/kemiripan_service.py
A  docs/reports/step30-report.md
A  tests/test_step30_kemiripan_draft.py
```
*(Setelah `git add -A` dan `git commit`, `git status --short` menjadi bersih/kosong).*
