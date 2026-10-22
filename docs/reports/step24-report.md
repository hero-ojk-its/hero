# Laporan Langkah 24 — Smoke Test Fase 2 (Read-Only) untuk M2 & Migrasi VPS

## 1. Ringkasan
Langkah 24 menambahkan skrip pengujian ketersediaan smoke test Fase 2 yang bersifat **hanya membaca (read-only)** di `scripts/smoke_fase2.py`, memperbarui runbook deployment VPS di `docs/deploy/RUNBOOK-VPS.md`, menambahkan peringatan data-modification pada skrip lama `scripts/smoke_test.py`, serta melengkapi suite pengujian otomatis `tests/test_step24_smoke_fase2.py` (kasus Q01–Q09).

### Karakteristik & Keamanan `scripts/smoke_fase2.py`:
1. **Read-Only:** Skrip ini hanya mengirimkan permintaan HTTP berjenis `GET`. Tidak ada pemanggilan `POST`, `PATCH`, `PUT`, atau `DELETE`.
2. **Efek Samping Caching:** Endpoint `GET /ml/analisa/{id}` secara alami memicu pencatatan baris di `analysis_results`, `analysis_runs`, dan audit log (`RUN_ANALYSIS`). Hal ini didokumentasikan di docstring skrip dan merupakan perilaku backend yang valid.
3. **Pencegahan Kebocoran Rahasia:** Token otentikasi dibaca dari variabel lingkungan `HERO_SMOKE_TOKEN` (bukan argumen CLI) dan tidak pernah dicetak ke output konsol atau log.
4. **Validasi Versi Deploy Otomatis:** Menghitung revisi head Alembic lokal via `alembic.script.ScriptDirectory` untuk mencocokkan dengan `alembic_revision` dari `GET /health` VPS target.

---

## 2. Cara Pakai (Panduan untuk Hamdan)

### Menjalankan dari Laptop Developer atau Bastion VPS:
```bash
# 1. Bila AUTH_ENABLED=false (default lingkungan development/staging awal):
python scripts/smoke_fase2.py --base-url https://api.hero-regulasi.id

# 2. Bila AUTH_ENABLED=true:
# PowerShell:
$env:HERO_SMOKE_TOKEN = "<isi_token_jwt_anda>"
python scripts/smoke_fase2.py --base-url https://api.hero-regulasi.id

# Linux / Bash:
HERO_SMOKE_TOKEN="<isi_token_jwt_anda>" python scripts/smoke_fase2.py --base-url https://api.hero-regulasi.id
```

### Opsi Argumen:
- `--base-url`: URL target backend (default: `http://localhost:8000`).
- `--doc-id`: Menguji dokumen regulasi tertentu (jika tidak diisi, skrip akan mendeteksi dokumen pertama yang berstatus `terindeks` / `perlu_koreksi` dan klasifikasi `publik`).
- `--expect-revision`: Menentukan revisi Alembic yang diharapkan (default: otomatis membaca head lokal dari direktori `alembic/`, yaitu `f2a3b4c5d6e7`).

### Memahami Hasil & Kode Keluar:
- **Exit Code 0:** Semua cek OK atau LEWATI (tidak ada GAGAL).
- **Exit Code 1:** Terdapat minimal satu cek yang GAGAL.
- **S01 GAGAL (`VPS belum di-deploy versi terbaru: <rev VPS> ≠ <rev diharapkan>`):**
  Instance backend di VPS belum menjalankan migrasi Alembic terbaru atau image container belum diperbarui ke commit git terkini. Lakukan `git pull` dan `alembic upgrade head` pada VPS.

---

## 3. Uji Fallback ML Mati (#83)
Prosedur pengujian ketahanan backend saat worker ML mati/tidak dapat dihubungi:
1. Jalankan `smoke_fase2.py` saat layanan ML aktif agar hasil analisa tersimpan dalam cache database.
2. Hentikan layanan ML (`hero bridge serve --stop` atau matikan container ML).
3. Jalankan kembali `smoke_fase2.py`.
4. Cek **S06** harus tetap berstatus **OK** dengan keterangan `"jalur ML mati"` (menggunakan cache riwayat basi).
5. Nyalakan kembali layanan ML (`hero bridge serve`).

---

## 4. Tabel Kasus Uji (Q01–Q09)

| # | Kasus | Skenario Uji | Ekspektasi | Status |
|---|---|---|---|---|
| **Q01** | ML hidup, semua normal | Mock ML status `siap` dan analisa sukses | Seluruh cek OK kecuali S15 (LEWATI jika tanpa non-publik); exit code 0 | **PASSED** |
| **Q02** | `--expect-revision` salah | Diberi nilai revisi beda (`revisi_palsu_999999`) | S01 GAGAL dengan pesan `"VPS belum di-deploy versi terbaru"`; exit code 1 | **PASSED** |
| **Q03** | ML mati setelah analisa tersimpan | ML melempar `ConnectError` setelah satu kali panggil | S03 LEWATI; S06 OK `"jalur ML mati"`; S07 LEWATI; tidak ada GAGAL | **PASSED** |
| **Q04** | ML mati, belum pernah ada analisa | ML melempar `ConnectError` pada dokumen baru | S06 OK (503 `"jalur ML mati"`); S08–S13 LEWATI / tidak GAGAL | **PASSED** |
| **Q05** | Dokumen tidak memenuhi syarat | `GET /documents/` mengembalikan list kosong | S04 LEWATI; cek terkait dokumen S05–S13 LEWATI; exit code 0 | **PASSED** |
| **Q06** | Ada dokumen non-publik, auth mati | Dokumen `access_classification=non_publik` di DB | S15 OK (ditolak 403 saat auth mati) | **PASSED** |
| **Q07** | Skrip hanya membaca | Tracking HTTP method di TestClient | 100% request adalah GET, tidak ada POST/PUT/PATCH/DELETE | **PASSED** |
| **Q08** | `HERO_SMOKE_TOKEN` di-set | Variabel lingkungan dipasang token rahasia | Token terkirim via header Authorization, tidak bocor ke output | **PASSED** |
| **Q09** | Head Alembic default | Pemanggilan tanpa `--expect-revision` | Membaca head lokal dari `ScriptDirectory` (`f2a3b4c5d6e7`) | **PASSED** |

---

## 5. Contoh Output Uji Live Terminal (Salinan Mentah)

```text
PS C:\Hero\hero-backend> .\venv\Scripts\python.exe scripts/smoke_fase2.py --base-url http://localhost:8000; echo "exit=$LASTEXITCODE"
================================================================================
       HERO BACKEND SMOKE TEST FASE 2 (READ-ONLY) - http://localhost:8000
       Revisi Alembic Diharapkan: f2a3b4c5d6e7
       Autentikasi: Tidak ada HERO_SMOKE_TOKEN (mode anonim/dev)
================================================================================
================================================================================
Kode   | Cek                                  | Status   | Keterangan
--------------------------------------------------------------------------------
S01    | GET /health                          | OK       | rev=f2a3b4c5d6e7
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
exit=0
```
