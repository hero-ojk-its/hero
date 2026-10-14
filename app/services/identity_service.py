"""
app/services/identity_service.py
Layanan untuk resolusi identitas dokumen dan kunci kanonik peraturan.
"""
import re
from typing import Optional, Union

ALLOWED_OJK_TYPES = {"POJK", "SEOJK", "PADK", "SEDK", "PDK", "KDK"}


def fallback_identity_key(
    regulation_type: Optional[str],
    regulation_number: Optional[str],
    regulation_year: Optional[Union[int, str]] = None,
) -> Optional[str]:
    """
    Cadangan pembangkit kunci identitas kanonik (JENIS|NOMOR|TAHUN) bila kunci_identitas
    tidak dikirim oleh lapisan data.

    Aturan:
    - Hanya untuk jenis OJK: POJK, SEOJK, PADK, SEDK, PDK, KDK.
    - Hanya bila nomor diawali bilangan (11/POJK.03/2022 -> 11, 36 Tahun 2024 -> 36).
    - Tahun harus diketahui (dari regulation_year, atau dari nomor bila memuat /YYYY atau Tahun YYYY).
    - Menghasilkan format: JENIS|NOMOR|TAHUN (misal: POJK|11|2022).
    - Selain itu mengembalikan None. Jangan menebak untuk jenis lain (PBI, UU, dsb).
    """
    if not regulation_type or not isinstance(regulation_type, str):
        return None

    clean_type = regulation_type.strip().upper()
    if clean_type not in ALLOWED_OJK_TYPES:
        return None

    if not regulation_number or not isinstance(regulation_number, str):
        return None

    # Nomor harus diawali bilangan
    m_num = re.match(r"^\s*(\d+)", regulation_number)
    if not m_num:
        return None
    num_str = m_num.group(1)

    # Deteksi tahun
    year_str: Optional[str] = None
    if regulation_year is not None:
        y_candidate = str(regulation_year).strip()
        if re.match(r"^(19|20)\d{2}$", y_candidate):
            year_str = y_candidate

    if not year_str:
        # Cek dari nomor bila memuat /YYYY atau Tahun YYYY
        m_yr = re.search(r"(?:/|[Tt]ahun\s+)(19\d{2}|20\d{2})\b", regulation_number)
        if m_yr:
            year_str = m_yr.group(1)

    if not year_str:
        return None

    return f"{clean_type}|{num_str}|{year_str}"
