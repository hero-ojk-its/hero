# LAPORAN LANGKAH 18: Versioning Dokumen (Relasi Mengubah & Mencabut, US-29 #37)

**Branch:** `feat/step18-versioning`  
**Tanggal:** 16 Oktober 2026  
**Status:** SELESAI  

---

## 1. Ringkasan Perubahan

### Bagian A — Perapian Import Tak Terpakai (Commit A: `6a0c912`)
- Menjalankan `.\venv\Scripts\ruff.exe check --select F401 --fix app scripts` untuk membersihkan 78 import yang tidak terpakai pada kode aplikasi dan skrip utilitas.
- Mengecualikan seluruh berkas `__init__.py` agar re-export modul tetap terjaga dengan aman.
- Terverifikasi dengan eksekusi ruff bersih dan seluruh test suite lulus (319 passed, 1 skipped).
- Dibuat dalam commit terpisah: `6a0c912 chore: hapus import tak terpakai`.

### Bagian B — Versioning Dokumen: Relasi Mengubah dan Mencabut (Commit B)
1. **Model Relasi Dokumen & Kolom Dokumen Baru**:
   - `app/models/enums.py`: Menambahkan enum `JenisRelasi` (`mengubah`, `mencabut`).
   - `app/models/document_relation.py`: Membuat model `DocumentRelation` yang memetakan relasi antarperaturan berdasarkan kunci identitas (`source_key`, `target_key`, `relation`, `partial`, `articles_text`, `origin`, `evidence`). Memiliki batasan unik komposit `(source_key, target_key, relation)`.
   - `app/models/document.py`: Menambahkan kolom `status_source` (`manual | relasi | lapisan_data | null`) pada tabel `documents`.
   - `app/models/__init__.py`: Melakukan re-export `JenisRelasi` dan `DocumentRelation`.
2. **Migrasi Database (`b8c9d0e1f2a3_step18_document_relations.py`)**:
   - Membuat tabel baru `document_relations` beserta index `id`, `source_key`, `target_key`.
   - Menambahkan kolom `status_source` pada tabel `documents`.
   - Menyediakan fungsi `downgrade` penuh yang menghapus tabel `document_relations` dan kolom `status_source`.
3. **Layanan Versioning (`app/services/version_service.py`)**:
   - `parse_identity_key_sort`: Mem-parsing kunci kanonik `JENIS|NOMOR|TAHUN` untuk pengurutan kronologis `(tahun, nomor_numerik, key_asli)`.
   - `recompute_status`: Menghitung ulang status keberlakuan dokumen secara deterministik dengan 5 aturan berurutan:
     1. Status `manual` menang: Dokumen dengan `status_source == 'manual'` tidak ditimpa relasi/node status.
     2. Mencabut penuh: Jika terdapat relasi masuk `relation == 'mencabut'` dan `partial == False`, status diubah menjadi `dicabut` (`status_source = 'relasi'`).
     3. Mengubah atau mencabut sebagian: Jika terdapat relasi masuk `relation == 'mengubah'` atau (`mencabut` dengan `partial == True`), status diubah menjadi `diubah` (`status_source = 'relasi'`).
     4. Lapisan data / node status: Jika ada inferensi eksplisit dari node status dan tidak ada relasi pengubah/pencabut, status mengikuti `node_status` (`status_source = 'lapisan_data'`).
     5. Jika tidak ada aturan di atas yang terpenuhi, status dokumen dibiarkan seperti sedia kala.
     - Setiap perubahan status akibat relasi/lapisan data mencatat audit log dengan action `STATUS_FROM_RELATION`.
   - `sync_relations`: Menerima hingga 5.000 relasi per batch, mendukung upsert tanpa duplikasi, opsi `replace_all` (menghapus relasi lama yang tidak ada dalam kiriman baru), memproses `node_status`, dan secara otomatis memicu perhitungan ulang status dokumen terkait.
   - `get_versioning_details`: Menyusun struktur silsilah versi untuk dokumen pemanggil (`induk`, `diubah_oleh`, `dicabut_oleh`, `mencabut`, `perubahan_ke`, resolusi ke dokumen Knowledge Base). Memproteksi dokumen non-publik pada mode proteksi dengan menyamarkan identitas (`document_id: null, judul: null, restricted: true`).
4. **Integrasi Router & Proteksi API**:
   - `app/routers/internal.py`:
     - Menambahkan endpoint `POST /api/v1/internal/relations` dengan proteksi header `X-Internal-API-Key`.
     - Mengintegrasikan pemanggilan `recompute_status` di `patch_extraction_result` dan `batch_update_document_identity` (dibungkus `try/except` agar tidak menggagalkan proses ekstraksi utama).
   - `app/routers/documents.py`:
     - Menambahkan endpoint `GET /api/v1/documents/{document_id}/versi` (dengan penanganan dokumen non-publik 403 / 404 / 200).
     - Menambahkan pemicu `recompute_status` di `patch_document_metadata` saat field identitas berubah.
     - Menetapkan `status_source = "manual"` saat kurator melakukan pembaruan status manual di `update_document_status`.
     - Menyertakan field `status_source` pada seluruh respons dokumen detail dan daftar pencarian.
   - `app/services/search_service.py`: Menyertakan `status_source` pada hasil pencarian regulasi.
5. **Pengujian Komprehensif (`tests/test_step18_versioning.py`)**:
   - Menulis 14 pengujian unit dan integrasi (R01 - R14) yang menguji relasi, upsert, replace_all, aturan status keberlakuan, audit log, proteksi mode lindung non-publik, penanganan galat asinkron, dan toleransi format payload.
6. **Dokumentasi Kontrak API**:
   - Memperbarui `docs/api/KONTRAK-API-FASE1.md` dengan spesifikasi endpoint `GET /api/v1/documents/{document_id}/versi`, penambahan field `status_source`, dan seksi 15 untuk `POST /api/v1/internal/relations`.

---

## 2. Catatan untuk Lapisan Data (Data/ML)

1. **Format Endpoint Sinkronisasi Relasi**:
   - Endpoint: `POST /api/v1/internal/relations`
   - Header: `X-Internal-API-Key: <INTERNAL_API_KEY>`
   - Body JSON:
     ```json
     {
       "relations": [
         {
           "src": "POJK|10|2026",
           "dst": "POJK|1|2020",
           "rel": "MENGUBAH",
           "sebagian": 0,
           "pasal_terkait": null,
           "asal": "ekstraksi",
           "bukti": "Mengubah POJK 1/2020 tentang Tata Kelola"
         }
       ],
       "node_status": [
         {
           "key": "POJK|1|2020",
           "status": "diubah"
         }
       ],
       "replace_all": false
     }
     ```
2. **Karakteristik & Ketentuan Payload**:
   - **Kunci Kanonik:** Kunci `src` dan `dst` menggunakan format kanonik string `JENIS|NOMOR|TAHUN` (contoh: `POJK|11|2022`). Relasi hukum disimpan di tabel `document_relations` tanpa foreign key ke `documents.id`, sehingga relasi dapat dikirim sebelum berkas fisik masuk ke Knowledge Base. Begitu berkas dengan identitas tersebut diekstraksi ke KB, relasi langsung aktif secara otomatis.
   - **Jenis Relasi (`rel`):** Menerima `"MENGUBAH"` atau `"MENCABUT"` (case-insensitive). Jenis relasi selain kedua nilai tersebut (misal `"BERDASAR"`) akan diabaikan (`skipped`).
   - **Mencabut Penuh vs Sebagian (`sebagian`):**
     - Nilai `0` atau `false` mengindikasikan pencabutan/perubahan penuh. Dokumen target yang dicabut penuh akan berstatus `dicabut`.
     - Nilai `1` atau `true` mengindikasikan pencabutan sebagian pasal. Dokumen target yang dicabut sebagian pasal akan berstatus `diubah` (bukan `dicabut`).
   - **Opsi `replace_all`:**
     - Jika `false` (default): Sinkronisasi bersifat inkremental (upsert). Relasi baru ditambahkan, relasi yang sudah ada diperbarui jika atributnya berubah.
     - Jika `true`: Melakukan reset penuh; seluruh relasi lama di database yang tidak ada di daftar payload baru akan dihapus.
   - **Ukuran Batch:** Maksimal 5.000 relasi per satu kali panggilan HTTP.

---

## 3. Temuan QA Terkait Lampiran Regulasi

Berdasarkan pengujian QA dan analisis pipeline:
1. **Lampiran Regulasi sebagai Berkas Terpisah**:
   - Sejumlah regulasi di situs otoritas (seperti SEOJK atau PADK) kerap menerbitkan dokumen batang tubuh dan lampiran dalam berkas PDF terpisah.
   - Ketika berkas lampiran dipindai, judulnya dapat memuat nomor regulasi yang sama dengan berkas utama.
2. **Perilaku Sistem Saat Ini**:
   - Pada Langkah 17 (Deduplikasi Identitas), sistem membandingkan berkas dengan `identity_key` yang sama. Berkas yang memiliki jumlah halaman lebih banyak atau ukuran lebih besar ditetapkan sebagai pemenang, sedangkan berkas yang kalah dinonaktifkan sebagai duplikat.
   - Jika berkas lampiran berukuran lebih kecil dari berkas batang tubuh, berkas lampiran akan otomatis ditandai sebagai duplikat (`is_active = false`, `duplicate_of_id = id_utama`).
3. **Rekomendasi untuk Pipeline Data & Crawler**:
   - Untuk lampiran yang berdiri sendiri, ekstraktor teks/lapisan data disarankan memberikan penanda khusus pada judul atau `kunci_identitas` (misal dengan penanda `LAMPIRAN` jika merupakan instrumen terpisah), atau menggabungkan berkas PDF batang tubuh dan lampiran sebelum ekstraksi dilakukan.
   - Pada antarmuka pengguna, kurator dapat menggunakan fitur pengaktifan kembali dokumen yang pernah ditandai duplikat jika lampiran tersebut memang sengaja disimpan sebagai dokumen mandiri; dokumen yang diaktifkan kembali manual memiliki proteksi dari penonaktifan otomatis ulang.

---

## 4. Hasil Verifikasi Terminal (Output Mentah)

### A. Ruff Check
```
.\venv\Scripts\ruff.exe check --select E9,F821,F822,F823 app scripts tests
All checks passed!
```

### B. Unit & Integration Tests Versioning (R01 - R14)
```
.\venv\Scripts\python.exe -m pytest tests/test_step18_versioning.py -v
============================= test session starts =============================
platform win32 -- Python 3.13.7, pytest-9.1.1, pluggy-1.6.0 -- C:\Hero\hero-backend\venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Hero\hero-backend
plugins: anyio-4.15.1
collecting ... collected 14 items

tests/test_step18_versioning.py::test_r01_post_relations_inserted_and_skipped PASSED [  7%]
tests/test_step18_versioning.py::test_r02_post_duplicate_relation_updates_without_doubles PASSED [ 14%]
tests/test_step18_versioning.py::test_r03_replace_all_deletes_unspecified_relations PASSED [ 21%]
tests/test_step18_versioning.py::test_r04_full_repeal_updates_status_and_records_audit PASSED [ 28%]
tests/test_step18_versioning.py::test_r05_amendment_relation_updates_to_diubah PASSED [ 35%]
tests/test_step18_versioning.py::test_r06_partial_repeal_updates_to_diubah_not_dicabut PASSED [ 42%]
tests/test_step18_versioning.py::test_r07_manual_status_not_overwritten_by_relations PASSED [ 50%]
tests/test_step18_versioning.py::test_r08_node_status_applied_when_no_incoming_relation PASSED [ 57%]
tests/test_step18_versioning.py::test_r09_relation_saved_before_document_applied_on_extraction PASSED [ 64%]
tests/test_step18_versioning.py::test_r10_get_versioning_sorted_and_resolved PASSED [ 71%]
tests/test_step18_versioning.py::test_r11_get_versioning_non_public_modifier_restricted_in_protect_mode PASSED [ 78%]
tests/test_step18_versioning.py::test_r12_get_versioning_without_identity_key_returns_empty_and_note PASSED [ 85%]
tests/test_step18_versioning.py::test_r13_lowercase_relation_and_boolean_partial_accepted PASSED [ 92%]
tests/test_step18_versioning.py::test_r14_forced_error_in_recompute_status_does_not_fail_patch_extraction PASSED [100%]

====================== 14 passed, 16 warnings in 18.09s =======================
```

### C. Full Test Suite Pytest
```
.\venv\Scripts\python.exe -m pytest -q
333 passed, 1 skipped, 72 warnings in 392.87s (0:06:32)
```

### D. Uji Live Docker Health & Internal Relations
```
curl.exe -s http://localhost:8000/health
{"status":"ok","database":"ok","version":"0.10.0","app_env":"development","alembic_revision":"b8c9d0e1f2a3","alembic_head":"b8c9d0e1f2a3","migrations_up_to_date":true,"storage_writable":true,"crawler_backend":"simple_http","crawler_loaded":true,"auth_enabled":false,"protect_non_public":true}
```

```
docker exec hero_fastapi python -c "import httpx; from app.config import settings; r = httpx.post('http://127.0.0.1:8000/api/v1/internal/relations', headers={'X-Internal-API-Key': settings.internal_api_key}, json={'relations': [{'src': 'UJI|2|2099', 'dst': 'UJI|1|2099', 'rel': 'MENGUBAH', 'sebagian': 0}], 'node_status': [{'key': 'UJI|1|2099', 'status': 'diubah'}]}); print('CONTAINER_POST:', r.status_code, r.json())"
CONTAINER_POST: 200 {'inserted': 1, 'updated': 0, 'skipped': 0, 'deleted': 0, 'documents_status_changed': 0}
```

```
docker exec hero_fastapi python -c "import httpx; r = httpx.get('http://127.0.0.1:8000/api/v1/documents/1/versi'); print('GET_VERSI:', r.status_code, r.json())"
GET_VERSI: 200 {'document_id': 1, 'identity_key': None, 'status_keberlakuan': 'tidak_diketahui', 'status_source': None, 'induk': [], 'diubah_oleh': [], 'dicabut_oleh': [], 'mencabut': [], 'catatan': 'Dokumen belum memiliki kunci identitas (identity_key); relasi versi belum dapat dipetakan.'}
```
