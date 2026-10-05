# Evaluasi Harmonisasi — pasangan peraturan perubahan ↔ induk

*Dihasilkan `hero harmonisasi evaluasi` pada 2026-10-02T20:10:13. Label diambil dari instruksi perubahan di teks peraturan itu sendiri ("Ketentuan Pasal N diubah", "disisipkan … Pasal NA"), bukan anotasi manual.*

## Hasil

| Ukuran | Nilai |
|---|---:|
| Pasangan dievaluasi | 14 |
| Induk menjadi kandidat #1 | 14 / 14 |
| Induk masuk 5 kandidat teratas | 14 / 14 |
| Pasal diubah (berpadanan di induk) | 213 |
| … dipasangkan ke pasal induk yang benar | 197 |
| **Recall deteksi** (padanan benar + dilabel objek yang sudah diatur) | **90.1%** (target FR-HRM-12: ≥ 70%) |
| Pasal disisipkan | 88 |
| … tidak dipasangkan ke induk | 74 |

## Kalibrasi ambang `objek_sama` (TD-07)

Kemiripan TF-IDF pasal baru ↔ pasal induk bernomor sama (positif) dibandingkan kemiripan tertinggi pasal sisipan ↔ pasal mana pun di induk (negatif).

| | Nilai |
|---|---:|
| Median positif / P10 positif | 0.811 / 0.411 |
| Median negatif / P90 negatif | 0.289 / 0.575 |
| AUC | 0.895 |
| Ambang yang disarankan (Youden J) | **0.45** (TPR 0.883, FPR 0.125) |
| Ambang yang dipakai saat ini | 0.4 |

Pengaruh ambang (pasal unik): *recall* = pasal diubah yang dipasangkan ke pasal induk yang benar dan tidak dilabel `pasal_baru`; *sisipan tertaut* = pasal sisipan yang keliru dipasangkan ke induk.

| Ambang | Recall | Sisipan tertaut ke induk |
|---:|---:|---:|
| 0.25 | 92.1% | 55.7% |
| 0.30 | 91.6% | 42.0% |
| 0.35 | 90.7% | 27.3% |
| 0.40 | 89.7% | 15.9% |
| 0.45 | 88.3% | 12.5% |
| 0.50 | 86.9% | 11.4% |
| 0.55 | 85.5% | 11.4% |

## Per pasangan

| Perubahan | Peringkat induk | Diubah | Padanan benar | Terdeteksi | Disisipkan | Label |
|---|---:|---:|---:|---:|---:|---|
| POJK 10 2026 | 1 | 6 | 6 | 6 | 3 | duplikasi 1, memperjelas 4, menggantikan 3, pasal_baru 1 |
| POJK 10 2025 | 1 | 9 | 9 | 9 | 10 | duplikasi 1, memperjelas 5, menggantikan 7, pasal_baru 6 |
| POJK 23 2025 | 1 | 42 | 39 | 39 | 10 | memperjelas 19, menggantikan 23, pasal_baru 11 |
| POJK 25 2025 | 1 | 1 | 1 | 1 | 0 | memperjelas 1 |
| POJK 29 2025 | 1 | 23 | 21 | 21 | 12 | memperjelas 7, menggantikan 18, pasal_baru 10 |
| POJK 35 2025 | 1 | 36 | 35 | 35 | 4 | memperjelas 20, menggantikan 20 |
| POJK 11 2024 | 1 | 9 | 9 | 9 | 1 | memperjelas 5, menggantikan 4, pasal_baru 1 |
| POJK 19 2024 | 1 | 9 | 7 | 7 | 1 | memperjelas 7, menggantikan 2, pasal_baru 1 |
| POJK 20 2024 | 1 | 3 | 2 | 2 | 1 | memperjelas 1, menggantikan 3 |
| POJK 36 2024 | 1 | 20 | 20 | 19 | 17 | memperjelas 15, menggantikan 8, pasal_baru 14 |
| POJK 38 2024 | 1 | 25 | 22 | 21 | 14 | duplikasi 1, memperjelas 16, menggantikan 18, pasal_baru 4 |
| POJK 1 2023 | 1 | 10 | 8 | 8 | 2 | konflik 1, memperjelas 2, menggantikan 7, pasal_baru 2 |
| POJK 2 2023 | 1 | 10 | 9 | 8 | 2 | duplikasi 2, memperjelas 3, menggantikan 4, pasal_baru 3 |
| POJK 4 2023 | 1 | 10 | 9 | 7 | 11 | memperjelas 6, menggantikan 3, pasal_baru 13 |

## Batas evaluasi ini

- Peraturan perubahan hanya bisa menguji *objek sama vs baru* dan *menggantikan*. `konflik` (dua aturan berbeda yang sama-sama berlaku) tidak pernah muncul di dalamnya; contohnya perlu dilabel DPEA lewat validasi sampling (FR-HRM-11/12).
- Pasal diubah yang redaksinya hampir tidak berubah menaikkan angka positif; pasal yang ditulis ulang total menurunkannya. Keduanya nyata terjadi dan sengaja tidak disaring.
