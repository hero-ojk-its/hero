# Laporan Pelaksanaan — Langkah 31: Skrip "Tarik Semua Hasil Scan" ke KB untuk Persiapan UAT

**Tanggal:** 31 Oktober 2026  
**Pelaksana:** Agent (HERO Backend)  
**Branch:** `chore/step31-tarik-semua`  

---

## 1. Ringkasan Eksekutif

Langkah 31 menuntaskan otomasi penarikan kandidat hasil pemindaian (*scraping*) ke *Knowledge Base* (KB) guna menyiapkan data uji coba UAT (skenario 1.480 + 20 dokumen) sebagaimana arahan Pak Faris pada Weekly #7:
> *"Semua dokumen yang terdeteksi saat scraping ditarik, diunduh ke lokal, dipecah, dan masuk vektor — itu ground truth."*

Sebelum langkah ini, terdapat 3.155 kandidat hasil scan yang belum ditarik ke KB. Penarikan manual melalui UI per dokumen atau per halaman tidak efisien untuk ribuan berkas. Langkah 31 menyediakan skrip CLI mandiri `scripts/tarik_semua.py` yang memanfaatkan REST API yang sudah tersedia di backend (tanpa mengubah kode aplikasi `app/`).

### Fitur Utama Skrip `scripts/tarik_semua.py`
1. **Mode Aman Default (DRY-RUN):** Tanpa argumen `--apply`, skrip hanya melakukan `GET` untuk mencacah kandidat per sumber, menampilkan tinjauan, dan menghitung estimasi perubahan corong tanpa mengubah state apa pun.
2. **Kriteria Penarikan Kandidat:**
   - Default: Menarik kandidat baru yang belum ditarik (`match_status="new"` dan `pull_outcome IS NULL`).
   - Flag `--ulang-gagal`: Menambahkan kandidat yang pernah gagal ditarik sebelumnya (`pull_outcome="failed"`).
   - Mengabaikan kandidat yang sudah terhubung dengan dokumen KB (`match_status IN ("exact_match", "partial_match")` atau `document_id / match_document_id IS NOT NULL`) dan yang sudah berhasil ditarik (`pull_outcome="success"`).
3. **Chunking & Batching API:**
   - Memilih kandidat via `PATCH /api/v1/scan/{id}/candidates/batch` dalam potongan maksimal 200 item per request untuk menghindari payload berlebih.
   - Memicu penarikan via `POST /api/v1/scan/{id}/pull` tanpa menyertakan `category_id` (mengandalkan auto-placement service berbasis nama berkas).
4. **Polling Asinkron & Timeout:**
   - Menunggu status sesi berubah dari `menarik` menjadi `siap` (atau `gagal`) dengan interval polling terkonfigurasi (default 15 detik) dan batas timeout (default 120 menit).
5. **Autentikasi Aman:**
   - Mendukung header `Authorization: Bearer <token>` bila environment variable `HERO_API_TOKEN` tersedia. Skrip dilarang dan tidak pernah mencetak token ke konsol/log.
6. **Perhitungan Hasil Nyata:**
   - Mengambil kandidat sesi setelah penarikan selesai dan menghitung secara akurat jumlah sukses/gagal khusus untuk kandidat yang ditarik pada pemanggilan tersebut.
7. **Tabel Ringkasan Corong:**
   - Membandingkan metrik corong (Total Dokumen di KB dan Total Scan Belum Ditarik) sebelum dan sesudah penarikan via `GET /api/v1/stats/corong`.

---

## 2. Format Tabel & Output Terminal (Dry-Run Lokal)

Pengujian dry-run dijalankan terhadap backend lokal:
`powershell -Command "Start-Sleep -Seconds 25; .\venv\Scripts\python.exe scripts/tarik_semua.py --base-url http://localhost:8000"`

```text
Autentikasi: Tidak ada HERO_API_TOKEN (mode anonim/dev)
Regulasi OJK (Situs Resmi) | sesi #12 | perlu ditarik: 14 (baru 14, ulang-gagal 0) | sudah ada di KB: 14
[LEWATI] JDIH OJK (Situs Resmi) | tidak ada sesi scan siap — jalankan scan dulu
OneDrive Public DPEA | sesi #8 | perlu ditarik: 2597 (baru 2597, ulang-gagal 0) | sudah ada di KB: 15
uji_folder | sesi #16 | perlu ditarik: 0 (baru 0, ulang-gagal 0) | sudah ada di KB: 2
demo_ojk_peraturan | sesi #18 | perlu ditarik: 0 (baru 0, ulang-gagal 0) | sudah ada di KB: 5

==========================================================================================
                    RINGKASAN PENARIKAN HASIL SCAN KE KB
                    Mode: DRY-RUN (Hanya Tinjauan)
==========================================================================================
Sumber                       | Sesi   | Perlu Ditarik (Baru / Ulang)   | Di KB  | Catatan
------------------------------------------------------------------------------------------
Regulasi OJK (Situs Resmi)   | #12    | 14 (baru 14, ulang 0)          | 14     | dry-run
JDIH OJK (Situs Resmi)       | -      | 0 (baru 0, ulang 0)            | 0      | tidak ada sesi scan siap — jalankan scan dulu
OneDrive Public DPEA         | #8     | 2597 (baru 2597, ulang 0)      | 15     | dry-run
uji_folder                   | #16    | 0 (baru 0, ulang 0)            | 2      | dry-run
demo_ojk_peraturan           | #18    | 0 (baru 0, ulang 0)            | 5      | dry-run

------------------------------------------------------------------------------------------
Metrik Corong                        | Sebelum      | Sesudah      | Perubahan
------------------------------------------------------------------------------------------
Total Dokumen di KB                  | 73           | 73           | +0
Total Scan Belum Ditarik             | 3154         | 3154         | +0
==========================================================================================
RINGKASAN: 5 sumber diproses | Perlu Ditarik: 2611 | Mode: DRY-RUN (tidak ada berkas ditarik)
```

---

## 3. Hasil Pengujian Otomatis

Rangkaian pengujian otomatis ditulis dalam `tests/test_step31_tarik_semua.py` mencakup 12 kasus uji (A01 s.d. A12):

| Kode | Kasus Uji | Hasil |
|------|-----------|-------|
| A01 | Mode default tanpa `--apply` adalah dry-run (hanya GET, tidak ada POST/PATCH) | LULUS |
| A02 | Filter kandidat baru mengabaikan kandidat yang sudah terhubung atau sukses ditarik | LULUS |
| A03 | Flag `--ulang-gagal` menyertakan kandidat dengan `pull_outcome="failed"` | LULUS |
| A04 | Batch selection memecah kandidat ke dalam potongan maksimal 200 per PATCH | LULUS |
| A05 | POST pull tidak menyertakan category_id (auto-placement aktif) | LULUS |
| A06 | Polling status sesi menunggu transisi `menarik` -> `siap` dan melaporkan hasil | LULUS |
| A07 | Timeout polling terdeteksi dan dilaporkan dengan benar | LULUS |
| A08 | Filter sumber spesifik via `--source-id` hanya memproses sumber yang dipilih | LULUS |
| A09 | Batas tarikan per sumber via `--batas N` memotong kandidat sesuai limit | LULUS |
| A10 | Sumber tanpa sesi scan siap dilewati dengan pesan catatan informatif | LULUS |
| A11 | Perbandingan corong memanggil `GET /api/v1/stats/corong` sebelum dan sesudah | LULUS |
| A12 | Autentikasi `HERO_API_TOKEN` disisipkan ke header tanpa dicetak ke stdout/log | LULUS |

---

## 4. Dokumentasi Operasional RUNBOOK VPS

Dokumentasi operasional pada `docs/deploy/RUNBOOK-VPS.md` telah diperbarui dengan dua subbagian baru:
- **5.6 Penarikan Seluruh Hasil Scan ke KB (`tarik_semua.py`)**: Sintaks CLI, daftar parameter lengkap, panduan dry-run, penarikan bertahap dengan batas, penarikan penuh dengan timeout, serta penanganan error.
- **5.7 Menyiapkan KB untuk UAT (Skenario 1.480 + 20)**: Langkah kerja penyiapan ground truth UAT dari sumber resmi OJK, pemisahan 20 dokumen pengujian (held-out test set), penarikan 1.480 dokumen ground truth, verifikasi metrik corong dan vektorisasi, serta verifikasi pengujian held-out.

---

## 5. Output Terminal Mentah

### 5.1. `pytest tests/test_step31_tarik_semua.py -q`
```text
............                                                             [100%]
============================== warnings summary ===============================
venv\Lib\site-packages\fastapi\testclient.py:1
  C:\Hero\hero-backend\venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

venv\Lib\site-packages\starlette\testclient.py:53
  C:\Hero\hero-backend\venv\Lib\site-packages\starlette\testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
12 passed, 2 warnings in 31.49s
```

### 5.2. `pytest -q` (seluruh suite)
```text
560 passed, 1 skipped, 184 warnings in 944.02s (0:15:44)
```

### 5.3. `ruff check --select E9,F scripts tests/test_step31_tarik_semua.py`
```text
All checks passed!
```

### 5.4. `git diff main --stat`
```text
 docs/deploy/RUNBOOK-VPS.md | 45 +++++++++++++++++++++++++++++++++++++++++++++
 1 file changed, 45 insertions(+)
```

### 5.5. `git log --oneline -3`
```text
fb25692 feat(backend): Langkah 30 - kemiripan draft berulang dan perbandingan per pasal
752c967 fix(step30): angka terdekat dari kemiripan sebenarnya, margin batas atas
795fcc0 feat: kemiripan draft berulang (persen teks) dan perbandingan per pasal antar-draft
```

### 5.6. `git status --short` (sebelum commit)
```text
 M docs/deploy/RUNBOOK-VPS.md
?? docs/reports/step31-report.md
?? scripts/tarik_semua.py
?? tests/test_step31_tarik_semua.py
```
