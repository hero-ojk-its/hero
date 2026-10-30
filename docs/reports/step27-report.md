# LAPORAN LANGKAH 27 — STATISTIK CORONG PER SUMBER (SCAN → UNDUH → SIMPAN → TERBACA) DAN PENANDA PDF DIPROTEKSI

## 1. Ringkasan Perubahan

1. **Skema & Migrasi Database (`b4c5d6e7f8a9_step27_pdf_terproteksi.py`)**:
   - Menambahkan kolom `pdf_terproteksi` (Boolean, nullable, index) pada tabel `documents`.
   - `NULL` menandakan dokumen lama yang belum diperiksa sebelum Langkah 27.
   - Upgrade dan downgrade diuji aman.

2. **Validasi PDF & Ekstraksi Metadata (`app/services/file_validation.py`)**:
   - Membuat dataclass beku `PdfInfo(terproteksi: bool, jumlah_halaman: int)`.
   - `validate_pdf()` mengembalikan `PdfInfo` saat validasi sukses tanpa mengubah aturan penolakan berkas.
   - Berkas dengan *owner password* / salin-proteksi diterima (`decrypt("")` berhasil) dengan `terproteksi=True`.

3. **Penyimpanan Status Proteksi & Halaman (`app/services/ingest_service.py`, `app/services/failure_service.py`)**:
   - Menetapkan `pdf_terproteksi` dan `page_count` saat dokumen dibuat dari unggah manual, penarikan scan, maupun pemrosesan ulang kegagalan (*retry*).

4. **Skrip Backfill (`scripts/backfill_pdf_info.py`)**:
   - Membaca dokumen dengan `pdf_terproteksi IS NULL` dari penyimpanan lokal (`StorageService`).
   - Default `--dry-run` (hanya menghitung kandidat tanpa menulis ke DB).
   - `--apply` untuk memperbarui DB dengan commit berkala per 100 dokumen. Berkas PDF rusak/hilang dilewati tanpa menggagalkan proses.

5. **Endpoint Dashboard Corong (`GET /api/v1/dashboard/corong`)**:
   - Otorisasi memerlukan izin `KB_BACA` (peran `admin_sistem`, `admin_kb`, `analis`).
   - Mendukung filter `source_id` opsional dan `format=json|csv`.
   - Seluruh metrik dihitung murni menggunakan agregasi SQL (`COUNT`, `SUM`, `CASE`, `EXISTS`), tanpa memuat `full_text` ke memori.
   - Mendukung ekspor CSV UTF-8 dengan BOM (`utf-8-sig`) dan header lengkap.

6. **Drill-down Filter Antrean Kegagalan (`GET /api/v1/ingest/failures`)**:
   - Menambahkan parameter query `reason_code` (mendukung multi-nilai) dan `source_id` (filter via `job.source_id` atau `scan_candidates.failure_id`).
   - Memungkinkan navigasi satu klik dari corong ke daftar kegagalan terkait.

7. **Kontrak API & Dokumentasi**:
   - Kontrak API diperbarui di `docs/api/KONTRAK-API-FASE1.md` (§9.2 dan §10.2) serta `docs/api/openapi-fase1.json`.

---

## 2. Output Mentah JSON Lokal `/api/v1/dashboard/corong`

```json
{"dihitung_pada":"2026-10-30T07:34:50Z","sumber":[{"source_id":1,"nama":"Regulasi OJK (Situs Resmi)","jenis":"situs_web","scan":{"ditemukan":90,"sudah_ada_di_kb":16,"ditarik":7,"duplikat":0,"gagal_unduh":0,"belum_ditarik":67},"dokumen":{"di_kb":23,"tersimpan_di_kb":23,"menunggu_ekstraksi":23,"terbaca":0,"terbaca_teks_langsung":0,"terbaca_ocr":0,"perlu_koreksi":0,"gagal_baca":0,"lainnya":0,"terpecah_pasal":0,"tervektor":0},"pdf":{"terproteksi":0,"terproteksi_terbaca":0,"hasil_pindai_ocr":0,"ocr_gagal":0,"belum_diperiksa":0},"gagal_per_alasan":{},"persen_terbaca":0.0},{"source_id":2,"nama":"JDIH OJK (Situs Resmi)","jenis":"situs_web","scan":{"ditemukan":506,"sudah_ada_di_kb":12,"ditarik":2,"duplikat":1,"gagal_unduh":0,"belum_ditarik":491},"dokumen":{"di_kb":17,"tersimpan_di_kb":17,"menunggu_ekstraksi":17,"terbaca":0,"terbaca_teks_langsung":0,"terbaca_ocr":0,"perlu_koreksi":0,"gagal_baca":0,"lainnya":0,"terpecah_pasal":0,"tervektor":0},"pdf":{"terproteksi":0,"terproteksi_terbaca":0,"hasil_pindai_ocr":0,"ocr_gagal":0,"belum_diperiksa":0},"gagal_per_alasan":{},"persen_terbaca":0.0},{"source_id":3,"nama":"OneDrive Public DPEA","jenis":"onedrive_public","scan":{"ditemukan":2612,"sudah_ada_di_kb":15,"ditarik":0,"duplikat":0,"gagal_unduh":0,"belum_ditarik":2597},"dokumen":{"di_kb":15,"tersimpan_di_kb":13,"menunggu_ekstraksi":15,"terbaca":0,"terbaca_teks_langsung":0,"terbaca_ocr":0,"perlu_koreksi":0,"gagal_baca":0,"lainnya":0,"terpecah_pasal":0,"tervektor":0},"pdf":{"terproteksi":0,"terproteksi_terbaca":0,"hasil_pindai_ocr":0,"ocr_gagal":0,"belum_diperiksa":0},"gagal_per_alasan":{},"persen_terbaca":0.0},{"source_id":7,"nama":"uji_folder","jenis":"folder_lokal","scan":{"ditemukan":2,"sudah_ada_di_kb":2,"ditarik":0,"duplikat":0,"gagal_unduh":0,"belum_ditarik":0},"dokumen":{"di_kb":2,"tersimpan_di_kb":0,"menunggu_ekstraksi":2,"terbaca":0,"terbaca_teks_langsung":0,"terbaca_ocr":0,"perlu_koreksi":0,"gagal_baca":0,"lainnya":0,"terpecah_pasal":0,"tervektor":0},"pdf":{"terproteksi":0,"terproteksi_terbaca":0,"hasil_pindai_ocr":0,"ocr_gagal":0,"belum_diperiksa":0},"gagal_per_alasan":{},"persen_terbaca":0.0},{"source_id":8,"nama":"demo_ojk_peraturan","jenis":"folder_lokal","scan":{"ditemukan":5,"sudah_ada_di_kb":5,"ditarik":0,"duplikat":0,"gagal_unduh":0,"belum_ditarik":0},"dokumen":{"di_kb":5,"tersimpan_di_kb":5,"menunggu_ekstraksi":5,"terbaca":0,"terbaca_teks_langsung":0,"terbaca_ocr":0,"perlu_koreksi":0,"gagal_baca":0,"lainnya":0,"terpecah_pasal":0,"tervektor":0},"pdf":{"terproteksi":0,"terproteksi_terbaca":0,"hasil_pindai_ocr":0,"ocr_gagal":0,"belum_diperiksa":0},"gagal_per_alasan":{},"persen_terbaca":0.0}],"unggah_manual":{"dokumen":{"di_kb":12,"tersimpan_di_kb":2,"menunggu_ekstraksi":12,"terbaca":0,"terbaca_teks_langsung":0,"terbaca_ocr":0,"perlu_koreksi":0,"gagal_baca":0,"lainnya":0,"terpecah_pasal":0,"tervektor":0},"pdf":{"terproteksi":0,"terproteksi_terbaca":0,"hasil_pindai_ocr":0,"ocr_gagal":0,"belum_diperiksa":0},"gagal_per_alasan":{"format_tidak_didukung":1,"pdf_rusak":1,"pdf_terenkripsi":1},"persen_terbaca":0.0},"total":{"scan":{"ditemukan":3215,"sudah_ada_di_kb":50,"ditarik":9,"duplikat":1,"gagal_unduh":0,"belum_ditarik":3155},"dokumen":{"di_kb":71,"tersimpan_di_kb":57,"menunggu_ekstraksi":71,"terbaca":0,"terbaca_teks_langsung":0,"terbaca_ocr":0,"perlu_koreksi":0,"gagal_baca":0,"lainnya":0,"terpecah_pasal":0,"tervektor":0},"pdf":{"terproteksi":0,"terproteksi_terbaca":0,"hasil_pindai_ocr":0,"ocr_gagal":0,"belum_diperiksa":0},"gagal_per_alasan":{"pdf_rusak":1,"pdf_terenkripsi":1,"format_tidak_didukung":1},"persen_terbaca":0.0}}
```

---

## 3. Tabel Hasil Uji C01–C15 (`tests/test_step27_corong.py`)

| Kode | Kasus Uji | Ekspektasi | Status |
|:---|:---|:---|:---:|
| **C01** | Invarian scan | `ditemukan = sudah_ada_di_kb + ditarik + duplikat + gagal_unduh + belum_ditarik`. Deduplikasi per `url_hash`. | **LULUS** |
| **C02** | Invarian dokumen & persentase terbaca | `di_kb = menunggu_ekstraksi + terbaca + gagal_baca + lainnya`. `persen_terbaca` tepat 50.0%. | **LULUS** |
| **C03** | Agregat pasal & embedding | `terpecah_pasal` menghitung dokumen yang punya relasi pasal, `tervektor` menghitung pasal dengan pgvector. | **LULUS** |
| **C04** | Upload PDF diproteksi (owner pass) | Dokumen diterima, `pdf_terproteksi = True`, `page_count` terisi. | **LULUS** |
| **C05** | Upload PDF biasa | Dokumen diterima, `pdf_terproteksi = False`, `page_count` terisi. | **LULUS** |
| **C06** | PDF terproteksi terbaca & belum diperiksa | Agregat `pdf.terproteksi`, `pdf.terproteksi_terbaca`, dan `pdf.belum_diperiksa` akurat. | **LULUS** |
| **C07** | Agregasi gagal_per_alasan | `gagal_per_alasan` menghitung kegagalan aktif, mengabaikan `status=diabaikan` dan duplikat. `ocr_gagal` terhitung. | **LULUS** |
| **C08** | Isolasi unggah manual | Dokumen manual (`job.source_id IS NULL`) tidak masuk ke sumber mana pun, hanya di `unggah_manual`. | **LULUS** |
| **C09** | Deduplikasi dokumen multi-sumber di total | Dokumen yang terikat ke 2 sumber berbeda hanya dihitung 1 kali pada blok `total`. | **LULUS** |
| **C10** | Filter query `source_id` | Respons hanya mengembalikan array 1 sumber, total dokumen menghitung sumber itu saja. | **LULUS** |
| **C11** | Format CSV | Mengembalikan `200 OK`, `text/csv`, BOM UTF-8 (`\xef\xbb\xbf`), nama kolom sesuai spesifikasi. | **LULUS** |
| **C12** | Drill-down filter antrean kegagalan | Endpoint `/ingest/failures` memfilter berdasarkan `reason_code` (multi-nilai) dan `source_id`. | **LULUS** |
| **C13** | Backfill PDF info (`--dry-run` vs `--apply`) | Mode dry-run tidak mengubah baris, mode apply memperbarui `pdf_terproteksi` dan `page_count`. | **LULUS** |
| **C14** | Autorisasi endpoint corong | Pengguna tanpa izin `KB_BACA` ditolak `403 Forbidden` (`akses_ditolak`). | **LULUS** |
| **C15** | Corong tidak memuat `full_text` | Listener `before_cursor_execute` memastikan string `full_text` tidak pernah muncul di query SQL corong. | **LULUS** |

---

## 4. Hasil Eksekusi Pytest

### a. `tests/test_step27_corong.py`
```
...............                                                          [100%]
============================== warnings summary ===============================
venv\Lib\site-packages\fastapi\testclient.py:1
  C:\Hero\hero-backend\venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

venv\Lib\site-packages\starlette\testclient.py:53
  C:\Hero\hero-backend\venv\Lib\site-packages\starlette\testclient.py:53: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
15 passed, 2 warnings in 19.19s
```

### b. Seluruh Test Suite Backend (`pytest -q`)
```
........................................................................ [ 14%]
.............................................s.......................... [ 28%]
........................................................................ [ 42%]
........................................................................ [ 57%]
........................................................................ [ 71%]
........................................................................ [ 85%]
.......................................................................  [100%]
502 passed, 1 skipped, 179 warnings in 881.58s (0:14:41)
```

---

## 5. Hasil Ruff Linter

Perintah: `.\venv\Scripts\python.exe -m ruff check --select E9,F app scripts tests/test_step27_corong.py`
```
All checks passed!
```

---

## 6. Output Eksekusi Nyata dari Docker

### a. `docker compose exec backend python scripts/backfill_pdf_info.py` (DRY-RUN)
```
=== Menjalankan Backfill PDF Info [DRY-RUN (bawaan - tanpa perubahan DB)] ===
Kandidat dokumen (pdf_terproteksi IS NULL): 71
=== Ringkasan Hasil Backfill ===
Mode                : DRY-RUN (bawaan - tanpa perubahan DB)
Kandidat ditemukan  : 71
Total diproses      : 71
PDF terproteksi     : 0
PDF biasa           : 71
Dilewati (rusak/dll): 0
Page count diisi    : 71
```

### b. `docker compose exec backend python scripts/backfill_pdf_info.py --apply`
```
=== Menjalankan Backfill PDF Info [APPLY] ===
Kandidat dokumen (pdf_terproteksi IS NULL): 71
=== Ringkasan Hasil Backfill ===
Mode                : APPLY
Kandidat ditemukan  : 71
Total diproses      : 71
PDF terproteksi     : 0
PDF biasa           : 71
Dilewati (rusak/dll): 0
Page count diisi    : 71
```

### c. `curl.exe -s -D - -o NUL "http://localhost:8000/api/v1/dashboard/corong?format=csv"`
```
HTTP/1.1 200 OK
date: Fri, 30 Oct 2026 07:35:03 GMT
server: uvicorn
content-disposition: attachment; filename="corong-hero-20261030.csv"; filename*=UTF-8''corong-hero-20261030.csv
content-length: 1167
content-type: text/csv; charset=utf-8
vary: Origin
x-content-type-options: nosniff
x-frame-options: DENY
referrer-policy: strict-origin-when-cross-origin
```

### d. `scripts/smoke_fase2.py --base-url http://localhost:8000`
```
================================================================================
       HERO BACKEND SMOKE TEST FASE 2 (READ-ONLY) - http://localhost:8000
       Revisi Alembic Diharapkan: b4c5d6e7f8a9
       Autentikasi: Tidak ada HERO_SMOKE_TOKEN (mode anonim/dev)
================================================================================
================================================================================
Kode   | Cek                                  | Status   | Keterangan
--------------------------------------------------------------------------------
S01    | GET /health                          | OK       | rev=b4c5d6e7f8a9
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

## 7. Catatan untuk Pak Faris (Bahan Weekly #8)

1. **Statistik Pembacaan Dokumen**:
   - Dari 71 dokumen yang saat ini berada di basis pengetahuan lokal (`hero_db`), seluruh 71 dokumen telah berhasil di-backfill informasi halamannya (`page_count`) dan status proteksinya.
   - Di data lokal saat ini, status pemrosesan berada di antrean `menunggu_ekstraksi` (belum dijalankan ekstraksi penuh). Pada staging, corong ini akan langsung menampilkan pembagian: berapa yang terbaca teks langsung vs OCR vs gagal.
2. **Kondisi PDF Terproteksi**:
   - Di corpus lokal, 100% (71 dari 71 dokumen) merupakan PDF biasa tanpa proteksi sandi (`pdf_terproteksi = 0`).
   - Apabila di staging ditemukan PDF terproteksi izin salin (*owner password*), dokumen akan diterima dan ditandai `pdf_terproteksi = True`. Metrik `terproteksi_terbaca` akan memantau berapa banyak dari PDF proteksi tersebut yang berhasil dibaca teksnya oleh worker ekstraksi/OCR.
3. **Penyebab Gagal Terbanyak (Top 3)**:
   - Dari riwayat kegagalan yang tersimpan di sistem saat ini:
     1. `format_tidak_didukung` (berkas non-PDF atau ekstensi salah)
     2. `pdf_rusak` (berkas korup, EOF terpotong, atau 0 halaman dari temuan QA Langkah 26)
     3. `pdf_terenkripsi` (berkas butuh user password untuk dibuka)

---

## 8. Catatan untuk Tim Frontend (Ikhwan)

1. **Cara Mengonsumsi Endpoint Corong**:
   - Endpoint: `GET /api/v1/dashboard/corong`.
   - Header: `Authorization: Bearer <token>` (membutuhkan izin `KB_BACA`).
   - Response memuat `sumber` (array per sumber scraping/folder), `unggah_manual` (dokumen upload langsung), dan `total` (gabungan terdeduplikasi).
   - Nilai persentase keberhasilan pembacaan tersedia di field `persen_terbaca` (float 0.0 s.d. 100.0, pembulatan 1 desimal).
   - Invarian scan: `ditemukan = sudah_ada_di_kb + ditarik + duplikat + gagal_unduh + belum_ditarik`.
   - Invarian dokumen: `di_kb = menunggu_ekstraksi + terbaca + gagal_baca + lainnya`.
2. **Implementasi Drill-Down ke Antrean Kegagalan**:
   - Saat pengguna mengklik baris/kartu kegagalan pada corong, arahkan langsung ke halaman kegagalan dengan query parameters yang baru didukung:
     - `GET /api/v1/ingest/failures?reason_code=ocr_gagal&source_id=1`
     - Mendukung multiple reasons: `GET /api/v1/ingest/failures?reason_code=teks_kosong_ocr&reason_code=ocr_gagal&source_id=2`
3. **Ekspor CSV**:
   - Berikan tombol "Unduh CSV" yang memanggil `GET /api/v1/dashboard/corong?format=csv` (atau dengan filter `?format=csv&source_id=...`). Berkas yang diunduh sudah memiliki UTF-8 BOM sehingga aman dibuka langsung di Microsoft Excel tanpa masalah encoding.

---

## 9. Catatan Deployment Staging

Urutan eksekusi saat deploy branch ini ke server Staging:
1. `docker compose exec backend alembic upgrade head` (menerapkan migrasi `b4c5d6e7f8a9_step27_pdf_terproteksi.py`).
2. Jalankan backfill verifikasi dry-run:
   `docker compose exec backend python scripts/backfill_pdf_info.py`
3. Jalankan backfill apply ke DB:
   `docker compose exec backend python scripts/backfill_pdf_info.py --apply`
4. Lakukan restart service backend/worker agar menggunakan logika validasi dan ekstraksi terbaru:
   `docker compose restart backend worker`
