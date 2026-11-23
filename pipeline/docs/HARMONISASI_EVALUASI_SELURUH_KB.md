# Evaluasi Harmonisasi — pasangan peraturan perubahan ↔ induk

*Dihasilkan `hero harmonisasi evaluasi` pada 2026-11-23T12:45:37. Label diambil dari instruksi perubahan di teks peraturan itu sendiri ("Ketentuan Pasal N diubah", "disisipkan … Pasal NA"), bukan anotasi manual.*

## Hasil

| Ukuran | Nilai |
|---|---:|
| Mode pembanding | `seluruh_kb` |
| Pasangan dievaluasi | 45 |
| Induk ditemukan lewat kata kunci relasi | 0 / 45 |
| Waktu per draft (median / maks) | 0.73 / 1.12 detik |
| Induk menjadi kandidat #1 | 38 / 45 |
| Induk masuk 5 kandidat teratas | 40 / 45 |
| Pasal diubah (berpadanan di induk) | 412 |
| … dipasangkan ke pasal induk yang benar | 343 |
| **Recall deteksi** (padanan benar + dilabel objek yang sudah diatur) | **80.1%** (target FR-HRM-12: ≥ 70%) |
| Pasal disisipkan | 172 |
| … tidak dipasangkan ke induk | 151 |

## Kalibrasi ambang `objek_sama` (TD-07)

Kemiripan TF-IDF pasal baru ↔ pasal induk bernomor sama (positif) dibandingkan kemiripan tertinggi pasal sisipan ↔ pasal mana pun di induk (negatif).

| | Nilai |
|---|---:|
| Median positif / P10 positif | 0.821 / 0.425 |
| Median negatif / P90 negatif | 0.232 / 0.512 |
| AUC | 0.92 |
| Ambang yang disarankan (Youden J) | **0.48** (TPR 0.883, FPR 0.116) |
| Ambang yang dipakai saat ini | 0.45 |

Pengaruh ambang (pasal unik): *recall* = pasal diubah yang dipasangkan ke pasal induk yang benar dan tidak dilabel `pasal_baru`; *sisipan tertaut* = pasal sisipan yang keliru dipasangkan ke induk.

| Ambang | Recall | Sisipan tertaut ke induk |
|---:|---:|---:|
| 0.25 | 81.7% | 36.6% |
| 0.30 | 80.7% | 28.5% |
| 0.35 | 80.2% | 22.7% |
| 0.40 | 79.8% | 15.1% |
| 0.45 | 78.6% | 12.2% |
| 0.50 | 76.9% | 10.5% |
| 0.55 | 75.7% | 7.6% |

## Simulasi ambang tampil / kutip (ISU-06, Weekly #10)

Pada jendela ±0,05 di sekitar tiap kemiripan: *presisi ketat* = porsi pasal terdekat yang tepat pasal induk bernomor sama (batas bawah); *presisi relevan* = ketat + pasal terdekat yang redaksinya ≥ 80% sama dengan pasal draft atau pasal induknya (pasal kembar di peraturan saudara) — "pasal serupa" yang memang layak dikutip.

Ambang tampil (presisi relevan ≥ 75%): **0.8** · ambang kutip (≥ 50%): **0.55** · versi ketat: {'tampil_75': 0.9, 'kutip_50': 0.6} · 343 tepat, 415 relevan dari 592 pasal.

| Kemiripan | n jendela | Presisi ketat | Presisi relevan | n ≥ kemiripan | Presisi kumulatif | Pasal benar tercakup |
|---:|---:|---:|---:|---:|---:|---:|
| 0.15 | 22 | 0% | 0% | 584 | 59% | 100% |
| 0.20 | 33 | 0% | 0% | 570 | 60% | 100% |
| 0.25 | 48 | 8% | 8% | 551 | 62% | 100% |
| 0.30 | 48 | 12% | 12% | 522 | 65% | 99% |
| 0.35 | 40 | 10% | 10% | 503 | 67% | 98% |
| 0.40 | 33 | 21% | 21% | 482 | 70% | 98% |
| 0.45 | 26 | 46% | 46% | 470 | 70% | 96% |
| 0.50 | 33 | 36% | 36% | 456 | 71% | 94% |
| 0.55 | 36 | 47% | 53% | 437 | 73% | 93% |
| 0.60 | 39 | 59% | 67% | 420 | 73% | 89% |
| 0.65 | 46 | 61% | 63% | 398 | 74% | 86% |
| 0.70 | 50 | 66% | 72% | 374 | 74% | 81% |
| 0.75 | 86 | 65% | 74% | 348 | 75% | 76% |
| 0.80 | 119 | 66% | 84% | 288 | 77% | 65% |
| 0.85 | 114 | 71% | 96% | 229 | 80% | 54% |
| 0.90 | 157 | 85% | 100% | 174 | 81% | 41% |
| 0.95 | 160 | 84% | 100% | 72 | 71% | 15% |

## Per pasangan

| Perubahan | Peringkat induk | Diubah | Padanan benar | Terdeteksi | Disisipkan | Label |
|---|---:|---:|---:|---:|---:|---|
| POJK 10 2026 | 1 | 6 | 6 | 6 | 3 | duplikasi 1, memperjelas 4, menggantikan 3, pasal_baru 1 |
| POJK 10 2025 | 1 | 9 | 9 | 9 | 10 | duplikasi 1, memperjelas 5, menggantikan 7, pasal_baru 6 |
| POJK 23 2025 | 1 | 42 | 39 | 39 | 10 | memperjelas 19, menggantikan 23, pasal_baru 11 |
| POJK 25 2025 | 1 | 1 | 1 | 1 | 0 | memperjelas 1 |
| POJK 29 2025 | 1 | 23 | 21 | 19 | 12 | memperjelas 6, menggantikan 17, pasal_baru 12 |
| POJK 35 2025 | 1 | 36 | 36 | 36 | 4 | memperjelas 20, menggantikan 20 |
| POJK 11 2024 | 1 | 9 | 3 | 3 | 1 | duplikasi 3, memperjelas 4, menggantikan 2, pasal_baru 1 |
| POJK 19 2024 | 1 | 9 | 7 | 7 | 1 | memperjelas 7, menggantikan 2, pasal_baru 1 |
| POJK 20 2024 | 1 | 3 | 2 | 2 | 1 | memperjelas 1, menggantikan 3 |
| POJK 36 2024 | 1 | 20 | 20 | 18 | 17 | konflik 1, memperjelas 17, menggantikan 10, pasal_baru 9 |
| POJK 38 2024 | 1 | 25 | 22 | 21 | 14 | duplikasi 1, memperjelas 16, menggantikan 15, pasal_baru 7 |
| POJK 1 2023 | 1 | 10 | 8 | 8 | 2 | konflik 1, memperjelas 2, menggantikan 7, pasal_baru 2 |
| POJK 2 2023 | 1 | 10 | 9 | 8 | 2 | duplikasi 2, memperjelas 3, menggantikan 4, pasal_baru 3 |
| POJK 4 2023 | 1 | 10 | 9 | 7 | 11 | memperjelas 6, menggantikan 3, pasal_baru 13 |
| POJK 5 2023 | 1 | 22 | 9 | 9 | 8 | duplikasi 7, konflik 1, memperjelas 6, menggantikan 17 |
| POJK 6 2023 | 1 | 22 | 10 | 10 | 8 | duplikasi 8, konflik 1, memperjelas 13, menggantikan 9 |
| POJK 12 2022 | 1 | 17 | 17 | 15 | 3 | memperjelas 4, menggantikan 11, pasal_baru 5 |
| POJK 28 2022 | 1 | 17 | 16 | 15 | 13 | konflik 1, memperjelas 14, menggantikan 7, pasal_baru 8 |
| POJK 4 2022 | 1 | 1 | 1 | 1 | 1 | memperjelas 1, pasal_baru 1 |
| POJK 7 2022 | 1 | 1 | 1 | 1 | 1 | menggantikan 1, pasal_baru 1 |
| POJK 14 2021 | 1 | 6 | 6 | 6 | 1 | duplikasi 1, memperjelas 5, pasal_baru 1 |
| POJK 16 2021 | — | 0 | 0 | 0 | 1 |  |
| POJK 17 2021 | 2 | 1 | 1 | 1 | 0 | duplikasi 1, memperjelas 1 |
| POJK 18 2021 | 2 | 1 | 0 | 0 | 0 | menggantikan 1 |
| POJK 2 2021 | 1 | 2 | 1 | 1 | 0 | menggantikan 2, pasal_baru 2 |
| POJK 27 2021 | 1 | 9 | 8 | 8 | 11 | memperjelas 5, menggantikan 5, pasal_baru 10 |
| POJK 30 2021 | 1 | 4 | 1 | 1 | 0 | duplikasi 3, konflik 1, menggantikan 2, pasal_baru 2 |
| POJK 29 2020 | 1 | 9 | 6 | 6 | 7 | konflik 1, memperjelas 3, menggantikan 8, pasal_baru 5 |
| POJK 30 2020 | 1 | 6 | 3 | 3 | 0 | konflik 1, memperjelas 1, menggantikan 4 |
| POJK 13 2020 | — | 0 | 0 | 0 | 1 |  |
| POJK 2 2020 | 1 | 2 | 2 | 2 | 0 | memperjelas 1, menggantikan 1 |
| POJK 36 2020 | — | 0 | 0 | 0 | 0 |  |
| POJK 38 2020 | 1 | 1 | 1 | 1 | 1 | memperjelas 1, menggantikan 1 |
| POJK 39 2020 | 1 | 13 | 13 | 13 | 1 | memperjelas 3, menggantikan 11 |
| POJK 58 2020 | 1 | 8 | 7 | 7 | 1 | duplikasi 2, konflik 2, memperjelas 5, menggantikan 2, pasal_baru 4 |
| POJK 60 2020 | — | 0 | 0 | 0 | 5 |  |
| POJK 64 2020 | 1 | 18 | 12 | 11 | 6 | duplikasi 3, memperjelas 5, menggantikan 9, pasal_baru 7 |
| POJK 48 2020 | 1 | 6 | 6 | 6 | 5 | duplikasi 1, memperjelas 4, menggantikan 3, pasal_baru 3 |
| POJK 14 2019 | 1 | 5 | 5 | 5 | 11 | memperjelas 6, menggantikan 5, pasal_baru 5 |
| POJK 19 2019 | 1 | 1 | 1 | 0 | 0 | pasal_baru 1 |
| POJK 23 2019 | 1 | 16 | 14 | 14 | 0 | duplikasi 1, memperjelas 8, menggantikan 8 |
| POJK 32 2019 | — | 0 | 0 | 0 | 0 |  |
| POJK 38 2019 | 1 | 5 | 5 | 5 | 5 | memperjelas 1, menggantikan 5, pasal_baru 5 |
| POJK 43 2019 | 1 | 2 | 1 | 1 | 0 | menggantikan 1, pasal_baru 1 |
| POJK 44 2019 | 1 | 4 | 4 | 4 | 1 | memperjelas 3, menggantikan 1, pasal_baru 1 |

Dilewati: POJK|27|2022 → POJK|11|2016: belum di KB

## Batas evaluasi ini

- Peraturan perubahan hanya bisa menguji *objek sama vs baru* dan *menggantikan*. `konflik` (dua aturan berbeda yang sama-sama berlaku) tidak pernah muncul di dalamnya; contohnya perlu dilabel DPEA lewat validasi sampling (FR-HRM-11/12).
- Pasal diubah yang redaksinya hampir tidak berubah menaikkan angka positif; pasal yang ditulis ulang total menurunkannya. Keduanya nyata terjadi dan sengaja tidak disaring.
