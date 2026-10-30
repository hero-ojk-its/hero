# Laporan Implementasi HERO Backend — Langkah 29
**Smoke Test Fase 2: Tambah Cek Corong, Kategori, Status, dan Harmonisasi**

---

## 1. Ringkasan Singkat

Langkah 29 memperluas skrip pengujian smoke test Fase 2 (`scripts/smoke_fase2.py`) dari S01–S15 menjadi **S01–S22** untuk memvalidasi fitur-fitur yang diperkenalkan pada Langkah 26–28 serta frame kanan harmonisasi per pasal:
1. **S16 (Status Keberlakuan `belum_berlaku` — Langkah 26)**:
   - Memastikan `GET /api/v1/dashboard/summary` memuat kunci `belum_berlaku` pada `by_status_keberlakuan`.
2. **S17 & S18 (Statistik Corong — Langkah 27)**:
   - S17: `GET /api/v1/dashboard/corong` memvalidasi invarian matematis untuk setiap sumber (`scan.ditemukan` = 5 subkategori scan, dan `dokumen.di_kb` = `menunggu_ekstraksi + terbaca + gagal_baca + lainnya`).
   - S18: `GET /api/v1/dashboard/corong?format=csv` memvalidasi header BOM UTF-8 (`\xef\xbb\xbf`), baris terakhir `TOTAL` (kolom kedua), dan header `Content-Disposition` dengan parameter `filename*=`.
3. **S19 (Filter Kegagalan — Langkah 26)**:
   - `GET /api/v1/ingest/failures?reason_code=pdf_rusak&reason_code=pdf_terenkripsi&limit=5` memvalidasi filter reason code baru. Jika token tidak memiliki izin `KEGAGALAN_KELOLA` (401/403), cek ini berstatus `LEWATI`.
4. **S20 & S21 (Kategori & Relokasi — Langkah 28)**:
   - S20: `GET /api/v1/categories/tree` memastikan seluruh node memuat field `jumlah_dokumen` dan `classification_rule`.
   - S21: Menghitung akumulasi dokumen yang berada pada node dengan nama `"Tanpa Tahun"`. Bila terdapat dokumen (> 0), status tetap `OK` dengan keterangan perintah relokasi dan mencetak peringatan tindak lanjut.
5. **S22 (Harmonisasi Per Pasal — Langkah 16 / Weekly #7)**:
   - Satu-satunya request non-GET (`POST /api/v1/ml/harmonisasi/{id}`) yang menghitung temuan harmonisasi draft regulasi terhadap korpus.
   - Memvalidasi bahwa hyperlink pembanding diawali `/api/v1/documents/` dan `document_id` berupa integer.
   - Menyediakan opsi `--tanpa-harmonisasi` untuk menonaktifkan S22 (`LEWATI "dinonaktifkan"` tanpa melakukan request POST).
   - Menangani ketiadaan draft kajian (`LEWATI "Tidak ada draft kajian terindeks"`), ML mati/503/504 (`LEWATI "jalur ML mati"`), dan korpus kosong (`LEWATI "KB pembanding kosong"`).
6. **Peringatan Rinci Pasca Ringkasan**:
   - Mencetak `PERINGATAN` terstruktur setelah baris `RINGKASAN`:
     - Peringatan lama S04 LEWATI.
     - Peringatan S21 > 0 dokumen di "Tanpa Tahun".
     - Peringatan S17 `belum_ditarik > 0`.
     - Peringatan S17 `belum_diperiksa > 0` (proteksi PDF).
7. **Dokumentasi Deploy**:
   - Memperbarui `docs/deploy/RUNBOOK-VPS.md` §5.3 dengan daftar S01–S22, penjelasan peringatan dan perintah tindak lanjut, opsi `--draft-id` & `--tanpa-harmonisasi`, serta menambahkan prosedur bernomor "Urutan pasca-deploy Fase 2".

---

## 2. Tabel Hasil Pengujian Langkah 29 (T01 s.d. T12)

| Kode | Kasus Uji | Ekspektasi | Status |
|---|---|---|:---:|
| **T01** | Server normal (seed 1 sumber dengan kandidat dan dokumen) | S16–S20 OK | **PASS** |
| **T02** | Respons summary tanpa `belum_berlaku` (monkeypatch endpoint) | S16 GAGAL dengan pesan Langkah 26 | **PASS** |
| **T03** | Corong dengan invarian dilanggar (monkeypatch respons) | S17 GAGAL dan menyebut nama sumber | **PASS** |
| **T04** | Ada dokumen di kategori `Tanpa Tahun` | S21 OK + baris PERINGATAN relokasi | **PASS** |
| **T05** | Seed `belum_ditarik > 0` dan `pdf_terproteksi` NULL | Dua baris PERINGATAN muncul; exit code 0 | **PASS** |
| **T06** | Draft `draft_kajian` terindeks + mock ML harmonisasi 200 (2 temuan valid) | S22 OK, keterangan memuat `temuan=2` | **PASS** |
| **T07** | Mock harmonisasi dengan `pembanding.pdf` = `"http://evil/x.pdf"` | S22 GAGAL `hyperlink pembanding tidak valid` | **PASS** |
| **T08** | Mock harmonisasi 422 / ConnectError | S22 LEWATI (`KB pembanding kosong` / `jalur ML mati`) | **PASS** |
| **T09** | Tidak ada draft kajian | S22 LEWATI `Tidak ada draft kajian terindeks` | **PASS** |
| **T10** | Opsi `--tanpa-harmonisasi` | S22 LEWATI `dinonaktifkan`, tidak ada request POST | **PASS** |
| **T11** | Hanya-baca: inspeksi seluruh metode HTTP selama `run_checks` | Semua GET kecuali tepat satu POST ke `/ml/harmonisasi/` | **PASS** |
| **T12** | Auth aktif, token tanpa izin kegagalan (`pilot_user`) | S19 LEWATI `token tanpa izin kegagalan` | **PASS** |

---

## 3. Output Terminal Pytest

### a. Berkas Uji Smoke Test (`tests/test_step24_smoke_fase2.py tests/test_step29_smoke_lanjutan.py`)
Perintah: `.\venv\Scripts\python.exe -m pytest tests/test_step24_smoke_fase2.py tests/test_step29_smoke_lanjutan.py -q`
```
.......................                                                  [100%]
23 passed, 2 warnings in 89.54s (0:01:29)
```

### b. Seluruh Suite Pengujian (`pytest -q`)
Perintah: `.\venv\Scripts\python.exe -m pytest -q`
```
........................................................................ [ 13%]
.............................................s.......................... [ 27%]
........................................................................ [ 40%]
........................................................................ [ 54%]
........................................................................ [ 67%]
........................................................................ [ 81%]
........................................................................ [ 94%]
...........................                                              [100%]
530 passed, 1 skipped, 184 warnings in 647.49s (0:10:47)
```

---

## 4. Output Terminal Ruff Linter
Perintah: `.\venv\Scripts\python.exe -m ruff check --select E9,F scripts tests/test_step24_smoke_fase2.py tests/test_step29_smoke_lanjutan.py`
```
All checks passed!
```

---

## 5. Output Terminal Uji Live (Docker)

### Perintah 1: Uji Live Lengkap
```powershell
docker compose up -d --build backend
Start-Sleep -Seconds 25
.\venv\Scripts\python.exe scripts/smoke_fase2.py --base-url http://localhost:8000
echo "exit=$LASTEXITCODE"
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
PERINGATAN: cek analisa/riwayat/ekspor (S05–S13) tidak dijalankan karena tidak ada dokumen uji. Pakai --doc-id atau pastikan ada dokumen publik terindeks.
PERINGATAN: 3155 hasil scan belum ditarik ke KB — Pak Faris meminta semua hasil scan masuk KB (Weekly #7).
exit=0
```

### Perintah 2: Uji Live dengan `--tanpa-harmonisasi`
```powershell
.\venv\Scripts\python.exe scripts/smoke_fase2.py --base-url http://localhost:8000 --tanpa-harmonisasi
echo "exit=$LASTEXITCODE"
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
S22    | Harmonisasi per pasal                    | LEWATI   | dinonaktifkan
====================================================================================
RINGKASAN: 9 OK, 0 GAGAL, 13 LEWATI
PERINGATAN: cek analisa/riwayat/ekspor (S05–S13) tidak dijalankan karena tidak ada dokumen uji. Pakai --doc-id atau pastikan ada dokumen publik terindeks.
PERINGATAN: 3155 hasil scan belum ditarik ke KB — Pak Faris meminta semua hasil scan masuk KB (Weekly #7).
exit=0
```

---

## 6. Git Status dan Diff

### a. `git diff main --stat`
```
 docs/deploy/RUNBOOK-VPS.md       |  88 ++++++++-
 scripts/smoke_fase2.py           | 375 ++++++++++++++++++++++++++++++++++++---
 tests/test_step24_smoke_fase2.py |  29 +--
 3 files changed, 453 insertions(+), 39 deletions(-)
```

### b. `git log --oneline -3`
```
4dcaaa5 feat(backend): Langkah 28 - relokasi kategori, kelola kategori, audit penempatan
ed0cd28 feat: relokasi kategori otomatis, kelola kategori (ubah nama/pindah/hapus/aturan), audit penempatan lengkap
e6adea7 feat(backend): Langkah 27 - statistik corong per sumber dan penanda PDF diproteksi
```

