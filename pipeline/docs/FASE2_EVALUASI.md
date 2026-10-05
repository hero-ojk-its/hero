# Evaluasi Fase 2 — Analisa, Summary, Key Takeaways

*Dihasilkan oleh `hero fase2` pada 02 October 2026 20:04 atas 118 dokumen. Semua angka diukur ulang setiap kali perintah dijalankan.*

## v1 (ekstraktif) vs v2 (terstruktur berbasis pasal)

| Metrik | v1 | v2 | Arah yang baik |
|---|---:|---:|---|
| Poin kunci berujukan pasal | 86.7% | **99.7%** | naik |
| Poin kunci terlacak ke teks pasalnya | 86.4% | **98.3%** | naik |
| Poin kunci terpotong di awal daftar | 12.6% | **2.8%** | turun |
| Definisi terbaca sebagai kewajiban/larangan | 2.2% | **0.1%** | turun |
| Cakupan pasal normatif | 23.9% | **98.3%** | naik |
| Dokumen tanpa poin kunci | 6 | **4** | turun |
| Median kata ringkasan | 318.5 | **152.5** | turun |
| Ringkasan dengan penanda ayat lepas | 73.7% | **4.2%** | turun |
| Kalimat ringkasan bercitasi pasal | 0.0% | **66.1%** | naik |

Waktu analisa v2: total 0.7 s untuk 118 dokumen · median 2.25 ms · maks 54.37 ms per dokumen.
Dokumen yang substansinya di Lampiran (ditandai eksplisit): 7.

## Indikator Fase 2 (URD bagian 5)

| Indikator | Aktual | Target | Status |
|---|---|---|:---:|
| Summary & Key Takeaways untuk ≥10 dokumen uji | 114 | 10 | ✅ |
| Waktu proses per dokumen < 5 menit (Deterministik) | 11.5 s (terburuk: ekstraksi 11.4 s + analisa v2) | 300 s | ✅ |
| Mode AI-Assisted dapat diaktifkan/nonaktifkan | tersedia, dinonaktifkan di konfigurasi (analysis.ai_enabled: false) | toggle berfungsi, narasi lebih natural | ⏳ |

**Cara hitung:**

- *Summary & Key Takeaways untuk ≥10 dokumen uji* — dokumen ingested dengan ≥1 poin kunci v2 dan ringkasan terstruktur
- *Waktu proses per dokumen < 5 menit (Deterministik)* — maks detik ekstraksi PDF tersimpan + maks waktu analisa v2
- *Mode AI-Assisted dapat diaktifkan/nonaktifkan* — konfigurasi analysis.ai_enabled + panggilan nyata ke model berhasil dan lolos verifikasi

## Batas evaluasi ini

- Metrik di atas memeriksa sifat yang bisa diuji mesin (rujukan, keterlacakan, cakupan, kebisingan). Ringkasan yang lolos semuanya tetap bisa melewatkan hal penting.
- Belum ada ringkasan acuan buatan manusia. Templat telaah ahli ada di `data/export/fase2_telaah_ahli.csv`; hasil telaah itu menjadi set evaluasi berlabel pertama.
