# Ambang kemiripan harmonisasi — hasil simulasi (ISU-06 / #28)

*23 November 2026 · Data/ML (Fathir) · menindaklanjuti Weekly #10, keputusan 3–5.*
*Angka dapat diulang: `hero harmonisasi evaluasi -n 60` (mode terarah) dan
`hero harmonisasi evaluasi -n 60 --seluruh-kb`. Laporan lengkap:
[HARMONISASI_EVALUASI.md](HARMONISASI_EVALUASI.md) · [HARMONISASI_EVALUASI_SELURUH_KB.md](HARMONISASI_EVALUASI_SELURUH_KB.md).*

## Ringkasan untuk DPEA

| Mode pembanding | Kapan dipakai | Ditampilkan (presisi ≥ 75%) | Dipertimbangkan (50–75%) | Tidak dikutip (< 50%) |
|---|---|---:|---:|---:|
| **Terarah** | draft menyebut "Perubahan atas …", "… diubah sebagai berikut", "dicabut dan dinyatakan tidak berlaku" | kemiripan ≥ **0,50** | 0,45 – 0,50 | < **0,45** |
| **Seluruh KB** | tidak ada kata kunci relasi → peraturan baru | kemiripan ≥ **0,80** | 0,55 – 0,80 | < **0,55** |

Arti "presisi 75%": dari pasal pembanding yang muncul di rentang kemiripan itu, setidaknya
3 dari 4 memang pasal yang benar (atau pasal kembar berredaksi ≥ 80% sama di peraturan lain).
Angka ini **diukur**, bukan dipilih: acuan Pak Faris (≥ 75% tampil, < 50% tidak dikutip)
dipakai sebagai syarat presisi, lalu dicari kemiripan berapa yang memenuhinya.

## Dari mana angkanya

**Data uji berlabel tanpa anotasi manual.** Peraturan perubahan menyebut sendiri pasal yang
diubah ("Ketentuan Pasal 5 diubah …") dan yang disisipkan ("disisipkan … Pasal 12A"). Pasal
yang diubah *harus* menemukan pasal bernomor sama di peraturan induknya; pasal sisipan
*tidak punya* padanan. Dipakai **45 pasangan POJK perubahan ↔ induk** (2019–2026, sumber
publik JDIH/ojk.go.id): 451 pasal diubah + 179 pasal disisipkan. Sampel naik dari 14 pasangan
(kalibrasi 2 Okt) agar angkanya stabil.

**Cara membaca tabel presisi.** Untuk setiap kemiripan *s*, diambil semua pasal yang padanan
terdekatnya punya kemiripan di *s* ± 0,05, lalu dihitung porsinya yang benar.

| Kemiripan | Terarah: presisi | Seluruh KB: presisi ketat | Seluruh KB: presisi relevan |
|---:|---:|---:|---:|
| 0,40 | 39% | 21% | 21% |
| 0,45 | 57% | 46% | 46% |
| 0,50 | 79% | 36% | 36% |
| 0,55 | 85% | 47% | 53% |
| 0,60 | 82% | 59% | 67% |
| 0,70 | 91% | 66% | 72% |
| 0,80 | 96% | 66% | 84% |
| 0,90 | 99% | 85% | 100% |

- *Presisi ketat* = tepat pasal induk bernomor sama (batas bawah).
- *Presisi relevan* = ketat + pasal terdekat yang redaksinya ≥ 80% sama dengan pasal draft
  atau pasal induknya. Diperiksa langsung: dari 130 "salah pasang" di kemiripan ≥ 0,60 (mode
  seluruh KB), **76 adalah pasal kembar di peraturan saudara** (mis. versi BPR vs BPRS) —
  memang "pasal serupa" yang layak ditunjukkan. Hanya 54 yang benar-benar tidak relevan.
- Mode seluruh KB butuh ambang lebih tinggi justru karena KB memuat banyak pasal kembar
  seperti itu; mode terarah hanya berhadapan dengan satu peraturan, sehingga 0,50 sudah cukup.

## Ambang label `objek_sama`: 0,40 → 0,45

Di bawah `objek_sama`, pasal dilabel **pasal baru** (tidak ada padanan). Nilainya dinaikkan
agar selaras dengan batas "tidak layak dikutip" di atas (di bawah 0,45 presisinya < 50%):

| | 0,40 (lama) | 0,45 (baru) |
|---|---:|---:|
| Recall pasal diubah (sweep) | 91,5% | 90,0% |
| Pasal sisipan yang keliru ditautkan ke induk | 15,6% | **11,7%** |
| Ambang Youden J (AUC 0,925) | | 0,46 |

Recall turun 1,5 poin dan tetap jauh di atas target FR-HRM-12 (≥ 70%); sebagai gantinya
seperempat tautan keliru untuk pasal sisipan hilang.

## Dampak keputusan "kata kunci dulu" (Weekly #10, keputusan 3)

| | Terarah (baru, bawaan) | Seluruh KB (cara lama) |
|---|---:|---:|
| Induk ditemukan | **45/45** lewat kata kunci | 38/45 sebagai kandidat #1 |
| Pasal diubah dipasangkan ke pasal induk yang benar | **446/451** | 343/412* |
| Recall deteksi (FR-HRM-12) | **91,8%** | 80,1% |
| Waktu per draft (median) | **0,04 detik** | 0,73 detik |

\* Mode seluruh KB tidak memuat induk yang sudah berstatus dicabut, sehingga penyebutnya lebih kecil.

Pada 137 POJK di KB lokal, kata kunci relasi terbaca di 93 dokumen: 49 perubahan (45 dari
judul "Perubahan atas …", 4 dari POJK omnibus "… diubah sebagai berikut"), 52 pencabutan
penuh, 12 pencabutan sebagian (nomor pasalnya ikut terbaca, mis. "Pasal 12 POJK Nomor
3/POJK.03/2022 … dicabut").

## Batas yang perlu diketahui

- Contoh `konflik` tidak mungkin muncul dari peraturan perubahan; ambang di sini tidak
  menguji label itu. Contohnya menunggu validasi sampling DPEA (2–3 dari 10 draft).
- Pada mode terarah, pasal draft tidak dibandingkan dengan peraturan lain di KB (sesuai
  arahan efisiensi Pak Faris). Konflik dengan peraturan ketiga hanya terlihat bila draft
  tidak menyebut relasi apa pun. `relasi.terarah: false` di `config/harmonisasi.yaml`
  mengembalikan cara lama bila DPEA membutuhkannya.
- Daftar kata kunci menunggu konfirmasi Pak Faris setelah skenario uji Hamdan
  (action item mitra Weekly #10).
