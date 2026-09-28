"""
app/services/naming_service.py
Layanan standardisasi penamaan berkas dokumen regulasi dan ekstraksi metadata nama.
"""
from dataclasses import dataclass
from datetime import date
import re
from typing import Optional

from app.services.file_validation import sanitize_filename

REGULATION_TYPE_ALIASES = {
    "POJK": "POJK",
    "PERATURAN OTORITAS JASA KEUANGAN": "POJK",
    "SEOJK": "SEOJK",
    "SE OJK": "SEOJK",
    "SURAT EDARAN OTORITAS JASA KEUANGAN": "SEOJK",
    "UU": "UU",
    "UNDANG-UNDANG": "UU",
    "UNDANG UNDANG": "UU",
    "PP": "PP",
    "PERATURAN PEMERINTAH": "PP",
    "PERPRES": "PERPRES",
    "PERATURAN PRESIDEN": "PERPRES",
    "PERMENKEU": "PERMENKEU",
    "PMK": "PERMENKEU",
    "PERATURAN MENTERI KEUANGAN": "PERMENKEU",
    "PADK": "PADK",
    "PERATURAN ANGGOTA DEWAN KOMISIONER": "PADK",
    "PBI": "PBI",
    "PERATURAN BANK INDONESIA": "PBI",
    "PERDA": "PERDA",
    "PERATURAN DAERAH": "PERDA",
}


@dataclass(frozen=True)
class NamingInput:
    regulation_number: Optional[str]
    title: Optional[str]
    regulation_type: Optional[str]
    release_date: Optional[date]


def normalize_regulation_type(raw: Optional[str]) -> Optional[str]:
    """
    Normalisasi jenis regulasi: trim, uppercase, dan petakan alias standar.
    """
    if not raw or not raw.strip():
        return None
    cleaned = re.sub(r"\s+", " ", raw.strip()).upper()
    return REGULATION_TYPE_ALIASES.get(cleaned, cleaned)


def extract_year(inp: NamingInput) -> Optional[int]:
    """
    Mengekstrak tahun dari release_date atau dari 4 digit tahun terakhir di regulation_number.
    """
    if inp.release_date and inp.release_date.year:
        return inp.release_date.year

    if inp.regulation_number:
        years = re.findall(r"\b(19\d\d|20\d\d)\b", inp.regulation_number)
        if years:
            return int(years[-1])

    return None


def is_metadata_sufficient(inp: NamingInput) -> bool:
    """
    Menentukan apakah metadata dokumen sudah cukup untuk penamaan dan penempatan otomatis.
    Cukup jika regulation_number terisi ATAU (regulation_type terisi dan release_date terisi).
    Judul saja tidak dihitung karena bisa jadi hanya nama berkas asli.
    """
    has_number = bool(inp.regulation_number and inp.regulation_number.strip())
    has_type = bool(inp.regulation_type and inp.regulation_type.strip())
    has_date = bool(inp.release_date is not None)

    return has_number or (has_type and has_date)


def build_standard_filename(
    inp: NamingInput,
    *,
    template: str = "{nomor} {judul} {tahun}",
    wildcard: str = "NA",
    max_length: int = 150,
) -> str:
    """
    Membangun nama berkas PDF baku berdasarkan template dan input metadata.
    Jika melebihi max_length, bagian judul dipotong di batas kata.
    """
    template = template or "{nomor} {judul} {tahun}"
    wildcard = wildcard or "NA"
    max_length = max_length or 150

    # 1. Nomor regulasi
    if inp.regulation_number and inp.regulation_number.strip():
        num_clean = inp.regulation_number.strip().replace("/", "-").replace("\\", "-")
        nomor_str = re.sub(r"\s+", " ", num_clean).strip()
    else:
        nomor_str = wildcard

    # 2. Jenis regulasi
    norm_type = normalize_regulation_type(inp.regulation_type)
    jenis_str = norm_type if norm_type else wildcard

    # 3. Tahun
    year = extract_year(inp)
    tahun_str = str(year) if year is not None else wildcard

    # 4. Judul
    if inp.title and inp.title.strip():
        judul_clean = re.sub(r"\s+", " ", inp.title.strip())
    else:
        judul_clean = wildcard

    def _clean_field(val: str) -> str:
        # Hapus karakter terlarang: / \ : * ? " < > |
        cleaned = re.sub(r'[/\\:*?"<>|]', "", val)
        return re.sub(r"\s+", " ", cleaned).strip()

    # Helper untuk format dan sanitize
    def render_filename(title_candidate: str) -> str:
        safe_title = _clean_field(title_candidate)
        safe_nomor = _clean_field(nomor_str)
        formatted = template.format(
            nomor=safe_nomor,
            judul=safe_title,
            tahun=tahun_str,
            jenis=jenis_str,
        )
        if not formatted.lower().endswith(".pdf"):
            formatted = f"{formatted}.pdf"
        return sanitize_filename(formatted, max_len=2000)

    full_result = render_filename(judul_clean)
    if len(full_result) <= max_length:
        return sanitize_filename(full_result, max_len=max_length)

    # Jika melebihi max_length, potong kata judul dari belakang sampai muat
    words = judul_clean.split()
    while words:
        words.pop()
        candidate_title = " ".join(words)
        candidate_filename = render_filename(candidate_title)
        if len(candidate_filename) <= max_length:
            return sanitize_filename(candidate_filename, max_len=max_length)

    return sanitize_filename(render_filename(""), max_len=max_length)



