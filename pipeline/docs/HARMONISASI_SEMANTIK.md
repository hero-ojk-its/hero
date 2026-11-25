# Harmonisasi — kesesuaian makna, label, dan status relasi

*Tim Data/ML, 24 November 2026. Issue #67 (FR-HRM-05), #68, #28; status keberlakuan #53.*

Dokumen ini menjelaskan **apa yang berubah pada mesin harmonisasi, kenapa, dan dengan bukti apa**.
Setiap angka di bawah dapat diulang: perintahnya ada di bagian akhir.

## 1. Ringkasan untuk mitra

| Pertanyaan | Jawaban singkat |
|---|---|
| Apakah pasal yang **beda redaksi tetapi bermakna sama** kini terdeteksi? | Ya. Pada set uji parafrase, 14 dari 15 parafrase dikenali sebagai *Tumpang Tindih* (mesin sebelumnya: 0 dari 15). |
| Apakah deteksi pada peraturan nyata membaik? | Ya, sedikit dan konsisten: recall 91,8% → **92,9%** (mode terarah) dan 85,0% → **86,1%** (seluruh KB), pada 45 pasangan perubahan ↔ induk. |
| Apakah ada teks yang dikirim ke layanan AI luar? | Tidak. Model makna berjalan lokal di server (ONNX). Tanpa model, mesin kembali ke perhitungan kata (TF-IDF) seperti sebelumnya. |
| Bagaimana status *mencabut / mencabut sebagian / mengubah* ditentukan? | Dari teks peraturan itu sendiri: judul dan pasal penutup (rincian di §4). |

## 2. Label — definisi yang dipakai mesin

| Label (tampilan) | Kunci internal | Kapan |
|---|---|---|
| **Menggantikan** | `menggantikan` | Draft **mencabut/mengubah** peraturan pembanding (relasi eksplisit). Perbedaan isinya dibaca sebagai penggantian, **bukan** konflik. |
| **Kontradiktif** | `konflik` | Objek sama, **ayat lawan ayat**: angka, batas waktu, nilai Rupiah, persentase, atau modalitas (wajib/dilarang/dapat/tidak wajib) berbeda — dan keduanya tetap berlaku. |
| **Tumpang Tindih** | `duplikasi` | Substansi hampir sama, hanya beda redaksi (kesamaan redaksi ≥ 0,80, atau kemiripan makna ≥ 0,88). |
| **Selaras / Melengkapi** | `memperjelas` | Topik sama, tidak bertentangan, tidak mengulang (mengatur aspek lain). |
| **Pasal Baru** | `pasal_baru` | Objek belum diatur di KB **untuk pihak yang diatur draft**, atau draft sendiri menyatakan pasal itu *disisipkan*. |

Kunci internal tidak berubah, sehingga backend, frontend, dan ekspor tetap berjalan.

### Perubahan aturan dan alasannya

1. **"Menggantikan" kini hanya untuk relasi eksplisit.** Dulu, pasal yang objeknya sama dan
   redaksinya berbeda tanpa relasi apa pun jatuh ke "menggantikan (keyakinan diturunkan)". Itu
   bertentangan dengan definisi mitra. Pada set uji, 9 dari 15 parafrase dulu berlabel "menggantikan".
2. **Kontradiksi diperiksa sebelum tumpang tindih.** Pasal yang hanya berubah satu angka punya
   kesamaan redaksi ≥ 0,95 sehingga dulu berlabel "duplikasi" (5 dari 15 varian kontradiktif).
3. **Kontradiksi dibandingkan ayat lawan ayat.** "15 hari" di ayat (2) draft tidak lagi diadu dengan
   "7 hari" milik ayat lain yang mengatur hal berbeda.
4. **Dua celah pembacaan angka/modalitas diperbaiki.** "50%" (tanda persen) dulu tidak pernah terbaca,
   dan "tidak wajib" dulu terbaca sebagai "wajib".
5. **Gerbang pihak yang diatur.** Pasal lintas peraturan yang mirip sering kali hanya ketentuan templat
   untuk *pihak lain* (RUPS 60 hari bagi Lembaga Penjamin vs bagi Perusahaan Pergadaian). Pihak dibaca
   dari perihal peraturan memakai leksikon sektor jasa keuangan; bila berbeda, pasal itu dibaca
   *Pasal Baru* untuk pihak draft dan ketentuan serupanya ditampilkan sebagai rujukan penyelarasan.
6. **Klausul templat** (sanksi, pengumuman sanksi, definisi, mulai berlaku, delegasi ke SEOJK) tidak
   boleh disebut tumpang tindih hanya karena maknanya mirip, dan keyakinannya diturunkan (×0,6).

## 3. Kemiripan makna — pemilihan metode

**Data uji 1, perilaku nyata.** Ada 45 pasangan peraturan perubahan ↔ induk di KB. Kebenarannya
diambil dari teks perubahan itu sendiri: 412 pasal *diubah* menjadi positif, dan 179 pasal
*disisipkan* menjadi negatif. Korpusnya 4.847 pasal.

| Metode | AUC | Induk benar #1 di seluruh KB | Catatan |
|---|---:|---:|---|
| TF-IDF kata (sebelumnya) | 0,915 | 78,9% | |
| TF-IDF karakter | 0,909 | 76,7% | |
| LSA 300 dimensi (deterministik) | 0,894 | 73,5% | tidak menambah apa pun bila digabung |
| MiniLM (lokal) | 0,894 | 75,5% | |
| e5-large (lokal) | 0,871 | 75,0% | 18 menit untuk 5.438 teks, ±20× lebih lambat |
| **Rata-rata TF-IDF + MiniLM (dipakai)** | **0,922** | **80,3%** | |

**Data uji 2, parafrase** (`tests/fixtures/uji_makna.yaml`). Set ini terdiri atas 15 pasal nyata dari
KB. Tiap pasal diberi tiga varian yang ditulis analis **sebelum** pengukuran: parafrase, pelengkap,
dan kontradiktif. Ini set **sintetis**, bukan label mitra. Gunanya menguji apakah mesin membedakan
ketiga varian ketika redaksinya tidak sama.

| Model | Median kemiripan parafrase / pelengkap / kontradiktif |
|---|---|
| TF-IDF | 0,54 / 0,27 / 0,89 (parafrase tidak terpisah dari pelengkap) |
| MiniLM | 0,95 / 0,73 / 0,98 (parafrase minimum 0,83 vs pelengkap maksimum 0,85) |
| e5-large | 0,99 / 0,96 / 0,99 (skala termampatkan, sulit diberi ambang) |

| Mesin | Benar (dari 45) | Parafrase | Pelengkap | Kontradiktif |
|---|---:|---:|---:|---:|
| `main` sebelum perubahan | 7 | 0 | 0 | 7 |
| **Sesudah** | **29** | **14** | 1 | **14** |

**Data uji 3, anotasi analis atas 40 pasangan lintas dokumen** yang kemiripan maknanya tinggi:
0 tumpang tindih sejati, 5 objek sama tetapi aspek lain, 33 ketentuan templat untuk pihak lain,
2 tidak terkait. Kelima pasangan "objek sama" semuanya berbagi pihak yang diatur. Inilah dasar
gerbang pihak, yang mempertahankan 5 dari 5 dan menyaring 17 dari 33 templat lintas sektor.

## 4. Status relasi (asumsi yang disepakati)

| Hubungan | Dibaca dari | Contoh |
|---|---|---|
| Mengubah | judul "PERUBAHAN … ATAS …" (juga "Beberapa ketentuan dalam … diubah" di Pasal I) | POJK 5/2025 tentang Perubahan atas POJK 12/2021 |
| Mencabut | pasal penutup "… dicabut dan dinyatakan tidak berlaku" | "… POJK 12/2021 … dicabut dan dinyatakan tidak berlaku." |
| Mencabut sebagian | klausa itu menyebut Pasal X, angka/huruf/butir, Bab/Bagian, Lampiran, "ketentuan mengenai …", atau memakai "kecuali …" | "Pasal 15 dan Pasal 16 SEOJK 3/2020 dicabut …"; "… dicabut, kecuali Pasal 4" |
| Rujukan | penyebutan lain di luar pola itu | dasar hukum di Mengingat |

Relasi dicatat dokumen-ke-dokumen. **Status peraturan lama kemudian diturunkan dari relasi itu**,
baik di graf Knowledge Base maupun saat harmonisasi:

- Dicabut penuh berarti `dicabut`.
- Dicabut sebagian berarti `dicabut_sebagian`: hanya pasal yang disebut gugur. Untuk "kecuali …",
  semua gugur selain yang dikecualikan.
- Diubah berarti `diubah`: hanya pasal yang disebut instruksi perubahan gugur.
- Rancangan tidak pernah mencabut apa pun.
- Status register yang lebih kuat tidak pernah diturunkan.
- Status register asli disimpan (`status_register`) beserta buktinya (`status_bukti`) untuk audit.

Aturan konsistensi waktu juga berlaku. Bila peraturan yang tercatat "dicabut" masih *diubah* oleh
peraturan yang lebih baru, pencabutan itu dibaca sebagai sebagian. Contohnya POJK 69/2016 yang
tercatat dicabut oleh POJK 4/2021, padahal masih diubah POJK 36/2024.

Pada KB lokal (172 dokumen), status yang diturunkan:

- Dari 102 dokumen yang tercatat *berlaku*, 99 tetap berlaku. 27 dokumen berstatus *diubah*,
  28 *dicabut*, dan 15 *dicabut sebagian*.
- Ada 26 relasi baru yang dibaca dari teks dan tidak tercatat di JDIH.

## 5. Tradeoff yang disengaja

- **Pelengkap yang redaksinya jauh tidak dikenali (1/15 di set sintetis).** Cabang "topik sama,
  aspek lain" sengaja dibuat ketat (`topik_sama: 0,90`). Pada draft nyata, sinyal makna 0,65–0,86
  hampir selalu berupa klausul templat atau "teman palsu", misalnya *Rencana Pemulihan Bencana* (TI)
  vs *Rencana Aksi Pemulihan* (keuangan bank): 0 dari 6 sampel tepat. Lebih baik melewatkan
  "melengkapi" daripada mengarang hubungan.
- **Ambang 0,62 dipilih lewat Youden J**, bukan dioptimalkan untuk recall. Pada 0,60 recall terarah
  93,8%, tetapi lebih banyak pasal sisipan ikut tertaut.
- **Leksikon pihak adalah draf tim** dan perlu dilengkapi bersama mitra. Pihak yang tak terbaca
  tidak pernah menghukum (gerbang hanya berlaku bila kedua pihak terbaca dan berbeda).
- **Backend belum punya status `dicabut sebagian`.** Ke backend status ini dipetakan ke `diubah`
  (masih berlaku sebagian), dan enum-nya perlu ditambah oleh tim Backend.

## 6. Mengulang angka-angka ini

```bash
hero harmonisasi siapkan-semantik --unduh      # sekali: model lokal + cache embedding korpus
hero harmonisasi evaluasi -n 60                # → docs/HARMONISASI_EVALUASI.md
hero harmonisasi evaluasi -n 60 --seluruh-kb   # → mode seluruh KB
hero graph build                               # status turunan di graf
pytest tests/test_harmonisasi.py tests/test_graph.py
```
