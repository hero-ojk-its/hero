"""
app/schemas/naming.py
Skema Pydantic untuk endpoint format penamaan dinamis berkas regulasi (US-20c).
"""
from datetime import date
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field


class NamingComponentItem(BaseModel):
    """Satu komponen nama berkas yang tersedia di UI."""
    key: str = Field(..., description="Kunci komponen (nama, tahun, jenis, bidang, nomor)")
    label: str = Field(..., description="Label teks untuk tombol di UI")


class NamingComponentsResponse(BaseModel):
    """Daftar komponen, pemisah, dan format default untuk pembangun nama berkas di UI."""
    components: List[NamingComponentItem]
    separators: List[str]
    wildcard: str
    default_format: List[str]
    max_components: int


class NamingSampleInput(BaseModel):
    """Sampel metadata kustom untuk pratinjau penamaan berkas."""
    title: Optional[str] = None
    regulation_number: Optional[str] = None
    regulation_type: Optional[str] = None
    release_date: Optional[date] = None
    bidang: Optional[str] = None


class NamingPreviewRequest(BaseModel):
    """Permintaan pratinjau penamaan berkas."""
    naming_format: Optional[List[str]] = Field(
        None,
        description="Daftar urutan komponen penamaan berkas pilihan pengguna",
    )
    naming_separator: Optional[str] = Field(
        " ",
        description="Pemisah antar komponen (' ', '_', '-')",
    )
    document_id: Optional[int] = Field(
        None,
        description="ID dokumen yang ada di database untuk mengambil metadata riil",
    )
    sample: Optional[NamingSampleInput] = Field(
        None,
        description="Sampel metadata ad-hoc jika tidak menggunakan document_id",
    )


class NamingPreviewResponse(BaseModel):
    """Hasil pratinjau penamaan berkas."""
    filename: str = Field(..., description="Nama berkas hasil standardisasi")
    missing_components: List[str] = Field(
        default_factory=list,
        description="Daftar komponen dalam format yang bernilai kosong (wildcard NA)",
    )
