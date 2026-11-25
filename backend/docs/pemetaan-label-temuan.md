# Pemetaan Label Jenis Temuan Harmonisasi

Dokumen ini mendokumentasikan pemetaan nilai jenis temuan internal engine harmonisasi ke label tampilan pada Antarmuka Pengguna (UI) dan berkas ekspor (XLSX, Word/DOCX, Catatan Dinas, Lembar Sampling).

> [!NOTE]
> Label ekspor kini mengikuti istilah mitra, yaitu `LABEL_TEXT` di `pipeline/hero/harmonisasi/engine.py` (definisi mitra, PR #233). Kunci internal tidak berubah.

> [!IMPORTANT]
> UI frontend (`HarmonisasiPanel.tsx`, `harmonisasiApi.ts`) masih memakai label lama Baru/Sama/Melengkapi/Konflik dan perlu disesuaikan agar tampilan sama dengan berkas ekspor.

## Tabel Pemetaan

| Nilai Internal (Engine/Pipeline) | Istilah SRS / DPEA | Label di UI (saat ini, perlu disesuaikan) | Label di Ekspor (XLSX, DOCX, Catatan Dinas, Lembar Sampling) — istilah mitra |
|---|---|---|---|
| `pasal_baru` / `baru` | pasal baru | Baru | Pasal Baru |
| `duplikasi` / `sama` | duplikasi | Sama | Tumpang Tindih |
| `memperjelas` / `melengkapi` | memperjelas | Melengkapi | Selaras / Melengkapi |
| `menggantikan` | menggantikan | Menggantikan | Menggantikan |
| `konflik` | konflik | Konflik | Kontradiktif |

Nilai `jenis` yang tidak dikenal tetap memakai fallback lama (nilai mentah / kapitalisasi) di tiap format.

*Catatan untuk format CSV:*
Ekspor CSV harmonisasi tetap mempertahankan nilai mentah (`t.get("jenis")`) yang dinetralkan dari injeksi formula untuk keperluan interoperabilitas data dan integrasi hilir.

## Catatan Khusus: `rujukan_dicabut` (TC-33)

Berdasarkan penelusuran implementasi pipeline dan backend:
1. `rujukan_dicabut` **bukan** merupakan salah satu kategori jenis temuan (`jenis`), melainkan informasi status pada:
   - Jumlah numerik di `ringkasan.rujukan_dicabut` (misal: `2`).
   - Penanda `status: "dicabut"` pada daftar `rujukan[]` untuk peraturan pembanding yang telah dicabut.
   - Rekomendasi/banner peringatan bagi analis hukum.
2. TC-33 di `docs/11-test-plan-uat.md` mensyaratkan hasil "Muncul temuan `rujukan_dicabut`", sedangkan implementasi saat ini menampilkan banner, status pada rujukan, dan rekomendasi. Ketidaksesuaian ini menunggu keputusan tim (ubah kriteria TC-33, atau tambahkan temuan tersendiri di pipeline). Backend meneruskan data ini tanpa perubahan.
3. Terhadap pengguna yang tidak memiliki hak akses dokumen non-publik, rujukan ke peraturan non-publik yang dicabut tetap disaring secara aman oleh `saring_rujukan_lengkap` (detail sensitif seperti `document_id`, `kutipan`, `pdf`, `halaman`, dan `pasal` dinetralkan/dihapus, sementara status dan nama tetap tersampaikan untuk keperluan peringatan keberlakuan).
