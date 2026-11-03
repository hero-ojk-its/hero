"""
app/services/judul_service.py
Fungsi pemeriksa judul hasil ekstraksi ML/Pipeline untuk mendeteksi penanda isi peraturan
atau paragraf yang terlalu panjang (Langkah 35, FR-SCR-04a / QA Hamdan).
"""
import re
from dataclasses import dataclass
from typing import Optional

from app.config import settings


@dataclass
class HasilJudul:
    status: str  # "ok" | "dipotong" | "ditolak"
    judul: str
    alasan: Optional[str] = None


# Penanda struktur atau isi peraturan perundang-undangan Indonesia
# Bila muncul di tengah judul ekstraksi (setelah karakter ke-15), menandakan
# bahwa pipeline ekstraksi menelan isi peraturan ke dalam judul dokumen.
POLA_PENANDA_ISI = re.compile(
    r"(?:"
    r"DENGAN\s+RAHMAT\s+TUHAN"
    r"|Menimbang\b"
    r"|Mengingat\b"
    r"|MEMUTUSKAN\b"
    r"|Menetapkan\s*:"
    r"|BAB\s+[IVXLCDM0-9]+\b"
    r"|Pasal\s+\d+\b"
    r"|(?<=[:\s])bahwa\s"
    r")",
    re.IGNORECASE,
)


def hitung_batas_kalimat(teks: str) -> int:
    """
    Menghitung batas kalimat (pola [.;] +[A-Z]) dengan mengecualikan singkatan umum
    nomor regulasi seperti 'No. 5', 'Nomor. 12', atau titik di dalam nomor peraturan
    seperti '11/POJK.03/2016' atau '1.2'.
    """
    # 1. Lindungi singkatan No. / Nomor.
    t = re.sub(r"\bNo\.\s*", "No_", teks, flags=re.IGNORECASE)
    t = re.sub(r"\bNomor\.\s*", "Nomor_", t, flags=re.IGNORECASE)
    # 2. Lindungi titik di antara alfanumerik (misal POJK.03, 1.2, UU.No)
    t = re.sub(r"(?<=[A-Za-z0-9])\.(?=[A-Za-z0-9])", "_", t)
    # 3. Cari pola [.;] +[A-Z]
    matches = re.findall(r"[.;]\s+[A-Z]", t)
    return len(matches)


BATAS_KOLOM_TITLE_DB = 255


def _cek_aturan_panjang_dan_paragraf(teks: str) -> Optional[str]:
    """
    Memeriksa aturan 3: terlalu panjang atau berbentuk paragraf.
    Mengembalikan alasan penolakan bila melanggar, atau None bila lolos.
    Menjaga panjang kolom database (255 karakter) dan setting judul_maks_karakter.
    """
    maks_karakter = getattr(settings, "judul_maks_karakter", 300)
    batas_efektif = min(maks_karakter, BATAS_KOLOM_TITLE_DB)
    maks_kata = getattr(settings, "judul_maks_kata", 45)

    if len(teks) > batas_efektif:
        return "terlalu_panjang"
    if len(teks.split()) > maks_kata:
        return "terlalu_banyak_kata"
    if hitung_batas_kalimat(teks) >= 2:
        return "berbentuk_paragraf"
    return None


def periksa_judul(judul: str) -> HasilJudul:
    """
    Fungsi murni untuk memeriksa judul hasil ekstraksi regulasi:
    1. Normalisasi spasi.
    2. Penanda isi peraturan (setelah karakter ke-15).
    3. Terlalu panjang (>300 karakter / >45 kata) atau berbentuk paragraf (>= 2 batas kalimat).
    4. Selain itu ok.
    """
    if not judul:
        return HasilJudul(status="ditolak", judul="", alasan="judul_kosong")

    # 1. Normalisasi spasi
    j = re.sub(r"\s+", " ", judul).strip()
    if not j:
        return HasilJudul(status="ditolak", judul="", alasan="judul_kosong")

    # 2. Penanda isi peraturan setelah karakter ke-15
    if len(j) > 15:
        match = POLA_PENANDA_ISI.search(j[15:])
        if match:
            pos = 15 + match.start()
            potong = j[:pos].rstrip(" .,;:-")
            if len(potong) >= 10:
                # Periksa apakah hasil potongan lolos aturan panjang/paragraf
                alasan_potong = _cek_aturan_panjang_dan_paragraf(potong)
                if alasan_potong is None:
                    return HasilJudul(status="dipotong", judul=potong, alasan="mengandung_isi_peraturan")
            return HasilJudul(status="ditolak", judul=j, alasan="mengandung_isi_peraturan")

    # 3. Terlalu panjang atau berbentuk paragraf
    alasan = _cek_aturan_panjang_dan_paragraf(j)
    if alasan is not None:
        return HasilJudul(status="ditolak", judul=j, alasan=alasan)

    # 4. Judul valid
    return HasilJudul(status="ok", judul=j, alasan=None)

