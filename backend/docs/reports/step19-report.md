# LAPORAN LANGKAH 19: Tanggal Berlaku + Lampiran (Sisa Temuan QA)

**Branch:** `feat/step19-berlaku-lampiran`  
**Tanggal:** 17 Oktober 2026  
**Status:** SELESAI  

---

## 1. Ringkasan Perubahan

### A. Migrasi Database (`c9d0e1f2a3b4_step19_effective_date_attachments.py`)
- Menambahkan 5 kolom baru ke tabel `documents`:
  - `effective_date`: `Date`, nullable.
  - `is_attachment`: `Boolean`, not null, default `False`, dengan index.
  - `parent_document_id`: `Integer`, FK `documents.id` `ON DELETE SET NULL`, nullable, dengan index.
  - `parent_identity_key`: `String(120)`, nullable, dengan index.
  - `attachment_label`: `String(100)`, nullable.
- Fungsi `downgrade` penuh untuk mencabut seluruh kolom dan indeks terkait.

### B. Tanggal Berlaku & Aturan Status 5a
1. **Model & Skema Masukan**:
   - `ExtractionResultIn` (`internal.py`): menerima `effective_date` dengan alias `tanggal_berlaku` dan `mulai_berlaku`.
   - `UpdateMetadataIn` (`documents.py`): menerima `effective_date`.
   - Proteksi koreksi manual: jika `metadata_corrected_at` sudah terisi, nilai dari worker masuk ke `ignored_fields`.
2. **Aturan 5a di `recompute_status` (`app/services/version_service.py`)**:
   - Jika tidak ada relasi masuk, dan `status_source` ∈ {`None`, `relasi`, `tanggal_berlaku`}, dan `effective_date` terisi dan `<= hari ini`:
     - `status_keberlakuan = "berlaku"`
     - `status_source = "tanggal_berlaku"`
     - Audit log dicatat dengan `rule: "tanggal_berlaku"`.
   - Aturan ini tidak menimpa status `manual` atau `lapisan_data`.
   - `effective_date` di masa depan dibiarkan (status tetap seperti apa adanya).
   - `recompute_status` tetap menjalankan aturan 5a meskipun dokumen belum memiliki `identity_key` (relasi tidak relevan untuk dokumen tanpa kunci).
   - Dokumen lampiran (`is_attachment = True`) hanya menjalankan aturan 5a.
3. **Pemicu**:
   - Dipanggil setiap kali `effective_date` berubah pada PATCH extraction maupun koreksi metadata pengguna.
   - Penanganan galat dibungkus `try/except` sehingga tidak menggagalkan endpoint (pola yang sama dengan Langkah 18).
4. **Skrip CLI (`scripts/recompute_status.py`)**:
   - Mendukung `--dry-run` (default) dan `--apply`.
   - Menghitung ulang status semua dokumen aktif dan mencatat perubahan status yang terjadi.

### C. Penanganan Lampiran & Penautan Induk
1. **Layanan Lampiran (`app/services/attachment_service.py`)**:
   - `detect_attachment_heuristics(title, original_filename, fallback_key)`:
     - Mendeteksi judul yang diawali `LAMPIRAN` (case-insensitive) atau nama berkas yang memuat kata `LAMPIRAN`.
     - Mengekstrak label lampiran dengan regex `LAMPIRAN\s+([IVXLC]+|\d+)` (mis. `Lampiran I`, `Lampiran II`), fallback ke `Lampiran`.
     - Kunci induk diisi dari `fallback_identity_key` jika jenis, nomor, tahun terbaca.
   - `link_attachment(db, doc)`: Menautkan lampiran ke induk non-lampiran aktif yang memiliki `identity_key == doc.parent_identity_key`.
   - `link_pending_children(db, parent_doc)`: Menautkan dokumen lampiran yang masih pending (`parent_document_id IS NULL`) saat dokumen induk non-lampiran mendapat `identity_key`.
2. **Isolasi Lampiran**:
   - Dokumen dengan `is_attachment = True` tidak diberi `identity_key` (`doc.identity_key = None`).
   - `check_identity_duplicate` mengabaikan dokumen lampiran, dan rekan kandidat (`peers`) menyaring dokumen lampiran (`is_attachment == False`).
3. **Validasi Koreksi Pengguna (`UpdateMetadataIn`)**:
   - `parent_document_id` divalidasi: tidak boleh merujuk ke dirinya sendiri, tidak boleh merujuk ke dokumen lampiran lain, dan harus dokumen yang ada (mengembalikan HTTP 422 bila salah).
   - Jika pengguna mengatur `is_attachment = False`, seluruh tautan induk dan label dikosongkan (`parent_document_id = None`, `parent_identity_key = None`, `attachment_label = None`).
4. **Format Respons**:
   - Respons `GET /api/v1/documents/{id}` menyertakan field `effective_date`, `is_attachment`, `parent_document_id`, `parent_identity_key`, `attachment_label`, `lampiran[]`, dan `induk`.
   - `induk` disamarkan (`null`) jika dokumen induk berstatus non-publik saat mode lindung aktif.
   - Filter query opsional `lampiran=true|false` ditambahkan pada `GET /api/v1/documents/`.

---

## 2. Catatan untuk Lapisan Data (Data / Worker)

### Field Baru PATCH Extraction
Endpoint: `PATCH /api/v1/internal/documents/{document_id}/extraction`  
Header: `X-Internal-API-Key: <INTERNAL_API_KEY>`

Field tambahan yang didukung pada payload:
1. `tanggal_berlaku` (alias `effective_date`, `mulai_berlaku`): format tanggal `YYYY-MM-DD`.
2. `lampiran_dari` (alias `parent_identity_key`): format kunci identitas regulasi induk `JENIS|NOMOR|TAHUN` (mis. `"POJK|91|2026"`). Jika dikirim, dokumen otomatis ditandai sebagai `is_attachment = True`.
3. `label_lampiran` (alias `attachment_label`): penanda label lampiran, misalnya `"Lampiran I"`, `"Lampiran II"`.

#### Contoh Payload Ekstraksi Lampiran
```json
{
  "title": "LAMPIRAN I PERATURAN OTORITAS JASA KEUANGAN NOMOR 91 TAHUN 2026 TENTANG TATA KELOLA",
  "regulation_type": "POJK",
  "regulation_number": "91",
  "regulation_year": 2026,
  "tanggal_berlaku": "2026-10-15",
  "lampiran_dari": "POJK|91|2026",
  "label_lampiran": "Lampiran I"
}
```

#### Contoh Payload Ekstraksi Dokumen Utama dengan Tanggal Berlaku
```json
{
  "title": "Peraturan Otoritas Jasa Keuangan Nomor 92/POJK.03/2026 tentang Penerapan Manajemen Risiko",
  "regulation_type": "POJK",
  "regulation_number": "92",
  "regulation_year": 2026,
  "release_date": "2026-08-25",
  "tanggal_berlaku": "2026-10-15"
}
```

---

## 3. Catatan untuk Infra (DevOps / Sysadmin)

### Pemeliharaan Status Keberlakuan Harian
Regulasi yang tanggal berlakunya baru saja terlewati (`effective_date <= CURRENT_DATE`) memerlukan pembaruan status menjadi `berlaku`.

Jalankan perintah berikut secara berkala (misal setiap tengah malam via `cron` atau `systemd timer` di server VPS / container production):

```bash
docker compose exec backend python scripts/recompute_status.py --apply
```

Opsi default adalah `--dry-run` untuk meninjau perubahan tanpa menulis ke database:
```bash
docker compose exec backend python scripts/recompute_status.py --dry-run
```

---

## 4. Hasil Pengujian T01–T16 (`tests/test_step19_berlaku_lampiran.py`)

| # | Kasus | Ekspektasi | Hasil |
|---|---|---|:---:|
| T01 | PATCH extraction `tanggal_berlaku` = kemarin, dokumen tanpa relasi, `tidak_diketahui` | `effective_date` tersimpan; status `berlaku`, `status_source=tanggal_berlaku`; audit tercatat | **LULUS** |
| T02 | `tanggal_berlaku` = besok | status tetap `tidak_diketahui` | **LULUS** |
| T03 | Dokumen `manual` `dicabut`, lalu `effective_date` lampau dikirim | tetap `dicabut` / `manual` | **LULUS** |
| T04 | Ada relasi masuk MENCABUT penuh + `effective_date` lampau | `dicabut` (relasi menang) | **LULUS** |
| T05 | Dokumen **tanpa `identity_key`** + `effective_date` lampau | `berlaku` | **LULUS** |
| T06 | Koreksi metadata `effective_date` | tersimpan, status dihitung ulang; worker berikutnya tidak bisa menimpanya (`ignored_fields`) | **LULUS** |
| T07 | `recompute_status.py --dry-run` | DB tidak berubah, laporan memuat kandidat | **LULUS** |
| T08 | PATCH extraction dokumen berjudul `LAMPIRAN I PERATURAN OTORITAS JASA KEUANGAN NOMOR 91 …`, jenis POJK, nomor `91`, tahun 2026 | `is_attachment=True`, `attachment_label="Lampiran I"`, `parent_identity_key="POJK\|91\|2026"`, `identity_key=None` | **LULUS** |
| T09 | Induk POJK 91 (`POJK\|91\|2026`) sudah ada; lampiran T08 masuk | `parent_document_id` = id induk; `GET` induk memuat lampiran di `lampiran[]` | **LULUS** |
| T10 | Lampiran masuk **lebih dulu**, induk menyusul dan mendapat `identity_key` | lampiran tertaut otomatis | **LULUS** |
| T11 | Induk dan lampiran dengan nomor sama | **tidak ada** yang dinonaktifkan oleh cek duplikat | **LULUS** |
| T12 | Koreksi metadata `parent_document_id` = dirinya sendiri; = dokumen lampiran lain; = id tidak ada | 422 untuk ketiganya | **LULUS** |
| T13 | Koreksi metadata `is_attachment=false` | label dan tautan induk dikosongkan | **LULUS** |
| T14 | Worker mengirim `lampiran_dari="POJK\|92\|2026"`, `label_lampiran="Lampiran II"` | tersimpan; tertaut bila induknya ada | **LULUS** |
| T15 | `GET /documents?lampiran=false` | lampiran tidak tercantum | **LULUS** |
| T16 | Lampiran dari induk non-publik, mode lindung | `induk` bernilai `null` | **LULUS** |

---

## 5. Verifikasi Linter & Seluruh Suite Pengujian

### A. Ruff Check
Perintah:
```powershell
.\venv\Scripts\ruff.exe check --select E9,F821,F822,F823 app scripts tests
```
Output:
```
All checks passed!
```

### B. Pytest Suite Penuh
Perintah:
```powershell
.\venv\Scripts\python.exe -m pytest -q
```
Output:
```
353 passed, 1 skipped, 96 warnings in 425.95s (0:07:05)
```

---

## 6. Uji Live Docker

Perintah & Output:
```powershell
PS C:\Hero\hero-backend> docker compose up -d --build backend
#13 naming to docker.io/library/hero-backend-backend:latest 0.0s done
#13 unpacking to docker.io/library/hero-backend-backend:latest 4.2s done
#13 DONE 22.1s
 hero-backend-backend  Built
 Container hero_postgres  Running
 Container hero_fastapi  Recreate
 Container hero_fastapi  Recreated
 Container hero_postgres  Waiting
 Container hero_postgres  Healthy
 Container hero_fastapi  Starting
 Container hero_fastapi  Started

PS C:\Hero\hero-backend> curl.exe -s http://localhost:8000/health
{"status":"ok","database":"ok","version":"0.10.0","app_env":"development","alembic_revision":"c9d0e1f2a3b4","alembic_head":"c9d0e1f2a3b4","migrations_up_to_date":true,"storage_writable":true,"crawler_backend":"simple_http","crawler_loaded":true,"auth_enabled":false,"protect_non_public":true}

PS C:\Hero\hero-backend> docker compose exec backend python scripts/recompute_status.py --dry-run
=== Menjalankan Perhitungan Ulang Status Dokumen [DRY-RUN (bawaan - simulasi tanpa perubahan DB)] ===
Total dokumen aktif di database: 71
Jumlah dokumen yang terpengaruh/kandidat perubahan: 0
Tidak ada dokumen yang memerlukan perubahan status.

[DRY-RUN] Database di-rollback. Tidak ada perubahan yang disimpan ke database.
```

