"""Membaca PDF berformat matriks tanggapan (tabel berkolom) kolom demi kolom.

OJK meminta tanggapan atas rancangan peraturan lewat berkas berbentuk tabel:
satu kolom memuat batang tubuh rancangan, kolom lain memuat penjelasan dan
kolom terakhir disediakan kosong untuk tanggapan pembaca. Secara visual itu
jelas; di lapisan teks PDF tidak ada kolom sama sekali, hanya kata-kata beserta
koordinatnya. Pembacaan baris demi baris menyulam ketiga kolom menjadi satu
kalimat:

    "BPR atau BPR Syariah yang melanggar Cukup jelas. ketentuan sebagaimana …"

Akibatnya pasal tak terbaca ("Pasal 40 Pasal 40" karena dua kolom sama-sama
menyebut nomornya), nama peraturan yang dicabut hilang di tengah sisipan, dan
poin ringkasan bercampur dengan Penjelasan — temuan QA 15 Nov 2026 atas
Agustus_02 (KP2KS) dan apr_01_in (RPOJK TI BPR/BPRS).

Kolomnya dipulihkan dari **garis tabel yang digambar di berkas**, bukan dari
tebakan atas celah antarkata: sebuah x adalah batas kolom bila garis tegak di
sana menutupi lebih dari separuh tinggi halaman, dan y adalah batas baris bila
garis mendatarnya menutupi lebih dari separuh lebar halaman. Pemisahan hanya
dijalankan bila baris judul tabel benar-benar menyebut kolom yang harus dibuang
("Penjelasan", "Tanggapan"), sehingga dokumen dua kolom lain — misalnya
terjemahan Inggris OJK/BI — tidak ikut berubah.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

# Garis sel per baris pendek-pendek; yang kita cari adalah rangka tabelnya.
_RASIO_GARIS = 0.5        # panjang garis ≥ separuh tinggi/lebar halaman
_TOLERANSI = 3.0          # dua garis dianggap satu batas bila berjarak ≤ 3 pt
_MIN_HALAMAN = 0.4        # batas kolom harus muncul di ≥ 40% halaman bergaris
# Matriks tanggapan bergaris di SETIAP halaman. Satu tabel formulir di lampiran
# sebuah SEOJK hanya menguasai 1 dari 12 halaman pertama — kolomnya tidak boleh
# ikut dibuang di seluruh dokumen.
_MIN_HALAMAN_BERGARIS = 0.6
_MIN_KOLOM = 2
_MAKS_JUDUL = 40          # judul kolom selalu pendek; kalimat bukan judul

# Judul kolom. Urutan periksa: BUANG lebih dulu, karena "Tanggapan dan Usulan
# Penyesuaian" juga memuat kata "usulan".
_JUDUL_BUANG = re.compile(
    r"penjelasan|tanggapan|usulan|keterangan|catatan|masukan|komentar|saran|paraf", re.I)
_JUDUL_BADAN = re.compile(
    r"batang\s+tubuh|bunyi|rumusan|substansi|materi|naskah|rancangan|draf|isi\b|ketentuan", re.I)
_JUDUL_LABEL = re.compile(r"^(bab|pasal|ayat|angka|huruf|butir|no\.?|nomor)$", re.I)
# Label yang perlu dilengkapi namanya: sel "5" di kolom "Pasal" berarti "Pasal 5".
_LABEL_BERNOMOR = {"pasal": "Pasal", "bab": "BAB", "angka": "Angka", "butir": "Butir"}

BUANG, BADAN, LABEL = "buang", "badan", "label"


@dataclass
class RencanaKolom:
    """Batas kolom dokumen dan peran tiap kolom."""
    batas: list[float]
    peran: list[str]
    judul: list[str] = field(default_factory=list)
    # Setiap teks sel yang pernah muncul di baris judul: baris itu dicetak ulang
    # di tiap halaman dan tidak boleh ikut terbaca sebagai isi.
    teks_judul: set[str] = field(default_factory=set)

    @property
    def layak(self) -> bool:
        return BUANG in self.peran and any(p != BUANG for p in self.peran)


def _kelompok(nilai: list[float], toleransi: float = _TOLERANSI) -> list[float]:
    """Rata-ratakan koordinat yang berdempetan menjadi satu batas."""
    out: list[float] = []
    for v in sorted(nilai):
        if out and v - out[-1] <= toleransi:
            out[-1] = (out[-1] + v) / 2
        else:
            out.append(v)
    return out


def garis_halaman(page) -> tuple[list[float], list[float]]:
    """(batas kolom, batas baris) dari garis tabel yang digambar di halaman."""
    lebar, tinggi = page.rect.width, page.rect.height
    tegak: dict[float, float] = defaultdict(float)
    datar: dict[float, float] = defaultdict(float)

    def catat(x0: float, y0: float, x1: float, y1: float) -> None:
        if abs(x1 - x0) < 1.5:
            tegak[round((x0 + x1) / 2, 1)] += abs(y1 - y0)
        elif abs(y1 - y0) < 1.5:
            datar[round((y0 + y1) / 2, 1)] += abs(x1 - x0)

    try:
        drawings = page.get_drawings()
    except Exception:  # noqa: BLE001 - halaman rusak tidak boleh menggagalkan dokumen
        return [], []
    for dr in drawings:
        for item in dr.get("items", ()):
            if item[0] == "l":
                a, b = item[1], item[2]
                catat(a.x, a.y, b.x, b.y)
            elif item[0] == "re":
                r = item[1]
                if r.width < 2 or r.height < 2:
                    catat(r.x0, r.y0, r.x1, r.y1)
                else:                      # kotak sel: empat sisinya ikut dihitung
                    tegak[round(r.x0, 1)] += r.height
                    tegak[round(r.x1, 1)] += r.height
                    datar[round(r.y0, 1)] += r.width
                    datar[round(r.y1, 1)] += r.width

    kolom = _kelompok([x for x, v in tegak.items() if v >= _RASIO_GARIS * tinggi])
    baris = _kelompok([y for y, v in datar.items() if v >= _RASIO_GARIS * lebar])
    return kolom, baris


def _baris_kata(words: list[tuple]) -> list[list[tuple]]:
    """Kelompokkan kata menjadi baris cetak: rentang tegaknya saling tindih."""
    baris: list[list[tuple]] = []
    y0 = y1 = tmin = 0.0
    for w in sorted(words, key=lambda w: (w[1], w[0])):
        tinggi = max(w[3] - w[1], 1.0)
        if baris and min(y1, w[3]) - max(y0, w[1]) >= 0.5 * min(tinggi, tmin):
            baris[-1].append(w)
            y0, y1, tmin = min(y0, w[1]), max(y1, w[3]), min(tmin, tinggi)
        else:
            baris.append([w])
            y0, y1, tmin = w[1], w[3], tinggi
    return baris


def _teks_sel(words: list[tuple]) -> list[str]:
    return [" ".join(w[4] for w in sorted(r, key=lambda w: w[0])).strip()
            for r in _baris_kata(words)]


def _sel(words: list[tuple], batas: list[float], i: int,
         atas: float | None = None, bawah: float | None = None) -> list[tuple]:
    kiri, kanan = batas[i], batas[i + 1]
    out = []
    for w in words:
        x, y = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
        if kiri - 1 <= x <= kanan + 1 and (atas is None or atas - 1 <= y <= bawah + 1):
            out.append(w)
    return out


def _peran(judul: str) -> str | None:
    judul = judul.strip()
    if not judul:
        return None
    if _JUDUL_BUANG.search(judul):
        return BUANG
    if _JUDUL_BADAN.search(judul):
        return BADAN
    if _JUDUL_LABEL.match(judul):
        return LABEL
    return None


def rencana_matriks(doc, maks_halaman: int = 12) -> RencanaKolom | None:
    """Batas kolom dan peran kolom dokumen, atau ``None`` bila ini bukan matriks.

    Batas kolom diambil dari gabungan halaman — satu halaman kadang kehilangan
    satu garis (sel BAB dan Pasal yang dibiarkan menyatu), dan memakai batas
    halaman itu sendiri akan menggabungkan dua kolom di situ saja.
    """
    jumlah = min(doc.page_count, maks_halaman)
    if jumlah < 1:
        return None
    hitung: dict[float, int] = defaultdict(int)
    bergaris = 0
    contoh: list[tuple] = []
    for i in range(jumlah):
        try:
            page = doc[i]
        except Exception:  # noqa: BLE001
            continue
        kolom, baris = garis_halaman(page)
        if len(kolom) < _MIN_KOLOM + 1:
            continue
        bergaris += 1
        for x in kolom:
            hitung[x] += 1
        contoh.append((page, baris))
    if bergaris < max(1, _MIN_HALAMAN_BERGARIS * jumlah):
        return None

    batas = _kelompok([x for x, n in hitung.items() if n >= max(1, _MIN_HALAMAN * bergaris)])
    if len(batas) < _MIN_KOLOM + 1:
        return None

    # Judul kolom dibaca dari baris judul tabel. Judulnya kerap bertingkat —
    # "Draft Peraturan" membentang di atas "Batang Tubuh | Penjelasan" — dan
    # baris yang PALING BAWAH lah yang benar-benar menamai tiap kolom, maka
    # baris berikutnya menimpa yang sebelumnya.
    suara: list[dict[int, str]] = []
    teks_judul: set[str] = set()
    for page, baris in contoh:
        words = page.get_text("words")
        judul_halaman: dict[int, str] = {}
        for j in range(len(baris) - 1):
            judul = {}
            for k in range(len(batas) - 1):
                teks = " ".join(_teks_sel(_sel(words, batas, k, baris[j], baris[j + 1])))
                if teks:
                    judul[k] = teks
            if sum(1 for t in judul.values() if _peran(t)) >= 2 \
                    and all(len(t) <= _MAKS_JUDUL for t in judul.values()):
                judul_halaman.update(judul)
                teks_judul.update(_samakan(t) for t in judul.values())
        if judul_halaman:
            suara.append(judul_halaman)

    # Baris judul tabel tanggapan dicetak ulang di tiap halaman. Satu tabel
    # yang judulnya hanya muncul sekali adalah tabel biasa, bukan matriks.
    if len(suara) < min(2, len(contoh)):
        return None
    judul_akhir: list[str] = []
    for k in range(len(batas) - 1):
        pilihan = [s.get(k, "") for s in suara if s.get(k)]
        judul_akhir.append(max(set(pilihan), key=pilihan.count) if pilihan else "")
    peran = [_peran(j) or BADAN for j in judul_akhir]
    rencana = RencanaKolom(batas=batas, peran=peran, judul=judul_akhir,
                           teks_judul=teks_judul)
    return rencana if rencana.layak else None


_HEADER_NORM = re.compile(r"[^a-z0-9]+")
_NOMOR_POLOS = re.compile(r"^\(?(\d{1,3}[A-Za-z]?|[IVXLC]{1,6})\)?\.?$")
_AYAT_POLOS = re.compile(r"^\((\d{1,2})\)\.?$")


def _samakan(teks: str) -> str:
    return _HEADER_NORM.sub(" ", teks.lower()).strip()


def teks_matriks(page, rencana: RencanaKolom) -> str:
    """Teks halaman dengan kolom tanggapan/penjelasan dibuang dan nomor pasal
    serta ayat dari kolom label dikembalikan ke depan isinya."""
    words = [w for w in page.get_text("words") if w[4].strip()]
    if not words:
        return ""
    _, baris = garis_halaman(page)
    if len(baris) < 2:
        baris = [page.rect.y0, page.rect.y1]
    batas = rencana.batas
    judul_norm = set(rencana.teks_judul) | {_samakan(j) for j in rencana.judul if j}

    keluaran: list[str] = []
    for j in range(len(baris) - 1):
        atas, bawah = baris[j], baris[j + 1]
        sel_teks: list[list[str]] = []
        for k in range(len(batas) - 1):
            sel_teks.append(_teks_sel(_sel(words, batas, k, atas, bawah)))
        isi = [" ".join(s) for s in sel_teks]
        # Baris judul tabel tercetak ulang di setiap halaman; ia bukan isi.
        terbaca = [t for t in isi if t]
        if terbaca and all(_samakan(t) in judul_norm for t in terbaca):
            continue

        label: list[str] = []
        badan: list[str] = []
        for k, lines in enumerate(sel_teks):
            if not lines or rencana.peran[k] == BUANG:
                continue
            if rencana.peran[k] == LABEL:
                label.extend(_label_baris(rencana.judul[k], lines))
            else:
                badan.extend(lines)
        if label or badan:
            keluaran.extend(label + badan)
    return "\n".join(keluaran)


def _label_baris(judul: str, lines: list[str]) -> list[str]:
    """Isi sel kolom label → baris teks yang dikenali pengurai struktur.

    Sel di kolom "Pasal" hanya memuat angkanya ("5"); tanpa nama kolomnya
    dikembalikan, pasal itu tetap tak terbaca. Sel yang sudah berbunyi
    "Pasal 5" atau "BAB I" dibiarkan apa adanya.
    """
    nama = _LABEL_BERNOMOR.get(judul.strip().lower())
    out: list[str] = []
    for line in lines:
        teks = line.strip()
        if not teks:
            continue
        ayat = _AYAT_POLOS.match(teks)
        if ayat:
            out.append(f"({ayat.group(1)})")
        elif nama and _NOMOR_POLOS.match(teks):
            out.append(f"{nama} {teks.strip('().')}")
        else:
            out.append(teks)
    return out
