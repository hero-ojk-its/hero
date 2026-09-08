# Panduan Kontribusi — HERO

## Alur kerja

1. **Ambil issue dari Project board** kolom `Todo` pada sprint berjalan. Jangan mulai pekerjaan
   yang belum ada issue-nya — RTM harus tetap utuh.
2. **Buat branch** dari `main`:
   ```
   <tipe>/<id-story>-<ringkas>
   ```
   Contoh: `feat/US-13-mesin-scraping`, `fix/TC-09-deteksi-duplikat`, `spike/US-32a-parser-pasal`

   Tipe: `feat` · `fix` · `spike` · `docs` · `chore` · `refactor` · `test`
3. **Commit** memakai Conventional Commits, sertakan ID story:
   ```
   feat(scraper): tambah kontrol kedalaman crawling per sumber (US-13a)
   ```
4. **Buka PR** ke `main`, isi template, tautkan issue dengan `Closes #`.
5. **Minta review** minimal satu anggota lain. PR tidak di-merge oleh penulisnya sendiri.

## Definition of Done

Sebuah story selesai bila:

- [ ] Seluruh kriteria penerimaan terpenuhi dan diverifikasi
- [ ] Kode di-review minimal satu anggota lain
- [ ] Pengujian fungsional terkait lulus
- [ ] Berjalan pada mode Deterministik tanpa layanan AI (bila menyentuh alur analisa)
- [ ] Terintegrasi ke lingkungan staging
- [ ] Audit log tercatat untuk aksi yang relevan
- [ ] Dokumentasi terkait diperbarui
- [ ] Tidak menyisakan defect severity Kritis/Tinggi yang terbuka

## Aturan yang tidak boleh dilanggar

| Aturan | Alasan |
| --- | --- |
| **Mode Deterministik wajib jalan tanpa AI** | Aplikasi harus tetap berfungsi saat offline, tanpa internet, tanpa anggaran AI |
| **AI tidak boleh mengubah substansi** | Lapisan AI hanya menaturalkan narasi; hasil deterministik disimpan terpisah |
| **Setiap keluaran berlabel *Draft / Rekomendasi*** | Keputusan final adalah kewenangan Pengawas DPEA, bukan sistem |
| **Setiap butir keluaran mengutip pasal sumbernya, apa adanya** | Validator DPEA memeriksa dengan membuka peraturan aslinya. Parafrase membuat validasi mustahil dinilai |
| **Dokumen peraturan tidak masuk repositori** | Dokumen internal DPEA tunduk NDA |
| **Dokumen non-publik tidak dikirim ke layanan AI pihak ketiga** | Periksa `klasifikasi_akses` lebih dulu. Model lokal menghilangkan risiko ini |

## Sebelum commit

```bash
git status
```

Pastikan tidak ada: berkas `.pdf` dokumen peraturan, folder `data/`, berkas `.env`, atau
kredensial apa pun. Bila terlanjur ter-commit, **jangan hanya menghapusnya di commit berikutnya** —
lapor ke PM agar riwayatnya dibersihkan.

## Penamaan issue

| Prefiks | Untuk |
| --- | --- |
| `[US-xx]` | User story |
| `[BUG]` | Cacat |
| `[SPIKE]` | Investigasi berbatas waktu |
| `[MITRA]` | Terblokir menunggu DPEA |
