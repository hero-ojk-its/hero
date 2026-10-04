"""
app/services/naming_service.py
Layanan standardisasi penamaan berkas dokumen regulasi dan ekstraksi metadata nama.
Mendukung penamaan dinamis berdasarkan urutan komponen pilihan pengguna (US-20c).
"""
from dataclasses import dataclass
from datetime import date
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple, Union

from fastapi import HTTPException

from app.crawlers.url_utils import extract_regulation_year
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
    "PERATURAN ADK": "PADK",
    "PERATURAN ANGGOTA DEWAN KOMISIONER": "PADK",
    "PERATURAN ANGGOTA DEWAN KOMISIONER OTORITAS JASA KEUANGAN": "PADK",
    "PERATURAN ANGGOTA DEWAN KOMISIONER OJK": "PADK",
    "KDK": "KDK",
    "KEPUTUSAN DEWAN KOMISIONER": "KDK",
    "KEPUTUSAN DEWAN KOMISIONER OTORITAS JASA KEUANGAN": "KDK",
    "PDK": "PDK",
    "PERATURAN DEWAN KOMISIONER": "PDK",
    "PBI": "PBI",
    "PERATURAN BANK INDONESIA": "PBI",
    "PERDA": "PERDA",
    "PERATURAN DAERAH": "PERDA",
}

VALID_NAMING_COMPONENTS = ["nama", "nomor", "tahun", "jenis", "bidang"]
COMPONENT_ORDER_UI = ["nama", "tahun", "jenis", "bidang", "nomor"]
COMPONENT_LABELS = {
    "nama": "Nama",
    "tahun": "Tahun",
    "jenis": "Jenis",
    "bidang": "Bidang",
    "nomor": "Nomor",
}
ALLOWED_SEPARATORS = [" ", "_", "-"]
DEFAULT_NAMING_FORMAT = ["nomor", "nama", "tahun"]
DEFAULT_NAMING_SEPARATOR = " "
DEFAULT_WILDCARD = "NA"
MAX_COMPONENTS = 8


@dataclass(frozen=True)
class NamingInput:
    regulation_number: Optional[str] = None
    title: Optional[str] = None
    regulation_type: Optional[str] = None
    release_date: Optional[date] = None
    bidang: Optional[str] = None
    original_filename: Optional[str] = None
    regulation_year: Optional[int] = None


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
    Mengekstrak tahun regulasi berdasarkan urutan prioritas resmi (Langkah 12b):
    1. Tahun yang sudah diekstrak / regulation_year
    2. Tahun dari nomor resmi
    3. Tahun dari judul
    4. Tahun dari nama berkas (OneDrive)
    5. Tahun dari release_date
    """
    if inp.regulation_year is not None:
        return inp.regulation_year

    return extract_regulation_year(
        regulation_number=inp.regulation_number,
        title=inp.title,
        filename=inp.original_filename,
        release_date=inp.release_date,
    )


def is_metadata_sufficient(inp: NamingInput) -> bool:
    """
    Menentukan apakah metadata dokumen sudah cukup untuk penamaan dan penempatan otomatis.
    Cukup jika regulation_number terisi ATAU (regulation_type terisi dan release_date/regulation_year terisi).
    Judul saja tidak dihitung karena bisa jadi hanya nama berkas asli.
    """
    has_number = bool(inp.regulation_number and inp.regulation_number.strip())
    has_type = bool(inp.regulation_type and inp.regulation_type.strip())
    has_date_or_year = bool(inp.release_date is not None or inp.regulation_year is not None)

    return has_number or (has_type and has_date_or_year)


def validate_naming_format(components: Any) -> List[str]:
    """
    Validasi daftar komponen naming_format.
    - Panjang 1-8.
    - Komponen yang sama boleh muncul lebih dari sekali.
    - Kunci tidak dikenal -> raises HTTPException(422).
    - Menerima 'judul' sebagai alias lama untuk 'nama'.
    """
    if components is None:
        return list(DEFAULT_NAMING_FORMAT)

    if not isinstance(components, (list, tuple)):
        raise HTTPException(
            status_code=422,
            detail="naming_format harus berupa array/daftar string komponen.",
        )

    if len(components) < 1 or len(components) > MAX_COMPONENTS:
        raise HTTPException(
            status_code=422,
            detail=f"Jumlah komponen naming_format harus antara 1 dan {MAX_COMPONENTS} (diterima: {len(components)}).",
        )

    validated: List[str] = []
    for comp in components:
        if not isinstance(comp, str):
            raise HTTPException(
                status_code=422,
                detail="Setiap elemen naming_format harus berupa string.",
            )
        cleaned = comp.strip().lower()
        if cleaned == "judul":
            cleaned = "nama"
        if cleaned not in VALID_NAMING_COMPONENTS:
            valid_list = ", ".join(f"'{c}'" for c in VALID_NAMING_COMPONENTS)
            raise HTTPException(
                status_code=422,
                detail=f"Komponen naming_format tidak valid: '{comp}'. Komponen yang didukung: {valid_list}.",
            )
        validated.append(cleaned)

    return validated


def validate_naming_separator(sep: Any) -> str:
    """
    Validasi pemisah penamaan (naming_separator).
    Salah satu dari ' ', '_', '-' (default ' ').
    """
    if sep is None:
        return DEFAULT_NAMING_SEPARATOR

    if not isinstance(sep, str) or sep not in ALLOWED_SEPARATORS:
        valid_list = ", ".join(f"'{s}'" for s in ALLOWED_SEPARATORS)
        raise HTTPException(
            status_code=422,
            detail=f"Pemisah naming_separator tidak valid: '{sep}'. Pemisah yang didukung: {valid_list}.",
        )

    return sep


def parse_template_to_components(template: str) -> Tuple[List[str], str]:
    """
    Mengurai template penamaan format string (misal '{nomor} {judul} {tahun}')
    menjadi daftar komponen dan pemisah.
    """
    placeholders = re.findall(r"\{([^}]+)\}", template)
    comps = []
    for p in placeholders:
        p_clean = p.strip().lower()
        if p_clean == "judul":
            p_clean = "nama"
        if p_clean in VALID_NAMING_COMPONENTS:
            comps.append(p_clean)

    # Deteksi pemisah
    sep = " "
    if "_" in template and " " not in template:
        sep = "_"
    elif "-" in template and " " not in template:
        sep = "-"

    return comps if comps else list(DEFAULT_NAMING_FORMAT), sep


def _clean_field(val: str) -> str:
    r"""Ganti / dan \ dengan -, hapus karakter terlarang : * ? \" < > |, dan rapikan whitespace."""
    if not val:
        return ""
    replaced = val.replace("/", "-").replace("\\", "-")
    cleaned = re.sub(r'[:*?"<>|]', "", replaced)
    return re.sub(r"\s+", " ", cleaned).strip()


def build_standard_filename(
    inp: NamingInput,
    *,
    naming_format: Optional[List[str]] = None,
    naming_separator: Optional[str] = None,
    template: Optional[str] = None,
    wildcard: str = DEFAULT_WILDCARD,
    max_length: int = 150,
) -> str:
    """
    Membangun nama berkas PDF baku berdasarkan format komponen atau template lama.
    Precedence: naming_format > template > DEFAULT_NAMING_FORMAT.
    Jika melebihi max_length, bagian nama (judul) dipotong di batas kata.
    """
    wildcard = wildcard or DEFAULT_WILDCARD
    max_length = max_length or 150

    # 1. Tentukan komponen dan separator
    if naming_format is not None:
        comps = validate_naming_format(naming_format)
        sep = validate_naming_separator(naming_separator)
    elif template is not None:
        comps, inferred_sep = parse_template_to_components(template)
        sep = validate_naming_separator(naming_separator) if naming_separator else inferred_sep
    else:
        comps = list(DEFAULT_NAMING_FORMAT)
        sep = validate_naming_separator(naming_separator)

    # 2. Nilai komponen
    # Nomor
    if inp.regulation_number and inp.regulation_number.strip():
        nomor_str = _clean_field(inp.regulation_number.strip()) or wildcard
    else:
        nomor_str = wildcard

    # Jenis
    norm_type = normalize_regulation_type(inp.regulation_type)
    jenis_str = _clean_field(norm_type) if norm_type else wildcard

    # Tahun
    year = extract_year(inp)
    tahun_str = str(year) if year is not None else wildcard

    # Bidang
    if inp.bidang and inp.bidang.strip():
        bidang_str = _clean_field(inp.bidang.strip()) or wildcard
    else:
        bidang_str = wildcard

    # Nama / Judul
    if inp.title and inp.title.strip() and inp.title.strip() != wildcard:
        raw_nama = inp.title.strip()
    elif inp.original_filename and inp.original_filename.strip():
        stem = Path(inp.original_filename.strip()).stem
        raw_nama = stem if stem and stem != wildcard else wildcard
    else:
        raw_nama = wildcard
    nama_str = _clean_field(raw_nama) if raw_nama != wildcard else wildcard

    def render_filename(custom_nama: str) -> str:
        safe_custom_nama = _clean_field(custom_nama) if custom_nama != wildcard else wildcard
        if not safe_custom_nama:
            safe_custom_nama = wildcard

        val_map = {
            "nomor": nomor_str,
            "jenis": jenis_str,
            "tahun": tahun_str,
            "bidang": bidang_str,
            "nama": safe_custom_nama,
        }

        parts = [val_map.get(c, wildcard) for c in comps]
        formatted = sep.join(parts)
        if not formatted.lower().endswith(".pdf"):
            formatted = f"{formatted}.pdf"
        return sanitize_filename(formatted, max_len=2000)

    full_result = render_filename(nama_str)
    if len(full_result) <= max_length:
        return sanitize_filename(full_result, max_len=max_length)

    # Jika melebihi max_length, potong kata nama/judul dari belakang sampai muat
    if nama_str != wildcard:
        # 1. Coba potong kata per spasi
        words = nama_str.split(" ")
        if len(words) > 1:
            while words:
                words.pop()
                cand = " ".join(words).strip()
                if cand:
                    cand_fn = render_filename(cand)
                    if len(cand_fn) <= max_length:
                        return sanitize_filename(cand_fn, max_len=max_length)
        # 2. Coba potong kata per underscore (misal nama berkas snake_case)
        tokens = nama_str.split("_")
        if len(tokens) > 1:
            while tokens:
                tokens.pop()
                cand = "_".join(tokens).strip("_")
                if cand:
                    cand_fn = render_filename(cand)
                    if len(cand_fn) <= max_length:
                        return sanitize_filename(cand_fn, max_len=max_length)
        # 3. Potong karakter langsung berdasarkan sisa kuota panjang nama
        dummy = render_filename("X")
        overhead = len(dummy) - 1
        avail = max(1, max_length - overhead)
        cand = nama_str[:avail].rstrip(" _-")
        if cand:
            return sanitize_filename(render_filename(cand), max_len=max_length)

    return sanitize_filename(render_filename(""), max_len=max_length)



