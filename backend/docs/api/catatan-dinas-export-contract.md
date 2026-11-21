# Kontrak & Spesifikasi Ekspor Catatan Dinas Harmonisasi

Dokumentasi endpoint ekspor format Catatan Dinas (DOCX dan PDF) sesuai keputusan **Weekly Update #10** dan **Backlog #76**.

---

## Endpoint API

- **Method:** `POST`
- **URL Path:** `/api/v1/documents/{document_id}/harmonisasi/ekspor/catatan-dinas`
- **Otorisasi / Izin:** Memerlukan izin `ANALISA_EKSPOR` (peran `analis`, `admin_kb`, atau `admin_sistem`).
- **Target Dokumen:** Hanya berlaku untuk dokumen bertipe `draft_kajian` yang telah memiliki hasil harmonisasi tersimpan.

---

## Skema Permintaan (Request Body)

Format: `application/json` (seluruh field bersifat opsional; jika kosong atau omit, backend menggunakan nilai bawaan kop baku).

| Field | Tipe | Maks Karakter | Nilai Bawaan (Default) | Keterangan |
|---|---|---|---|---|
| `format` | string | - | `"docx"` | Pilihan: `"docx"` atau `"pdf"`. |
| `run_id` | integer | - | `null` | Opsional: ID riwayat eksekusi harmonisasi spesifik. |
| `pakai_ai` | boolean | - | `false` | `true` untuk mengaktifkan narasi AI pada Butir 1 (Latar Belakang). |
| `nomor_cd` | string | 60 | `"CD-xx/…/xxxx"` | Nomor Catatan Dinas (dapat dikonfigurasi via `CD_PLACEHOLDER_NOMOR_CD`). |
| `yth` | string | 200 | `"Kepala Departemen"` | Kepada / Yth. (Baku Weekly #10; dikonfigurasi via `CD_DEFAULT_YTH`). |
| `dari` | string | 200 | `"Analis Eksekutif"` | Dari (Baku Weekly #10; dikonfigurasi via `CD_DEFAULT_DARI`). |
| `sifat` | string | 60 | `"Biasa"` | Sifat naskah dinas (dikonfigurasi via `CD_DEFAULT_SIFAT`). |
| `lampiran` | string | 120 | `"-"` | Lampiran surat (dikonfigurasi via `CD_DEFAULT_LAMPIRAN`). |
| `hal` | string | 300 | `"Tanggapan atas <judul draf>"` | Perihal (Otomatis dicegah agar tidak menduplikasi jika judul draf sudah diawali kata tersebut; pola diatur via `CD_DEFAULT_HAL_TEMPLATE`). |
| `tanggal` | date (YYYY-MM-DD) | - | `"…"` | Tanggal Catatan Dinas diisi manual oleh pengguna. Bila kosong, menampilkan placeholder `"…"`, **bukan** tanggal hari ini. Bila diisi, diformat misal: `13 November 2026`. |
| `unit_peminta` | string | 200 | `"…"` | Unit kerja peminta nota dinas. |
| `nomor_nd` | string | 60 | `"ND-xx/…/xxxx"` | Nomor Nota Dinas permintaan. |
| `tanggal_nd` | date (YYYY-MM-DD) | - | `"…"` | Tanggal Nota Dinas permintaan. Bila diisi, diformat misal: `25 Oktober 2026`. |
| `hal_nd` | string | 300 | `"…"` | Perihal Nota Dinas permintaan. |
| `catatan_tambahan`| string | 4000 | `null` | Catatan tambahan untuk Butir 4. Jika kosong/omit, Butir 4 dilewati dan penomoran butir berikutnya otomatis menyesuaikan. |
| `penandatangan_jabatan` | string | 200 | `"…"` | Jabatan penandatangan. |
| `penandatangan_nama` | string | 200 | `"…"` | Nama penandatangan. |
| `penandatangan_nip` | string | 30 | `"…"` | NIP penandatangan. |

---

## Konfigurasi Tanpa Ubah Kode (Backlog #76)

Nilai bawaan kop dan placeholder dapat diatur tanpa mengubah kode sumber melalui environment variables atau berkas `.env`:

```env
# Nilai bawaan kop Catatan Dinas
CD_DEFAULT_YTH="Kepala Departemen"
CD_DEFAULT_DARI="Analis Eksekutif"
CD_DEFAULT_SIFAT="Biasa"
CD_DEFAULT_LAMPIRAN="-"
CD_DEFAULT_HAL_TEMPLATE="Tanggapan atas {judul}"

# Placeholder isian yang diisi manual atau belum ditentukan
CD_PLACEHOLDER_TANGGAL="…"
CD_PLACEHOLDER_NOMOR_CD="CD-xx/…/xxxx"
CD_PLACEHOLDER_NOMOR_ND="ND-xx/…/xxxx"
CD_PLACEHOLDER_UNIT_PEMINTA="…"
CD_PLACEHOLDER_HAL_ND="…"
```

---

## Contoh Body Permintaan Minimal (Untuk Frontend / Ikhwan)

### Permintaan Minimal (Hanya Format)
```json
{
  "format": "docx"
}
```
*(atau `{"format": "pdf"}` untuk keluaran PDF)*

### Hasil Keluaran Bawaan pada Dokumen:
1. **Nomor:** `NOMOR CD-xx/…/xxxx`
2. **Kop Identitas:**
   - **Yth.:** `Kepala Departemen`
   - **Dari:** `Analis Eksekutif`
   - **Sifat:** `Biasa`
   - **Lampiran:** `-`
   - **Hal:** `Tanggapan atas Rancangan Peraturan Otoritas Jasa Keuangan tentang Tata Kelola BPR`
   - **Tanggal:** `…` *(placeholder, tanggal tidak diisi otomatis)*
3. **Kalimat Pembuka:**
   `Sehubungan dengan nota dinas … nomor ND-xx/…/xxxx tanggal … hal …, dapat kami sampaikan hal-hal sebagai berikut:`
4. **Butir-butir Naskah:**
   - **1.** Latar belakang regulasi (jumlah bab, pasal, dan pokok pengaturan).
   - **2.** Riwayat permintaan tanggapan.
   - **3.** Tanggapan atas seluruh temuan harmonisasi (dikelompokkan per pasal draf).
   - **4.** *(Butir Catatan Tambahan otomatis dilewati karena kosong).*
   - **4.** `Apabila Bapak/Ibu sependapat, terlampir konsep nota dinas tanggapan untuk ditindaklanjuti.` *(penomoran otomatis bergeser ke 4).*
5. **Kalimat Penutup:**
   `Demikian kami sampaikan, atas perhatian Bapak/Ibu kami ucapkan terima kasih.`
6. **Blok Penandatangan:**
   - Jabatan: `…`
   - Nama: `…`
   - NIP: `…`

---

## Header Respons

- **DOCX:**
  - `Content-Type`: `application/vnd.openxmlformats-officedocument.wordprocessingml.document`
  - `Content-Disposition`: `attachment; filename="catatan_dinas_<slug>_<id>.docx"; filename*="UTF-8''..."`
- **PDF:**
  - `Content-Type`: `application/pdf`
  - `Content-Disposition`: `attachment; filename="catatan_dinas_<slug>_<id>.pdf"; filename*="UTF-8''..."`
- **Status AI (saat `pakai_ai: true`):**
  - `X-Catatan-Dinas-AI`: `"dipakai"` | `"tidak_tersedia"`
