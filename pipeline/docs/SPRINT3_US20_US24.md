# Sprint 3 — US-20a (#12), US-20 (#11), US-24 (#16)

> Ditulis untuk: tim HERO (reviewer kode, Backend, QA) dan Product Owner.
> SPIKE #42 dilaporkan terpisah di [SPIKE_42_PENYIMPANAN.md](SPIKE_42_PENYIMPANAN.md).
> Semua angka di bawah diukur pada katalog lokal (91 dokumen KB, 986 baris JDIH) pada 1 Okt 2026.

## Ringkasan

| Issue | Status | Bukti utama |
|---|---|---|
| **#12 US-20a** OCR halaman 1 + penamaan baku | Selesai, menunggu review | 84,3% dokumen lengkap otomatis; sisanya masuk antrian, tidak ada yang dibuang; templat bebas + `hero penamaan cek` |
| **#11 US-20** metadata dasar | Selesai, menunggu review | judul 95,5% · nomor 89,9% · tanggal 88,8% terisi; yang kurang masuk antrian koreksi |
| **#16 US-24** klasifikasi yang dapat dikonfigurasi | Selesai, menunggu review | Aturan pindah ke `config/kategori.yaml`; akurasi vs label sektor JDIH (belahan uji) **63,9% → 97,1%** tanpa mengubah kode |
| **#42 SPIKE** folder PDF vs vektor | Lihat laporan spike | Diukur di VPS pada korpus OneDrive nyata |

Semua jalan di mode Deterministik: tidak ada panggilan AI di jalur mana pun.
Tes: **348 lulus** (`pytest`), termasuk 35 tes baru di `tests/test_naming.py` dan `tests/test_kategori.py`.

---

## #12 US-20a — Identitas halaman pertama dan nama berkas baku

### Apa yang dibangun

| Bagian | Berkas |
|---|---|
| Pembaca identitas (nomor, tanggal, judul, jenis, tahun) + OCR bila halaman 1 hasil pindai | `hero/extract/firstpage.py` |
| Mesin templat nama berkas (token, filter, validasi, nama aman lintas OS) | `hero/kb/naming.py` |
| Penempatan sebelum masuk KB, antrian koreksi, penyelesaian koreksi, ganti nama massal | `hero/kb/correction.py` |
| Integrasi ke pipeline (sebelum salin ke folder KB) | `hero/pipeline.py` |
| Konfigurasi | `config/sources.yaml` bagian `naming:` |

### Alur

```
PDF masuk ──► baca halaman 1 (lapisan teks; OCR bila hasil pindai)
              ├─ tanggal tidak ada di hal. 1 → cari di blok penutup "Ditetapkan di … pada tanggal …"
              └─ unsur yang masih kosong → isi dari metadata dokumen utuh / sumber (JDIH)
         ──► unsur wajib lengkap?
              ├─ ya    → nama dari templat → folder KB  (status: dinamai)
              └─ tidak → data/antrian_koreksi/<doc_id>.pdf  (status: antrian)
                          petugas melengkapi → nama baku → folder KB  (status: dikoreksi)
```

### Format nama tidak dikunci (Weekly #4)

OJK tidak punya format baku, jadi format adalah templat yang bisa diganti pengguna.
Bawaan: `{jenis} {nomor_urut} Tahun {tahun} tentang {judul:90|title}` →
`POJK 7 Tahun 2025 tentang Laporan Bulanan Perusahaan Pembiayaan.pdf`.

| Token | Isi | Contoh argumen/filter |
|---|---|---|
| `{jenis}` `{nomor}` `{nomor_urut}` `{tahun}` | identitas peraturan | `{nomor}` → `11-POJK.03-2024` (garis miring diganti) |
| `{tanggal}` | tanggal penetapan | `{tanggal:%d-%m-%Y}` |
| `{judul}` | perihal | `{judul:60}` (maks. 60 karakter, dipotong di batas kata) |
| `{kategori}` `{sumber}` `{status}` | konteks KB | — |
| filter | `|lower` `|upper` `|title` `|slug` | `{judul:40|slug}` |

Templat diperiksa sebelum disimpan (token/filter tidak dikenal, kurung tidak berpasangan,
templat tanpa token). Setiap token identitas yang dipakai templat otomatis menjadi unsur wajib —
templat yang memakai `{tahun}` tidak akan menghasilkan "POJK 11 Tahun .pdf".
Rancangan peraturan (`ojk-rancangan`) memakai templat sendiri karena belum punya nomor/tanggal.

Ini adalah dasar untuk #89 (UI penyusun format: `check_template` + pratinjau `apply_template(dry_run=True)`)
dan #90 (ganti nama dinamis: `hero penamaan terapkan --apply`, memakai identitas tersimpan tanpa membaca ulang PDF).

### Temuan untuk mitra: tanggal hampir tidak pernah ada di halaman pertama

Arahan mitra: "Buka halaman pertama… pasti terdiri dari nomor peraturan, tanggal, dan judul."
Diukur pada 89 PDF KB:

| Unsur | Ada di halaman 1 | Terisi setelah blok penutup/metadata |
|---|---:|---:|
| Nomor | 80 (89,9%) | 89,9% |
| Judul | 85 (95,5%) | 95,5% |
| **Tanggal** | **18 (20,2%)** | **88,8%** (61 dari blok penutup) |

Peraturan perundang-undangan menaruh tanggal penetapan di blok penutup (UU 12/2011 Lampiran II),
bukan di halaman judul. Membaca halaman 1 secara harfiah akan mengirim ±80% dokumen ke antrian koreksi.
Setiap unsur menyimpan **sumbernya** (`halaman-1` / `penutup` / `metadata-dokumen` / `koreksi-manual`)
dan **caranya** (`teks` / `ocr`), jadi keputusan ini bisa diaudit. Bila mitra ingin perilaku harfiah:
`naming.fallback_metadata: false`.

**Perlu keputusan PO:** apakah tanggal dari blok penutup boleh dipakai untuk penamaan? Rekomendasi: ya.

### Dampak pada 91 dokumen yang sudah ada (dry-run, belum diterapkan)

`hero penamaan cek`: 78 akan berganti nama, 11 masuk antrian (nomor 7, tanggal 7, judul 2),
2 berkas hilang (PADG 27 & 28/2026 — sudah tercatat sebagai temuan, dapat diunduh ulang dari URL BI dan diverifikasi dengan sha256).
Dokumen lama yang tidak lengkap **tidak dipindah**, hanya ditandai di antrian.

---

## #11 US-20 — Ekstraksi metadata dasar

| Kriteria penerimaan | Bukti |
|---|---|
| Judul, nomor, tanggal terbit terisi otomatis untuk dokumen baku | 84,3% dokumen lengkap ketiganya; per unsur: judul 95,5%, nomor 89,9%, tanggal 88,8% (`hero identitas`) |
| Metadata tidak lengkap masuk antrian koreksi, tidak dibuang | Dokumen tetap di katalog (`status=ingested`, `reason="antrian koreksi: …"`), berkas di `data/antrian_koreksi/`; tes `test_incomplete_document_is_queued_outside_the_kb_not_discarded` |

Antrian koreksi:

```bash
hero koreksi daftar
hero koreksi selesaikan <doc_id> --nomor 3/SEOJK.05/2025 --tanggal 2025-05-21 \
    --judul "Pemberitahuan Laporan" --oleh "NIP-123"
```

`selesaikan` memvalidasi isian (tanggal YYYY-MM-DD, tahun wajar), menolak bila masih ada unsur
kosong, lalu memberi nama baku, memindahkan berkas ke folder KB, memperbarui katalog, dan mencatat
siapa yang mengoreksi (`penamaan.dikoreksi_oleh`).

Penyebab dokumen masuk antrian (11 dokumen lama): rancangan dengan "pada tanggal …" (kini punya
templat sendiri), salinan tanpa halaman judul, PDF 1 halaman berupa ringkasan, dan nama berkas UUID
dari OneDrive tanpa identitas apa pun. Terjemahan Inggris BI/OJK ("Enacted in Jakarta on …") kini dikenali.

---

## #16 US-24 — Klasifikasi kategori yang dapat dikonfigurasi

### Apa yang berubah

* Aturan pindah dari kode (`CATEGORY_RULES`) ke **`config/kategori.yaml`**. Kode hanya membaca
  dan memvalidasi; berkas dibaca ulang otomatis saat berubah (cek `mtime`), tanpa restart.
* Berkas rusak gagal keras dengan pesan yang menunjuk barisnya (kode ganda, kata kunci kosong, dll.);
  berkas tidak ada → aturan bawaan.
* Jenis aturan: `kata_kunci` (di perihal bobot 5, di isi bobot 1, maks 3 per kata),
  `kecuali`, `kode_nomor` (kode satker di nomor lama, dengan `sejak`/`sampai` tahun),
  `sektor_jdih` (pemetaan ke label JDIH untuk pengukuran).
* Pencocokan per kata (`cocok: kata`): "efek" tidak lagi cocok dengan "efektivitas".

### Bug yang ditemukan dan diperbaiki

Aturan lama mencocokkan **nama penerbit**: "Peraturan Anggota Dewan Komisioner **Otoritas Jasa
Keuangan** … tentang Laporan Bulanan Perusahaan Pembiayaan" masuk `kelembagaan` karena
"otoritas jasa keuangan" dan "dewan komisioner" adalah kata kunci kelembagaan — dan keduanya ada
di judul hampir semua peraturan OJK. Kini hanya **perihal** (bagian setelah "tentang") yang dinilai.

### Pengukuran

Label sektor JDIH OJK (986 peraturan) dipakai sebagai kunci jawaban. Aturan disetel hanya dengan
melihat galat belahan *latih*; angka yang dilaporkan dari belahan *uji* (476 dokumen).

| Aturan | Akurasi uji | Nomor dengan kode satker (416) | Nomor tanpa kode (60) |
|---|---:|---:|---:|
| Bawaan lama (substring, judul utuh) | 63,9% | 64,7% | 58,3% |
| YAML v3 tanpa `kode_nomor` | 82,1% | 82,0% | 83,3% |
| **YAML v3 lengkap** | **97,1%** | 99,0% | 83,3% |

Kejujuran soal angka: kode satker di nomor (`.03` perbankan, `.04` pasar modal, `.05` IKNB, …)
dekat dengan cara JDIH memberi sektor, jadi angka 99% sebagian melingkar. Angka yang mencerminkan
kekuatan kata kunci adalah **83,3%** pada nomor model baru ("Nomor 7 Tahun 2026") yang tidak punya kode.
Sisa galat sebagian besar perbedaan taksonomi: HERO punya kategori topik (APU-PPT, tata kelola) yang di
JDIH masuk sektor.

Pada 91 dokumen KB, aturan baru mengubah kategori 17 dokumen (dry-run; belum diterapkan) — mis. aset
kripto → teknologi-informasi, piutang PT SMI → iknb, terjemahan Inggris BI keluar dari `lain-lain`.

**Perlu keputusan PO:** saat skor seri, sektor (perbankan/pasar modal/IKNB) didahulukan dari topik
lintas-sektor (TI), sehingga "Keamanan Siber bagi Bank Umum" → perbankan (sama dengan JDIH). Untuk
DPEA yang fokus TI mungkin sebaliknya — cukup pindahkan blok `teknologi-informasi` ke atas di YAML.

```bash
hero kategori cek --belahan uji     # validasi + akurasi vs JDIH
hero kategori uji "…judul peraturan…"
```

---

## Definition of Done

| Butir DoD | #12 | #11 | #16 |
|---|---|---|---|
| Kriteria penerimaan terpenuhi & terverifikasi | ✅ (dengan temuan tanggal) | ✅ | ✅ |
| Kode direview anggota lain | ⏳ menunggu | ⏳ | ⏳ |
| Tes fungsional lulus | ✅ 348 | ✅ | ✅ |
| Jalan di mode Deterministik tanpa AI | ✅ | ✅ | ✅ |
| Terintegrasi di staging | ⏳ kode sudah di VPS (`~/hero-work`), belum di layanan staging | ⏳ | ⏳ |
| Dokumentasi diperbarui | ✅ ini, `belajar.md` Bagian 12, `README.md` | ✅ | ✅ |

Catatan untuk repo tim: `hero-team/backend` adalah salinan lama basis kode ini; perubahan di atas
belum dipindahkan ke sana.
