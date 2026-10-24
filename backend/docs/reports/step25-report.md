# Laporan Langkah 25 — Tandai Cache Analisa Usang setelah Mesin ML Diperbarui

## 1. Ringkasan Pelaksanaan
Langkah 25 mengatasi temuan Fathir (PR #137) di mana cache analisa regulasi di backend terkunci oleh sidik jari sumber (`source_fingerprint`), sehingga pembaruan mesin ML (misal: aturan baru atau versi `v2.0` ke `v2.1`) tidak memicu komputasi ulang secara otomatis kecuali parameter `segar=true` disertakan.

Penyelesaian diimplementasikan melalui:
1. **Migrasi Database (`a3b4c5d6e7f8`):** Penambahan kolom `usang_sejak` (`timestamptz`, nullable, indexed) dan `alasan_usang` (`String(200)`, nullable) pada tabel `analysis_results`.
2. **Pembaruan Layanan Cache & Ekspor (`analysis_result_service.py` & `analysis_export_service.py`):**
   - Cache hit segar (`expected_fingerprint` disertakan): Mewajibkan syarat `usang_sejak IS NULL`. Baris usang dianggap miss sehingga memicu evaluasi ulang ke mesin ML.
   - Fallback ML offline (`expected_fingerprint=None`): Tetap diizinkan menggunakan baris cache yang usang dengan penanda `cache.basi = true`.
   - `save_analysis_result`: Mengosongkan `usang_sejak = None` dan `alasan_usang = None` saat hasil baru disimpan.
   - Perbandingan & Ekspor: Evaluasi `basi = (source_fingerprint != curr_fingerprint) or (usang_sejak is not None)`.
   - Pesan pada ekspor DOCX & JSON: Kalimat `"Mesin analisa telah diperbarui sejak hasil ini dibuat — jalankan analisa ulang."` ditampilkan apabila cache usang.
3. **Endpoint Internal (`POST /api/v1/internal/analysis-cache/invalidate`):**
   - Dilindungi dependency `verify_internal_api_key`.
   - Menandai baris berstatus `usang_sejak IS NULL` (idempoten).
   - Filter `versi_mesin`: Menandai baris yang `ml_version IS DISTINCT FROM versi_mesin`.
   - Filter `kind` dan `document_ids`: Array kosong `document_ids: []` divalidasi dan mengembalikan status HTTP 422.
   - Pencatatan jejak audit: Aksi `ANALYSIS_CACHE_INVALIDATED` pada `target_resource="analysis_results"`, pelaku `user_id=None`.
4. **Dokumentasi & Kontrak API:** Pembaruan §15.2 pada `docs/api/KONTRAK-API-FASE1.md`, pembaruan OpenAPI JSON via `scripts/build_api_contract.py`.

---

## 2. Catatan untuk Lapisan Data (Fathir)

Tambahkan satu perintah berikut ke dalam alur pipeline CI/CD atau skrip deploy worker mesin analisa segera setelah rilis mesin ML selesai di-deploy ke lingkungan produksi/staging:

```bash
curl -s -X POST "http://<backend-host>:8000/api/v1/internal/analysis-cache/invalidate" \
  -H "X-Internal-API-Key: $INTERNAL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"versi_mesin": "v2.1", "alasan": "deploy mesin v2.1: kerangka BAB & metrik baru"}'
```

> **Catatan Penting:**  
> Nilai field `versi_mesin` sebaiknya **sama persis** dengan nilai field `versi` yang dikirimkan oleh layanan ML pada respons JSON endpoint analisa (contoh: `"v2.1"`). Dengan demikian, baris cache yang kelak dihitung menggunakan versi baru tersebut tidak akan ikut tertandai usang pada pemanggilan invalidasi berikutnya.

---

## 3. Matriks Kasus Uji (V01 – V13)

| # | Kasus Uji | Ekspektasi | Hasil |
|---|---|---|:---:|
| **V01** | Analisa 2x, invalidate tanpa filter, analisa lagi | Panggilan ML ke-1 dan ke-3 terjadi (total 2), panggilan ke-2 cache hit; respons ke-3 `cache.hit=false` | **LULUS** |
| **V02** | Setelah V01 (atau simpan hasil analisa sukses) | Baris `usang_sejak` kembali `NULL`, `alasan_usang` kembali `NULL`, dan `ml_version` diperbarui | **LULUS** |
| **V03** | `versi_mesin="v2.1"`; dok A tersimpan `v2.0`, dok B tersimpan `v2.1` | `ditandai=1`; hanya A yang usang, B tetap valid (`usang_sejak is None`) | **LULUS** |
| **V04** | Invalidate dua kali berturut-turut | Panggilan ke-2: `ditandai=0`, `sudah_usang_sebelumnya >= 1` (idempoten) | **LULUS** |
| **V05** | `document_ids=[A]` | Hanya baris dokumen A yang ditandai, dokumen B tidak tersentuh | **LULUS** |
| **V06** | `kind="harmonisasi"` | Baris jenis analisa regulasi tidak tersentuh (`ditandai=0`) | **LULUS** |
| **V07** | `document_ids=[]` | Ditolak dengan status HTTP 422 Unprocessable Entity | **LULUS** |
| **V08** | Tanpa atau salah `X-Internal-API-Key` | Ditolak dengan status HTTP 401 Unauthorized | **LULUS** |
| **V09** | Baris usang, lalu ML mati (`ConnectError`) | Status 200, hasil lama tersaji, `cache.basi=true` (fallback tetap bekerja) | **LULUS** |
| **V10** | `/analisa/banding` dengan baris usang | `deterministik.basi=true` | **LULUS** |
| **V11** | Ekspor DOCX dan JSON baris usang | DOCX memuat kalimat "Mesin analisa telah diperbarui…", JSON memuat `basi=true` dan kalimat peringatan | **LULUS** |
| **V12** | Jumlah baris `analysis_runs` sebelum dan sesudah invalidate | Tidak berubah (riwayat eksekusi tidak dimodifikasi) | **LULUS** |
| **V13** | Audit log | Satu entri `ANALYSIS_CACHE_INVALIDATED` dengan `detail.ditandai`, `user_id=None`, `target_resource="analysis_results"` | **LULUS** |

---

## 4. Hasil Verifikasi Pytest

### 4.1 Pytest Berkas Uji Langkah 25 (`tests/test_step25_cache_usang.py`)
```
PS C:\Hero\hero-backend> .\venv\Scripts\python.exe -m pytest tests/test_step25_cache_usang.py -q
.............                                                            [100%]
13 passed, 2 warnings in 36.31s
```

### 4.2 Pytest Suite Regresi Utama (Langkah 20, 22, 24, 25)
```
PS C:\Hero\hero-backend> .\venv\Scripts\python.exe -m pytest tests/test_step20_hasil_analisa.py tests/test_step22_ekspor_analisa.py tests/test_step24_smoke_fase2.py tests/test_step25_cache_usang.py -q
.........................................................                [100%]
57 passed, 2 warnings in 134.41s (0:02:14)
```

### 4.3 Pytest Seluruh Suite Repositori
```
PS C:\Hero\hero-backend> .\venv\Scripts\python.exe -m pytest -q
461 passed, 1 skipped, 172 warnings in 785.80s (0:13:05)
```

---

## 5. Pemeriksaan Ruff
```
PS C:\Hero\hero-backend> .\venv\Scripts\ruff.exe check --select E9,F app
All checks passed!

PS C:\Hero\hero-backend> .\venv\Scripts\ruff.exe check --select E9,F tests/test_step25_cache_usang.py
All checks passed!
```

---

## 6. Uji Live (Terminal Mentah)

### 6.1 Build & Health Check Live Backend
```powershell
PS C:\Hero\hero-backend> docker compose up -d --build backend
#1 [internal] load local bake definitions
#1 reading from stdin 512B done
#1 DONE 0.0s
#2 [internal] load build definition from Dockerfile
#2 transferring dockerfile: 825B 0.1s done
#2 DONE 0.2s
#3 [internal] load metadata for docker.io/library/python:3.11-slim
#3 DONE 3.6s
#4 [internal] load .dockerignore
#4 transferring context: 110B 0.0s done
#4 DONE 0.1s
#5 [internal] load build context
#5 DONE 0.0s
#6 [1/7] FROM docker.io/library/python:3.11-slim@sha256:b7a9e5f6a93d6d4a31f129bbd4bdee69efccb6ded0fb230d78aafaf37af98377
#6 resolve docker.io/library/python:3.11-slim@sha256:b7a9e5f6a93d6d4a31f129bbd4bdee69efccb6ded0fb230d78aafaf37af98377 0.1s done
#6 DONE 0.1s
#5 [internal] load build context
#5 transferring context: 1.54MB 4.8s
#5 transferring context: 1.62MB 5.5s done
#5 DONE 5.9s
#7 [2/7] WORKDIR /app
#7 CACHED
#8 [3/7] RUN apt-get update && apt-get install -y     gcc     libpq-dev     && rm -rf /var/lib/apt/lists/*
#8 CACHED
#9 [4/7] COPY requirements.txt .
#9 CACHED
#10 [5/7] RUN pip install --no-cache-dir -r requirements.txt
#10 CACHED
#11 [6/7] COPY . .
#11 DONE 26.3s
#12 [7/7] RUN chmod +x scripts/entrypoint.sh
#12 DONE 1.9s
#13 exporting to image
#13 exporting layers 34.4s done
#13 naming to docker.io/library/hero-backend-backend:latest 0.0s done
#13 unpacking to docker.io/library/hero-backend-backend:latest 9.1s done
#13 DONE 44.2s
#14 resolving provenance for metadata file
#14 DONE 0.2s
 hero-backend-backend  Built
 Container hero_postgres  Running
 Container hero_fastapi  Recreate
 Container hero_fastapi  Recreated
 Container hero_postgres  Waiting
 Container hero_postgres  Healthy
 Container hero_fastapi  Starting
 Container hero_fastapi  Started

PS C:\Hero\hero-backend> Start-Sleep -Seconds 20
PS C:\Hero\hero-backend> curl.exe -s http://localhost:8000/health
{"status":"ok","database":"ok","version":"0.10.0","app_env":"development","alembic_revision":"a3b4c5d6e7f8","alembic_head":"a3b4c5d6e7f8","migrations_up_to_date":true,"storage_writable":true,"crawler_backend":"simple_http","crawler_loaded":true,"auth_enabled":false,"protect_non_public":true}
```

### 6.2 Eksekusi Invalidation Endpoint
```powershell
PS C:\Hero\hero-backend> $k = (Get-Content .env | Select-String '^INTERNAL_API_KEY=').ToString().Split('=',2)[1]
PS C:\Hero\hero-backend> curl.exe -s -X POST http://localhost:8000/api/v1/internal/analysis-cache/invalidate -H "X-Internal-API-Key: $k" -H "Content-Type: application/json" -d '{\"versi_mesin\":\"v2.1\"}'
{"ditandai":0,"sudah_usang_sebelumnya":0,"versi_mesin":"v2.1","kind":null}
PS C:\Hero\hero-backend> Remove-Variable k
```

### 6.3 Eksekusi Smoke Test Fase 2
```powershell
PS C:\Hero\hero-backend> .\venv\Scripts\python.exe scripts/smoke_fase2.py --base-url http://localhost:8000
================================================================================
       HERO BACKEND SMOKE TEST FASE 2 (READ-ONLY) - http://localhost:8000
       Revisi Alembic Diharapkan: a3b4c5d6e7f8
       Autentikasi: Tidak ada HERO_SMOKE_TOKEN (mode anonim/dev)
================================================================================
================================================================================
Kode   | Cek                                  | Status   | Keterangan
--------------------------------------------------------------------------------
S01    | GET /health                          | OK       | rev=a3b4c5d6e7f8
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

## 7. Status Git Sebelum Commit

### 7.1 `git diff main --stat`
```
 app/models/analysis_result.py           |  11 +++
 app/routers/internal.py                 |  97 +++++++++++++++++++++++++-
 app/services/analysis_export_service.py |  24 ++++++-
 app/services/analysis_result_service.py |  11 ++-
 app/services/audit_service.py           |   1 +
 docs/api/KONTRAK-API-FASE1.md           |  60 ++++++++++++++--
 docs/api/openapi-fase1.json             | 118 ++++++++++++++++++++++++++++++++
 7 files changed, 313 insertions(+), 9 deletions(-)
```

### 7.2 `git status --short`
```
 M app/models/analysis_result.py
 M app/routers/internal.py
 M app/services/analysis_export_service.py
 M app/services/analysis_result_service.py
 M app/services/audit_service.py
 M docs/api/KONTRAK-API-FASE1.md
 M docs/api/openapi-fase1.json
?? alembic/versions/a3b4c5d6e7f8_step25_analysis_cache_invalidation.py
?? docs/reports/step25-report.md
?? tests/test_step25_cache_usang.py
```

### 7.3 `git log --oneline -3`
```
f89db40 chore: Langkah 24 smoke test Fase 2 read-only
525b18d fix(step24): pemilihan dokumen uji pakai filter, peringatan uji inti dilewati, perapian tes
b60bed5 chore: smoke test Fase 2 read-only untuk M2 dan migrasi VPS
```
