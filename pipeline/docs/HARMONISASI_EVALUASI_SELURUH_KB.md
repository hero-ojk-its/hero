# Evaluasi Harmonisasi — pasangan peraturan perubahan ↔ induk

*Dihasilkan `hero harmonisasi evaluasi` pada 2026-11-24T10:57:13. Label diambil dari instruksi perubahan di teks peraturan itu sendiri ("Ketentuan Pasal N diubah", "disisipkan … Pasal NA"), bukan anotasi manual.*

## Hasil

| Ukuran | Nilai |
|---|---:|
| Mode pembanding | `seluruh_kb` |
| Pasangan dievaluasi | 45 |
| Induk ditemukan lewat kata kunci relasi | 0 / 45 |
| Waktu per draft (median / maks) | 0.66 / 0.73 detik |
| Induk menjadi kandidat #1 | 34 / 45 |
| Induk masuk 5 kandidat teratas | 36 / 45 |
| Pasal diubah (berpadanan di induk) | 346 |
| … dipasangkan ke pasal induk yang benar | 308 |
| **Recall deteksi** (padanan benar + dilabel objek yang sudah diatur) | **86.1%** (target FR-HRM-12: ≥ 70%) |
| Pasal disisipkan | 156 |
| … tidak dipasangkan ke induk | 156 |

## Kalibrasi ambang `objek_sama` (TD-07)

Kemiripan (leksikal + makna) pasal baru ↔ pasal induk bernomor sama (positif) dibandingkan kemiripan tertinggi pasal sisipan ↔ pasal mana pun di induk (negatif).

| | Nilai |
|---|---:|
| Median positif / P10 positif | 0.898 / 0.636 |
| Median negatif / P90 negatif | 0.482 / 0.677 |
| AUC | 0.922 |
| Ambang yang disarankan (Youden J) | **0.66** (TPR 0.879, FPR 0.109) |
| Metode kemiripan | leksikal + makna |
| Ambang yang dipakai saat ini | 0.62 |

Pengaruh ambang (pasal unik): *recall* = pasal diubah yang dipasangkan ke pasal induk yang benar dan tidak dilabel `pasal_baru`; *sisipan tertaut* = pasal sisipan yang keliru dipasangkan ke induk.

| Ambang | Recall | Sisipan tertaut ke induk |
|---:|---:|---:|
| 0.25 | 87.5% | 60.3% |
| 0.30 | 87.5% | 60.3% |
| 0.35 | 87.5% | 60.3% |
| 0.40 | 87.5% | 57.1% |
| 0.45 | 87.2% | 48.7% |
| 0.50 | 87.2% | 37.2% |
| 0.55 | 86.1% | 26.9% |

## Simulasi ambang tampil / kutip (ISU-06, Weekly #10)

Pada jendela ±0,05 di sekitar tiap kemiripan: *presisi ketat* = porsi pasal terdekat yang tepat pasal induk bernomor sama (batas bawah); *presisi relevan* = ketat + pasal terdekat yang redaksinya ≥ 80% sama dengan pasal draft atau pasal induknya (pasal kembar di peraturan saudara) — "pasal serupa" yang memang layak dikutip.

Ambang tampil (presisi relevan ≥ 75%): **0.85** · ambang kutip (≥ 50%): **0.7** · versi ketat: {'tampil_75': 0.85, 'kutip_50': 0.7} · 308 tepat, 346 relevan dari 508 pasal.

| Kemiripan | n jendela | Presisi ketat | Presisi relevan | n ≥ kemiripan | Presisi kumulatif | Pasal benar tercakup |
|---:|---:|---:|---:|---:|---:|---:|
| 0.15 | 0 | — | — | 508 | 61% | 100% |
| 0.20 | 0 | — | — | 508 | 61% | 100% |
| 0.25 | 0 | — | — | 508 | 61% | 100% |
| 0.30 | 1 | — | — | 508 | 61% | 100% |
| 0.35 | 7 | — | — | 507 | 61% | 100% |
| 0.40 | 30 | 3% | 3% | 501 | 62% | 100% |
| 0.45 | 49 | 2% | 2% | 477 | 64% | 100% |
| 0.50 | 57 | 7% | 7% | 452 | 68% | 100% |
| 0.55 | 56 | 12% | 12% | 420 | 72% | 98% |
| 0.60 | 45 | 20% | 20% | 396 | 76% | 97% |
| 0.65 | 37 | 40% | 40% | 375 | 78% | 96% |
| 0.70 | 30 | 60% | 60% | 359 | 79% | 92% |
| 0.75 | 51 | 59% | 63% | 345 | 80% | 90% |
| 0.80 | 83 | 65% | 71% | 308 | 83% | 83% |
| 0.85 | 102 | 79% | 84% | 262 | 85% | 72% |
| 0.90 | 149 | 85% | 96% | 206 | 84% | 56% |
| 0.95 | 204 | 85% | 100% | 113 | 85% | 31% |

## Per pasangan

| Perubahan | Peringkat induk | Diubah | Padanan benar | Terdeteksi | Disisipkan | Label |
|---|---:|---:|---:|---:|---:|---|
| POJK 10 2026 | 1 | 6 | 6 | 6 | 3 | menggantikan 6, pasal_baru 3 |
| POJK 10 2025 | 1 | 9 | 9 | 9 | 10 | menggantikan 9, pasal_baru 10 |
| POJK 23 2025 | 1 | 42 | 39 | 38 | 10 | menggantikan 41, pasal_baru 12 |
| POJK 25 2025 | 1 | 1 | 1 | 1 | 0 | menggantikan 1 |
| POJK 29 2025 | 1 | 23 | 20 | 20 | 12 | menggantikan 20, pasal_baru 15 |
| POJK 35 2025 | 1 | 36 | 35 | 35 | 4 | menggantikan 35, pasal_baru 5 |
| POJK 11 2024 | 1 | 9 | 3 | 3 | 1 | duplikasi 4, memperjelas 2, menggantikan 3, pasal_baru 1 |
| POJK 19 2024 | 1 | 9 | 8 | 7 | 1 | duplikasi 1, menggantikan 7, pasal_baru 2 |
| POJK 20 2024 | 1 | 3 | 2 | 2 | 1 | duplikasi 1, menggantikan 2, pasal_baru 1 |
| POJK 36 2024 | 1 | 20 | 20 | 19 | 17 | menggantikan 19, pasal_baru 18 |
| POJK 38 2024 | 1 | 25 | 22 | 22 | 14 | duplikasi 1, menggantikan 21, pasal_baru 17 |
| POJK 1 2023 | 1 | 10 | 9 | 9 | 2 | memperjelas 1, menggantikan 9, pasal_baru 2 |
| POJK 2 2023 | 1 | 10 | 9 | 9 | 2 | duplikasi 3, menggantikan 7, pasal_baru 2 |
| POJK 4 2023 | 1 | 10 | 9 | 8 | 11 | duplikasi 1, menggantikan 8, pasal_baru 13 |
| POJK 5 2023 | — | 0 | 0 | 0 | 8 |  |
| POJK 6 2023 | — | 0 | 0 | 0 | 8 |  |
| POJK 12 2022 | 1 | 17 | 17 | 15 | 3 | menggantikan 15, pasal_baru 5 |
| POJK 28 2022 | 1 | 17 | 16 | 15 | 13 | menggantikan 15, pasal_baru 15 |
| POJK 4 2022 | 1 | 1 | 1 | 1 | 1 | menggantikan 1, pasal_baru 1 |
| POJK 7 2022 | 1 | 1 | 1 | 1 | 1 | menggantikan 1, pasal_baru 1 |
| POJK 14 2021 | 1 | 6 | 6 | 6 | 1 | duplikasi 1, menggantikan 5, pasal_baru 1 |
| POJK 16 2021 | — | 0 | 0 | 0 | 1 |  |
| POJK 17 2021 | 2 | 1 | 1 | 1 | 0 | duplikasi 1, menggantikan 1 |
| POJK 18 2021 | 2 | 1 | 0 | 0 | 0 | duplikasi 1 |
| POJK 2 2021 | 1 | 2 | 1 | 1 | 0 | duplikasi 1, menggantikan 1, pasal_baru 2 |
| POJK 27 2021 | 1 | 9 | 9 | 8 | 11 | menggantikan 8, pasal_baru 12 |
| POJK 30 2021 | 1 | 4 | 1 | 1 | 0 | duplikasi 4, konflik 1, menggantikan 1, pasal_baru 2 |
| POJK 29 2020 | 1 | 9 | 6 | 6 | 7 | menggantikan 8, pasal_baru 9 |
| POJK 30 2020 | — | 0 | 0 | 0 | 0 |  |
| POJK 13 2020 | — | 0 | 0 | 0 | 1 |  |
| POJK 2 2020 | 1 | 2 | 2 | 2 | 0 | menggantikan 2 |
| POJK 36 2020 | — | 0 | 0 | 0 | 0 |  |
| POJK 38 2020 | 1 | 1 | 1 | 1 | 1 | menggantikan 1, pasal_baru 1 |
| POJK 39 2020 | 1 | 13 | 13 | 13 | 1 | menggantikan 13, pasal_baru 1 |
| POJK 58 2020 | 1 | 8 | 7 | 7 | 1 | duplikasi 1, konflik 1, menggantikan 7, pasal_baru 6 |
| POJK 60 2020 | — | 0 | 0 | 0 | 5 |  |
| POJK 64 2020 | 1 | 18 | 12 | 12 | 6 | duplikasi 4, memperjelas 2, menggantikan 12, pasal_baru 6 |
| POJK 48 2020 | 1 | 6 | 6 | 5 | 5 | menggantikan 5, pasal_baru 6 |
| POJK 14 2019 | 1 | 5 | 5 | 5 | 11 | menggantikan 5, pasal_baru 11 |
| POJK 19 2019 | 1 | 1 | 1 | 0 | 0 | pasal_baru 1 |
| POJK 23 2019 | — | 0 | 0 | 0 | 0 |  |
| POJK 32 2019 | — | 0 | 0 | 0 | 0 |  |
| POJK 38 2019 | 1 | 5 | 5 | 5 | 5 | menggantikan 6, pasal_baru 5 |
| POJK 43 2019 | 1 | 2 | 1 | 1 | 0 | menggantikan 1, pasal_baru 1 |
| POJK 44 2019 | 1 | 4 | 4 | 4 | 1 | menggantikan 4, pasal_baru 1 |

Dilewati: POJK|27|2022 → POJK|11|2016: belum di KB

## Batas evaluasi ini

- Peraturan perubahan hanya bisa menguji *objek sama vs baru* dan *menggantikan*. `konflik` (dua aturan berbeda yang sama-sama berlaku) tidak pernah muncul di dalamnya; contohnya perlu dilabel DPEA lewat validasi sampling (FR-HRM-11/12).
- Pasal diubah yang redaksinya hampir tidak berubah menaikkan angka positif; pasal yang ditulis ulang total menurunkannya. Keduanya nyata terjadi dan sengaja tidak disaring.
