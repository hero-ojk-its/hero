# Evaluasi Harmonisasi — pasangan peraturan perubahan ↔ induk

*Dihasilkan `hero harmonisasi evaluasi` pada 2026-11-23T12:44:35. Label diambil dari instruksi perubahan di teks peraturan itu sendiri ("Ketentuan Pasal N diubah", "disisipkan … Pasal NA"), bukan anotasi manual.*

## Hasil

| Ukuran | Nilai |
|---|---:|
| Mode pembanding | `terarah` |
| Pasangan dievaluasi | 45 |
| Induk ditemukan lewat kata kunci relasi | 45 / 45 |
| Waktu per draft (median / maks) | 0.04 / 0.55 detik |
| Induk menjadi kandidat #1 | 45 / 45 |
| Induk masuk 5 kandidat teratas | 45 / 45 |
| Pasal diubah (berpadanan di induk) | 451 |
| … dipasangkan ke pasal induk yang benar | 446 |
| **Recall deteksi** (padanan benar + dilabel objek yang sudah diatur) | **91.8%** (target FR-HRM-12: ≥ 70%) |
| Pasal disisipkan | 179 |
| … tidak dipasangkan ke induk | 158 |

## Kalibrasi ambang `objek_sama` (TD-07)

Kemiripan TF-IDF pasal baru ↔ pasal induk bernomor sama (positif) dibandingkan kemiripan tertinggi pasal sisipan ↔ pasal mana pun di induk (negatif).

| | Nilai |
|---|---:|
| Median positif / P10 positif | 0.82 / 0.421 |
| Median negatif / P90 negatif | 0.183 / 0.486 |
| AUC | 0.925 |
| Ambang yang disarankan (Youden J) | **0.46** (TPR 0.887, FPR 0.106) |
| Ambang yang dipakai saat ini | 0.45 |

Pengaruh ambang (pasal unik): *recall* = pasal diubah yang dipasangkan ke pasal induk yang benar dan tidak dilabel `pasal_baru`; *sisipan tertaut* = pasal sisipan yang keliru dipasangkan ke induk.

| Ambang | Recall | Sisipan tertaut ke induk |
|---:|---:|---:|
| 0.25 | 95.2% | 34.6% |
| 0.30 | 93.3% | 27.9% |
| 0.35 | 92.6% | 20.7% |
| 0.40 | 91.5% | 15.6% |
| 0.45 | 90.0% | 11.7% |
| 0.50 | 88.0% | 10.1% |
| 0.55 | 85.0% | 8.4% |

## Simulasi ambang tampil / kutip (ISU-06, Weekly #10)

Pada jendela ±0,05 di sekitar tiap kemiripan: *presisi ketat* = porsi pasal terdekat yang tepat pasal induk bernomor sama (batas bawah); *presisi relevan* = ketat + pasal terdekat yang redaksinya ≥ 80% sama dengan pasal draft atau pasal induknya (pasal kembar di peraturan saudara) — "pasal serupa" yang memang layak dikutip.

Ambang tampil (presisi relevan ≥ 75%): **0.5** · ambang kutip (≥ 50%): **0.45** · versi ketat: {'tampil_75': 0.5, 'kutip_50': 0.45} · 446 tepat, 449 relevan dari 639 pasal.

| Kemiripan | n jendela | Presisi ketat | Presisi relevan | n ≥ kemiripan | Presisi kumulatif | Pasal benar tercakup |
|---:|---:|---:|---:|---:|---:|---:|
| 0.15 | 86 | 5% | 5% | 583 | 76% | 100% |
| 0.20 | 76 | 9% | 9% | 537 | 82% | 99% |
| 0.25 | 52 | 25% | 25% | 507 | 86% | 98% |
| 0.30 | 38 | 32% | 32% | 485 | 88% | 96% |
| 0.35 | 31 | 26% | 26% | 469 | 91% | 96% |
| 0.40 | 31 | 39% | 39% | 454 | 93% | 94% |
| 0.45 | 28 | 57% | 57% | 438 | 94% | 93% |
| 0.50 | 29 | 79% | 79% | 426 | 95% | 91% |
| 0.55 | 40 | 85% | 85% | 409 | 96% | 88% |
| 0.60 | 42 | 83% | 83% | 386 | 96% | 83% |
| 0.65 | 50 | 84% | 84% | 367 | 97% | 80% |
| 0.70 | 67 | 91% | 91% | 336 | 98% | 74% |
| 0.75 | 78 | 95% | 95% | 300 | 98% | 66% |
| 0.80 | 99 | 96% | 98% | 258 | 99% | 57% |
| 0.85 | 105 | 98% | 100% | 201 | 100% | 45% |
| 0.90 | 144 | 99% | 100% | 153 | 99% | 34% |
| 0.95 | 146 | 99% | 100% | 57 | 100% | 13% |

## Per pasangan

| Perubahan | Peringkat induk | Diubah | Padanan benar | Terdeteksi | Disisipkan | Label |
|---|---:|---:|---:|---:|---:|---|
| POJK 10 2026 | 1 | 6 | 6 | 5 | 3 | memperjelas 3, menggantikan 2, pasal_baru 4 |
| POJK 10 2025 | 1 | 9 | 9 | 9 | 10 | memperjelas 5, menggantikan 6, pasal_baru 8 |
| POJK 23 2025 | 1 | 42 | 40 | 40 | 10 | memperjelas 19, menggantikan 23, pasal_baru 11 |
| POJK 25 2025 | 1 | 1 | 1 | 1 | 0 | memperjelas 1 |
| POJK 29 2025 | 1 | 23 | 23 | 22 | 12 | memperjelas 6, menggantikan 17, pasal_baru 12 |
| POJK 35 2025 | 1 | 36 | 36 | 36 | 4 | memperjelas 20, menggantikan 18, pasal_baru 2 |
| POJK 11 2024 | 1 | 9 | 9 | 8 | 1 | memperjelas 5, menggantikan 3, pasal_baru 2 |
| POJK 19 2024 | 1 | 9 | 9 | 7 | 1 | memperjelas 6, menggantikan 1, pasal_baru 3 |
| POJK 20 2024 | 1 | 3 | 3 | 2 | 1 | menggantikan 2, pasal_baru 2 |
| POJK 36 2024 | 1 | 20 | 20 | 18 | 17 | memperjelas 12, menggantikan 7, pasal_baru 18 |
| POJK 38 2024 | 1 | 25 | 25 | 24 | 14 | duplikasi 1, memperjelas 15, menggantikan 14, pasal_baru 9 |
| POJK 1 2023 | 1 | 10 | 10 | 8 | 2 | memperjelas 2, menggantikan 6, pasal_baru 4 |
| POJK 2 2023 | 1 | 10 | 10 | 9 | 2 | duplikasi 2, memperjelas 2, menggantikan 5, pasal_baru 3 |
| POJK 4 2023 | 1 | 10 | 10 | 8 | 11 | memperjelas 6, menggantikan 2, pasal_baru 14 |
| POJK 5 2023 | 1 | 22 | 22 | 18 | 8 | memperjelas 8, menggantikan 10, pasal_baru 13 |
| POJK 6 2023 | 1 | 22 | 22 | 20 | 8 | duplikasi 1, memperjelas 9, menggantikan 10, pasal_baru 11 |
| POJK 12 2022 | 1 | 17 | 17 | 15 | 3 | memperjelas 4, menggantikan 11, pasal_baru 5 |
| POJK 28 2022 | 1 | 17 | 17 | 16 | 13 | memperjelas 13, menggantikan 4, pasal_baru 13 |
| POJK 4 2022 | 1 | 1 | 1 | 1 | 1 | memperjelas 1, pasal_baru 1 |
| POJK 7 2022 | 1 | 1 | 1 | 1 | 1 | menggantikan 1, pasal_baru 1 |
| POJK 14 2021 | 1 | 6 | 6 | 6 | 1 | duplikasi 1, memperjelas 5, pasal_baru 1 |
| POJK 16 2021 | 1 | 2 | 2 | 2 | 1 | menggantikan 2, pasal_baru 1 |
| POJK 17 2021 | 1 | 1 | 1 | 1 | 0 | memperjelas 1, pasal_baru 1 |
| POJK 18 2021 | 1 | 1 | 1 | 1 | 0 | menggantikan 1 |
| POJK 2 2021 | 1 | 2 | 2 | 2 | 0 | menggantikan 2, pasal_baru 2 |
| POJK 27 2021 | 1 | 9 | 8 | 8 | 11 | memperjelas 5, menggantikan 5, pasal_baru 10 |
| POJK 30 2021 | 1 | 4 | 4 | 4 | 0 | memperjelas 2, menggantikan 2, pasal_baru 4 |
| POJK 29 2020 | 1 | 9 | 8 | 7 | 7 | memperjelas 3, menggantikan 6, pasal_baru 8 |
| POJK 30 2020 | 1 | 6 | 6 | 3 | 0 | menggantikan 3, pasal_baru 3 |
| POJK 13 2020 | 1 | 1 | 1 | 1 | 1 | memperjelas 1, pasal_baru 2 |
| POJK 2 2020 | 1 | 2 | 2 | 2 | 0 | memperjelas 1, menggantikan 1 |
| POJK 36 2020 | 1 | 1 | 1 | 1 | 0 | memperjelas 1 |
| POJK 38 2020 | 1 | 1 | 1 | 1 | 1 | memperjelas 1, pasal_baru 1 |
| POJK 39 2020 | 1 | 13 | 13 | 13 | 1 | memperjelas 3, menggantikan 10, pasal_baru 1 |
| POJK 58 2020 | 1 | 8 | 8 | 8 | 1 | memperjelas 5, menggantikan 3, pasal_baru 7 |
| POJK 60 2020 | 1 | 31 | 31 | 28 | 5 | duplikasi 1, memperjelas 15, menggantikan 13, pasal_baru 7 |
| POJK 64 2020 | 1 | 18 | 18 | 17 | 6 | memperjelas 9, menggantikan 8, pasal_baru 7 |
| POJK 48 2020 | 1 | 6 | 6 | 6 | 5 | memperjelas 4, menggantikan 2, pasal_baru 5 |
| POJK 14 2019 | 1 | 5 | 5 | 5 | 11 | memperjelas 5, menggantikan 5, pasal_baru 6 |
| POJK 19 2019 | 1 | 1 | 1 | 0 | 0 | pasal_baru 1 |
| POJK 23 2019 | 1 | 16 | 16 | 16 | 0 | duplikasi 1, memperjelas 10, menggantikan 6 |
| POJK 32 2019 | 1 | 4 | 4 | 4 | 0 | memperjelas 2, menggantikan 2 |
| POJK 38 2019 | 1 | 5 | 5 | 5 | 5 | memperjelas 1, menggantikan 5, pasal_baru 5 |
| POJK 43 2019 | 1 | 2 | 1 | 1 | 0 | menggantikan 1, pasal_baru 1 |
| POJK 44 2019 | 1 | 4 | 4 | 4 | 1 | memperjelas 3, menggantikan 1, pasal_baru 1 |

Dilewati: POJK|27|2022 → POJK|11|2016: belum di KB

## Batas evaluasi ini

- Peraturan perubahan hanya bisa menguji *objek sama vs baru* dan *menggantikan*. `konflik` (dua aturan berbeda yang sama-sama berlaku) tidak pernah muncul di dalamnya; contohnya perlu dilabel DPEA lewat validasi sampling (FR-HRM-11/12).
- Pasal diubah yang redaksinya hampir tidak berubah menaikkan angka positif; pasal yang ditulis ulang total menurunkannya. Keduanya nyata terjadi dan sengaja tidak disaring.
