# Pemetaan Label Jenis Temuan Harmonisasi

Dokumen ini mendokumentasikan pemetaan nilai jenis temuan internal engine harmonisasi ke label tampilan pada Antarmuka Pengguna (UI) dan berkas ekspor (XLSX, Word/DOCX, Catatan Dinas).

> [!NOTE]
> Kosakata akhir (istilah UI vs istilah DPEA/SRS) masih menunggu konfirmasi lebih lanjut dari tim. Perubahan saat ini menyelaraskan seluruh format ekspor dengan tampilan UI saat ini.

## Tabel Pemetaan

| Nilai Internal (Engine/Pipeline) | Istilah SRS / DPEA | Label di UI | Label di Ekspor (XLSX, DOCX, Catatan Dinas) |
|---|---|---|---|
| `pasal_baru` / `baru` | Pasal Baru / Ketentuan Baru | Baru | Baru |
| `duplikasi` / `sama` | Duplikasi / Kesamaan Norma | Sama | Sama |
| `memperjelas` / `melengkapi` | Memperjelas / Melengkapi | Melengkapi | Melengkapi |
| `menggantikan` | Menggantikan | Menggantikan | Menggantikan |
| `konflik` | Konflik / Pertentangan Norma | Konflik | Konflik |

*Catatan untuk format CSV:*
Ekspor CSV harmonisasi tetap mempertahankan nilai mentah (`t.get("jenis")`) yang dinetralkan dari injeksi formula untuk keperluan interoperabilitas data dan integrasi hilir.

## Catatan Khusus: `rujukan_dicabut` (TC-33)

Berdasarkan penelusuran implementasi pipeline dan backend:
1. `rujukan_dicabut` **bukan** merupakan salah satu kategori jenis temuan (`jenis`), melainkan informasi status pada:
   - Jumlah numerik di `ringkasan.rujukan_dicabut` (misal: `2`).
   - Penanda `status: "dicabut"` pada daftar `rujukan[]` untuk peraturan pembanding yang telah dicabut.
   - Rekomendasi/banner peringatan bagi analis hukum.
2. Sesuai skenario UAT dan TC-33 (`docs/11-test-plan-uat.md`), backend meneruskan (*pass-through*) data ini dari engine ML ke klien tanpa perubahan.
3. Terhadap pengguna yang tidak memiliki hak akses dokumen non-publik, rujukan ke peraturan non-publik yang dicabut tetap disaring secara aman oleh `saring_rujukan_lengkap` (detail sensitif seperti `document_id`, `kutipan`, `pdf`, `halaman`, dan `pasal` dinetralkan/dihapus, sementara status dan nama tetap tersampaikan untuk keperluan peringatan keberlakuan).
