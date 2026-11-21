"""
app/schemas/catatan_dinas.py
Skema Pydantic untuk ekspor harmonisasi format Catatan Dinas (DOCX dan PDF).
"""
from datetime import date
from typing import Any, Optional
import unicodedata

from pydantic import BaseModel, Field, field_validator


def _sanitize_string(val: Optional[str]) -> Optional[str]:
    """
    Membersihkan teks dari karakter kontrol (Cc, Cf) kecuali newline, CR, tab.
    Mengembalikan None jika hasil bersih kosong.
    """
    if val is None:
        return None
    cleaned = "".join(
        c for c in val
        if c in ("\n", "\r", "\t") or not unicodedata.category(c).startswith("C")
    )
    cleaned = cleaned.strip()
    return cleaned if cleaned else None


class CatatanDinasExportIn(BaseModel):
    format: Optional[str] = "docx"
    run_id: Optional[int] = None
    pakai_ai: Optional[bool] = False
    nomor_cd: Optional[str] = None
    yth: Optional[str] = None
    dari: Optional[str] = None
    sifat: Optional[str] = None
    lampiran: Optional[str] = None
    hal: Optional[str] = None
    tanggal: Optional[date] = None
    unit_peminta: Optional[str] = None
    nomor_nd: Optional[str] = None
    tanggal_nd: Optional[date] = None
    hal_nd: Optional[str] = None
    catatan_tambahan: Optional[str] = None
    penandatangan_jabatan: Optional[str] = None
    penandatangan_nama: Optional[str] = None
    penandatangan_nip: Optional[str] = None

    @field_validator("format")
    @classmethod
    def validate_format(cls, v: Optional[str]) -> str:
        if not v:
            return "docx"
        v_clean = str(v).lower().strip()
        if v_clean not in ("docx", "pdf"):
            raise ValueError(f"Format '{v}' tidak didukung. Format yang tersedia: docx, pdf.")
        return v_clean

    @field_validator("tanggal", "tanggal_nd", mode="before")
    @classmethod
    def parse_date_optional(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, str):
            v_strip = v.strip()
            if not v_strip:
                return None
            return v_strip
        return v

    @field_validator(
        "nomor_cd",
        "yth",
        "dari",
        "sifat",
        "lampiran",
        "hal",
        "unit_peminta",
        "nomor_nd",
        "hal_nd",
        "catatan_tambahan",
        "penandatangan_jabatan",
        "penandatangan_nama",
        "penandatangan_nip",
        mode="before",
    )
    @classmethod
    def sanitize_and_check_length(cls, v: Any, info) -> Optional[str]:
        if v is None:
            return None
        if not isinstance(v, str):
            v = str(v)
        cleaned = _sanitize_string(v)
        if not cleaned:
            return None

        # Batas panjang per field
        LIMITS = {
            "nomor_cd": (60, "Nomor Catatan Dinas"),
            "yth": (200, "Yth."),
            "dari": (200, "Dari"),
            "sifat": (60, "Sifat"),
            "lampiran": (120, "Lampiran"),
            "hal": (300, "Hal"),
            "unit_peminta": (200, "Unit Peminta"),
            "nomor_nd": (60, "Nomor Nota Dinas"),
            "hal_nd": (300, "Hal Nota Dinas"),
            "catatan_tambahan": (4000, "Catatan Tambahan"),
            "penandatangan_jabatan": (200, "Jabatan Penandatangan"),
            "penandatangan_nama": (200, "Nama Penandatangan"),
            "penandatangan_nip": (30, "NIP Penandatangan"),
        }
        limit, label = LIMITS.get(info.field_name, (200, info.field_name))
        if len(cleaned) > limit:
            raise ValueError(f"Panjang {label} melebihi batas maksimum {limit} karakter.")
        return cleaned

