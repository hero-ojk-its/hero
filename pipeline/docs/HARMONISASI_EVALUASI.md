# Evaluasi Harmonisasi — pasangan peraturan perubahan ↔ induk

*Dihasilkan `hero harmonisasi evaluasi` pada 2026-11-24T10:56:20. Label diambil dari instruksi perubahan di teks peraturan itu sendiri ("Ketentuan Pasal N diubah", "disisipkan … Pasal NA"), bukan anotasi manual.*

## Hasil

| Ukuran | Nilai |
|---|---:|
| Mode pembanding | `terarah` |
| Pasangan dievaluasi | 45 |
| Induk ditemukan lewat kata kunci relasi | 45 / 45 |
| Waktu per draft (median / maks) | 0.05 / 1.12 detik |
| Induk menjadi kandidat #1 | 45 / 45 |
| Induk masuk 5 kandidat teratas | 45 / 45 |
| Pasal diubah (berpadanan di induk) | 451 |
| … dipasangkan ke pasal induk yang benar | 442 |
| **Recall deteksi** (padanan benar + dilabel objek yang sudah diatur) | **92.9%** (target FR-HRM-12: ≥ 70%) |
| Pasal disisipkan | 179 |
| … tidak dipasangkan ke induk | 179 |

## Kalibrasi ambang `objek_sama` (TD-07)

Kemiripan (leksikal + makna) pasal baru ↔ pasal induk bernomor sama (positif) dibandingkan kemiripan tertinggi pasal sisipan ↔ pasal mana pun di induk (negatif).

| | Nilai |
|---|---:|
| Median positif / P10 positif | 0.894 / 0.628 |
| Median negatif / P90 negatif | 0.456 / 0.661 |
| AUC | 0.931 |
| Ambang yang disarankan (Youden J) | **0.62** (TPR 0.907, FPR 0.123) |
| Metode kemiripan | leksikal + makna |
| Ambang yang dipakai saat ini | 0.62 |

Pengaruh ambang (pasal unik): *recall* = pasal diubah yang dipasangkan ke pasal induk yang benar dan tidak dilabel `pasal_baru`; *sisipan tertaut* = pasal sisipan yang keliru dipasangkan ke induk.

| Ambang | Recall | Sisipan tertaut ke induk |
|---:|---:|---:|
| 0.25 | 96.1% | 99.4% |
| 0.30 | 96.1% | 98.9% |
| 0.35 | 96.1% | 91.6% |
| 0.40 | 95.9% | 74.9% |
| 0.45 | 95.2% | 53.6% |
| 0.50 | 94.8% | 31.3% |
| 0.55 | 93.5% | 21.2% |

## Simulasi ambang tampil / kutip (ISU-06, Weekly #10)

Pada jendela ±0,05 di sekitar tiap kemiripan: *presisi ketat* = porsi pasal terdekat yang tepat pasal induk bernomor sama (batas bawah); *presisi relevan* = ketat + pasal terdekat yang redaksinya ≥ 80% sama dengan pasal draft atau pasal induknya (pasal kembar di peraturan saudara) — "pasal serupa" yang memang layak dikutip.

Ambang tampil (presisi relevan ≥ 75%): **0.7** · ambang kutip (≥ 50%): **0.6** · versi ketat: {'tampil_75': 0.7, 'kutip_50': 0.6} · 442 tepat, 445 relevan dari 639 pasal.

| Kemiripan | n jendela | Presisi ketat | Presisi relevan | n ≥ kemiripan | Presisi kumulatif | Pasal benar tercakup |
|---:|---:|---:|---:|---:|---:|---:|
| 0.15 | 0 | — | — | 639 | 69% | 100% |
| 0.20 | 1 | — | — | 639 | 69% | 100% |
| 0.25 | 3 | — | — | 638 | 69% | 100% |
| 0.30 | 15 | 0% | 0% | 636 | 70% | 100% |
| 0.35 | 45 | 2% | 2% | 623 | 71% | 100% |
| 0.40 | 76 | 5% | 5% | 591 | 75% | 100% |
| 0.45 | 89 | 6% | 6% | 547 | 80% | 99% |
| 0.50 | 74 | 11% | 11% | 502 | 87% | 99% |
| 0.55 | 48 | 27% | 27% | 473 | 91% | 97% |
| 0.60 | 43 | 56% | 56% | 454 | 93% | 96% |
| 0.65 | 36 | 69% | 69% | 430 | 94% | 92% |
| 0.70 | 38 | 76% | 76% | 418 | 95% | 90% |
| 0.75 | 61 | 82% | 84% | 392 | 96% | 85% |
| 0.80 | 93 | 87% | 88% | 357 | 98% | 79% |
| 0.85 | 135 | 94% | 95% | 299 | 99% | 67% |
| 0.90 | 176 | 99% | 99% | 222 | 100% | 50% |
| 0.95 | 220 | 100% | 100% | 123 | 99% | 28% |

## Per pasangan

| Perubahan | Peringkat induk | Diubah | Padanan benar | Terdeteksi | Disisipkan | Label |
|---|---:|---:|---:|---:|---:|---|
| POJK 10 2026 | 1 | 6 | 6 | 6 | 3 | menggantikan 6, pasal_baru 3 |
| POJK 10 2025 | 1 | 9 | 9 | 9 | 10 | menggantikan 9, pasal_baru 10 |
| POJK 23 2025 | 1 | 42 | 39 | 39 | 10 | menggantikan 42, pasal_baru 11 |
| POJK 25 2025 | 1 | 1 | 1 | 1 | 0 | menggantikan 1 |
| POJK 29 2025 | 1 | 23 | 23 | 23 | 12 | menggantikan 23, pasal_baru 12 |
| POJK 35 2025 | 1 | 36 | 36 | 36 | 4 | menggantikan 36, pasal_baru 4 |
| POJK 11 2024 | 1 | 9 | 9 | 8 | 1 | menggantikan 8, pasal_baru 2 |
| POJK 19 2024 | 1 | 9 | 9 | 7 | 1 | menggantikan 7, pasal_baru 3 |
| POJK 20 2024 | 1 | 3 | 3 | 2 | 1 | menggantikan 2, pasal_baru 2 |
| POJK 36 2024 | 1 | 20 | 20 | 19 | 17 | menggantikan 19, pasal_baru 18 |
| POJK 38 2024 | 1 | 25 | 25 | 25 | 14 | duplikasi 1, menggantikan 24, pasal_baru 14 |
| POJK 1 2023 | 1 | 10 | 10 | 9 | 2 | menggantikan 9, pasal_baru 3 |
| POJK 2 2023 | 1 | 10 | 10 | 9 | 2 | duplikasi 2, menggantikan 7, pasal_baru 3 |
| POJK 4 2023 | 1 | 10 | 10 | 7 | 11 | menggantikan 7, pasal_baru 15 |
| POJK 5 2023 | 1 | 22 | 21 | 18 | 8 | menggantikan 18, pasal_baru 13 |
| POJK 6 2023 | 1 | 22 | 22 | 20 | 8 | duplikasi 1, menggantikan 19, pasal_baru 11 |
| POJK 12 2022 | 1 | 17 | 17 | 15 | 3 | menggantikan 15, pasal_baru 5 |
| POJK 28 2022 | 1 | 17 | 16 | 16 | 13 | menggantikan 16, pasal_baru 14 |
| POJK 4 2022 | 1 | 1 | 1 | 1 | 1 | menggantikan 1, pasal_baru 1 |
| POJK 7 2022 | 1 | 1 | 1 | 1 | 1 | menggantikan 1, pasal_baru 1 |
| POJK 14 2021 | 1 | 6 | 6 | 6 | 1 | duplikasi 1, menggantikan 5, pasal_baru 1 |
| POJK 16 2021 | 1 | 2 | 2 | 2 | 1 | menggantikan 2, pasal_baru 1 |
| POJK 17 2021 | 1 | 1 | 1 | 1 | 0 | menggantikan 1, pasal_baru 1 |
| POJK 18 2021 | 1 | 1 | 1 | 1 | 0 | menggantikan 1 |
| POJK 2 2021 | 1 | 2 | 2 | 2 | 0 | menggantikan 2, pasal_baru 2 |
| POJK 27 2021 | 1 | 9 | 9 | 8 | 11 | menggantikan 8, pasal_baru 12 |
| POJK 30 2021 | 1 | 4 | 4 | 4 | 0 | menggantikan 4, pasal_baru 4 |
| POJK 29 2020 | 1 | 9 | 8 | 7 | 7 | menggantikan 9, pasal_baru 8 |
| POJK 30 2020 | 1 | 6 | 4 | 4 | 0 | menggantikan 4, pasal_baru 2 |
| POJK 13 2020 | 1 | 1 | 1 | 1 | 1 | menggantikan 2, pasal_baru 1 |
| POJK 2 2020 | 1 | 2 | 2 | 2 | 0 | menggantikan 2 |
| POJK 36 2020 | 1 | 1 | 1 | 1 | 0 | menggantikan 1 |
| POJK 38 2020 | 1 | 1 | 1 | 1 | 1 | menggantikan 1, pasal_baru 1 |
| POJK 39 2020 | 1 | 13 | 13 | 13 | 1 | menggantikan 13, pasal_baru 1 |
| POJK 58 2020 | 1 | 8 | 8 | 8 | 1 | menggantikan 8, pasal_baru 7 |
| POJK 60 2020 | 1 | 31 | 31 | 29 | 5 | duplikasi 1, menggantikan 28, pasal_baru 7 |
| POJK 64 2020 | 1 | 18 | 18 | 18 | 6 | menggantikan 18, pasal_baru 6 |
| POJK 48 2020 | 1 | 6 | 6 | 5 | 5 | menggantikan 5, pasal_baru 6 |
| POJK 14 2019 | 1 | 5 | 5 | 5 | 11 | menggantikan 5, pasal_baru 11 |
| POJK 19 2019 | 1 | 1 | 1 | 0 | 0 | pasal_baru 1 |
| POJK 23 2019 | 1 | 16 | 16 | 16 | 0 | duplikasi 1, menggantikan 16 |
| POJK 32 2019 | 1 | 4 | 4 | 4 | 0 | menggantikan 4 |
| POJK 38 2019 | 1 | 5 | 5 | 5 | 5 | menggantikan 6, pasal_baru 5 |
| POJK 43 2019 | 1 | 2 | 1 | 1 | 0 | menggantikan 1, pasal_baru 1 |
| POJK 44 2019 | 1 | 4 | 4 | 4 | 1 | menggantikan 4, pasal_baru 1 |

Dilewati: POJK|27|2022 → POJK|11|2016: belum di KB

## Batas evaluasi ini

- Peraturan perubahan hanya bisa menguji *objek sama vs baru* dan *menggantikan*. `konflik` (dua aturan berbeda yang sama-sama berlaku) tidak pernah muncul di dalamnya; contohnya perlu dilabel DPEA lewat validasi sampling (FR-HRM-11/12).
- Pasal diubah yang redaksinya hampir tidak berubah menaikkan angka positif; pasal yang ditulis ulang total menurunkannya. Keduanya nyata terjadi dan sengaja tidak disaring.
